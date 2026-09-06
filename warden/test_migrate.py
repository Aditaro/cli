"""Unit tests for Warden's checkpoint/graph logic (no live Databricks needed).

Run: python3 -m pytest warden/test_migrate.py -v
"""
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
from migrate import get_latest_checkpoint, graph_impact, run_entire  # noqa: E402


def _fake_run(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_get_latest_checkpoint_skips_pending_shadow_entries():
    checkpoints = [
        {"checkpoint_id": "64a7d4c812988756485531f299aba5bc7f2af23b", "message": "live shadow, not committed"},
        {"checkpoint_id": "01M1TJNMKW7CKJ4NJ8BY6VCQ6B", "agent": "Claude Code", "is_logs_only": True, "message": "Pivot to Warden"},
    ]

    def fake_subprocess_run(cmd, **kwargs):
        if cmd[:3] == ["entire", "checkpoint", "list"]:
            return _fake_run(stdout=json.dumps(checkpoints))
        if cmd[:3] == ["entire", "checkpoint", "explain"]:
            assert cmd[3] == "01M1TJNMKW7CKJ4NJ8BY6VCQ6B", "must use the committed checkpoint, not the pending one"
            return _fake_run(stdout="## Intent\nPivot to Warden")
        raise AssertionError(f"unexpected command {cmd}")

    with patch("subprocess.run", side_effect=fake_subprocess_run):
        cp_id, intent = get_latest_checkpoint()

    assert cp_id == "01M1TJNMKW7CKJ4NJ8BY6VCQ6B"
    assert "Pivot to Warden" in intent


def test_get_latest_checkpoint_degrades_gracefully_when_entire_unavailable():
    with patch("subprocess.run", side_effect=FileNotFoundError("entire: command not found")):
        cp_id, intent = get_latest_checkpoint()
    assert cp_id is None
    assert intent is None


def test_get_latest_checkpoint_degrades_gracefully_on_malformed_json():
    with patch("subprocess.run", return_value=_fake_run(stdout="not json")):
        cp_id, intent = get_latest_checkpoint()
    assert cp_id is None
    assert intent is None


def test_graph_impact_never_asserts_unavailable_output_as_fact():
    with patch("subprocess.run", return_value=_fake_run(returncode=1, stderr="timed out")):
        result = graph_impact("demo_users")
    assert "unavailable" in result
    assert "timed out" in result


def test_graph_impact_returns_raw_output_on_success():
    with patch("subprocess.run", return_value=_fake_run(stdout="  callers: none  \n")):
        result = graph_impact("demo_users")
    assert result == "callers: none"


def test_run_entire_never_raises_on_timeout():
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="entire", timeout=30)):
        out, err = run_entire(["graph", "impact", "--symbol", "x"])
    assert out is None
    assert "30" in err or "Timeout" in err or "timed out" in err.lower()
