"""Visibility gains stay distinct from human usefulness and query-policy claims."""

from __future__ import annotations

import httpx
import pytest

from evaluations.source_leads import evaluate


def test_held_out_visibility_comparison_uses_no_network_and_keeps_quality_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("offline evaluation attempted network transport")

    monkeypatch.setattr(httpx.Client, "request", no_network)
    report = evaluate()
    assert {case["topic_id"] for case in report["cases"]} == {"school-start", "green-roofs"}
    assert report["query_policy_winner"] is None
    assert report["useful_source_coverage"] is None
    assert report["human_readability"] is None
    assert report["new_paid_provider_calls"] == 0
    for case in report["cases"]:
        assert case["baseline_leads_visible_without_brief"] == 0
        assert case["source_leads_visible_without_brief"] == 5
        assert case["source_dispositions_inspectable"] == 5
        assert case["source_bytes_and_mtime_unchanged"]
        assert all(value == 0 for value in case["incremental_rendering_calls"].values())
