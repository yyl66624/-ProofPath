"""DeepSeek reasoner tests with a fake OpenAI-compatible client.

No test uses credentials or the network. The fake stops at the provider
boundary while parsing, retrieval, retry decisions, and citation trust state
remain real production behavior.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx2
import openai
import pytest

import proofpath.reasoner as reasoner_module
from proofpath.errors import (
    MalformedModelOutputError,
    ModelRefusedError,
    ProofPathError,
    ReasonerUnavailableError,
)
from proofpath.models import CitationStatus, ConditionStatus, Document
from proofpath.parsers import load_document
from proofpath.reasoner import _build_user_prompt, _parse_payload
from proofpath.retrieval import Bm25Index

DeepSeekReasoner = getattr(reasoner_module, "DeepSeekReasoner", None)

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


def _response(
    payload: Any,
    *,
    finish_reason: str = "stop",
    refusal: str | None = None,
    reasoning_content: str = "",
) -> Any:
    body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    message = SimpleNamespace(
        content=body,
        refusal=refusal,
        reasoning_content=reasoning_content,
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason=finish_reason)]
    )


class _FakeCompletions:
    def __init__(self, outcomes: list[Any]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        if callable(outcome):
            return outcome()
        return outcome


class _FakeClient:
    """Mimics only ``client.chat.completions.create``."""

    def __init__(self, *outcomes: Any) -> None:
        self.completions = _FakeCompletions(list(outcomes))
        self.chat = self

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self.completions.calls


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
        """Removing NOT_FOUND would let an unverified model quote look trusted."""
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

    def test_rejects_malformed_citation_entries(self) -> None:
        payload = {
            "summary": "",
            "checklist": [],
            "conditions": [
                {
                    "condition": "c",
                    "status": "UNKNOWN",
                    "rationale": "",
                    "citations": [
                        {"quote": "缺少页码"},
                        {"page": 1, "quote": "完整引用"},
                    ],
                    "missing_info": [],
                }
            ],
        }
        with pytest.raises(MalformedModelOutputError, match="citation"):
            _parse_payload(json.dumps(payload), "q", "doc-1")

    def test_rejects_non_object_condition(self) -> None:
        payload = {"summary": "", "checklist": [], "conditions": ["nope"]}
        with pytest.raises(MalformedModelOutputError, match="not an object"):
            _parse_payload(json.dumps(payload), "q", "doc-1")

    @pytest.mark.parametrize(
        "payload",
        [
            [],
            {"summary": [], "conditions": [], "checklist": []},
            {"summary": "", "conditions": {}, "checklist": []},
            {"summary": "", "conditions": [], "checklist": "身份证"},
            {"summary": "", "conditions": [], "checklist": [1]},
        ],
    )
    def test_rejects_wrong_top_level_types(self, payload: Any) -> None:
        with pytest.raises(MalformedModelOutputError):
            _parse_payload(json.dumps(payload), "q", "doc-1")

    @pytest.mark.parametrize(
        "mutation",
        [
            {"condition": 1},
            {"rationale": []},
            {"citations": {}},
            {"missing_info": "备案日期"},
            {"missing_info": [1]},
        ],
    )
    def test_rejects_wrong_condition_field_types(self, mutation: dict[str, Any]) -> None:
        payload = json.loads(json.dumps(WELL_FORMED, ensure_ascii=False))
        payload["conditions"][0].update(mutation)
        with pytest.raises(MalformedModelOutputError, match="condition"):
            _parse_payload(json.dumps(payload), "q", "doc-1")

    def test_rejects_non_integer_citation_page(self) -> None:
        payload = json.loads(json.dumps(WELL_FORMED, ensure_ascii=False))
        payload["conditions"][0]["citations"][0]["page"] = "1"
        with pytest.raises(MalformedModelOutputError, match="citation"):
            _parse_payload(json.dumps(payload), "q", "doc-1")


class TestBuildUserPrompt:
    def test_includes_question_and_context(self) -> None:
        prompt = _build_user_prompt("我能申请吗", "[第 1 页]\n条件如下", None)
        assert "我能申请吗" in prompt
        assert "[第 1 页]" in prompt
        assert "尚未提供任何个人信息" in prompt

    def test_renders_profile_deterministically(self) -> None:
        first = _build_user_prompt("q", "ctx", {"学历": "硕士", "年龄": "28"})
        second = _build_user_prompt("q", "ctx", {"年龄": "28", "学历": "硕士"})
        assert first == second


class TestConstruction:
    def test_deepseek_reasoner_is_available(self) -> None:
        assert DeepSeekReasoner is not None

    def test_uses_deepseek_environment_and_disables_sdk_retries(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake_openai(**kwargs: Any) -> _FakeClient:
            captured.update(kwargs)
            return _FakeClient(_response(WELL_FORMED))

        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")
        monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://deepseek.test")
        monkeypatch.setattr(openai, "OpenAI", fake_openai)

        DeepSeekReasoner()

        assert captured == {
            "api_key": "test-only-key",
            "base_url": "https://deepseek.test",
            "max_retries": 0,
            "timeout": 120.0,
        }

    def test_missing_credentials_are_reported_without_secret_details(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        with pytest.raises(ReasonerUnavailableError, match="DEEPSEEK_API_KEY"):
            DeepSeekReasoner()

    def test_rejects_token_budget_below_verified_floor(self) -> None:
        with pytest.raises(ValueError, match="at least 2000"):
            DeepSeekReasoner(client=_FakeClient(), max_tokens=1999)


class TestAnalyze:
    def test_returns_report_from_model_output(self, document, index) -> None:
        client = _FakeClient(_response(WELL_FORMED))
        report = DeepSeekReasoner(client=client).analyze("硕士补贴多少", document, index)
        assert len(report.verdicts) == 2
        assert report.doc_id == document.doc_id

    def test_sends_deepseek_request_shape(self, document, index) -> None:
        client = _FakeClient(_response(WELL_FORMED))
        DeepSeekReasoner(client=client).analyze("硕士补贴多少", document, index)
        request = client.calls[0]
        assert request["model"] == "deepseek-flash"
        assert request["max_tokens"] == 3000
        assert request["response_format"] == {"type": "json_object"}
        assert request["extra_body"] == {"thinking": {"type": "disabled"}}
        assert request["messages"][0]["role"] == "system"
        system_prompt = request["messages"][0]["content"]
        assert "JSON" in system_prompt.upper()
        assert "材料清单" in system_prompt
        assert "独立条件" in system_prompt

    def test_question_reaches_the_user_message(self, document, index) -> None:
        client = _FakeClient(_response(WELL_FORMED))
        DeepSeekReasoner(client=client).analyze("社保要交几个月", document, index)
        assert "社保要交几个月" in client.calls[0]["messages"][1]["content"]

    def test_only_message_content_is_parsed(self, document, index) -> None:
        client = _FakeClient(
            _response(WELL_FORMED, reasoning_content="{this is not response JSON")
        )
        report = DeepSeekReasoner(client=client).analyze("硕士补贴", document, index)
        assert report.verdicts[0].condition == "学历要求"

    def test_refusal_raises_without_retry(self, document, index) -> None:
        client = _FakeClient(
            _response("", finish_reason="content_filter", refusal="无法处理该请求")
        )
        with pytest.raises(ModelRefusedError, match="无法处理"):
            DeepSeekReasoner(client=client).analyze("硕士补贴多少", document, index)
        assert len(client.calls) == 1

    def test_no_retrieval_hits_short_circuits(self, document, index) -> None:
        client = _FakeClient(_response(WELL_FORMED))
        report = DeepSeekReasoner(client=client).analyze(
            "tomorrow weather forecast", document, index
        )
        assert report.verdicts == ()
        assert "未能在文档中检索到" in report.summary
        assert client.calls == []

    def test_empty_length_response_retries_then_reports_truncation(
        self, document, index
    ) -> None:
        client = _FakeClient(
            _response("", finish_reason="length"),
            _response("", finish_reason="length"),
            _response("", finish_reason="length"),
        )
        with pytest.raises(MalformedModelOutputError) as raised:
            DeepSeekReasoner(client=client).analyze("硕士补贴", document, index)
        assert type(raised.value).__name__ == "ModelOutputTruncatedError"
        assert "truncated" in str(raised.value)
        assert [call["model"] for call in client.calls] == [
            "deepseek-flash",
            "deepseek-flash",
            "deepseek-v4-pro",
        ]

    def test_nonempty_invalid_json_retries_then_reports_structure_error(
        self, document, index
    ) -> None:
        client = _FakeClient(
            _response("not-json"), _response("not-json"), _response("not-json")
        )
        with pytest.raises(MalformedModelOutputError, match="not valid JSON") as raised:
            DeepSeekReasoner(client=client).analyze("硕士补贴", document, index)
        assert type(raised.value) is MalformedModelOutputError
        assert len(client.calls) == 3

    def test_retryable_failures_are_bounded_and_fallback_to_pro_model(
        self, document, index
    ) -> None:
        request = httpx2.Request("POST", "https://api.deepseek.com/chat/completions")
        timeout = openai.APITimeoutError(request=request)
        rate_limit = openai.RateLimitError(
            "slow down",
            response=httpx2.Response(429, request=request),
            body=None,
        )
        client = _FakeClient(timeout, rate_limit, _response(WELL_FORMED))

        report = DeepSeekReasoner(client=client).analyze("硕士补贴", document, index)

        assert report.verdicts
        assert [call["model"] for call in client.calls] == [
            "deepseek-flash",
            "deepseek-flash",
            "deepseek-v4-pro",
        ]

    def test_cancellation_between_attempts_prevents_further_model_calls(
        self, document, index
    ) -> None:
        request = httpx2.Request("POST", "https://api.deepseek.com/chat/completions")
        holder: dict[str, Any] = {}

        def first_attempt() -> Any:
            holder["reasoner"].cancel()
            raise openai.APITimeoutError(request=request)

        client = _FakeClient(first_attempt, _response(WELL_FORMED))
        reasoner = DeepSeekReasoner(client=client)
        holder["reasoner"] = reasoner

        with pytest.raises(ProofPathError) as raised:
            reasoner.analyze("硕士补贴", document, index)

        assert type(raised.value).__name__ == "AnalysisCancelledError"
        assert len(client.calls) == 1

    @pytest.mark.parametrize(
        ("provider_error", "public_type", "message"),
        [
            ("timeout", "ModelTimeoutError", "timed out"),
            ("rate_limit", "ModelRateLimitedError", "rate limited"),
            ("connection", "ReasonerUnavailableError", "network error"),
        ],
    )
    def test_exhausted_provider_errors_have_stable_public_types(
        self, provider_error, public_type, message, document, index
    ) -> None:
        request = httpx2.Request("POST", "https://api.deepseek.com/chat/completions")
        factories = {
            "timeout": lambda: openai.APITimeoutError(request=request),
            "rate_limit": lambda: openai.RateLimitError(
                "slow down",
                response=httpx2.Response(429, request=request),
                body=None,
            ),
            "connection": lambda: openai.APIConnectionError(request=request),
        }
        client = _FakeClient(*(factories[provider_error]() for _ in range(3)))

        with pytest.raises(ReasonerUnavailableError, match=message) as raised:
            DeepSeekReasoner(client=client).analyze("硕士补贴", document, index)

        assert type(raised.value).__name__ == public_type
        assert len(client.calls) == 3

    def test_authentication_failure_is_not_retried(self, document, index) -> None:
        request = httpx2.Request("POST", "https://api.deepseek.com/chat/completions")
        auth_error = openai.AuthenticationError(
            "invalid credentials",
            response=httpx2.Response(401, request=request),
            body=None,
        )
        client = _FakeClient(auth_error)

        with pytest.raises(ReasonerUnavailableError, match="authentication failed"):
            DeepSeekReasoner(client=client).analyze("硕士补贴", document, index)

        assert len(client.calls) == 1

    def test_verifier_catches_fabrication_from_the_model_path(self, document, index) -> None:
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
        client = _FakeClient(_response(payload))
        raw = DeepSeekReasoner(client=client).analyze("能追补吗", document, index)
        verified, summary = verify_report(raw, document)
        assert verified.verdicts[0].status is ConditionStatus.UNKNOWN
        assert summary.downgraded_conditions == 1
