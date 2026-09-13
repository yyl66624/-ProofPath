"""Pydantic representation of the public HTTP contract.

These models make the JSON shapes visible in FastAPI's OpenAPI document. The
domain remains independent of Pydantic; conversion happens in ``api.py`` only.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentResponse(_ContractModel):
    document_id: str
    filename: str
    media_type: str
    parser: str
    page_count: int
    created_at: str


class SourceFragmentResponse(_ContractModel):
    fragment_id: str
    document_id: str
    page: int
    text: str


class SourcePageResponse(_ContractModel):
    document_id: str
    page: int
    text: str
    fragments: list[SourceFragmentResponse]


class ProfileField(_ContractModel):
    key: str
    value: str | None
    state: Literal["PROVIDED", "UNKNOWN", "DECLINED"]
    source: Literal["USER_INPUT"]


class AnalysisRequest(_ContractModel):
    document_id: str
    question: str
    profile: list[ProfileField]


class CitationResponse(_ContractModel):
    page: int
    fragment_id: str
    quote: str
    status: Literal["VERIFIED", "PARTIAL", "NOT_FOUND", "TOO_SHORT", "BAD_PAGE"]
    coverage: float
    locator: str


class ConditionVerdictResponse(_ContractModel):
    condition: str
    status: Literal["MET", "UNMET", "NEEDS_INPUT", "UNKNOWN"]
    rationale: str
    citations: list[CitationResponse]
    missing_info: list[str]


class MaterialItemResponse(_ContractModel):
    name: str
    basis: Literal["POLICY_TEXT", "USER_INPUT"]
    requirement_state: Literal["REQUIRED", "CONDITIONAL", "UNKNOWN"]
    provision_state: Literal[
        "PROVIDED", "NOT_PROVIDED", "DECLINED", "NOT_APPLICABLE"
    ]
    citations: list[CitationResponse]


class AnalysisResultResponse(_ContractModel):
    summary: str
    verdicts: list[ConditionVerdictResponse]
    materials: list[MaterialItemResponse]
    missing_inputs: list[str]
    requires_human_review: bool


class PublicError(_ContractModel):
    code: str
    message: str
    retryable: bool
    suggested_action: str
    request_id: str


class ErrorEnvelope(_ContractModel):
    error: PublicError


class AnalysisTaskResponse(_ContractModel):
    analysis_id: str
    document_id: str
    state: Literal["RUNNING", "SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED"]
    question: str
    profile: list[ProfileField]
    result: AnalysisResultResponse | None
    error: PublicError | None
    created_at: str
    updated_at: str


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    409: {"model": ErrorEnvelope},
    413: {"model": ErrorEnvelope},
    415: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    429: {"model": ErrorEnvelope},
    500: {"model": ErrorEnvelope},
    502: {"model": ErrorEnvelope},
    503: {"model": ErrorEnvelope},
    504: {"model": ErrorEnvelope},
}
