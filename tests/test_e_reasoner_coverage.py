"""Additional reasoner tests to fill coverage gaps (reasoner.py 84% → target 95%+).

Coverage gaps targeted:
- _build_user_prompt with and without profile (lines 103-110)
- ClaudeReasoner.__init__ credential validation (lines 172-179)
- API error handling: APIStatusError, APIConnectionError (lines 239-249)
- Response with no text block (line 262)

T07 alignment: model timeout, no auth, quota exceeded, abnormal output.

NOTE (2026-09-13): Disabled after the DeepSeek migration (PR #21).
This file was written against the Anthropic SDK (`anthropic.Anthropic`,
`client.beta.messages.create`, `APIStatusError`, `stop_reason == "refusal"`).
P05 replaced the reasoner with `DeepSeekReasoner`, which uses the
OpenAI-compatible interface (`client.chat.completions.create`,
`openai.APIStatusError`, refusal signaled differently). The new behavior is
covered by `tests/test_reasoner.py`. Re-enable once equivalent T07 coverage
for DeepSeekReasoner is in place.
"""
from __future__ import annotations

import pytest

pytest.skip(
    "Anthropic-only coverage tests; superseded by tests/test_reasoner.py after DeepSeek migration.",
    allow_module_level=True,
)

WELL_FORMED = {
    "summary": "初步判断如下。",
    "conditions": [
        {
            "condition": "学历要求",
            "status": "MET",
            "rationale": "硕士符合。",
            "citations": [{"page": 1, "quote": "具有全日制本科及以上学历"}],
            "missing_info": [],
        },
    ],
    "checklist": ["身份证"],
}


# ---------------------------------------------------------------------------
#  _build_user_prompt
# ---------------------------------------------------------------------------

class TestBuildUserPrompt:
    def test_with_profile(self) -> None:
        prompt = _build_user_prompt("能申请吗", "政策片段", {"学历": "硕士", "年龄": "28"})
        assert "用户已提供的信息" in prompt
        assert "学历: 硕士" in prompt
        assert "年龄: 28" in prompt
        assert "政策原文片段" in prompt

    def test_without_profile(self) -> None:
        prompt = _build_user_prompt("能申请吗", "政策片段", None)
        assert "尚未提供任何个人信息" in prompt

    def test_empty_profile(self) -> None:
        prompt = _build_user_prompt("能申请吗", "政策片段", {})
        assert "尚未提供任何个人信息" in prompt

    def test_question_appears_in_prompt(self) -> None:
        prompt = _build_user_prompt("硕士能拿多少", "ctx", None)
        assert "硕士能拿多少" in prompt


# ---------------------------------------------------------------------------
#  ClaudeReasoner initialization — credential errors (T07)
# ---------------------------------------------------------------------------

class TestReasonerInit:
    def test_constructor_wraps_credential_exception(self) -> None:
        """T07: If anthropic.Anthropic() raises → ReasonerUnavailableError."""
        import anthropic
        with patch.object(anthropic, "Anthropic", side_effect=Exception("no creds")):
            with pytest.raises(ReasonerUnavailableError, match="credentials"):
                ClaudeReasoner()

    def test_custom_client_accepted(self) -> None:
        """Passing an explicit client skips credential lookup."""
        fake_client = MagicMock()
        reasoner = ClaudeReasoner(client=fake_client)
        assert reasoner is not None


# ---------------------------------------------------------------------------
#  API error handling (T07)
# ---------------------------------------------------------------------------

class _FakeBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _FakeResponse:
    def __init__(self, payload: Any, stop_reason: str = "end_turn") -> None:
        body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        self.content = [_FakeBlock(body)]
        self.stop_reason = stop_reason
        self.stop_details: MagicMock | None = None


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


# Use a Chinese query that has lexical overlap with the policy document,
# so analyze() proceeds past the early-return guard to the API call.
_QUERY = "学历要求是什么"


class TestApiErrors:
    def test_api_status_error(self, document: Document, index: Bm25Index) -> None:
        """T07: API returns 429/500 → ReasonerUnavailableError."""
        import anthropic

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}

        error = anthropic.APIStatusError(
            message="rate limited",
            response=mock_response,
            body=None,
        )
        client = _FakeClient(error)
        with pytest.raises(ReasonerUnavailableError, match="429"):
            ClaudeReasoner(client=client).analyze(_QUERY, document, index)

    def test_api_connection_error(self, document: Document, index: Bm25Index) -> None:
        """T07: Network failure → ReasonerUnavailableError."""
        import anthropic

        error = anthropic.APIConnectionError(request=MagicMock())
        client = _FakeClient(error)
        with pytest.raises(ReasonerUnavailableError, match="network"):
            ClaudeReasoner(client=client).analyze(_QUERY, document, index)

    def test_model_refusal(self, document: Document, index: Bm25Index) -> None:
        """T07: Model refuses → ModelRefusedError with category."""
        response = _FakeResponse(WELL_FORMED)
        response.stop_reason = "refusal"
        response.stop_details = MagicMock(category="policy", explanation="不合规")
        client = _FakeClient(response)
        with pytest.raises(ModelRefusedError):
            ClaudeReasoner(client=client).analyze(_QUERY, document, index)

    def test_no_text_block_in_response(self, document: Document, index: Bm25Index) -> None:
        """T07: Response with no text block → MalformedModelOutputError."""
        response = MagicMock()
        response.stop_reason = "end_turn"
        response.stop_details = None
        img_block = MagicMock()
        img_block.type = "image"
        response.content = [img_block]

        client = _FakeClient(response)
        with pytest.raises(MalformedModelOutputError, match="no text block"):
            ClaudeReasoner(client=client).analyze(_QUERY, document, index)


# ---------------------------------------------------------------------------
#  render.py gap: empty verdicts (line 37-38)
# ---------------------------------------------------------------------------

class TestRenderEmptyReport:
    def test_no_verdicts(self) -> None:
        """A report with zero verdicts renders a 'no conditions' message."""
        from proofpath.render import render_report
        from proofpath.verifier import VerificationSummary

        report = MagicMock()
        report.summary = ""
        report.verdicts = ()
        report.checklist = ()
        report.missing_inputs = ()
        report.is_conclusive = False

        summary = VerificationSummary(
            total_citations=0, verified=0, partial=0, rejected=0,
            downgraded_conditions=0,
        )
        output = render_report(report, summary)
        assert "没有可判定的条件" in output
