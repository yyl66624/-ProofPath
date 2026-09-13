"""Hash-chained audit log.

Every consequential step - document parsed, verdict downgraded, form field
filled, submission confirmed - is appended here. Entries are chained by hash, so
a later edit to any entry invalidates every entry after it and `verify_chain`
reports exactly where the break is.

This is append-only by construction: there is no update or delete method.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .errors import AuditChainBrokenError

GENESIS_HASH = "0" * 64
_SENSITIVE_KEYS = ("api_key", "token", "password", "secret", "authorization", "credential", "private_key")


def _is_sensitive_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    compact = key.lower().replace("-", "").replace("_", "")
    return any(marker.replace("_", "") in compact for marker in _SENSITIVE_KEYS)


def _redact_sensitive(value: Any) -> Any:
    """Remove credential fields before an entry is hashed or persisted.

    This protects structured audit payloads; callers must still avoid putting
    secrets in free-text fields such as error messages.
    """
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if _is_sensitive_key(key)
                else _redact_sensitive(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_sensitive(item) for item in value]
    return value


def _canonical(payload: dict[str, Any]) -> str:
    """Deterministic JSON: sorted keys, no incidental whitespace.

    Determinism matters - if serialization varied, a re-computed hash would not
    match the stored one and every chain would look broken.
    """
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """One immutable record in the chain."""

    index: int
    timestamp: str
    event: str
    payload: dict[str, Any]
    prev_hash: str
    entry_hash: str

    def compute_hash(self) -> str:
        """Recompute this entry's hash from its own contents."""
        material = _canonical(
            {
                "index": self.index,
                "timestamp": self.timestamp,
                "event": self.event,
                "payload": self.payload,
                "prev_hash": self.prev_hash,
            }
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "event": self.event,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditEntry:
        try:
            return cls(
                index=int(data["index"]),
                timestamp=str(data["timestamp"]),
                event=str(data["event"]),
                payload=dict(data["payload"]),
                prev_hash=str(data["prev_hash"]),
                entry_hash=str(data["entry_hash"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AuditChainBrokenError(f"malformed audit entry: {exc}") from exc


@dataclass
class AuditLog:
    """Append-only chain, optionally mirrored to a JSONL file."""

    path: Path | None = None
    _entries: list[AuditEntry] = field(default_factory=list, repr=False)

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[AuditEntry]:
        return iter(tuple(self._entries))

    @property
    def entries(self) -> tuple[AuditEntry, ...]:
        """Snapshot of the chain; mutating the result cannot affect the log."""
        return tuple(self._entries)

    @property
    def head_hash(self) -> str:
        return self._entries[-1].entry_hash if self._entries else GENESIS_HASH

    def append(self, event: str, **payload: Any) -> AuditEntry:
        """Add an entry and return it."""
        if not event:
            raise ValueError("audit event name must not be empty")

        index = len(self._entries)
        draft = AuditEntry(
            index=index,
            timestamp=datetime.now(timezone.utc).isoformat(),
            event=event,
            payload=_redact_sensitive(payload),
            prev_hash=self.head_hash,
            entry_hash="",
        )
        entry = AuditEntry(
            index=draft.index,
            timestamp=draft.timestamp,
            event=draft.event,
            payload=draft.payload,
            prev_hash=draft.prev_hash,
            entry_hash=draft.compute_hash(),
        )
        self._entries.append(entry)
        self._flush(entry)
        return entry

    def _flush(self, entry: AuditEntry) -> None:
        """Append one line to the mirror file, if configured."""
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry.to_dict(), ensure_ascii=False, sort_keys=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def verify_chain(self) -> None:
        """Raise AuditChainBrokenError at the first inconsistency."""
        expected_prev = GENESIS_HASH
        for position, entry in enumerate(self._entries):
            if entry.index != position:
                raise AuditChainBrokenError(
                    f"entry at position {position} claims index {entry.index}"
                )
            if entry.prev_hash != expected_prev:
                raise AuditChainBrokenError(
                    f"entry {entry.index}: prev_hash does not match entry {position - 1}"
                )
            if entry.compute_hash() != entry.entry_hash:
                raise AuditChainBrokenError(
                    f"entry {entry.index}: contents do not match its stored hash"
                )
            expected_prev = entry.entry_hash

    @classmethod
    def load(cls, path: str | Path) -> AuditLog:
        """Read a JSONL log back and verify it before returning."""
        file_path = Path(path).expanduser()
        entries: list[AuditEntry] = []
        try:
            raw = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise AuditChainBrokenError(f"cannot read audit log: {exc}") from exc

        for line_number, line in enumerate(raw.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                entries.append(AuditEntry.from_dict(json.loads(stripped)))
            except json.JSONDecodeError as exc:
                raise AuditChainBrokenError(
                    f"line {line_number} is not valid JSON: {exc}"
                ) from exc

        log = cls(path=file_path, _entries=entries)
        log.verify_chain()
        return log
