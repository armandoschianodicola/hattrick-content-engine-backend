from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from hattrick_backend.application.prompts.educational_post import build_prompt
from hattrick_backend.core.exceptions import AppError
from hattrick_backend.infrastructure.ai.fake import FakeAIProvider
from hattrick_backend.infrastructure.rendering.pillow_renderer import PillowRenderer
from hattrick_backend.infrastructure.retrieval.fake import FakeKnowledgeRetriever
from hattrick_backend.infrastructure.storage import LocalAssetStorage
from hattrick_backend.schemas.posts import GenerationRequest, RenderRequest


def test_renderer_preserves_words_when_wrapping():
    renderer = PillowRenderer()
    draw = ImageDraw.Draw(Image.new("RGB", (1080, 1080)))
    font = renderer._font(40)
    width = draw.textlength("alpha beta", font=font) - 1
    assert renderer._lines(draw, "alpha beta", font, width) == ["alpha", "beta"]
    long_word = "x" * 200
    lines = renderer._lines(draw, long_word, font, width)
    assert "".join(lines) == long_word
    assert all(draw.textlength(line, font=font) <= width for line in lines)


async def test_image_dimensions_theme_and_long_content(tmp_path):
    result = await FakeAIProvider().generate(
        build_prompt(GenerationRequest(topic_id="weather"), FakeKnowledgeRetriever().chunks, [])
    )
    content = result.response.content
    content.title = "Weather " * 17
    content.visual_text = "Research " * 44
    data = PillowRenderer().render(content, RenderRequest(background="#123456"))
    image = Image.open(BytesIO(data))
    assert image.size == (1080, 1080) and image.getpixel((0, 0)) == (18, 52, 86)
    assert len(image.getcolors(maxcolors=1080 * 1080)) > 2
    storage = LocalAssetStorage(tmp_path)
    storage.put("post/card.png", data)
    assert storage.read("post/card.png") == data
    with pytest.raises(AppError):
        storage.read("../outside.png")
