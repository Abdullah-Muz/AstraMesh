"""Command-line interface: ``astramesh {run,validate,schema}``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from astramesh import __version__
from astramesh.core.config import ConfigError, load_scenario, scenario_json_schema
from astramesh.evaluation.runner import run_scenario

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INVALID_CONFIG = 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="astramesh", description=__doc__)
    parser.add_argument("--version", action="version", version=f"astramesh {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a scenario config and write run artifacts")
    run.add_argument("config", type=Path, help="scenario YAML file")
    run.add_argument("--out", type=Path, required=True, help="output run directory")
    run.add_argument("--experiment-id", default=None, help="override the experiment ID")
    run.add_argument(
        "--overwrite", action="store_true", help="allow writing into a non-empty directory"
    )

    validate = sub.add_parser("validate", help="validate a scenario config without running it")
    validate.add_argument("config", type=Path)

    sub.add_parser("schema", help="print the scenario configuration JSON Schema")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "run":
            result = run_scenario(
                args.config, args.out, experiment_id=args.experiment_id, overwrite=args.overwrite
            )
            print(f"run complete: {result.output_dir}")
            print(f"  events:        {result.n_events}")
            print(f"  events sha256: {result.events_sha256}")
            print(f"  config hash:   {result.manifest['config_hash']}")
            return EXIT_OK
        if args.command == "validate":
            config = load_scenario(args.config)
            print(f"valid: {args.config} (scenario_id={config.scenario_id})")
            print(f"  config hash: {config.config_hash()}")
            return EXIT_OK
        if args.command == "schema":
            print(json.dumps(scenario_json_schema(), indent=2, sort_keys=True))
            return EXIT_OK
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    raise AssertionError(f"unhandled command {args.command!r}")  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
