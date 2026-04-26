import json
import re

from app.models import LLMClient

_SYSTEM = """You are a federal acquisition classification expert with deep knowledge of the \
DoD Product and Service Code (PSC) Manual (April 2022) and the North American Industry \
Classification System (NAICS).

Given a document summary, output a JSON object (no markdown, no preamble) with exactly these fields:
{
  "psc_code": "<4-character PSC code>",
  "psc_description": "<short PSC category name>",
  "naics_code": "<6-digit NAICS code>",
  "naics_description": "<short NAICS industry name>",
  "rationale": "<one or two sentences explaining the classification>"
}

PSC codes are 4-character alphanumeric codes (e.g. "D302", "R408", "AC13").
NAICS codes are 6-digit numeric codes (e.g. "541511", "336411").
Choose the most specific applicable code for each system."""


def classify(final_summary: str, client: LLMClient) -> dict:
    """Return a classification dict with psc_code, psc_description, naics_code,
    naics_description, and rationale."""
    raw = client.complete(
        system=_SYSTEM,
        user=f"Document summary:\n\n{final_summary}",
        max_tokens=256,
    )
    return _parse(raw)


def _parse(raw: str) -> dict:
    # Strip markdown code fences if the model wrapped the JSON
    text = re.sub(r"^```[a-z]*\n?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        # Fall back: return raw text under rationale so the caller still gets something
        return {
            "psc_code": None,
            "psc_description": None,
            "naics_code": None,
            "naics_description": None,
            "rationale": raw.strip(),
        }
    return {
        "psc_code": result.get("psc_code"),
        "psc_description": result.get("psc_description"),
        "naics_code": result.get("naics_code"),
        "naics_description": result.get("naics_description"),
        "rationale": result.get("rationale"),
    }
