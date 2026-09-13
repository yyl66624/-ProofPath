"""Tests for the confirmation gate and the audit chain."""
from __future__ import annotations

import json

import pytest

from proofpath.actions import (
    Action,
    ActionGate,
    DryRunExecutor,
    classify,
    redact,
    summarize_plan,
)
from proofpath.audit import GENESIS_HASH, AuditEntry, AuditLog
from proofpath.errors import AuditChainBrokenError, ConfirmationRequiredError
from proofpath.models import RiskLevel


class TestClassify:
    @pytest.mark.parametrize("kind", ["navigate", "read", "screenshot", "scroll", "extract"])
    def test_read_only_kinds(self, kind: str) -> None:
        assert classify(kind, "https://example.gov") is RiskLevel.READ_ONLY

    @pytest.mark.parametrize("kind", ["fill", "type", "select", "check"])
    def test_local_write_kinds(self, kind: str) -> None:
        assert classify(kind, "姓名", "张三") is RiskLevel.LOCAL_WRITE

    @pytest.mark.parametrize(
        "kind,target",
        [
            ("submit", "申请"),
            ("upload", "证书"),
            ("pay", "手续费"),
            ("delete", "草稿"),
        ],
    )
    def test_sensitive_kinds(self, kind: str, target: str) -> None:
        assert classify(kind, target) is RiskLevel.SENSITIVE

    def test_unknown_kind_defaults_to_sensitive(self) -> None:
        """Deny by default: an unrecognized verb must not slip through."""
        assert classify("frobnicate", "something") is RiskLevel.SENSITIVE

    def test_sensitive_target_escalates_a_safe_kind(self) -> None:
        """Typing into a payment field is not a mere local write."""
        assert classify("fill", "支付密码", "1234") is RiskLevel.SENSITIVE

    def test_chinese_markers_escalate(self) -> None:
        assert classify("click", "提交按钮") is RiskLevel.SENSITIVE

    def test_case_insensitive(self) -> None:
        assert classify("SUBMIT") is RiskLevel.SENSITIVE
        assert classify("Navigate", "https://x.gov") is RiskLevel.READ_ONLY


class TestAction:
    def test_describe_truncates_long_values(self) -> None:
        action = Action(kind="fill", target="身份证号", value="11010119900307123X")
        described = action.describe()
        assert "11010119900" in described
        assert "123X" not in described  # full ID must not be echoed

    def test_redact_masks_value(self) -> None:
        masked = redact(Action(kind="fill", target="卡号", value="6222021234567890"))
        assert masked.value.startswith("6222")
        assert masked.value.endswith("*")
        assert "567890" not in masked.value

    def test_redact_noop_on_empty_value(self) -> None:
        action = Action(kind="navigate", target="https://x.gov")
        assert redact(action) is action

    def test_summarize_plan(self) -> None:
        plan = (
            Action("navigate", "https://x.gov"),
            Action("fill", "姓名", "张三"),
            Action("submit", "申请"),
        )
        tally = summarize_plan(plan)
        assert tally["READ_ONLY"] == 1
        assert tally["LOCAL_WRITE"] == 1
        assert tally["SENSITIVE"] == 1


class TestActionGate:
    def test_safe_actions_run_without_confirmation(self) -> None:
        executor = DryRunExecutor()
        gate = ActionGate(executor)
        plan = (Action("navigate", "https://x.gov"), Action("fill", "姓名", "张三"))
        results = gate.run_plan(plan)
        assert len(results) == 2
        assert all(r.executed for r in results)
        assert len(executor.seen) == 2

    def test_sensitive_action_blocked_by_default(self) -> None:
        executor = DryRunExecutor()
        gate = ActionGate(executor)
        with pytest.raises(ConfirmationRequiredError):
            gate.run_one(Action("submit", "提交申请"))
        assert executor.seen == ()  # nothing ran

    def test_sensitive_action_runs_when_confirmed(self) -> None:
        executor = DryRunExecutor()
        gate = ActionGate(executor, confirm=lambda _: True)
        result = gate.run_one(Action("submit", "提交申请"))
        assert result.executed
        assert len(executor.seen) == 1

    def test_plan_stops_at_first_blocked_action(self) -> None:
        """A partially-run plan must not be mistaken for a completed one."""
        executor = DryRunExecutor()
        gate = ActionGate(executor)
        plan = (
            Action("navigate", "https://x.gov"),
            Action("fill", "姓名", "张三"),
            Action("submit", "提交"),
            Action("read", "结果"),
        )
        with pytest.raises(ConfirmationRequiredError):
            gate.run_plan(plan)
        assert len(executor.seen) == 2  # the two safe steps only

    def test_blocked_action_is_audited(self) -> None:
        log = AuditLog()
        gate = ActionGate(DryRunExecutor(), audit=log)
        with pytest.raises(ConfirmationRequiredError):
            gate.run_one(Action("submit", "提交申请"))
        assert len(log) == 1
        assert log.entries[0].event == "action_blocked"
        assert log.entries[0].payload["reason"] == "confirmation_denied"

    def test_executed_action_is_audited(self) -> None:
        log = AuditLog()
        gate = ActionGate(DryRunExecutor(), audit=log)
        gate.run_one(Action("navigate", "https://x.gov"))
        assert log.entries[0].event == "action_executed"
        assert log.entries[0].payload["risk"] == "READ_ONLY"


class TestAuditLog:
    def test_chain_links_entries(self) -> None:
        log = AuditLog()
        first = log.append("document_parsed", doc_id="d1")
        second = log.append("report_verified", rejected=1)
        assert first.prev_hash == GENESIS_HASH
        assert second.prev_hash == first.entry_hash
        log.verify_chain()

    def test_empty_log_verifies(self) -> None:
        AuditLog().verify_chain()

    def test_head_hash_of_empty_log(self) -> None:
        assert AuditLog().head_hash == GENESIS_HASH

    def test_empty_event_name_rejected(self) -> None:
        with pytest.raises(ValueError):
            AuditLog().append("")

    def test_tampered_payload_breaks_chain(self) -> None:
        log = AuditLog()
        log.append("action_executed", target="申请表")
        log.append("action_executed", target="提交")
        original = log.entries[0]
        # Simulate an edit to history: same hash, different contents.
        forged = AuditEntry(
            index=original.index,
            timestamp=original.timestamp,
            event=original.event,
            payload={"target": "别的东西"},
            prev_hash=original.prev_hash,
            entry_hash=original.entry_hash,
        )
        tampered = AuditLog(_entries=[forged, log.entries[1]])
        with pytest.raises(AuditChainBrokenError, match="do not match its stored hash"):
            tampered.verify_chain()

    def test_removed_entry_breaks_chain(self) -> None:
        log = AuditLog()
        log.append("a")
        log.append("b")
        log.append("c")
        truncated = AuditLog(_entries=[log.entries[0], log.entries[2]])
        with pytest.raises(AuditChainBrokenError):
            truncated.verify_chain()

    def test_entries_snapshot_is_immutable(self) -> None:
        log = AuditLog()
        log.append("a")
        snapshot = log.entries
        log.append("b")
        assert len(snapshot) == 1
        assert len(log.entries) == 2

    def test_roundtrip_through_file(self, tmp_path) -> None:
        path = tmp_path / "audit.jsonl"
        log = AuditLog(path=path)
        log.append("document_parsed", doc_id="d1", parser="pypdf")
        log.append("action_blocked", reason="confirmation_denied")
        reloaded = AuditLog.load(path)
        assert len(reloaded) == 2
        assert reloaded.entries[0].payload["doc_id"] == "d1"
        assert reloaded.head_hash == log.head_hash

    def test_load_detects_tampered_file(self, tmp_path) -> None:
        path = tmp_path / "audit.jsonl"
        log = AuditLog(path=path)
        log.append("action_executed", target="提交申请")
        lines = path.read_text(encoding="utf-8").splitlines()
        record = json.loads(lines[0])
        record["payload"]["target"] = "改过的内容"
        path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
        with pytest.raises(AuditChainBrokenError):
            AuditLog.load(path)

    def test_load_rejects_invalid_json(self, tmp_path) -> None:
        path = tmp_path / "audit.jsonl"
        path.write_text("{not json}\n", encoding="utf-8")
        with pytest.raises(AuditChainBrokenError, match="not valid JSON"):
            AuditLog.load(path)

    def test_load_rejects_malformed_entry(self, tmp_path) -> None:
        path = tmp_path / "audit.jsonl"
        path.write_text(json.dumps({"index": 0}) + "\n", encoding="utf-8")
        with pytest.raises(AuditChainBrokenError, match="malformed"):
            AuditLog.load(path)

    def test_load_missing_file(self, tmp_path) -> None:
        with pytest.raises(AuditChainBrokenError, match="cannot read"):
            AuditLog.load(tmp_path / "nope.jsonl")

    def test_unicode_survives_roundtrip(self, tmp_path) -> None:
        path = tmp_path / "audit.jsonl"
        log = AuditLog(path=path)
        log.append("report_verified", note="第2页引用无法核验")
        assert AuditLog.load(path).entries[0].payload["note"] == "第2页引用无法核验"
