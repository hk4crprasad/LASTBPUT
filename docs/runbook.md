# Operating runbook

## Startup and provider checks

Follow the root README. `docker compose run --rm migrate` safely repeats migrations/bootstrap. Seed and generate are explicit operations. A source-only MinIO build is used because the old official image tags could not be pulled; the pinned release is built from the official Go module. Lockfiles are `services/api/uv.lock` and `apps/web/package-lock.json`.

This machine's Docker socket denied access. Verification used rootless Podman with its Docker API socket and the ordinary Docker Compose configuration. Fresh-volume verification initially used ports 3100/8100 while development servers occupied the default ports. Those task-owned development services have been stopped; the final verified Compose stack runs on localhost:3000/8000. `./scripts/compose.sh` was tested without DOCKER_HOST and starts the rootless socket automatically. For rootless operation:

```bash
podman system service --time=0 unix:///tmp/greenops-podman.sock
# In another terminal:
export DOCKER_HOST=unix:///tmp/greenops-podman.sock
docker compose up --build -d
```

`check-llm` actually calls the selected endpoint; it is separate from deterministic CI. Model naming alone never establishes compatibility. The tested Azure GPT-6 Luna deployment uses `reasoning_effort=none`, `max_completion_tokens`, streaming and parallel tool calls; no temperature parameter. Set `LLM_SUPPORTS_STRICT_SCHEMA` only after verifying that capability. Provider chunks are collected server-side, then grounded final text is emitted; the UI streams persisted tool progress and reconnectable SSE events. See primary references in `references.md`.

## Offline training, evaluation and campaign

Original data/artifacts remain immutable. Training reads private labels only in the isolated offline container and writes a new version directory. Its runtime API image never mounts this data.

```bash
docker compose -f compose.training.yaml --profile offline build trainer
docker compose -f compose.training.yaml --profile offline run --rm trainer \
  python -m app.cli train --data /workspace/research/starter/data \
  --out /workspace/research/evaluation/local-training-v2
# Same explicit CLI supports evaluate (train/evaluate together produce the versioned evidence):
docker compose -f compose.training.yaml --profile offline run --rm trainer \
  python -m app.cli evaluate --data /workspace/research/starter/data \
  --out /workspace/research/evaluation/evaluated-v2
```

The real local training check used Python 3.12 and the exact supplied ML pins:

```bash
cd services/api && uv sync --frozen && cd ../..
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 services/api/.venv/bin/python \
  scripts/offline_train.py --data research/starter/data \
  --out research/evaluation/another-immutable-version
```

Outputs include six lead-specific regressors, generic detector, predictions, per-zone errors, chronological purge split manifest, artifact hashes and separately evaluated contextual detection metrics. They do not establish field accuracy. The supplied registry and stress failures remain the serving contract. New artifacts require offline review and an explicit checksum allowlist/release; the API never accepts arbitrary pickle/joblib files.

Use a new output version on subsequent runs. The recorded `retrained-v1` and `container-training-v1` evidence is already present; training refuses to overwrite completed output directories.

```bash
# Small independent-seed smoke campaign:
services/api/.venv/bin/python scripts/generate_campaign.py --days 2 --facilities 2 --zones 12 --out research/evaluation/campaign-smoke
# Full future option: 6 × 12 × 365 × 24 = 630,720 zone-hour rows:
services/api/.venv/bin/python scripts/generate_campaign.py --out research/evaluation/campaign-new-version
```

Archetypes are fictional campaign labels with independent seeds, not calibrated hospital populations. Campaign private truth files stay under `research/evaluation`; never mount them into API/worker or operating documents.

## Clean demo reset

Clock reset in the UI changes the cutoff; it does not erase records. A **clean database reset** is deliberately a migration-only CLI, restricted to `APP_MODE=demo`. It truncates demo tables, regenerates identities/credentials and requires re-seeding. API/worker never receive credentials capable of doing this.

```bash
docker compose stop api worker scheduler web
docker compose run --rm migrate python -m app.bootstrap --reset-demo
docker compose up -d
docker compose exec api python -m app.cli seed-demo
docker compose exec api python -m app.cli generate-world --config /app/data/public/extended-demo.yaml
# Repeat inference and retrieve the NEW credential file as in README.
```

A reset does not delete content-addressed object storage: previous objects may still be referenced by a backup. For an entirely new empty installation use a separate Compose project name and volumes. Do not share object buckets between unrelated deployments.

## Backup and restore

Quiesce writers before a coordinated database/artifact backup. Supply a dedicated backup connection that can read FORCE RLS tables; never use the restricted application URL. Backups contain confidential operating records, identities and password hashes: protect their directory and retain the matching environment/generated credential file separately. Object contents are immutable and SHA256 checked.

```bash
# Host needs Python project dependencies and PostgreSQL 18 client binaries.
export BACKUP_DATABASE_URL='postgresql://BACKUP_USER:SECRET@HOST:5432/greenops'
# Also provide OBJECT_STORAGE_ENDPOINT/ACCESS_KEY/SECRET_KEY/BUCKET in the backup process.
services/api/.venv/bin/python scripts/backup.py backup --directory /secure/greenops-backup
# Target must be a fresh, empty DB with bootstrap/runtime/migrator roles provisioned.
services/api/.venv/bin/python scripts/backup.py restore --directory /secure/greenops-backup
```

For local container clients, add `--container-runtime docker --database-container hospital-greenops-postgres-1` (or `podman`) to use that container's exact PostgreSQL client. The connection URL still identifies the target for the emptiness check. The container's local socket must permit the specified privileged username. The manifest verifies dump and object hashes before restore; objects must use the backed-up key prefix. Restore applies ownership to `greenops_migrator` and retains RLS policies/grants. Verify readiness, source/observation counts, file checksums, scope denial, demo smoke and migrations before resuming writers.

Actual validation restored 51,840 source rows, 362,880 observations and 12 artifacts into freshly created PostgreSQL/MinIO services, and checked FORCE RLS and revision 0005.

## Jobs, failures and monitoring

Jobs and outbox records live in PostgreSQL. Redis outage leaves requests pending; readiness returns 503. Restart Redis and worker/scheduler; dispatch picks pending IDs every ten seconds. Worker duplicate deliveries recheck a row lease/idempotency key. Expired leases are selected for recovery. `python -m app.cli reconcile-jobs` is an explicit owner-scoped recovery command. Inspect Jobs/Agent Activity for attempts, error type, status and actual result. Provider timeout/rate limit becomes `waiting_provider` with deferred retry, bounded by `JOB_MAX_RETRIES` (default 3), then explicitly fails. After fixing the dependency, an eligible owner/admin can retry a failed job from Jobs using its original snapshot; a new request captures refreshed state. Configuration failures never become successful answers. Cancellation stops future tools, not a transaction already committed before cancellation.

Monitoring uses an explicitly granted service principal. Deterministic rules work without an LLM. Monitor policies default disabled; enabling them schedules high/critical risks and overdue work with cooldowns. Policy changes are append-only. Autonomous software task creation also requires `AGENT_AUTONOMOUS_WRITES_ENABLED=true`, a current incident, selected categories/severities, eligible owners and daily caps. Essential equipment control is never available.

Track ingestion freshness/coverage, SQL request duration/request ID, jobs/leases/retries, detector incident volume, forecast fallback gaps, simulation failures, provider usage/latency/errors, budgets and action verification. Request/run IDs correlate evidence; keys are not logged. Structured failure records remain inspectable. The included performance command measures warmed actual HTTP latency and the 72-hour engine separately from queue dispatch time.

## Production preparation and rollback

`compose.production.yaml` provides TLS Caddy, secure cookies, no direct web/API ports and read-only application filesystems. It is configuration only; no deployment was performed. Set `APP_MODE=production`, private/public hostname, matching HTTPS `PUBLIC_URL`/`CORS_ORIGINS`, unique secrets and restricted networking. Production migration disables demo identities. Provision organizational identity/grants explicitly with the migration-only provisioning command before login. Demo clock/reset operations are unavailable in production.

Run migrations as a release step, keep the previous application image and a tested backup. Do not downgrade a data-changing migration without checking compatibility and backup. Model admin can disable a supplied model and restore `experimental_synthetic_only` serving with an audited reason/current version; no UI control can promote it to validated real-hospital accuracy. Historical forecasts remain immutable; a serving-policy version changes the inference run key. Roll back policies by appending the previous reviewed configuration with a new effective date, preserving historical evidence.

Identity provisioning example (edit organization, facilities and eligible operational users first; this is a local migration operation):

```bash
# Copy the reviewed input into the shared migration volume, then:
docker compose run --rm migrate python -m app.provision \
  --input /app/shared/provision.json --credentials-out /app/shared/provisioned-credentials.json
```

The input schema is illustrated by `docs/provision.example.json`. The command creates identities/grants and an empty operational world; it does not invent operational history. Existing roles are preserved, with conflicting role changes rejected. Read the generated password file securely and provision building/zone setup and approved public aggregate CSV inputs through the scoped API.
