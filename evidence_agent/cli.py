"""Composition root: wiring, JSON transport, explicit optional persistence."""
import argparse
import asyncio
from importlib.resources import files
import json
from pathlib import Path
import sqlite3
import sys
from .assessment import LexicalAssessment
from .corpus import Corpus, LocalRetrieval
from .domain import Policy, Request
from .service import EvidenceService
from .store import RunStore


def main():
    parser = argparse.ArgumentParser(description="Retrieve auditable candidate evidence from a local corpus")
    parser.add_argument("question")
    parser.add_argument("--claim", action="append", required=True)
    parser.add_argument("--corpus", type=Path, default=Path(str(files("evidence_agent").joinpath("data/corpus.json"))))
    parser.add_argument("--max-reads", type=int, default=3)
    parser.add_argument("--audit-db", type=Path, help="Persist full results (includes user input and evidence excerpts)")
    parser.add_argument("--wikipedia", action="store_true", help="Retrieve English Wikipedia lead extracts over HTTPS")
    parser.add_argument("--semantic", action="store_true", help="Use the predownloaded optional local NLI model")
    parser.add_argument("--deadline-seconds", type=float, default=10)
    parser.add_argument("--retain-runs", type=int, help="Keep only this many latest stored runs; opt-in deletion")
    args = parser.parse_args()
    try:
        request = Request(args.question, tuple(args.claim))
        from .wikipedia import WikipediaRetrieval
        retrieval = WikipediaRetrieval() if args.wikipedia else LocalRetrieval(Corpus(args.corpus))
        from .semantic import SemanticAssessment
        if args.retain_runs is not None and (not args.audit_db or args.retain_runs < 1):
            raise ValueError("retention requires audit-db and a positive count")
        service = EvidenceService(retrieval, SemanticAssessment() if args.semantic else LexicalAssessment(), Policy(max_reads=args.max_reads, deadline_seconds=args.deadline_seconds))
        result = asyncio.run(service.run(request))
        if args.audit_db:
            try:
                RunStore(args.audit_db, max_runs=args.retain_runs).save(result)
            except (sqlite3.Error, OSError):
                print(json.dumps({"error": {"code": "persistence_failed"}}))
                return 4
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0 if result["status"] == "complete" else 3
    except (ValueError, OSError):
        print(json.dumps({"error": {"code": "invalid_input_or_corpus"}}))
        return 2
    except sqlite3.Error:
        print(json.dumps({"error": {"code": "persistence_failed"}}))
        return 4
    except Exception:
        # Do not echo provider messages, filesystem paths, credentials or corpus data.
        print(json.dumps({"error": {"code": "internal_error"}}))
        return 3


if __name__ == "__main__":
    sys.exit(main())

