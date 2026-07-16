"""Durable call memory and reconnect recovery.

The service owns no voice/LLM behavior. It records compact, structured
state around Retell function invocations so a new Retell call can
continue an interrupted booking without re-asking known information.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.retell.schemas import RetellCallContext
from app.core.exceptions import NotFoundError
from app.db.models.call import Call
from app.db.models.enums import CallDirection
from app.repositories.call_repository import CallRepository
from app.schemas.conversation import ConversationStateResponse


class ConversationStateService:
    def __init__(self, session: AsyncSession, calls: CallRepository) -> None:
        self._session = session
        self._calls = calls

    async def restore_or_create(self, context: RetellCallContext | None) -> Call | None:
        """Load a current call or create it by cloning resumable state.

        Explicit Retell `resumed_from_call_id` takes precedence. If it
        is missing, a callback from the same number resumes only the
        most recent unfinished/disconnected call — completed calls are
        never reopened as interrupted work.
        """

        if context is None or not context.call_id:
            return None

        phone = (context.from_number or "unknown").strip()
        direction = (
            CallDirection.OUTBOUND
            if (context.direction or "").lower() == "outbound"
            else CallDirection.INBOUND
        )

        async with self._session.begin():
            existing = await self._calls.by_retell_call_id(context.call_id)
            if existing is not None:
                return existing

            source: Call | None = None
            explicit_parent = (context.resumed_from_call_id or "").strip()
            if explicit_parent:
                source = await self._calls.by_retell_call_id(explicit_parent)
            if source is None and phone != "unknown":
                source = await self._calls.latest_resumable_for_phone(
                    phone, exclude_retell_call_id=context.call_id
                )
            call = await self._calls.ensure_from_retell(
                retell_call_id=context.call_id,
                phone=phone,
                direction=direction,
                resumed_from_call_id=source.id if source else None,
            )
            if source is not None:
                self._copy_resumable_state(source, call)
            self._apply_context_language(call, context)
            await self._session.flush()
        return call

    async def record_tool_result(
        self,
        *,
        call: Call | None,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any] | None,
    ) -> None:
        if call is None:
            return

        if self._session.in_transaction():
            await self._session.commit()
        async with self._session.begin():
            # Re-fetch in this transaction to avoid mutating an entity
            # associated with a completed service transaction.
            current = await self._calls.by_id(call.id)
            if current is None:
                return
            current.last_tool_called = tool_name
            current.current_intent = self._intent_for_tool(tool_name, current.current_intent)

            if tool_name == "lookup_patient" and result:
                patients = result.get("patients") or []
                if len(patients) == 1 and not result.get("requires_disambiguation"):
                    current.identified_patient_id = UUID(str(patients[0]["id"]))
                    current.patient_id = current.identified_patient_id
                elif result.get("requires_disambiguation"):
                    current.identified_patient_id = None

            if tool_name == "search_availability":
                current.last_availability_search = self._json_safe(
                    {"args": args, "result": result or {}, "searched_at": datetime.now(UTC)}
                )
                self._set_selection_from_args(current, args)
                slots = (result or {}).get("slots") or []
                if slots:
                    current.pending_confirmation = self._json_safe(
                        {
                            "type": "availability_options",
                            "slots": slots[:3],
                            "message": "Caller has not confirmed a slot yet.",
                        }
                    )

            if tool_name in {"create_appointment", "reschedule_appointment"} and result:
                self._set_selection_from_result(current, result)
                current.pending_confirmation = None
                current.current_intent = "appointment_confirmed"

            if tool_name == "cancel_appointment":
                current.pending_confirmation = None
                current.current_intent = "appointment_cancelled"

            await self._session.flush()

    async def set_pending_confirmation(
        self, *, call: Call | None, confirmation: dict[str, Any]
    ) -> None:
        if call is None:
            return
        if self._session.in_transaction():
            await self._session.commit()
        async with self._session.begin():
            current = await self._calls.by_id(call.id)
            if current is None:
                return
            current.pending_confirmation = self._json_safe(confirmation)
            current.current_intent = "awaiting_booking_confirmation"
            self._set_selection_from_args(current, confirmation)
            await self._session.flush()

    async def get_state(self, retell_call_id: str) -> ConversationStateResponse:
        call = await self._calls.by_retell_call_id(retell_call_id)
        if call is None:
            raise NotFoundError("Retell call context was not found.")
        parent = (
            await self._calls.by_id(call.resumed_from_call_id)
            if call.resumed_from_call_id
            else None
        )
        return self._to_response(call, parent)

    async def complete(
        self, *, retell_call_id: str, disconnected: bool = False
    ) -> ConversationStateResponse | None:
        async with self._session.begin():
            call = (
                await self._calls.mark_disconnected(retell_call_id)
                if disconnected
                else await self._calls.mark_completed(retell_call_id)
            )
            if call is None:
                return None
            call.conversation_summary = self._build_summary(call)
            await self._session.flush()
            # `last_updated_at` is assigned by PostgreSQL's `now()` on
            # UPDATE; refresh before serializing so async SQLAlchemy
            # never tries a lazy attribute load outside greenlet context.
            await self._session.refresh(call)
            parent = (
                await self._calls.by_id(call.resumed_from_call_id)
                if call.resumed_from_call_id
                else None
            )
            return self._to_response(call, parent)

    @staticmethod
    def _copy_resumable_state(source: Call, target: Call) -> None:
        target.language = source.language
        target.current_intent = source.current_intent
        target.identified_patient_id = source.identified_patient_id
        target.patient_id = source.patient_id
        target.selected_branch_id = source.selected_branch_id
        target.selected_practitioner_id = source.selected_practitioner_id
        target.selected_appointment_type_id = source.selected_appointment_type_id
        target.last_availability_search = source.last_availability_search
        target.pending_confirmation = source.pending_confirmation
        target.conversation_summary = source.conversation_summary
        target.last_tool_called = source.last_tool_called

    @staticmethod
    def _apply_context_language(call: Call, context: RetellCallContext) -> None:
        language = (context.language or "").strip()
        if language:
            call.language = language

    @staticmethod
    def _intent_for_tool(tool_name: str, prior: str | None) -> str:
        mapping = {
            "lookup_patient": "identify_patient",
            "search_availability": "search_availability",
            "create_appointment": "book_appointment",
            "reschedule_appointment": "reschedule_appointment",
            "cancel_appointment": "cancel_appointment",
            "create_followup": "followup_requested",
        }
        return mapping.get(tool_name, prior or "general_inquiry")

    @staticmethod
    def _set_selection_from_args(call: Call, args: dict[str, Any]) -> None:
        for field in (
            "branch_id",
            "practitioner_id",
            "appointment_type_id",
        ):
            value = args.get(field)
            if value:
                setattr(call, f"selected_{field}", UUID(str(value)))

    @staticmethod
    def _set_selection_from_result(call: Call, result: dict[str, Any]) -> None:
        for source, target in (
            ("branch_id", "selected_branch_id"),
            ("practitioner_id", "selected_practitioner_id"),
            ("appointment_type_id", "selected_appointment_type_id"),
            ("patient_id", "identified_patient_id"),
        ):
            value = result.get(source)
            if value:
                setattr(call, target, UUID(str(value)))
        if call.identified_patient_id:
            call.patient_id = call.identified_patient_id

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, dict):
            return {key: ConversationStateService._json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [ConversationStateService._json_safe(item) for item in value]
        return value

    @staticmethod
    def _build_summary(call: Call) -> str:
        parts = [f"Intent: {call.current_intent or 'unknown'}."]
        if call.identified_patient_id:
            parts.append("Patient identified.")
        if call.selected_branch_id:
            parts.append("Branch selected.")
        if call.selected_practitioner_id:
            parts.append("Practitioner selected.")
        if call.selected_appointment_type_id:
            parts.append("Appointment type selected.")
        if call.pending_confirmation:
            parts.append("Booking confirmation was pending.")
        if call.last_tool_called:
            parts.append(f"Last tool: {call.last_tool_called}.")
        return " ".join(parts)

    @staticmethod
    def _to_response(call: Call, parent: Call | None) -> ConversationStateResponse:
        return ConversationStateResponse(
            call_id=call.retell_call_id or str(call.id),
            database_call_id=call.id,
            resumed_from_call_id=call.resumed_from_call_id,
            resumed_from_retell_call_id=parent.retell_call_id if parent else None,
            language=call.language,
            current_intent=call.current_intent,
            identified_patient_id=call.identified_patient_id,
            selected_branch_id=call.selected_branch_id,
            selected_practitioner_id=call.selected_practitioner_id,
            selected_appointment_type_id=call.selected_appointment_type_id,
            last_availability_search=call.last_availability_search,
            pending_confirmation=call.pending_confirmation,
            conversation_summary=call.conversation_summary,
            last_tool_called=call.last_tool_called,
            last_updated_at=call.last_updated_at,
            restored=call.resumed_from_call_id is not None,
        )
