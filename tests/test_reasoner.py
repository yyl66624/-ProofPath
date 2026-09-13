"""Reasoner tests with a fake client - no credentials, no network.

The reasoner's contract is narrow but safety-relevant: whatever the model
returns, the citations it produces must come back marked unverified, so that a
report which somehow skips the verifier can never look like it passed.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from proofpath.errors import (
    MalformedModelOutputError,
    ModelRefusedError,
    ReasonerUnavailableError,
)
from proofpath.models import CitationStatus, ConditionStatus, Document
from proofpath.parsers import load_document
from proofpath.reasoner import ClaudeReasoner, _build_user_prompt, _parse_payload
from proofpath.retrieval import Bm25Index

WELL_FORMED = {
    "summary": "初步判断如下。",
    "conditions": [
        {
            "condition": "学历要求",
            "status": "MET",
            "rationale": "硕士符合本科及以上。",
            "citations": [{"page": 1, "quote": "具有全日制本科及以上学历"}],
            "missing_info": [],
        },
        {
            "condition": "备案日期",
            "status": "NEEDS_INPUT",
            "rationale": "缺少日期。",
            "citations": [],
            "missing_info": ["网签备案日期"],
        },
    ],
    "checklist": ["身份证", "学历学位证书"],
}


class _FakeBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _FakeResponse:
    def __init__(self, payload: Any, stop_reason: str = "end_turn") -> None:
        body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        self.content = [_FakeBlock(body)]
        self.stop_reason = stop_reason
        self.stop_details = None


class _FakeMessages:
    def __init__(self, response: Any) -> None:
        self._response = response
        self.last_kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> Any:
        self.last_kwargs = kwargs
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class _FakeClient:
    """Mimics the `client.beta.messages.create` surface the reasoner uses."""

    def __init__(self, response: Any) -> None:
        self.messages = _FakeMessages(response)
        self.beta = self

    @property
    def last_kwargs(self) -> dict[str, Any]:
        return self.messages.last_kwargs


@pytest.fixture
def document() -> Document:
    from proofpath.demo import EXAMPLE_POLICY

    return load_document(EXAMPLE_POLICY)


@pytest.fixture
def index(document: Document) -> Bm25Index:
    return Bm25Index.from_document(document)


class TestParsePayload:
    def test_parses_conditions_and_checklist(self) -> None:
        report = _parse_payload(json.dumps(WELL_FORMED), "q", "doc-1")
        assert len(report.verdicts) == 2
        assert report.verdicts[0].status is ConditionStatus.MET
        assert report.verdicts[1].missing_info == ("网签备案日期",)
        assert report.checklist == ("身份证", "学历学位证书")
        assert report.doc_id == "doc-1"

    def test_citations_start_unverified(self) -> None:
        """The critical invariant: nothing is trusted before the verifier runs."""
        report = _parse_payload(json.dumps(WELL_FORMED), "q", "doc-1")
        citation = report.verdicts[0].citations[0]
        assert citation.status is CitationStatus.NOT_FOUND
        assert citation.coverage == 0.0
        assert not citation.is_trustworthy

    def test_rejects_invalid_json(self) -> None:
        with pytest.raises(MalformedModelOutputError, match="not valid JSON"):
            _parse_payload("{oops", "q", "doc-1")

    def test_rejects_missing_conditions_field(self) -> None:
        with pytest.raises(MalformedModelOutputError, match="conditions"):
            _parse_payload(json.dumps({"summary": "x"}), "q", "doc-1")

    def test_rejects_unknown_status(self) -> None:
        payload = {
            "summary": "",
            "checklist": [],
            "conditions": [
                {
                    "condition": "c",
                    "status": "PROBABLY",
                    "rationale": "",
                    "citations": [],
                    "missing_info": [],
                }
            ],
        }
        with pytest.raises(MalformedModelOutputError, match="invalid condition status"):
            _parse_payload(json.dumps(payload), "q", "doc-1")

    def test_skips_malformed_citation_entries(self) -> None:
        """A citation without a page is dropped rather than crashing the run."""
        payload = {
            "summary": "",
            "checklist": [],
            "conditions": [
                {
                    "condition": "c",
                    "status": "UNKNOWN",
                    "rationale": "",
                    "citations": [{"quote": "缺少页码"}, {"page": 1, "quote": "完整引用"}],
                    "missing_info": [],
                }
            ],
        }
        report = _parse_payload(json.dumps(payload), "q", "doc-1")
        assert len(report.verdicts[0].citations) == 1

    def test_rejects_non_object_condition(self) -> None:
        payload = {"summary": "", "checklist": [], "conditions": ["nope"]}
        with pytest.raises(MalformedModelOutputError, match="not an object"):
            _parse_payload(json.dumps(payload), "q", "doc-1")


class TestBuildUserPrompt:
    def test_includes_question_and_context(self) -> None:
        prompt = _build_user_prompt("我能申请吗", "[第 1 页]\n条件如下", None)
        assert "我能申请吗" in prompt
        assert "[第 1 页]" in prompt
        assert "尚未提供任何个人信息" in prompt

    def test_renders_profile_deterministically(self) -> None:
        """Sorted keys keep the prompt prefix stable for cache reuse."""
        first = _build_user_prompt("q", "ctx", {"学历": "硕士", "年龄": "28"})
        second = _build_user_prompt("q", "ctx", {"年龄": "28", "学历": "硕士"})
        assert first == second


class TestAnalyze:
    def test_returns_report_from_model_output(self, document, index) -> None:
        client = _FakeClient(_FakeResponse(WELL_FORMED))
        report = ClaudeReasoner(client=client).analyze("硕士补贴多少", document, index)
        assert len(report.verdicts) == 2
        assert report.doc_id == document.doc_id

    def test_sends_expected_request_shape(self, document, index) -> None:
        client = _FakeClient(_FakeResponse(WELL_FORMED))
        ClaudeReasoner(client=client).analyze("硕士补贴多少", document, index)
        kwargs = client.last_kwargs
        assert kwargs["model"] == "claude-opus-5"
        assert kwargs["thinking"] == {"type": "adaptive"}
        assert kwargs["output_config"]["format"]["type"] == "json_schema"
        # Refusal fallback: the scalar "default" form pairs with the 07-01 beta.
        assert kwargs["fallbacks"] == "default"
        assert kwargs["betas"] == ["server-side-fallback-2026-07-01"]
        # The stable system prompt is cached; the volatile question is not.
        assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}

    def test_question_reaches_the_prompt(self, document, index) -> None:
        client = _FakeClient(_FakeResponse(WELL_FORMED))
        ClaudeReasoner(client=client).analyze("社保要交几个月", document, index)
        assert "社保要交几个月" in client.last_kwargs["messages"][0]["content"]

    def test_refusal_raises(self, document, index) -> None:
        # The question must overlap the document lexically, or the retrieval
        # short-circuit returns before the model is ever consulted.
        client = _FakeClient(_FakeResponse(WELL_FORMED, stop_reason="refusal"))
        with pytest.raises(ModelRefusedError):
            ClaudeReasoner(client=client).analyze("硕士补贴多少", document, index)

    def test_no_retrieval_hits_short_circuits(self, document, index) -> None:
        """With no lexical overlap, answering would mean inventing content."""
        client = _FakeClient(_FakeResponse(WELL_FORMED))
        report = ClaudeReasoner(client=client).analyze(
            "tomorrow weather forecast", document, index
        )
        assert report.verdicts == ()
        assert "未能在文档中检索到" in report.summary
        assert client.last_kwargs == {}  # the model was never called

    def test_missing_text_block_raises(self, document, index) -> None:
        class _NoText:
            content: list[Any] = []
            stop_reason = "end_turn"
            stop_details = None

        client = _FakeClient(_NoText())
        with pytest.raises(MalformedModelOutputError, match="no text block"):
            ClaudeReasoner(client=client).analyze("硕士补贴", document, index)

    def test_api_errors_surface_as_unavailable(self, document, index) -> None:
        import anthropic
        import httpx2

        request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
        error = anthropic.RateLimitError(
            "slow down",
            response=httpx2.Response(429, request=request),
            body=None,
        )
        client = _FakeClient(error)
        with pytest.raises(ReasonerUnavailableError, match="rate limited"):
            ClaudeReasoner(client=client).analyze("硕士补贴", document, index)

    def test_verifier_catches_fabrication_from_the_model_path(self, document, index) -> None:
        """End-to-end: a fabricated quote from the model is downgraded."""
        from proofpath.verifier import verify_report

        payload = {
            "summary": "",
            "checklist": [],
            "conditions": [
                {
                    "condition": "追补条款",
                    "status": "MET",
                    "rationale": "可以追补",
                    "citations": [
                        {"page": 2, "quote": "首次申请的人员可以追补此前3个月的补贴"}
                    ],
                    "missing_info": [],
                }
            ],
        }
        client = _FakeClient(_FakeResponse(payload))
        raw = ClaudeReasoner(client=client).analyze("能追补吗", document, index)
        verified, summary = verify_report(raw, document)
        assert verified.verdicts[0].status is ConditionStatus.UNKNOWN
        assert summary.downgraded_conditions == 1
