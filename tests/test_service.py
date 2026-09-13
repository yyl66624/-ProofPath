"""Application-service tests for the verified analysis boundary."""
from __future__ import annotations

from typing import Any

import pytest

from proofpath.errors import ReportDocumentMismatchError
from proofpath.errors import MalformedModelOutputError
from proofpath.models import (
    Chunk,
    Citation,
    CitationStatus,
    ConditionStatus,
    ConditionVerdict,
    Document,
    EligibilityReport,
    VerifiedCitation,
)
from proofpath.service import analyze_document


def _unverified(page: int, quote: str) -> VerifiedCitation:
    return VerifiedCitation(
        citation=Citation(page=page, quote=quote),
        status=CitationStatus.NOT_FOUND,
        coverage=0.0,
    )


@pytest.fixture
def document() -> Document:
    page = "申请条件：申请时年龄不超过35周岁。"
    return Document(
        doc_id="policy-1234",
        source_path="/tmp/policy.txt",
        parser="plaintext",
        pages=(page,),
        chunks=(Chunk(chunk_id="policy-1234-p1-c0", page=1, text=page),),
    )


class _RecordingReasoner:
    def __init__(self, report: EligibilityReport) -> None:
        self.report = report
        self.calls: list[dict[str, Any]] = []

    def analyze(
        self,
        question: str,
        document: Document,
        index: object,
        *,
        profile: dict[str, Any] | None = None,
        top_k: int,
    ) -> EligibilityReport:
        self.calls.append(
            {
                "question": question,
                "document": document,
                "index": index,
                "profile": profile,
                "top_k": top_k,
            }
        )
        return self.report


def _report(
    document_id: str,
    *,
    quote: str = "申请时年龄不超过35周岁",
    status: ConditionStatus = ConditionStatus.MET,
    missing_info: tuple[str, ...] = (),
    summary: str = "模型声称申请人一定符合。",
    checklist: tuple[str, ...] = ("模型编造的材料",),
) -> EligibilityReport:
    return EligibilityReport(
        doc_id=document_id,
        question="我28岁，符合年龄要求吗？",
        verdicts=(
            ConditionVerdict(
                condition="申请时年龄不超过35周岁",
                status=status,
                rationale="用户年龄为28岁，低于35岁。",
                citations=(_unverified(1, quote),),
                missing_info=missing_info,
            ),
        ),
        summary=summary,
        checklist=checklist,
    )


def test_fabricated_model_citation_is_downgraded_before_return(
    document: Document,
) -> None:
    """Removing verification from the service must make this test fail."""
    reasoner = _RecordingReasoner(
        _report(document.doc_id, quote="首次申请可以追补此前三个月补贴")
    )

    outcome = analyze_document("追补政策", document, reasoner)

    assert outcome.report.verdicts[0].status is ConditionStatus.UNKNOWN
    assert outcome.verification.downgraded_conditions == 1
    assert "用户年龄为28岁" not in outcome.report.verdicts[0].rationale
    assert outcome.report.verdicts[0].rationale.startswith("证据核验未通过：")


def test_unverified_summary_and_checklist_are_not_exposed(document: Document) -> None:
    """Returning model prose or materials directly must make this test fail."""
    reasoner = _RecordingReasoner(_report(document.doc_id))

    outcome = analyze_document("年龄要求", document, reasoner)

    assert outcome.report.summary == (
        "证据核验结果：满足 1 项，不满足 0 项，需补充信息 0 项，原文未明确 0 项。"
        "当前仅核对引用位置，结论语义仍需人工复核。"
    )
    assert "一定符合" not in outcome.report.summary
    assert outcome.report.checklist == ()


def test_report_for_another_document_is_rejected(document: Document) -> None:
    """Removing the document identity guard must make this test fail."""
    reasoner = _RecordingReasoner(_report("another-document"))

    with pytest.raises(ReportDocumentMismatchError) as caught:
        analyze_document("学历要求", document, reasoner)

    assert caught.value.expected_doc_id == document.doc_id
    assert caught.value.actual_doc_id == "another-document"


def test_needs_input_without_missing_fields_is_rejected(document: Document) -> None:
    """Removing cross-field validation must make this test fail."""
    reasoner = _RecordingReasoner(
        _report(document.doc_id, status=ConditionStatus.NEEDS_INPUT)
    )

    with pytest.raises(MalformedModelOutputError, match="NEEDS_INPUT"):
        analyze_document("年龄要求", document, reasoner)


def test_verified_outcome_preserves_inputs_and_forwards_options(
    document: Document,
) -> None:
    """Dropping caller profile or top-k must make this contract test fail."""
    reasoner = _RecordingReasoner(_report(document.doc_id))
    profile = {"年龄": "28"}

    outcome = analyze_document(
        "年龄要求",
        document,
        reasoner,
        profile=profile,
        top_k=3,
    )

    assert outcome.report.verdicts[0].status is ConditionStatus.MET
    assert outcome.report.verdicts[0].citations[0].status is CitationStatus.VERIFIED
    assert outcome.verification.verified == 1
    assert outcome.requires_human_review is True
    assert len(reasoner.calls) == 1
    assert reasoner.calls[0]["question"] == "年龄要求"
    assert reasoner.calls[0]["document"] is document
    assert reasoner.calls[0]["profile"] == profile
    assert reasoner.calls[0]["top_k"] == 3


def test_definite_verdict_requires_review_until_semantic_support_is_checked(
    document: Document,
) -> None:
    """Claiming semantic safety before C-8 exists must make this test fail."""
    reasoner = _RecordingReasoner(_report(document.doc_id))

    outcome = analyze_document("年龄要求", document, reasoner)

    assert outcome.requires_human_review is True
    assert "语义仍需人工复核" in outcome.report.summary


def test_empty_report_has_explicit_non_conclusive_summary(document: Document) -> None:
    """Returning four unexplained zero counts must make this test fail."""
    reasoner = _RecordingReasoner(
        EligibilityReport(
            doc_id=document.doc_id,
            question="天气怎么样",
            verdicts=(),
            summary="模型没有检索到相关内容。",
        )
    )

    outcome = analyze_document("天气怎么样", document, reasoner)

    assert outcome.report.summary == "未形成可核验的条件判断。"
    assert outcome.requires_human_review is False
