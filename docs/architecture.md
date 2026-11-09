# Architecture and operating boundaries

This is a modular monolith: FastAPI validates input and injects dependencies; application services
coordinate retrieval, generation, content revisions, rendering and publishing; domain rules define
transitions and approval guards; infrastructure implements PostgreSQL, OpenAI, Pillow, local file
storage and platform APIs. Small protocols isolate external systems without a generic repository
framework. No scraper, message broker, in-process timer, or autonomous agent is included.

`main.py` is the composition root. Connections and HTTP clients have application lifetimes;
database sessions have request lifetimes and roll back on errors. Migrations are an explicit
deployment step. `/health` is liveness; `/health/ready` checks backend tables and topic access when
pgvector is selected. Readiness does not make paid AI calls or verify platform credentials.

Generated content is a validated JSONB value with bounded fields. Posts, revisions, source
references, generation metadata, assets, approval events, platform statuses, and attempts each
have relational ownership and foreign keys. Revisions retain edited content, not entire source
documents. List endpoints have deterministic ordering, bounds, and totals. Use `state` and
`topic_id` to filter posts; document/context endpoints scope knowledge to a topic.

## Generation and evidence

The versioned prompt treats documents and request options as data, gives an authority ordering,
forbids invented mechanics and values, and permits insufficient-evidence responses. The OpenAI
Responses adapter uses Pydantic structured output, checks refusals/missing parsed output, and
captures usage. Model and output limits are configured; temperature is omitted unless explicitly
set for a model that supports it. There are no tools available to the model. Citation/related-topic
membership is checked before persistence. Empty evidence never calls the AI. The development fake
always writes a labelled research checklist; it is not a factual weather tutorial or a real AI.

Prompt instructions and schema validation cannot guarantee semantic truth. Reviewers must verify
every claim, especially numerical claims, against sources. Conflicting or weak evidence requires
review; production excludes illustrative evidence entirely. Future factuality evaluation can add
claim-level evidence checks. Do not treat a successful generation request as permission to publish.

## Content lifecycle and concurrency

Draft → pending review → approved → scheduled → published is supported, as are rejection and
reopening a rejected post. All review/edit requests include `expected_revision`. PostgreSQL post
row locks serialize transitions and writes; stale revisions return 409. Only drafts are editable.
Approval records cover an exact revision. Approved, scheduled and published revisions are immutable.
A rejected post can return to draft and be revised and reviewed again. No automatic approval exists.
Shared API-key authentication records `api-key-admin`, not an unverifiable individual identity.

`FAILED` is reserved for aggregate operational failure/recovery; individual publishing failures
are stored per platform and leave approval intact for retry. A post becomes `PUBLISHED` after every
target platform succeeds. One target's failure never changes another target's success. Publishing
an already published post only returns its existing outcome: it cannot intentionally repost.

## External side effects and retry safety

The publisher first locks the post, validates approval and due time, and transactionally records
per-platform `IN_PROGRESS` attempts. It commits before contacting the platform. Same-key retries
return the original attempt. A new key may retry definite failures, but a platform that already
succeeded is never sent again. Per-post/platform uniqueness plus post locks serialize competing
API instances. Use a stable key for a logical request and a new key only for an intentional retry
of a definite failure. IDs are scoped to post/platform.

Telegram lacks a client-provided deduplication key. A read timeout, malformed success response,
5xx, or crash after send may hide a successful remote send. Such outcomes are `UNKNOWN` or remain
`IN_PROGRESS`; new sends are blocked. Exactly-once delivery across PostgreSQL and Telegram is
not promised. Reconcile these records manually using the destination chat and application history.
Do not expire and blindly retry them. With exclusive operator access and no active request, record
the known external ID and mark attempt/platform `SUCCEEDED`, or record verified non-delivery and
mark both `FAILED`; document the evidence in an operations ticket. If all targets succeeded,
reconcile the aggregate post and append an approval-history event in the same transaction. A future
admin reconciliation tool should formalize this process with operator identity and an audit table.

The Telegram MVP sends plain text through `sendMessage`; rendered PNG cards are downloadable and
not automatically uploaded. Oversized Telegram messages fail explicitly before sending. Bot must
have access to the configured chat/channel and permission to post. Upstream error descriptions,
token-bearing URLs and response bodies are not returned or logged. No live send occurs in tests.

Facebook and Instagram adapters always return `FAILED/not_implemented`. Future integration needs
a Meta app, appropriate accounts/pages, permission review and token rotation; Instagram image
publication additionally needs media hosting and container creation/status/publish handling.
Confirm the then-current official provider requirements before implementing either adapter.

## Rendering and assets

Pillow renders 1080×1080 PNGs with bounded title/body areas, adaptive font size and configurable
colors/branding. Configure a font for the languages you publish; bundled Docker DejaVu covers
common Latin scripts, not every writing system. Rendering and filesystem work run off the event
loop. `CardRenderer` and `AssetStorage` allow replacing Pillow or local storage independently.
Asset metadata records the content revision. Paths are confined to the asset root; downloads
require authentication. Shared deployments need a shared asset volume or an object-store adapter.
A database failure after file creation can leave an orphan; future cleanup should remove only
unreferenced assets after a retention window.

## Scheduling and HTTP operation limits

The schedule endpoint persists a future timezone-aware timestamp after approval. There is **no
automatic scheduler in the MVP**. A due scheduled post can be published through the normal API;
future workers should query due posts, use durable claims/leases or `FOR UPDATE SKIP LOCKED`, and
call the same publishing service with stable job/platform keys. Commit durable claims before
network calls and reconcile unknown outcomes. `workers/scheduling.py` defines the future runner
contract. Scheduled generation will require its own durable jobs and deduplicated draft creation.

Service orchestration is separate from HTTP handlers, but generation and rendering currently run
within a request. Database transactions do not remain open during AI generation. Use suitable
proxy/client timeouts and avoid automatic retry of generation requests: generation creation is
not idempotent. A future durable job API can provide 202 responses and polling without changing
domain services. Scheduling/external publishing are not FastAPI background tasks.

## Security and deployment

All `/api/v1` endpoints require `X-API-Key`; health endpoints are public. Use TLS and an ingress
rate limiter for any external deployment. Rotate keys and platform secrets through environment
configuration. Production rejects sample providers, weak/default API keys and illustrative
evidence. Secrets use Pydantic `SecretStr`; SQL echo/access logging and outbound HTTP logs are
disabled. Error envelopes omit stack traces, validation input and provider strings. API-key auth
is an MVP shared administrator credential, not multi-user authorization.

Compose binds development ports to localhost. Its database credentials are development defaults.
Production requires separate runtime/migration database roles, secret management, backup/restore
testing, dependency/image patching, and externally managed schema deployment. Build uses a lockfile
and a non-root runtime. Migration execution is a one-shot Compose service, not API startup logic.

## Deferred beyond MVP

- Ingestion schema finalization, source verification and real knowledge population.
- Facebook/Instagram integrations and Telegram photo uploads.
- Durable generation/publication workers, automatic scheduled execution and job monitoring.
- Operator reconciliation API, individual identities/RBAC and approval separation of duties.
- Claim-level factuality evaluation, evidence snapshots and multilingual content quality evaluation.
- Object storage, advanced card templates/editor and comprehensive script/font coverage.
- Cursor pagination, retention/asset cleanup, rate limits and full metrics/tracing.
- Intentional reposting, destination changes and editing content after approval/publication.
