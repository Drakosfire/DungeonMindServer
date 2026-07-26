# DungeonBuddy statblock v1 configuration

The route is internal-only. Set `DUNGEONBUDDY_INTERNAL_API_KEY` in the server
secret store and send it only in `X-DungeonBuddy-Internal-Key`. Rotate by
deploying a new key to both services, verifying the smoke, then retiring the
old key; this version accepts one active key at a time.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DUNGEONBUDDY_INTERNAL_API_KEY` | required | Internal service authentication |
| `OPENAI_API_KEY` | required when generation enabled | Provider credential |
| `STATBLOCKS_V1_OPENAI_MODEL` | model policy role | Structured generation model |
| `STATBLOCKS_V1_OPENAI_TIMEOUT_SECONDS` | `45` | Per-attempt provider timeout |
| `STATBLOCKS_V1_OPENAI_MAX_RETRIES` | `1` | SDK retries for transient provider failures |
| `STATBLOCKS_V1_CANDIDATE_TTL_SECONDS` | `86400` | Candidate expiration |
| `STATBLOCKS_V1_FIRESTORE_ENABLED` | `true` | Enables durable v1 persistence |
| `STATBLOCKS_V1_FIRESTORE_NAMESPACE` | `dungeonbuddy_statblocks_v1` | Deployment namespace label |
| `STATBLOCKS_V1_CANDIDATES_COLLECTION` | `dungeonbuddy_statblock_candidates_v1` | Candidate collection |
| `STATBLOCKS_V1_STATBLOCKS_COLLECTION` | `dungeonbuddy_statblocks_v1` | Logical statblocks and revisions |
| `STATBLOCKS_V1_IDEMPOTENCY_COLLECTION` | `dungeonbuddy_statblock_idempotency_v1` | Idempotency records |
| `STATBLOCKS_V1_GENERATE_OPS_COLLECTION` | `dungeonbuddy_statblock_candidate_generate_ops_v1` | Candidate generate-operation leases |
| `STATBLOCKS_V1_GENERATE_LEASE_SECONDS` | `max(120, ceil(timeout×(retries+1)+asset_timeout+30))` | Pending generate lease; must cover provider retries plus asset generation |
| `STATBLOCKS_V1_REVISE_OPS_COLLECTION` | `dungeonbuddy_statblock_candidate_revise_ops_v1` | Candidate revise-operation leases |
| `STATBLOCKS_V1_REVISE_LEASE_SECONDS` | same default as generate lease | Pending revise lease; same provider/asset budget rule as generate |
| `STATBLOCKS_V1_ASSET_GATEWAY_ENABLED` | `false` | Enables optional asset pipeline wiring |
| `STATBLOCKS_V1_ASSET_TIMEOUT_SECONDS` | `20` | Asset pipeline timeout policy |
| `FAL_KEY` | required when assets enabled | fal.ai credential for text-to-image |
| `CLOUDFLARE_ACCOUNT_ID` | required when assets enabled | Cloudflare Images account |
| `CLOUDFLARE_IMAGES_API_TOKEN` | required when assets enabled | Cloudflare Images upload token |
| `STATBLOCKS_V1_FEATURE_ENABLED` | `true` | Enables candidate generation/revision |
| `STATBLOCKS_V1_ALLOW_READS_WHEN_DISABLED` | `true` | Keeps persisted reads available during a generation rollback |
| `STATBLOCKS_V1_STRUCTURED_LOGGING` | `true` | Enables structured v1 telemetry policy |
| `STATBLOCKS_V1_LOG_LEVEL` | `INFO` | v1 logger level |

`/health/live` means the route process can respond. Authenticated
`/health/ready` validates deploy configuration; it is not an OpenAI probe.
Authenticated `/health` publishes the contract and only exposes generation
capabilities when the feature flag is enabled. If generation is disabled,
generation endpoints return `503 generation_disabled`; persisted reads retain
service when Firestore is configured and `ALLOW_READS_WHEN_DISABLED=true`.

Firestore documents use the PR15 layout: candidates, logical statblocks with
`revisions` subcollections, and idempotency records, plus PR23 generate-operation
records in `STATBLOCKS_V1_GENERATE_OPS_COLLECTION`, plus SBW06a revise-operation
records in `STATBLOCKS_V1_REVISE_OPS_COLLECTION`. Configure a Firestore TTL
policy on candidate `expires_at`; never TTL revisions, PR15 idempotency records,
or candidate generate- or revise-operation records.
Provision indexes required by operational list/query workflows, least-privilege
service-account access, and exports/backups for immutable revisions.

Generate-request idempotency keys are body `request_id` values namespaced by
`caller_scope` and operation `generate_candidate`. The pending lease
(`STATBLOCKS_V1_GENERATE_LEASE_SECONDS`) must cover the full provider retry
budget plus asset-generation timeout
(`timeout × (retries+1) + asset_timeout + margin`, ceiling fractional timeouts)
so an in-flight worker holding the lease through provider and asset work is not
spuriously taken over. Completed operations retain `candidate_expires_at` (bound
to the persisted candidate's `expires_at`) so a missing candidate before that
instant is treated as integrity failure rather than normal expiry; a present
candidate whose `expires_at` disagrees with the operation is also integrity
failure. They also retain `outcome_digest` (canonical fingerprint of the full
persisted candidate payload) so completed replay fails closed when a candidate
is recreated under the same ID with any response-significant field changed.
Document identity fields must match the hashed lookup key; completed records
without `candidate_expires_at` or `outcome_digest` are integrity failures.
Completed replay also requires the candidate generation receipt to bind the
same `request_digest`.

The provider uses one retry only for transient SDK/provider failures. It never
retries refusals, malformed/semantic output, or validation failures. Firestore
transactions use the client transaction behavior; callers retry writes with the
same idempotency key and reconcile the returned locator after a timeout.

`STATBLOCKS_V1_ASSET_GATEWAY_ENABLED=true` only marks assets ready when
`FAL_KEY`, `CLOUDFLARE_ACCOUNT_ID`, and `CLOUDFLARE_IMAGES_API_TOKEN` are set.
The production pipeline treats `AssetBriefV1.prompt` as generation intent
(authored description / name), runs text-to-image, then uploads the result to
Cloudflare Images for a durable `asset_id` + CDN URL.
