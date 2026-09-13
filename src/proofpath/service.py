"""Framework-neutral application services.

HTTP, persistence, and background execution belong in adapters around this
module. The boundary here has one safety-critical promise: callers receive only
a report that has been matched to the requested document and citation-verified.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Protocol

from . import config
from .errors import MalformedModelOutputError, ReportDocumentMismatchError
from .models import ConditionStatus, Document, EligibilityReport
from .retrieval import Bm25Index
from .verifier import VerificationSummary, verify_report


class Reasoner(Protocol):
    """The analysis behavior required by the application service."""

    def analyze(
        self,
        question: str,
        document: Document,
        index: Bm25Index,
        *,
        profile: dict[str, Any] | None = None,
        top_k: int = config.DEFAULT_TOP_K,
    ) -> EligibilityReport:
        """Propose an unverified report for one document."""
        ...


@dataclass(frozen=True, slots=True)
class AnalysisOutcome:
    """A location-verified report and whether semantic review is still required."""

    report: EligibilityReport
    verification: VerificationSummary
    requires_human_review: bool


def _validate_proposed_report(report: EligibilityReport) -> None:
    for position, verdict in enumerate(report.verdicts, start=1):
        if verdict.status is ConditionStatus.NEEDS_INPUT and not verdict.missing_info:
            raise MalformedModelOutputError(
                f"condition {position} is NEEDS_INPUT but has no missing_info"
            )


def _safe_summary(report: EligibilityReport, *, requires_human_review: bool) -> str:
    if not report.verdicts:
        return "未形成可核验的条件判断。"

    counts = report.counts()
    summary = (
        f"证据核验结果：满足 {counts['MET']} 项，不满足 {counts['UNMET']} 项，"
        f"需补充信息 {counts['NEEDS_INPUT']} 项，原文未明确 {counts['UNKNOWN']} 项。"
    )
    if requires_human_review:
        summary += "当前仅核对引用位置，结论语义仍需人工复核。"
    return summary


def analyze_document(
    question: str,
    document: Document,
    reasoner: Reasoner,
    *,
    profile: dict[str, Any] | None = None,
    top_k: int = config.DEFAULT_TOP_K,
) -> AnalysisOutcome:
    """Retrieve, reason, enforce document identity, and verify every citation."""
    index = Bm25Index.from_document(document)
    proposed = reasoner.analyze(
        question,
        document,
        index,
        profile=profile,
        top_k=top_k,
    )
    if proposed.doc_id != document.doc_id:
        raise ReportDocumentMismatchError(document.doc_id, proposed.doc_id)
    _validate_proposed_report(proposed)

    report, verification = verify_report(proposed, document)
    requires_human_review = any(
        verdict.status in (ConditionStatus.MET, ConditionStatus.UNMET)
        for verdict in report.verdicts
    )
    safe_report = replace(
        report,
        summary=_safe_summary(
            report,
            requires_human_review=requires_human_review,
        ),
        checklist=(),
    )
    return AnalysisOutcome(
        report=safe_report,
        verification=verification,
        requires_human_review=requires_human_review,
    )
