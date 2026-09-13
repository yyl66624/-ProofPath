"""Immutable domain types.

Every type here is frozen and holds tuples rather than lists: a report that has
been verified must not be mutable afterwards, or the audit trail would describe
something other than what was shown to the user.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class ConditionStatus(str, Enum):
    """Whether the applicant satisfies one policy condition."""

    MET = "MET"
    UNMET = "UNMET"
    NEEDS_INPUT = "NEEDS_INPUT"  # cannot decide without more from the user
    UNKNOWN = "UNKNOWN"  # the document does not settle it, or evidence failed


class CitationStatus(str, Enum):
    """Result of checking a quote against its cited page."""

    VERIFIED = "VERIFIED"  # found verbatim (after normalization)
    PARTIAL = "PARTIAL"  # mostly present; likely a transcription slip
    NOT_FOUND = "NOT_FOUND"  # not on that page
    TOO_SHORT = "TOO_SHORT"  # not distinctive enough to be evidence
    BAD_PAGE = "BAD_PAGE"  # cited page does not exist in the document


class RiskLevel(str, Enum):
    """How much damage an execution action can do."""

    READ_ONLY = "READ_ONLY"  # navigate, read, screenshot
    LOCAL_WRITE = "LOCAL_WRITE"  # type into a field; reversible, not submitted
    SENSITIVE = "SENSITIVE"  # submit, upload, pay, delete - needs confirmation


@dataclass(frozen=True, slots=True)
class Chunk:
    """A page-anchored slice of a document."""

    chunk_id: str
    page: int
    text: str


@dataclass(frozen=True, slots=True)
class Document:
    """A parsed source document."""

    doc_id: str
    source_path: str
    parser: str
    pages: tuple[str, ...]  # full text per page, 1-indexed by position
    chunks: tuple[Chunk, ...]

    def page_text(self, page: int) -> str | None:
        """Text of a 1-indexed page, or None when the page does not exist."""
        if 1 <= page <= len(self.pages):
            return self.pages[page - 1]
        return None


@dataclass(frozen=True, slots=True)
class Citation:
    """A claim's pointer back into the source document."""

    page: int
    quote: str


@dataclass(frozen=True, slots=True)
class VerifiedCitation:
    """A citation after it has been checked against the document."""

    citation: Citation
    status: CitationStatus
    coverage: float

    @property
    def is_trustworthy(self) -> bool:
        """Whether this citation may support a definite conclusion."""
        return self.status in (CitationStatus.VERIFIED, CitationStatus.PARTIAL)


@dataclass(frozen=True, slots=True)
class ConditionVerdict:
    """One policy condition, the call on it, and the evidence behind it."""

    condition: str
    status: ConditionStatus
    rationale: str
    citations: tuple[VerifiedCitation, ...] = ()
    missing_info: tuple[str, ...] = ()

    @property
    def unverifiable_citations(self) -> tuple[VerifiedCitation, ...]:
        """Citations that could not be located in the source document.

        A definite verdict must have none of these. Requiring *every* citation
        to check out - rather than merely one - is what stops a compound claim
        from smuggling an unsupported half past verification: "硕士1500元,且可
        追补3个月" pairs a real quote with a fabricated one, and only the strict
        rule catches it.
        """
        return tuple(c for c in self.citations if not c.is_trustworthy)

    def downgraded(self, reason: str) -> ConditionVerdict:
        """Return a copy forced to UNKNOWN because its evidence failed."""
        return replace(
            self,
            status=ConditionStatus.UNKNOWN,
            rationale=f"{self.rationale}\n[证据核验未通过] {reason}",
        )


@dataclass(frozen=True, slots=True)
class EligibilityReport:
    """The full answer to 'do I qualify, and what do I need?'."""

    doc_id: str
    question: str
    verdicts: tuple[ConditionVerdict, ...]
    checklist: tuple[str, ...] = ()
    summary: str = ""

    @property
    def missing_inputs(self) -> tuple[str, ...]:
        """De-duplicated questions the user still has to answer."""
        seen: dict[str, None] = {}
        for verdict in self.verdicts:
            for item in verdict.missing_info:
                seen.setdefault(item, None)
        return tuple(seen)

    @property
    def is_conclusive(self) -> bool:
        """True only when every condition was decided on trustworthy evidence."""
        return bool(self.verdicts) and all(
            v.status in (ConditionStatus.MET, ConditionStatus.UNMET)
            for v in self.verdicts
        )

    def counts(self) -> dict[str, int]:
        """Verdict tally, for CLI summaries and audit payloads."""
        tally = {status.value: 0 for status in ConditionStatus}
        for verdict in self.verdicts:
            tally[verdict.status.value] += 1
        return tally
