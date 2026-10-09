# Supabase PostgreSQL and Azure Blob Storage

The cloud adapters keep the app local: web/API ports bind to loopback. No public deployment is required. Provider and storage keys live only in ignored `.env` (mode 600); application containers receive only their required secrets. Do not copy another application's entire environment into GreenOps.

The Next.js same-origin proxy allows up to 180 seconds for upstream requests and SSE connections. Cloud snapshot capture performs multiple permission-scoped SQL reads and can exceed the proxy's ordinary short timeout. Unexpected non-JSON upstream errors are shown as explicit API errors. The agent's own execution, retry and cancellation budgets remain separate. These settings do not claim local-equivalent cloud latency.

## PostgreSQL

Use a dedicated Supabase project with an empty `public` schema. GreenOps migrations own their tables and apply FORCE RLS and explicit grants. Supabase's administrator connection must never be the API/worker runtime connection.

1. Put `SUPABASE_ADMIN_DATABASE_URL=postgresql+psycopg://postgres.PROJECT:PASSWORD@POOLER:5432/postgres?sslmode=require` in `.env`. This is the IPv4 session pooler used for DDL.
2. Install the host command environment with `uv sync --project services/api`, then run `services/api/.venv/bin/python scripts/configure_supabase.py`. It generates a random password for a `greenops` runtime role with `NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB`. It verifies the login before saving `DATABASE_URL` and `MIGRATION_DATABASE_URL`. Existing credentials are preserved on repeat execution.
3. Set `COMPOSE_FILE=compose.yaml:compose.supabase.yaml` in `.env` (add `:compose.azure.yaml` when using Azure).
4. Run `./scripts/compose.sh up --build -d`. Migrations and demo bootstrap run before API startup. Seed/generate/infer commands remain those in README. After the initial bulk cloud load, run `services/api/.venv/bin/python scripts/analyze_database.py` to refresh statistics on the 72 app tables without changing other schemas.

The transaction pooler (6543) runs API/worker requests. Psycopg automatic prepared statements are disabled with `DATABASE_PREPARE_THRESHOLD=disabled`. Identity uses transaction-local `set_config(..., true)`; pooled sessions do not retain tenant identity. TLS is required. The configured cloud statement budget is `DATABASE_STATEMENT_TIMEOUT_MS=10000`; the local default remains 3000 ms. Connection setup is bounded by `DATABASE_CONNECT_TIMEOUT_SECONDS=15`. Cloud response times include remote connection latency and are distinct from the earlier local performance results. The checked Supabase server reports PostgreSQL 17.11; local Compose retains PostgreSQL 18.3. No PostgreSQL 18-only features are required by the schema.

Migration credentials are only passed to the one-shot migrator. A Supabase admin supplies bypass privileges for migrations/security-definer functions; the app runtime remains restricted. Installing the schema does not transfer earlier actions, sessions or artifacts from another database: demo commands recreate the supplied synthetic operational worlds.

## Azure storage

The API and worker support private Azure Blob Storage directly with the official Python SDK. Set:

```dotenv
OBJECT_STORAGE_PROVIDER=azure
AZURE_STORAGE_CONNECTION_STRING=YOUR_SERVER_SIDE_CONNECTION_STRING
AZURE_STORAGE_CONTAINER=YOUR_PRIVATE_CONTAINER
AZURE_STORAGE_PREFIX=hospital-greenops/
AZURE_STORAGE_CREATE_CONTAINER=false
COMPOSE_FILE=compose.yaml:compose.supabase.yaml:compose.azure.yaml
```

Alternatively set `AZURE_STORAGE_ACCOUNT_URL=https://ACCOUNT.blob.core.windows.net` and `AZURE_STORAGE_ACCOUNT_KEY`, leaving the connection string empty. These storage values have no relationship to the Azure OpenAI endpoint/key.

Create a private container through Azure Portal/IaC before startup. With `AZURE_STORAGE_CREATE_CONTAINER=false`, GreenOps never creates it. The explicit opt-in `true` permits private creation. Readiness checks reject public containers. All physical blob names begin with the non-empty application prefix; tenant/facility/world/category/checksum keys follow it. This permits isolation in an existing private container. Backup enumeration filters this prefix and never copies unrelated application blobs.

Downloads still authenticate through GreenOps and check database scope and SHA256. The browser never receives account keys, SAS URLs or public blob URLs. Reports and uploads use the same storage interface. `scripts/backup.py` also supports both providers; run it with the API environment/venv and a dedicated backup DB connection and matching PostgreSQL client tools. Supabase restores use `--restore-role postgres`; local restores use the default `greenops_migrator`. Database dumps include only the app public schema, excluding Supabase internal schemas. Switching providers does not silently copy old objects; back up and restore the app's objects explicitly if preserving an existing database.

MinIO and local PostgreSQL are omitted by the overlays. Redis remains local for Celery. To return to local services, restore the local DB URLs, set `OBJECT_STORAGE_PROVIDER=s3` and `COMPOSE_FILE=compose.yaml`. Local and remote database contents are independent.

## Demo sign-in

In `APP_MODE=demo`, the entrance shows seven one-click role buttons. Each authenticates against the actual Argon2 password hash and creates the regular session/CSRF cookies. Credentials remain in the server's demo credential file; passwords are never returned by the account-list endpoint or shipped in the frontend bundle. Manual email/password sign-in still works. Sign out to switch perspectives.

In `APP_MODE=production`, the account list is empty and the demo login endpoint returns HTTP 403. The maintenance technician retains Ward A-only grants; auditors retain their restricted writes. These are demo accounts, so demo mode should only be enabled for the synthetic demonstration.

References: [Supabase connection modes](https://supabase.com/docs/guides/database/connecting-to-postgres), [Supabase prepared statement restrictions](https://supabase.com/docs/guides/troubleshooting/disabling-prepared-statements-qL8lEL), [Microsoft Azure Blob Python SDK](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blob-python-get-started).
