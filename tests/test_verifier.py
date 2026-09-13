"""Tests for the citation verifier - the component that must not be fooled."""
from __future__ import annotations

import pytest

from proofpath.models import (
    Citation,
    CitationStatus,
    ConditionStatus,
    ConditionVerdict,
    Document,
    EligibilityReport,
    VerifiedCitation,
)
from proofpath.verifier import PageTextCache, verify_citation, verify_report

PAGE_ONE = "第三条 申请人应当同时符合以下条件:(一)具有全日制本科及以上学历;(二)年龄不超过35周岁。"
PAGE_TWO = "第五条 补贴标准:博士每月2000元;硕士研究生或副高级职称,每月1500元。"


@pytest.fixture
def document() -> Document:
    return Document(
        doc_id="doc-test",
        source_path="/tmp/policy.txt",
        parser="plaintext",
        pages=(PAGE_ONE, PAGE_TWO),
        chunks=(),
    )


@pytest.fixture
def pages(document: Document) -> PageTextCache:
    return PageTextCache(document)


def _unverified(page: int, quote: str) -> VerifiedCitation:
    return VerifiedCitation(Citation(page=page, quote=quote), CitationStatus.NOT_FOUND, 0.0)


class TestVerifyCitation:
    def test_exact_quote_verifies(self, pages: PageTextCache) -> None:
        result = verify_citation(Citation(1, "年龄不超过35周岁"), pages)
        assert result.status is CitationStatus.VERIFIED
        assert result.coverage == 1.0

    def test_whitespace_and_newlines_are_ignored(self, pages: PageTextCache) -> None:
        """PDF extraction inserts stray whitespace; that must not break a match."""
        result = verify_citation(Citation(1, "年龄不超过\n  35 周岁"), pages)
        assert result.status is CitationStatus.VERIFIED

    def test_fullwidth_halfwidth_normalizes(self, pages: PageTextCache) -> None:
        result = verify_citation(Citation(2, "每月１５００元"), pages)
        assert result.status is CitationStatus.VERIFIED

    def test_fabricated_quote_is_rejected(self, pages: PageTextCache) -> None:
        result = verify_citation(
            Citation(2, "首次申请的人员可以追补此前3个月的补贴"), pages
        )
        assert result.status is CitationStatus.NOT_FOUND
        assert result.coverage < 0.85

    def test_quote_from_wrong_page_is_rejected(self, pages: PageTextCache) -> None:
        """Real text, but attributed to the wrong page, is still not evidence."""
        result = verify_citation(Citation(1, "硕士研究生或副高级职称"), pages)
        assert result.status is CitationStatus.NOT_FOUND

    def test_nonexistent_page(self, pages: PageTextCache) -> None:
        assert verify_citation(Citation(99, "任何内容"), pages).status is CitationStatus.BAD_PAGE

    def test_page_zero_is_invalid(self, pages: PageTextCache) -> None:
        assert verify_citation(Citation(0, "任何内容"), pages).status is CitationStatus.BAD_PAGE

    def test_short_quote_is_not_evidence(self, pages: PageTextCache) -> None:
        """A 2-char fragment matches almost anything, so it cannot support a claim."""
        result = verify_citation(Citation(1, "条件"), pages)
        assert result.status is CitationStatus.TOO_SHORT

    def test_near_miss_is_partial(self, pages: PageTextCache) -> None:
        """One wrong character in a long quote reads as a slip, not a fabrication."""
        result = verify_citation(Citation(1, "具有全日制本科及以上学历X"), pages)
        assert result.status is CitationStatus.PARTIAL
        assert 0.85 <= result.coverage < 1.0

    def test_empty_quote_is_too_short(self, pages: PageTextCache) -> None:
        assert verify_citation(Citation(1, ""), pages).status is CitationStatus.TOO_SHORT

    def test_cache_returns_consistent_results(self, pages: PageTextCache) -> None:
        first = verify_citation(Citation(1, "年龄不超过35周岁"), pages)
        second = verify_citation(Citation(1, "年龄不超过35周岁"), pages)
        assert first == second


class TestVerifyReport:
    def _report(self, *verdicts: ConditionVerdict, doc_id: str = "doc-test") -> EligibilityReport:
        return EligibilityReport(doc_id=doc_id, question="q", verdicts=verdicts)

    def test_met_with_good_citation_survives(self, document: Document) -> None:
        report = self._report(
            ConditionVerdict(
                condition="学历",
                status=ConditionStatus.MET,
                rationale="符合",
                citations=(_unverified(1, "具有全日制本科及以上学历"),),
            )
        )
        verified, summary = verify_report(report, document)
        assert verified.verdicts[0].status is ConditionStatus.MET
        assert summary.verified == 1
        assert summary.downgraded_conditions == 0

    def test_met_with_fabricated_citation_is_downgraded(self, document: Document) -> None:
        report = self._report(
            ConditionVerdict(
                condition="追补条款",
                status=ConditionStatus.MET,
                rationale="可以追补",
                citations=(_unverified(2, "首次申请的人员可以追补此前3个月的补贴"),),
            )
        )
        verified, summary = verify_report(report, document)
        assert verified.verdicts[0].status is ConditionStatus.UNKNOWN
        assert summary.downgraded_conditions == 1
        assert "证据核验未通过" in verified.verdicts[0].rationale

    def test_met_with_no_citation_is_downgraded(self, document: Document) -> None:
        report = self._report(
            ConditionVerdict(
                condition="无引用",
                status=ConditionStatus.MET,
                rationale="凭印象",
                citations=(),
            )
        )
        verified, _ = verify_report(report, document)
        assert verified.verdicts[0].status is ConditionStatus.UNKNOWN

    def test_any_unverifiable_citation_sinks_the_verdict(self, document: Document) -> None:
        """A compound claim must not pass on the strength of its true half.

        "硕士1500元" is real; "可追补3个月" is invented. Accepting the verdict
        because one quote checks out would tell the user they are owed money the
        policy never promises.
        """
        report = self._report(
            ConditionVerdict(
                condition="混合引用",
                status=ConditionStatus.MET,
                rationale="部分真实",
                citations=(
                    _unverified(2, "硕士研究生或副高级职称,每月1500元"),
                    _unverified(2, "首次申请的人员可以追补此前3个月的补贴"),
                ),
            )
        )
        verified, summary = verify_report(report, document)
        assert verified.verdicts[0].status is ConditionStatus.UNKNOWN
        assert summary.verified == 1
        assert summary.rejected == 1
        # The rationale must name the page that failed, not just say "failed".
        assert "第 2 页" in verified.verdicts[0].rationale

    def test_unmet_is_also_downgraded_when_unsupported(self, document: Document) -> None:
        """A negative claim needs evidence just as much as a positive one."""
        report = self._report(
            ConditionVerdict(
                condition="不满足项",
                status=ConditionStatus.UNMET,
                rationale="不符合",
                citations=(_unverified(1, "本细则自发布之日起施行满两年"),),
            )
        )
        verified, _ = verify_report(report, document)
        assert verified.verdicts[0].status is ConditionStatus.UNKNOWN

    def test_needs_input_is_not_downgraded(self, document: Document) -> None:
        """NEEDS_INPUT asserts nothing about the document, so it needs no evidence."""
        report = self._report(
            ConditionVerdict(
                condition="备案日期",
                status=ConditionStatus.NEEDS_INPUT,
                rationale="缺少日期",
                citations=(),
                missing_info=("备案日期",),
            )
        )
        verified, summary = verify_report(report, document)
        assert verified.verdicts[0].status is ConditionStatus.NEEDS_INPUT
        assert summary.downgraded_conditions == 0

    def test_input_report_is_not_mutated(self, document: Document) -> None:
        original = ConditionVerdict(
            condition="学历",
            status=ConditionStatus.MET,
            rationale="符合",
            citations=(_unverified(2, "不存在的句子完全是编造出来的内容"),),
        )
        report = self._report(original)
        verified, _ = verify_report(report, document)
        assert verified.verdicts[0].status is ConditionStatus.UNKNOWN
        assert report.verdicts[0].status is ConditionStatus.MET
        assert original.status is ConditionStatus.MET

    def test_report_metadata_is_preserved(self, document: Document) -> None:
        report = EligibilityReport(
            doc_id="doc-test",
            question="我能申请吗",
            verdicts=(),
            checklist=("身份证",),
            summary="摘要",
        )
        verified, summary = verify_report(report, document)
        assert verified.question == "我能申请吗"
        assert verified.checklist == ("身份证",)
        assert verified.summary == "摘要"
        assert summary.total_citations == 0
        assert summary.rejection_rate == 0.0

    def test_is_conclusive_requires_all_definite(self, document: Document) -> None:
        report = self._report(
            ConditionVerdict(
                condition="a",
                status=ConditionStatus.MET,
                rationale="",
                citations=(_unverified(1, "具有全日制本科及以上学历"),),
            ),
            ConditionVerdict(
                condition="b", status=ConditionStatus.NEEDS_INPUT, rationale=""
            ),
        )
        verified, _ = verify_report(report, document)
        assert not verified.is_conclusive

    def test_counts_tally(self, document: Document) -> None:
        report = self._report(
            ConditionVerdict(
                condition="a",
                status=ConditionStatus.MET,
                rationale="",
                citations=(_unverified(1, "具有全日制本科及以上学历"),),
            ),
            ConditionVerdict(condition="b", status=ConditionStatus.NEEDS_INPUT, rationale=""),
        )
        verified, _ = verify_report(report, document)
        counts = verified.counts()
        assert counts["MET"] == 1
        assert counts["NEEDS_INPUT"] == 1
        assert counts["UNMET"] == 0

    def test_missing_inputs_deduplicated(self, document: Document) -> None:
        report = self._report(
            ConditionVerdict(
                condition="a",
                status=ConditionStatus.NEEDS_INPUT,
                rationale="",
                missing_info=("备案日期", "合同期限"),
            ),
            ConditionVerdict(
                condition="b",
                status=ConditionStatus.NEEDS_INPUT,
                rationale="",
                missing_info=("备案日期",),
            ),
        )
        verified, _ = verify_report(report, document)
        assert verified.missing_inputs == ("备案日期", "合同期限")
