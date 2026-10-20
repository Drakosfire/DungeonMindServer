# HANDOFF: DMS CI lock enforcement v1

Status: ACTIVE implementation slice, based on `origin/main` at `65b20dca712a050171bed2d496ddc5c06363ad6c`.

## Invariant

The DMS red-team hardening workflow installs dependencies from the committed `uv.lock` and fails if `pyproject.toml` and the lock disagree. CI must not retry with an unlocked resolution.

## Lease

- `.github/workflows/redteam-hardening.yml`: replace the frozen-sync fallback with `uv sync --locked`.
- `Docs/Plans/HANDOFF-dms-ci-lock-enforcement-v1.md`: record this bounded implementation contract and evidence.

## Acceptance

- The workflow's dependency step runs only `uv sync --locked`.
- Static diff checks pass; the existing workflow then proves the locked install and runs its current offline suites in PR CI.
- Do not run provider or networked tests locally.

## Exclusions

Do not change `Dockerfile`, `uv.lock`, dependencies, GitHub Action pins, production configuration, or application code. Do not treat local lock validation as complete: `uv lock --check --offline` could not start because the default `/home/drakosfire/.cache/uv` is read-only. Cache relocation is outside this slice.
