import hashlib
import json
from pathlib import Path

import pytest

from fde_deploy.preflight import PreflightError
from fde_deploy.release import (
    DeployError,
    current_release_id,
    deploy,
    history,
    read_manifest,
    rollback,
    status,
)
from fde_deploy.spec import spec_hash, validate_spec
from helpers import TickingClock, make_spec


def deploy_v(root, version, **kwargs):
    kwargs.setdefault("clock", TickingClock())
    return deploy(root, make_spec(version=version), **kwargs)


def test_deploy_v1_then_v2_status_shows_v2_then_rollback_to_v1(tmp_path):
    clock = TickingClock()
    m1 = deploy(tmp_path, make_spec(version="1.0.0"), clock=clock)
    assert current_release_id(tmp_path) == m1["release_id"]
    assert (tmp_path / "current" / "docker-compose.yml").exists()

    m2 = deploy(tmp_path, make_spec(version="2.0.0"), clock=clock)
    assert m2["release_id"] != m1["release_id"]
    st = status(tmp_path)
    assert st["current"] == m2["release_id"]
    assert st["version"] == "2.0.0"

    rolled = rollback(tmp_path, clock=clock)
    assert rolled["release_id"] == m1["release_id"]
    st = status(tmp_path)
    assert st["current"] == m1["release_id"]
    assert st["version"] == "1.0.0"


def test_rollback_with_no_previous_release_fails(tmp_path):
    deploy_v(tmp_path, "1.0.0")
    with pytest.raises(DeployError, match="no previous release"):
        rollback(tmp_path, clock=TickingClock())


def test_rollback_with_nothing_deployed_fails(tmp_path):
    with pytest.raises(DeployError, match="nothing deployed"):
        rollback(tmp_path, clock=TickingClock())


def test_failed_preflight_port_conflict_leaves_current_untouched(tmp_path):
    clock = TickingClock()
    m1 = deploy(tmp_path, make_spec(version="1.0.0"), clock=clock)
    with pytest.raises(PreflightError, match="port 8080"):
        deploy(tmp_path, make_spec(version="2.0.0"), clock=clock,
               occupied_ports={8080})
    assert current_release_id(tmp_path) == m1["release_id"]
    assert status(tmp_path)["version"] == "1.0.0"
    rows = history(tmp_path)
    assert rows[-1]["status"] == "preflight_failed"


def test_failed_preflight_low_disk_leaves_current_untouched(tmp_path):
    clock = TickingClock()
    m1 = deploy(tmp_path, make_spec(version="1.0.0"), clock=clock)
    with pytest.raises(PreflightError, match="disk"):
        deploy(tmp_path, make_spec(version="2.0.0"), clock=clock,
               disk_free=lambda p: 0)
    assert current_release_id(tmp_path) == m1["release_id"]


def test_failed_preflight_on_first_deploy_creates_no_current(tmp_path):
    with pytest.raises(PreflightError):
        deploy(tmp_path, make_spec(), clock=TickingClock(), occupied_ports={8080})
    assert current_release_id(tmp_path) is None


def _failing_health(spec):
    return [("app", False, "connection refused"), ("proxy", True, "ok")]


def test_health_failure_auto_rolls_back_to_previous(tmp_path):
    clock = TickingClock()
    m1 = deploy(tmp_path, make_spec(version="1.0.0"), clock=clock)
    with pytest.raises(DeployError, match="health checks failed"):
        deploy(tmp_path, make_spec(version="2.0.0"), clock=clock,
               health_checker=_failing_health)
    # Previous release is live again.
    assert current_release_id(tmp_path) == m1["release_id"]
    assert status(tmp_path)["version"] == "1.0.0"
    rows = history(tmp_path)
    assert rows[-1]["status"] == "health_failed"
    assert rows[-1]["version"] == "2.0.0"


def test_health_failure_on_first_deploy_leaves_no_current(tmp_path):
    with pytest.raises(DeployError, match="health checks failed"):
        deploy(tmp_path, make_spec(), clock=TickingClock(),
               health_checker=_failing_health)
    assert current_release_id(tmp_path) is None


def test_history_is_recorded(tmp_path):
    clock = TickingClock()
    deploy(tmp_path, make_spec(version="1.0.0"), clock=clock)
    deploy(tmp_path, make_spec(version="2.0.0"), clock=clock)
    rollback(tmp_path, clock=clock)
    rows = history(tmp_path)
    assert [r["action"] for r in rows] == ["deploy", "deploy", "rollback"]
    assert [r["status"] for r in rows] == ["ok", "ok", "ok"]
    assert rows[0]["version"] == "1.0.0"
    assert rows[1]["version"] == "2.0.0"
    assert rows[2]["version"] == "1.0.0"


def test_manifest_is_deterministic_for_same_spec_and_clock(tmp_path):
    from datetime import datetime, timezone
    fixed = datetime(2026, 2, 2, 9, 30, 0, tzinfo=timezone.utc)
    spec = make_spec()
    m1 = deploy(tmp_path / "a", spec, clock=lambda: fixed)
    m2 = deploy(tmp_path / "b", spec, clock=lambda: fixed)
    assert m1["spec_hash"] == m2["spec_hash"] == spec_hash(validate_spec(spec))
    assert m1["timestamp"] == m2["timestamp"]
    assert m1["artifacts"] == m2["artifacts"]
    # The whole manifest hashes identically across independent roots.
    h1 = hashlib.sha256(json.dumps(m1, sort_keys=True).encode()).hexdigest()
    h2 = hashlib.sha256(json.dumps(m2, sort_keys=True).encode()).hexdigest()
    assert h1 == h2


def test_deploy_writes_all_artifacts_and_manifest(tmp_path):
    m = deploy_v(tmp_path, "1.0.0")
    release_dir = tmp_path / "releases" / m["release_id"]
    for name in ("docker-compose.yml", ".env", "nginx.conf", "app.service",
                 "manifest.json", "spec.json"):
        assert (release_dir / name).exists(), name
    on_disk = read_manifest(tmp_path, m["release_id"])
    assert on_disk == m


def test_release_ids_unique_for_same_second_deploys(tmp_path):
    from datetime import datetime, timezone
    fixed = datetime(2026, 3, 3, 0, 0, 0, tzinfo=timezone.utc)
    m1 = deploy(tmp_path, make_spec(version="1.0.0"), clock=lambda: fixed)
    m2 = deploy(tmp_path, make_spec(version="1.0.0"), clock=lambda: fixed)
    assert m1["release_id"] != m2["release_id"]
    assert Path(tmp_path, "releases", m1["release_id"]).is_dir()
    assert Path(tmp_path, "releases", m2["release_id"]).is_dir()
