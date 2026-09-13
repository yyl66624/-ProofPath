"""Model-backed condition analysis.

The model's only job is to read retrieved policy text and propose, per condition:
a status, a rationale, a page + quote, and what it still needs from the user. It
is explicitly told that quotes are machine-checked, and its output is in fact
checked by `verifier.py` before anything reaches the user.

DeepSeek JSON mode is paired with local validation because the provider only
guarantees syntactically valid JSON, not this application's schema.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any

from . import config
from .errors import (
    AnalysisCancelledError,
    MalformedModelOutputError,
    ModelOutputTruncatedError,
    ModelRateLimitedError,
    ModelRefusedError,
    ModelTimeoutError,
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

你的完整响应必须是一个 JSON 对象，不得带 Markdown 代码块或 JSON 之外的文字。
顶层字段固定为 summary、conditions、checklist。conditions 是数组，每项必须包含
condition、status、rationale、citations、missing_info；citations 每项必须包含整数 page
和字符串 quote；checklist 是字符串数组。

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
4. 政策要求提交的身份证、证书、表格等属于材料清单，只能放入 checklist；
   除非材料本身也是资格门槛，否则不得把每份材料单独列成已满足或不满足的独立条件。
"""


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

    required_root = {"summary", "conditions", "checklist"}
    if not isinstance(data, dict) or set(data) != required_root:
        raise MalformedModelOutputError(
            "response must contain exactly summary, conditions, and checklist"
        )
    if not isinstance(data["summary"], str):
        raise MalformedModelOutputError("response summary was not a string")
    if not isinstance(data["conditions"], list):
        raise MalformedModelOutputError("response conditions was not an array")
    if not isinstance(data["checklist"], list) or not all(
        isinstance(item, str) for item in data["checklist"]
    ):
        raise MalformedModelOutputError(
            "response checklist was not an array of strings"
        )

    verdicts: list[ConditionVerdict] = []
    required_condition = {
        "condition",
        "status",
        "rationale",
        "citations",
        "missing_info",
    }
    for item in data["conditions"]:
        if not isinstance(item, dict):
            raise MalformedModelOutputError("a condition entry was not an object")
        if set(item) != required_condition:
            raise MalformedModelOutputError(
                "a condition entry did not contain the required fields"
            )
        if not isinstance(item["condition"], str):
            raise MalformedModelOutputError("condition text was not a string")
        if not isinstance(item["rationale"], str):
            raise MalformedModelOutputError("condition rationale was not a string")
        if not isinstance(item["citations"], list):
            raise MalformedModelOutputError("condition citations was not an array")
        if not isinstance(item["missing_info"], list) or not all(
            isinstance(value, str) for value in item["missing_info"]
        ):
            raise MalformedModelOutputError(
                "condition missing_info was not an array of strings"
            )
        try:
            status = ConditionStatus(item["status"])
        except (KeyError, ValueError) as exc:
            raise MalformedModelOutputError(f"invalid condition status: {exc}") from exc

        checked_citations: list[VerifiedCitation] = []
        for citation in item["citations"]:
            if (
                not isinstance(citation, dict)
                or set(citation) != {"page", "quote"}
                or not isinstance(citation["page"], int)
                or isinstance(citation["page"], bool)
                or not isinstance(citation["quote"], str)
            ):
                raise MalformedModelOutputError(
                    "citation must contain an integer page and string quote"
                )
            checked_citations.append(
                VerifiedCitation(
                    citation=Citation(
                        page=citation["page"], quote=citation["quote"]
                    ),
                    status=CitationStatus.NOT_FOUND,
                    coverage=0.0,
                )
            )

        # Wrapped as UNVERIFIED so an un-run verifier can never look like a pass.
        verdicts.append(
            ConditionVerdict(
                condition=item["condition"],
                status=status,
                rationale=item["rationale"],
                citations=tuple(checked_citations),
                missing_info=tuple(item["missing_info"]),
            )
        )

    return EligibilityReport(
        doc_id=doc_id,
        question=question,
        verdicts=tuple(verdicts),
        checklist=tuple(data["checklist"]),
        summary=data["summary"],
    )


def _response_content(response: Any, question: str, doc_id: str) -> EligibilityReport:
    """Read only ``message.content`` and classify provider-side empty output."""
    choices = getattr(response, "choices", None)
    if not choices:
        raise MalformedModelOutputError("response contained no choices")

    choice = choices[0]
    message = getattr(choice, "message", None)
    refusal = getattr(message, "refusal", None) if message is not None else None
    finish_reason = getattr(choice, "finish_reason", None)
    if refusal or finish_reason == "content_filter":
        raise ModelRefusedError("content_filter", refusal or "provider content filter")

    content = getattr(message, "content", None) if message is not None else None
    if not isinstance(content, str) or not content.strip():
        if finish_reason == "length":
            raise ModelOutputTruncatedError(
                "model response was truncated before message.content was produced"
            )
        raise MalformedModelOutputError("response contained empty message.content")
    return _parse_payload(content, question, doc_id)


def _provider_failure(exc: Exception) -> ReasonerUnavailableError:
    """Map SDK exceptions to stable public failure categories without secrets."""
    import openai

    if isinstance(exc, openai.APITimeoutError):
        return ModelTimeoutError("model request timed out")
    if isinstance(exc, openai.RateLimitError):
        return ModelRateLimitedError("model request was rate limited")
    if isinstance(exc, openai.APIConnectionError):
        return ReasonerUnavailableError("model network error")
    if isinstance(exc, openai.AuthenticationError):
        return ReasonerUnavailableError(
            "model authentication failed; check DEEPSEEK_API_KEY"
        )
    if isinstance(exc, openai.NotFoundError):
        return ReasonerUnavailableError("configured DeepSeek model was not found")
    if isinstance(exc, openai.PermissionDeniedError):
        return ReasonerUnavailableError("model request was not permitted")
    if isinstance(exc, openai.BadRequestError):
        return ReasonerUnavailableError("model request was invalid")
    if isinstance(exc, openai.APIStatusError):
        return ReasonerUnavailableError(
            f"model provider returned HTTP {exc.status_code}"
        )
    return ReasonerUnavailableError("model provider failed")


def _retryable_provider_failure(exc: Exception) -> bool:
    import openai

    if isinstance(
        exc,
        (openai.APITimeoutError, openai.RateLimitError, openai.APIConnectionError),
    ):
        return True
    return isinstance(exc, openai.APIStatusError) and exc.status_code >= 500


class DeepSeekReasoner:
    """OpenAI-compatible DeepSeek client with bounded retries and model fallback."""

    __slots__ = (
        "_client",
        "_cancelled",
        "_fallback_model",
        "_max_retries",
        "_max_tokens",
        "_model",
    )

    def __init__(
        self,
        client: Any | None = None,
        model: str | None = None,
        *,
        fallback_model: str = config.FALLBACK_MODEL,
        max_retries: int = config.MODEL_MAX_RETRIES,
        max_tokens: int = config.MAX_TOKENS,
    ) -> None:
        if max_tokens < config.MIN_MODEL_TOKENS:
            raise ValueError(
                f"max_tokens must be at least {config.MIN_MODEL_TOKENS}"
            )
        if max_retries < 0 or max_retries > config.MODEL_MAX_RETRIES:
            raise ValueError(
                f"max_retries must be between 0 and {config.MODEL_MAX_RETRIES}"
            )

        self._model = model or os.environ.get("DEEPSEEK_MODEL") or config.MODEL
        self._fallback_model = fallback_model
        self._max_retries = max_retries
        self._max_tokens = max_tokens
        self._cancelled = threading.Event()
        if client is not None:
            self._client = client
            return

        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            raise ReasonerUnavailableError(
                "DEEPSEEK_API_KEY is required for model-backed analysis"
            )
        try:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=api_key,
                base_url=os.environ.get("DEEPSEEK_BASE_URL")
                or config.DEEPSEEK_BASE_URL,
                max_retries=0,
                timeout=config.MODEL_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # pragma: no cover - SDK validates environment
            raise ReasonerUnavailableError(
                "could not initialize the DeepSeek client"
            ) from exc

    def cancel(self) -> None:
        """Prevent another provider attempt after the current call returns."""
        self._cancelled.set()

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
        if self._cancelled.is_set():
            raise AnalysisCancelledError("analysis was cancelled before model call")
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

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _build_user_prompt(question, context, profile),
            },
        ]
        retry_models = [self._model]
        if self._max_retries:
            retry_models.extend([self._model] * (self._max_retries - 1))
            retry_models.append(self._fallback_model)

        last_error: Exception | None = None
        for attempt, current_model in enumerate(retry_models):
            if self._cancelled.is_set():
                raise AnalysisCancelledError(
                    "analysis was cancelled before another model attempt"
                )
            try:
                response = self._client.chat.completions.create(
                    model=current_model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    max_tokens=self._max_tokens,
                    extra_body={"thinking": {"type": "disabled"}},
                )
                return _response_content(response, question, document.doc_id)
            except ModelRefusedError:
                raise
            except MalformedModelOutputError as exc:
                last_error = exc
            except Exception as exc:
                if not _retryable_provider_failure(exc):
                    raise _provider_failure(exc) from exc
                last_error = exc

            if attempt == len(retry_models) - 1:
                if isinstance(last_error, MalformedModelOutputError):
                    raise last_error
                assert last_error is not None
                raise _provider_failure(last_error) from last_error

        raise ReasonerUnavailableError("model provider failed")  # pragma: no cover
