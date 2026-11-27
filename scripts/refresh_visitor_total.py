"""Refresh the cumulative, hostname-filtered GA4 visitor total used by the footer."""
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

CONFIG = Path(__file__).resolve().parents[1] / "config/site.json"
HOST = "brief.hamelberg-ai.com"
START = "2026-09-01"
PROPERTY = "549530905"


def report_request(end):
    return {
        "dateRanges": [{"startDate": START, "endDate": end}],
        "metrics": [{"name": "totalUsers"}],
        "dimensionFilter": {"filter": {"fieldName": "hostName", "stringFilter": {
            "matchType": "EXACT", "value": HOST, "caseSensitive": False}}},
    }


def snapshot(report, end, today):
    metadata = report.get("metadata", {})
    if any(metadata.get(key) for key in ("subjectToThresholding", "samplingMetadatas", "dataLossFromOtherRow")):
        raise ValueError("Google returned a limited report. The saved visitor total was preserved.")
    rows = report.get("rows", [])
    if report.get("rowCount") != 1 or len(rows) != 1 or [h["name"] for h in report["metricHeaders"]] != ["totalUsers"]:
        raise ValueError("Expected one cumulative totalUsers result.")
    value = rows[0]["metricValues"]
    if len(value) != 1 or not value[0]["value"].isdecimal():
        raise ValueError("Google returned an invalid visitor total.")
    return {"count": int(value[0]["value"]), "source": "Google Analytics", "metric": "totalUsers",
            "property_id": PROPERTY, "hostname": HOST, "period_start": START, "period_end": end,
            "period_label": f"{START} to {end}", "updated_at": today, "refresh": "ga4_data_api"}


def main():
    today = datetime.now(ZoneInfo("Europe/Amsterdam")).date()
    end = (today - timedelta(days=2)).isoformat()
    request = Request(f"https://analyticsdata.googleapis.com/v1beta/properties/{PROPERTY}:runReport",
                      data=json.dumps(report_request(end)).encode(), headers={
                          "Authorization": "Bearer " + os.environ["GA4_ACCESS_TOKEN"],
                          "Content-Type": "application/json"})
    with urlopen(request, timeout=30) as response:
        fresh = snapshot(json.load(response), end, today.isoformat())
    config = json.loads(CONFIG.read_text())
    if fresh["period_end"] < config["visitor_total"]["period_end"]:
        raise ValueError("Refusing to replace a newer report.")
    config["visitor_total"] = fresh
    CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
