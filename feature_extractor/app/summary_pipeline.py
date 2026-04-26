from app.models import LLMClient

_CHUNK_SYSTEM = (
    "You are a precise acquisition analyst for federal government acquisition documents. "
    "Summarize the provided document excerpt clearly and concisely, capturing key "
    "requirements, deliverables, parties, dates, and dollar amounts if present. "
    "Output only the summary text with no preamble."
)

_ROLLUP_SYSTEM = (
    "You are a precise acquisition analyst for federal government acquisition documents. "
    "You are given a set of summaries from consecutive sections of a document. "
    "Synthesize them into a single coherent summary preserving the most important "
    "requirements, deliverables, parties, dates, and dollar amounts. "
    "Output only the summary text with no preamble."
)

_FINAL_SYSTEM = (
    "You are a precise acquisition analyst for federal government acquisition documents. "
    "You are given a set of section summaries covering an entire document. "
    "Write a comprehensive final summary of the full document, highlighting the "
    "overall purpose, scope, key requirements, deliverables, parties, and any "
    "critical dates or values. Output only the summary text with no preamble."
)


def chunk_items(items: list, size: int = 8) -> list[list]:
    """Split items into groups of `size`, evenly distributing any remainder
    across the last two groups instead of leaving a small trailing group.

    Example: 17 items → [8, 8, 1] → merge last two → 9 → [5, 4] → [8, 5, 4]
    """
    if not items:
        return []
    chunks = [items[i : i + size] for i in range(0, len(items), size)]
    if len(chunks) > 1 and len(chunks[-1]) < size:
        merged = chunks[-2] + chunks[-1]
        half = (len(merged) + 1) // 2  # ceil → first part is >= second
        chunks[-2:] = [merged[:half], merged[half:]]
    return chunks


def _join_pages(pages: list[str]) -> str:
    return "\n\n".join(pages)


def _join_summaries(summaries: list[str]) -> str:
    return "\n\n---\n\n".join(
        f"Section {i + 1}:\n{s}" for i, s in enumerate(summaries)
    )


def run(pages: list[str], client: LLMClient) -> dict:
    """Run hierarchical summarization over a list of page strings.

    Returns a dict ready to be merged into summary.json:
      {
        "layers": [...],
        "final_summary": "...",
      }
    """
    # Layer 0: summarize page chunks
    page_groups = chunk_items(pages)
    layer_0_chunks = []
    layer_0_summaries = []
    offset = 0
    for i, group in enumerate(page_groups):
        page_range = [offset, offset + len(group) - 1]
        offset += len(group)
        summary = client.complete(
            system=_CHUNK_SYSTEM,
            user=_join_pages(group),
            max_tokens=256,
        )
        layer_0_chunks.append(
            {"chunk_index": i, "page_range": page_range, "summary": summary}
        )
        layer_0_summaries.append(summary)

    layers = [{"layer": 0, "chunks": layer_0_chunks}]

    # Intermediate layers: roll up while > 8 summaries remain
    current_summaries = layer_0_summaries
    layer_num = 1
    while len(current_summaries) > 8:
        groups = chunk_items(current_summaries)
        next_summaries = []
        layer_chunks = []
        for i, group in enumerate(groups):
            summary = client.complete(
                system=_ROLLUP_SYSTEM,
                user=_join_summaries(group),
                max_tokens=256,
            )
            layer_chunks.append(
                {
                    "chunk_index": i,
                    "summary_range": [
                        sum(len(g) for g in groups[:i]),
                        sum(len(g) for g in groups[: i + 1]) - 1,
                    ],
                    "summary": summary,
                }
            )
            next_summaries.append(summary)
        layers.append({"layer": layer_num, "chunks": layer_chunks})
        current_summaries = next_summaries
        layer_num += 1

    # Final summary: at most 8 summaries remain
    final_summary = client.complete(
        system=_FINAL_SYSTEM,
        user=_join_summaries(current_summaries),
        max_tokens=512,
    )

    return {"layers": layers, "final_summary": final_summary}
