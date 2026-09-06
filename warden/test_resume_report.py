import sys
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).parent))
from migrate import LocalOnlyText  # noqa: E402
from resume_report import checkpoint_context, render_report  # noqa: E402


def test_resume_report_never_reveals_checkpoint_intent():
    secret = "SECRET_INTENT_MARKER: do not expose this"
    report = render_report(
        "cp1",
        LocalOnlyText(secret),
        "complete",
        "migrations/001_add_plan_column.sql",
        "warden.demo_users",
        None,
        "unavailable (Databricks credentials not set)",
    )

    assert secret not in report
    assert "Context completeness: complete" in report
    assert "Recommended next action: proceed" in report


def test_checkpoint_context_uses_existing_completeness_classifier():
    with patch(
        "resume_report.run_entire",
        return_value=("checkpoint has [REDACTED_EMAIL]", None),
    ):
        intent, completeness = checkpoint_context("cp1")

    assert completeness == "redacted"
    assert "REDACTED_EMAIL" not in str(intent)
