# Evidence — statblock provider-default temperature

**Status:** implementation evidence for PRIME review; no merge or live DEMO acceptance claimed

**Base:** Server main `eb3125455454716d32c6daf53ad005cdc1ec968c`

**Branch:** `codex/statblock-provider-default-temperature`

**Implementation code commit:** `ca3ffa5794fea3ff5ad0a83ace999d2e54899f67`

**GE dependency:** accepted #7 merge `80288d7b467ac3c3586f4e3c964385cefe69f931`

## Change

The statblock GenerationEngine request now explicitly passes `temperature=None`.
The profile, resolved default model, explicit model override, prompts, schema,
deadline, provider failure mapping, observations and durable replay behavior are
unchanged. `pyproject.toml` and `uv.lock` pin only the accepted GE #7 merge.

Lock comparison against the base shows exactly two changed existing records
(`dungeonmind-web-api` metadata and `generationengine`) plus four GE structured
conformance dependencies: `jsonschema`, `jsonschema-specifications`, `referencing`
and `rpds-py`. No other package record changed. The installed
`generationengine/direct_url.json` reports commit
`80288d7b467ac3c3586f4e3c964385cefe69f931`.

The new provider-free integration witness invokes SERVER's public
`generate_definition` through the actual pinned `GenerationClient` and OpenAI
adapter. A recording fake SDK returns structurally invalid JSON once and valid
JSON on repair. Both SDK calls resolve to `gpt-5.6-luna` and omit the temperature
key; the initial prompt/schema and corrective request cross the normal GE
conformance path. No provider call or credential is used.

The same witness fails against the base GE pin: its `TextRequest` rejects
`temperature=None` during validation. This demonstrates why the dependency
update and call-site change must land together.

## Verification

- Focused SERVER adapter + integrated fake-SDK tests: **5 passed**.
- Isolated statblocks v1 API/auth/lease/idempotency routes with exact GE source:
  **37 passed**.
- Full statblocks v1 non-integration cohort: **290 passed, 2 failed**. Both
  failures are test-harness compatibility checks in `test_health.py` that spawn
  an older Pydantic 2.7.4 / `pydantic-core` 2.18.4 under Python 3.13; that
  PyO3 release supports only Python through 3.12. The failure occurs in nested
  dependency installation before the check runs. Neither file nor that helper
  dependency is changed here.
- Terminal failed-operation replay regression:
  `test_generate_terminal_failure_replays_without_provider` — **1 passed**.
- Shared profile, GE boundary and package identity tests: **9 passed**.
- Map inpainting and compositing regressions: **10 passed**.
- `uv lock --check`: passed; `git diff --check`: passed on tracked implementation
  paths; `compileall` passed on changed Python files.
- The repository's red-team CI target was started with CI-style dummy
  credentials; it emitted 10 passing tests but stalled before a final summary and
  was stopped. Its overall result remains unverified. No lint/type-check command
  is configured in the repository workflow.

Commands used the isolated Python 3.13.1 environment, accepted GE #7 and fake
SDKs. No live OpenAI/Gateway/Firestore call was made. The existing failed DEMO
request `d41f849e-334d-4248-814d-8e9ccebf9148` was not retried or modified.

## Remaining review evidence / limits

- The current source's `tests/test_map_prompt.py` has five failures in static
  mask-prompt expectations; these tests do not exercise GenerationEngine and
  their files are outside this repair's lease.
- `tests/test_map_router.py` cannot collect in the isolated checkout because it
  imports the full app, whose global Firestore composition requires an unavailable
  service account. Its collection failure is outside the changed paths.
- This repository has no focused unit suites for `CardGenerationService`, player
  character generation, or the GenerationEngine invocations in map prompt/SVG
  mask compilation. The unchanged call sites were identified in the handoff;
  this PR does not claim those behaviors were directly exercised. PRIME should
  treat the missing consumer-specific witnesses as a review gate or explicitly
  accept the bounded evidence limitation.
- No live DEMO acceptance is claimed. After this fix is accepted and deployed,
  DEMO may use its standing authorization for a genuinely new explicit
  generation intent. The original failed operation remains terminal and
  replay-only.
