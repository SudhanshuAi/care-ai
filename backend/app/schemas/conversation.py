"""Public representation of durable Retell conversation state."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ConversationStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    call_id: str
    database_call_id: UUID
    resumed_from_call_id: UUID | None
    resumed_from_retell_call_id: str | None = None
    language: str | None
    current_intent: str | None
    identified_patient_id: UUID | None
    selected_branch_id: UUID | None
    selected_practitioner_id: UUID | None
    selected_appointment_type_id: UUID | None
    last_availability_search: dict[str, Any] | None
    pending_confirmation: dict[str, Any] | None
    conversation_summary: str | None
    last_tool_called: str | None
    last_updated_at: datetime
    restored: bool = False
