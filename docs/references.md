# Implementation references

Checked 8 October 2026. The local build contract remains the specification; references do not turn illustrative assumptions into legal/clinical requirements.

- [WHO: climate resilient and environmentally sustainable health care facilities](https://www.who.int/publications/i/item/9789240012226/): operations scope and water, waste, energy, infrastructure resilience.
- [WHO WASH FIT](https://qualityhealthservices.who.int/quality-toolkit/qt-catalog-item/water-and-sanitation-for-health-facility-improvement-tool-%28wash-fit%29-a-practical-guide-for-improving-quality-of-care-through-water-sanitation-and-hygiene-in-health-care-facilities.-second-edition): evidence-based improvement plans and infrastructure maintenance context.
- [PostgreSQL 18 row security](https://www.postgresql.org/docs/18/ddl-rowsecurity.html): FORCE RLS, owner/bypass exceptions, USING/WITH CHECK.
- [OpenAI Python SDK](https://github.com/openai/openai-python): AsyncOpenAI, custom base URL and bounded retries.
- [Using GPT-6](https://developers.openai.com/api/docs/guides/latest-model): current reasoning and parameter compatibility guidance.
- [GPT-6 Luna model](https://developers.openai.com/api/docs/models/gpt-6-luna): official model capabilities; compatible Azure deployments must still be checked directly.
- [Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create): `max_completion_tokens`, streaming and parallel tool-call request fields. The configured Azure endpoint passed real capability checks; no `temperature` or `max_tokens` is sent.
- [Celery tasks](https://docs.celeryq.dev/en/stable/userguide/tasks.html): late acknowledgements require idempotent effects.
- [Next.js installation](https://nextjs.org/docs/app/getting-started/installation): App Router and current package compatibility.
- [MinIO source repository](https://github.com/minio/minio): source-only distribution. Registry pulls for official MinIO tags failed; the repository uses a pinned Go source build of RELEASE.2025-04-22T22-12-26Z.

Sources inform engineering and scope. Waste age 24 h, environmental thresholds, tariff INR 8/kWh and carbon factor 0.7 kgCO2e/kWh are explicitly labeled internal synthetic demo assumptions, not quoted official current requirements.
