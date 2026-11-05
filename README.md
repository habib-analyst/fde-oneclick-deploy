# fde-oneclick-deploy

A one-click customer deployment toolkit for a SaaS product. You describe a
customer deployment in one spec file; the tool validates the spec, renders
every deployment artifact, runs preflight checks, installs the release,
health-checks it, and can roll back to the previous release in one command.

## Scope, stated plainly

This is a **local simulation**. The sandbox directory given with `--root`
stands in for the customer host's filesystem. There is no cloud API, no SSH,
and no Docker daemon involved: artifacts are rendered text files, the
"deployed stack" is a release directory plus a `current` symlink, and health
checks are in-process fixture functions that simulate the stack's health
endpoints. The point is the deployment *logic* — validation, deterministic
rendering, preflight gating, atomic release switching, health-gated rollout,
and rollback — exercised end to end and covered by tests.

## The flow

```
spec ──► validate ──► render ──► preflight ──► deploy ──► health gate ──► live
                                      │                        │
                                      └─ fail: abort,          └─ fail: auto-rollback
                                         current untouched        to previous release
```

1. **Validate** — required fields, sizing tier (`small` / `medium` / `large`,
   each with a fixed CPU/memory/replica table), environment, region label
   format (`us-east-1`), semver version, and a feature-flag allowlist
   (`audit_log`, `beta_api`, `metrics`, `new_ui`, `rate_limiting`, `sso`).
2. **Secrets are references only** — every value in the spec's `secrets` map
   must match `vault://...` or `env://...`. A literal secret value in the
   spec is a validation error, by design, and a test pins that behaviour.
3. **Render** — `docker-compose.yml`, `.env` template (placeholder lines that
   name the secret *reference*, never a value), `nginx.conf` reverse-proxy
   config, and a systemd unit, all rendered from templates in `templates/`.
   Rendering is deterministic: the same spec always produces byte-identical
   artifacts, and a golden test pins one full artifact set.
4. **Preflight** — target directory writable, enough free disk, and no port
   conflict for the spec's port. Any failure aborts *before* the live release
   is touched.
5. **Deploy** — artifacts plus a `manifest.json` (spec SHA-256, timestamp,
   per-artifact hashes) are written to `releases/<release_id>/`, then the
   `current` symlink is flipped atomically (temporary symlink + rename).
   History is recorded in a local SQLite database (`state.sqlite3`).
6. **Health gate** — fixture health checks run against the new release. If
   any check fails, the deploy is marked failed in history and `current` is
   flipped back to the previous release automatically.
7. **Rollback** — one command flips `current` back to the previous
   successful release and verifies the switch against its manifest.

## Spec format

YAML or JSON (JSON specs work with or without PyYAML, since JSON is a valid
subset of YAML). See `examples/acme.yaml`:

```yaml
customer: acme-corp
environment: production        # development | staging | production
region: us-east-1
tier: medium                   # small | medium | large
version: 1.0.0
port: 8080
feature_flags:
  audit_log: true
  metrics: true
secrets:
  DB_PASSWORD: vault://prod/acme/db-password
  API_TOKEN: env://ACME_API_TOKEN
```

## CLI demo

```console
$ python3 -m fde_deploy validate --spec examples/acme.yaml
spec OK: acme-corp 1.0.0 (production, us-east-1, tier medium)
spec hash: 52fab4372341b60c6113019321fb0bfcf76ef64d1c38772e17e52e4c4745e20a

$ python3 -m fde_deploy deploy --root ./sandbox --spec examples/acme.yaml
deployed release 1.0.0-20261105144047 (version 1.0.0) to ./sandbox

$ python3 -m fde_deploy deploy --root ./sandbox --spec examples/acme-v2.yaml
deployed release 2.0.0-20261105144047 (version 2.0.0) to ./sandbox

$ python3 -m fde_deploy status --root ./sandbox
{ "current": "2.0.0-...", "version": "2.0.0", "customer": "acme-corp", ... }

$ python3 -m fde_deploy rollback --root ./sandbox
rolled back: current is now release 1.0.0-20261105144047 (version 1.0.0)

$ python3 -m fde_deploy history --root ./sandbox
...  deploy    1.0.0-...   v1.0.0    ok
...  deploy    2.0.0-...   v2.0.0    ok
...  rollback  1.0.0-...   v1.0.0    ok  (rolled back from 2.0.0-...)
```

Exit codes: `0` success, `2` spec or preflight problem, `1` deploy/rollback
failure. Errors print a readable message to stderr.

Sandbox layout after two deploys:

```
sandbox/
├── current -> releases/1.0.0-20261105144047   (after the rollback above)
├── releases/
│   ├── 1.0.0-20261105144047/  {docker-compose.yml, .env, nginx.conf,
│   │                           app.service, manifest.json, spec.json}
│   └── 2.0.0-20261105144047/  {...}
└── state.sqlite3              deploy history
```

## Measured results

- **62 tests, all passing** (`python3 -m pytest tests/ -q`, ~0.2 s, tmp dirs
  only — the suite never touches a real host path).
- Validation: full accept/reject matrix, including 7 literal-secret shapes
  rejected and 4 valid `vault://` / `env://` reference shapes accepted.
- Golden test pins the complete rendered artifact set for the example spec;
  rendering the same spec twice produces identical bytes and identical
  artifact hashes.
- Deploy scenario verified end to end: deploy v1 → deploy v2 → `status`
  reports v2 → `rollback` → `current` is v1 again.
- Failed preflight (occupied port, or zero free disk) leaves the previously
  live release untouched and records `preflight_failed` in history.
- Health-check failure on v2 automatically rolls back to v1 and records
  `health_failed`; a health failure on a first deploy leaves no live release.
- Manifest determinism: the same spec deployed under the same injected clock
  into two independent sandboxes produces identical manifests (same spec
  hash, timestamp, and artifact hashes).

## Layout

```
fde_deploy/
├── spec.py      spec loading, validation, spec hash
├── render.py    deterministic template rendering
├── preflight.py writable-dir / disk / port checks (injectable)
├── health.py    fixture health checks (injectable)
├── release.py   deploy, rollback, status, history (SQLite)
└── cli.py       validate / deploy / rollback / status / history
templates/       docker-compose, .env, nginx, systemd templates
examples/        acme.yaml example spec
tests/           pytest suite (62 tests)
```

## Requirements

Python 3.10+. PyYAML is used when installed; without it, specs must be JSON.
No other dependencies. Nothing here needs a network connection, a cloud
account, or a Docker daemon.
