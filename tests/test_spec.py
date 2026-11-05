import pytest

from fde_deploy.spec import SpecError, spec_hash, validate_spec
from helpers import make_spec


def test_valid_spec_accepted_and_normalized():
    spec = validate_spec(make_spec())
    assert spec["customer"] == "acme-corp"
    assert spec["tier"] == "medium"
    assert spec["port"] == 8080
    # secrets preserved as references
    assert spec["secrets"]["DB_PASSWORD"] == "vault://prod/acme/db-password"


def test_minimal_spec_defaults():
    spec = validate_spec({
        "customer": "globex",
        "environment": "staging",
        "region": "eu-west-2",
        "tier": "small",
        "version": "0.1.0",
    })
    assert spec["port"] == 8080
    assert spec["feature_flags"] == {}
    assert spec["secrets"] == {}


@pytest.mark.parametrize("field", ["customer", "environment", "region", "tier", "version"])
def test_missing_required_field_rejected(field):
    spec = make_spec()
    del spec[field]
    with pytest.raises(SpecError, match=field):
        validate_spec(spec)


@pytest.mark.parametrize("overrides", [
    {"tier": "huge"},
    {"tier": ""},
    {"environment": "prod"},
    {"environment": "qa"},
    {"region": "useast1"},
    {"region": "US-EAST-1"},
    {"region": "us_east_1"},
    {"version": "1.0"},
    {"version": "v1.0.0"},
    {"customer": "Acme Corp"},
    {"customer": "-acme"},
    {"port": 0},
    {"port": 70000},
    {"port": "8080"},
    {"feature_flags": {"unknown_flag": True}},
    {"feature_flags": {"sso": "yes"}},
    {"feature_flags": ["sso"]},
])
def test_invalid_specs_rejected(overrides):
    with pytest.raises(SpecError):
        validate_spec(make_spec(**overrides))


@pytest.mark.parametrize("tier", ["small", "medium", "large"])
def test_all_tiers_accepted(tier):
    assert validate_spec(make_spec(tier=tier))["tier"] == tier


@pytest.mark.parametrize("ref", [
    "vault://prod/acme/db-password",
    "vault://kv/team/token",
    "env://ACME_API_TOKEN",
    "env://HOME",
])
def test_secret_references_accepted(ref):
    spec = validate_spec(make_spec(secrets={"SOME_SECRET": ref}))
    assert spec["secrets"]["SOME_SECRET"] == ref


@pytest.mark.parametrize("value", [
    "hunter2",
    "s3cr3t-literal-value",
    "AKIAIOSFODNN7EXAMPLE",
    "postgres://user:pass@db.internal:5432/app",
    "vault:prod/acme/db",          # wrong scheme form
    "file:///etc/secrets/db",      # not an allowed reference scheme
    "",
])
def test_literal_secret_values_rejected(value):
    with pytest.raises(SpecError, match="literal secret"):
        validate_spec(make_spec(secrets={"DB_PASSWORD": value}))


def test_spec_hash_is_deterministic_and_order_insensitive():
    a = validate_spec(make_spec())
    b = validate_spec(dict(reversed(list(make_spec().items()))))
    assert spec_hash(a) == spec_hash(b)
    assert len(spec_hash(a)) == 64


def test_spec_hash_changes_with_spec():
    a = validate_spec(make_spec())
    b = validate_spec(make_spec(version="1.0.1"))
    assert spec_hash(a) != spec_hash(b)
