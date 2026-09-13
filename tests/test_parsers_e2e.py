"""Parser tests plus an end-to-end run over the bundled example policy."""
from __future__ import annotations

import pytest

from proofpath.cli import build_parser, main
from proofpath.demo import DEMO_QUESTION, EXAMPLE_POLICY, ScriptedReasoner
from proofpath.errors import DocumentLoadError, NoParserAvailableError
from proofpath.models import (
    Citation,
    CitationStatus,
    ConditionStatus,
    ConditionVerdict,
    EligibilityReport,
    VerifiedCitation,
)
from proofpath.parsers import load_document
from proofpath.render import render_report
from proofpath.retrieval import Bm25Index
from proofpath.verifier import verify_report


class TestLoadDocument:
    def test_plaintext_roundtrip(self, tmp_path) -> None:
        path = tmp_path / "notice.txt"
        path.write_text("第一条 测试内容。", encoding="utf-8")
        doc = load_document(path)
        assert doc.parser == "plaintext"
        assert len(doc.pages) == 1
        assert doc.chunks

    def test_explicit_page_breaks_split_pages(self, tmp_path) -> None:
        path = tmp_path / "two.txt"
        path.write_text("第一页内容\n--- PAGE BREAK ---\n第二页内容", encoding="utf-8")
        doc = load_document(path)
        assert len(doc.pages) == 2
        assert doc.page_text(2) is not None and "第二页" in doc.page_text(2)

    def test_chunks_carry_page_anchors(self, tmp_path) -> None:
        """Every chunk must know its page, or citations cannot name one."""
        path = tmp_path / "two.txt"
        path.write_text("甲" * 500 + "\n--- PAGE BREAK ---\n" + "乙" * 500, encoding="utf-8")
        doc = load_document(path)
        assert {c.page for c in doc.chunks} == {1, 2}
        assert all(c.page >= 1 for c in doc.chunks)

    def test_doc_id_is_content_addressed(self, tmp_path) -> None:
        a = tmp_path / "a.txt"
        b = tmp_path / "a2.txt"
        a.write_text("同样的内容", encoding="utf-8")
        b.write_text("同样的内容", encoding="utf-8")
        # Same bytes -> same hash suffix, even from a different filename.
        assert load_document(a).doc_id.split("-")[-1] == load_document(b).doc_id.split("-")[-1]

    def test_page_text_out_of_range(self, tmp_path) -> None:
        path = tmp_path / "one.txt"
        path.write_text("内容", encoding="utf-8")
        doc = load_document(path)
        assert doc.page_text(2) is None
        assert doc.page_text(0) is None

    def test_missing_file(self, tmp_path) -> None:
        with pytest.raises(DocumentLoadError, match="not a file"):
            load_document(tmp_path / "nope.txt")

    def test_empty_file(self, tmp_path) -> None:
        path = tmp_path / "empty.txt"
        path.write_bytes(b"")
        with pytest.raises(DocumentLoadError, match="empty"):
            load_document(path)

    def test_whitespace_only_file(self, tmp_path) -> None:
        path = tmp_path / "blank.txt"
        path.write_text("   \n\n  ", encoding="utf-8")
        with pytest.raises(DocumentLoadError, match="no extractable text"):
            load_document(path)

    def test_invalid_utf8_text_is_rejected_as_damaged(self, tmp_path) -> None:
        path = tmp_path / "damaged.txt"
        path.write_bytes(b"policy\xff\xfecontent")
        with pytest.raises(DocumentLoadError, match="UTF-8"):
            load_document(path)

    def test_unsupported_type(self, tmp_path) -> None:
        path = tmp_path / "data.xyz"
        path.write_text("content", encoding="utf-8")
        with pytest.raises(NoParserAvailableError, match="unsupported file type"):
            load_document(path)

    def test_rich_type_without_docling_explains_the_extra(self, tmp_path) -> None:
        from proofpath.parsers import docling_available

        if docling_available():
            pytest.skip("docling is installed; the guidance path does not apply")
        path = tmp_path / "form.docx"
        path.write_bytes(b"PK\x03\x04fake")
        with pytest.raises(NoParserAvailableError, match="docling"):
            load_document(path)


class TestExamplePolicy:
    def test_example_policy_parses(self) -> None:
        doc = load_document(EXAMPLE_POLICY)
        assert len(doc.pages) == 2
        # Both pages fit inside one chunk each at the configured chunk size;
        # what matters is that every page is represented.
        assert {chunk.page for chunk in doc.chunks} == {1, 2}

    def test_retrieval_finds_subsidy_amount(self) -> None:
        doc = load_document(EXAMPLE_POLICY)
        hits = Bm25Index.from_document(doc).search("硕士每月补贴多少钱")
        assert hits
        assert any("1500" in h.chunk.text for h in hits)


class TestEndToEnd:
    """The scripted report carries planted defects; verification must catch them."""

    def test_verifier_catches_planted_defects(self) -> None:
        doc = load_document(EXAMPLE_POLICY)
        index = Bm25Index.from_document(doc)
        raw = ScriptedReasoner().analyze(DEMO_QUESTION, doc, index)
        verified, summary = verify_report(raw, doc)

        # The fabricated "追补3个月" clause must not survive as MET.
        fabricated = next(v for v in verified.verdicts if "追补" in v.condition)
        assert fabricated.status is ConditionStatus.UNKNOWN

        # The 2-character "合同" quote is not evidence.
        too_short = next(v for v in verified.verdicts if "劳动合同期限" in v.condition)
        assert too_short.status is ConditionStatus.UNKNOWN
        assert too_short.citations[0].status is CitationStatus.TOO_SHORT

        # Genuine citations survive.
        education = next(v for v in verified.verdicts if "学历要求" in v.condition)
        assert education.status is ConditionStatus.MET
        assert education.citations[0].status is CitationStatus.VERIFIED

        assert summary.downgraded_conditions == 2
        assert summary.verified >= 3

    def test_report_is_not_conclusive_when_input_is_missing(self) -> None:
        doc = load_document(EXAMPLE_POLICY)
        raw = ScriptedReasoner().analyze(DEMO_QUESTION, doc, Bm25Index.from_document(doc))
        verified, _ = verify_report(raw, doc)
        assert not verified.is_conclusive
        assert "住房租赁合同网签备案的具体日期" in verified.missing_inputs

    def test_render_marks_downgraded_conditions(self) -> None:
        doc = load_document(EXAMPLE_POLICY)
        raw = ScriptedReasoner().analyze(DEMO_QUESTION, doc, Bm25Index.from_document(doc))
        verified, summary = verify_report(raw, doc)
        output = render_report(verified, summary)
        assert "原文未明确" in output
        assert "已核验" in output
        assert "不是最终资格认定" in output


class TestCli:
    def test_demo_exits_clean(self, capsys) -> None:
        assert main(["demo"]) == 0
        assert "逐条判定" in capsys.readouterr().out

    def test_parse_command(self, capsys) -> None:
        assert main(["parse", str(EXAMPLE_POLICY)]) == 0
        assert "第 1 页" in capsys.readouterr().out

    def test_search_command(self, capsys) -> None:
        assert main(["search", str(EXAMPLE_POLICY), "-q", "社保"]) == 0
        assert "score=" in capsys.readouterr().out

    def test_plan_stops_before_submission(self, capsys) -> None:
        """Exit code 3 signals 'stopped at a sensitive action', not failure."""
        assert main(["plan", "https://example.gov/apply"]) == 3
        out = capsys.readouterr().out
        assert "SENSITIVE" in out
        assert "未进行任何提交" in out

    def test_doctor_command(self, capsys) -> None:
        assert main(["doctor"]) == 0
        output = capsys.readouterr().out
        assert "deepseek-flash" in output
        assert "openai (DeepSeek 模型调用)" in output
        assert "anthropic" not in output.lower()

    def test_check_model_default_is_resolved_from_environment(self) -> None:
        args = build_parser().parse_args(
            ["check", str(EXAMPLE_POLICY), "-q", "年龄条件"]
        )
        assert args.model is None

    def test_doctor_reports_environment_model(self, monkeypatch, capsys) -> None:
        monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
        assert main(["doctor"]) == 0
        assert "默认模型: deepseek-v4-pro" in capsys.readouterr().out

    def test_check_uses_safe_service_summary_and_hides_model_checklist(
        self, monkeypatch, capsys
    ) -> None:
        import proofpath.reasoner as reasoner_module

        class FakeLiveReasoner:
            def __init__(self, **_: object) -> None:
                pass

            def analyze(self, question, document, index, *, profile=None, top_k=6):
                return EligibilityReport(
                    doc_id=document.doc_id,
                    question=question,
                    verdicts=(
                        ConditionVerdict(
                            condition="学历要求",
                            status=ConditionStatus.MET,
                            rationale="模型理由",
                            citations=(
                                VerifiedCitation(
                                    citation=Citation(
                                        page=1,
                                        quote="具有全日制本科及以上学历",
                                    ),
                                    status=CitationStatus.NOT_FOUND,
                                    coverage=0.0,
                                ),
                            ),
                        ),
                    ),
                    checklist=("模型材料",),
                    summary="模型保证一定符合",
                )

        monkeypatch.setattr(reasoner_module, "DeepSeekReasoner", FakeLiveReasoner)

        assert main(
            ["check", str(EXAMPLE_POLICY), "-q", "硕士学历要求"]
        ) == 0
        output = capsys.readouterr().out
        assert output.startswith("证据核验结果：")
        assert "模型保证一定符合" not in output
        assert "模型材料" not in output

    def test_audit_roundtrip_via_cli(self, tmp_path, capsys) -> None:
        audit_path = tmp_path / "run.jsonl"
        assert main(["demo", "--audit", str(audit_path)]) == 0
        capsys.readouterr()
        assert main(["audit", str(audit_path)]) == 0
        assert "审计链校验通过" in capsys.readouterr().out

    def test_missing_file_reports_error(self, tmp_path, capsys) -> None:
        assert main(["parse", str(tmp_path / "nope.txt")]) == 1
        assert "错误" in capsys.readouterr().err
