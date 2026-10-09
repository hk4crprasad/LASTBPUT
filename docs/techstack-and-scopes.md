# Hospital GreenOps AI — technology stack and user scopes

These diagrams follow the implemented permission checks and database policies. Roles define permitted operations; organization membership, facility grants, zone grants, record ownership and selected world further restrict every request. All hospital operating data is synthetic.

## Technology stack

[Editable Mermaid](diagrams/technology-stack.mmd) · [SVG](diagrams/technology-stack.svg) · [PNG](diagrams/technology-stack.png)

```mermaid
flowchart TB
    User["Hospital operations and sustainability users"]
    subgraph Frontend["1 · Dashboard — Next.js / TypeScript"]
        Login["Real account login<br/>Seven demo-role buttons in demo mode"]
        ScopePicker["Organization, facility and world selector<br/>Virtual clock and date-range filters"]
        OperationsUI["Operational pages<br/>Overview · Facility · Energy · Water · Waste<br/>Environment · Assets · Parking · Safety · Sustainability"]
        IntelligenceUI["Intelligence pages<br/>Simulations · Actions · Reports · Chat · Agent activity"]
        AdminUI["Management pages<br/>Import quality · Model evaluation · Policy and settings"]
        Proxy["Same-origin /api/v1 proxy<br/>Session cookies and CSRF headers<br/>Server responses and SSE progress"]
        Login --> ScopePicker
        ScopePicker --> OperationsUI & IntelligenceUI & AdminUI
        OperationsUI & IntelligenceUI & AdminUI --> Proxy
    end
    User --> Login
    subgraph Backend["2 · API — FastAPI / Python"]
        Auth["Authentication<br/>Argon2 passwords · hashed opaque sessions<br/>Allowed Origin and CSRF checks"]
        Scope["Authorization<br/>Organization + facility + world + zone<br/>Role + owner + optimistic version"]
        Contracts["Typed input contracts<br/>Allowlisted fields, interval units and timestamps"]
        CRUD["Domain CRUD services<br/>Facility configuration · assets and maintenance<br/>Waste workflow · environment · parking · safety"]
        Reads["Operating reads and calculations<br/>Coverage · aggregates · reserves · intensity<br/>Versioned illustrative cost and carbon factors"]
        Actions["Actions and proposals<br/>Eligible owner · permitted transitions<br/>Independent verification and evidence audit"]
        Jobs["Durable request acceptance<br/>Commit job and PostgreSQL outbox"]
        Files["Authenticated file API<br/>Recheck scope and content SHA256"]
        Events["Persisted agent event stream<br/>Ordered SSE replay and cancellation"]
        Auth --> Scope --> Contracts
        Contracts --> CRUD & Reads & Actions & Jobs & Files
    end
    Proxy --> Auth
    subgraph Data["3 · Persistence and isolation"]
        DB[("PostgreSQL / Supabase<br/>Alembic migrations · restricted runtime role<br/>FORCE RLS and composite scope constraints")]
        Worlds["Independent worlds<br/>base_v1 · stress_v1 · extended_v1<br/>Separate clocks and operating ledgers"]
        Audit["Persisted evidence<br/>Source lineage · quality · versions<br/>Actions · tool results · jobs · usage · audit"]
        Blob["Private Azure Blob Storage<br/>hospital-greenops/ scoped prefix<br/>CSV · HTML · PDF · uploaded evidence"]
        Alternative["Local alternative<br/>S3-compatible MinIO adapter"]
        DB --> Worlds & Audit
        Blob -. "provider alternative" .- Alternative
    end
    CRUD & Reads & Actions & Jobs & Events --> DB
    Files --> DB & Blob
    subgraph Workers["4 · Asynchronous work — Celery / Redis"]
        Scheduler["Celery scheduler<br/>Dispatch, retries and opt-in monitoring"]
        Dispatch["Read committed outbox<br/>Recover expired leases and prevent duplicate effects"]
        Redis["Redis broker"]
        Worker["Celery worker<br/>Restore initiating user's scoped identity<br/>Claim lease and enforce retry budget"]
        Scheduler --> Dispatch --> Redis --> Worker
    end
    DB --> Dispatch
    subgraph Intelligence["5 · AI services and deterministic analysis"]
        ML["Trusted ML inference<br/>Six experimental forecasts and generic detector<br/>Original feature contracts and checksum trust"]
        Rules["Deterministic risk rules<br/>Resources · waste deadlines · environment<br/>Asset modes · protected access routes"]
        Simulator["Deterministic what-if engine<br/>Frozen baseline · 15-minute steps · 1-72 hours<br/>Balances, violations and low/central/high sensitivity"]
        Agent["Chatbot and investigation agent<br/>Frozen authorized snapshots<br/>19 typed scoped tools and grounded final answers"]
        Policy["Monitoring and permitted task writes<br/>Server flag + versioned facility policy<br/>Cooldown, incident, owner, duplicate and daily-budget checks"]
        Adapter["Server-side OpenAI-compatible adapter<br/>Streaming and parallel read calls<br/>Sequential authorized mutations"]
        Provider["Configured Azure deployment<br/>Actual provider calls and usage<br/>Keys remain server-side"]
        Reports["Deterministic report renderer<br/>Scoped frozen facts, factors and limitations<br/>Actual CSV, HTML and PDF bytes"]
        Agent --> Adapter --> Provider
        Agent --> Reads & Simulator & Actions
        Policy --> Agent
        ML --> Rules
    end
    Worker --> ML & Rules & Simulator & Agent & Reports
    DB --> ML & Rules & Simulator & Agent & Reports
    Scheduler --> Policy
    Agent --> Events
    ML & Rules & Simulator & Agent & Reports --> DB
    Reports --> Blob
    subgraph Offline["6 · Offline research and model preparation"]
        Starter["Supplied synthetic starter<br/>Preserved original observations and ML foundation"]
        Private["Private labels and hidden event configuration<br/>Offline evaluation only"]
        Public["Sanitized public allowlist<br/>Checksums, canonical fields and permitted features"]
        Training["Explicit offline training and evaluation<br/>Chronological splits, purge and baseline comparisons"]
        Artifacts["Trusted model artifacts and evaluation manifests"]
        Generator["Clearly identified additional synthetic generator<br/>Missing operational domains in extended_v1"]
        Starter --> Private & Public
        Starter --> Training --> Artifacts
        Public --> Generator
    end
    Public --> DB
    Generator --> Worlds
    Artifacts --> ML
    Output["7 · Outputs in the dashboard<br/>Observed metrics and coverage · experimental predictions<br/>Evidence-backed answers · simulation results<br/>Reviewed software actions · downloadable reports<br/>Explicit limitations, failures and configuration states"]
    DB & Events & Files --> Output
    Output --> OperationsUI & IntelligenceUI & AdminUI
    classDef ui fill:#e8f3ed,stroke:#176448,color:#153c2e
    classDef api fill:#eaf0fa,stroke:#3c6794,color:#203c5b
    classDef ai fill:#eeeafa,stroke:#67539a,color:#352856
    classDef data fill:#f1f3f4,stroke:#687979,color:#263c3c
    class Login,ScopePicker,OperationsUI,IntelligenceUI,AdminUI,Proxy,Output ui
    class Auth,Scope,Contracts,CRUD,Reads,Actions,Jobs,Files,Events api
    class ML,Rules,Simulator,Agent,Policy,Adapter,Provider,Reports ai
    class DB,Worlds,Audit,Blob,Alternative,Scheduler,Dispatch,Redis,Worker,Starter,Private,Public,Training,Artifacts,Generator data
```

The offline private-truth branch has no runtime connection. An agent can use only authorized tools; it cannot query SQL, read the filesystem, run shell commands or operate hospital equipment. The runtime has no arbitrary model-upload execution path. Reports, risk rules and simulations work without the LLM.

## Separate user scopes

[Editable Mermaid](diagrams/user-scopes.mmd) · [SVG](diagrams/user-scopes.svg) · [PNG](diagrams/user-scopes.png)

```mermaid
flowchart LR
    Identity["Authenticated real user<br/>Organization membership and explicit facility/zone grants"]
    subgraph Org["Organization admin"]
        OA["Scope<br/>Own organization and granted facilities<br/>Selected world and virtual cutoff"]
        OW["Writes<br/>Facility, policies, imports, models<br/>All permitted operating domains and actions"]
        OR["Review<br/>Approve proposals and eligible owners<br/>Independently verify and close actions"]
        OA --> OW --> OR
    end
    subgraph Hospital["Hospital admin"]
        HA["Scope<br/>Granted hospital facility<br/>All granted zones in selected world"]
        HW["Writes<br/>Facility configuration, policies and model serving<br/>Imports, operating ledgers and actions"]
        HR["Review<br/>Approve proposals and eligible owners<br/>Independently verify and close actions"]
        HA --> HW --> HR
    end
    subgraph Operations["Operations supervisor"]
        SA["Scope<br/>Granted facility and zones<br/>Facility-wide grant in the demo"]
        SW["Writes<br/>Assets and maintenance · waste<br/>Environment · parking · safety<br/>Actions, simulations and reports"]
        SR["Review<br/>Manage assigned work and transitions<br/>Independent action verification/closure<br/>No proposal approval or admin configuration"]
        SA --> SW --> SR
    end
    subgraph Technician["Maintenance technician"]
        TA["Scope<br/>Only granted zones<br/>Demo grant: WARD_A"]
        TW["Writes<br/>Create assets within zone grant<br/>Maintenance orders assigned to self<br/>Maintenance actions assigned to self"]
        TR["Limits<br/>Owner-limited asset/order/action updates<br/>No what-if execution or report generation<br/>No independent verification or admin writes"]
        TA --> TW --> TR
    end
    subgraph Waste["Waste officer"]
        WA["Scope<br/>Granted facility and zones<br/>Facility-wide grant in the demo"]
        WW["Writes<br/>Waste bins, batches and pickups<br/>Waste-category actions<br/>What-if simulations"]
        WR["Limits<br/>Own action progression<br/>No report generation, admin configuration<br/>or independent verification/closure"]
        WA --> WW --> WR
    end
    subgraph Sustainability["Sustainability officer"]
        CA["Scope<br/>Granted facility and zones<br/>Facility-wide grant in the demo"]
        CW["Writes<br/>Versioned tariffs and emission factors<br/>Sustainability-category actions<br/>What-if simulations and reports"]
        CR["Limits<br/>Own action progression<br/>No facility/policy/model/import administration<br/>or independent verification/closure"]
        CA --> CW --> CR
    end
    subgraph Auditor["Auditor"]
        AA["Scope<br/>Granted facility and zones<br/>Facility-wide grant in the demo"]
        AW["Allowed<br/>Read operating evidence and saved results<br/>Generate reports and download authorized files<br/>Ask-mode grounded chatbot"]
        AR["Limits<br/>No operating CRUD, action writes or proposals<br/>No new what-if execution or investigation mode"]
        AA --> AW --> AR
    end
    Identity --> OA & HA & SA & TA & WA & CA & AA
    OR & HR & SR & TR & WR & CR & AR --> Gateway["Shared FastAPI authorization boundary<br/>Role does not bypass organization/facility/zone grants<br/>CSRF, allowed Origin, contracts and current versions"]
    Gateway --> Read["Read scope<br/>Authorized operating domains in granted facility/zones<br/>World cutoff and evidence links remain scoped"]
    Gateway --> Write["Write scope<br/>Only permitted domain + category + zone + owner<br/>Audit and evidence required by workflow"]
    Gateway --> Chat["Agent scope equals initiating user scope<br/>Owner-private conversations, runs, tools and jobs<br/>Administrators can inspect authorized users' runs"]
    Read & Write & Chat --> RLS[("Restricted PostgreSQL runtime role<br/>FORCE RLS plus relational constraints<br/>Transaction-local user and organization identity")]
    RLS --> World["Independent base, stress or extended world<br/>No cross-world data substitution"]
    World --> Output["Scope-correct dashboard, tools and exports<br/>Denied operations return an explicit error"]
    classDef admin fill:#e8f3ed,stroke:#176448,color:#153c2e
    classDef operational fill:#eaf0fa,stroke:#3c6794,color:#203c5b
    classDef constrained fill:#fff3df,stroke:#a87926,color:#59401b
    classDef boundary fill:#eeeafa,stroke:#67539a,color:#352856
    class OA,OW,OR,HA,HW,HR admin
    class SA,SW,SR,WA,WW,WR,CA,CW,CR operational
    class TA,TW,TR,AA,AW,AR constrained
    class Identity,Gateway,Read,Write,Chat,RLS,World,Output boundary
```

Operational reads are governed by grants and RLS, rather than invented role-specific data silos. A waste or sustainability officer with a facility-wide grant can read authorized context from other operational domains. Domain write permission remains narrow. The technician's zone grant excludes facility-wide rows that have no granted zone.

## Permission matrix

“Yes” always means **within explicit grants** and subject to the operation's additional contract, ownership and evidence checks.

| Capability | Org admin | Hospital admin | Supervisor | Technician | Waste officer | Sustainability officer | Auditor |
|---|---|---|---|---|---|---|---|
| Read scoped operational data | Yes | Yes | Yes | Granted zones | Yes | Yes | Yes |
| Facility, policy, import and model administration | Yes | Yes | No | No | No | No | No |
| Assets and maintenance CRUD | Yes | Yes | Yes | Granted zones; own updates/orders | No | No | No |
| Waste workflow CRUD | Yes | Yes | Yes | No | Yes | No | No |
| Environment, parking and safety CRUD | Yes | Yes | Yes | No | No | No | No |
| Tariff and emission-factor versions | Yes | Yes | No | No | No | Yes | No |
| New what-if simulations | Yes | Yes | Yes | No | Yes | Yes | No |
| Generate reports | Yes | Yes | Yes | No | No | Yes | Yes |
| Ask-mode chatbot | Yes | Yes | Yes | Within zone grant | Yes | Yes | Yes |
| Investigate and draft | Yes | Yes | Yes | Tools remain zone/role constrained | Yes | Yes | No |
| Create actions | Yes | Yes | Yes | Maintenance; self | Waste category | Sustainability category | No |
| Approve an action proposal | Yes | Yes | No | No | No | No | No |
| Independently verify and close actions | Yes | Yes | Yes | No | No | No | No |
| Inspect another user's agent run/job | Within scope | Within scope | No | No | No | No | No |

The two admin roles currently share the same domain permission set. Their effective visibility comes from membership and facility/zone grants; the diagram does not imply that an organization admin can access an ungranted facility. The runtime's monitor service account is not a jury login. It has an operations-supervisor membership and still requires enabled server/facility policy before autonomous task creation.

Authorization sources: [role permissions and grant resolution](../services/api/app/core/auth.py), [domain contracts](../services/api/app/domains/contracts.py), [CRUD ownership checks](../services/api/app/domains/crud.py), [action transitions](../services/api/app/domains/actions.py), [agent tool restrictions](../services/api/app/ai/tools.py), [proposal approval](../services/api/app/routes.py), [database role policies](../services/api/alembic/versions/0004_write_permissions.py) and [demo grant setup](../services/api/app/bootstrap.py).

[Complete operational workflow](workflow.md) · [README and screenshot gallery](../README.md) · [Architecture](architecture.md)
