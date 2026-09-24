import argparse
import json
from pathlib import Path
from .agent import Agent, Corpus


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--claim", action="append", required=True)
    parser.add_argument("--corpus", type=Path, default=Path(__file__).resolve().parents[1] / "corpus.json")
    args = parser.parse_args()
    print(json.dumps(Agent(Corpus(args.corpus)).run(args.question, args.claim), indent=2))


if __name__ == "__main__":
    main()
