# Evidence workflow agent (Python 3.12)

A reproducible, offline baseline for a research assistant. Its bounded tool loop searches a local corpus, reads at most three sources, records every tool call, and flags claims needing human verification. It never states that lexical overlap proves a scientific claim.

```sh
PYTHONPATH=. python3 -m unittest discover -s tests -v
PYTHONPATH=. python3 -m evidence_agent.cli 'How do reservation holds consume capacity?' --claim 'A hold consumes available capacity while active.'
```

## Architecture

`Corpus.search` ranks local documents by shared words; `Agent.run` reads within a fixed budget and emits source metadata, a trace, and claim flags. The fixture corpus uses local design notes, not external research. The result is inspectable JSON. The search and claim signals are deliberately conservative candidates, not semantic entailment or fact checking.

## Evaluation and next work

Current tests cover the read budget, trace, unsupported unrelated claim, and input validation. Before calling this an agentic AI portfolio project, add an actual model-backed planner behind an interface, an allowlisted external retrieval tool, evaluation cases with expert-labelled support and contradiction, citation-span validation, retry and timeout policy, and measured cost and latency. Keep the deterministic baseline as a comparison. Never send private documents to an external model without permission.
