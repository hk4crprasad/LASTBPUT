# Hospital GreenOps build evidence

Contract: `Hospital_GreenOps_Codex_Build_Plan.md`. Scope: aggregate operations and sustainability only.

| Milestone | Status | Evidence / open checks |
|---|---|---|
| M0 | Validated locally; Compose verification pending | Web production build passed. API readiness passed with real PostgreSQL 18.3, Redis 7.4.8, source-built MinIO under rootless Podman. Lockfiles committed to workspace. |
| M1 | Passed slice checks | Exact source counts 17,280 / 8,640; null water preserved; repeat import idempotent; forced RLS and zone/pool/CSRF checks passed. 17 invalid stress fill metrics quarantined while raw rows retained. |
| M2 | API checks passed; UI in progress | SQL/API consumption and units agree. Context and evidence services use world clock. |
| M3 | Passed slice checks | Exact ML pins, preserved feature contract, checksum trust, chronological purge, no future feature leakage and reload agreement. 9 M1–M3 checks passed in 4.88 s. |
| M4 | Validation running | Numeric fixtures, balance/priority engine, durable job interface and audited action lifecycle implemented. |
| M5 | In progress | Independent seeded full-domain world generator and typed domain ledgers/CRUD implemented; generation and balance checks running. |
| M6 | Pending | Provider and grounded tools |
| M7 | Pending | Agent reactions |
| M8 | Pending | Reporting/admin |
| M9 | Pending | Verification/recovery |
| M10 | Pending | Handoff |

No real-provider verification or public deployment has occurred.
