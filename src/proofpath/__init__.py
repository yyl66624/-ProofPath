"""ProofPath - evidence-grounded policy navigation.

Public surface:

    load_document   parse a file into page-anchored chunks
    Bm25Index       lexical retrieval over those chunks
    verify_report   check every citation against the source document
    ActionGate      risk-classify and gate execution actions
    AuditLog        hash-chained record of what happened
"""
from __future__ import annotations

from .models import (
    Citation,
    CitationStatus,
    Chunk,
    ConditionStatus,
    ConditionVerdict,
    Document,
    EligibilityReport,
    RiskLevel,
    VerifiedCitation,
)
from .parsers import load_document
from .retrieval import Bm25Index, ScoredChunk, build_context
from .verifier import VerificationSummary, verify_report

__version__ = "0.1.0"

__all__ = [
    "Bm25Index",
    "Chunk",
    "Citation",
    "CitationStatus",
    "ConditionStatus",
    "ConditionVerdict",
    "Document",
    "EligibilityReport",
    "RiskLevel",
    "ScoredChunk",
    "VerificationSummary",
    "VerifiedCitation",
    "build_context",
    "load_document",
    "verify_report",
]
