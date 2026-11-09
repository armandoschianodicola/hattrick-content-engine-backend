from io import BytesIO
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageDraw, ImageFont

from hattrick_backend.core.exceptions import AppError


class CardRenderer(Protocol):
    def render(self, content, theme) -> bytes: ...


class PillowRenderer:
    def __init__(self, font_path: Path | None = None):
        self.font_path = font_path

    def _font(self, size):
        candidates = (
            [str(self.font_path)]
            if self.font_path
            else [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "C:/Windows/Fonts/arial.ttf",
            ]
        )
        for candidate in candidates:
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
        if self.font_path:
            raise AppError("font_unavailable", "Configured rendering font is unavailable", 503)
        return ImageFont.load_default(size=size)

    @staticmethod
    def _lines(draw, text, font, width):
        lines = []
        for paragraph in text.split("\n"):
            current = ""
            for word in paragraph.split():
                candidate = f"{current} {word}" if current else word
                if draw.textlength(candidate, font=font) <= width:
                    current = candidate
                    continue
                if current:
                    lines.append(current)
                    current = ""
                # Fall back to character wrapping for long words and scripts without spaces.
                for char in word:
                    if current and draw.textlength(current + char, font=font) > width:
                        lines.append(current)
                        current = ""
                    current += char
            lines.append(current)
        return lines

    def _fit(self, draw, text, box, initial_size, fill):
        x, y, width, height = box
        for size in range(initial_size, 17, -2):
            font = self._font(size)
            lines = self._lines(draw, text, font, width)
            spacing = int(size * 1.4)
            if len(lines) * spacing <= height:
                for index, line in enumerate(lines):
                    draw.text((x, y + index * spacing), line, font=font, fill=fill)
                return
        raise AppError("text_does_not_fit", "Card text is too long for this template", 422)

    def render(self, content, theme):
        image = Image.new("RGB", (1080, 1080), theme.background)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((64, 60, 1016, 76), radius=8, fill=theme.accent)
        self._fit(draw, content.title, (72, 115, 936, 260), 66, theme.foreground)
        self._fit(
            draw,
            content.visual_text or content.explanation,
            (72, 400, 936, 420),
            44,
            theme.foreground,
        )
        draw.line((72, 900, 1008, 900), fill=theme.accent, width=3)
        self._fit(draw, theme.branding, (72, 935, 936, 95), 30, theme.accent)
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()
