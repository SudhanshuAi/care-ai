import json
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[3] / "docs" / "bolna" / "tools"
pytestmark = pytest.mark.skipif(
    not TOOLS_DIR.exists(),
    reason="Bolna dashboard artifacts are not copied into the backend image.",
)
EXPECTED_TOOLS = {
    "lookup_patient",
    "get_clinic_catalog",
    "list_appointments",
    "search_availability",
    "create_appointment",
    "reschedule_appointment",
    "cancel_appointment",
    "create_followup",
}


def _contracts() -> dict[str, dict[str, object]]:
    return {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in TOOLS_DIR.glob("*.json")
    }


def test_all_eight_bolna_tools_are_present_and_use_per_tool_urls() -> None:
    contracts = _contracts()

    assert set(contracts) == EXPECTED_TOOLS
    for name, contract in contracts.items():
        assert contract["name"] == name
        assert contract["key"] == "custom_task"
        value = contract["value"]
        assert value["url"].endswith(f"/webhooks/bolna/tools/{name}")
        assert value["api_token"] == "Bearer {{BOLNA_API_TOKEN}}"


def test_pre_call_messages_are_short_and_neutral() -> None:
    for contract in _contracts().values():
        assert contract["pre_call_message"] == "One moment."


def test_mutations_require_ids_from_prior_tool_results() -> None:
    contracts = _contracts()

    assert set(contracts["create_appointment"]["parameters"]["required"]) >= {
        "patient_id",
        "caller_full_name",
        "practitioner_id",
        "branch_id",
        "appointment_type_id",
        "start_time",
    }
    assert set(contracts["reschedule_appointment"]["parameters"]["required"]) >= {
        "appointment_id",
        "caller_full_name",
        "practitioner_id",
        "branch_id",
        "appointment_type_id",
        "start_time",
    }
    assert contracts["list_appointments"]["parameters"]["required"] == [
        "patient_id"
    ]
