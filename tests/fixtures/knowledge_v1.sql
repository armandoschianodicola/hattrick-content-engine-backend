-- TEST-ONLY example contract. Never installed by backend migrations/startup.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS knowledge;
CREATE TABLE IF NOT EXISTS knowledge.topics (
    id text PRIMARY KEY, name text NOT NULL, description text NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge.sources (
    id text PRIMARY KEY, url text,
    authority text NOT NULL CHECK (authority IN ('official','community','personal','illustrative'))
);
CREATE TABLE IF NOT EXISTS knowledge.documents (
    id text PRIMARY KEY, source_id text NOT NULL REFERENCES knowledge.sources(id),
    title text NOT NULL, metadata jsonb NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS knowledge.chunks (
    id text PRIMARY KEY, document_id text NOT NULL REFERENCES knowledge.documents(id),
    text text NOT NULL, checksum text NOT NULL, embedding vector(1536) NOT NULL,
    embedding_model text NOT NULL, embedding_dimensions integer NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge.chunk_topics (
    chunk_id text REFERENCES knowledge.chunks(id), topic_id text REFERENCES knowledge.topics(id),
    PRIMARY KEY (chunk_id, topic_id)
);
CREATE INDEX IF NOT EXISTS ix_chunk_topics_topic ON knowledge.chunk_topics(topic_id, chunk_id);
CREATE TABLE IF NOT EXISTS knowledge.topic_relationships (
    topic_id text REFERENCES knowledge.topics(id),
    related_topic_id text REFERENCES knowledge.topics(id),
    PRIMARY KEY (topic_id, related_topic_id), CHECK (topic_id <> related_topic_id)
);
INSERT INTO knowledge.topics VALUES
    ('weather', 'Weather', 'Contract test only'),
    ('attendance', 'Attendance', 'Contract test only') ON CONFLICT DO NOTHING;
INSERT INTO knowledge.sources VALUES
    ('test-source', 'https://example.org/test-only', 'illustrative') ON CONFLICT DO NOTHING;
INSERT INTO knowledge.documents VALUES
    ('test-document', 'test-source', 'Contract fixture', '{"verified": false}') ON CONFLICT DO NOTHING;
INSERT INTO knowledge.chunks VALUES (
    'test-chunk', 'test-document', 'Illustrative contract fixture; no verified game mechanics.',
    encode(sha256(convert_to('Illustrative contract fixture; no verified game mechanics.', 'UTF8')), 'hex'),
    ('[1,' || repeat('0,',1534) || '0]')::vector,
    'text-embedding-3-small', 1536
) ON CONFLICT DO NOTHING;
INSERT INTO knowledge.chunk_topics VALUES
    ('test-chunk', 'weather'), ('test-chunk', 'attendance') ON CONFLICT DO NOTHING;
INSERT INTO knowledge.topic_relationships VALUES ('weather', 'attendance') ON CONFLICT DO NOTHING;
