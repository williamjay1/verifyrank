"""Command-line entry point."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
from . import __version__
from .core import evaluate, load_csv, load_json
from .report import write_report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="verifyrank", description="Evaluate frozen weights against incomplete reference evidence.")
    parser.add_argument("--version", action="version", version=f"verifyrank {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="validate inputs and write CSV, JSON and HTML reports")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="JSON object with decisions and references arrays")
    source.add_argument("--decisions", type=Path, help="frozen selection weights CSV")
    run.add_argument("--references", type=Path, help="evidence CSV, required with --decisions")
    run.add_argument("--output", required=True, type=Path)
    run.add_argument("--tolerance", type=float, default=.02)
    run.add_argument("--cost-budget", type=float, help="optional reference acquisition cost budget per policy pair")
    run.add_argument("--strategy", choices=("width_per_cost", "expected_width_per_cost"), default="width_per_cost")
    run.add_argument("--overwrite", action="store_true", help="explicitly replace report files, never inputs")
    args = parser.parse_args(argv)
    if args.decisions and not args.references:
        parser.error("--references is required with --decisions")
    if args.input and args.references:
        parser.error("--references cannot accompany --input")
    try:
        inputs = [args.input] if args.input else [args.decisions, args.references]
        data = load_json(args.input) if args.input else load_csv(args.decisions, args.references)
        result = evaluate(data, tolerance=args.tolerance, cost_budget=args.cost_budget, strategy=args.strategy)
        result["metadata"]["inputs"] = [{"name": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs]
        files = write_report(result, args.output, overwrite=args.overwrite, protected_paths=inputs)
        print(json.dumps({"status": "completed", "version": __version__, "output": str(args.output.resolve()),
                          "decision_count": result["metadata"]["decision_count"],
                          "policy_pairs": len(result["macro_comparison"]), "files": [p.name for p in files]}))
        return 0
    except (ValueError, OSError) as exc:
        print(f"verifyrank: {exc}", file=sys.stderr)
        return 2

