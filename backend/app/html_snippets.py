from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List


HTML_CODE_LANGUAGES = {"html", "htm"}
DEFAULT_HTML_TAGS = (
    "html",
    "body",
    "head",
    "style",
    "script",
    "div",
    "span",
    "p",
    "a",
    "img",
    "svg",
    "canvas",
    "section",
    "article",
    "main",
    "header",
    "footer",
    "table",
    "ul",
    "ol",
    "li",
    "form",
    "button",
    "input",
)

FENCED_CODE_BLOCK_RE = re.compile(
    r"```(?P<language>[A-Za-z0-9_-]*)[^\n\r]*[\r\n]+(?P<body>.*?)```",
    re.DOTALL,
)


@dataclass(frozen=True)
class HtmlSnippet:
    html: str
    source: str
    truncated: bool = False


def looks_like_html(value: str, tag_names: Iterable[str] = DEFAULT_HTML_TAGS) -> bool:
    text = value.strip()
    if not text:
        return False

    lowered = text.lower()
    if "<!doctype html" in lowered or "<html" in lowered:
        return True

    for tag_name in tag_names:
        if re.search(rf"<\s*/?\s*{re.escape(tag_name)}(?:\s|>|/)", lowered):
            return True

    return False


def normalize_html_document(value: str) -> str:
    html = value.strip()
    lowered = html.lower()

    if "<!doctype html" in lowered or "<html" in lowered:
        return html

    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<style>",
            "html, body { margin: 0; min-height: 100%; background: white; }",
            "body { box-sizing: border-box; }",
            "*, *::before, *::after { box-sizing: inherit; }",
            "</style>",
            "</head>",
            "<body>",
            html,
            "</body>",
            "</html>",
        ]
    )


def _bounded_snippet(value: str, *, max_chars: int, source: str) -> HtmlSnippet:
    html = value.strip()
    truncated = len(html) > max_chars
    if truncated:
        html = html[:max_chars]

    return HtmlSnippet(html=normalize_html_document(html), source=source, truncated=truncated)


def extract_html_snippets(
    text: str,
    *,
    max_chars: int = 12_000,
    max_snippets: int = 3,
) -> List[HtmlSnippet]:
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero")
    if max_snippets <= 0:
        raise ValueError("max_snippets must be greater than zero")

    snippets: List[HtmlSnippet] = []

    for match in FENCED_CODE_BLOCK_RE.finditer(text):
        language = match.group("language").lower()
        body = match.group("body")
        if language in HTML_CODE_LANGUAGES or (not language and looks_like_html(body)):
            snippets.append(_bounded_snippet(body, max_chars=max_chars, source="message"))
            if len(snippets) >= max_snippets:
                return snippets

    if snippets:
        return snippets

    if looks_like_html(text):
        return [_bounded_snippet(text, max_chars=max_chars, source="message")]

    return []
