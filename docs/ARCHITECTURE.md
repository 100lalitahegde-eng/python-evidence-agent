# Architecture and decisions

The product boundary is an embeddable evidence-retrieval service plus a packaged CLI.
Its output is a set of candidate passages for human review. The current adapter is
local and deterministic by default; opt-in Wikipedia retrieval fetches secondary-source lead extracts.

| Layer | Responsibility | Dependencies |
| --- | --- | --- |
| domain.py | Immutable validated requests, source snapshots, policy and citations | Standard library |
| ports.py | Async retrieval and synchronous assessment contracts; typed failures | Domain |
| service.py | Admission, budgets, retries, cooperative timeouts, partial results, traces | Domain and ports |
| corpus.py | Size/schema-limited local corpus, stable lexical ranking | Domain and retrieval errors |
| assessment.py | Sentence-level lexical candidates | Domain and tokenizer |
| store.py | Optional transactional local run retention | SQLite, result schema |
| cli.py | Composition, JSON output, exit codes, explicit persistence | Service and adapters |
| agent.py | Compatibility for existing synchronous consumers | Service and local adapters |

## ADR 1: preserve a deterministic baseline

Lexical overlap cannot establish entailment, contradictions, scientific validity or
source credibility. The assessor returns spans, never a verified verdict. A future
model adapter must preserve source-snapshot validation and distinguish its own predictions
from independent evidence. The synthetic contradiction case intentionally produces a
candidate: it documents the baseline's limitation instead of reporting misleading accuracy.
No content is sent externally by default. Opt-in Wikipedia retrieval sends the search question to its API; no model is used.

## ADR 2: bound work at application boundaries

Each service instance belongs to one event loop. At most `max_concurrent` runs enter;
excess calls raise BusyError immediately. There is no internal waiting backlog. An async
host should reuse one service per loop and translate overload into its chosen response.
Creating a service per request bypasses the shared admission bound. The sync compatibility
facade is intended for single-call tools, not admission control across threads/processes.

Read limits count successful source selections, while total call limits count every
search/read attempt, including retries. Only transient failures and timeouts retry with
bounded exponential delay; permanent and unexpected provider failures return stable codes.
Retries are safe here because retrieval is read-only. Do not reuse this retry policy for
mutating tools without an idempotency design. Deterministic backoff is sufficient for this
local adapter; distributed clients should add bounded jitter in their network adapter.

Custom async retrieval remains cooperative: adapters must not block the event loop or
suppress cancellation. The supplied Wikipedia adapter isolates DNS/socket work in a
killable subprocess, enforces a response cap and disables redirects. A timed-out call
kills/reaps its worker before returning or retrying. It uses the MediaWiki Action API
search and plaintext lead-extract contracts:
https://www.mediawiki.org/wiki/API:Search and
https://www.mediawiki.org/wiki/Extension:TextExtracts#API.

Synchronous assessment now runs in a spawned process (`isolated.py`), with the remaining
absolute run deadline covering startup, all claims and citation validation. Timeout discards
all assessment results, returns `assessment incomplete`, and kills/reaps the worker. Caller
cancellation also reaps before releasing admission. Workers do not mutate parent state;
assessors must be module-level/picklable. This deliberately changes the custom-assessor
contract: closures and local classes are rejected. Spawn and OS cleanup can overshoot the
deadline; the scheduler is not real-time. Persistence and final output serialization are
outside the assessment boundary. Process isolation is not a security sandbox.

## ADR 3: failures cannot masquerade as absence of evidence

A successful empty search means no candidate in the retrieved corpus. A failed search
or missing read means retrieval is incomplete. Partial results retain successful source
snapshots and explicit errors. A citation points to exact Python Unicode character offsets
(not UTF-8 byte offsets) plus the SHA-256 of the full source text. The application checks
all returned citations before publishing. Invalid assessor output raises and fails closed.
Hashes establish identity, not source authenticity. URLs are metadata, not fetch targets.

## ADR 4: trace metadata, persist content only explicitly

Tool traces contain operation, attempt, outcome code and duration. Logger records carry
run ID, status and call count; queries, source text and provider exception messages are
excluded. A host must configure structured log serialization to expose those extra fields.
The JSON result intentionally contains user input and evidence excerpts.

`--audit-db` explicitly opts into saving complete results. SQLite commits each result
atomically; the primary key rejects overwrite. A run ID is a correlation ID, not a request
idempotency key: repeating a request starts a new run. Storage failure prevents the CLI
from reporting success. This local store has no encryption, tenant isolation or distributed
coordination. Directory permissions, retention and backups belong to the operator.

## Evolution boundary

An HTTP product would additionally need authentication, authorization per corpus,
request-size limits at ingress, tenant-specific quotas, durable job ownership if requests
outlive connections, and health/metrics endpoints. Add those with a concrete hosting model.
Those deployment boundaries are outside the current component.

