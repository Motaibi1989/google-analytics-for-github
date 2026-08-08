#!/usr/bin/env python3
"""Fetch aggregate GA4 metrics and publish JSON/badge files for GitHub."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import DateRange, Metric, RunReportRequest
from google.oauth2 import service_account

ROOT = Path(__file__).resolve().parents[1]
STATS_DIR = ROOT / "stats"
ANALYTICS_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
DEFAULT_START_DATE = "2020-10-14"


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def build_client(service_account_json: str) -> BetaAnalyticsDataClient:
    try:
        service_account_info = json.loads(service_account_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON") from exc

    credentials = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=[ANALYTICS_SCOPE],
    )
    return BetaAnalyticsDataClient(credentials=credentials)


def fetch_metrics(
    client: BetaAnalyticsDataClient,
    property_id: str,
    start_date: str,
    end_date: str,
    metric_names: Iterable[str],
) -> dict[str, int]:
    names = list(metric_names)
    request = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        metrics=[Metric(name=name) for name in names],
    )

    response = client.run_report(request)
    if not response.rows:
        return {name: 0 for name in names}

    values = response.rows[0].metric_values
    return {name: int(float(values[index].value or 0)) for index, name in enumerate(names)}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def badge(label: str, value: int) -> dict:
    return {
        "schemaVersion": 1,
        "label": label,
        "message": f"{value:,}",
    }


def main() -> None:
    property_id = required_env("GA_PROPERTY_ID")
    service_account_json = required_env("GOOGLE_SERVICE_ACCOUNT_JSON")
    start_date = os.getenv("GA_START_DATE", "").strip() or DEFAULT_START_DATE

    client = build_client(service_account_json)

    all_time = fetch_metrics(
        client=client,
        property_id=property_id,
        start_date=start_date,
        end_date="yesterday",
        metric_names=["totalUsers", "screenPageViews"],
    )

    last_30_days = fetch_metrics(
        client=client,
        property_id=property_id,
        start_date="30daysAgo",
        end_date="yesterday",
        metric_names=["activeUsers", "sessions", "screenPageViews"],
    )

    stats = {
        "source": "Google Analytics 4",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "all_time": {
            "start_date": start_date,
            "end_date": "yesterday",
            "total_users": all_time["totalUsers"],
            "views": all_time["screenPageViews"],
        },
        "last_30_days": {
            "start_date": "30daysAgo",
            "end_date": "yesterday",
            "active_users": last_30_days["activeUsers"],
            "sessions": last_30_days["sessions"],
            "views": last_30_days["screenPageViews"],
        },
    }

    write_json(STATS_DIR / "stats.json", stats)
    write_json(
        STATS_DIR / "badge-total-users.json",
        badge("Total users", all_time["totalUsers"]),
    )
    write_json(
        STATS_DIR / "badge-users-30d.json",
        badge("Users (30d)", last_30_days["activeUsers"]),
    )
    write_json(
        STATS_DIR / "badge-sessions-30d.json",
        badge("Sessions (30d)", last_30_days["sessions"]),
    )
    write_json(
        STATS_DIR / "badge-views-30d.json",
        badge("Views (30d)", last_30_days["screenPageViews"]),
    )

    print("Google Analytics statistics updated successfully.")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
