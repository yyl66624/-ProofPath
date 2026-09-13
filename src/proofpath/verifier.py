"""Citation verification - the project's trust boundary.

The model proposes a verdict per condition and cites a page plus a quote. None
of that is believed. Every quote is checked against the actual text of the page
it names, and any definite verdict that survives on unverifiable evidence is
forcibly downgraded to UNKNOWN.

This runs entirely offline and deterministically: it is the part of the system
that does not depend on a model behaving well.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import config
from .models import (
    Citation,
    CitationStatus,
    ConditionStatus,
    ConditionVerdict,
    Document,
    EligibilityReport,
    VerifiedCitation,
)
from .text import coverage_ratio, normalize

_DEFINITE = frozenset({ConditionStatus.MET, ConditionStatus.UNMET})


class PageTextCache:
    """Normalized page text, computed once per document.

    Normalization is not free and every citation needs it, so caching turns an
    O(citations x page_size) cost into O(pages x page_size).
    """

    __slots__ = ("_document", "_cache")

    def __init__(self, document: Document) -> None:
        self._document = document
        self._cache: dict[int, str | None] = {}

    def get(self, page: int) -> str | None:
        """Normalized text for a 1-indexed page, or None if the page is absent."""
        if page not in self._cache:
            raw = self._document.page_text(page)
            self._cache[page] = None if raw is None else normalize(raw)
        return self._cache[page]


def verify_citation(citation: Citation, pages: PageTextCache) -> VerifiedCitation:
    """Check one quote against the page it claims to come from."""
    page_text = pages.get(citation.page)
    if page_text is None:
        return VerifiedCitation(citation, CitationStatus.BAD_PAGE, 0.0)

    needle = normalize(citation.quote)
    if len(needle) < config.MIN_QUOTE_CHARS:
        # Short fragments match by accident; treating them as evidence would
        # let "符合" verify against any policy page.
        return VerifiedCitation(citation, CitationStatus.TOO_SHORT, 0.0)

    if needle in page_text:
        return VerifiedCitation(citation, CitationStatus.VERIFIED, 1.0)

    coverage = coverage_ratio(needle, page_text)
    status = (
        CitationStatus.PARTIAL
        if coverage >= config.PARTIAL_THRESHOLD
        else CitationStatus.NOT_FOUND
    )
    return VerifiedCitation(citation, status, round(coverage, 4))


def verify_verdict(verdict: ConditionVerdict, pages: PageTextCache) -> ConditionVerdict:
    """Verify a verdict's citations and downgrade it if the evidence fails.

    NEEDS_INPUT and UNKNOWN are not downgraded - they make no factual claim
    about the document, so they need no evidence to be honest.
    """
    checked = tuple(
        verify_citation(vc.citation, pages) for vc in verdict.citations
    )
    verified = verdict.__class__(
        condition=verdict.condition,
        status=verdict.status,
        rationale=verdict.rationale,
        citations=checked,
        missing_info=verdict.missing_info,
    )

    if verdict.status not in _DEFINITE:
        return verified

    if not checked:
        return verified.downgraded("该结论没有提供任何原文引用。")

    # Every citation must check out, not merely one. A compound claim that pairs
    # a real quote with a fabricated one would otherwise pass on the strength of
    # its true half while asserting the false half.
    unverifiable = verified.unverifiable_citations
    if unverifiable:
        detail = "、".join(
            f"第 {vc.citation.page} 页（{vc.status.value}，覆盖率 {vc.coverage:.0%}）"
            for vc in unverifiable
        )
        return verified.downgraded(f"以下引用无法在原文中定位：{detail}。")

    return verified


@dataclass(frozen=True, slots=True)
class VerificationSummary:
    """Aggregate outcome of verifying a whole report."""

    total_citations: int
    verified: int
    partial: int
    rejected: int
    downgraded_conditions: int

    @property
    def rejection_rate(self) -> float:
        if not self.total_citations:
            return 0.0
        return self.rejected / self.total_citations


def verify_report(
    report: EligibilityReport, document: Document
) -> tuple[EligibilityReport, VerificationSummary]:
    """Verify every citation in a report, returning a new report plus a summary.

    The input report is never mutated - the returned one is what should be shown
    to the user, and it is the only version safe to display.
    """
    pages = PageTextCache(document)

    checked_verdicts: list[ConditionVerdict] = []
    downgraded = 0
    for verdict in report.verdicts:
        result = verify_verdict(verdict, pages)
        if verdict.status in _DEFINITE and result.status is ConditionStatus.UNKNOWN:
            downgraded += 1
        checked_verdicts.append(result)

    statuses = [vc.status for v in checked_verdicts for vc in v.citations]
    summary = VerificationSummary(
        total_citations=len(statuses),
        verified=sum(1 for s in statuses if s is CitationStatus.VERIFIED),
        partial=sum(1 for s in statuses if s is CitationStatus.PARTIAL),
        rejected=sum(
            1
            for s in statuses
            if s
            in (
                CitationStatus.NOT_FOUND,
                CitationStatus.BAD_PAGE,
                CitationStatus.TOO_SHORT,
            )
        ),
        downgraded_conditions=downgraded,
    )

    verified_report = EligibilityReport(
        doc_id=report.doc_id,
        question=report.question,
        verdicts=tuple(checked_verdicts),
        checklist=report.checklist,
        summary=report.summary,
    )
    return verified_report, summary
