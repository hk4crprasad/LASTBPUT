# Actual verification evidence

These files are captured results from real local services on 8 October 2026, not example output. Provider keys, generated passwords and privileged connection URLs are excluded. `manifest.json` records file SHA256 hashes and environment/counts. The initial complete browser suite passed five flows; after the final bounded waste-ledger change, its two affected page/CRUD flows were rerun and passed. The final backend suite passed 36 tests.

| Check | Evidence |
|---|---|
| Backend and original starter | [backend-tests.txt](backend-tests.txt), [starter-tests.txt](starter-tests.txt) |
| Browser | [browser-tests.txt](browser-tests.txt), [affected flows](browser-affected-tests.txt) |
| Real provider text, streaming and parallel reads | [provider.json](provider.json) |
| Fifteen grounded domain questions | [agent-campaign.json](agent-campaign.json) |
| Actual input change and refresh, original restored | [input-refresh.json](input-refresh.json) |
| All 250 authorized evidence URLs | [evidence-urls.json](evidence-urls.json) |
| Live risk → scenario → proposal → reviewed task, lifecycle and CSV/HTML/PDF | [http-demo.txt](http-demo.txt) |
| Warm performance | [performance.json](performance.json) |
| Fresh-service database/object restore | [recovery.txt](recovery.txt) |
| Migration reversibility and clean demo reset | [migration-cycle.txt](migration-cycle.txt), [demo-reset.txt](demo-reset.txt) |
| Actual Redis outage recovery | [redis-recovery.json](redis-recovery.json) |
| Actual model disable, baseline fallback and restore | [model-policy.json](model-policy.json) |
| Isolated production identity provisioning | [provisioning.json](provisioning.json) |
| Actual image private-truth boundary and trusted checksums | [runtime-boundary.txt](runtime-boundary.txt), [checksums.json](checksums.json) |

Offline training artifacts/evaluation are preserved in `research/evaluation/container-training-v1`; they are excluded from operating containers. The independent two-facility smoke campaign has 1,152 rows under `research/evaluation/campaign-smoke`; its private truth stays offline. The full optional 630,720-row campaign and public deployment were not performed. These results do not establish real-hospital model accuracy or measured savings.

Validation/demo records remain identifiable in the working demo database. For a new empty demonstration use the documented demo-only reset and re-seed process; it regenerates passwords and removes those records.


## Supabase, Azure, jury roles and complete page coverage

The original local results above are the M0–M10 baseline. The follow-up uses Supabase PostgreSQL 17.11, revision 0006 and private Azure Blob Storage. It retains 51,840 sources and 362,880 observations. The full cloud backend rerun passed 41 tests; seven distinct browser tests passed across recorded runs. The initial SQL timeout and chat proxy failure are preserved as failures, with actual successful reruns.

| Check | Actual evidence |
|---|---|
| Full cloud backend: 41 passes | [backend](cloud-backend-tests.txt) |
| Initial SQL timeout and isolated rerun | [initial failure](cloud-backend-initial.txt), [rerun](cloud-injection-rerun-tests.txt) |
| Seven browser scenarios, including role switching and live chat | [run summary](cloud-browser-tests.txt), [first five passes](cloud-browser-before-interruption.txt), [action/import pass and initial chat failure](cloud-browser-initial-remaining.txt), [final live chat pass](cloud-chat-tests.txt) |
| Actual cloud row counts and migration | [database](cloud-database.json) |
| Live provider capability check | [provider](cloud-provider.json) |
| Azure bytes, checksum and cross-world denial | [artifact round trip](cloud-artifact-roundtrip.txt) |
| Demo authentication, production refusal, storage prefix and static RLS | [targeted checks](cloud-demo-login-tests.txt) |
| All 20 loaded views and final screenshots | [clean page output](all-pages-tests.txt), [page results](../screenshots/pages/page-results.json), [initial refresh failures](page-refresh-initial.txt) |
| Rendered Mermaid technology, scope and workflow diagrams | [15 diagram renders](mermaid-tests.txt), [technology and role scopes](../techstack-and-scopes.md) |

[README gallery and diagrams](../../README.md) · [Cloud runbook](../cloud-services.md). Provider keys, credentials and privileged URLs are omitted from these files.

[Cloud follow-up SHA256 manifest](cloud-manifest.json) records the final evidence, captures, diagrams and relevant source hashes. [Readiness](cloud-readiness.json) confirms PostgreSQL, Redis and private object storage were available at the final check.
