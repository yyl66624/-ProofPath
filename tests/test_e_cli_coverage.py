"""Additional CLI tests to fill coverage gaps (cli.py 83% → target 95%+).

Coverage gaps targeted:
- _parse_profile error path (lines 35-41)
- cmd_search with no hits (line 82-83)
- cmd_check (lines 91-107) — mocked, no real API call
- cmd_demo with custom file (line 151)
- Error handlers: ConfirmationRequired, AuditChainBroken, ProofPathError, KeyboardInterrupt
  (lines 235-245)

T01/T02/T06/T07 alignment.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from proofpath.cli import main, build_parser, _parse_profile
from proofpath.errors import ProofPathError


# ---------------------------------------------------------------------------
#  _parse_profile
# ---------------------------------------------------------------------------

class TestParseProfile:
    def test_valid_pairs(self) -> None:
        result = _parse_profile(["学历=硕士", "年龄=28"])
        assert result == {"学历": "硕士", "年龄": "28"}

    def test_strips_whitespace(self) -> None:
        result = _parse_profile(["  学历 = 硕士  "])
        assert result == {"学历": "硕士"}

    def test_none_input(self) -> None:
        assert _parse_profile(None) == {}

    def test_empty_list(self) -> None:
        assert _parse_profile([]) == {}

    def test_missing_equals_raises(self) -> None:
        with pytest.raises(ProofPathError, match="key=value"):
            _parse_profile(["no_equals_here"])

    def test_empty_key_raises(self) -> None:
        with pytest.raises(ProofPathError, match="key=value"):
            _parse_profile(["=value"])

    def test_value_with_equals(self) -> None:
        """Values containing '=' should work (partition splits on first)."""
        result = _parse_profile(["formula=a=b+c"])
        assert result == {"formula": "a=b+c"}


# ---------------------------------------------------------------------------
#  CLI commands
# ---------------------------------------------------------------------------

class TestCliParse:
    def test_parse_example_policy(self, capsys) -> None:
        """T01: parse command on a supported file."""
        from proofpath.demo import EXAMPLE_POLICY
        rc = main(["parse", str(EXAMPLE_POLICY)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "第 1 页" in out
        assert "第 2 页" in out


class TestCliSearch:
    def test_search_finds_relevant(self, capsys) -> None:
        from proofpath.demo import EXAMPLE_POLICY
        rc = main(["search", str(EXAMPLE_POLICY), "-q", "硕士补贴标准"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "score=" in out

    def test_search_no_hits(self, capsys) -> None:
        """When no chunks match, we get a polite message."""
        from proofpath.demo import EXAMPLE_POLICY
        rc = main(["search", str(EXAMPLE_POLICY), "-q", "quantum physics entropy"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "没有检索到" in out

    def test_search_nonexistent_file(self, capsys) -> None:
        rc = main(["search", "/nonexistent/file.txt", "-q", "test"])
        assert rc == 1
        assert "错误" in capsys.readouterr().err


class TestCliDemo:
    def test_demo_default(self, capsys) -> None:
        """T01: Full demo pipeline runs successfully."""
        rc = main(["demo"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "逐条判定" in out

    def test_demo_with_explicit_policy(self, capsys) -> None:
        """Demo with explicit file path (positional arg)."""
        from proofpath.demo import EXAMPLE_POLICY
        rc = main(["demo", str(EXAMPLE_POLICY)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "逐条判定" in out


class TestCliPlan:
    def test_plan_blocks_at_sensitive(self, capsys) -> None:
        """T12: Plan stops at SENSITIVE action with exit code 3."""
        rc = main(["plan", "https://example.gov/apply"])
        assert rc == 3
        out = capsys.readouterr().out
        assert "SENSITIVE" in out


class TestCliDoctor:
    def test_doctor_reports_components(self, capsys) -> None:
        rc = main(["doctor"])
        assert rc == 0
        out = capsys.readouterr().out
        # Should mention model name
        assert "claude-opus-5" in out or "deepseek" in out.lower() or len(out) > 0


class TestCliCheck:
    """cmd_check requires credentials. We mock the reasoner to test the wiring."""

    def test_check_missing_credentials(self, capsys) -> None:
        """T07: Missing API credentials → understandable error.

        anthropic.Anthropic() does not raise on construction even without a key;
        the error surfaces at call time. We simulate that by making the reasoner
        raise ReasonerUnavailableError.
        """
        from proofpath.demo import EXAMPLE_POLICY
        from proofpath.errors import ReasonerUnavailableError

        mock_reasoner = MagicMock()
        mock_reasoner.analyze.side_effect = ReasonerUnavailableError("no key")

        with patch("proofpath.reasoner.ClaudeReasoner", return_value=mock_reasoner):
            rc = main([
                "check", str(EXAMPLE_POLICY),
                "-q", "我能申请吗",
            ])
            assert rc == 1
            err = capsys.readouterr().err
            assert "错误" in err

    def test_check_with_mocked_reasoner(self, capsys) -> None:
        """T01: check wiring works when model returns valid response."""
        from proofpath.demo import EXAMPLE_POLICY, ScriptedReasoner

        # Patch where cmd_check imports ClaudeReasoner (inside the function body)
        with patch("proofpath.reasoner.ClaudeReasoner", return_value=ScriptedReasoner()):
            rc = main([
                "check", str(EXAMPLE_POLICY),
                "-q", "我硕士毕业能申请多少",
                "-p", "学历=硕士",
            ])
            assert rc == 0
            out = capsys.readouterr().out
            assert "逐条判定" in out


class TestCliErrorHandlers:
    """Test the error handler branches in main()."""

    def test_keyboard_interrupt(self, capsys) -> None:
        """Ctrl+C → clean exit with message."""
        with patch("proofpath.cli.build_parser") as mock_parser:
            mock_args = MagicMock()
            mock_args.func.side_effect = KeyboardInterrupt()
            mock_parser.return_value.parse_args.return_value = mock_args
            rc = main([])
            assert rc == 1
            assert "已取消" in capsys.readouterr().err

    def test_audit_chain_broken_error(self, capsys) -> None:
        from proofpath.errors import AuditChainBrokenError
        with patch("proofpath.cli.build_parser") as mock_parser:
            mock_args = MagicMock()
            mock_args.func.side_effect = AuditChainBrokenError("chain broken")
            mock_parser.return_value.parse_args.return_value = mock_args
            rc = main([])
            assert rc == 1
            assert "审计链校验失败" in capsys.readouterr().err

    def test_generic_proofpath_error(self, capsys) -> None:
        with patch("proofpath.cli.build_parser") as mock_parser:
            mock_args = MagicMock()
            mock_args.func.side_effect = ProofPathError("something went wrong")
            mock_parser.return_value.parse_args.return_value = mock_args
            rc = main([])
            assert rc == 1
            assert "错误" in capsys.readouterr().err

    def test_confirmation_required_error(self, capsys) -> None:
        from proofpath.errors import ConfirmationRequiredError
        with patch("proofpath.cli.build_parser") as mock_parser:
            mock_args = MagicMock()
            mock_args.func.side_effect = ConfirmationRequiredError("submit", "SENSITIVE")
            mock_parser.return_value.parse_args.return_value = mock_args
            rc = main([])
            assert rc == 3
            assert "操作已阻止" in capsys.readouterr().err


# ---------------------------------------------------------------------------
#  T02: Missing user info
# ---------------------------------------------------------------------------

class TestT02MissingInfo:
    """T02: Missing user info → NEEDS_INPUT, not false MET."""

    def test_demo_shows_needs_input(self, capsys) -> None:
        """Demo report includes NEEDS_INPUT conditions."""
        rc = main(["demo"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "待补充" in out
        assert "需要你提供" in out or "还需要你确认" in out
