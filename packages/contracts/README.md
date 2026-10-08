# Public contracts

`openapi.json` is generated from FastAPI; `domain-schemas.json` contains the typed operational write contracts. Regenerate with `services/api/.venv/bin/python scripts/export_contracts.py`. Then, from `apps/web`, run `npx openapi-typescript ../../packages/contracts/openapi.json -o lib/generated-api.ts`.

The frontend imports generated action/transition/scenario request types. Dynamic record editors fetch the same authenticated domain schemas at runtime. No operational data, credentials or private evaluation truth is included in these files.
