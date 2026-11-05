"""Fixture health checks.

In-process functions that simulate the deployed stack's health endpoints.
Which checks run depends on the spec's feature flags, mirroring how a real
stack exposes more surface when more features are enabled.
"""
from __future__ import annotations


def check_app(spec: dict) -> tuple[str, bool, str]:
    return ("app", True, f"app {spec['version']} responding")


def check_proxy(spec: dict) -> tuple[str, bool, str]:
    return ("proxy", True, f"proxy forwarding to port {spec['port']}")


def check_sso(spec: dict) -> tuple[str, bool, str]:
    return ("sso", True, "sso endpoint responding")


def check_metrics(spec: dict) -> tuple[str, bool, str]:
    return ("metrics", True, "metrics endpoint responding")


def run_health_checks(spec: dict, *, checker=None) -> list[tuple[str, bool, str]]:
    """Run the fixture checks for a spec and return (name, ok, detail) rows.

    ``checker`` may be injected (a callable taking the spec and returning
    rows) to simulate an unhealthy stack in tests.
    """
    if checker is not None:
        return list(checker(spec))
    checks = [check_app, check_proxy]
    flags = spec.get("feature_flags", {})
    if flags.get("sso"):
        checks.append(check_sso)
    if flags.get("metrics"):
        checks.append(check_metrics)
    return [fn(spec) for fn in checks]
