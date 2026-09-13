"""Terminal rendering of a verified report.

Kept separate from the CLI so the formatting can be unit-tested without argv
plumbing, and separate from the domain types so they stay presentation-free.
"""
from __future__ import annotations

from .models import CitationStatus, ConditionStatus, EligibilityReport
from .text import collapse_for_display
from .verifier import VerificationSummary

_STATUS_LABEL = {
    ConditionStatus.MET: "[满足]",
    ConditionStatus.UNMET: "[不满足]",
    ConditionStatus.NEEDS_INPUT: "[待补充]",
    ConditionStatus.UNKNOWN: "[原文未明确]",
}

_CITATION_LABEL = {
    CitationStatus.VERIFIED: "已核验",
    CitationStatus.PARTIAL: "基本一致",
    CitationStatus.NOT_FOUND: "未能在该页找到",
    CitationStatus.TOO_SHORT: "引用过短，不足为证",
    CitationStatus.BAD_PAGE: "页码不存在",
}


def render_report(report: EligibilityReport, summary: VerificationSummary) -> str:
    """Full report as plain text."""
    lines: list[str] = []

    if report.summary:
        lines.append(report.summary)
        lines.append("")

    if not report.verdicts:
        lines.append("没有可判定的条件。")
        return "\n".join(lines)

    lines.append("## 逐条判定")
    lines.append("")
    for position, verdict in enumerate(report.verdicts, start=1):
        lines.append(f"{position}. {_STATUS_LABEL[verdict.status]} {verdict.condition}")
        if verdict.rationale:
            for rationale_line in verdict.rationale.splitlines():
                lines.append(f"   {rationale_line}")
        for vc in verdict.citations:
            label = _CITATION_LABEL[vc.status]
            quote = collapse_for_display(vc.citation.quote, limit=70)
            suffix = "" if vc.status is CitationStatus.VERIFIED else f" ({vc.coverage:.0%})"
            lines.append(f"   └ 第 {vc.citation.page} 页 · {label}{suffix}：“{quote}”")
        for item in verdict.missing_info:
            lines.append(f"   ? 需要你提供：{item}")
        lines.append("")

    missing = report.missing_inputs
    if missing:
        lines.append("## 还需要你确认")
        lines.extend(f"- {item}" for item in missing)
        lines.append("")

    if report.checklist:
        lines.append("## 材料清单")
        lines.extend(f"- {item}" for item in report.checklist)
        lines.append("")

    lines.append("## 证据核验")
    lines.append(
        f"引用 {summary.total_citations} 处："
        f"已核验 {summary.verified}，基本一致 {summary.partial}，"
        f"未通过 {summary.rejected}"
    )
    if summary.downgraded_conditions:
        lines.append(
            f"有 {summary.downgraded_conditions} 条结论因引用无法核验，已降级为“原文未明确”。"
        )
    if not report.is_conclusive:
        lines.append("本结果不是最终资格认定，请以受理窗口的答复为准。")

    return "\n".join(lines)
