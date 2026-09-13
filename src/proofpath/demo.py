"""Offline demo path.

Runs the whole pipeline - parse, retrieve, verify, render - without credentials,
using a scripted report instead of a live model call. The script deliberately
contains one fabricated citation and one over-short one, because the point worth
demonstrating is not that the model answers, but that the system catches the
model when it is wrong.

Nothing here is used by the live path; it exists for demos and integration tests.
"""
from __future__ import annotations

from pathlib import Path

from .models import (
    Citation,
    CitationStatus,
    ConditionStatus,
    ConditionVerdict,
    Document,
    EligibilityReport,
    VerifiedCitation,
)

EXAMPLE_POLICY = Path(__file__).resolve().parents[2] / "examples" / "policy.txt"

DEMO_QUESTION = "我硕士毕业,28岁,在本市工作了8个月,社保交了8个月,名下没有房,已经网签备案了租房合同。我能申请多少补贴?需要准备什么?"

DEMO_PROFILE = {
    "学历": "硕士研究生",
    "年龄": "28岁",
    "社保缴纳": "本市连续8个月",
    "自有住房": "无",
    "租赁备案": "已完成网签备案",
}


def _unverified(page: int, quote: str) -> VerifiedCitation:
    """Wrap a raw claim the way the reasoner does - unverified until checked."""
    return VerifiedCitation(
        citation=Citation(page=page, quote=quote),
        status=CitationStatus.NOT_FOUND,
        coverage=0.0,
    )


def scripted_report(document: Document) -> EligibilityReport:
    """A report shaped exactly like the model's, with planted defects.

    Verdict 1-3 cite real text and should survive verification.
    Verdict 4 cites a plausible-sounding sentence that is not in the document -
      it must be downgraded to UNKNOWN.
    Verdict 5 cites a two-character fragment - too short to be evidence.
    """
    return EligibilityReport(
        doc_id=document.doc_id,
        question=DEMO_QUESTION,
        # Written in the model's own confident voice - it does not know its
        # citations are about to be checked. The rendered report will contradict
        # part of this, which is the point of the demo.
        summary=(
            "按你提供的信息,补贴标准对应每月1500元,主要条件均已满足,"
            "另有一项申请时限需要你补充确认。"
        ),
        verdicts=(
            ConditionVerdict(
                condition="学历要求:全日制本科及以上学历,或中级及以上职称",
                status=ConditionStatus.MET,
                rationale="你是硕士研究生,符合本科及以上的学历要求。",
                citations=(
                    _unverified(1, "具有全日制本科及以上学历,或具有中级及以上专业技术职称"),
                ),
            ),
            ConditionVerdict(
                condition="年龄要求:申请时不超过35周岁",
                status=ConditionStatus.MET,
                rationale="你28岁,在35周岁上限之内。",
                citations=(_unverified(1, "申请时年龄不超过35周岁"),),
            ),
            ConditionVerdict(
                condition="社保要求:在本市连续缴纳社会保险满6个月",
                status=ConditionStatus.MET,
                rationale="你已连续缴纳8个月,超过6个月的下限。",
                citations=(
                    _unverified(1, "在本市连续缴纳\n社会保险满6个月"),
                ),
            ),
            ConditionVerdict(
                condition="补贴标准:硕士研究生每月1500元,且首次申请可追补3个月",
                status=ConditionStatus.MET,
                rationale="按学历分档,硕士对应每月1500元,并可追补此前3个月。",
                citations=(
                    # First quote is real; second is fabricated - no such
                    # sentence exists anywhere in the document.
                    _unverified(2, "硕士研究生或副高级职称,每月1500元"),
                    _unverified(2, "首次申请的人员可以追补此前3个月的补贴"),
                ),
            ),
            ConditionVerdict(
                condition="劳动合同期限不少于1年",
                status=ConditionStatus.MET,
                rationale="你与本市用人单位已建立劳动关系。",
                # Two characters - matches almost any page, so it is not evidence.
                citations=(_unverified(1, "合同"),),
            ),
            ConditionVerdict(
                condition="申请时限:租赁合同备案之日起6个月内提出申请",
                status=ConditionStatus.NEEDS_INPUT,
                rationale="原文对申请时限有硬性要求,但你没有说明备案的具体日期。",
                citations=(
                    _unverified(2, "申请人应当在租赁合同备案之日起6个月内提出申请,逾期不再受理"),
                ),
                missing_info=("住房租赁合同网签备案的具体日期",),
            ),
        ),
        checklist=(
            "租房补贴申请表(在线填写并打印签字)",
            "身份证正反面复印件",
            "硕士学历学位证书(国外学历需教育部留学服务中心认证书)",
            "劳动合同复印件",
            "近6个月社会保险缴纳记录",
            "住房租赁合同网签备案证明",
            "本人名下本市银行账户信息",
        ),
    )


class ScriptedReasoner:
    """Drop-in stand-in for the live model reasoner in demos and tests."""

    def analyze(self, question: str, document: Document, index: object, **_: object):
        report = scripted_report(document)
        # Honour the caller's question so the rendered output stays coherent.
        return EligibilityReport(
            doc_id=report.doc_id,
            question=question,
            verdicts=report.verdicts,
            checklist=report.checklist,
            summary=report.summary,
        )
