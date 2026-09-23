"""CLI entrypoint (spec §7).

    python -m router.cli route scenarios/flash-sale.json                 # table
    python -m router.cli route scenarios/flash-sale.json --json out.json # table + JSON file
    python -m router.cli route scenarios/flash-sale.json --json -        # JSON to stdout
"""

from __future__ import annotations

import argparse
import json
import sys

from .baselines import always_cheapest, always_fastest, cheapest_fit
from .logging_setup import configure_logging
from .models import ScenarioError, load_scenario
from .report import build_report, render_table
from .router import route


def _run_route(args: argparse.Namespace) -> int:
    try:
        scenario = load_scenario(args.scenario)
    except (ScenarioError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    router_result = route(scenario)
    baselines = [always_cheapest(scenario), cheapest_fit(scenario), always_fastest(scenario)]
    report = build_report(scenario, router_result, baselines)

    json_to_stdout = args.json == "-"

    # Table to stdout unless JSON is explicitly directed there.
    if not json_to_stdout:
        sys.stdout.write(render_table(report))

    if args.json:
        payload = json.dumps(report.to_dict(), indent=2)
        if json_to_stdout:
            sys.stdout.write(payload + "\n")
        else:
            with open(args.json, "w", encoding="utf-8") as fh:
                fh.write(payload + "\n")
            print(f"(JSON report written to {args.json})", file=sys.stderr)

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="router", description="Cost-aware inference router (prototype).")
    sub = parser.add_subparsers(dest="command", required=True)

    p_route = sub.add_parser("route", help="route a scenario and print the cost report")
    p_route.add_argument("scenario", help="path to a scenario JSON file")
    p_route.add_argument("--log-level", default="WARNING", help="DEBUG/INFO/WARNING/ERROR (default: WARNING)")
    p_route.add_argument(
        "--json", metavar="PATH", nargs="?", const="-", default=None,
        help="also write JSON report to PATH; '-' or bare flag prints JSON to stdout instead of the table",
    )
    p_route.set_defaults(func=_run_route)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
