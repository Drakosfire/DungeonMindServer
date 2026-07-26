# Revise idempotency fixtures (SBW06a)

Illustrative v1 transport evidence for `POST .../statblock-candidates:revise`.
No secrets, no absolute paths, no live corpus.

## Files

- `revise-request.json` — locator-backed revise body (`source_locator` XOR inline `source_definition`).
- `revise-replay-response.json` — 200 replay fields (`candidate_id`, `request_digest`, locator echo).
- `revise-conflict-response.json` — `409` / `idempotency_conflict` envelope.

## Capture procedure

1. Run statblocks_v1 API tests with in-memory persistence  
   (`tests/statblocks_v1/api/test_candidate_routes.py`, locator replay test).
2. Copy response JSON; redact provider tokens and truncate `definition`.
3. Replace identifiers with `fixture-*` placeholders; keep digest prefix shape `sha256:`.
