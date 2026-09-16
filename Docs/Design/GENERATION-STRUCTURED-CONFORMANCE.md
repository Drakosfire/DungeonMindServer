# GenerationEngine structured-conformance consumer boundary

**Status:** ACTIVE CONSUMER GUIDANCE  
**Date:** 2026-09-16  
**Owner of execution contract:** `Drakosfire/GenerationEngine`

## Decision

DungeonMind Web API owns product schemas and the domain meaning of generated data. GenerationEngine owns structural conformance of inference output to the caller-supplied schema.

Target boundary:

```text
DungeonMind Web API
  owns prompt/task meaning
  owns JSON Schema / product model definition
        ↓
GenerationEngine.generate_structured
  owns provider-specific strategy
  owns parsing
  owns local JSON Schema validation
  owns bounded corrective inference retries
        ↓
schema-conforming generic object
        ↓
DungeonMind Web API
  constructs/interprets product type
  performs domain/business/workflow validation
```

The practical rule is:

> **“Did the model produce the requested structure?” belongs to GenerationEngine. “Is that structure correct for this product workflow?” remains in DungeonMind Web API.**

## Migration consequence

As GenerationEngine's provider-independent conformance layer lands, existing product paths should classify their validation/retry code before deleting anything.

Candidates to centralize in GenerationEngine:

```text
JSON parsing/extraction
structural schema validation
schema-validation feedback to the model
bounded repair attempts caused only by structural mismatch
```

Stays product-owned:

```text
MapSpec/statblock/card semantic correctness
product authorization/quota policy
workflow/business invariants
product-specific interpretation and persistence
```

Pydantic usage does not by itself determine ownership. Structural validation against the same schema supplied to GenerationEngine is reusable inference machinery; domain validators remain product behavior.

## Retry distinction

GenerationEngine should distinguish:

```text
transport retry
→ timeout / rate limit / transient provider failure

conformance retry
→ provider returned content, but structural schema validation failed
```

Both consume the same overall inference-operation budget. DungeonMind Web API should not wrap GE in another equivalent structural repair loop once the replacement is proven.

## Provider-native structured output

Provider-native strict JSON Schema is an implementation optimization, not the Generation Contract.

A provider without native strict-schema support may still satisfy `generate_structured()` through JSON-object or text generation followed by local validation and bounded correction inside GenerationEngine.

The final structural conformance check belongs above provider adapters.

## Transition rule

Do not remove existing product-side structural repair logic until the GenerationEngine replacement exists, is pinned to an accepted revision, and is proven on the relevant product path.

Once proven, remove duplicated generic structural repair in the same migration slice while preserving product/domain validation.
