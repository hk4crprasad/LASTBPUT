# Packaged run: actual synthetic evaluation

Run date: 8 October 2026. Base seed 42; shifted seed 1043. Four fictional zones; 168 configured inpatient beds. No real hospital data.

Base data: 17,280 rows (180 days). Shifted world: 8,640 rows (90 days). Missing water remains missing; affected model rows are excluded according to the declared feature contract.

## Forecast results

MAE units are kWh per hourly zone interval or L per hourly zone interval. Improvement is against same-hour-last-week baseline; negative means worse. Each lead predicts that hourly interval, not a summed day total.

| Model | Test MAE | Test baseline improvement | Stress baseline improvement | Test range coverage | Stress range coverage |
|---|---:|---:|---:|---:|---:|
| energy_kwh_1h | 0.727 | 39.93% | -33.62% | 87.52% | 36.02% |
| water_l_1h | 8.855 | 51.43% | 21.10% | 91.24% | 56.09% |
| energy_kwh_6h | 0.802 | 33.65% | -127.08% | 86.63% | 11.64% |
| water_l_6h | 10.035 | 45.04% | 25.37% | 90.39% | 64.32% |
| energy_kwh_24h | 0.904 | 25.69% | -74.11% | 84.66% | 32.22% |
| water_l_24h | 11.416 | 37.62% | 20.80% | 88.86% | 65.24% |

Ranges nominally target 90%, using a validation residual quantile. They have no guaranteed coverage under distribution shift. Stress coverage degrades materially; do not reuse these ranges as calibrated operational uncertainty in a new facility.

## Anomaly results

| World | Precision | Recall | Event detection | False-positive rows/facility-day |
|---|---:|---:|---:|---:|
| test | 2.27% | 3.57% | 25.00% (4 eligible events) | 2.39 |
| shifted_world | 5.94% | 12.08% | 65.00% (20 eligible events) | 5.10 |

## Engineering interpretation

- Base-world forecast improvements are demonstrated synthetic results only. They are not energy/water savings.
- Energy candidates fail the shifted-world baseline comparison. Keep a useful baseline and add out-of-distribution/context checks; do not promote these candidates globally.
- Water candidates beat the stress baseline but interval coverage degrades. New-facility calibration and wider/appropriate uncertainty handling are needed.
- Generic Isolation Forest has weak sample/event detection on held-out data. It remains experimental; use contextual expected-demand residuals and known activity schedules before release.
- Report raw row-alert counts honestly. A production incident policy needs persistence, deduplication, calibrated operating thresholds and an approved false-alert budget.
- Private labels are used only for evaluating anomaly results. They do not tune thresholds, choose training rows or enter model features.
- Models and stress worlds share a simulator family. Independent generator mechanisms and real pilot observations are still needed for generalization.

## Executed verification

8 unittest checks passed. Data validation passed for both worlds. Six forecast models and one Isolation Forest were fitted; joblib artifacts and held-out prediction CSVs were saved. Scenario CLI executed and produced explicit water, battery and waste calculations.

No browser UI, authenticated API, PostgreSQL deployment or live source integration is implemented by this offline starter.
