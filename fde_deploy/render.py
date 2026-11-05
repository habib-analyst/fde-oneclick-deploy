"""Deterministic artifact rendering.

Same normalized spec in -> byte-identical artifacts out. Templates live in
the top-level ``templates/`` directory as plain text files using
``string.Template`` placeholders.
"""
from __future__ import annotations

import hashlib
import string
from pathlib import Path

from .spec import TIERS

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

# artifact filename -> template filename
ARTIFACTS = {
    "docker-compose.yml": "docker-compose.yml.tmpl",
    ".env": "env.tmpl",
    "nginx.conf": "nginx.conf.tmpl",
    "app.service": "systemd.service.tmpl",
}


def _context(spec: dict) -> dict:
    tier = TIERS[spec["tier"]]
    secret_lines = ""
    for name in sorted(spec.get("secrets", {})):
        # Only the reference is rendered, never a resolved value.
        secret_lines += f"{name}_REF={spec['secrets'][name]}\n"
    flag_lines = ""
    for name in sorted(spec.get("feature_flags", {})):
        value = "true" if spec["feature_flags"][name] else "false"
        flag_lines += f"FEATURE_{name.upper()}={value}\n"
    return {
        "customer": spec["customer"],
        "environment": spec["environment"],
        "region": spec["region"],
        "tier": spec["tier"],
        "version": spec["version"],
        "port": str(spec["port"]),
        "cpu": tier["cpu"],
        "memory_mb": str(tier["memory_mb"]),
        "replicas": str(tier["replicas"]),
        "secret_lines": secret_lines,
        "flag_lines": flag_lines,
    }


def render_artifacts(spec: dict) -> dict[str, str]:
    """Render all artifacts for a normalized spec. Returns {filename: text}."""
    ctx = _context(spec)
    rendered: dict[str, str] = {}
    for artifact_name, template_name in ARTIFACTS.items():
        template_text = (TEMPLATE_DIR / template_name).read_text(encoding="utf-8")
        rendered[artifact_name] = string.Template(template_text).substitute(ctx)
    return rendered


def artifact_hashes(artifacts: dict[str, str]) -> dict[str, str]:
    return {
        name: hashlib.sha256(text.encode("utf-8")).hexdigest()
        for name, text in sorted(artifacts.items())
    }
