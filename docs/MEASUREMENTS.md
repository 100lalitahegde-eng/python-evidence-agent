# Measurements — 2026-10-17

These are development measurements, not a production SLO or scientific accuracy claim.
Raw data: `benchmarks/results.json`, `evaluations/results.json`.

## Sustained workload

Command: `python -m benchmarks.load --seconds 60 --concurrency 4`
Environment: Python 3.12.14, Linux-6.18.55-x86_64-with-glibc2.39. Shared container; CPU quota and
host contention were not controlled. Four closed-loop clients; packaged synthetic local
corpus, one claim/run, spawned lexical assessment, SQLite FULL-sync save per run.
Latency includes persistence. No network/provider latency is represented. No warmup exclusion.

| Metric | Observed |
| --- | ---: |
| Measured duration | 60.084 s |
| Completed / successful | 2632 / 2632 |
| Throughput | 43.81 runs/s |
| p50 / p95 / p99 | 89.24 / 109.01 / 117.35 ms |
| Maximum latency | 142.84 ms |
| SQLite initial / final size | 12288 / 3751936 bytes |
| Physical growth / run | 1420.84 bytes |
| Parent RSS initial / final | 18247680 / 21708800 bytes |
| Parent peak RSS | 20940 KiB |
| Largest child peak RSS | 20940 KiB |
| Cancellation trials | 20 |
| Cancellation p95 / maximum | 1.031 / 1.097 ms |
| Workers / admission slots left after cancellations | 0 / 0 |

Database integrity check: `ok`; retained rows equal completed runs.
One-second samples include parent RSS and database/WAL sizes. Child peak is the largest
individual child, **not aggregate process-tree memory**. Parent RSS also includes harness
latency/sample accumulation. These data cannot establish absence of a long-term leak.
Cancellation probes cancel during a deliberately 30-second synchronous assessment after
75 ms; separate tests cover retrieval cancellation, a real sleeping transport subprocess,
and a 150 ms run deadline against a slow assessment. Deadline test tolerance is one second
to accommodate shared CI scheduling; no claim of zero deadline overshoot is made.

Physical growth depends on result size, page layout and indexes. Retention remains unbounded
across runs: this exercise measures growth, it does not implement automatic data deletion.
Run the manual workflow for 120-second concurrency 1/4/8 measurements on a consistent runner.
Long soak, open-loop overload, large sources/multiple claims, aggregate child memory,
network contention and disk-full tests remain follow-up qualification work.

## Labeled retrieval evaluation

36 authored synthetic cases: 12 software domains, each with support, contradiction and
irrelevant lexical-match variants. Includes negation, quantities, version/condition scope,
paraphrases, quoted/UI text, questions, proposals and entity mismatch. Each record stores
its gold label and annotation rationale. Labels have not received independent expert review;
this is a representative challenge set for software evidence, not general scientific NLI.
No cases were used to tune a semantic classifier; no such classifier is implemented.

| Gold label | Cases | Selected by lexical baseline |
| --- | ---: | ---: |
| Support | 12 | 10 |
| Contradiction | 12 | 8 |
| Irrelevant | 12 | 12 |

Support candidate recall is 83.3%. If selection were incorrectly interpreted as support,
only 10/30 (33.3%) selected cases would actually support the claim. Contradiction candidates
can be useful for review, but must not be called supporting evidence. Stance accuracy is
reported as null because the adapter does not predict stance. The application continues to
say `needs human verification`. Run `python -m evaluations.score` to reproduce the counts.

## External retrieval verification

Optional `WikipediaRetrieval` uses the actual MediaWiki search/lead-extract API contract.
Tests exercise real loopback HTTP sockets and the real transport subprocess, response/status
mapping, size limits, malformed/missing pages, input IDs, cancellation and process cleanup.
TLS certificate verification is supplied by urllib's default HTTPS transport; loopback
integration does not independently exercise TLS or establish live API compatibility.

A live `--wikipedia` smoke attempt for Earth ended with two provider timeouts (about 4.16 s
total). No successful live retrieval is claimed. This environment has restricted external
network access; rerun the command on a network-enabled host before relying on this adapter.
Wikipedia leads are secondary reference material, not primary scientific evidence.

## Verification

26 tests pass with `python -W error -m unittest discover -s tests -q` on Python 3.12.
Version 0.3.0 wheel builds, installs and runs its module CLI outside the checkout, producing
validated citations. Existing CI will verify Python 3.11–3.13 after the branch is pushed.
Custom assessor migration: module-level picklable class/state and guarded host entry point.
