import pytest

from app.html_snippets import extract_html_snippets, looks_like_html, normalize_html_document


def test_extracts_fenced_html_code_block():
    snippets = extract_html_snippets(
        "please render this\n```html\n<div class=\"card\">Hello</div>\n```"
    )

    assert len(snippets) == 1
    assert "<div class=\"card\">Hello</div>" in snippets[0].html
    assert snippets[0].source == "message"
    assert snippets[0].truncated is False


def test_extracts_unlabeled_fence_that_looks_like_html():
    snippets = extract_html_snippets("```\n<section>Report</section>\n```")

    assert len(snippets) == 1
    assert "<section>Report</section>" in snippets[0].html


def test_ignores_non_html_code_block():
    assert extract_html_snippets("```python\nprint('hello')\n```") == []


def test_extracts_raw_html_message():
    snippets = extract_html_snippets("<table><tr><td>Cost</td></tr></table>")

    assert len(snippets) == 1
    assert "<table>" in snippets[0].html


def test_does_not_treat_discord_mentions_as_html():
    assert looks_like_html("<@1234567890>") is False
    assert extract_html_snippets("<@1234567890> please review") == []


def test_truncates_large_snippets():
    snippets = extract_html_snippets("<div>" + "x" * 20 + "</div>", max_chars=12)

    assert len(snippets) == 1
    assert snippets[0].truncated is True
    assert "<div>xxxxxxx" in snippets[0].html


def test_rejects_invalid_limits():
    with pytest.raises(ValueError):
        extract_html_snippets("<div>hello</div>", max_chars=0)

    with pytest.raises(ValueError):
        extract_html_snippets("<div>hello</div>", max_snippets=0)


def test_wraps_html_fragments_in_document():
    normalized = normalize_html_document("<div>Hello</div>")

    assert normalized.startswith("<!doctype html>")
    assert "<body>\n<div>Hello</div>\n</body>" in normalized


def test_keeps_full_html_document():
    html = "<!doctype html><html><body>Hello</body></html>"

    assert normalize_html_document(html) == html
