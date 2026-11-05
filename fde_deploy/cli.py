"""Command line interface.

    python3 -m fde_deploy validate --spec spec.yaml
    python3 -m fde_deploy deploy   --root ./sandbox --spec spec.yaml
    python3 -m fde_deploy rollback --root ./sandbox
    python3 -m fde_deploy status   --root ./sandbox
    python3 -m fde_deploy history  --root ./sandbox

Exit codes: 0 = success, 2 = spec/preflight problem, 1 = other failure.
Errors are printed to stderr in plain language.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .preflight import PreflightError
from .release import DeployError, deploy, history, rollback, status
from .spec import SpecError, load_spec, spec_hash, validate_spec


def _add_root(parser):
    parser.add_argument("--root", required=True,
                        help="sandbox directory standing in for the target host")


def _add_spec(parser):
    parser.add_argument("--spec", required=True, help="path to the deployment spec (YAML or JSON)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fde_deploy",
                                     description="One-click customer deployment toolkit (local sandbox).")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="validate a spec and print its hash")
    _add_spec(p)

    p = sub.add_parser("deploy", help="validate, preflight, deploy and health-check a spec")
    _add_root(p)
    _add_spec(p)

    p = sub.add_parser("rollback", help="roll back to the previous release")
    _add_root(p)

    p = sub.add_parser("status", help="show the live release")
    _add_root(p)

    p = sub.add_parser("history", help="show deploy history")
    _add_root(p)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            spec = validate_spec(load_spec(args.spec))
            print(f"spec OK: {spec['customer']} {spec['version']} "
                  f"({spec['environment']}, {spec['region']}, tier {spec['tier']})")
            print(f"spec hash: {spec_hash(spec)}")
            return 0

        if args.command == "deploy":
            manifest = deploy(Path(args.root), load_spec(args.spec))
            print(f"deployed release {manifest['release_id']} "
                  f"(version {manifest['version']}) to {args.root}")
            print(f"spec hash: {manifest['spec_hash']}")
            return 0

        if args.command == "rollback":
            manifest = rollback(Path(args.root))
            print(f"rolled back: current is now release {manifest['release_id']} "
                  f"(version {manifest['version']})")
            return 0

        if args.command == "status":
            info = status(Path(args.root))
            if info["current"] is None:
                print("no release deployed")
            else:
                print(json.dumps(info, indent=2, sort_keys=True))
            return 0

        if args.command == "history":
            rows = history(Path(args.root))
            if not rows:
                print("no deploy history")
            for row in rows:
                print(f"{row['ts']}  {row['action']:<8}  {row['release_id'] or '-':<24} "
                      f"v{row['version'] or '-':<8}  {row['status']}"
                      + (f"  ({row['detail']})" if row["detail"] else ""))
            return 0

    except SpecError as exc:
        print(f"error: invalid spec: {exc}", file=sys.stderr)
        return 2
    except PreflightError as exc:
        print(f"error: preflight failed: {exc}", file=sys.stderr)
        return 2
    except DeployError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"error: file not found: {exc.filename}", file=sys.stderr)
        return 2
    return 0  # pragma: no cover
