# Evidence — statblock provider-default temperature

**Status:** Cycle 2 evidence submitted for PRIME review; draft PR #34 remains unmerged; no live DEMO acceptance claimed

**Base:** Server main `eb3125455454716d32c6daf53ad005cdc1ec968c`

**Branch:** `codex/statblock-provider-default-temperature`

**Implementation code commit:** `ca3ffa5794fea3ff5ad0a83ace999d2e54899f67`

**Cycle 2 test/evidence commit:** `7d0f21462fec76360515391b313d6bddca2c6dd8`

**PR:** https://github.com/Drakosfire/DungeonMindServer/pull/34 (draft; PRIME review authority)

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
- The local red-team invocation stalled and was stopped. Hosted exact-head
  run `36376677914` on `0828fbbecfacd5cd1ed594f2bea17bf29946a25d`
  completed **SUCCESS**, independently verified by PRIME and refreshed by SERVER.
  The new test-only head has its own hosted gate; its status is reported with the
  handback. No lint/type-check command is configured in the repository workflow.

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
- No live DEMO acceptance is claimed. After this fix is accepted and deployed,
  DEMO may use its standing authorization for a genuinely new explicit
  generation intent. The original failed operation remains terminal and
  replay-only.

## Cycle 1 review and authorized rework

PRIME review `5333928957` on `0828fbbecfacd5cd1ed594f2bea17bf29946a25d`
confirmed the implementation, exact dependency and hosted CI, and retained HOLD
solely for handoff §6.3 shared-consumer behavioral evidence. PRIME independently
ran the 290 v1 cases with the two unchanged nested-install checks deselected,
the five focused tests and the 19 existing shared/map-image tests successfully.

PRIME extended the lease to one test file,
`tests/test_ge_shared_consumer_compatibility.py`, and factual handoff/report/PR
updates. This rework changes no runtime, prompt, model, schema or dependency.
SERVER implemented the following actual consumer witnesses:

- Card item: real service prompt manager, `STRUCTURED_LOW_COST` / explicit
  `gpt-4o`, item schema/required fields, omitted request temperature retaining
  default numeric `0.7`, and keyed frontend item response.
- PCG: actual `generate_preferences`, real prompt manager and validated
  preference parsing; `TEXT_FAST` / no explicit model resolves `gpt-5.1`,
  numeric `0.7`, unchanged token/product response mapping.
- MapSpec: actual compiler and Pydantic model/schema, input/style/default prompt,
  `STRUCTURED_LOW_COST` resolving `gpt-5.1`, numeric `0.7`, source-prompt and hard
  constraint interpretation.
- SVG: actual generation/extraction/validation; `TEXT_FAST` resolving
  `gpt-5.1`, unchanged prompts/numeric `0.7`, fenced SVG interpreted normally.
- Card core/template image methods: actual service calls through real GE,
  explicit `nano-banana-pro` / `flux-lora-i2i`, original prompts, dimensions,
  image counts and template/strength policy; actual GE image bytes reach the
  publication seam and return the product URL list.
- Map inpainting: actual bounded PNG decoding and `edit_image` through real GE,
  `IMAGE_EDIT_HIGH_QUALITY` / `gpt-image-1.5`, mask/base/negative prompt
  preserved; real GE image result is published and returned as a URL.
- Map generation route: actual MapSpec → compiled prompt → real GE image
  pipeline, `IMAGE_HIGH_QUALITY` / `gpt-image-1.5`, requested dimensions,
  negative constraints, and normal response/asset/owner mapping.
- Image-library route: actual handler for each of `flux-2-pro`,
  `nano-banana-pro`, and `gpt-image-1.5`; selected model/count/dimensions,
  publication bytes, asset ownership and generation-info response preserved.

A recording subclass captures requests then delegates to the real installed
`GenerationClient`. Text/structured calls use its real OpenAI adapter with a
fake SDK; image calls use its injected provider interface returning generated
PNG bytes. Only external IO seams are faked: image publication, asset storage,
quota persistence and Firestore bootstrap. Unexpected Firestore access raises;
actual consumer bodies, schemas, prompt managers and result interpretation run.
Dummy R2 credentials suppress metadata discovery and dotenv loading is disabled.
These route witnesses call handlers directly with a validated user; they prove
consumer compatibility, not HTTP authentication or deployed composition.

Verification on the same exact installed GE #7:

- New shared-consumer file: **11 passed, zero skips**, 12.40 seconds.
- New file plus existing statblock adapter/omission witnesses in one process:
  **16 passed, zero skips**, 12.13 seconds; this verifies test isolation against
  the changed statblock seam. Existing Pydantic deprecation warnings remain.
- One targeted map-route diagnostic: **1 passed**, 12.37 seconds. An earlier
  first invocation was interrupted after seven progress passes before a summary;
  it is not counted as completed evidence.
- Installed `direct_url.json` reconfirmed #7 SHA. The base remains
  `eb3125455454716d32c6daf53ad005cdc1ec968c`; no other open work was inherited.

This is the second substantive implementation/evidence cycle following PRIME's
Cycle 1 review. Broad unchanged cohorts were not repeated. Measured test times
above are test wall time only; total task cost/token usage is unavailable and
account-wide usage must not be represented as task cost. PRIME owns Cycle 2
acceptance, token issuance and merge. SERVER has not updated runtime 7861 or
mutated/retried the original terminal failed operation.

Cumulative committed diff against the exact base contains only the nine
leased files. `git diff --check`, `uv lock --check` and compilation of the new
test passed. Hydrated LFS assets in this temporary worktree were not staged or
committed; saved checkout and running DEMO runtime were not changed.
