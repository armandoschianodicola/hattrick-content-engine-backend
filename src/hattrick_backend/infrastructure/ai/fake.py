import json

from hattrick_backend.infrastructure.ai.openai_provider import AIResult, GenerationResponse
from hattrick_backend.schemas.posts import Content


class FakeAIProvider:
    async def generate(self, prompt):
        data = json.loads(prompt)
        evidence = data["untrusted_evidence"]
        if not evidence:
            return AIResult(
                GenerationResponse(sufficient_evidence=False, content=None), "fake-v1", {}
            )
        # Deliberately restricted to the development fixture; never synthesizes game claims.
        content = Content(
            title="Weather: a research checklist (illustrative)",
            explanation="Illustrative sample, not verified game mechanics. Explore weather "
            "alongside player specialties and stadium attendance.",
            body="Before making a weather decision, consult verified official documentation "
            "on specialties and attendance. This development fixture establishes no "
            "specific effects, formulas, or numerical modifiers.",
            key_takeaway="Verify weather claims against authoritative sources before using them.",
            caption="Illustrative learning checklist: weather, specialties, attendance.",
            hashtags=["#Hattrick", "#Learning"],
            source_chunk_ids=[c["id"] for c in evidence],
            related_topic_ids=data["related_topic_ids"][:4],
            visual_text="Illustrative sample — verify mechanics with official rules.",
        )
        return AIResult(
            GenerationResponse(sufficient_evidence=True, content=content), "fake-v1", {}
        )
