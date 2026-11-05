"""Release management: deploy, rollback, status, history.

Layout under the sandbox root (the simulated target host filesystem)::

    <root>/releases/<release_id>/   rendered artifacts + manifest.json
    <root>/current                  symlink -> releases/<release_id>
    <root>/state.sqlite3            deploy history

The ``current`` symlink is flipped atomically (temp symlink + os.replace),
so readers never see a half-switched state.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .health import run_health_checks
from .preflight import PreflightError, run_preflight
from .render import artifact_hashes, render_artifacts
from .spec import spec_hash, validate_spec


class DeployError(RuntimeError):
    pass


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


def _db(root: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(root / "state.sqlite3"))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            action TEXT NOT NULL,
            release_id TEXT,
            version TEXT,
            spec_hash TEXT,
            status TEXT NOT NULL,
            detail TEXT
        )
        """
    )
    return conn


def _record(root: Path, ts: str, action: str, release_id, version, shash, status, detail=""):
    conn = _db(root)
    try:
        conn.execute(
            "INSERT INTO history (ts, action, release_id, version, spec_hash, status, detail)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ts, action, release_id, version, shash, status, detail),
        )
        conn.commit()
    finally:
        conn.close()


def history(root: Path) -> list[dict]:
    root = Path(root)
    if not (root / "state.sqlite3").exists():
        return []
    conn = _db(root)
    try:
        rows = conn.execute(
            "SELECT ts, action, release_id, version, spec_hash, status, detail"
            " FROM history ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    keys = ("ts", "action", "release_id", "version", "spec_hash", "status", "detail")
    return [dict(zip(keys, row)) for row in rows]


def _flip_current(root: Path, release_id: str) -> None:
    """Atomically point ``current`` at releases/<release_id>."""
    tmp_link = root / ".current.tmp"
    if tmp_link.exists() or tmp_link.is_symlink():
        tmp_link.unlink()
    tmp_link.symlink_to(Path("releases") / release_id)
    os.replace(tmp_link, root / "current")


def current_release_id(root: Path) -> str | None:
    link = Path(root) / "current"
    if not link.is_symlink():
        return None
    return Path(os.readlink(link)).name


def read_manifest(root: Path, release_id: str) -> dict:
    path = Path(root) / "releases" / release_id / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def status(root: Path) -> dict:
    root = Path(root)
    release_id = current_release_id(root)
    if release_id is None:
        return {"current": None}
    manifest = read_manifest(root, release_id)
    releases = sorted(p.name for p in (root / "releases").iterdir() if p.is_dir())
    return {
        "current": release_id,
        "version": manifest["version"],
        "customer": manifest["customer"],
        "spec_hash": manifest["spec_hash"],
        "deployed_at": manifest["timestamp"],
        "releases": releases,
    }


def _successful_deploys(root: Path) -> list[str]:
    """Release ids of successful deploys, in deploy order (duplicates kept)."""
    return [
        row["release_id"]
        for row in history(root)
        if row["action"] == "deploy" and row["status"] == "ok" and row["release_id"]
    ]


def previous_release_id(root: Path, before: str | None = None) -> str | None:
    """The successful release deployed immediately before ``before``."""
    deploys = _successful_deploys(root)
    target = before if before is not None else current_release_id(root)
    if target is None:
        return None
    # Walk newest-first; find the first deploy of `target`, then the one before it.
    idx = None
    for i in range(len(deploys) - 1, -1, -1):
        if deploys[i] == target:
            idx = i
            break
    if idx is None or idx == 0:
        return None
    return deploys[idx - 1]


def deploy(
    root: Path,
    raw_spec: dict,
    *,
    clock=None,
    disk_free=None,
    occupied_ports=None,
    health_checker=None,
) -> dict:
    """Validate -> preflight -> render -> release -> flip -> health gate.

    On health failure the previous release is restored automatically and a
    DeployError is raised. Returns the manifest of the live release.
    """
    root = Path(root)
    clock = clock or _default_clock
    spec = validate_spec(raw_spec)

    # Preflight happens before anything touches `current`.
    try:
        run_preflight(root, spec, disk_free=disk_free, occupied_ports=occupied_ports)
    except PreflightError:
        _record(root, clock().isoformat(), "deploy", None, spec["version"],
                spec_hash(spec), "preflight_failed")
        raise

    root.mkdir(parents=True, exist_ok=True)
    (root / "releases").mkdir(exist_ok=True)

    now = clock()
    shash = spec_hash(spec)
    release_id = f"{spec['version']}-{now.strftime('%Y%m%d%H%M%S')}"
    # Keep release ids unique if two deploys land in the same second.
    base_id, n = release_id, 2
    while (root / "releases" / release_id).exists():
        release_id = f"{base_id}-{n}"
        n += 1

    artifacts = render_artifacts(spec)
    manifest = {
        "release_id": release_id,
        "customer": spec["customer"],
        "environment": spec["environment"],
        "region": spec["region"],
        "tier": spec["tier"],
        "version": spec["version"],
        "spec_hash": shash,
        "timestamp": now.isoformat(),
        "artifacts": artifact_hashes(artifacts),
    }

    release_dir = root / "releases" / release_id
    release_dir.mkdir(parents=True)
    for name, text in artifacts.items():
        (release_dir / name).write_text(text, encoding="utf-8")
    (release_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    # Keep a copy of the normalized spec that produced this release.
    (release_dir / "spec.json").write_text(
        json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    previous = current_release_id(root)
    _flip_current(root, release_id)

    # Health gate: a failed check rolls the deploy back automatically.
    results = run_health_checks(spec, checker=health_checker)
    failed = [name for name, ok, _ in results if not ok]
    if failed:
        if previous is not None:
            _flip_current(root, previous)
        else:
            (root / "current").unlink()
        _record(root, clock().isoformat(), "deploy", release_id, spec["version"],
                shash, "health_failed", f"failed checks: {', '.join(failed)}")
        raise DeployError(
            f"health checks failed for release {release_id} "
            f"({', '.join(failed)}); rolled back to "
            f"{previous if previous else 'no release'}"
        )

    _record(root, clock().isoformat(), "deploy", release_id, spec["version"],
            shash, "ok")
    return manifest


def rollback(root: Path, *, clock=None) -> dict:
    """Flip ``current`` back to the previous successful release and verify it."""
    root = Path(root)
    clock = clock or _default_clock
    current = current_release_id(root)
    if current is None:
        raise DeployError("nothing deployed: there is no current release to roll back from")
    previous = previous_release_id(root, before=current)
    if previous is None:
        raise DeployError(f"no previous release available to roll back to (current: {current})")
    manifest_path = root / "releases" / previous / "manifest.json"
    if not manifest_path.exists():
        raise DeployError(f"previous release {previous} is missing its manifest; refusing to roll back")
    _flip_current(root, previous)
    # Verify: the symlink resolves and the manifest parses.
    if current_release_id(root) != previous:
        raise DeployError("rollback verification failed: current did not move")
    manifest = read_manifest(root, previous)
    _record(root, clock().isoformat(), "rollback", previous, manifest["version"],
            manifest["spec_hash"], "ok", f"rolled back from {current}")
    return manifest
