"""Preflight checks. Runs before anything touches the live ``current`` link.

Disk space and occupied ports are injected so tests (and real adapters) can
supply their own view of the target host.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

MIN_FREE_BYTES = 50 * 1024 * 1024  # 50 MiB floor for a release directory


class PreflightError(RuntimeError):
    pass


def default_disk_free(path: Path) -> int:
    return shutil.disk_usage(str(path)).free


def run_preflight(
    root: Path,
    spec: dict,
    *,
    disk_free=None,
    occupied_ports=None,
) -> None:
    """Raise PreflightError on the first failed check; return None if clear."""
    root = Path(root)

    # 1. Target directory exists or can be created, and is writable.
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PreflightError(f"target directory cannot be created: {root} ({exc})")
    if not os.access(root, os.W_OK):
        raise PreflightError(f"target directory is not writable: {root}")
    probe = root / ".fde-write-probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise PreflightError(f"target directory is not writable: {root} ({exc})")

    # 2. Disk space (injected stub in tests; real disk_usage by default).
    free_fn = disk_free or default_disk_free
    free = free_fn(root)
    if free < MIN_FREE_BYTES:
        raise PreflightError(
            f"insufficient disk space: {free} bytes free, need at least {MIN_FREE_BYTES}"
        )

    # 3. Port conflict (injected registry in tests).
    occupied = set(occupied_ports or ())
    port = spec["port"]
    if port in occupied:
        raise PreflightError(f"port {port} is already occupied on the target host")
