"""Typed errors so callers can distinguish user error from system failure."""
from __future__ import annotations


class ProofPathError(Exception):
    """Base class for every error this package raises deliberately."""


class DocumentLoadError(ProofPathError):
    """The source document could not be read or produced no text."""


class NoParserAvailableError(DocumentLoadError):
    """No installed parser can handle this file type."""


class EmptyIndexError(ProofPathError):
    """Retrieval was attempted against an index with no chunks."""


class ReasonerUnavailableError(ProofPathError):
    """The model-backed reasoner cannot run (missing credentials, etc.)."""


class ModelRefusedError(ProofPathError):
    """The model declined the request (stop_reason == 'refusal')."""

    def __init__(self, category: str | None, explanation: str | None) -> None:
        self.category = category
        self.explanation = explanation
        super().__init__(f"model refused (category={category}): {explanation}")


class MalformedModelOutputError(ProofPathError):
    """The model returned content that did not satisfy the output schema."""


class ConfirmationRequiredError(ProofPathError):
    """A sensitive action was attempted without an explicit confirmation."""

    def __init__(self, action_name: str, risk: str) -> None:
        self.action_name = action_name
        self.risk = risk
        super().__init__(
            f"action {action_name!r} is {risk} and requires explicit user confirmation"
        )


class AuditChainBrokenError(ProofPathError):
    """The audit log's hash chain does not validate."""
