# Hospital GreenOps AI — Complete Codex Build Specification

Version: 1.0 · Language: English · Prepared: 8 October 2026

## 1. Build outcome and scope

Build a complete, runnable hospital operations and sustainability decision platform from the supplied synthetic-data and ML starter. Use PostgreSQL, a real backend, a functional dashboard, reproducible training, deterministic what-if simulations, and an OpenAI-compatible chatbot and agent. Finish every module and the acceptance checks in this document; an attractive dashboard with hardcoded responses is not completion.

The hospital is the example facility for the sustainable facility intelligence problem. Keep the core configurable for other facility types. The confirmed Hospital MS scope is **facility operations and GreenOps**: buildings, zones, beds, aggregate occupancy, OPD counts, resource consumption, maintenance and operating risks. It does not include patient diagnosis, prescriptions, billing or insurance. An HMS integration supplies aggregate operating context without requiring patient identities.

The initial release is a complete synthetic demonstration. It must show where values are synthetic, forecasted, simulated or estimated. Training on synthetic data does not establish real-hospital accuracy. Preserve that distinction throughout the interface and reports.

### Required end-to-end behavior

Ingest operating data → validate and store it → calculate trends and forecasts → identify risks → show supporting evidence → run scenarios → recommend and track actions → record verification → report outcomes.

The chatbot answers questions using current authorized data. The agent can investigate across all authorized domains, run simulations, and create or update permitted software actions. Numeric calculations, permissions and action transitions belong to application services, not to the language model.

## 2. Inputs Codex must use

Attach these files to the Codex session:

1. `Hospital_GreenOps_Codex_Build_Plan.md` — this implementation contract.
2. `Hospital_GreenOps_Synthetic_ML_Starter.zip` — existing executable generator, data, models, tests and evaluation evidence.
3. If available, `Hospital_GreenOps_AI_Research_Report.md` and the original problem statement — domain background and traceability.

Extract the archive's `hospital_greenops_starter/` contents into `research/starter/`. Preserve its original files and checksums. Adapt code into the application rather than editing away the original evaluation evidence. Provide a host-side preparation command that creates a sanitized `data/public/starter/` bundle and a new manifest linking it to the original manifest. Only that sanitized bundle is available to seed/API containers.

| Supplied item | Actual contents | Required treatment |
|---|---|---|
| `data/observations.csv` | 17,280 hourly zone records: 180 days × 4 zones | Import as `base_v1` |
| `data/stress_observations.csv` | 8,640 records: 90 days × 4 zones | Import as separate `stress_v1` world |
| Zones | ICU: 24 beds; WARD_A: 72; WARD_B: 72; OPD: 0 | Total bed capacity: 168 |
| `*facility.json` | Public assumptions **and private injected-event intervals** | Explicitly allowlist public fields; remove events and hidden fault metadata |
| `*private_labels.csv` | Ground truth for offline evaluation | Training/evaluation area only; never runtime database, chatbot, agent or dashboard queries |
| Six forecast bundles | Energy/water at 1, 6 and 24-hour leads | Experimental synthetic models; preserve feature and runtime contracts |
| `anomaly.joblib` | Generic Isolation Forest detector | Experimental; not a validated hospital alarm policy |
| `evaluation.json`, `RESULTS.md` | Measured results and limitations | Display honestly in model evaluation view |
| `demo_scenarios.json` | Tested arithmetic examples | Reuse as simulation regression fixtures |

Both worlds reuse facility ID `DEMO_HOSPITAL`, zone IDs and overlapping timestamps. Add a `world_id` to runtime records. Never combine worlds into one series or treat stress rows as duplicate base rows. Application identity is `(organization_id, facility_id, world_id, zone_id, observed_at)` where appropriate.

The existing starter has no OpenAI integration. Implement a real one. The supplied aggregate waste data is not a colour-category or batch ledger; build additional synthetic records for that module.

## 3. Product modules and working screens

All twelve modules are required for the finished product. Staging the work is allowed; leaving later modules as placeholder cards is not.

| Module | Working functionality | Required screen |
|---|---|---|
| Facility / HMS operations | Buildings, floors, zones, capacities, occupancy and OPD snapshots, schedules, aggregate import | Facility configuration and operations |
| Energy | Hourly usage, load context, comparisons, forecasts, contextual anomalies and evidence | Energy explorer |
| Water | Usage, quality gaps, separate tank reserves, inflow, shortage projections | Water and reserves |
| Waste | Categories, bins, batches, aging, pickups, handovers, deadlines and missing evidence | Waste operations |
| Environment | Indoor/outdoor context, temperature, humidity, PM2.5 and CO2, configured thresholds | Environment |
| Assets / maintenance | Asset register, dependencies, telemetry, inspections and work orders | Assets and maintenance |
| Traffic / parking | Arrival/exit counts, capacity, occupancy, queue and protected route indicators | Parking |
| Safety incidents | Location, severity, incident records, hotspot counts and denominator-aware rates | Safety |
| Climate / resilience | Weather context, grid outage, pump failure, heat, rainfall and supply interruption scenarios | What-if studio |
| Sustainability / cost | Versioned tariffs and carbon factors, resource intensity and estimated costs | Sustainability |
| Action centre | Alert linkage, ownership, due dates, state transitions and verification evidence | Action board |
| Reporting / explainability | Daily briefs, trend reports, evidence links and model/assumption details | Reports and model evaluation |

Also provide login, organization/facility/world selector, overview, chatbot, agent activity, policy settings and import quality screens. Every visible control must work or explicitly describe a unavailable integration. Use English labels.

## 4. Technical stack

Use a modular monolith with a separate worker process. This reduces deployment complexity while preserving clean domain boundaries.

| Layer | Selected technology | Purpose |
|---|---|---|
| Web | Next.js, React, TypeScript | Dashboard, admin flows and chatbot |
| UI | Tailwind CSS, accessible component primitives | Consistent forms, dialogs, tables and navigation |
| Charts | Apache ECharts | Time series, forecast intervals, scenario comparison and heatmaps |
| API | Python 3.12, FastAPI, Pydantic | Typed REST, validation, authentication and SSE |
| Database | PostgreSQL 18, SQLAlchemy, Alembic, psycopg | Transactional data, time series, audit, forecasts and chat history |
| Jobs | Celery with Redis broker | Imports, inference, simulations, reports and agent runs |
| Scheduling | One Celery Beat instance | Periodic jobs; database constraints prevent duplicate effects |
| ML | Supplied NumPy / pandas / scikit-learn / joblib versions initially | Reproducible starter inference and retraining |
| LLM | Official OpenAI Python SDK behind a provider adapter | Compatible Chat Completions and function tools |
| Files | S3-compatible object storage; MinIO in local Compose | Model artifacts, report files and action evidence |
| Tests | pytest, real PostgreSQL integration tests, Playwright | Domain, authorization, integration and browser verification |
| Packaging | Docker Compose, committed dependency lockfiles | Repeatable local run and container deployment |

PostgreSQL is the source of truth. Redis loss must not lose action, chat, job or simulation state. Keep durable `jobs` and an outbox in PostgreSQL; Celery delivers work at least once. Recover undispatched/unfinished jobs using a reconciliation task. Workers use idempotency keys and transactional updates.

Do not require LangChain, a separate vector database, Kubernetes or microservices. PostgreSQL full-text search is sufficient for initial policy/SOP retrieval. Add pgvector only if a documented use case and an explicitly configured compatible embedding endpoint justify it; numeric analytics must use SQL/domain services.

Resolve compatible frontend/backend package versions at implementation time and commit lockfiles. For supplied joblib bundles, retain Python 3.12 and the starter's exact pins: NumPy 2.3.5, pandas 2.2.3, scikit-learn 1.8.0, joblib 1.5.3. If dependencies conflict, isolate the ML worker environment or retrain and record the new environment. Do not silently load bundles under a different scikit-learn version.

## 5. Repository organization

| Path | Contents |
|---|---|
| `apps/web/` | Next.js application, generated API client, page and component tests |
| `services/api/app/core/` | Settings, auth, permissions, clock, DB sessions, errors and audit |
| `services/api/app/domains/` | Facility, energy, water, waste, environment, assets, parking, safety, sustainability and actions |
| `services/api/app/analytics/` | Features, forecast serving, contextual detectors and metrics |
| `services/api/app/simulation/` | Typed scenarios, dependency graph, deterministic engine and comparison |
| `services/api/app/ai/` | Provider adapter, tools, orchestration, grounded responses and evaluations |
| `services/api/app/jobs/` | Durable job handlers, Celery tasks, outbox and schedules |
| `services/api/alembic/` | Reversible schema migrations and RLS policies |
| `packages/contracts/` | Generated TypeScript schemas / OpenAPI client |
| `data/public/` | Sanitized source fixtures, runtime synthetic configuration and manifests |
| `research/starter/` | Untouched extracted starter |
| `research/evaluation/` | Private labels, offline results and evaluation-only code |
| `scripts/` | Import, synthetic generation, train, evaluate, smoke test and demo replay |
| `infra/` | Dockerfiles, Compose, deployment and backup configuration |
| `tests/` | Cross-domain, integration, agent and end-to-end tests |
| `docs/` | Architecture, assumptions, demo script, operating runbook and build evidence |

Private research files must not enter the API/web runtime image or an agent-accessible storage bucket. Test this boundary, including sanitized configuration.

## 6. Data contract and import mapping

Store all timestamps as PostgreSQL `timestamptz`, normalized to UTC. Display the facility timezone, initially `Asia/Kolkata`. The starter's `observed_at` is the **end of an hourly usage interval**. `energy_kwh` is interval energy; it is not kW or a cumulative meter reading.

| CSV field | Canonical treatment |
|---|---|
| `observed_at` | `interval_end`; `interval_start = end - 1 hour` |
| `facility_id`, `zone_id` | Resolve stable runtime keys within selected world |
| `zone_code` | Persist source encoding for original model adapter; do not re-encode arbitrarily |
| `bed_capacity`, `occupied_beds`, `opd_visits` | Operational context snapshot; occupancy bounded by capacity |
| `temperature_c`, `cleaning_schedule` | Available context; schedule meaning retained |
| `energy_kwh` | Metric `energy.interval_kwh`, unit kWh, interval semantics |
| `water_l` | Metric `water.interval_l`, unit L; null stays missing |
| `waste_generated_kg`, `waste_stock_kg` | Aggregate waste metrics; no inferred colour category |
| `bin_fill_pct` | Aggregate source fill metric; 0–100 validation |
| `oldest_batch_age_hours` | Aggregate age observation, nullable; not a fabricated batch identity |
| `pickup_recorded` | Aggregate pickup flag; not a proof-of-handover document |
| `source_type`, `quality` | Provenance plus metric-specific quality flags |

Import process: verify archive and manifest → allowlist files → sanitize configuration → create worlds and zones → validate source rows → stage/import → normalize metrics and context → write import summary and rejects → compute aggregates → enqueue inference/rules.

Use a deterministic source event identity from dataset version, zone and timestamp. Unique `(dataset_id, source_event_id)` makes a re-import idempotent. Reject duplicate conflicting values, impossible units and invalid capacities into an inspectable quarantine. Derive water-specific missing quality from the source rather than marking otherwise valid energy readings missing. Never replace missing water with zero.

Maintain a metric registry containing domain, code, unit, interval/state/cumulative semantics, supported aggregation, valid range and availability. Sum interval consumption; use time-weighted averages for rates/states where appropriate; convert cumulative meters with reset-aware differencing. Avoid double counting parent meters and submeters by defining reporting boundaries.

### Demo clock

The historical data starts in 2025. Use a per-world virtual `as_of` clock, initially the latest available complete interval. Freshness rules, batch ages, jobs and queries use that clock in demo mode. Show its timestamp prominently. System time controls authentication, audit creation and scheduling; distinguish it from event/demo time. Provide pause, advance, reset and replay endpoints restricted to demo administrators. Do not report every historical observation as stale merely because the current calendar is 2026.

## 7. Complete synthetic data generation

Keep the supplied base/stress datasets usable immediately. Add a configuration-driven generator for domains absent from the starter. New generated data must be visibly distinct from imported records and deterministic by seed/configuration version.

Generate causal worlds: occupancy and OPD drive demand; weather changes cooling; grid supply controls pumps; pumps change inflow; waste activity changes batches and pickup demand; parking arrivals reflect activity; asset modes affect telemetry. Maintain resource balances, capacities and consistent timestamps.

Required additional records: buildings/floors, assets and telemetry, separate tank types and inflow, power sources/battery/fuel, waste yellow/red/white/blue categories with actual synthetic batches and movements, pickup/handover evidence metadata, PM2.5/CO2/humidity, parking arrivals/exits and queues, structured safety incidents, tariffs, emission factors, policies and operating schedules.

Do not attach new category/batch records to imported aggregate waste while implying they reconstruct the original history. Either build a separate extended world from its own consistent generator or identify the extension as a separate synthetic stream with its own reporting boundary. Prefer `extended_v1` for the full-domain demo.

Fault catalogue: excessive energy, water leak, missing sensor, stuck sensor, pump outage, grid outage, delayed waste pickup, bin capacity pressure, heat-driven load surge, asset telemetry fault and parking surge. Keep injected truth separate from observable telemetry. The agent can infer candidates from observations; it cannot read injection names to pretend it discovered faults.

Default small extended world: one fictional hospital, at least four clinical/operating zones plus service zones, 180 days hourly context and realistic event records. Offer a configurable training campaign of six fictional facility archetypes × 12 zones × 365 days × 24 hours = 630,720 zone-hour rows. This larger campaign is a future generation option, not the size of the supplied starter.

Use independent seeds, parameter ranges, sensor-error patterns and intervention profiles for validation/test worlds. A stress world from the same generator is a shift test, not proof of real-world generalization. Store seed, generator commit, config hash, dataset hash and provenance.

## 8. PostgreSQL schema and authorization

Use UUID internal keys. Include organization, facility and world scope on world-bound data, with composite foreign keys to prevent inconsistent parent references. Keep facility setup separate from world-specific capacities/configuration overrides where needed.

| Table group | Required tables / key records |
|---|---|
| Identity | `organizations`, `users`, `memberships`, `facility_grants`, `sessions` |
| Facility | `facilities`, `buildings`, `floors`, `zones`, `zone_capacities`, `operating_schedules` |
| Worlds / import | `worlds`, `dataset_versions`, `source_events`, `import_jobs`, `import_rejects`, `metric_catalog` |
| Operations / readings | `operational_snapshots`, `observations`, `quality_events`, `aggregate_snapshots` |
| Infrastructure | `assets`, `asset_dependencies`, `asset_telemetry`, `tanks`, `tank_states`, `power_sources`, `power_states` |
| Waste | `waste_categories`, `waste_bins`, `waste_batches`, `waste_movements`, `pickups`, `handover_evidence` |
| Other domains | `environment_readings`, `parking_areas`, `parking_events`, `parking_snapshots`, `safety_incidents`, `maintenance_orders` |
| Policy / accounting | `policy_versions`, `tariff_versions`, `emission_factor_versions`, `documents`, `document_chunks` |
| ML | `model_versions`, `training_runs`, `evaluation_results`, `forecast_runs`, `forecast_points`, `detector_runs` |
| Risks / actions | `alerts`, `alert_evidence`, `actions`, `action_events`, `action_evidence`, `action_proposals` |
| Simulation | `scenario_definitions`, `simulation_runs`, `simulation_points`, `simulation_comparisons` |
| AI | `conversations`, `messages`, `agent_runs`, `tool_calls`, `ai_usage`, `agent_policies` |
| Platform | `jobs`, `outbox_events`, `audit_events`, `report_runs`, `stored_files` |

`observations`: scope keys, zone/asset reference, metric code, interval start/end or state timestamp, value, unit, quality, source type, source event ID, ingestion timestamp and dataset version. Make timestamp semantics explicit with checks. Store immutable raw public source events for lineage; hidden labels are excluded.

Use JSONB for validated configurations, tool results and evidence metadata; normal relational columns for identity, permissions, statuses, timestamps and commonly queried metrics. Use numeric precision appropriate to financial values; retain engineering units and enough precision for resource balances.

Index observations by scope/metric/zone/time; forecasts by run/zone/target time; open alerts by scope/status/severity; actions by assignee/state/due date. Benchmark indexes with real queries. Use monthly observation partitions when scale justifies them, with valid unique keys including partition keys. Do not add partition complexity merely for the small starter.

### Permission model

Implement organization admin, hospital admin, operations supervisor, maintenance technician, waste officer, sustainability officer and auditor. Enforce roles plus facility/zone/assigned-task grants at API and tool boundaries. Auditors have read/export access without operational writes; technicians have assigned scope; waste officers have waste permissions. Use HttpOnly sessions, strong password hashing, CSRF protection for cookie-authenticated mutations and production TLS. Seed documented demo users only in demo mode; generate credentials locally and never ship production defaults.

Enable and FORCE PostgreSQL RLS on tenant-owned domain tables. Use a runtime DB role that is not the owner, superuser or `BYPASSRLS`. Set transaction-local server-derived user/org identity using `set_config(..., true)`; policies check membership/grants. Do not trust a client-supplied tenant header as identity. Use dedicated migration/admin roles. Include `WITH CHECK` policies and pooled-connection isolation tests. RLS is additional protection; domain permissions remain necessary.

Cache keys include principal permission scope, world, snapshot and policy/model versions. Files and chat conversations have the same authorization boundaries as data. An agent receives the requesting user's effective permissions; background agents use explicit service-principal grants.

## 9. Analytics and model lifecycle

Use the supplied models first, with transparent experimental badges. The six bundles predict an hourly target value at lead 1, 6 or 24 hours. They do **not** predict a full 24-hour trajectory or total daily usage. Plot three supported points honestly. Extend and evaluate horizons 1–24 or train a separately evaluated daily-total model before offering those outputs as ML forecasts. Do not interpolate three points and label them a validated curve.

Preserve the starter feature order and meanings. Features include zone code, cyclic hour, weekday, lead hours, current occupancy/OPD/temperature, a temperature proxy, current energy/water, 24/168-hour lags and rolling means. Current means the known interval at forecast issue time. Do not use measured future weather, future occupancy or injected labels. Insufficient history returns unavailable or an explicitly named fallback.

Training process: dataset manifest → quality checks → chronological split shared across zones → purge targets crossing boundaries → fit transforms on training only → fit model → calibrate on validation → compare against seasonal/persistence baseline → evaluate locked test and independent stress worlds → write registry and report. Maintain immutable split manifests. Once a stress dataset guides changes, create a fresh locked test world for final assessment.

Metrics: MAE by target/horizon/zone, baseline gain, interval coverage/width, low/high activity errors, missing-data performance and shift degradation. Prediction intervals from validation residuals are empirical intervals; do not guarantee coverage under shift.

Known supplied evidence: energy baseline gains are positive on the original test but negative on stress; the generic anomaly detector has base precision approximately 2.27% and recall 3.57%. Therefore these are not production-approved models. Preserve the exact full metrics from `evaluation.json`; do not convert forecast improvement into claimed resource savings.

Implement contextual residual detection using expected usage conditioned on operating activity, hour and weather. Combine robust residual thresholds with persistence, quality gating and incident deduplication. Keep explicit rules for reserves, missing readings, waste age and essential dependencies. Distinguish observed excess from an inferred leak/fault candidate.

Registry states: `experimental_synthetic_only`, `candidate`, `approved_for_demo`, `pilot_validated`, `retired`. Demo approval means suitable for demonstration, not clinical or real-hospital validation. Define demo gates before training: no leakage, reproducible serving, baseline comparisons, measurable shift failures, bounded alert volume and calibrated incident evaluation. A failing learned component stays experimental; rule/baseline fallbacks remain available. Asset faults start with rules until adequate labels and validation exist.

Only load trusted, checksum-verified local model artifacts. Do not accept arbitrary uploaded joblib/pickle models. Inference records feature version, model version, issue time, target time, units, quality, interval method and fallback reason. Retraining creates a new version and never silently replaces an approved artifact.

## 10. Deterministic what-if simulation engine

Build a server-side discrete-time engine with default 15-minute steps and a configurable 1–72-hour horizon. Each scenario references an immutable baseline snapshot, configuration/policy versions, start time, model/baseline demand source and typed interventions. Store every result for repeatable comparison.

Support grid outages, pump failures, water supply interruption, occupancy/OPD surges, heat increases, excessive demand/leaks, delayed pickups, earlier pickups, approved nonessential schedule changes and asset restoration. Validate parameter limits and service constraints. A scenario may combine multiple events.

At each step: apply events → resolve available power and critical load priorities → determine pump/inflow availability → update water reserves and served/unmet demand → update waste batches/age/capacity → update parking and queues → accumulate cost/carbon and constraint violations. Record unmet demand and queued/rejected arrivals; do not hide them by clipping state variables.

Core balance: `next_water_L = previous_water_L + inflow_L - served_demand_L`, bounded by usable capacity. Protected fire reserves and incompatible water types are separate. Essential/nonessential demand allocation is explicit. Battery state subtracts delivered energy; use either usable deliverable capacity or an efficiency conversion, never both. Genset fuel requires its own documented load/fuel curve.

| Regression scenario | Required result |
|---|---|
| 30,000 usable L; 3,000 L/h demand; zero inflow | Reserve lasts 10 hours |
| Same tank; additional 500 L/h demand | Reserve lasts about 8.5714 hours |
| 120 deliverable kWh; essential load 60 kW | Battery lasts 2 hours |
| Waste fill 70%; growth 8 percentage points/h; fill threshold 85%; age 5 h; internal age threshold 24 h | Capacity deadline 1.875 h is earlier |
| Waste fill 30%; growth 2 pp/h; age 23 h; same thresholds | Age deadline 1 h is earlier |
| Missing oldest-batch age | Age deadline is unknown; never silently safe |

The 24-hour waste age threshold above is a configurable internal demonstration policy, not a universal legal limit. Store policy source, category applicability, jurisdiction, version and effective date. Report evidence gaps separately from threshold exceedance.

For uncertainty, simulate low/central/high demand paths and show sensitivity. Unless calibrated probabilistic input assumptions exist, call these sensitivity ranges, not statistical confidence intervals. Repair/schedule benefits are modeled deltas from the selected baseline, not measured real savings.

Scenario UI: baseline selector, event builder, sliders with units, parameter validation, dependency view, run/progress, baseline-versus-scenario charts, reserve breach timeline, unmet essential demand, waste deadlines, cost/carbon deltas and save/compare/export. A saved scenario can draft a linked action plan. Simulations must never alter observations or physically control hospital equipment.

## 11. OpenAI-compatible provider integration

Use an `LLMProvider` interface with `chat_with_tools`, optional streaming and usage reporting. Default adapter: `AsyncOpenAI(api_key=..., base_url=...)` and `client.chat.completions.create(...)`. Support a user-configured compatible endpoint and model name; do not hardcode availability of a particular model.

Official SDK configuration supports custom base URLs, and OpenAI function calling uses declared function schemas with application-executed results. Those API mechanisms support this design; compatibility with a different provider must still be tested. See technical references at the end.

Required configuration example:

```dotenv
APP_MODE=demo
FACILITY_TIMEZONE=Asia/Kolkata
DATABASE_URL=postgresql+psycopg://greenops:CHANGE_ME@postgres:5432/greenops
MIGRATION_DATABASE_URL=postgresql+psycopg://greenops_migrator:CHANGE_ME@postgres:5432/greenops
REDIS_URL=redis://redis:6379/0
OBJECT_STORAGE_ENDPOINT=http://minio:9000
OBJECT_STORAGE_BUCKET=greenops
SESSION_SECRET=GENERATE_LOCALLY
LLM_ENABLED=true
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=SET_SERVER_SIDE
OPENAI_CHAT_MODEL=SET_SUPPORTED_MODEL
OPENAI_AGENT_MODEL=SET_TOOL_CAPABLE_MODEL
LLM_SUPPORTS_TOOLS=true
LLM_SUPPORTS_STREAMING=true
LLM_SUPPORTS_STRICT_SCHEMA=false
LLM_SUPPORTS_PARALLEL_TOOL_CALLS=false
LLM_TIMEOUT_SECONDS=45
AGENT_MAX_STEPS=8
AGENT_MAX_TOOL_CALLS=16
AGENT_MAX_RUN_SECONDS=120
AGENT_MAX_OUTPUT_TOKENS=3000
AGENT_AUTONOMOUS_WRITES_ENABLED=false
```

Complete `.env.example` also covers DB bootstrap/admin credentials, object-store credentials, CORS/public URLs, job limits and demo controls. `greenops` is the restricted runtime role; `greenops_migrator` owns/migrates tables and its credentials belong only to the controlled migration process. The normal API/worker environment must not receive the migration/admin URL. Never expose provider keys through `NEXT_PUBLIC_*`, browser requests, logs or repository files.

Provider capability flags control request parameters: do not assume Responses API, strict JSON schemas, parallel calls, temperature, reasoning settings or provider-specific token fields exist everywhere. Default to sequential function execution. Only send supported parameters. Add a capability-check command that performs a real text and harmless read-tool round trip for the configured model.

If function calling is unsupported, display that agent mode is unavailable for the selected model. A text-only chatbot may use a controlled, server-fetched context bundle, clearly identified as that mode. Do not parse arbitrary prose as privileged tool calls or claim a fake tool-using agent. With no credentials, core product, simulations and deterministic reports work; chat shows configuration required.

Handle rate limits, authentication failures, timeouts, malformed arguments and unsupported capabilities. Use bounded retries, cancellation and per-user/run budgets. Avoid stacked SDK and application retries multiplying requests. Do not claim an actual provider integration passed when only a mock test ran.

## 12. How the agent sees all relevant data

The agent receives a compact facility snapshot, metric/domain catalog and typed tools that query every authorized operational domain on demand. PostgreSQL/domain services return actual values, aggregates, evidence and recorded assumptions. This is how it sees the facility comprehensively without stuffing the entire database into each prompt.

The access scope is enforced by the server, not supplied by the model. The agent cannot retrieve another tenant, unassigned facility/zone, credentials, private evaluation labels or hidden injection events. This preserves useful access to all authorized operational data while preventing leakage and fabricated fault detection.

Expose the following 19 tools. Domain-specific subservices implement their functions; include only authorized tools in each run.

| Tool | Inputs and output |
|---|---|
| `get_facility_snapshot` | Current scoped state, clock, coverage, capacities, risks and source versions |
| `list_data_catalog` | Available metrics, domains, units, supported filters and time coverage |
| `query_metric_series` | Allowlisted metric/zone/time/bucket query; measured series and quality |
| `get_operational_context` | Occupancy, OPD, cleaning and operating schedules |
| `get_assets_and_dependencies` | Scoped assets, modes, maintenance and resource dependencies |
| `get_resource_reserves` | Tanks, power availability, battery/fuel and reserve assumptions |
| `get_waste_state` | Categories, bins, batches, aging, pickups and handover evidence |
| `get_environment_state` | Indoor/outdoor readings, averaging windows and threshold evidence |
| `get_parking_and_safety` | Parking capacity/queues plus incident counts and denominators |
| `get_forecasts` | Supported target/horizon predictions, intervals, model status and fallback |
| `get_alert_evidence` | Alert details, observations, detector/rule versions and uncertainty |
| `get_actions` | Scoped action list, owner, due date, state and evidence |
| `get_sustainability_summary` | Consumption/intensity/cost/carbon with factor and boundary versions |
| `search_operating_documents` | Authorized SOP/policy chunks with titles, versions and citations |
| `run_what_if` | Validated scenario; saved run ID, results, assumptions and limitations |
| `compare_scenarios` | Baseline and saved runs; calculated comparable deltas |
| `draft_action_plan` | Persisted proposal tied to alert/scenario evidence; no automatic assignment |
| `create_action` | Permission/policy-checked creation with owner, due date and idempotency key |
| `transition_action` | Authorized state change with expected version and required evidence |

Domain queries use typed filters and parameterized SQL, not unrestricted model-written SQL. Expose metric/group/filter selection through an allowlisted query builder. Limit rows, date range, result size and query duration; provide cursor pagination and explicit `truncated` indicators. Bound expensive simulation jobs and return a run handle when asynchronous.

Every tool result includes `tool_result_id`, scope, world, snapshot/version, event `as_of`, retrieval timestamp, source type, units, coverage/quality, evidence references and limitations. Tool errors are structured and actionable. Keep exact numeric values in results; let the UI format units.

### Example read-tool contract

```json
{
  "name": "query_metric_series",
  "arguments": {
    "metric": "water.interval_l",
    "zone_ids": ["WARD_A"],
    "start": "2025-06-20T00:00:00Z",
    "end": "2025-06-21T00:00:00Z",
    "bucket": "hour",
    "limit": 200
  }
}
```

This is an illustrative schema, not a guaranteed available date range. Validate against the selected world's catalog. Scope and snapshot are injected by the server. Pydantic validates required fields, enums, units, times and ranges; reject unexpected fields. Generate provider JSON Schema from the same contracts.

Preserve stable snapshot evidence during a run. Time-series reads use a pinned data cutoff; mutable operating state uses a versioned snapshot captured at run start. If the user asks for a refresh, create a new snapshot. Before any mutation, recheck permissions, current action version and current risk state to prevent stale decisions.

## 13. Chatbot and agent orchestration

Implement separate modes sharing the same tool layer:

* **Ask:** answer, inspect evidence, query trends and run user-requested scenarios; mutations require the user's requested action plus permission checks.
* **Investigate:** multi-step read/simulate/draft workflow producing a prioritized plan and linked evidence.
* **Monitor:** scheduled/event-driven facility investigations under an explicit agent policy and service principal.

Orchestration loop:

1. Authenticate, resolve scope, capture snapshot and create an `agent_run`.
2. Load compact context, relevant conversation summary and authorized tool schemas.
3. Call the configured model with messages and tools.
4. Persist the assistant tool-call message; parse and validate each declared function call.
5. Execute registered functions with server context, budget checks and audit.
6. Append one tool response per call with the matching `tool_call_id`.
7. Repeat until a final response or budget/cancellation/error boundary.
8. Persist structured evidence/action/scenario references, usage and completion status.

The browser never executes tools directly. The model cannot call arbitrary URLs, run shell commands or execute uploaded instructions. Treat document bodies, telemetry annotations and tool-result free text as data, not authority to change permissions or instructions.

Use backend SSE events: `run_started`, `tool_started`, `tool_completed`, `text_delta`, `proposal_created`, `run_completed`, `run_failed`. Provide ordered IDs, heartbeat, reconnect/resume and cancellation. Backend events work even when the provider cannot stream tokens. Show tool names, result summaries and evidence—not private reasoning traces.

Final answers identify: finding, supporting values/time window, probable interpretation, unknowns, simulation assumptions and recommended next action. Link actual dashboard records and scenario runs. If evidence does not support a conclusion, say what is missing. No invented SQL values, savings, source citations or action success. Calculations use domain services; a failed write cannot be described as completed.

Example questions to support:

* “Which zones used unusually high water yesterday relative to occupancy?”
* “What happens if the grid fails for six hours and the pump stops?”
* “Which waste batches need attention first, and why?”
* “Compare repairing the assumed leak now with waiting four hours.”
* “Create a maintenance task for the pump inspection and assign it to an authorized technician.”
* “Explain this carbon estimate and the factor used.”

These must trigger appropriate live tools, not canned answers. “Yesterday” resolves using the displayed facility clock and timezone.

## 14. Agent reactions and action policy

The agent reacts through software workflows: surface a risk, run a scenario, create a proposal, create a task if permitted, update permitted task states and publish an in-app report. This product does not operate physical hospital equipment.

By default, monitor mode is read/simulate/draft. A facility admin may explicitly enable narrowly defined autonomous task creation by category, severity, owner pool and limits. Store the policy version and service-principal grants. Allow low-impact in-app notices and task creation only within that policy; deduplicate against existing incidents/actions. Other proposals remain reviewable in the action centre.

User-requested permitted task operations proceed through normal application authorization; do not add a generic confirmation to every read, simulation or harmless requested action. High-impact plan approvals, protected-service schedule changes, action verification and closure follow the configured role/evidence requirements. Never let the LLM waive them.

Action states: `open → acknowledged → in_progress → resolved → verified → closed`. Verification and closure require appropriate evidence/reviewer role; invalid transitions fail. Reopening follows a defined reasoned transition with audit. Store optimistic version numbers, actor, evidence, before/after state and timestamps. Separate generated proposals from committed actions.

Event triggers: new high-severity alert, reserve projection breach, pickup deadline risk, unresolved action overdue and daily brief schedule. Use cooldowns, one active investigation per scoped incident, idempotency and bounded retries. Server-derived mutation keys bind the run/trigger, incident and operation; retries or repeated model calls cannot create duplicate actions even if the model changes its own arguments. A provider outage preserves deterministic alerts and the pending investigation, with an honest status.

## 15. Backend API contract

Prefix routes with `/api/v1`. Use OpenAPI generation, pagination, consistent error envelopes, request IDs, documented validation and idempotency headers for mutations/jobs.

| API group | Representative routes |
|---|---|
| Session / scope | `/auth/login`, `/auth/logout`, `/me`, `/organizations`, `/facilities`, `/worlds` |
| Facility | `/facilities/{id}/buildings`, `/zones`, `/capacities`, `/operational-snapshots`, `/schedules` |
| Import / quality | `/imports`, `/imports/{id}`, `/quality-events`, `/metric-catalog` |
| Overview / data | `/overview`, `/metrics/series`, `/metrics/comparison`, `/evidence/{id}` |
| Domain CRUD | `/assets`, `/tanks`, `/waste/batches`, `/waste/pickups`, `/environment`, `/parking`, `/safety-incidents` |
| ML | `/forecasts`, `/models`, `/models/{id}/evaluation`, `/training-runs` |
| Alerts / actions | `/alerts`, `/alerts/{id}/evidence`, `/actions`, `/actions/{id}/transition`, `/action-proposals` |
| Simulations | `/scenarios`, `/simulations`, `/simulations/{id}`, `/simulations/compare` |
| Chat / agent | `/conversations`, `/conversations/{id}/messages`, `/agent-runs`, `/agent-runs/{id}/events`, `/agent-runs/{id}/cancel` |
| Reports / policy | `/reports`, `/policies`, `/tariffs`, `/emission-factors`, `/documents` |
| Demo | `/demo/clock`, `/demo/replay`, `/demo/reset` |
| Platform | `/health/live`, `/health/ready`, `/jobs/{id}` |

Each route takes authorized scope through a shared dependency; never duplicate a weaker agent-only analytics implementation. Worker operations use the same domain services. Return `202` plus a durable job/run ID for long work, not an indefinitely hanging request. Uploaded evidence gets file-size/type checks and scoped signed access.

## 16. Frontend behavior and UX

Build a polished hospital operations dashboard with readable charts, clear units and evidence drill-down. Use a restrained visual system, accessible keyboard navigation and responsive layouts. Distinguish synthetic source badges, observations, forecasts, simulations and estimates through labels and line styles.

Overview includes resource usage, occupancy-adjusted intensity, reserve status, waste deadline, critical assets, active risks and assigned work. Every KPI links to its underlying period/boundary and evidence. Provide facility/world/date filters consistently, visible virtual clock and a data coverage panel.

Energy/water explorers show measured values, supported forecast leads, intervals, quality gaps and baseline comparison. Waste shows category-specific batches and pickup/age evidence. Maintenance supports inspection/work-order CRUD. Parking/safety supports actual records and meaningful counts. Reports show methods, source/factor versions and unknowns.

Chat has tool progress, citations to application records, scenario cards and action proposal cards. Agent activity lists trigger, policy, tool calls, result, created actions and failures. Do not imply the agent is monitoring when its scheduler/provider is disabled. Preserve user navigation context when opening evidence.

Charts must show missing values as gaps. Show loading, empty, stale, partial, unauthorized and failed states. No fake improvements, invented occupancy or random frontend chart data. Browser data comes from backend APIs.

## 17. Cost, carbon and reporting

Calculate cost using versioned tariff assumptions and explicit reporting boundaries. Separate demand charges from consumption charges when modeled; unsupported tariff components are omitted with an explanation. Carbon estimates use configured factor, unit, geographic scope, year and source. Do not hardcode an unsourced factor as an official current value.

Intensity examples: kWh per occupied bed-day, water L per occupied bed-day and OPD-related indicators. Define how mixed OPD/inpatient activity is allocated; avoid pretending one denominator explains all hospital demand. Do not use an empty/zero denominator to manufacture a score.

Daily and period reports contain operating context, consumption trends, risks, open actions, simulated scenarios, estimates, data gaps and methodology. Offer downloadable CSV and printable HTML/PDF. PDF generation may use browser print or a server renderer; test the output. The deterministic report works without an LLM; optional narrative references the same facts.

## 18. Implementation milestones for Codex

Complete these in dependency order. Maintain `docs/build-status.md` with implemented behavior, commands run, evidence and remaining blockers. Each milestone should leave a runnable system. Do not stop after M3/MVP; completion requires M10.

| Milestone | Deliverables | Exit checks |
|---|---|---|
| M0 — Inspect and scaffold | Inspect attachments/repo instructions; preserve starter; create monorepo, Compose, lockfiles and environment example | Web/API/DB boot; readiness reflects dependencies |
| M1 — Data and security | Alembic schema, auth/roles/RLS, worlds, clock, importer, quality and metric catalog | Exact base/stress counts, isolation, idempotent import, no private truth in runtime |
| M2 — Operations and resource views | Facility CRUD, context, energy/water/waste aggregate views and evidence | API-backed charts match SQL totals and units |
| M3 — ML and risk workflow | Trusted model serving, registry/evaluation, fallback, contextual detector, rules, alert deduplication | Reload predictions agree; unsupported horizon/missing history handled honestly |
| M4 — Simulation and actions | Deterministic engine, scenario studio, comparison, proposals, action state machine | Balance/deadline fixtures pass; actions enforce roles/evidence |
| M5 — Full domain data and pages | Extended generator, waste ledger, assets, environment, parking, safety, resilience, sustainability | All twelve modules have real persisted functionality |
| M6 — Grounded chatbot | Provider adapter, capability check, scoped tools, chat persistence, SSE and evidence cards | Mock tool loop tests plus real configured-provider read-tool round trip |
| M7 — Agent reactions | Investigate/monitor modes, triggers, policies, scoped actions, budgets, retries and run audit | End-to-end risk → investigation → scenario → proposal/permitted task |
| M8 — Reporting and admin | Deterministic/LLM briefs, exports, policy/tariff/factor settings and model admin | Reproducible reports and permission-scoped downloads |
| M9 — Verification and operations | Integration/E2E tests, backup/restore, security boundaries, performance checks and runbooks | Complete fresh-volume startup and core failure cases verified |
| M10 — Handoff | Clean run instructions, demo script, test results, limitations, screenshots and deployment configuration | All definition-of-done rows pass or an explicit external blocker is recorded |

If the provider key is unavailable, finish all independent work, test the adapter with mocks and leave the real-provider check explicitly blocked. Do not silently replace the requested integration with fake responses or describe it as fully verified. Likewise, implement cloud deployment configuration without claiming a hosted deployment occurred.

## 19. Required commands and reproducible startup

Codex must implement these command contracts. They are requested interfaces, not claims that this plan itself contains an application:

```bash
cp .env.example .env
python3 scripts/prepare_starter.py --archive Hospital_GreenOps_Synthetic_ML_Starter.zip --research-out research/starter --public-out data/public/starter
docker compose up --build -d
docker compose run --rm migrate
docker compose exec api python -m app.cli seed-demo --starter /app/data/public/starter
docker compose exec api python -m app.cli generate-world --config /app/data/public/extended-demo.yaml
docker compose exec api python -m app.cli infer --world base_v1
docker compose exec api python -m app.cli smoke-test
docker compose exec api python -m app.cli check-llm
docker compose exec api pytest
docker compose exec web npm run test:e2e
```

Document actual service URLs and generated demo credentials in local setup output. Provide health-gated startup; migration/seed are idempotent. The migration service receives the dedicated migration URL; API/worker services receive only the restricted runtime URL. Do not make import or long training a module-import side effect. Training has an explicit CLI/job with progress and artifacts. Public source fixtures may be mounted into seed/API containers; private evaluation data is mounted only into an isolated offline training/evaluation container, never a running API/agent container.

Also implement clean database reset restricted to demo mode, database backup/restore commands, dataset/model checksum verification and an agent-evaluation command. The E2E container/config must include its browser dependencies and a correctly networked application URL.

## 20. Mandatory verification

Use meaningful tests of behavior and boundaries, not tests that merely reproduce implementation constants.

| Area | Required verification |
|---|---|
| Import | Exact 17,280/8,640 source counts; separate worlds; duplicate import unchanged; null water preserved; quarantine visible |
| Private truth | Labels and injected-event config absent from runtime images, searchable documents, storage and tools |
| Auth / RLS | Cross-tenant/facility/zone reads and writes fail; auditor cannot mutate; pooled connections do not retain identity |
| Metrics | API and chart aggregates agree with source SQL; interval units correct; hierarchy does not double count |
| ML | Original feature contract preserved; chronological purge/leakage tests; saved/reloaded predictions agree; stress failures displayed |
| Detection | Persistence/dedup behavior; quality gating; precision/recall/event delay/false incidents by world; no hidden-label tuning |
| Simulation | Five numeric fixtures above plus unknown-age case; water/energy mass balance, essential priority and explicit unmet demand |
| Full domains | Extended waste stock/batch/pickup consistency; parking capacity/queue balance; asset/incident CRUD persisted |
| Action lifecycle | Invalid transitions rejected; evidence/reviewer requirements; stale version conflict; duplicate agent task prevented |
| Agent tools | Correct scope/schema/units; bounded queries; SQL injection and unknown tool attempts rejected; mutation checks server-side |
| Prompt injection | Malicious document/annotation cannot change scope, reveal secrets or trigger unauthorized action |
| Provider | Real text + read-tool round trip for chosen endpoint/model; mock malformed arguments, rate limit, timeout and unsupported tool mode |
| Grounding | Ask at least 15 questions across domains; numeric facts match tool output; evidence links valid; missing data disclosed; change a permitted input and refresh to verify the answer changes with actual data |
| Jobs / stream | Worker retry duplicates do not duplicate effects; restart recovery; SSE resume/cancel; provider/Redis failure visible |
| Browser | Login, world switch, import, explorer, waste/maintenance CRUD, scenario comparison, chat and action closure flows |
| Recovery | Database and artifact backup restored into fresh services; core demo reproducible |

Performance targets are project targets to measure, not vendor guarantees: warmed overview under 2 seconds on a documented local environment with the starter, bounded analytical queries under 3 seconds, a 72-hour single-facility simulation under 5 seconds for the configured small world. Report actual measurements and dataset sizes. Longer work uses a job/progress UI.

Do not use SQLite as a substitute for PostgreSQL integration/RLS tests. Do not call live LLM endpoints in every CI unit test; separate mocked deterministic tests from explicit credentialed integration checks.

## 21. Definition of done

The product is complete when:

* A new developer can start it from a fresh checkout/volume using documented commands.
* PostgreSQL migrations, roles, import, world separation and synthetic clock work.
* All twelve modules have meaningful API-backed functionality and saved data.
* Supplied datasets/models are used faithfully; extensions and limitations are explicit.
* What-if calculations reproduce fixtures and reveal risks, unmet demand and assumptions.
* Chat queries actual authorized data; the chosen compatible model completes a real tool round trip when credentials exist.
* The agent investigates across domains, reacts under its configured policy and records tool/action evidence.
* Actions have real lifecycle, ownership, deadlines and evidence checks.
* Reports/export/backup work and tests provide recorded evidence.
* No private injected truth, secrets, fake successes, invented model performance or unsupported resource-saving claims appear in the product.

## 22. Deployment and operating handoff

Local deliverable: containerized web, API, worker, scheduler, PostgreSQL, Redis and object storage. Include development and production Compose configuration, dependency health checks, persistent volumes, bounded resources and structured logs. Separate inference/training resource use from request handling.

Optional Azure path: suitable container service or a VM for a small demo, managed PostgreSQL and object storage for a pilot. Choose services after workload/budget review; this document makes no current pricing assumptions. Include reverse proxy/TLS configuration, secret management, allowed origins, migration release step and rollback.

Monitor ingestion lag, metric coverage, query latency, job retries, forecast baseline gaps, interval coverage, incident volume, simulation failures, provider latency/errors, agent budgets and action verification. Logs use request/run IDs and omit secrets and unnecessary prompt contents. Keep dataset/model/configuration hashes and restore instructions. Provide a rollback to the previous model/policy version without changing historical evidence.

Final Codex handoff should state implemented scope, how to run, credentials/setup requirements, test results, real-provider verification status, remaining external dependencies and honest limitations. Publishing to a hosting account is a separate action unless requested in that Codex session.

## 24. Technical references and evidence boundary

Primary technical references checked for this plan:

1. [Official OpenAI Python SDK](https://github.com/openai/openai-python) — async client, configurable base URL, timeouts and retries.
2. [OpenAI function calling guide](https://developers.openai.com/api/docs/guides/function-calling) — tool schemas, application execution and matching tool responses.
3. [PostgreSQL row security documentation](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) — row policies, owner/superuser bypass and FORCE RLS behavior.
4. [scikit-learn HistGradientBoostingRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html) and [IsolationForest](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html) — underlying starter algorithms.

This document's architecture, tool inventory, milestones, performance targets and acceptance criteria are proposed engineering requirements. Starter row counts, units, numeric fixtures and model limitations come from the supplied executable starter and its recorded evaluation, not from claims about a real hospital. No application implementation or hosted deployment is claimed by delivery of this plan.
