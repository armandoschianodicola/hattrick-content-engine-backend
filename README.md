# Hattrick Educational Content Engine — Backend

Working FastAPI modular monolith for source-grounded educational drafts, revision history, human
review, square PNG cards, and Telegram text publication. Python 3.12+, async SQLAlchemy,
PostgreSQL/pgvector, Alembic, Pydantic v2, OpenAI SDK, Pillow, uv and Ruff.

Development defaults use deterministic fake AI and illustrative knowledge. The sample connects
weather, player specialties and attendance as **research topics, not verified game mechanics**.
No source scraping or ingestion is implemented. No content is automatically approved or published.

## Quick start

Install [uv](https://docs.astral.sh/uv/) and Docker with Compose. From this repository:

```powershell
Copy-Item .env.example .env
uv sync --frozen
docker compose up -d db
uv run alembic upgrade head
uv run uvicorn hattrick_backend.main:app --host localhost --port 8010 --reload --no-access-log
```

On macOS/Linux use `cp .env.example .env`. API docs: <http://localhost:8010/docs>. Health:
<http://localhost:8010/health/ready>. Click **Authorize** in Swagger and enter the `.env` `API_KEY`.
All `/api/v1` routes require this key in `X-API-Key`. Defaults: database `localhost:5434`, API
`localhost:8010`; override `DATABASE_PORT`, `API_PORT` for Compose and `DATABASE_URL`/uvicorn flags
for host execution. These ports allow the stack to coexist with a separate ingestion database.

To run everything in Docker instead:

```sh
docker compose up --build -d
docker compose logs api
```

Compose runs a one-shot migration before starting the non-root API container. PostgreSQL data and
assets use named volumes. `docker compose down` stops the stack and retains data. Configure real
credentials and separate database roles before production; see [architecture](docs/architecture.md).

## Demonstrate the workflow

With the API running and default fake providers:

```sh
uv run python scripts/demo.py
```

This lists topics, retrieves weather context, generates/persists a draft, retrieves/edits it,
submits/approves it, renders/downloads `data/demo-card.png`, and inspects publication history.
The demonstration script performs review actions explicitly; generation itself only creates drafts.
Review generated content in Swagger before publishing anything outside development.

Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`, give the bot access to that chat/channel,
restart the API, then explicitly request a real send:

```sh
uv run python scripts/demo.py --publish
```

Telegram is plain text in this MVP. PNG assets can be downloaded separately. Unconfigured
Telegram returns a recorded `FAILED/not_configured` attempt, never simulated success.

Example generation:

```sh
curl -X POST http://localhost:8010/api/v1/generations \
  -H 'X-API-Key: local-development-key-change-me' -H 'Content-Type: application/json' \
  -d '{"topic_id":"weather","content_type":"educational","target_platforms":["telegram"],"tone":"informative","language":"en"}'
```

For edits send `{"expected_revision":1,"content":{...complete content...}}` to `PATCH /posts/{id}`.
Review actions require `{"expected_revision":1,"note":"Reviewed sources"}`. Use the current revision
after any edit. Only drafts can be edited; reject a pending post and reopen it to revise it.

| Operation | Endpoint under `/api/v1` |
| --- | --- |
| Topics and evidence | `GET /topics`, `/topics/{id}`, `/{id}/documents`, `/{id}/related`, `/{id}/context` |
| Generate draft | `POST /generations` |
| List/read/edit | `GET /posts`, `GET /posts/{id}`, `PATCH /posts/{id}` |
| Review | `POST /posts/{id}/submit-review`, `/approve`, `/reject`, `/reopen` |
| Schedule | `POST /posts/{id}/schedule` with revision and timezone-aware `scheduled_at` |
| Audit | `GET /posts/{id}/history`, `/revisions` |
| Card assets | `POST /posts/{id}/render`, `GET /posts/{id}/assets`, `/assets/{asset_id}` |
| Publication | `POST /posts/{id}/publish`, `GET /posts/{id}/publications` |

Publish body: `{"platforms":["telegram"],"idempotency_key":"my-publication-001"}`. A repeated key
returns its original attempt. Successful platforms are never sent again even with a new key.
Use a new key only to retry a definite failure. `UNKNOWN` or `IN_PROGRESS` blocks new attempts until
operator reconciliation; Telegram cannot guarantee exactly-once delivery after a timeout.
Partial platform failure leaves approval intact; aggregate `PUBLISHED` means all targets succeeded.

List endpoints accept `limit` (1–100) and `offset`; posts also accept `state` and `topic_id`.
Context accepts `query` and a bounded retrieval `limit`. Errors use
`{"error":{"code":"...","message":"...","request_id":"...","details":null}}`.
Validation is 422, missing entities 404, authentication 401, conflicts 409, provider failures 502,
unavailable configuration/database 503. Publishing results report platform failures in a 200
orchestration response; inspect each item's `status` and `error`.

## OpenAI and ingestion integration

Set `AI_PROVIDER=openai` and `OPENAI_API_KEY`, restart the API. `OPENAI_MODEL`,
`OPENAI_MAX_OUTPUT_TOKENS` and optional `OPENAI_TEMPERATURE` configure generation. Omit temperature
for models that do not support it. The adapter follows the
[official OpenAI structured-output documentation](https://developers.openai.com/api/docs/guides/structured-outputs)
using the Responses API and Pydantic. Generation records model, prompt version, usage and sources.
Refused, invalid, insufficient-evidence and unknown-citation responses never become drafts.
Using OpenAI with sample knowledge still produces illustrative material, not verified instruction.

For real knowledge, agree [provisional ingestion contract v1](docs/knowledge-contract.md), provision
it through the **ingestion repository**, and set `RETRIEVAL_PROVIDER=pgvector`. Configure matching
embedding model/dimensions and OpenAI credentials for query embeddings even if generation uses a
different provider. Backend migrations never create knowledge tables. Missing knowledge schema
is a clear 503. Production requires real providers, `ALLOW_ILLUSTRATIVE_EVIDENCE=false`, a unique
API key of at least 32 characters, and secure database/platform credentials.

## Tests and checks

```sh
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run alembic check
```

The default suite uses SQLite only as a fast test persistence adapter and mocks all network calls.
It needs no real AI/platform credentials or running PostgreSQL. PostgreSQL integration tests are
opt-in and cover pgvector SQL plus competing publication claims. Use a **dedicated database ending
in `_test`**; the fixture creates test-only knowledge tables there. With the Compose database:

```powershell
docker compose exec db createdb -U hattrick hattrick_backend_test
$env:DATABASE_URL='postgresql+asyncpg://hattrick:hattrick@localhost:5434/hattrick_backend_test'
uv run alembic upgrade head
$env:TEST_DATABASE_URL=$env:DATABASE_URL
uv run pytest -q
Remove-Item Env:DATABASE_URL, Env:TEST_DATABASE_URL
```

Use shell `export`/`unset` equivalents on Linux. On repeated runs, skip `createdb` if it already
exists. `alembic check` compares only backend-owned tables. Do not point integration tests at
production or ingestion databases. Tests do not auto-drop schemas or databases.

See [architecture and deferred features](docs/architecture.md) for lifecycle semantics, publishing
crash behavior, scheduling/worker design, security boundaries, renderer/storage extension points,
and the explicit list of work beyond this MVP. Facebook/Instagram publishing, automatic scheduled
execution, object storage and multi-user authentication are deferred.
