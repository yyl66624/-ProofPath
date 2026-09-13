"""FastAPI adapter for ProofPath's verified application services.

The adapter owns HTTP validation, process-local task state, and serialization.
It never returns a model report directly: all successful results come from
``service.analyze_document``, which enforces document identity and citation
verification first.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Iterator

from fastapi import FastAPI, File, Header, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import config
from .api_schemas import (
    AnalysisRequest,
    AnalysisTaskResponse,
    DocumentResponse,
    ERROR_RESPONSES,
    SourcePageResponse,
)
from .errors import (
    DocumentLoadError,
    MalformedModelOutputError,
    ModelRateLimitedError,
    ModelRefusedError,
    ModelTimeoutError,
    NoParserAvailableError,
    ProofPathError,
    ReasonerUnavailableError,
    ReportDocumentMismatchError,
)
from .models import CitationStatus, ConditionStatus, Document, VerifiedCitation
from .parsers import load_document
from .reasoner import DeepSeekReasoner
from .service import AnalysisOutcome, analyze_document
from .text import normalize

_SUPPORTED_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
}
_TERMINAL_STATES = frozenset({"SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED"})


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def _public_error(
    code: str,
    message: str,
    *,
    retryable: bool,
    suggested_action: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "retryable": retryable,
        "suggested_action": suggested_action,
        "request_id": _new_id("req"),
    }


def _error_response(status_code: int, error: dict[str, Any]) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": error})


def _invalid_request(message: str = "请求字段不符合接口约定。") -> JSONResponse:
    return _error_response(
        400,
        _public_error(
            "INVALID_REQUEST",
            message,
            retryable=False,
            suggested_action="请检查请求字段后重新提交。",
        ),
    )


@dataclass(slots=True)
class _DocumentRecord:
    document: Document
    filename: str
    media_type: str
    created_at: str


@dataclass(slots=True)
class _AnalysisRecord:
    analysis_id: str
    document_id: str
    question: str
    profile: list[dict[str, Any]]
    fingerprint: str
    state: str = "RUNNING"
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    future: Future[Any] | None = None
    timer: threading.Timer | None = None
    cancel_model: Callable[[], None] | None = None


class _InMemoryStore:
    """Thread-safe process-local state; no cross-restart durability is claimed."""

    def __init__(self, *, max_workers: int = 4) -> None:
        self.documents: dict[str, _DocumentRecord] = {}
        self.analyses: dict[str, _AnalysisRecord] = {}
        self.idempotency: dict[str, str] = {}
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="proofpath-analysis",
        )

    def close(self) -> None:
        with self.lock:
            for record in self.analyses.values():
                if record.timer is not None:
                    record.timer.cancel()
        self.executor.shutdown(wait=False, cancel_futures=True)


def _sanitize_filename(filename: str | None) -> str:
    candidate = (filename or "upload").replace("\\", "/").split("/")[-1]
    return candidate or "upload"


def _document_payload(record: _DocumentRecord) -> dict[str, Any]:
    return {
        "document_id": record.document.doc_id,
        "filename": record.filename,
        "media_type": record.media_type,
        "parser": record.document.parser,
        "page_count": len(record.document.pages),
        "created_at": record.created_at,
    }


def _source_fragment(document: Document, chunk: Any) -> dict[str, Any]:
    return {
        "fragment_id": chunk.chunk_id,
        "document_id": document.doc_id,
        "page": chunk.page,
        "text": chunk.text,
    }


def _fragment_id(document: Document, citation: VerifiedCitation) -> str:
    same_page = [
        chunk for chunk in document.chunks if chunk.page == citation.citation.page
    ]
    needle = normalize(citation.citation.quote)
    for chunk in same_page:
        if needle and needle in normalize(chunk.text):
            return chunk.chunk_id
    if same_page:
        return same_page[0].chunk_id
    return f"{document.doc_id}-p{citation.citation.page}-c0"


def _citation_payload(
    document: Document, citation: VerifiedCitation
) -> dict[str, Any]:
    page = citation.citation.page
    return {
        "page": page,
        "fragment_id": _fragment_id(document, citation),
        "quote": citation.citation.quote,
        "status": citation.status.value,
        "coverage": citation.coverage,
        "locator": f"/api/v1/documents/{document.doc_id}/pages/{page}",
    }


def _result_payload(
    document: Document, outcome: AnalysisOutcome
) -> dict[str, Any]:
    report = outcome.report
    verdicts = [
        {
            "condition": verdict.condition,
            "status": verdict.status.value,
            "rationale": verdict.rationale,
            "citations": [
                _citation_payload(document, citation)
                for citation in verdict.citations
            ],
            "missing_info": list(verdict.missing_info),
        }
        for verdict in report.verdicts
    ]
    return {
        "summary": report.summary,
        "verdicts": verdicts,
        "materials": [],
        "missing_inputs": list(report.missing_inputs),
        "requires_human_review": outcome.requires_human_review,
    }


def _result_state(outcome: AnalysisOutcome) -> str:
    report = outcome.report
    if not report.verdicts or outcome.requires_human_review:
        return "PARTIAL"
    if any(
        verdict.status in (ConditionStatus.NEEDS_INPUT, ConditionStatus.UNKNOWN)
        for verdict in report.verdicts
    ):
        return "PARTIAL"
    if any(
        citation.status is CitationStatus.PARTIAL
        for verdict in report.verdicts
        for citation in verdict.citations
    ):
        return "PARTIAL"
    return "SUCCEEDED"


def _task_payload(record: _AnalysisRecord) -> dict[str, Any]:
    return {
        "analysis_id": record.analysis_id,
        "document_id": record.document_id,
        "state": record.state,
        "question": record.question,
        "profile": record.profile,
        "result": record.result,
        "error": record.error,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _failure_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ModelRateLimitedError):
        return _public_error(
            "MODEL_RATE_LIMITED",
            "模型服务当前额度不足或请求过多。",
            retryable=True,
            suggested_action="请稍后重试，或检查模型账户额度。",
        )
    if isinstance(exc, ModelTimeoutError):
        return _public_error(
            "MODEL_TIMEOUT",
            "模型分析超过服务端时间上限。",
            retryable=True,
            suggested_action="请稍后重试，或缩短文档与问题。",
        )
    if isinstance(exc, ModelRefusedError):
        return _public_error(
            "MODEL_REFUSED",
            "模型拒绝处理该请求。",
            retryable=False,
            suggested_action="请调整问题，避免要求最终法律承诺或无关内容。",
        )
    if isinstance(exc, MalformedModelOutputError):
        return _public_error(
            "MODEL_OUTPUT_INVALID",
            "模型响应不符合结构约定，结果未展示。",
            retryable=True,
            suggested_action="请重新发起分析；若持续出现请联系维护者。",
        )
    if isinstance(exc, ReportDocumentMismatchError):
        return _public_error(
            "DOCUMENT_MISMATCH",
            "分析结果与源文档不一致，结果已阻断。",
            retryable=False,
            suggested_action="请重新上传文档并创建新的分析任务。",
        )
    if isinstance(exc, ReasonerUnavailableError):
        return _public_error(
            "MODEL_UNAVAILABLE",
            "模型服务当前不可用。",
            retryable=True,
            suggested_action="请检查服务凭证与网络后重试。",
        )
    return _public_error(
        "ANALYSIS_FAILED",
        "分析未能完成，未返回不完整结果。",
        retryable=isinstance(exc, (ProofPathError, OSError)),
        suggested_action="请重新发起分析；若持续出现请联系维护者。",
    )


def _normalize_profile(raw: Any) -> tuple[list[dict[str, Any]], dict[str, str]]:
    if raw is None:
        raw = []
    if not isinstance(raw, list) or len(raw) > 50:
        raise ValueError("profile must be an array with at most 50 entries")

    normalized: list[dict[str, Any]] = []
    provided: dict[str, str] = {}
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("profile entries must be objects")
        key_raw = item.get("key")
        key = key_raw.strip() if isinstance(key_raw, str) else ""
        state = item.get("state")
        source = item.get("source")
        value = item.get("value")
        if not key or key in seen:
            raise ValueError("profile keys must be non-empty and unique")
        if state not in {"PROVIDED", "UNKNOWN", "DECLINED"}:
            raise ValueError("profile state is invalid")
        if source != "USER_INPUT":
            raise ValueError("profile source is invalid")
        if state == "PROVIDED":
            if not isinstance(value, str) or not value.strip():
                raise ValueError("provided profile values must be non-empty strings")
            value = value.strip()
            provided[key] = value
        elif value is not None:
            raise ValueError("unprovided profile values must be null")
        seen.add(key)
        normalized.append(
            {"key": key, "value": value, "state": state, "source": source}
        )
    normalized.sort(key=lambda item: item["key"])
    return normalized, provided


def _normalize_analysis_request(
    raw: Any,
) -> tuple[str, str, list[dict[str, Any]], dict[str, str], str]:
    if not isinstance(raw, dict):
        raise ValueError("request body must be an object")
    document_id = raw.get("document_id")
    question_raw = raw.get("question")
    if not isinstance(document_id, str) or not document_id:
        raise ValueError("document_id is required")
    if not isinstance(question_raw, str):
        raise ValueError("question is required")
    question = question_raw.strip()
    if not 1 <= len(question) <= 2_000:
        raise ValueError("question length is invalid")
    profile, provided = _normalize_profile(raw.get("profile", []))
    canonical = json.dumps(
        {"document_id": document_id, "question": question, "profile": profile},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return document_id, question, profile, provided, fingerprint


def _valid_idempotency_key(key: str | None) -> bool:
    if key is None or not 16 <= len(key) <= 128:
        return False
    return all(32 <= ord(character) <= 126 for character in key)


def _env_number(name: str, fallback: int | float, converter: Any) -> int | float:
    raw = os.environ.get(name)
    if raw is None:
        return fallback
    try:
        value = converter(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def create_app(
    *,
    reasoner_factory: Callable[[], Any] | None = None,
    max_upload_bytes: int | None = None,
    analyze_timeout_seconds: float | None = None,
) -> FastAPI:
    """Create an isolated service instance with process-local state.

    ``reasoner_factory`` defaults to a credential-aware selector: if
    ``DEEPSEEK_API_KEY`` is set in the environment, ``DeepSeekReasoner`` is
    used; otherwise ``ScriptedReasoner`` (from ``proofpath.demo``) returns the
    canned demo report so the service is usable end-to-end without a key. Pass
    an explicit factory to override — used by tests.
    """
    upload_limit = int(
        max_upload_bytes
        if max_upload_bytes is not None
        else _env_number(
            "PROOFPATH_MAX_UPLOAD_BYTES", config.MAX_UPLOAD_BYTES, int
        )
    )
    analysis_timeout = float(
        analyze_timeout_seconds
        if analyze_timeout_seconds is not None
        else _env_number(
            "PROOFPATH_ANALYZE_TIMEOUT_SECONDS",
            config.ANALYZE_TIMEOUT_SECONDS,
            float,
        )
    )
    if upload_limit <= 0 or analysis_timeout <= 0:
        raise ValueError("service limits must be positive")

    if reasoner_factory is None:
        # Demo mode: fall back to the canned reasoner so the service works
        # without DEEPSEEK_API_KEY. The verifier still runs over the canned
        # report, so the trust-boundary evidence check is exercised.
        if os.environ.get("DEEPSEEK_API_KEY"):
            reasoner_factory = DeepSeekReasoner
        else:
            from .demo import ScriptedReasoner

            reasoner_factory = ScriptedReasoner

    store = _InMemoryStore()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Iterator[None]:
        yield
        store.close()

    application = FastAPI(
        title="ProofPath API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.store = store
    application.state.reasoner_factory = reasoner_factory

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _: Request, __: RequestValidationError
    ) -> JSONResponse:
        return _invalid_request()

    @application.post(
        "/api/v1/documents",
        status_code=201,
        response_model=DocumentResponse,
        responses=ERROR_RESPONSES,
    )
    async def upload_document(file: UploadFile = File(...)) -> Any:
        filename = _sanitize_filename(file.filename)
        suffix = Path(filename).suffix.casefold()
        media_type = _SUPPORTED_MEDIA_TYPES.get(suffix)
        if media_type is None:
            return _error_response(
                415,
                _public_error(
                    "UNSUPPORTED_MEDIA_TYPE",
                    "当前只支持 PDF、TXT 和 Markdown 文件。",
                    retryable=False,
                    suggested_action="请上传扩展名为 .pdf、.txt 或 .md 的文件。",
                ),
            )

        payload = await file.read(upload_limit + 1)
        if len(payload) > upload_limit:
            return _error_response(
                413,
                _public_error(
                    "FILE_TOO_LARGE",
                    f"文件超过 {upload_limit} 字节的上传上限。",
                    retryable=False,
                    suggested_action="请压缩或拆分文件后重新上传。",
                ),
            )
        if not payload:
            return _error_response(
                422,
                _public_error(
                    "EMPTY_FILE",
                    "上传文件为空。",
                    retryable=False,
                    suggested_action="请选择包含政策正文的文件。",
                ),
            )

        try:
            with TemporaryDirectory(prefix="proofpath-upload-") as temp_dir:
                # The user filename is display-only. A fixed basename keeps
                # reserved characters, excessive length, and URL delimiters
                # out of both the filesystem path and content-addressed ID.
                path = Path(temp_dir) / f"source{suffix}"
                path.write_bytes(payload)
                document = load_document(path)
        except NoParserAvailableError:
            return _error_response(
                415,
                _public_error(
                    "UNSUPPORTED_MEDIA_TYPE",
                    "当前无法解析该文件类型。",
                    retryable=False,
                    suggested_action="请转换为 PDF、TXT 或 Markdown 后重试。",
                ),
            )
        except DocumentLoadError as exc:
            no_text = "no extractable text" in str(exc)
            return _error_response(
                422,
                _public_error(
                    "NO_EXTRACTABLE_TEXT" if no_text else "DOCUMENT_DAMAGED",
                    "文件中没有可提取文本。" if no_text else "文件无法解析。",
                    retryable=False,
                    suggested_action=(
                        "请上传带文本层的文件，或在启用 OCR 后重试。"
                        if no_text
                        else "请确认文件未损坏后重新上传。"
                    ),
                ),
            )

        record = _DocumentRecord(document, filename, media_type, _now())
        with store.lock:
            store.documents[document.doc_id] = record
        return _document_payload(record)

    @application.get(
        "/api/v1/documents/{document_id}/pages/{page}",
        response_model=SourcePageResponse,
        responses=ERROR_RESPONSES,
    )
    def get_document_page(document_id: str, page: int) -> Any:
        with store.lock:
            record = store.documents.get(document_id)
        if record is None:
            return _error_response(
                404,
                _public_error(
                    "DOCUMENT_NOT_FOUND",
                    "未找到该文档。",
                    retryable=False,
                    suggested_action="请重新上传文档。",
                ),
            )
        text = record.document.page_text(page)
        if text is None:
            return _error_response(
                404,
                _public_error(
                    "PAGE_NOT_FOUND",
                    "该页不在文档范围内。",
                    retryable=False,
                    suggested_action="请检查页码后重试。",
                ),
            )
        fragments = [
            _source_fragment(record.document, chunk)
            for chunk in record.document.chunks
            if chunk.page == page
        ]
        return {
            "document_id": document_id,
            "page": page,
            "text": text,
            "fragments": fragments,
        }

    def finish_timeout(analysis_id: str) -> None:
        with store.lock:
            record = store.analyses.get(analysis_id)
            if record is None or record.state != "RUNNING":
                return
            # ``DeepSeekReasoner.cancel`` only sets an Event and cannot block.
            # Signal it before publishing the terminal state so no retry can
            # begin after observers see FAILED.
            if record.cancel_model is not None:
                record.cancel_model()
                record.cancel_model = None
            record.state = "FAILED"
            record.error = _failure_payload(ModelTimeoutError("service timeout"))
            record.updated_at = _now()

    def run_analysis(
        analysis_id: str,
        document: Document,
        question: str,
        provided_profile: dict[str, str],
    ) -> None:
        try:
            reasoner = reasoner_factory()
            with store.lock:
                record = store.analyses[analysis_id]
                if record.state != "RUNNING":
                    return
                cancel_model = getattr(reasoner, "cancel", None)
                if callable(cancel_model):
                    record.cancel_model = cancel_model
            outcome = analyze_document(
                question,
                document,
                reasoner,
                profile=provided_profile,
            )
        except Exception as exc:
            with store.lock:
                record = store.analyses[analysis_id]
                if record.state != "RUNNING":
                    return
                if record.timer is not None:
                    record.timer.cancel()
                record.cancel_model = None
                record.state = "FAILED"
                record.error = _failure_payload(exc)
                record.updated_at = _now()
            return

        with store.lock:
            record = store.analyses[analysis_id]
            if record.state != "RUNNING":
                return
            if record.timer is not None:
                record.timer.cancel()
            record.cancel_model = None
            record.state = _result_state(outcome)
            record.result = _result_payload(document, outcome)
            record.updated_at = _now()

    @application.post(
        "/api/v1/analyses",
        status_code=202,
        response_model=AnalysisTaskResponse,
        responses={
            200: {"model": AnalysisTaskResponse},
            **ERROR_RESPONSES,
        },
    )
    def create_analysis(
        body: AnalysisRequest,
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ) -> Any:
        if not _valid_idempotency_key(idempotency_key):
            return _invalid_request(
                "Idempotency-Key 必须为 16–128 个可打印 ASCII 字符。"
            )
        try:
            document_id, question, profile, provided, fingerprint = (
                _normalize_analysis_request(body.model_dump())
            )
        except ValueError:
            return _invalid_request()

        with store.lock:
            document_record = store.documents.get(document_id)
            if document_record is None:
                return _error_response(
                    404,
                    _public_error(
                        "DOCUMENT_NOT_FOUND",
                        "未找到该文档。",
                        retryable=False,
                        suggested_action="请重新上传文档。",
                    ),
                )
            previous_id = store.idempotency.get(idempotency_key)
            if previous_id is not None:
                previous = store.analyses[previous_id]
                if previous.fingerprint != fingerprint:
                    return _error_response(
                        409,
                        _public_error(
                            "IDEMPOTENCY_CONFLICT",
                            "同一幂等键已用于不同的分析请求。",
                            retryable=False,
                            suggested_action="请为新请求使用新的幂等键。",
                        ),
                    )
                return JSONResponse(status_code=200, content=_task_payload(previous))

            analysis_id = _new_id("ana")
            record = _AnalysisRecord(
                analysis_id=analysis_id,
                document_id=document_id,
                question=question,
                profile=profile,
                fingerprint=fingerprint,
            )
            store.analyses[analysis_id] = record
            store.idempotency[idempotency_key] = analysis_id
            timer = threading.Timer(
                analysis_timeout,
                finish_timeout,
                args=(analysis_id,),
            )
            timer.daemon = True
            record.timer = timer
            timer.start()
            record.future = store.executor.submit(
                run_analysis,
                analysis_id,
                document_record.document,
                question,
                provided,
            )
            accepted = _task_payload(record)
        return JSONResponse(status_code=202, content=accepted)

    @application.get(
        "/api/v1/analyses/{analysis_id}",
        response_model=AnalysisTaskResponse,
        responses=ERROR_RESPONSES,
    )
    def get_analysis(analysis_id: str) -> Any:
        with store.lock:
            record = store.analyses.get(analysis_id)
            if record is not None:
                return _task_payload(record)
        return _error_response(
            404,
            _public_error(
                "ANALYSIS_NOT_FOUND",
                "未找到该分析任务。",
                retryable=False,
                suggested_action="请检查任务标识或重新创建分析。",
            ),
        )

    @application.post(
        "/api/v1/analyses/{analysis_id}/cancel",
        response_model=AnalysisTaskResponse,
        responses=ERROR_RESPONSES,
    )
    def cancel_analysis(analysis_id: str) -> Any:
        with store.lock:
            record = store.analyses.get(analysis_id)
            if record is None:
                return _error_response(
                    404,
                    _public_error(
                        "ANALYSIS_NOT_FOUND",
                        "未找到该分析任务。",
                        retryable=False,
                        suggested_action="请检查任务标识或重新创建分析。",
                    ),
                )
            if record.state in _TERMINAL_STATES:
                return _task_payload(record)
            if record.cancel_model is not None:
                record.cancel_model()
                record.cancel_model = None
            record.state = "CANCELLED"
            record.result = None
            record.error = None
            record.updated_at = _now()
            if record.timer is not None:
                record.timer.cancel()
            if record.future is not None:
                record.future.cancel()
            payload = _task_payload(record)
        return payload

    return application


app = create_app()
