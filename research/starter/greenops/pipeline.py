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


def write_json(path: Path, value: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def weather_profile(hour: np.ndarray) -> np.ndarray:
    return 4.0 * np.sin(2 * np.pi * (hour - 8) / 24)


def generate_world(seed: int, days: int, stress: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Return observations, private ground-truth labels, and configurable facility state.

    Stress changes coefficients, event amplitudes, drift and frequency, not just noise.
    No real facility or patient data are used. Intervals end at observed_at.
    """
    if days < 30:
        raise ValueError("Use at least 30 days so weekly lags and evaluation are available")
    rng = np.random.default_rng(seed)
    times = pd.date_range("2025-01-01T00:00:00Z", periods=days * 24, freq="h")
    hour = times.hour.to_numpy()
    day = np.arange(len(times)) / 24
    temperature = 29 + 5 * np.sin(2 * np.pi * day / 365) + weather_profile(hour) + rng.normal(0, .8, len(times))
    if stress:
        temperature += 2.5
    pieces, events = [], []
    for zone_code, (zone, beds, base_kw) in enumerate(ZONES):
        inpatient = beds > 0
        occ_fraction = np.clip(.68 + .08 * np.sin(2 * np.pi * day / 14 + zone_code) + rng.normal(0, .04, len(times)), .35, .98)
        occupied = np.rint(beds * occ_fraction).astype(int)
        clinic_open = (hour >= 8) & (hour <= 17) & (times.weekday.to_numpy() < 6)
        opd = np.where(clinic_open, rng.poisson(24 if not inpatient else 2, len(times)), 0)
        cleaning = np.isin(hour, [6, 14, 20]).astype(int)
        scale = (1 + .0007 * day) if stress else np.ones(len(times))
        energy = (base_kw + .11 * occupied + .15 * opd + .55 * np.maximum(temperature - 25, 0)
                  + 1.7 * cleaning + .8 * clinic_open) * scale
        water = (22 + 2.3 * occupied + 2.5 * opd + 85 * cleaning) * scale
        energy *= (1.18 if stress else 1)
        water *= (1.12 if stress else 1)
        energy += rng.normal(0, .45 if not stress else .9, len(times))
        water += rng.normal(0, 8 if not stress else 15, len(times))
        event_id = np.full(len(times), "", dtype=object)
        event_kind = np.full(len(times), "normal", dtype=object)
        # Varied non-overlapping sustained faults; ground truth is stored separately.
        for j, start_day in enumerate(range(12 + zone_code, days - 3, 21 if not stress else 16)):
            start = start_day * 24 + int(rng.integers(0, 12))
            duration = int(rng.integers(7, 19))
            end = min(start + duration, len(times))
            kind = "water_excess" if j % 2 == 0 else "energy_excess"
            eid = f"{'stress' if stress else 'base'}-{seed}-{zone}-{j}"
            if kind == "water_excess":
                water[start:end] += rng.uniform(100, 210) if not stress else rng.uniform(65, 170)
            else:
                energy[start:end] += rng.uniform(6, 13) if not stress else rng.uniform(4, 10)
            event_id[start:end] = eid
            event_kind[start:end] = kind
            events.append({"event_id": eid, "zone_id": zone, "kind": kind,
                           "start": times[start].isoformat(), "end_exclusive": times[min(end, len(times)-1)].isoformat()})
        waste = np.maximum(0, (.014 * occupied + .025 * opd + .04) + rng.normal(0, .03, len(times)))
        capacity_kg = 25.0 if inpatient else 15.0
        fill, ages, pickup, stocks = [], [], [], []
        stock = 0.0
        oldest = 0
        for i, new_kg in enumerate(waste):
            collected = bool(hour[i] in (7, 19))
            # Explicit delayed pickup under stress, not an unlabelled fill reset.
            if stress and (i // 24) % 23 == 0:
                collected = False
            if collected:
                stock, oldest = 0.0, 0
            stock += float(new_kg)
            oldest += 1
            stocks.append(stock)
            fill.append(100 * stock / capacity_kg)
            ages.append(oldest)
            pickup.append(int(collected))
        observed_water = np.maximum(water, 0)
        observed_energy = np.maximum(energy, 0)
        quality = np.full(len(times), "ok", dtype=object)
        # Missing readings are missing, never zero; labels still describe physical events.
        missing = rng.choice(len(times), max(1, len(times) // (140 if stress else 400)), replace=False)
        observed_water[missing] = np.nan
        quality[missing] = "missing_water"
        piece = pd.DataFrame({"observed_at": times, "facility_id": "DEMO_HOSPITAL", "zone_id": zone,
                              "zone_code": zone_code, "bed_capacity": beds, "occupied_beds": occupied,
                              "opd_visits": opd, "temperature_c": np.round(temperature, 3),
                              "cleaning_schedule": cleaning, "energy_kwh": np.round(observed_energy, 4),
                              "water_l": np.round(observed_water, 3), "waste_generated_kg": np.round(waste, 4),
                              "waste_stock_kg": np.round(stocks, 4), "bin_fill_pct": np.round(fill, 3),
                              "oldest_batch_age_hours": ages, "pickup_recorded": pickup,
                              "source_type": "synthetic", "quality": quality})
        pieces.append(piece)
        for t, eid, kind in zip(times, event_id, event_kind):
            events.append({"observed_at": t.isoformat(), "zone_id": zone, "event_id": eid,
                           "kind": kind, "is_fault": int(kind != "normal")})
    data = pd.concat(pieces).sort_values(["zone_id", "observed_at"]).reset_index(drop=True)
    labels = pd.DataFrame([e for e in events if "observed_at" in e])
    intervals = [e for e in events if "start" in e]
    state = {"facility_id": "DEMO_HOSPITAL", "facility_type": "hospital", "source_type": "synthetic",
             "seed": seed, "days": days, "stress": stress, "bed_capacity": sum(z[1] for z in ZONES),
             "interval_semantics": "Resource usage is for the hourly interval ending at observed_at",
             "tank_usable_l": 30000, "essential_water_lph": 3000,
             "battery_deliverable_kwh": 120, "essential_load_kw": 60,
             "events": intervals,
             "waste_note": "Aggregate simulated biomedical stream only; category/batch ledger is specified in the full plan"}
    return data, labels, state


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


def train(data_dir: Path, out_dir: Path) -> dict:
    data = pd.read_csv(data_dir/"observations.csv", parse_dates=["observed_at"])
    stress = pd.read_csv(data_dir/"stress_observations.csv", parse_dates=["observed_at"])
    labels = pd.read_csv(data_dir/"private_labels.csv", keep_default_na=False)
    stress_labels = pd.read_csv(data_dir/"stress_private_labels.csv", keep_default_na=False)
    validate_data(data)
    validate_data(stress)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {"scope": "Synthetic-only validation, not real hospital accuracy", "forecast": {},
              "selection": "Single preset model per target/horizon; validation calibrates interval only; test/stress never tunes models",
              "versions": {"python": platform.python_version(), "sklearn": sklearn.__version__,
                           "pandas": pd.__version__, "numpy": np.__version__, "joblib": joblib.__version__},
              "data_sha256": hashlib.sha256((data_dir/"observations.csv").read_bytes()).hexdigest()}
    for lead in (1, 6, 24):
        frame, sf = features(data, lead), features(stress, lead)
        train_mask, val_mask, test_mask, splits = chronological_masks(frame, data.observed_at)
        report["split_policy"] = splits
        for target in TARGETS:
            needed = [f"target_{target}", f"baseline_{target}"]
            tr = frame.loc[train_mask].dropna(subset=needed)
            va = frame.loc[val_mask].dropna(subset=needed)
            te = frame.loc[test_mask].dropna(subset=needed)
            ss = sf.dropna(subset=needed)
            if min(len(tr), len(va), len(te), len(ss)) < 24:
                raise ValueError("Insufficient eligible time-ordered rows")
            model = HistGradientBoostingRegressor(max_iter=110, max_leaf_nodes=15, learning_rate=.07,
                                                  l2_regularization=2, early_stopping=False, random_state=42)
            model.fit(tr[FEATURES], tr[f"target_{target}"])
            bundle = {"model": model, "feature_columns": FEATURES, "target": target, "horizon_hours": lead,
                      "synthetic_only": True, "training_cutoff": splits["train_target_before"]}
            width = float(np.quantile(np.abs(va[f"target_{target}"].to_numpy()-model_predict(bundle, va)), .9))
            bundle["validation_residual_half_width"] = width
            filename = f"{target}_{lead}h.joblib"
            joblib.dump(bundle, out_dir/filename)
            evaluation = {"train_rows": len(tr), "validation_rows": len(va), "units": "kWh" if target=="energy_kwh" else "L",
                          "test": regression_metrics(te[f"target_{target}"].to_numpy(), model_predict(bundle, te), te[f"baseline_{target}"].to_numpy(), width),
                          "shifted_world": regression_metrics(ss[f"target_{target}"].to_numpy(), model_predict(bundle, ss), ss[f"baseline_{target}"].to_numpy(), width)}
            report["forecast"][f"{target}_{lead}h"] = evaluation
            predictions = te[["zone_id", "origin_time", "target_time"]].copy()
            predictions["actual"] = te[f"target_{target}"]
            predictions["prediction"] = model_predict(bundle, te)
            predictions["lower"] = np.maximum(0, predictions.prediction-width)
            predictions["upper"] = predictions.prediction+width
            predictions["baseline"] = te[f"baseline_{target}"]
            predictions.to_csv(out_dir/f"predictions_{target}_{lead}h.csv", index=False)
    af, asf = anomaly_features(data), anomaly_features(stress)
    cut = pd.Timestamp(report["split_policy"]["train_target_before"])
    test_cut = pd.Timestamp(report["split_policy"]["test_origin_from"])
    at = pd.to_datetime(af.observed_at, utc=True)
    a_cols = [c for c in af.columns if c not in ("observed_at", "zone_id")]
    detector = IsolationForest(n_estimators=120, contamination=.025, random_state=42, n_jobs=1)
    # Ground-truth labels do not select rows or tune this unsupervised detector.
    detector.fit(af.loc[at<cut, a_cols])
    atest = af.loc[at>=test_cut]
    report["anomaly"] = {"test": detection_metrics(atest, (detector.predict(atest[a_cols])==-1).astype(int), labels),
                         "shifted_world": detection_metrics(asf, (detector.predict(asf[a_cols])==-1).astype(int), stress_labels),
                         "score_semantics": "Outlier score, not a calibrated fault/leak probability"}
    joblib.dump({"model": detector, "feature_columns": a_cols, "synthetic_only": True}, out_dir/"anomaly.joblib")
    write_json(out_dir/"evaluation.json", report)
    return report


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


def demo(out_dir: Path) -> dict:
    scenarios = {"source_type": "synthetic", "water_normal": reserve_simulation(30000, 3000),
                 "water_with_possible_excess": reserve_simulation(30000, 3000, excess_lph=500),
                 "water_after_assumed_repair": reserve_simulation(30000, 3000),
                 "battery": {"deliverable_energy_kwh": 120, "essential_load_kw": 60, "runtime_hours": 2,
                             "note": "Deliverable capacity already includes losses; no second efficiency multiplier"},
                 "waste_fill_priority": waste_service_deadline(70, 8, 5),
                 "waste_age_priority": waste_service_deadline(30, 2, 23),
                 "waste_age_unknown": waste_service_deadline(30, 2, None)}
    write_json(out_dir/"demo_scenarios.json", scenarios)
    return scenarios


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--days", type=int, default=180)
    g.add_argument("--stress-days", type=int, default=90)
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--out", type=Path, default=Path("data"))
    t = sub.add_parser("train")
    t.add_argument("--data", type=Path, default=Path("data"))
    t.add_argument("--out", type=Path, default=Path("artifacts"))
    d = sub.add_parser("demo")
    d.add_argument("--out", type=Path, default=Path("artifacts"))
    args = parser.parse_args()
    if args.command == "generate":
        args.out.mkdir(parents=True, exist_ok=True)
        validations = {}
        for prefix, seed, days, shift in [("", args.seed, args.days, False), ("stress_", args.seed+1001, args.stress_days, True)]:
            data, labels, state = generate_world(seed, days, shift)
            validations[prefix or "base"] = validate_data(data)
            data.to_csv(args.out/f"{prefix}observations.csv", index=False)
            labels.to_csv(args.out/f"{prefix}private_labels.csv", index=False)
            write_json(args.out/f"{prefix}facility.json", state)
        write_json(args.out/"validation.json", validations)
        print(json.dumps(validations, indent=2))
    elif args.command == "train":
        report = train(args.data, args.out)
        print(json.dumps({"models": len(report["forecast"])+1, "evaluation": str(args.out/"evaluation.json"),
                          "scope": report["scope"]}, indent=2))
    else:
        print(json.dumps(demo(args.out), indent=2))


if __name__ == "__main__":
    main()
