# Hospital Operations + GreenOps: runnable data/ML starter

Yeh offline Python foundation hai: reproducible synthetic observations, six resource forecasting models, one anomaly model, held-out evaluation, reserve/waste scenario functions aur action-state checks. Full HMS web application ki architecture `Hospital_GreenOps_Technical_Workflow_Plan.md` mein specified hai; UI/backend deployment is starter mein implemented nahi hai.

Python 3.12 par verified dependency versions `requirements.txt` mein hain. Network sirf first dependency install ke liye chahiye; generation/training/demo offline chal sakte hain.

```bash
python -m venv .venv
```

Linux/macOS: `source .venv/bin/activate`. Windows PowerShell: `.venv\Scripts\Activate.ps1`.

```bash
python -m pip install -r requirements.txt
python -m greenops.pipeline generate --days 180 --stress-days 90 --seed 42
python -m greenops.pipeline train
python -m greenops.pipeline demo
python -m unittest discover -s tests -v
```

## Included outputs

- `data/observations.csv`: 180-day, four-zone base world.
- `data/stress_observations.csv`: independent 90-day shifted world with different seed, coefficients, drift and fault strength.
- `data/*private_labels.csv`: evaluation-only hidden ground truth; never an input feature.
- `data/*facility.json`: synthetic assumptions and injected event intervals.
- `artifacts/*.joblib`: six energy/water forecasts (1, 6, 24 hours) and one Isolation Forest.
- `artifacts/evaluation.json`: actual held-out/stress metrics, versions, data fingerprint and interval coverage.
- `artifacts/predictions_*.csv`: held-out predictions versus actual values/baseline.
- `artifacts/demo_scenarios.json`: explicit reserve/waste scenarios.
- `RESULTS.md`: interpretation of this packaged run.

Read `evaluation.json` and `RESULTS.md` before interpreting model quality. A model that fails to beat the weekly baseline remains a baseline candidate; synthetic performance does not establish real-hospital performance. Anomaly scores are not leak probabilities.

## Forecast contract

Each forecast origin is after the current hourly interval reading is known. Features use past/current measurements and future calendar values. Future temperature is a current-temperature + known daily-cycle proxy; realized future weather and occupancy are not used. Each direct-horizon model predicts its own target; 24-hour output is the hourly demand 24 hours ahead, not total next-day demand. All zones use common 60/20/20 temporal boundaries. Training/validation targets crossing boundaries are purged. Test and shifted-world data do not tune models. Nominal 90% symmetric residual ranges are calibrated on validation; actual test coverage is reported.

The bundled baseline detector has no deduplication or hospital-specific calibration. Raw false-positive rows per facility-day may be high. Event-level recall includes only events overlapping eligible evaluation rows; boundary events can be partial. These are research diagnostics, not a production alarm policy.

Waste data is an aggregate simulated stream, not a complete category/batch compliance ledger. That ledger, full-product telemetry and six further modules are specified in the technical plan. Starter intentionally contains no patient identities. Runtime reserve examples assume constant flow and explicitly usable reserves. Only load trusted bundled/local joblib files.

To scale data, rerun generation with `--days 365 --stress-days 180`; then retrain. Increasing duration alone does not prove generalization—vary facility configurations/generator mechanisms and later validate on real pilot data.
