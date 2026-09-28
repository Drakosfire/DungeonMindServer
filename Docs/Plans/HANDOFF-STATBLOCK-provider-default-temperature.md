# HANDOFF — STATBLOCK: request provider-default temperature through accepted GE

**Created:** 2026-09-27
**Status:** IMPLEMENTED / CYCLE 2 PENDING — PRIME owns acceptance and merge
**Owner/repository:** DungeonMindServer; SERVER activates, PRIME reviews/controls merge
**Activated implementation base:** Server `eb3125455454716d32c6daf53ad005cdc1ec968c`
**Implementation code commit:** `ca3ffa5794fea3ff5ad0a83ace999d2e54899f67`

**Cycle 2 test/evidence commit:** `7d0f21462fec76360515391b313d6bddca2c6dd8`

**PR:** https://github.com/Drakosfire/DungeonMindServer/pull/34 (draft; PRIME review authority)
**Activation GE pin:** `0d01547e2d9afec68e87b4c8f7e6aaa047e8c42a` (accepted #3)
**Target GE pin:** `80288d7b467ac3c3586f4e3c964385cefe69f931` (accepted #7 / E5B.2)
**PR topology:** serial — one bounded Server repair
**Suggested branch/title:** `codex/statblock-provider-default-temperature` / `STATBLOCK: omit provider temperature through GenerationEngine`

This is the SERVER implementation lease activated by the operator request and PRIME direction. It does not activate platform refresh, dispatch GE work, or grant merge authority.

## 1. Evidence and execution contract

SERVER reported one authorized minimal SDK diagnostic, with no World prompt and
SDK retries disabled: the selected OpenAI `gpt-5.6-luna` rejected a numeric
temperature with HTTP 400 `invalid_request_error`, unsupported parameter
`temperature`, provider request `req_fad6d94dd9c14cdf8a3b21e715548a99`.
Usage and response model are unknown. This is **separate diagnostic evidence**;
the original production provider body was discarded and is not reconstructed.

The original DEMO request `d41f849e-334d-4248-814d-8e9ccebf9148` is terminal
failed. Same key/body must continue replaying that failure without inference.
Do not clear, mutate, replace or relabel that operation to test the fix.

At Server's exact current pin, `TextRequest` defaults to numeric `0.7` and the
OpenAI adapter emits it. `GenerationEngineDefinitionProvider.generate_definition`
does not set temperature. A repin by itself is insufficient.

Accepted GE #7 reviewed head `f7c0a9ceaabc2a13abbd7ce834c4ce528dce1a22`,
Cycle 1 MERGE-READY review `5249531979`, merge
`80288d7b467ac3c3586f4e3c964385cefe69f931`, supplies the exact contract:

- omitted field retains compatibility default `0.7`;
- explicit numeric value forwards exactly, including `0.0`;
- explicit `None` omits the provider temperature key, not JSON null.

None survives ordinary/structured generation, structured corrective attempts,
and streaming through OpenAI/OpenRouter. Relevant accepted witnesses are
`test_openai_generate_omits_temperature_when_none`,
`test_openai_none_temperature_omits_provider_field`, and
`test_repair_preserves_explicit_none_temperature`. GE's core contract §1 records
the three states. The design author independently ran `tests/test_client.py`,
`test_openai_text.py`, `test_openrouter_text.py` and
`test_structured_conformance.py` at the exact #7 merge: **71 passed, zero skips**
(5.51 seconds). This provider-free GE proof does not certify Server consumer
compatibility or live product generation.

GE catalog is unchanged between Server's #3 pin and this #7 merge. Keep
`STRUCTURED_HIGH_RELIABILITY`, its resolved `gpt-5.6-luna`, and existing explicit
model overrides. Choose the smallest accepted omission-capable merge, not moving
GE main (`128710668369b73beff78ea0e4377ec252cd04e4` at design). No model
substitution, new model policy, provider bypass or catalog modification.

The dependency move also inherits E5B explicit-target/OpenRouter and E5B.1
generic structured-conformance capabilities. Those are already accepted GE
contracts, but Server consumer compatibility must be proved—not assumed from
the narrow final #7 diff. No E5H–E5P/Jev/lifecycle capability is selected here.

## 2. One merge-ready invariant

Server statblock generation and revision use the existing product request,
profile/model, prompts, strict schema and deadline, but explicitly choose
provider-default sampling with `TextRequest(temperature=None)`. At the accepted
pin the real GE request path emits **no temperature key** on initial or
structural-repair provider calls. Other migrated Server inference consumers
retain their existing request policy and pass the dependency regression union.
Durable idempotency/failure replay and observation truth remain unchanged.

## 3. Implementation scope

1. Change only the GE source revision/comment in `pyproject.toml` to the exact
   target above and regenerate `uv.lock` normally. Review lock changes; preserve
   unrelated accepted dependency state. No handcrafted lockfile or broad update.
2. Add explicit `temperature=None` to the existing statblock `TextRequest`.
   Do not rely on omission/default, pass `0`, alter prompts/schema/profile/model,
   reset request identity, add retries or move provider execution into Server.
3. Extend request-parity tests for profile resolution and explicit override.
   Add a provider-free integrated Server → real pinned GenerationClient → real
   OpenAI adapter → recording fake SDK witness. Exercise public
   `generate_definition`, not just an adapter kwargs helper. Test-only adapter
   construction/injection is allowed; production remains public GE consumption.
4. Record exact installed dependency identity and compatibility results, including
   original failed-operation replay. A live DEMO witness is separately scheduled
   by SERVER/DEMO after accepted deployment, with genuinely new explicit intent.

## 4. Write lease after activation

```text
statblocks_v1/infrastructure/ge_provider.py
tests/statblocks_v1/test_ge_provider.py
tests/statblocks_v1/test_ge_temperature_omission.py                 # new integrated fake-SDK proof
tests/test_ge_shared_consumer_compatibility.py                      # PRIME Cycle 1 test-only extension
pyproject.toml
uv.lock
Docs/Design/GENERATION-STRUCTURED-CONFORMANCE.md                    # bounded current sampling guidance
Docs/Plans/HANDOFF-STATBLOCK-provider-default-temperature.md        # activation/factual handback
Docs/Reports/REPORT-STATBLOCK-provider-default-temperature.md       # new evidence receipt
```

No other runtime edit is expected. A needed change to another consumer, model
catalog, provider mechanics, failure taxonomy, production client lifecycle,
product schema/prompt, retry policy, auth, persistence or deployment is a stop
and owner rebrief. Discovery is not permission to bundle cleanup.

## 5. Activation and authority sync

Activation facts (2026-09-27): Server main was fetched at exact base `eb3125455454716d32c6daf53ad005cdc1ec968c`. Current open PRs are #28 (`7273be812c0158b8e4aa645d0ff19acc0e1639b1`) and #29 (`83e242f8c2ba791bd30c70c9409f99f3cc46f9db`). File lists confirm neither touches this lease; #28 changes prompts/domain/schema/openapi/fixtures, #29 changes rule_elements and legacy revision tests. They remain proposed behavior. The implementation branch is `codex/statblock-provider-default-temperature`, code commit `ca3ffa5794fea3ff5ad0a83ace999d2e54899f67`. GE #7 is already merged; this lease changes only the consumer and pin, not GE.

The shared GenerationEngine consumer cohort was identified before editing:

- structured text: statblocks v1, card item generation, map prompt compiler;
- text: map SVG mask generation and player-character generation;
- image: card generation, map inpainting, map generation and image-management routes.

Available owning-boundary regressions are `tests/statblocks_v1/**` (non-integration), `tests/test_map_inpainting.py`, `tests/test_map_router.py`, `tests/test_map_prompt.py`, `tests/test_inference_policy.py`, `tests/test_generationengine_cutover_fitness.py`, and `tests/test_packaging_identity.py`. At activation the repository had no focused behavioral tests for card-generation service, player-character generation, or map prompt/SVG-mask GenerationEngine invocation. PRIME Cycle 1 authorized adding these witnesses in `tests/test_ge_shared_consumer_compatibility.py` on this same PR. This test-only extension captures actual consumer requests and normal results through real pinned GE with external IO fakes; runtime/model/prompt/dependency edits remain excluded. The installed environment uses fake SDK clients only, dummy test credentials from the test conftest where required, and no provider/network call.

This repair is independent of broad platform modernization. Keep
`ANCHOR-dungeonmind-net-platform-refresh.md` at no-implementation-dispatch; do
not activate its roadmap or mutate OverMind for a sampling call-site repair.
Current archived statblock handoffs stay historical. Only mutable documents
that actually claim this repair's pin/active state need settlement. The new
report/handoff and the bounded consumer guidance comprise this local state set;
SERVER records accepted merge/review after merge and then releases the lease.
The target GE prerequisite is already merged; never invent this repair's future
merge SHA or mark it complete inside its implementation PR.

Runtime ownership: fake SDKs, test-only credentials, in-memory operation stores;
no live Firestore, assets, provider calls, model prompt, Buddy World/campaign,
DEMO request record or deployed service changes are authorized in this lane.
Any live test is a separate explicit operator decision, not permission inherited
from SERVER's earlier minimal diagnostic.

## 6. Merge-blocking evidence

1. New omission regression fails on the old exact dependency/request combination.
   Against target pin, default-profile and explicit-model statblock requests
   have `temperature is None`, exact prompts/schema/name/deadline and unchanged
   profile/model policy.
2. Integrated real GE + OpenAI adapter witness records SDK kwargs with the exact
   resolved model and no temperature key; successful structured payload crosses
   the existing Server interpretation boundary. Force structural invalid output
   then repair: both real provider invocations omit temperature. No Server repair
   loop, fabricated production usage or provider bypass is added.
3. Numeric GE callers still forward numeric values. Existing non-statblock Server
   migrated consumers retain their current policies; compare captured request
   shapes/defaults and run their focused map/card/PCG/image regression cohorts.
   Since the dependency is shared, this is merge-blocking even with one call-site
   edit. Record actual available tests and inherited base failures separately.
4. Statblock generation/revision service and API/auth/lease/idempotency regressions
   pass. `test_generate_terminal_failure_replays_without_provider` continues
   proving that a terminal failure is not retried by replay. Existing operation
   identities/records and failure observations are not rewritten by a dependency
   upgrade. Success does not prove a live model response.
5. Unknown usage/model/response IDs remain unknown; pass-through observed fields
   retain their values. Existing typed failure mappings remain unchanged.
6. Exact installed `direct_url.json` SHA and lockfile agree with #7 merge;
   package/import/factory and GenerationEngine boundary-fitness tests pass.
   New mandatory fake-SDK witnesses run, zero skips. Optional live/cloud tests
   may remain unrun/skipped but must be identified—not called end-to-end PASS.

Use an environment containing the exact GE dependency; the project-independent
statblock script alone does not install it and cannot prove this seam. Suggested
owning cohort:

```bash
uv lock
uv sync --locked
uv run pytest --confcutdir=tests/statblocks_v1 tests/statblocks_v1 --ignore=tests/statblocks_v1/integration
uv run pytest --noconftest tests/test_inference_policy.py tests/test_generationengine_cutover_fitness.py tests/test_packaging_identity.py
uv lock --check
git diff --check
```

Root `tests/conftest.py` imports the full production app: if it contacts services
or fails collection, use an explicitly isolated equivalent lane or documented
base/head classification; never enable live credentials just to collect tests.
Name the additional migrated-consumer cohort/environment at activation. Do not
silently weaken it to four fake-client statblock tests.

Implementation evidence (2026-09-27) is in
`Docs/Reports/REPORT-STATBLOCK-provider-default-temperature.md`. The exact #7
pin is installed and lock-checked; the public Server → real GE → OpenAI adapter
fake-SDK witness passes initial and structural-repair calls, and fails against
the old pin as required. The isolated v1 API/auth/lease/idempotency cohort passed
37 tests; the focused adapter/integration pair passed 5; terminal failure replay
passed; inference-policy/boundary/packaging passed 9; map inpainting/compositing
passed 10. The larger non-integration v1 cohort passed 290 tests, with two
`test_health.py` nested-install checks failing before execution because their
Pydantic 2.7.4 / `pydantic-core` 2.18.4 lane cannot build on Python 3.13. The
static mask-prompt suite has five failures outside this repair's lease; the
map-router suite cannot collect without production Firestore composition.
The local red-team invocation did not finish; hosted exact-head red-team run
`36376677914` succeeded, independently verified by PRIME.

PRIME Cycle 1 review `5333928957` confirmed the implementation and retained
HOLD solely for §6.3 behavioral shared-consumer evidence. PRIME authorized the
test-only lease extension above, including card item/core/template images, PCG,
MapSpec/SVG, and remaining image consumers. The new actual-consumer cohort passed 11 tests (zero skips); the combined
shared-consumer/statblock seam cohort passed 16 (zero skips). Evidence and
remaining limits are recorded in the report. No acceptance token is claimed before PRIME's
Cycle 2 review; the draft PR and original failed DEMO operation remain intact.

Handback includes exact base/head/PR, lease diff, installed GE pin, request parity,
SDK omission/repair proof, regression union, lock changes, inherited failures,
tests not run and remaining live-witness status. PRIME reviews the frozen head;
worker opens only the assigned PR after activation and never merges autonomously.

After accepted merge/deployment, DEMO may request a genuinely new explicit
generation intent. Preserve `d41f849e-334d-4248-814d-8e9ccebf9148` as the
original failed witness. Do not reuse its same key/body expecting new inference.
