import json

from evaluation.metrics import CaseResult, StepResult, build_report
from evaluation.report import write_reports


def test_build_report_separates_backend_latency_from_ttft(tmp_path) -> None:
    report = build_report(
        [
            CaseResult(
                case_id="booking",
                scenario="exact_time_booking",
                success=True,
                steps=[
                    StepResult(
                        name="book",
                        success=True,
                        latency_ms=12.5,
                        tool="create_appointment",
                        booking_operation=True,
                    )
                ],
            ),
            CaseResult(
                case_id="failed",
                scenario="doctor_unavailable",
                success=False,
                failure="Expected no availability.",
            ),
        ]
    )

    assert report["summary"]["conversation_success_rate"] == 0.5
    assert report["summary"]["booking_accuracy"] == 1.0
    assert report["summary"]["average_ttft_ms"] is None
    assert "not_collected" in report["metric_notes"]["average_ttft_ms"]

    json_path, markdown_path, csv_path = write_reports(report, tmp_path)

    assert json.loads(json_path.read_text())["summary"]["failed_cases"] == 1
    assert "doctor_unavailable" in markdown_path.read_text()
    assert "case_id,scenario,success" in csv_path.read_text()
