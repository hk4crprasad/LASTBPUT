# Guided demo

1. Sign in as hospital administrator. Choose `base_v1`, inspect the virtual clock and open Energy/Water. Compare source units, chart totals, gaps and forecast target points. Switch to `stress_v1` and inspect model failures and quality quarantine.
2. Choose `extended_v1`. Visit Facility, Assets, Water, Environment, Parking and Safety. Inspect actual ledger records and scope-bound evidence. In Waste, distinguish category stock/age/handover metadata from the original aggregate stream.
3. Add an asset and assigned inspection; create a red-category waste batch and record a scoped pickup/handover. Refresh to see persisted state and signed movement balances.
4. In What-if Studio, run a six-hour grid outage plus pump failure. Inspect protected fire reserves, essential service priorities, sensitivity paths, unmet demand and assumptions. Save a second intervention under the same baseline and compare; export the saved scenario JSON.
5. With the provider enabled, ask: “Read current water reserves and explain protected fire storage.” Tool progress, scope, units and evidence come from authorized records. Use Investigate mode to request a scenario and draft a follow-up proposal. Review and assign the proposal in Action Centre.
6. Advance an action through acknowledged, in progress and resolved. A different supervisor/admin must verify it with evidence, then close it. A stale version or missing evidence is rejected.
7. Enable a versioned monitor policy for the facility to demonstrate trigger/cooldown activity. Autonomous task creation remains opt-in and narrowly bounded. Inspect trigger, policy, tools, proposal/task and failures in Agent Activity.
8. Generate a daily report and download CSV, HTML and PDF. Inspect illustrative tariff/factor versions and missing consumption coverage. Run the documented backup/restore check.

For an automated HTTP walkthrough run `scripts/demo.py`. It waits for actual job outcomes and checks downloaded artifacts; it does not manufacture action success or savings. Repeated demo runs leave identifiable demonstration records.
