# Launch note — fde-oneclick-deploy

20-point pre-launch checklist, worked item by item on 2026-11-05.
Every item is PASS or N/A with a reason; no FAIL items.

1. **Tests green** — PASS. `python3 -m pytest tests/ -q`: 62 passed in 0.20s.
2. **No real secrets anywhere** — PASS. Specs accept `vault://` / `env://`
   references only; literal secret values are a validation error, pinned by
   tests. Example specs contain references, not values.
3. **No credentials or tokens in code, templates or history** — PASS. Grepped
   the tree; only fixture references (`env://ACME_API_TOKEN` style) exist.
4. **Free of cost** — PASS. Pure Python + PyYAML, local filesystem only; no
   paid service, no account, no card anywhere in the flow.
5. **No network calls** — PASS. The tool performs no HTTP, SSH or cloud API
   calls; grep confirms no socket/urllib/subprocess use.
6. **Scope honesty in README** — PASS. README states plainly that the sandbox
   directory simulates a host: no cloud, no SSH, no Docker daemon.
7. **Measured results only** — PASS. README numbers are the real pytest count
   (62) and scenario outcomes reproduced by the test suite and a live CLI run.
8. **Deterministic output claim verified** — PASS. Golden test pins a full
   artifact set; manifest determinism test compares two independent sandboxes.
9. **Failure paths tested** — PASS. Failed preflight (port, disk),
   health-failure auto-rollback, rollback with no previous release, and
   invalid-spec CLI exits are all covered.
10. **Rollback verified, not just implemented** — PASS. v1 → v2 → rollback →
    v1 scenario is a test and was also run live through the CLI.
11. **Atomic live-switch** — PASS. `current` flips via temporary symlink +
    `os.replace`; no window where `current` is missing during a deploy.
12. **State stays local** — PASS. History lives in `state.sqlite3` inside the
    sandbox root the user chose; nothing is written outside `--root` in
    deploy/rollback/status/history.
13. **Tests use tmp dirs only** — PASS. Every filesystem test runs under
    pytest `tmp_path`; the suite cannot touch a real deployment directory.
14. **Readable errors and meaningful exit codes** — PASS. 0 / 2 / 1 exit code
    contract is implemented in the CLI and covered by tests.
15. **Public identity correct** — PASS. README and package metadata carry no
    personal identifiers beyond the project itself; author is the GitHub
    account that will host the repo.
16. **No third-party private data** — PASS. All customers, regions and values
    in examples and tests are invented fixtures (`acme-corp`, `globex`).
17. **Dependencies minimal and declared** — PASS. `pyproject.toml` declares
    Python ≥3.10 and PyYAML; the code also runs without PyYAML for JSON specs.
18. **Health/preflight seams are injectable** — PASS. Disk, port registry,
    clock and health checker are parameters, so a real host adapter can be
    dropped in without changing deploy logic.
19. **Licence / third-party code** — N/A. No third-party code is vendored;
    templates are original text written for this project.
20. **Demo runnable from the README alone** — PASS. The CLI demo in the
    README was executed verbatim against `examples/acme.yaml` and produced
    the shown output, including the rollback and history lines.
