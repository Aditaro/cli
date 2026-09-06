"""Create or update the Warden migration-health AI/BI dashboard."""

import json
import os
import re
import sys
import uuid
from pathlib import Path

import requests


DASHBOARD_NAME = "Warden Migration Health"
API_PATH = "/api/2.0/lakeview/dashboards"


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} must be exported")
    return value


def warehouse_id(http_path: str) -> str:
    explicit = os.environ.get("DATABRICKS_WAREHOUSE_ID")
    if explicit:
        return explicit
    match = re.search(r"/warehouses/([^/]+)", http_path)
    if not match:
        raise RuntimeError(
            "DATABRICKS_WAREHOUSE_ID is required when DATABRICKS_HTTP_PATH "
            "does not contain /warehouses/<id>"
        )
    return match.group(1)


def dashboard_definition(query: str) -> str:
    dataset_name = uuid.uuid4().hex[:8]
    page_name = uuid.uuid4().hex[:8]
    widget_name = uuid.uuid4().hex[:8]
    fields = ["day", "attempts", "heals", "failures"]
    serialized = {
        "datasets": [
            {
                "name": dataset_name,
                "displayName": "Migration attempts and heals",
                "query": query,
            }
        ],
        "pages": [
            {
                "name": page_name,
                "displayName": "Migration health",
                "layout": [
                    {
                        "widget": {
                            "name": widget_name,
                            "queries": [
                                {
                                    "name": "main_query",
                                    "query": {
                                        "datasetName": dataset_name,
                                        "fields": [
                                            {
                                                "name": field,
                                                "expression": f"`{field}`",
                                            }
                                            for field in fields
                                        ],
                                        "disaggregated": False,
                                    },
                                }
                            ],
                            "spec": {
                                "version": 3,
                                "widgetType": "bar",
                                "encodings": {
                                    "x": {
                                        "fieldName": "day",
                                        "scale": {"type": "temporal"},
                                        "displayName": "Day",
                                    },
                                    "y": {
                                        "scale": {"type": "quantitative"},
                                        "fields": [
                                            {
                                                "fieldName": field,
                                                "displayName": field.title(),
                                            }
                                            for field in fields[1:]
                                        ],
                                    },
                                },
                                "mark": {"layout": "group"},
                                "frame": {
                                    "showTitle": True,
                                    "title": "Migration attempts, heals, and failures",
                                },
                            },
                        },
                        "position": {"x": 0, "y": 0, "width": 6, "height": 6},
                    }
                ],
            }
        ],
    }
    return json.dumps(serialized, separators=(",", ":"))


def request_json(
    session: requests.Session, method: str, url: str, **kwargs: object
) -> dict:
    response = session.request(method, url, timeout=30, **kwargs)
    if not response.ok:
        raise RuntimeError(f"Databricks API {response.status_code}: {response.text}")
    if not response.content:
        return {}
    return response.json()


def main() -> int:
    host = required_env("DATABRICKS_SERVER_HOSTNAME").removeprefix("https://")
    token = required_env("DATABRICKS_TOKEN")
    http_path = required_env("DATABRICKS_HTTP_PATH")
    query_path = Path(__file__).with_name("dashboard_queries.sql")
    query = query_path.read_text(encoding="utf-8").strip()
    warehouse = warehouse_id(http_path)
    serialized = dashboard_definition(query)

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}"})
    base_url = f"https://{host}{API_PATH}"
    dashboards = request_json(session, "GET", base_url, params={"page_size": 100})
    existing = next(
        (
            dashboard
            for dashboard in dashboards.get("dashboards", [])
            if dashboard.get("display_name") == DASHBOARD_NAME
        ),
        None,
    )
    body = {
        "display_name": DASHBOARD_NAME,
        "warehouse_id": warehouse,
        "serialized_dashboard": serialized,
    }
    if existing:
        dashboard = request_json(
            session,
            "PATCH",
            f"{base_url}/{existing['dashboard_id']}",
            json=body,
        )
        action = "updated"
    else:
        dashboard = request_json(session, "POST", base_url, json=body)
        action = "created"

    dashboard_id = dashboard["dashboard_id"]
    print(f"Dashboard {action}: {DASHBOARD_NAME}")
    print(f"Workspace URL: https://{host}/dashboardsv3/{dashboard_id}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, requests.RequestException, RuntimeError, KeyError) as exc:
        print(f"create_dashboard.py: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
