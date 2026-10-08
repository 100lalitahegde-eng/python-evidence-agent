# Running and diagnosing the component

1. Install the wheel in an isolated environment. Use a synthetic corpus first.
2. Run the CLI without `--audit-db` to avoid retention; opt in only in a restricted directory.
3. Consume `schema_version`, `status`, `errors`, and claim status together. A successful CLI
   exit does not mean a claim is true: it means retrieval completed.
4. In an async host, reuse EvidenceService on one loop, handle BusyError, and cancel request
   tasks on client cancellation. Let cancellation propagate and wait for cleanup at shutdown.

| Signal | Interpretation | Response |
| --- | --- | --- |
| BusyError | Per-instance active-run limit reached | Reject/defer upstream; do not create an unlimited retry queue |
| provider_timeout / deadline_exceeded | Cooperative provider work exceeded a time limit | Inspect adapter/transport latency and cancellation behavior |
| provider_transient | Retryable provider failure exhausted attempts | Check provider health; avoid multiplying retries across layers |
| call_budget_exhausted | Total attempted calls reached policy limit | Inspect the trace before increasing the budget |
| invalid_provider_response | Adapter broke its ID/source contract | Fix/quarantine the adapter; do not trust the result as complete |
| partial | Some retrieval failed | Review surviving citations with the errors visible |
| persistence_failed (exit 4) | Result could not be committed | Check disk capacity, permissions and SQLite lock contention |

CLI exit codes: 0 complete retrieval, 2 invalid input/corpus or argparse usage error,
3 incomplete retrieval/internal failure, 4 persistence failure. JSON errors contain stable
codes; argparse syntax errors use its normal stderr usage output.

Track status rates, overload, tool-call counts and duration percentiles in the host.
No SLO or throughput result is claimed. Measure representative corpus sizes and concurrent
requests before choosing capacities. Audit data grows until the operator applies retention;
there is no automatic purge. SQLite WAL files are part of the active database: use SQLite's
backup API for a consistent backup, restore into a separate path, and verify representative
run IDs before switching. Backup/restore is guidance, not a deployment exercise verified here.
