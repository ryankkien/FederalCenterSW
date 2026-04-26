from __future__ import annotations

from typing import List, Optional, Sequence

from pydantic import BaseModel, Field


DEFAULT_TARGET_TOKENS = 1000
DEFAULT_OVERLAP_TOKENS = 120
CHARS_PER_TOKEN = 4


class TextChunk(BaseModel):
    index: int
    text: str
    start_char: int
    end_char: int
    pages: List[int] = Field(default_factory=list)


class PageText(BaseModel):
    page_number: int
    text: str
    start_char: Optional[int] = None
    end_char: Optional[int] = None


def chunk_text(
    text: str,
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    pages: Optional[Sequence[PageText]] = None,
) -> List[TextChunk]:
    normalized = (text or "").strip()
    if not normalized:
        return []

    target_chars = max(3200, target_tokens * CHARS_PER_TOKEN)
    overlap_chars = min(max(0, overlap_tokens * CHARS_PER_TOKEN), target_chars // 2)
    chunks = []
    start = 0

    while start < len(normalized):
        raw_end = min(len(normalized), start + target_chars)
        end = _preferred_break(normalized, start, raw_end, target_chars)
        chunk_text_value = normalized[start:end].strip()
        if chunk_text_value:
            actual_start = start + len(normalized[start:end]) - len(normalized[start:end].lstrip())
            actual_end = end - len(normalized[start:end]) + len(normalized[start:end].rstrip())
            chunks.append(
                TextChunk(
                    index=len(chunks),
                    text=chunk_text_value,
                    start_char=actual_start,
                    end_char=actual_end,
                    pages=_pages_for_range(pages or [], actual_start, actual_end),
                )
            )
        if end >= len(normalized):
            break
        start = max(0, end - overlap_chars)
        if start >= end:
            start = end

    return chunks


def _preferred_break(text: str, start: int, raw_end: int, target_chars: int) -> int:
    if raw_end >= len(text):
        return len(text)

    minimum = start + max(target_chars // 2, 1)
    window = text[minimum:raw_end]
    for marker in ("\n\n", "\n", ". ", "; ", ", ", " "):
        offset = window.rfind(marker)
        if offset >= 0:
            return minimum + offset + len(marker)
    return raw_end


def _pages_for_range(pages: Sequence[PageText], start_char: int, end_char: int) -> List[int]:
    result = []
    for page in pages:
        if page.start_char is None or page.end_char is None:
            continue
        if page.end_char <= start_char or page.start_char >= end_char:
            continue
        result.append(page.page_number)
    return result
