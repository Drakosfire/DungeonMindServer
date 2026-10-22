# STATBLOCK — current model schema artifacts

ACTIVE. PRIME owns this bounded DMS repair under the operator's preparation/play
goal. Base223cbbe92f64bb14019a1678cac1f4e2336efd40; reuse existing inactive
statblock-explains-contract checkout on codex/statblock-current-schema-artifacts.
Serial one PR. Primary checkout remains the owned running7860 source until merge.
Preserve unrelated dirty AGENTS.md; do not include or discard it.

Real Buddy generation request7eed4919-8c93-470b-965c-14d2707b2aef reached DMS but
failed before provider execution: compile_openai_definition_schema rejects stale
published artifacts. Current model already contains optional RuleElement.explains
and ExplainsEdge; committed canonical/strict artifacts omit them. Existing schema
snapshot/compiler tests reproduce2failures/8passes at current main. Open PR28 is
historical unmerged prompt-v6 proposal, not authority for this model repair.

Regenerate canonical schema from the accepted model. Derive the provider write
schema through an explicit product projection excluding retired RuleElement.explains
and its unreachable ExplainsEdge definition, then use the existing strict compiler.
Do not force retired metadata into every new generated element. Do not adopt PR28, change prompts,
models, accepted revisions/digests, dependencies, Firestore data, generation
retries/claims or provider settings. This repairs DMS's product-schema input to
GenerationEngine and Buddy's existing candidate contract; no new shared contract.
Exclusive writes: domain/schema.py provider projection, canonical/strict
schema_artifacts JSON files, tests/statblocks_v1/test_schema_compiler.py, test_schema_snapshots.py and this
handoff. The initial full-model regeneration was held by Bugbot because it made
retired explains required in new provider output; this amended projection fixes
that owning boundary without changing persisted models.

Verify existing schema/compiler/model/generation/API tests against the cumulative
change, independently Bugbot review, PRIME exact-head merge. Then guarded owned
DMS7860 restart preserving config/persistence, prove actual compiler coherence,
resume only the original saved Buddy generation request ID through normal UI and
inspect the real candidate/receipt. Do not restart or manufacture a second request
because the first response is unknown. Native Combat association remains separate.

Verification boundary: the API revise fixture cohort has four inherited failures
at unchanged223cbbe (strict validation and source-definition digest coherence).
The same four fail after artifact regeneration; no fixture/accepted-revision bytes
are changed here. Do not report that cohort green or use this repair to award
revision/full product acceptance. Existing schema gates go from2failed/8passed
to11passed, with the path-equivalence gate asserting the exact retired-field exclusion. Exact model→artifact coherence owns this repair's invariant.
