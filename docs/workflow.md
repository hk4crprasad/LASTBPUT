# Hospital GreenOps AI: complete system workflow

These diagrams describe the implemented product. Hospital data is explicitly synthetic and limited to operations and sustainability. Virtual event time determines operating state; system time controls authentication, auditing, leases and scheduling.

For separate diagrams of the full technology stack and all seven role scopes, see [Technology stack and user scopes](techstack-and-scopes.md).

## 1. Users → Dashboard → FastAPI → AI services → Outputs

```mermaid
flowchart LR
    Users["Users<br/>Admins, supervisors, technicians,<br/>waste and sustainability officers, auditors"]
    Dashboard["Dashboard<br/>Next.js and TypeScript<br/>18 operational and management pages"]
    FastAPI["FastAPI backend<br/>Login, role and zone permissions<br/>Domain APIs, CRUD and audit"]
    AI["AI services<br/>Experimental ML forecasts<br/>Grounded chatbot and scoped agents"]
    Analysis["Deterministic analysis<br/>What-if simulations<br/>Risk rules, cost and carbon estimates"]
    Outputs["Outputs shown in dashboard<br/>Metrics, forecasts and evidence<br/>Scenario results, reviewed actions and reports"]
    DB[("PostgreSQL / Supabase<br/>World-scoped data and FORCE RLS")]
    Queue["Celery and Redis<br/>Durable asynchronous jobs"]
    Blob["Private Azure Blob Storage<br/>Reports and evidence files"]
    Users --> Dashboard --> FastAPI
    FastAPI --> AI --> Outputs
    FastAPI --> Analysis --> Outputs
    FastAPI --> Outputs
    FastAPI <--> DB
    FastAPI --> Queue
    Queue --> AI
    Queue --> Analysis
    FastAPI <--> Blob
    Outputs --> Dashboard
    classDef app fill:#e8f3ed,stroke:#176448,color:#153c2e
    classDef intelligence fill:#eeeafa,stroke:#67539a,color:#352856
    classDef infrastructure fill:#f1f3f4,stroke:#687979,color:#263c3c
    class Users,Dashboard,FastAPI,Outputs app
    class AI,Analysis intelligence
    class DB,Queue,Blob infrastructure
```

[Editable Mermaid source](diagrams/greenops-workflow.mmd)

[SVG diagram](diagrams/greenops-workflow.svg) · [PNG diagram](diagrams/greenops-workflow.png)

### Detailed operating journey

```mermaid
flowchart TD
    Login["Sign in manually or choose one of seven demo roles"] --> Auth["Authenticate real account and issue session plus CSRF cookie"]
    Auth --> Scope["Select authorized organization, facility and world"]
    Scope --> Clock["Apply selected virtual clock and date range"]
    Clock --> API["Next.js screens call same-origin FastAPI domain APIs"]
    API --> Guard["Check session, domain, zone, ownership and input contracts"]
    Guard --> RLS["Restricted PostgreSQL role and transaction-local FORCE RLS"]
    RLS --> Read["Read scoped observations, configuration and operating ledgers"]
    RLS --> Write["Permitted CRUD with version checks and audit records"]
    Read --> Pages["Overview and operational modules"]
    Write --> Pages
    Read --> ML["Trusted experimental inference and deterministic risk rules"]
    Read --> Sim["Freeze baseline and run deterministic what-if simulation"]
    Read --> Chat["Grounded chatbot or policy-enabled investigation"]
    ML --> Risks["Forecasts, quality events and observable alerts"]
    Risks --> Chat
    Chat --> Tools["Typed permission-scoped tools"]
    Tools --> Read
    Tools --> Sim
    Sim --> Results["Saved results, balances, violations and sensitivity"]
    Results --> Proposal["Reviewable action proposal"]
    Tools --> Proposal
    Proposal --> Review["Administrator reviews and optionally approves"]
    Review --> Action["Assigned software action and evidence-based lifecycle"]
    Tools --> Policy["Explicit write permission and current policy checks"]
    Policy --> Action
    Pages --> Report["Generate reproducible CSV, HTML and PDF report"]
    Results --> Report
    Action --> Report
    Report --> Blob["Private scoped object storage with SHA256"]
    Blob --> Download["Authenticated API download rechecks scope and checksum"]
```

Operational screens cover facility, energy, water/reserves, waste, environment, assets/maintenance, parking, safety and sustainability. Supporting screens expose simulations, actions, reports, chat, agent activity, import quality, model evaluation and policy/settings. There are 18 product pages plus sign-in.

## 2. Technology and trust boundaries

```mermaid
flowchart LR
    Browser["Browser: Next.js and TypeScript"] --> Proxy["Same-origin Next.js API proxy"]
    Proxy --> API["FastAPI: authentication and domain services"]
    API --> DB["PostgreSQL: scoped operational records, sessions, jobs and audit"]
    API --> Storage["Private Azure Blob Storage or S3/MinIO"]
    API --> Provider["Server-side OpenAI-compatible provider adapter"]
    DB --> Outbox["Durable PostgreSQL outbox"]
    Beat["Celery scheduler"] --> Dispatch["Scoped dispatch and recovery"]
    Outbox --> Dispatch
    Dispatch --> Redis["Redis broker"]
    Redis --> Worker["Celery worker"]
    Worker --> Domain["Same authorized domain services used by HTTP"]
    Domain --> DB
    Domain --> Storage
    Domain --> Provider
    API --> SSE["Persisted ordered agent events"]
    SSE --> Browser
    Migrator["Separate migration/bootstrap role"] --> DB
```

The configured cloud installation uses Supabase PostgreSQL 17, private Azure Blob Storage and Azure's OpenAI-compatible endpoint. Local Compose also supports PostgreSQL 18 and MinIO. Provider and storage keys stay server-side. The API, worker and scheduler do not receive the privileged migration URL. Agents receive typed tool interfaces rather than SQL, shell or filesystem access.

## 3. Authentication and ordinary domain requests

```mermaid
sequenceDiagram
    actor User
    participant Web as Next.js UI
    participant API as FastAPI
    participant DB as PostgreSQL with FORCE RLS
    User->>Web: Sign in or select demo role
    Web->>API: Login request
    API->>DB: Verify account and persist hashed session
    API-->>Web: Session cookie, CSRF token and principal
    User->>Web: Select world and open a module
    Web->>API: Scoped read or validated mutation
    API->>DB: Begin transaction and set local user/organization identity
    API->>API: Recheck domain, facility, zone, owner and version
    API->>DB: Query or write through restricted role
    DB->>DB: Apply RLS and relational constraints
    DB-->>API: Authorized records or denial
    API->>DB: Commit successful mutation and audit
    API-->>Web: Committed result with values, units and source context
    Web-->>User: Render loaded data or explicit error
```

Seven demo roles are organization admin, hospital admin, operations supervisor, maintenance technician, waste officer, sustainability officer and auditor. The demo picker uses actual account authentication and is disabled in production. Writes require CSRF and an allowed Origin. Sign-out clears cached scope and operating data before another user signs in.

## 4. Data ingestion and world separation

```mermaid
flowchart TD
    Starter["Supplied synthetic ML starter"] --> Offline["Preserve original starter in offline research area"]
    Offline --> Private["Private labels and hidden injected-event configuration: offline only"]
    Offline --> Sanitize["Explicit public allowlist, sanitization and checksums"]
    Sanitize --> Import["Validate canonical source fields, timestamps and interval units"]
    CSV["Authorized aggregate operations CSV upload"] --> Import
    Import --> Quality{"Valid field and canonical world/zone/time identity?"}
    Quality -->|Yes| Source["Persist immutable source lineage and normalized observations"]
    Quality -->|Invalid or conflicting| Quarantine["Inspect rejected fields and quality evidence"]
    Source --> Base["base_v1: 17,280 source rows"]
    Source --> Stress["stress_v1: 8,640 source rows"]
    Config["Identified extended synthetic generator configuration"] --> Generate["Generate missing operational domains independently"]
    Generate --> Extended["extended_v1: 25,920 zone-hours"]
    Extended --> Ledgers["Waste categories, assets, reserves, environment, parking and incidents"]
    Base --> Clock["Each world has its own virtual clock and scoped records"]
    Stress --> Clock
    Ledgers --> Clock
    Clock --> Services["Domain reads, simulations and agent snapshots"]
```

Missing water remains missing. Invalid fields do not erase valid fields from the source row. Duplicate imports cannot silently replace conflicting canonical observations. Extended-world category waste is a separate synthetic ledger; it is not reconstructed from base/stress aggregate waste. Hidden truth is never copied into runtime documents, object storage or agent context.

## 5. Experimental ML and observable rules

```mermaid
flowchart LR
    Research["Offline original starter and permitted evaluation truth"] --> Features["Preserve original feature columns and interval contracts"]
    Features --> Split["Chronological split with leakage checks and purge"]
    Split --> Train["Train six forecasts and generic detector"]
    Train --> Evaluate["Baseline comparison, shifted-world metrics and limitations"]
    Evaluate --> Manifest["Trusted artifact hashes and evaluation manifests"]
    Manifest --> Serving["Checksum-verified artifact load"]
    Data["Authorized public observations at world cutoff"] --> Serving
    Serving --> Forecasts["Experimental 1, 6 and 24 hour forecast points"]
    Serving --> Detector["Experimental anomaly evidence"]
    Data --> Rules["Deterministic resource, waste, environment and access rules"]
    Disabled["Disabled model or insufficient history"] --> Fallback["Explicit seasonal fallback or unavailable prediction"]
    Forecasts --> UI["Model evaluation, resource charts and scoped evidence"]
    Detector --> UI
    Rules --> Alerts["Observable risk alerts"]
    Fallback --> UI
```

Training is an explicit isolated offline command, not an arbitrary uploaded-model execution path. Energy gains become negative under stress; the generic detector has weak precision/recall. Forecasts and fallback states are labeled. These models do not establish real-hospital accuracy or savings.

## 6. Deterministic what-if simulations

```mermaid
flowchart TD
    Scenario["User or permitted tool submits a typed scenario"] --> Validate["Check domain permission, interventions and 1-72 hour horizon"]
    Validate --> Freeze["Freeze authorized baseline, clock, configuration and assumptions"]
    Freeze --> Queue["Commit durable simulation job"]
    Queue --> Engine["Celery runs 15-minute deterministic steps"]
    Engine --> Power["Apply grid, battery, fuel and essential-power priorities"]
    Power --> Water["Track pumps and separate tanks; protect fire reserve"]
    Water --> Other["Evaluate waste deadlines, dependencies and parking balances"]
    Other --> Balance["Record unmet demand, conservation balances and violations"]
    Balance --> Sensitivity["Run low, central and high demand sensitivity"]
    Sensitivity --> Save["Persist baseline, intervention result and modeled deltas"]
    Save --> Compare{"Same frozen baseline and horizon?"}
    Compare -->|Yes| Comparison["Compare saved scenarios"]
    Compare -->|No| Reject["Reject incompatible comparison"]
    Save --> Export["View chart, export result or draft an action"]
```

Supported interventions include grid outage, pump failure, supply interruption, occupancy/OPD surge, heat, water leak, excess energy, pickup timing, schedules, asset restoration and rainfall. Sensitivity is not a confidence interval; modeled deltas are not measured savings.

## 7. Grounded chatbot and agent tools

```mermaid
sequenceDiagram
    actor User
    participant API as FastAPI
    participant DB as Scoped PostgreSQL
    participant Worker as Celery agent worker
    participant LLM as Compatible provider
    participant Tools as Typed domain tools
    User->>API: Ask or investigate in selected world
    API->>DB: Save conversation and freeze authorized snapshot
    API->>DB: Commit run, job and outbox event
    API-->>User: Run ID and observable progress stream
    Worker->>DB: Claim lease and load initiating user's grants
    Worker->>LLM: Scoped context and allowed tool schemas
    loop Until final answer, cancellation or budget limit
        LLM-->>Worker: Tool call with matching call ID
        Worker->>Worker: Validate tool name, typed arguments and cancellation
        Worker->>Tools: Read pinned state or request permitted operation
        Tools->>DB: Scoped query or rechecked committed mutation
        DB-->>Tools: Records, values, units and evidence
        Tools-->>Worker: Result or honest denial/error
        Worker->>DB: Persist tool call, result, usage and ordered events
        Worker->>LLM: Matching tool result
    end
    LLM-->>Worker: Candidate final response
    Worker->>Worker: Check numeric claims and supplied evidence citations
    alt Grounding passes
        Worker->>DB: Persist completed answer and usage
        API-->>User: Answer with inspectable evidence
    else Unsupported answer or provider failure
        Worker->>DB: Persist grounding/provider failure state
        API-->>User: Explicit limitation or failure - unsupported answer withheld
    end
```

Nineteen tools cover facility/catalog/metrics/context, assets, reserves, waste, environment, parking/safety, forecasts, alerts, actions, sustainability, document search, simulations/comparisons, proposals and permitted action writes. Parallel read tool calls are supported; mutations run sequentially. Documents are untrusted input and cannot grant access. The provider key is never sent to the browser.

Scheduled monitoring adds observable triggers → enabled versioned policy → cooldown check → frozen investigation → evidence → relevant simulation → proposal. Autonomous software task creation additionally requires the server flag, current policy, permitted category/severity/owner, incident state, duplicate prevention and daily budget. A tool never operates physical equipment.

## 8. Proposal review and action lifecycle

```mermaid
flowchart LR
    Evidence["Observable alert or investigation evidence"] --> Proposal["Saved proposal with rationale and scenario references"]
    Proposal --> Reviewer{"Authorized reviewer decision"}
    Reviewer -->|Leave unapproved| Pending["Proposal remains proposed; no action created"]
    Reviewer -->|Approve and choose permitted owner| Open["Open assigned action"]
    Manual["Permitted manual action creation"] --> Open
    Autonomous["Narrow server and facility policy permits creation"] --> Open
    Open --> Lifecycle["Versioned transitions and audit evidence"]
```

```mermaid
stateDiagram-v2
    [*] --> open
    open --> acknowledged
    acknowledged --> in_progress
    in_progress --> resolved
    in_progress --> acknowledged: Return for reassignment
    resolved --> verified: Independent authorized reviewer and evidence
    resolved --> in_progress: Further work needed
    verified --> closed
    verified --> in_progress: Verification requires rework
    closed --> open: Reopen with recorded reason
```

Creation checks the domain, zone, category, eligible owner, due date and linked evidence. Transitions check current scope, ownership/role, optimistic version and reason. Verification requires evidence and independent review. A simulation or generated proposal alone does not prove action success or savings.

## 9. Jobs, recovery and reports

```mermaid
flowchart TD
    Request["Authorized asynchronous request"] --> Commit["Commit job and outbox in PostgreSQL"]
    Commit --> Dispatch["Scheduler dispatches durable IDs"]
    Dispatch --> Broker{"Redis available?"}
    Broker -->|No| Pending["Keep durable request for later dispatch"]
    Pending --> Dispatch
    Broker -->|Yes| Worker["Worker claims scoped job lease"]
    Worker --> Idempotency["Recheck status and idempotency before effects"]
    Idempotency --> Execute["Execute simulation, inference, import, report or agent work"]
    Execute --> Success["Commit actual result and completed status"]
    Execute --> Failure["Persist explicit dependency or provider failure"]
    Failure --> Budget{"Retry permitted within budget?"}
    Budget -->|Yes| Retry["Retry original frozen context"]
    Retry --> Dispatch
    Budget -->|No| Failed["Failed job remains inspectable"]
    Worker --> Expired["Expired lease found by recovery"]
    Expired --> Dispatch
    Success --> UI["UI polls persisted job status"]
    Failed --> UI
```

```mermaid
flowchart LR
    Request["Choose world, virtual cutoff and report window"] --> Facts["Freeze scoped facts, factors, quality gaps and limitations"]
    Facts --> Render["Deterministically render CSV, printable HTML and PDF"]
    Render --> Upload["Upload private object and compute SHA256"]
    Upload --> Metadata["Persist scoped file metadata and report record"]
    Metadata --> Link["UI shows authenticated download links"]
    Link --> Check["API rechecks world/zone permission and checksum"]
    Check --> File["Return actual file bytes"]
```

Azure uses a private container and the `hospital-greenops/` prefix in this installation. S3/MinIO uses the same logical scoped keys. No browser storage credential or public blob URL is required. Deterministic reports work without the LLM.

## Jury walkthrough

1. Select Hospital admin on the sign-in screen; explain the fictional hospital, selected world and paused virtual clock.
2. Open Overview, Energy and Water to show measured interval values, coverage, reserves and experimental forecast labels.
3. Show Waste, Assets, Environment, Parking and Safety with their actual scoped ledgers.
4. Run a six-hour grid/pump disruption, inspect unmet demand and balances, and compare another scenario on the same baseline.
5. Ask the chatbot for current water reserves; inspect its tool activity and evidence links.
6. Show the saved proposal and independently reviewed action workflow; explain the server/policy limits on automatic task creation.
7. Generate a report and download its actual PDF/CSV; show model limitations and import-quality evidence.
8. Sign out and select a technician or auditor to demonstrate narrower access.

[README and screenshots](../README.md) · [Architecture](architecture.md) · [Build evidence](build-status.md) · [Verification output](verification/README.md) · [Cloud runbook](cloud-services.md)

Reproduce the diagram validation and main PNG/SVG exports:

```bash
npm install --prefix .local/mermaid-validation --no-save --ignore-scripts mermaid@12.1.0
uv run --frozen --project scripts/ui-tests python -m playwright install chromium
uv run --frozen --project scripts/ui-tests python scripts/validate_workflow.py
```
