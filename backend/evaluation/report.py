"""Stable JSON, Markdown, and CSV report writers."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def write_reports(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "evaluation_report.json"
    markdown_path = output_dir / "evaluation_report.md"
    csv_path = output_dir / "evaluation_summary.csv"

    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    _write_csv(report, csv_path)
    return json_path, markdown_path, csv_path


def _markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Evaluation Report",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, value in summary.items():
        lines.append(f"| {key} | {value if value is not None else 'not collected'} |")

    lines.extend(["", "## Cases", "", "| Case | Scenario | Result |", "|---|---|---|"])
    for case in report["cases"]:
        result = "PASS" if case["success"] else "FAIL"
        lines.append(f"| {case['case_id']} | {case['scenario']} | {result} |")

    lines.extend(["", "## Failures", ""])
    if report["failures"]:
        for failure in report["failures"]:
            lines.append(
                f"- `{failure['case_id']}` ({failure['scenario']}): {failure['failure']}"
            )
    else:
        lines.append("No failures.")

    lines.extend(["", "## Metric Notes", ""])
    for metric, note in report["metric_notes"].items():
        lines.append(f"- `{metric}`: {note}")
    return "\n".join(lines) + "\n"


def _write_csv(report: dict[str, Any], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "case_id",
                "scenario",
                "success",
                "failure",
                "step_count",
                "average_step_latency_ms",
            ],
        )
        writer.writeheader()
        for case in report["cases"]:
            latencies = [step["latency_ms"] for step in case["steps"]]
            writer.writerow(
                {
                    "case_id": case["case_id"],
                    "scenario": case["scenario"],
                    "success": case["success"],
                    "failure": case["failure"] or "",
                    "step_count": len(case["steps"]),
                    "average_step_latency_ms": (
                        round(sum(latencies) / len(latencies), 2) if latencies else ""
                    ),
                }
            )
