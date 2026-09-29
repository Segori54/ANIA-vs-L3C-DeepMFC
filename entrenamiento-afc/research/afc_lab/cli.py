from __future__ import annotations

import argparse
import json

from .config import load_batch, load_config
from .runner import run_experiment


def main() -> None:
    parser = argparse.ArgumentParser(description="AFC thesis experiment runner")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="run one YAML/JSON experiment")
    run_parser.add_argument("config")
    batch_parser = subparsers.add_parser("batch", help="expand and run a parameter grid")
    batch_parser.add_argument("config")
    args = parser.parse_args()
    if args.command == "run":
        rows = run_experiment(load_config(args.config))
        print(json.dumps(rows, indent=2))
    elif args.command == "batch":
        all_rows = []
        for index, config in enumerate(load_batch(args.config)):
            all_rows.append({"run": index, "results": run_experiment(config)})
        print(json.dumps(all_rows, indent=2))


if __name__ == "__main__":
    main()
