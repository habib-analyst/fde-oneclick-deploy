"""Deployment spec loading and validation.

A spec describes one customer deployment. Secrets are references only
(``vault://...`` or ``env://...``); a literal secret value anywhere in the
``secrets`` map is a validation error by design.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

try:
    import yaml  # type: ignore
    HAS_YAML = True
except ImportError:  # pragma: no cover - PyYAML present in the dev env
    yaml = None
    HAS_YAML = False

TIERS = {
    "small": {"cpu": "1", "memory_mb": 1024, "replicas": 1},
    "medium": {"cpu": "2", "memory_mb": 2048, "replicas": 2},
    "large": {"cpu": "4", "memory_mb": 4096, "replicas": 3},
}

ENVIRONMENTS = ("development", "staging", "production")

FEATURE_FLAGS = (
    "audit_log",
    "beta_api",
    "metrics",
    "new_ui",
    "rate_limiting",
    "sso",
)

SECRET_REF_RE = re.compile(r"^(vault|env)://[A-Za-z0-9_./\-]+$")
REGION_RE = re.compile(r"^[a-z]{2}-[a-z]+-\d+$")
CUSTOMER_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")

REQUIRED_FIELDS = ("customer", "environment", "region", "tier", "version")


class SpecError(ValueError):
    """Raised when a spec is invalid. Message is human-readable."""


def load_spec(path: str | Path) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    return parse_spec(text)


def parse_spec(text: str) -> dict:
    """Parse spec text. YAML when PyYAML is available, else JSON.

    JSON is a valid subset of YAML, so JSON specs work in both modes.
    """
    if HAS_YAML:
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise SpecError("spec must be a mapping at the top level")
    return data


def validate_spec(spec: dict) -> dict:
    """Validate a parsed spec; return a normalized copy.

    Raises SpecError listing the first problem found.
    """
    if not isinstance(spec, dict):
        raise SpecError("spec must be a mapping")

    for field in REQUIRED_FIELDS:
        if field not in spec or spec[field] in (None, ""):
            raise SpecError(f"missing required field: {field}")

    customer = spec["customer"]
    if not isinstance(customer, str) or not CUSTOMER_RE.match(customer):
        raise SpecError(
            f"invalid customer name: {customer!r} "
            "(lowercase letters, digits and hyphens only)"
        )

    if spec["environment"] not in ENVIRONMENTS:
        raise SpecError(
            f"invalid environment: {spec['environment']!r} "
            f"(allowed: {', '.join(ENVIRONMENTS)})"
        )

    region = spec["region"]
    if not isinstance(region, str) or not REGION_RE.match(region):
        raise SpecError(
            f"invalid region label: {region!r} (expected form like 'us-east-1')"
        )

    if spec["tier"] not in TIERS:
        raise SpecError(
            f"invalid sizing tier: {spec['tier']!r} "
            f"(allowed: {', '.join(sorted(TIERS))})"
        )

    version = spec["version"]
    if not isinstance(version, str) or not VERSION_RE.match(version):
        raise SpecError(f"invalid version: {version!r} (expected semver like '1.2.0')")

    flags = spec.get("feature_flags", {})
    if flags is None:
        flags = {}
    if not isinstance(flags, dict):
        raise SpecError("feature_flags must be a mapping of flag name to boolean")
    for name, value in flags.items():
        if name not in FEATURE_FLAGS:
            raise SpecError(
                f"unknown feature flag: {name!r} "
                f"(allowed: {', '.join(FEATURE_FLAGS)})"
            )
        if not isinstance(value, bool):
            raise SpecError(f"feature flag {name!r} must be true or false")

    secrets = spec.get("secrets", {})
    if secrets is None:
        secrets = {}
    if not isinstance(secrets, dict):
        raise SpecError("secrets must be a mapping of name to reference")
    for name, ref in secrets.items():
        if not isinstance(ref, str) or not SECRET_REF_RE.match(ref):
            raise SpecError(
                f"secret {name!r} must be a reference matching vault://... or "
                f"env://... — literal secret values are not allowed in a spec"
            )

    port = spec.get("port", 8080)
    if not isinstance(port, int) or isinstance(port, bool) or not (1 <= port <= 65535):
        raise SpecError(f"invalid port: {port!r} (expected integer 1-65535)")

    normalized = {
        "customer": customer,
        "environment": spec["environment"],
        "region": region,
        "tier": spec["tier"],
        "version": version,
        "feature_flags": {k: flags[k] for k in sorted(flags)},
        "secrets": {k: secrets[k] for k in sorted(secrets)},
        "port": port,
    }
    return normalized


def spec_hash(normalized_spec: dict) -> str:
    """Deterministic SHA-256 of the canonical (sorted, compact) spec JSON."""
    import hashlib

    canonical = json.dumps(normalized_spec, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
