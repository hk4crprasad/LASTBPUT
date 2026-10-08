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
