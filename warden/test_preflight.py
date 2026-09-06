import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
from preflight import databricks_readiness, render_human, report  # noqa: E402


ENVIRONMENT = {
    "DATABRICKS_SERVER_HOSTNAME": "host",
    "DATABRICKS_HTTP_PATH": "path",
    "DATABRICKS_TOKEN": "SECRET_TOKEN_VALUE",
}


def test_preflight_reports_both_services_ready_without_exposing_credentials():
    with patch("preflight.run_entire", return_value=("[]", None)):
        result = report(environment=ENVIRONMENT)
    output = render_human(result) + json.dumps(result)
    assert result["ready"] is True
    assert result["entire"]["state"] == "ready"
    assert result["databricks"]["state"] == "configured"
    assert "SECRET_TOKEN_VALUE" not in output


def test_preflight_labels_unavailable_entire_and_missing_databricks_configuration():
    with patch("preflight.run_entire", return_value=(None, "do not print this")):
        result = report(environment={})
    assert result["ready"] is False
    assert result["entire"] == {"state": "unavailable"}
    assert result["databricks"]["missing"] == [
        "DATABRICKS_SERVER_HOSTNAME",
        "DATABRICKS_HTTP_PATH",
        "DATABRICKS_TOKEN",
    ]


def test_live_preflight_reduces_database_error_to_its_type():
    class SensitiveError(RuntimeError):
        pass

    with patch("preflight.run_entire", return_value=("[]", None)), \
         patch("preflight.databricks_readiness", return_value={"state": "unavailable", "error_type": "SensitiveError"}):
        result = report(live=True, environment=ENVIRONMENT)
    assert "SensitiveError" in render_human(result)
    assert "SECRET_TOKEN_VALUE" not in json.dumps(result)


def test_databricks_preflight_does_not_connect_without_live_flag():
    assert databricks_readiness(environment=ENVIRONMENT) == {"state": "configured"}
