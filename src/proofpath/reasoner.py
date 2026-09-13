"""Model-backed condition analysis.

The model's only job is to read retrieved policy text and propose, per condition:
a status, a rationale, a page + quote, and what it still needs from the user. It
is explicitly told that quotes are machine-checked, and its output is in fact
checked by `verifier.py` before anything reaches the user.

Structured outputs are used so the response is guaranteed-parseable JSON rather
than prose we would have to scrape.
"""
from __future__ import annotations

import json
from typing import Any

from . import config
from .errors import (
    MalformedModelOutputError,
    ModelRefusedError,
    ReasonerUnavailableError,
)
from .models import (
    Citation,
    ConditionStatus,
    ConditionVerdict,
    Document,
    EligibilityReport,
    VerifiedCitation,
)
from .models import CitationStatus
from .retrieval import Bm25Index, build_context

SYSTEM_PROMPT = """\
你是政策办事助手。你只能依据提供的政策原文片段作答，不得依赖常识或推测补充政策内容。

对用户问题，逐条拆解政策中的**独立条件**，每条给出：

- status：
  - MET：原文明确支持，且用户已提供的信息足以判定满足
  - UNMET：原文明确支持，且用户信息足以判定不满足
  - NEEDS_INPUT：原文清楚，但缺少用户的关键信息才能判定
  - UNKNOWN：提供的原文片段没有说清这一条
- rationale：简短说明依据，用中文
- citations：page 为片段标注的页码，quote 必须是原文的**逐字连续片段**
- missing_info：还需要用户提供什么（没有则空数组）

硬性要求：

1. quote 会被程序逐字比对原文。任何拼凑、改写或概括的引用都会被判定为无效，
   该条结论会被强制降级为 UNKNOWN。宁可写 UNKNOWN，也不要编造引用。
2. 只有 MET 和 UNMET 需要引用；信息不足时用 NEEDS_INPUT，不要猜。
3. 不要给出法律或资格的最终承诺，你产出的是**依据原文的初步判断**。
"""

# additionalProperties:false + required on every level is what makes the schema
# strict enough for the API to guarantee a parseable shape.
_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "conditions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "condition": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["MET", "UNMET", "NEEDS_INPUT", "UNKNOWN"],
                    },
                    "rationale": {"type": "string"},
                    "citations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "page": {"type": "integer"},
                                "quote": {"type": "string"},
                            },
                            "required": ["page", "quote"],
                            "additionalProperties": False,
                        },
                    },
                    "missing_info": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "condition",
                    "status",
                    "rationale",
                    "citations",
                    "missing_info",
                ],
                "additionalProperties": False,
            },
        },
        "checklist": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "conditions", "checklist"],
    "additionalProperties": False,
}


def _build_user_prompt(question: str, context: str, profile: dict[str, Any] | None) -> str:
    sections = [f"## 用户问题\n{question}"]
    if profile:
        rendered = "\n".join(f"- {key}: {value}" for key, value in sorted(profile.items()))
        sections.append(f"## 用户已提供的信息\n{rendered}")
    else:
        sections.append("## 用户已提供的信息\n(用户尚未提供任何个人信息)")
    sections.append(f"## 政策原文片段\n{context}")
    return "\n\n".join(sections)


def _parse_payload(raw: str, question: str, doc_id: str) -> EligibilityReport:
    """Turn the model's JSON into domain objects. Citations start unverified."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MalformedModelOutputError(f"response was not valid JSON: {exc}") from exc

    if not isinstance(data, dict) or "conditions" not in data:
        raise MalformedModelOutputError("response is missing the 'conditions' field")

    verdicts: list[ConditionVerdict] = []
    for item in data.get("conditions", []):
        if not isinstance(item, dict):
            raise MalformedModelOutputError("a condition entry was not an object")
        try:
            status = ConditionStatus(item["status"])
        except (KeyError, ValueError) as exc:
            raise MalformedModelOutputError(f"invalid condition status: {exc}") from exc

        # Wrapped as UNVERIFIED so an un-run verifier can never look like a pass.
        citations = tuple(
            VerifiedCitation(
                citation=Citation(page=int(c["page"]), quote=str(c["quote"])),
                status=CitationStatus.NOT_FOUND,
                coverage=0.0,
            )
            for c in item.get("citations", [])
            if isinstance(c, dict) and "page" in c and "quote" in c
        )
        verdicts.append(
            ConditionVerdict(
                condition=str(item.get("condition", "")),
                status=status,
                rationale=str(item.get("rationale", "")),
                citations=citations,
                missing_info=tuple(str(m) for m in item.get("missing_info", [])),
            )
        )

    return EligibilityReport(
        doc_id=doc_id,
        question=question,
        verdicts=tuple(verdicts),
        checklist=tuple(str(c) for c in data.get("checklist", [])),
        summary=str(data.get("summary", "")),
    )


class ClaudeReasoner:
    """Wraps one Claude call. Construct once and reuse - it holds an HTTP client."""

    __slots__ = ("_client", "_model")

    def __init__(self, client: Any | None = None, model: str = config.MODEL) -> None:
        self._model = model
        if client is not None:
            self._client = client
            return
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise ReasonerUnavailableError("the anthropic SDK is not installed") from exc
        try:
            self._client = anthropic.Anthropic()
        except Exception as exc:
            raise ReasonerUnavailableError(
                "no Anthropic credentials found. Run `ant auth login` or export "
                "ANTHROPIC_API_KEY."
            ) from exc

    def analyze(
        self,
        question: str,
        document: Document,
        index: Bm25Index,
        *,
        profile: dict[str, Any] | None = None,
        top_k: int = config.DEFAULT_TOP_K,
    ) -> EligibilityReport:
        """Retrieve context, ask the model, and return an UNVERIFIED report.

        The caller must pass the result through `verify_report` before showing it
        to anyone - that is where fabricated citations get caught.
        """
        import anthropic

        hits = index.search(question, top_k=top_k)
        context = build_context(hits)
        if not context:
            # No lexical overlap at all - answering would mean inventing content.
            return EligibilityReport(
                doc_id=document.doc_id,
                question=question,
                verdicts=(),
                summary="未能在文档中检索到与问题相关的内容，请换一种问法或确认上传了正确的文件。",
            )

        try:
            response = self._client.beta.messages.create(
                model=self._model,
                max_tokens=config.MAX_TOKENS,
                betas=[config.FALLBACK_BETA],
                fallbacks="default",
                thinking={"type": "adaptive"},
                output_config={
                    "effort": config.EFFORT,
                    "format": {"type": "json_schema", "schema": _SCHEMA},
                },
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        # Stable prefix: the system prompt never varies per
                        # request, so it is worth caching across conditions.
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": _build_user_prompt(question, context, profile),
                    }
                ],
            )
        except anthropic.AuthenticationError as exc:
            raise ReasonerUnavailableError(f"authentication failed: {exc}") from exc
        except anthropic.NotFoundError as exc:
            raise ReasonerUnavailableError(f"unknown model {self._model!r}: {exc}") from exc
        except anthropic.RateLimitError as exc:
            raise ReasonerUnavailableError(f"rate limited: {exc}") from exc
        except anthropic.APIStatusError as exc:
            raise ReasonerUnavailableError(
                f"API error {exc.status_code}: {exc.message}"
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise ReasonerUnavailableError(f"network error: {exc}") from exc

        if getattr(response, "stop_reason", None) == "refusal":
            details = getattr(response, "stop_details", None)
            raise ModelRefusedError(
                getattr(details, "category", None),
                getattr(details, "explanation", None),
            )

        text = next(
            (block.text for block in response.content if block.type == "text"), None
        )
        if text is None:
            raise MalformedModelOutputError("response contained no text block")

        return _parse_payload(text, question, document.doc_id)
