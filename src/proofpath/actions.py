"""Action risk classification and the confirmation gate.

The promise to the user is that nothing irreversible happens without an explicit
confirmation. That promise is enforced here rather than in the browser layer, so
it holds regardless of which executor runs the plan - and so it can be tested
without a browser.

Design note: classification is deny-by-default. An action whose kind is not
recognized is treated as SENSITIVE, because the failure mode of over-confirming
is an extra click and the failure mode of under-confirming is a wrongly filed
government application.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Protocol

from .errors import ConfirmationRequiredError
from .models import RiskLevel

# Explicit whitelist of low-risk action kinds. Everything else escalates.
_READ_ONLY_KINDS = frozenset({"navigate", "read", "screenshot", "wait", "scroll", "extract"})
_LOCAL_WRITE_KINDS = frozenset({"fill", "type", "select", "check", "focus"})

# Substrings that force SENSITIVE regardless of kind. A "fill" action that
# targets a payment field is not a local write in any meaningful sense.
_SENSITIVE_MARKERS = (
    "submit", "upload", "pay", "delete", "confirm", "sign", "purchase", "transfer",
    "提交", "上传", "支付", "删除", "确认", "签署", "缴费", "付款", "转账", "注销",
)


def classify(kind: str, target: str = "", value: str = "") -> RiskLevel:
    """Classify an action by its kind and where it points.

    Sensitive markers win over the kind whitelist: intent is inferred from the
    whole action, not from the verb alone.
    """
    haystack = f"{kind} {target} {value}".casefold()
    if any(marker in haystack for marker in _SENSITIVE_MARKERS):
        return RiskLevel.SENSITIVE

    normalized = kind.strip().casefold()
    if normalized in _READ_ONLY_KINDS:
        return RiskLevel.READ_ONLY
    if normalized in _LOCAL_WRITE_KINDS:
        return RiskLevel.LOCAL_WRITE
    return RiskLevel.SENSITIVE  # deny by default


@dataclass(frozen=True, slots=True)
class Action:
    """One step in an execution plan."""

    kind: str
    target: str = ""
    value: str = ""
    note: str = ""

    @property
    def risk(self) -> RiskLevel:
        return classify(self.kind, self.target, self.value)

    @property
    def requires_confirmation(self) -> bool:
        return self.risk is RiskLevel.SENSITIVE

    def describe(self) -> str:
        """Human-readable one-liner for a confirmation prompt or the audit log."""
        parts = [self.kind]
        if self.target:
            parts.append(f"-> {self.target}")
        if self.value:
            # Never echo a full value: it may hold an ID number or a password.
            preview = self.value if len(self.value) <= 12 else self.value[:12] + "…"
            parts.append(f"= {preview!r}")
        return " ".join(parts)


@dataclass(frozen=True, slots=True)
class ActionResult:
    """Outcome of a single attempted action."""

    action: Action
    executed: bool
    detail: str = ""


class Executor(Protocol):
    """Anything that can carry out an action (a browser, a dry run, a fake)."""

    def execute(self, action: Action) -> str:
        """Perform the action and return a short description of what happened."""
        ...


class DryRunExecutor:
    """Records actions without performing them.

    This is the default so that `proofpath fill` is safe to run during a demo:
    the plan and its risk classification are visible before any real browser is
    involved.
    """

    def __init__(self) -> None:
        self._seen: list[Action] = []

    @property
    def seen(self) -> tuple[Action, ...]:
        return tuple(self._seen)

    def execute(self, action: Action) -> str:
        self._seen.append(action)
        return f"dry-run: {action.describe()}"


ConfirmFn = Callable[[Action], bool]


def deny_all(_: Action) -> bool:
    """Default confirmation policy: refuse every sensitive action."""
    return False


class ActionGate:
    """Runs a plan, stopping at sensitive actions unless they are confirmed."""

    __slots__ = ("_executor", "_confirm", "_audit")

    def __init__(
        self,
        executor: Executor,
        *,
        confirm: ConfirmFn = deny_all,
        audit: "AuditSink | None" = None,
    ) -> None:
        self._executor = executor
        self._confirm = confirm
        self._audit = audit

    def _record(self, event: str, action: Action, **extra: object) -> None:
        if self._audit is None:
            return
        self._audit.append(
            event,
            kind=action.kind,
            target=action.target,
            risk=action.risk.value,
            **extra,
        )

    def run_one(self, action: Action) -> ActionResult:
        """Execute one action, honouring the confirmation requirement.

        Raises ConfirmationRequiredError when a sensitive action is declined, so
        a partially-completed plan cannot be mistaken for a completed one.
        """
        if action.requires_confirmation and not self._confirm(action):
            self._record("action_blocked", action, reason="confirmation_denied")
            raise ConfirmationRequiredError(action.describe(), action.risk.value)

        detail = self._executor.execute(action)
        self._record("action_executed", action, detail=detail)
        return ActionResult(action=action, executed=True, detail=detail)

    def run_plan(self, actions: tuple[Action, ...]) -> tuple[ActionResult, ...]:
        """Execute a plan in order, stopping at the first blocked action.

        Returns results for the actions that ran; the blocked one is reported
        via the raised error.
        """
        results: list[ActionResult] = []
        for action in actions:
            results.append(self.run_one(action))
        return tuple(results)


class AuditSink(Protocol):
    """The subset of AuditLog that ActionGate needs."""

    def append(self, event: str, **payload: object) -> object:
        ...


def summarize_plan(actions: tuple[Action, ...]) -> dict[str, int]:
    """Count actions by risk level, for a pre-flight summary."""
    tally = {level.value: 0 for level in RiskLevel}
    for action in actions:
        tally[action.risk.value] += 1
    return tally


def redact(action: Action, *, keep: int = 4) -> Action:
    """Return a copy with the value masked, for logging or display."""
    if not action.value:
        return action
    visible = action.value[:keep]
    return replace(action, value=f"{visible}{'*' * max(0, len(action.value) - keep)}")
