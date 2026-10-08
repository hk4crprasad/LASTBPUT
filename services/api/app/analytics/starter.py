"""Seeded synthetic data, leakage-aware forecasts, and synthetic evaluation.

Run from the bundle root: python -m greenops.pipeline --help
This implements the offline data/ML foundation, not the planned web product.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor, IsolationForest
from sklearn.metrics import mean_absolute_error, mean_squared_error, precision_recall_fscore_support

ZONES = [("ICU", 24, 11.0), ("WARD_A", 72, 6.0), ("WARD_B", 72, 5.8), ("OPD", 0, 8.5)]
TARGETS = ("energy_kwh", "water_l")
FEATURES = ["zone_code", "hour_sin", "hour_cos", "weekday", "lead_hours", "occupied_beds",
            "opd_visits", "temperature_c", "temperature_proxy_c", "energy_current",
            "water_current", "energy_lag24", "water_lag24", "energy_lag168",
            "water_lag168", "energy_roll24", "water_roll24"]
STATES = {"open": {"acknowledged"}, "acknowledged": {"in_progress"},
          "in_progress": {"resolved", "acknowledged"}, "resolved": {"verified", "in_progress"},
          "verified": {"closed", "in_progress"}, "closed": {"open"}}




def weather_profile(hour: np.ndarray) -> np.ndarray:
    return 4.0 * np.sin(2 * np.pi * (hour - 8) / 24)




def validate_data(data: pd.DataFrame) -> dict:
    required = {"observed_at", "zone_id", "energy_kwh", "water_l", "source_type", "quality", "occupied_beds", "bed_capacity"}
    if not required.issubset(data.columns):
        raise ValueError(f"Missing columns: {required - set(data.columns)}")
    if data.duplicated(["zone_id", "observed_at"]).any():
        raise ValueError("Duplicate zone/timestamp")
    if not (data.source_type == "synthetic").all():
        raise ValueError("Starter accepts synthetic data only")
    if (data.occupied_beds > data.bed_capacity).any() or (data.occupied_beds < 0).any():
        raise ValueError("Invalid occupied bed count")
    for col in ["energy_kwh", "water_l", "waste_stock_kg", "bin_fill_pct"]:
        if (data[col].dropna() < 0).any():
            raise ValueError(f"Negative measurement: {col}")
    t = pd.to_datetime(data.observed_at, utc=True)
    for _, idx in data.groupby("zone_id").groups.items():
        delta = t.loc[idx].sort_values().diff().dropna()
        if not (delta == pd.Timedelta(hours=1)).all():
            raise ValueError("Expected a complete hourly timestamp grid")
    return {"rows": int(len(data)), "zones": int(data.zone_id.nunique()),
            "missing_water_rows": int(data.water_l.isna().sum()), "validation": "passed"}


def features(data: pd.DataFrame, lead: int) -> pd.DataFrame:
    """Each row is a forecast issued AFTER the current hourly reading is known.

    Features use only origin-time observations and known calendar values.
    No interpolation/bfill, no hidden fault label, and no realized future weather.
    Future temperature is a persistence + daily-cycle proxy, not an external forecast.
    """
    if lead not in (1, 6, 24):
        raise ValueError("Supported leads: 1, 6, 24")
    parts = []
    for _, group in data.groupby("zone_id"):
        g = group.sort_values("observed_at").copy()
        origin = pd.to_datetime(g.observed_at, utc=True)
        future = origin + pd.Timedelta(hours=lead)
        f = pd.DataFrame(index=g.index)
        f["zone_id"] = g.zone_id
        f["origin_time"] = origin
        f["target_time"] = future
        f["zone_code"] = g.zone_code
        f["hour_sin"] = np.sin(2*np.pi*future.dt.hour/24)
        f["hour_cos"] = np.cos(2*np.pi*future.dt.hour/24)
        f["weekday"] = future.dt.weekday
        f["lead_hours"] = lead
        for col in ["occupied_beds", "opd_visits", "temperature_c"]:
            f[col] = g[col]
        f["temperature_proxy_c"] = (g.temperature_c.to_numpy() - weather_profile(origin.dt.hour.to_numpy())
                                     + weather_profile(future.dt.hour.to_numpy()))
        for prefix, target in [("energy", "energy_kwh"), ("water", "water_l")]:
            f[f"{prefix}_current"] = g[target]
            f[f"{prefix}_lag24"] = g[target].shift(24)
            f[f"{prefix}_lag168"] = g[target].shift(168)
            f[f"{prefix}_roll24"] = g[target].rolling(24, min_periods=18).mean()
            f[f"target_{target}"] = g[target].shift(-lead)
            # Target timestamp minus one week; value is already observed at origin.
            f[f"baseline_{target}"] = g[target].shift(168-lead)
        # Complete current observations and lags required. No hidden imputation.
        f = f.dropna(subset=FEATURES)
        parts.append(f)
    return pd.concat(parts).sort_values(["origin_time", "zone_id"]).reset_index(drop=True)


def chronological_masks(frame: pd.DataFrame, all_times: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series, dict]:
    t = np.sort(pd.to_datetime(all_times, utc=True).unique())
    train_boundary, validation_boundary = pd.Timestamp(t[int(.6*len(t))]), pd.Timestamp(t[int(.8*len(t))])
    # A training target cannot cross into validation, even if its origin is earlier.
    train = frame.target_time < train_boundary
    validation = (frame.origin_time >= train_boundary) & (frame.target_time < validation_boundary)
    test = frame.origin_time >= validation_boundary
    info = {"train_target_before": train_boundary.isoformat(), "validation_target_before": validation_boundary.isoformat(),
            "test_origin_from": validation_boundary.isoformat(), "policy": "Shared time cutoffs across all zones; boundary-crossing targets purged"}
    return train, validation, test, info


def regression_metrics(y: np.ndarray, pred: np.ndarray, baseline: np.ndarray, width: float) -> dict:
    mae = float(mean_absolute_error(y, pred))
    bmae = float(mean_absolute_error(y, baseline))
    return {"n": int(len(y)), "mae": mae, "rmse": float(np.sqrt(mean_squared_error(y, pred))),
            "weekly_baseline_mae": bmae, "mae_improvement_pct": 100*(bmae-mae)/bmae if bmae else None,
            "validation_residual_half_width": width,
            "empirical_interval_coverage": float(np.mean(np.abs(y-pred) <= width)),
            "interval_note": "Nominal 90% residual interval, calibrated on validation; test coverage is reported, not assumed"}


def model_predict(bundle: dict, frame: pd.DataFrame) -> np.ndarray:
    return np.maximum(0, bundle["model"].predict(frame[bundle["feature_columns"]]))


def anomaly_features(data: pd.DataFrame) -> pd.DataFrame:
    g = data.sort_values(["zone_id", "observed_at"])
    out = g[["observed_at", "zone_id"]].copy()
    context = np.maximum(g.occupied_beds + g.opd_visits*.5, 6)
    out["energy_per_activity"] = g.energy_kwh / context
    out["water_per_activity"] = g.water_l / context
    out["energy_change"] = g.groupby("zone_id").energy_kwh.diff()
    out["water_change"] = g.groupby("zone_id").water_l.diff()
    out["temperature_c"] = g.temperature_c
    out["cleaning_schedule"] = g.cleaning_schedule
    out["hour_sin"] = np.sin(2*np.pi*pd.to_datetime(g.observed_at, utc=True).dt.hour/24)
    return out.dropna().reset_index(drop=True)


def detection_metrics(frame: pd.DataFrame, pred: np.ndarray, labels: pd.DataFrame) -> dict:
    score = frame[["observed_at", "zone_id"]].copy()
    score["observed_at"] = pd.to_datetime(score.observed_at, utc=True)
    lab = labels.copy()
    lab["observed_at"] = pd.to_datetime(lab.observed_at, utc=True)
    score["predicted_fault"] = pred
    merged = score.merge(lab, on=["observed_at", "zone_id"], how="left", validate="one_to_one")
    if merged.is_fault.isna().any():
        raise ValueError("Missing private evaluation labels")
    precision, recall, f1, _ = precision_recall_fscore_support(merged.is_fault, pred, average="binary", zero_division=0)
    evaluated_events = merged[merged.is_fault == 1].groupby("event_id")
    detected, delays = [], []
    for _, event in evaluated_events:
        positives = event[event.predicted_fault == 1]
        detected.append(not positives.empty)
        if not positives.empty:
            delays.append((positives.observed_at.min()-event.observed_at.min()).total_seconds()/3600)
    span_days = max((merged.observed_at.max()-merged.observed_at.min()).total_seconds()/86400, 1)
    return {"n": int(len(merged)), "precision": float(precision), "recall": float(recall), "f1": float(f1),
            "false_positive_rows_per_facility_day": float(((merged.is_fault == 0)&(merged.predicted_fault == 1)).sum()/span_days),
            "evaluated_events": len(detected), "event_detection_rate": float(np.mean(detected)) if detected else None,
            "median_detection_delay_hours": float(np.median(delays)) if delays else None,
            "note": "Raw row alerts, no deduplication. Event delay is measured from first event row in evaluation window; boundary events may be partial."}




def reserve_simulation(tank_l: float, demand_lph: float, inflow_lph: float = 0, excess_lph: float = 0) -> dict:
    if min(tank_l, demand_lph, inflow_lph, excess_lph) < 0:
        raise ValueError("Reserve parameters cannot be negative")
    drain = demand_lph + excess_lph - inflow_lph
    return {"usable_reserve_l": tank_l, "net_drain_lph": drain,
            "hours_to_depletion": tank_l/drain if drain>0 else None,
            "depleting": drain>0, "assumptions": "Constant flow, no quality inference, segregated usable reserve"}


def waste_service_deadline(fill_pct: float, growth_pph: float, age_hours: float | None,
                           threshold_pct: float = 85, configured_age_limit: float = 24) -> dict:
    if min(fill_pct, growth_pph, threshold_pct, configured_age_limit) < 0 or (age_hours is not None and age_hours<0):
        raise ValueError("Waste parameters cannot be negative")
    fill_eta = max(0, (threshold_pct-fill_pct)/growth_pph) if growth_pph>0 else (0.0 if fill_pct>=threshold_pct else None)
    age_eta = max(0, configured_age_limit-age_hours) if age_hours is not None else None
    known = [x for x in (fill_eta, age_eta) if x is not None]
    return {"hours_to_fill_threshold": fill_eta, "hours_to_configured_age_limit": age_eta,
            "service_within_hours": min(known) if known else None, "age_status": "known" if age_hours is not None else "unknown",
            "policy_note": "Demo age limit is configurable internal SOP; no legal compliance certification"}


def transition_action(current: str, new: str, evidence: str | None = None) -> str:
    if new not in STATES.get(current, set()):
        raise ValueError(f"Invalid transition {current} -> {new}")
    if new in ("verified", "closed") and not evidence:
        raise ValueError("Verification/closure needs evidence")
    return new






