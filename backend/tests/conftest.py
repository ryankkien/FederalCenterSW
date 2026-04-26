import pytest


@pytest.fixture(autouse=True)
def disable_live_ai_by_default(monkeypatch):
    monkeypatch.setenv("AI_PROCESSING_ENABLED", "false")
    monkeypatch.setenv("AI_INLINE_PROCESSING_ENABLED", "false")
