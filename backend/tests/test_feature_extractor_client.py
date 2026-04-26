from app.feature_extractor_client import trigger_feature_extractor


def test_trigger_feature_extractor_calls_summary_then_primitives(monkeypatch) -> None:
    calls = []

    def fake_post_json(base_url, path, payload, headers=None):
        calls.append((base_url, path, payload, headers))
        if path == "/summarize":
            return {
                "doc_id": "doc-1",
                "blob_path": "contracts/doc-1/summary.json",
                "model": "test-model",
                "classification": {"psc_code": "D302", "naics_code": "541511"},
            }
        return {
            "doc_id": "doc-1",
            "extraction_run_id": "primitive-run-1",
            "primitives_extracted": {"deliverable": 2},
        }

    monkeypatch.setenv("FEATURE_EXTRACTOR_URL", "http://extractor.local/")
    monkeypatch.setattr("app.feature_extractor_client._post_json", fake_post_json)

    steps = trigger_feature_extractor("doc-1", "contract-1", "monthly_report")

    assert calls == [
        (
            "http://extractor.local",
            "/summarize",
            {"doc_id": "doc-1", "contract_id": "contract-1"},
            {
                "X-Document-Upload-ID": "doc-1",
                "X-Contract-ID": "contract-1",
            },
        ),
        (
            "http://extractor.local",
            "/extract-primitives",
            {
                "doc_id": "doc-1",
                "contract_id": "contract-1",
                "doc_classification": "monthly_report",
            },
            {
                "X-Document-Upload-ID": "doc-1",
                "X-Contract-ID": "contract-1",
            },
        ),
    ]
    assert [step.step_name for step in steps] == [
        "feature_extractor.summary",
        "feature_extractor.primitives",
    ]
    assert [step.status for step in steps] == ["success", "success"]
    assert steps[1].metadata["primitives_extracted"] == {"deliverable": 2}


def test_trigger_feature_extractor_returns_failed_step_when_summary_fails(monkeypatch) -> None:
    def fake_post_json(base_url, path, payload, headers=None):
        raise RuntimeError("connection refused")

    monkeypatch.setenv("FEATURE_EXTRACTOR_URL", "http://extractor.local")
    monkeypatch.setattr("app.feature_extractor_client._post_json", fake_post_json)

    steps = trigger_feature_extractor("doc-1", "contract-1", "monthly_report")

    assert len(steps) == 1
    assert steps[0].step_name == "feature_extractor.summary"
    assert steps[0].status == "failed"
    assert "connection refused" in (steps[0].message or "")
