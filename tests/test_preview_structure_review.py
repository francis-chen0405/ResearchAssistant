from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from researchassistant.contracts.discovery_v2 import V2PreviewRequest, V2PreviewResult, discovery_id
from researchassistant.contracts.model_contracts import SourceSnapshot
from researchassistant.contracts.research_directions import ResearchDirection, ResearchDirections
from researchassistant.evidence.evidence_core import build_source_snapshot
from researchassistant.research.source_preview import build_capture_windows, build_claim_preview

NOW = datetime(2026, 10, 7, 12, tzinfo=UTC)
CLAIM = "The intervention reduces depression symptoms."


def _build(
    text: str,
    *,
    truncated: bool = False,
    claim: str = CLAIM,
    components: tuple[str, ...] = ("depression symptoms", "intervention"),
) -> tuple[SourceSnapshot, V2PreviewResult]:
    snapshot: SourceSnapshot = build_source_snapshot(
        run_id=uuid4(),
        retrieval_attempt_id=uuid4(),
        snapshot_id=uuid4(),
        source_url="https://example.test/article",
        retrieved_at=NOW,
        normalized_text=text,
        truncated=truncated,
        created_at=NOW,
    )
    key = f"preview-structure/{snapshot.snapshot_id}"
    request = V2PreviewRequest(
        run_id=snapshot.run_id,
        artifact_id=discovery_id(snapshot.run_id, "V2PreviewRequest", key),
        identity_key=key,
        exact_claim=claim,
        asserted_components=components,
        target_gaps=("methods", "results", "effect estimate"),
        direction=ResearchDirection.SUPPORT,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=True),
        source_id=uuid4(),
        snapshot_id=snapshot.snapshot_id,
        snapshot_hash=snapshot.snapshot_sha256,
        preview_identity="source-claim-preview-v2",
    )
    return snapshot, build_claim_preview(request, snapshot)


def test_flat_abstract_with_inline_doi_and_reference_heading_keeps_only_abstract() -> None:
    text = (
        "The intervention and depression symptoms\n"
        "Abstract: In a randomized trial, the intervention reduced depression symptoms by "
        "3 points compared with usual care. References: 1. Smith et al. (2020), DOI "
        "10.1000/182, 2. Jones (2021), DOI 10.1000/183."
    )
    snapshot, result = _build(text)

    assert result.outcome == "completed"
    assert result.content_classification == "abstract_only"
    assert "abstract" in result.observed_sections
    assert "bibliography" in result.observed_sections
    assert "reduced depression symptoms" in "\n".join(span.text for span in result.spans)
    assert all("10.1000/" not in span.text for span in result.spans)
    assert all(
        snapshot.normalized_text[span.start : span.end] == span.text for span in result.spans
    )


def test_inline_numbered_methods_results_and_references_are_separate_sections() -> None:
    text = (
        "Article: Depression symptoms after treatment. 2. Methods: We randomized 72 adults "
        "with depression to an intervention or usual care. 3. Results: The intervention "
        "reduced symptoms by 4 points at week 12. References: 1. Smith et al. (2019), "
        "DOI 10.1000/1."
    )
    snapshot, result = _build(text)
    preview = "\n".join(span.text for span in result.spans)

    assert {"methods", "results", "bibliography"}.issubset(result.observed_sections)
    assert "randomized 72 adults" in preview
    assert "reduced symptoms by 4 points" in preview
    assert "10.1000/1" not in preview
    assert all(
        snapshot.normalized_text[span.start : span.end] == span.text for span in result.spans
    )


def test_windows_do_not_bridge_skipped_reference_lines() -> None:
    text = (
        "Methods\nWe randomized adults with depression to intervention or usual care.\n"
        "1. Smith et al. (2020). Randomized treatment and depression outcomes. "
        "DOI 10.1000/reference\n"
        "The intervention was compared with usual care for symptom change.\n"
        "Results\nThe intervention reduced depression symptoms by 3 points.\n"
    )
    _snapshot, result = _build(text)

    assert result.outcome == "completed"
    assert all("10.1000/reference" not in span.text for span in result.spans)
    assert all("Smith et al." not in span.text for span in result.spans)


def test_long_paragraph_preview_windows_keep_neighboring_sentences_contiguous() -> None:
    filler = "This sentence describes the general study setting without adding an outcome. "
    text = (
        "Results\nThe intervention reduced depression symptoms by 3 points at week 8. "
        "The difference versus usual care was 2 points and the confidence interval excluded zero. "
        + filler
        * 35
    )
    snapshot, result = _build(text)
    preview = "\n".join(span.text for span in result.spans)

    assert "The intervention reduced depression symptoms" in preview
    assert "The difference versus usual care" in preview
    assert all(len(span.text) <= 1200 for span in result.spans)
    assert all(
        snapshot.normalized_text[span.start : span.end] == span.text for span in result.spans
    )


def test_excluded_chrome_does_not_make_capture_usable() -> None:
    text = (
        "Results\nBrowse issues, submit a manuscript, or read our conclusion. "
        "Sign in to access the latest articles."
    )
    _snapshot, result = _build(text)

    assert result.outcome == "unavailable"
    assert result.capture_usable is False


def test_short_unicode_result_is_substantive_and_claim_relevant() -> None:
    text = "Results: L’intervention a réduit les symptômes en huit semaines."
    _snapshot, result = _build(text)

    assert result.outcome == "completed"
    assert result.capture_usable is True
    assert "réduit les symptômes" in "\n".join(span.text for span in result.spans)


@pytest.mark.parametrize(
    ("text", "claim", "components"),
    [
        (
            "摘要\n一项随机对照试验纳入了120名抑郁症患者。干预组的抑郁症状评分下降了4分。\n"
            "方法\n研究人员将参与者随机分配到干预组和对照组。\n"
            "结果\n干预组的抑郁症状明显减少。",
            "干预减少抑郁症状。",
            ("干预", "抑郁症状"),
        ),
        (
            "摘要\n一項隨機對照試驗納入了120名抑鬱症患者。干預組的抑鬱症狀評分下降了4分。\n"
            "材料與方法\n研究人員將參與者隨機分配到干預組和對照組。\n"
            "結果\n干預組的抑鬱症狀明顯減少。",
            "干預減少抑鬱症狀。",
            ("干預", "抑鬱症狀"),
        ),
    ],
)
def test_unspaced_chinese_study_preserves_relevant_exact_windows(
    text: str, claim: str, components: tuple[str, ...]
) -> None:
    snapshot, result = _build(text, claim=claim, components=components)

    assert result.capture_usable is True
    assert result.outcome == "completed"
    assert result.relevance_score > 0
    assert {"abstract", "methods", "results"}.issubset(result.observed_sections)
    assert any(span.section == "results" for span in result.spans)
    assert any(components[0] in span.text for span in result.spans)
    result.require_snapshot(snapshot)


def test_unrelated_chinese_capture_is_usable_without_inventing_relevance() -> None:
    text = (
        "方法\n研究人员将120名高血压患者随机分配到运动组和对照组。\n"
        "结果\n研究发现运动组的血压明显下降，而对照组的血压没有变化。"
    )
    snapshot, result = _build(text)

    assert result.capture_usable is True
    assert result.outcome == "unavailable"
    assert result.relevance_score == 0
    assert build_capture_windows(snapshot)


def test_unheaded_chinese_research_retains_capture_windows() -> None:
    text = "研究人员将120名高血压患者随机分配到运动组和对照组，并测量了治疗前后的血压变化。"
    snapshot, result = _build(text)

    assert result.capture_usable is True
    assert result.relevance_score == 0
    windows = build_capture_windows(snapshot)
    assert windows
    assert all(snapshot.normalized_text[span.start : span.end] == span.text for span in windows)


@pytest.mark.parametrize(
    "text",
    [
        "结果\n研究研究研究研究研究研究研究研究研究研究研究研究。",
        "结果\n首页目录登录注册订阅帮助联系账户隐私设置网站导航。",
        "结果\n访问被拒绝，请登录账户查看研究结果和患者症状信息。",
        "参考文献\n研究人员将120名患者随机分配到干预组和对照组。",
    ],
)
def test_chinese_chrome_repetition_and_references_are_not_usable(text: str) -> None:
    snapshot, result = _build(text)

    assert result.capture_usable is False
    assert result.outcome == "unavailable"
    assert build_capture_windows(snapshot) == ()


def test_capture_windows_preserve_substantive_unrelated_context_without_claim_score() -> None:
    text = (
        "Methods\nWe randomized 160 adults with hypertension to supervised exercise "
        "or usual care.\n"
        "Results\nSystolic blood pressure fell by 8 mmHg after 16 weeks.\n"
        "References\n1. Smith et al. (2020). DOI 10.1000/irrelevant\n"
    )
    snapshot, result = _build(text)

    windows = build_capture_windows(snapshot)
    assert result.outcome == "unavailable"
    assert result.capture_usable is True
    assert windows
    assert any("randomized 160 adults" in span.text for span in windows)
    assert all("10.1000/irrelevant" not in span.text for span in windows)
    assert all(span.omitted_before == (span.start > 0) for span in windows)
    assert all(span.omitted_after == (span.end < len(text)) for span in windows)
