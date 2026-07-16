from uuid import uuid4

from app.db.models.call import Call
from app.db.models.enums import CallDirection, CallStatus
from app.services.conversation_state_service import ConversationStateService


def _call() -> Call:
    return Call(
        id=uuid4(),
        retell_call_id="retell-source-call",
        phone="+91-98765-10001",
        direction=CallDirection.INBOUND,
        status=CallStatus.DISCONNECTED,
    )


def test_resume_copy_preserves_booking_context() -> None:
    source = _call()
    source.language = "hi-IN"
    source.current_intent = "book_appointment"
    source.identified_patient_id = uuid4()
    source.patient_id = source.identified_patient_id
    source.selected_branch_id = uuid4()
    source.selected_practitioner_id = uuid4()
    source.selected_appointment_type_id = uuid4()
    source.last_availability_search = {"slots": [{"start_time": "2026-07-16T09:00:00Z"}]}
    source.pending_confirmation = {"type": "availability_options"}
    source.conversation_summary = "Caller was choosing a morning slot."
    source.last_tool_called = "search_availability"

    target = _call()
    target.retell_call_id = "retell-reconnected-call"

    ConversationStateService._copy_resumable_state(source, target)

    assert target.language == "hi-IN"
    assert target.current_intent == "book_appointment"
    assert target.identified_patient_id == source.identified_patient_id
    assert target.selected_branch_id == source.selected_branch_id
    assert target.last_availability_search == source.last_availability_search
    assert target.pending_confirmation == source.pending_confirmation
    assert target.last_tool_called == "search_availability"


def test_summary_describes_pending_booking_concisely() -> None:
    call = _call()
    call.current_intent = "book_appointment"
    call.identified_patient_id = uuid4()
    call.pending_confirmation = {"type": "availability_options"}
    call.last_tool_called = "search_availability"

    summary = ConversationStateService._build_summary(call)

    assert "Intent: book_appointment." in summary
    assert "Patient identified." in summary
    assert "Booking confirmation was pending." in summary
    assert "Last tool: search_availability." in summary
