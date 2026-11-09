# Ingestion/backend boundary — provisional v1

The ingestion repository owns knowledge records, vector extension installation, and all migrations
under `knowledge`. Backend Alembic manages only `backend` (including its version table). Backend
startup never creates, seeds, scrapes, or migrates knowledge. The repositories can share a PostgreSQL
instance; use separate login roles and schemas. The standalone Compose database is an isolated
development option, not an attempt to provision ingestion.

The read-only `KnowledgeRetriever` protocol is the application boundary. Adapt
`PgvectorRetriever` or expose compatibility views when the ingestion schema is finalized. Changing
storage layout must not affect generation, API, or lifecycle services. Knowledge IDs are opaque
strings; backend-owned IDs are UUIDs. Do not add cross-schema foreign keys: deleting or replacing
knowledge must not destroy historical content provenance.

Required relations (all IDs below are non-null `text`; timestamps, where used, are `timestamptz`):

| Relation | Required columns and constraints |
| --- | --- |
| `knowledge.topics` | `id` PK, `name` text, `description` text |
| `knowledge.sources` | `id` PK, `url` nullable text, `authority` text: official/community/personal/illustrative |
| `knowledge.documents` | `id` PK, `source_id` FK sources, `title` text, `metadata` JSONB object |
| `knowledge.chunks` | `id` PK, `document_id` FK documents, `text` text, `checksum` SHA-256 text, `embedding` vector(1536), `embedding_model` text, `embedding_dimensions` integer |
| `knowledge.chunk_topics` | `chunk_id` FK chunks, `topic_id` FK topics; composite PK |
| `knowledge.topic_relationships` | `topic_id`, `related_topic_id` FKs topics; composite PK; no self-links |

All columns are required unless explicitly nullable. `metadata` should include document revision,
retrieved/updated timestamps, original author/license where available, and verification status.
URLs must be stable source references, never signed links, access tokens, or credentials. Backend
exposes source metadata to administrators. Chunk checksums must change when the exact UTF-8 text
changes; preserve historical IDs or versions where possible.

Embeddings must use the same model, dimensions and preprocessing as backend query embeddings.
Defaults: `text-embedding-3-small`, 1536 dimensions, cosine distance. A model/dimension change requires
an ingestion migration and re-embedding; do not mix incompatible vectors. Backend filters by model
and dimensions and applies `RETRIEVAL_MIN_SIMILARITY`. A missing contract yields 503
`knowledge_unavailable`; no relevant or compatible evidence yields 422 `insufficient_evidence`.

Ingestion should install `CREATE EXTENSION vector`, index `chunk_topics(topic_id, chunk_id)` and
`chunks(document_id)`, and consider an HNSW `vector_cosine_ops` index after evaluating filtered
search recall and corpus size. The adapter uses parameterized SQL and cosine similarity; it does
not write knowledge. Related-topic links are traversed in both directions. Generation combines
multiple chunks tagged to the requested topic. Ingestion can tag chunks with multiple topics;
the backend does not silently pull unfiltered text from every related topic.

Backend stores every retrieved chunk's ID, document/source IDs, title, URL, authority, similarity,
and checksum in `backend.post_sources`. Content lists the subset actually cited. Source text is
not copied. Generation options, prompt version, model, and usage are recorded separately.
Similarity measures relevance, not truth. Context orders official evidence before community,
personal, and illustrative evidence. Human reviewers remain responsible for checking claims;
structured output and citation membership do not prove factual entailment.

Suggested integration sequence:

1. Agree this contract or provide ingestion-owned views matching it.
2. Grant the API role `USAGE` on `knowledge` and `SELECT` on these relations; grant no write rights.
3. Grant a migration role ownership of `backend`; use a separate runtime role with backend DML.
4. Run backend Alembic independently of ingestion deployment.
5. Set `RETRIEVAL_PROVIDER=pgvector`, configure embedding credentials/model/dimensions, and disable
   illustrative evidence. Check `/health/ready` and `/api/v1/topics/weather/context`.
6. Exercise generation and source auditing before enabling publication credentials.

`tests/fixtures/knowledge_v1.sql` is a **test-only contract fixture**, not an ingestion migration.
It is never loaded by API startup, backend migrations, or Compose.
