import hashlib

from hattrick_backend.schemas.knowledge import Chunk, Document, Topic

TOPICS = [
    Topic(id="weather", name="Weather", description="Illustrative, unverified learning context"),
    Topic(id="specialties", name="Player specialties", description="Illustrative related topic"),
    Topic(id="attendance", name="Stadium attendance", description="Illustrative related topic"),
    Topic(id="match-engine", name="Match engine", description="Illustrative related topic"),
    Topic(id="tactics", name="Match tactics", description="Illustrative related topic"),
]
SAMPLE_TEXTS = [
    (
        "specialties",
        "Illustrative, not verified game mechanics: weather and player specialties "
        "are connected research topics. Check official rules before claiming a specialty benefit "
        "or penalty under particular weather conditions.",
    ),
    (
        "attendance",
        "Illustrative, not verified game mechanics: weather and stadium attendance "
        "are connected research topics. This sample provides no verified attendance effects, "
        "formulas, percentages, or numerical modifiers.",
    ),
]


class FakeKnowledgeRetriever:
    def __init__(self):
        self.chunks = []
        for index, (related, text) in enumerate(SAMPLE_TEXTS):
            self.chunks.append(
                Chunk(
                    id=f"sample-weather-{index}",
                    document=Document(
                        id=f"sample-doc-{index}",
                        title=f"Sample weather / {related}",
                        source_id="illustrative-fixture",
                        source_url=None,
                        authority="illustrative",
                        metadata={"verified": False},
                    ),
                    text=text,
                    topic_ids=["weather", related],
                    checksum=hashlib.sha256(text.encode()).hexdigest(),
                    score=1.0,
                )
            )

    async def list_topics(self, limit=20, offset=0):
        return TOPICS[offset : offset + limit], len(TOPICS)

    async def get_topic(self, topic_id):
        return next((t for t in TOPICS if t.id == topic_id), None)

    async def documents(self, topic_id, limit=20, offset=0):
        docs = [c.document for c in self.chunks if topic_id in c.topic_ids]
        return docs[offset : offset + limit], len(docs)

    async def related(self, topic_id, limit=20, offset=0):
        topics = (
            [t for t in TOPICS if t.id != topic_id]
            if topic_id == "weather"
            else ([TOPICS[0]] if await self.get_topic(topic_id) else [])
        )
        return topics[offset : offset + limit], len(topics)

    async def search(self, query, topic_id=None, limit=8):
        # Fixture filtering, deliberately not advertised as semantic search.
        return [c for c in self.chunks if topic_id is None or topic_id in c.topic_ids][:limit]
