# Hosted uv and systemd preparation

**Status:** Local preparation only; not an activation procedure

**Checked source:** DungeonMindServer `48b3f5181890ee3b3362cd12d9bfb8b41ddd65c1`

**Runtime baseline:** Python 3.11, matching the current project and CI contract

This runbook proposes a host-native release for the existing DungeonMind Web API. Each Python service gets an independent versioned release, committed lock, uv-managed virtual environment, service account, environment file, and systemd unit. It retains the current Docker deployment files for compatibility. It does not change application behavior, dependencies, `pyproject.toml`, or `uv.lock`.

The proposed DMS unit binds to `127.0.0.1:7860`, matching the app's current reverse-proxy comment, Docker `EXPOSE`/command, and host mapping in `deploy.sh`. The host inventory also observed the existing Nginx `/sms/` route forwarding to loopback port 7860. That is evidence for a candidate same-port handoff, not permission to stop the container or activate systemd. Do not run `deploy.sh`; it resets a checkout and removes/replaces Docker resources.

## Source and dependency contract

The checked source declares Python `>=3.11` and has a committed `uv.lock`. Existing CI uses `uv sync --locked --python 3.11`; the lock pins the Git source for `generationengine` at `80288d7b467ac3c3586f4e3c964385cefe69f931`. No Python 3.13 migration or dependency/lock update is included here. Select and record the uv executable version for each prepared release; the current DMS repo does not pin a uv version, and this preparation does not invent a new project pin. The current project lists `pytest` among main dependencies, so `--no-dev` does not remove it; moving test tools to the dev group would require a separate dependency change.

For a separately approved release-preparation operation:

1. Check out the reviewed full source revision into a new immutable path such as `/opt/dungeonmindserver/releases/<full-commit-sha>`. Verify the checkout is clean and `uv.lock` matches that revision.
2. Use the reviewed Python 3.11 interpreter and recorded uv executable to install dependencies in that release directory with `uv sync --locked --python 3.11 --no-dev --no-editable`. This is the only dependency-resolution/install phase. It may retrieve locked package/source artifacts; it must not invoke application providers or write credentials.
3. Record the source SHA, Python version, uv version, lock SHA, command, and preparation result alongside the release. Validate imports and the owning test suites in a provider-free environment before it can be considered for staging.
4. Create the `/opt/dungeonmindserver/current` symlink to an accepted release only under a separate operator-approved activation plan.

The systemd unit executes the release's absolute `.venv/bin/uvicorn` directly. It does not invoke uv, perform dependency resolution, run migrations, pull model assets, or alter a release at service start. A missing venv or incomplete release fails visibly instead of installing substitutes.

## Unit and configuration template

`deploy/production/systemd/dungeonmind-server.service` is a template for a dedicated `dungeonmindserver` account and the candidate loopback port 7860. `ProtectSystem=strict` and `ProtectHome=true` make the filesystem read-only by default. The only writable roots are candidate state `/var/lib/dungeonmindserver` and cache `/var/cache/dungeonmindserver`; choose and provision them deliberately outside every release. The unit expects production environment configuration in `/etc/dungeonmindserver/dms.env`.

`dms.env.example` contains placeholders. The installed environment file must be provisioned separately as root-owned with mode `0600`, using the approved secret process. Provide a real session secret, approved frontend/API host values, OAuth settings, OpenAI key and service-account path before any staging test that imports the production app. Do not create credentials as part of this preparation. Optional provider integration placeholders should only be populated for explicitly approved features. `TWILIO_TEST_MODE` must remain false in production. The app defaults `MONGODB_URI` to `mongodb://localhost:27017`; the placeholder prevents a release operator from accidentally adopting that default. Identify and approve the dedicated Rules Lawyer database/role and exact retained corpus before replacing its placeholders.

The application calls `load_dotenv('.env.production', override=True)` when `ENVIRONMENT=production`, and Firebase configuration also loads that file. Keep `.env.production` out of the immutable release tree so it cannot silently override the systemd environment file. Credentials belong only in the protected external configuration/secret paths.

The source contains tracked Rules Lawyer corpus files under `ruleslawyer/`. The candidate external `RULESLAWYER_DATA_DIR` path is only a durable location proposal: no corpus was copied, selected, or migrated. Before staging, the data owner must choose the exact retained corpus, check its provenance/retention rights, size, completeness, ownership and checksums, and stage it under the approved durable path through a reviewed procedure. Do not treat the current source directory, ignored `saved_data/`, or Docker bind mount as proven application backup/restore evidence.

The embedding model cache path is also only a candidate. The source uses `BAAI/bge-m3` through SentenceTransformers; no model artifact was fetched or validated here. Confirm its approved source, exact artifact/revision, cache ownership, and offline availability before any Rules Lawyer traffic. Do not let a future service smoke test silently fetch model weights.

## Existing Nginx integration

Keep the host's already-running Nginx service and include chain as the only reverse proxy. DMS continues to own port 7860; the inventory observed `/sms/` forwarded there. Preserve all current DMS vhosts and routes during preparation. Buddy's separately prepared location fragment targets its own loopback port 8080 and should be included by the existing Nginx configuration only after a separate route review. Do not create another Nginx process/container, replace the existing server block, or add/activate an unreviewed DMS route. Before any future switch, prove the 7860 port is no longer owned by the current DMS container; the old and new DMS processes cannot bind it concurrently.

Nginx configuration installation, validation against the live config, reload, DNS/TLS changes, and route activation are outside this preparation. The local static contract checks only that the templates name consistent candidate ports and paths.

## Data, databases, and service start

The current DMS image and Docker service remain untouched. Existing DMS Docker support is retained; this document proposes uv/systemd as the host-native path without deleting the container option. Do not connect to, inspect through credentials, or change the existing PostgreSQL/pgvector or Mongo containers. The bounded inventory established network adjacency only, not which application/database/owner any container serves.

The systemd template contains no migration command. Do not run migrations during release preparation or service start. Record each authority's owner, database, role and migration head before a future staging proposal. Prove a supported backup and isolated restore for each selected authority before any activation. Do not use a source symlink switch or application rollback to undo data/schema changes, and honor owner-specific migration downgrade fences.

No backup/restore was attempted for this preparation. The supplied host inventory was a bounded read-only snapshot; its scoped package-backup scan neither proves that application backups exist nor that they are absent elsewhere.

## Gates before a separate staging decision

- Select approved DMS public host/origin values and verify them with the same-origin Buddy route plan while retaining the existing DMS-managed user population.
- Establish the dedicated DMS service account, secure environment/credential delivery, data/cache roots, disk budget, and release-retention policy.
- Decide the exact retained Rules Lawyer corpus and owner; verify it before staging. The corpus directory is data, not an inference that the files are already backed up.
- Identify the actual Mongo/Firestore authorities and database ownership; do not reuse the network-adjacent containers by assumption.
- Review Python 3.11 / uv / lock evidence and provider-free imports/tests at the exact release SHA. Python 3.13 or broad dependency compatibility work requires a separately scoped change.
- Confirm the approved `BAAI/bge-m3` artifact/revision and stage it in the candidate cache through a reviewed procedure before serving Rules Lawyer traffic.
- Confirm the current container's port ownership and approved process switch/rollback sequence before trying to bind systemd on 7860.
- Review the existing single Nginx include chain and Buddy route, then validate and activate only under explicit live-change authority.
- Demonstrate isolated backup/restore and record migration heads before any data-bearing staging decision.

No source changes, dependencies, credentials, services, databases, Nginx configuration, DNS, provider calls, or live data were changed by this runbook.
