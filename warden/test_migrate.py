"""Unit tests for Warden's checkpoint/graph logic (no live Databricks needed).

Run: python3 -m pytest warden/test_migrate.py -v
"""
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
from migrate import (  # noqa: E402
    LocalOnlyText,
    classify_completeness,
    describe_failure,
    error_summary,
    get_latest_checkpoint,
    graph_impact,
    run_entire,
)


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
        cp_id, intent, completeness = get_latest_checkpoint()

    assert cp_id == "01M1TJNMKW7CKJ4NJ8BY6VCQ6B"
    assert isinstance(intent, LocalOnlyText)
    assert "Pivot to Warden" in intent.reveal()
    assert completeness == "complete"


def test_get_latest_checkpoint_degrades_gracefully_when_entire_unavailable():
    with patch("subprocess.run", side_effect=FileNotFoundError("entire: command not found")):
        cp_id, intent, completeness = get_latest_checkpoint()
    assert cp_id is None
    assert isinstance(intent, LocalOnlyText)
    assert intent.reveal() is None
    assert completeness == "unavailable"


def test_get_latest_checkpoint_degrades_gracefully_on_malformed_json():
    with patch("subprocess.run", return_value=_fake_run(stdout="not json")):
        cp_id, intent, completeness = get_latest_checkpoint()
    assert cp_id is None
    assert isinstance(intent, LocalOnlyText)
    assert intent.reveal() is None
    assert completeness == "unavailable"


def test_get_latest_checkpoint_flags_redacted_intent():
    checkpoints = [{"checkpoint_id": "01M1TJNMKW7CKJ4NJ8BY6VCQ6B", "agent": "Claude Code"}]

    def fake_subprocess_run(cmd, **kwargs):
        if cmd[:3] == ["entire", "checkpoint", "list"]:
            return _fake_run(stdout=json.dumps(checkpoints))
        if cmd[:3] == ["entire", "checkpoint", "explain"]:
            return _fake_run(stdout="## Intent\nRotate the [REDACTED_EMAIL] account's plan")
        raise AssertionError(f"unexpected command {cmd}")

    with patch("subprocess.run", side_effect=fake_subprocess_run):
        cp_id, intent, completeness = get_latest_checkpoint()

    assert cp_id == "01M1TJNMKW7CKJ4NJ8BY6VCQ6B"
    assert completeness == "redacted"


def test_classify_completeness():
    assert classify_completeness(None, None) == "unavailable"
    assert classify_completeness("cp1", None) == "unavailable"
    assert classify_completeness("cp1", "plain intent text") == "complete"
    assert classify_completeness("cp1", "touched the REDACTED field") == "redacted"
    assert classify_completeness("cp1", "[REDACTED_EMAIL] signed up") == "redacted"


def test_describe_failure_never_leaks_raw_intent_to_db_note():
    """The db_note is what reaches Databricks -- an external service outside
    Entire's own boundary. It must never carry the checkpoint intent text,
    even when that intent is fully available (not just when redacted)."""
    secret_intent = "SECRET_INTENT_MARKER: only free/pro/enterprise plans are allowed"
    console_text, db_note = describe_failure(
        "migrations/001_add_plan_column.sql", RuntimeError("boom"), "warden.demo_users",
        "3", "cp1", LocalOnlyText(secret_intent), "complete",
    )
    assert secret_intent not in db_note
    assert "complete" in db_note
    # sanity check the test isn't vacuous: the console text does carry it
    assert secret_intent in console_text


def test_local_only_text_fails_safe_by_default():
    """The structural guarantee this session's privacy work rests on: naive
    misuse (interpolating the wrapper directly into an f-string, the same
    mistake that would leak intent into db_note) yields the placeholder, not
    the real text. Only the explicit .reveal() call gets the real text back."""
    secret = LocalOnlyText("SECRET_INTENT_MARKER: do not leak this")
    accidental_leak = f"migration note: {secret}"
    assert "SECRET_INTENT_MARKER" not in accidental_leak
    assert "SECRET_INTENT_MARKER" in secret.reveal()
    assert bool(secret) is True
    assert bool(LocalOnlyText(None)) is False


def test_describe_failure_never_leaks_raw_error_text_to_db_note():
    """Delta's own CHECK-constraint violation message
    (DELTA_VIOLATE_CONSTRAINT_WITH_VALUES) embeds the offending row's actual
    column values -- e.g. 'CHECK ... violated by row with values: plan=legacy'.
    That's the same leak shape as raw checkpoint intent, through a different
    door: db_note must reduce it to the exception's type name, never its
    message text, while the console text (local-only) may still show it in
    full for operator triage."""
    error = ValueError("CHECK constraint demo_users_valid_plan violated by row with values: plan = SENSITIVE_VALUE")
    console_text, db_note = describe_failure(
        "migrations/001_add_plan_column.sql", error, "warden.demo_users",
        "3", "cp1", LocalOnlyText("some intent"), "complete",
    )
    assert "SENSITIVE_VALUE" not in db_note
    assert "ValueError" in db_note
    assert "SENSITIVE_VALUE" in console_text


def test_error_summary_returns_type_name_only():
    assert error_summary(ValueError("plan = SENSITIVE_VALUE")) == "ValueError"
    assert error_summary(RuntimeError("boom")) == "RuntimeError"


def test_describe_failure_with_redacted_or_missing_checkpoint():
    """Constraint: keep working (usefully) when checkpoint fields are
    redacted/unavailable, and never present that partial context as complete."""
    for intent, completeness in [("[REDACTED_EMAIL] wants a plan change", "redacted"), (None, "unavailable")]:
        console_text, db_note = describe_failure(
            "migrations/001_add_plan_column.sql", RuntimeError("boom"), "warden.demo_users",
            "3", "cp1", LocalOnlyText(intent), completeness,
        )
        assert completeness in db_note
        assert completeness in console_text
        assert "REDACTED" not in db_note


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
