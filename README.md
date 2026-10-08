# Evidence workflow service — Python

An embeddable, bounded evidence-retrieval pipeline with validated source snapshots,
exact citation spans, explicit partial failures, cancellable async orchestration and
optional transactional run retention. The included retrieval and assessment adapters
are deterministic and offline. Candidate passages always require human verification.

## Run

Python 3.11–3.13 are covered by the CI matrix. No runtime dependencies.

```sh
python -m pip install .
evidence-agent 'How do reservation holds consume capacity?' \
  --claim 'A hold consumes available capacity while active.'
python -m unittest discover -s tests -v
```

The installed package includes a synthetic sample corpus. Use `--corpus path.json`
for your own bounded local corpus and `--max-reads 3` to choose a read budget. The original
`from evidence_agent.agent import Agent, Corpus` and module CLI remain supported.
Do not use the sample design notes as evidence of another repository's current behavior.

```python
from evidence_agent.assessment import LexicalAssessment
from evidence_agent.corpus import Corpus, LocalRetrieval
from evidence_agent.domain import Policy, Request
from evidence_agent.service import EvidenceService
from pathlib import Path

# Create once per application event loop; inject another retrieval adapter as needed.
service = EvidenceService(LocalRetrieval(Corpus(Path("corpus.json"))),
                          LexicalAssessment(), Policy(max_reads=3, max_concurrent=8))
# Inside an async function:
# result = await service.run(Request("reservation capacity", ("Active holds consume capacity.",)))
```

## Architecture

Domain contracts → application orchestration → injected retrieval/assessment adapters.
The CLI wires dependencies and optional storage. See [architecture decisions](docs/ARCHITECTURE.md)
for boundaries, retry semantics, source trust and deliberate trade-offs.

- Validates corpus schemas, unique IDs, URLs, input sizes, read limits and finite deadlines.
- Rejects excess concurrent runs immediately; caps provider attempts including retries.
- Retries transient read-only failures with bounded backoff and cooperative call timeouts.
- Propagates caller cancellation and releases admission capacity in all exit paths.
- Distinguishes complete, partial and failed retrieval; missing evidence after a failure
  is marked `retrieval incomplete`, never presented as a complete negative assessment.
- Validates every citation against exact source offsets and SHA-256 before output.
- Emits a versioned JSON envelope, correlation ID, tool trace and timing/call metrics.
- Keeps input/source content and provider error messages out of standard telemetry.

`--audit-db runs.db` opts into saving complete results, including input and excerpts.
Results commit atomically and duplicate IDs cannot overwrite previous runs. Treat that
file as sensitive. The default performs no persistence. See the [operations guide](docs/OPERATIONS.md)
for exit codes, diagnosis, storage limits and hosting responsibilities.

## Verification and evidence boundary

CI runs unit, async failure-injection, SQLite reopen, CLI integration and synthetic
regression tests on three Python versions. It builds a wheel and exercises its installed
entry point outside the checkout, checking that the default corpus is packaged.
Coverage includes overload, cancellation cleanup, retry exhaustion, total call budgets,
permanent failures, partial retrieval, malformed providers and fabricated citations.

`evaluations/cases.json` records supported, contradictory, unrelated and unretrieved
synthetic cases. A contradiction can still receive a lexical candidate; the suite makes
that limitation explicit. These are regression checks, not expert-labelled scientific
accuracy measurements. Source instructions remain data and cannot schedule extra tools.

The current implementation is an offline evidence component. No live model planner,
external web retrieval, semantic claim
verification, HTTP authentication, multi-tenant isolation, deployed SLO, or workload
benchmark is implemented. Async providers must cooperate with cancellation; Python cannot
forcibly stop a blocking provider. Deployment and production load/recovery remain unverified.
