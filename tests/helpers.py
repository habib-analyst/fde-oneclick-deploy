"""Shared test helpers: a base spec and a deterministic ticking clock."""
from datetime import datetime, timedelta, timezone

BASE_SPEC = {
    "customer": "acme-corp",
    "environment": "production",
    "region": "us-east-1",
    "tier": "medium",
    "version": "1.0.0",
    "port": 8080,
    "feature_flags": {"audit_log": True, "metrics": True},
    "secrets": {
        "DB_PASSWORD": "vault://prod/acme/db-password",
        "API_TOKEN": "env://ACME_API_TOKEN",
    },
}


def make_spec(**overrides):
    spec = dict(BASE_SPEC)
    spec.update(overrides)
    return spec


class TickingClock:
    """Returns start, start+1s, start+2s, ... on successive calls."""

    def __init__(self, start=None):
        self._t = start or datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self):
        t = self._t
        self._t = self._t + timedelta(seconds=1)
        return t
