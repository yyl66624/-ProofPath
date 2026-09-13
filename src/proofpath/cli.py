"""Command-line interface.

Commands that need no credentials - `parse`, `search`, `demo`, `plan`, `audit` -
work fully offline, so the system can be exercised and demonstrated without a
live model. Only `check` calls the API.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Sequence

from . import __version__, config
from .actions import Action, ActionGate, DryRunExecutor, summarize_plan
from .audit import AuditLog
from .errors import (
    AuditChainBrokenError,
    ConfirmationRequiredError,
    ProofPathError,
)
from .parsers import docling_available, load_document
from .render import render_report
from .retrieval import Bm25Index
from .text import collapse_for_display
from .verifier import verify_report

_EXIT_OK = 0
_EXIT_ERROR = 1
_EXIT_BLOCKED = 3


def _parse_profile(pairs: Sequence[str] | None) -> dict[str, str]:
    """Turn `--profile 学历=硕士` repeats into a dict."""
    profile: dict[str, str] = {}
    for pair in pairs or ():
        key, separator, value = pair.partition("=")
        if not separator or not key.strip():
            raise ProofPathError(f"--profile expects key=value, got {pair!r}")
        profile[key.strip()] = value.strip()
    return profile


def _load(path: str) -> Any:
    document = load_document(path)
    print(
        f"已解析 {Path(document.source_path).name}"
        f"(解析器 {document.parser},{len(document.pages)} 页,{len(document.chunks)} 个片段)",
        file=sys.stderr,
    )
    return document


def _report_and_render(report: Any, document: Any, audit: AuditLog | None) -> int:
    verified, summary = verify_report(report, document)
    if audit is not None:
        audit.append(
            "report_verified",
            doc_id=document.doc_id,
            counts=verified.counts(),
            citations=summary.total_citations,
            rejected=summary.rejected,
            downgraded=summary.downgraded_conditions,
        )
    print(render_report(verified, summary))
    return _EXIT_OK


def cmd_parse(args: argparse.Namespace) -> int:
    document = _load(args.file)
    for number, page in enumerate(document.pages, start=1):
        preview = collapse_for_display(page, limit=100)
        print(f"第 {number} 页 ({len(page)} 字): {preview}")
    return _EXIT_OK


def cmd_search(args: argparse.Namespace) -> int:
    document = _load(args.file)
    index = Bm25Index.from_document(document)
    hits = index.search(args.query, top_k=args.top_k)
    if not hits:
        print("没有检索到相关片段。")
        return _EXIT_OK
    for rank, hit in enumerate(hits, start=1):
        print(f"{rank}. [第 {hit.chunk.page} 页] score={hit.score:.3f}")
        print(f"   {collapse_for_display(hit.chunk.text, limit=140)}")
    return _EXIT_OK


def cmd_check(args: argparse.Namespace) -> int:
    from .reasoner import ClaudeReasoner

    document = _load(args.file)
    index = Bm25Index.from_document(document)
    audit = AuditLog(path=Path(args.audit)) if args.audit else None
    if audit is not None:
        audit.append("document_parsed", doc_id=document.doc_id, parser=document.parser)

    reasoner = ClaudeReasoner(model=args.model)
    report = reasoner.analyze(
        args.question,
        document,
        index,
        profile=_parse_profile(args.profile),
        top_k=args.top_k,
    )
    return _report_and_render(report, document, audit)


def cmd_demo(args: argparse.Namespace) -> int:
    from .demo import DEMO_QUESTION, EXAMPLE_POLICY, ScriptedReasoner

    source = args.file or str(EXAMPLE_POLICY)
    document = _load(source)
    index = Bm25Index.from_document(document)
    audit = AuditLog(path=Path(args.audit)) if args.audit else None
    if audit is not None:
        audit.append("document_parsed", doc_id=document.doc_id, parser=document.parser)

    print("(离线演示:使用预设回答,不调用模型)\n", file=sys.stderr)
    report = ScriptedReasoner().analyze(args.question or DEMO_QUESTION, document, index)
    return _report_and_render(report, document, audit)


def cmd_plan(args: argparse.Namespace) -> int:
    """Show an execution plan's risk classification without running it."""
    actions = tuple(
        Action(kind=kind, target=target)
        for kind, target in (
            ("navigate", args.url),
            ("fill", "申请人姓名"),
            ("fill", "身份证号"),
            ("upload", "学历学位证书"),
            ("submit", "提交申请"),
        )
    )
    tally = summarize_plan(actions)
    print("执行计划:")
    for position, action in enumerate(actions, start=1):
        mark = "需确认" if action.requires_confirmation else "可自动"
        print(f"  {position}. [{action.risk.value:<11}] {mark}  {action.describe()}")
    print(f"\n风险统计: {tally}")

    gate = ActionGate(DryRunExecutor())  # deny_all: sensitive steps stop here
    try:
        gate.run_plan(actions)
    except ConfirmationRequiredError as exc:
        print(f"\n已在敏感操作前停止: {exc}")
        print("真实执行需要逐项确认;当前为演练模式,未进行任何提交。")
        return _EXIT_BLOCKED
    return _EXIT_OK


def cmd_audit(args: argparse.Namespace) -> int:
    log = AuditLog.load(args.file)  # load() verifies the chain
    print(f"审计链校验通过:{len(log)} 条记录")
    for entry in log:
        print(f"  #{entry.index} {entry.timestamp} {entry.event} {entry.payload}")
    return _EXIT_OK


def cmd_doctor(_: argparse.Namespace) -> int:
    """Report which optional capabilities are available."""
    from importlib.util import find_spec

    print(f"ProofPath {__version__}")
    print(f"默认模型: {config.MODEL}")
    checks = (
        ("pypdf (PDF 解析)", find_spec("pypdf") is not None, "必需,已随主依赖安装"),
        ("docling (DOCX/图片/OCR)", docling_available(), "uv pip install -e '.[docling]'"),
        ("browser-use (表单自动填写)", find_spec("browser_use") is not None,
         "uv pip install -e '.[browser]' && playwright install chromium"),
        ("anthropic (模型调用)", find_spec("anthropic") is not None, "必需,已随主依赖安装"),
    )
    for name, available, hint in checks:
        status = "可用" if available else "未安装"
        suffix = "" if available else f"  -> {hint}"
        print(f"  [{status:<6}] {name}{suffix}")
    return _EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="proofpath",
        description="把政策文件变成有原文证据、可核验的办事结论",
    )
    parser.add_argument("--version", action="version", version=f"proofpath {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_parse = sub.add_parser("parse", help="解析文档并按页预览")
    p_parse.add_argument("file")
    p_parse.set_defaults(func=cmd_parse)

    p_search = sub.add_parser("search", help="只做检索,不调用模型")
    p_search.add_argument("file")
    p_search.add_argument("-q", "--query", required=True)
    p_search.add_argument("-k", "--top-k", type=int, default=config.DEFAULT_TOP_K)
    p_search.set_defaults(func=cmd_search)

    p_check = sub.add_parser("check", help="判定资格并核验引用(需要模型凭证)")
    p_check.add_argument("file")
    p_check.add_argument("-q", "--question", required=True)
    p_check.add_argument("-p", "--profile", action="append", metavar="KEY=VALUE")
    p_check.add_argument("-k", "--top-k", type=int, default=config.DEFAULT_TOP_K)
    p_check.add_argument("--model", default=config.MODEL)
    p_check.add_argument("--audit", metavar="PATH", help="写入审计链文件")
    p_check.set_defaults(func=cmd_check)

    p_demo = sub.add_parser("demo", help="离线演示完整链路(含证据核验拦截)")
    p_demo.add_argument("file", nargs="?", help="默认使用内置示例政策")
    p_demo.add_argument("-q", "--question")
    p_demo.add_argument("--audit", metavar="PATH")
    p_demo.set_defaults(func=cmd_demo)

    p_plan = sub.add_parser("plan", help="展示表单执行计划的风险分级(演练,不执行)")
    p_plan.add_argument("url")
    p_plan.set_defaults(func=cmd_plan)

    p_audit = sub.add_parser("audit", help="校验审计链完整性")
    p_audit.add_argument("file")
    p_audit.set_defaults(func=cmd_audit)

    p_doctor = sub.add_parser("doctor", help="检查可选组件安装情况")
    p_doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ConfirmationRequiredError as exc:
        print(f"操作已阻止: {exc}", file=sys.stderr)
        return _EXIT_BLOCKED
    except AuditChainBrokenError as exc:
        print(f"审计链校验失败: {exc}", file=sys.stderr)
        return _EXIT_ERROR
    except ProofPathError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return _EXIT_ERROR
    except KeyboardInterrupt:
        print("\n已取消。", file=sys.stderr)
        return _EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
