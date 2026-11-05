import json

from fde_deploy.cli import main
from helpers import make_spec


def write_spec(tmp_path, spec, name="spec.json"):
    path = tmp_path / name
    path.write_text(json.dumps(spec), encoding="utf-8")
    return str(path)


def test_cli_validate_ok(tmp_path, capsys):
    spec_path = write_spec(tmp_path, make_spec())
    assert main(["validate", "--spec", spec_path]) == 0
    out = capsys.readouterr().out
    assert "spec OK" in out
    assert "spec hash:" in out


def test_cli_validate_literal_secret_exits_2(tmp_path, capsys):
    spec_path = write_spec(tmp_path, make_spec(secrets={"DB_PASSWORD": "hunter2"}))
    assert main(["validate", "--spec", spec_path]) == 2
    assert "literal secret" in capsys.readouterr().err


def test_cli_full_flow(tmp_path, capsys):
    root = str(tmp_path / "sandbox")
    s1 = write_spec(tmp_path, make_spec(version="1.0.0"), "v1.json")
    s2 = write_spec(tmp_path, make_spec(version="2.0.0"), "v2.json")

    assert main(["deploy", "--root", root, "--spec", s1]) == 0
    assert "deployed release" in capsys.readouterr().out

    assert main(["deploy", "--root", root, "--spec", s2]) == 0
    capsys.readouterr()

    assert main(["status", "--root", root]) == 0
    out = capsys.readouterr().out
    assert '"version": "2.0.0"' in out

    assert main(["rollback", "--root", root]) == 0
    assert "rolled back" in capsys.readouterr().out

    assert main(["status", "--root", root]) == 0
    out = capsys.readouterr().out
    assert '"version": "1.0.0"' in out

    assert main(["history", "--root", root]) == 0
    out = capsys.readouterr().out
    assert out.count("deploy") >= 2
    assert "rollback" in out


def test_cli_status_with_nothing_deployed(tmp_path, capsys):
    assert main(["status", "--root", str(tmp_path / "empty")]) == 0
    assert "no release deployed" in capsys.readouterr().out


def test_cli_deploy_invalid_spec_exits_2(tmp_path, capsys):
    spec_path = write_spec(tmp_path, make_spec(tier="huge"))
    assert main(["deploy", "--root", str(tmp_path / "sb"), "--spec", spec_path]) == 2
    assert "invalid spec" in capsys.readouterr().err


def test_cli_missing_spec_file_exits_2(tmp_path, capsys):
    assert main(["validate", "--spec", str(tmp_path / "nope.json")]) == 2
    assert "file not found" in capsys.readouterr().err
