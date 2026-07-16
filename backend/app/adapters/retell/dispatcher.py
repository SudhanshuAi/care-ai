"""Maps Retell Custom Function invocations onto existing tool services.

This adapter is the only telephony-specific surface. It does not change
`/tools/*` contracts; it only translates Retell's `{name, args, call}`
payload into service calls and returns a JSON string Retell can feed
back to the LLM.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters.retell.schemas import RetellCallContext, RetellToolInvocation
from app.core.exceptions import DomainError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.models import (
    AppointmentType,
    Branch,
    Department,
    Practitioner,
)
from app.db.models.enums import CallDirection, FollowUpCategory
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.call_repository import CallRepository
from app.repositories.followup_repository import FollowUpRepository
from app.repositories.patient_repository import PatientRepository
from app.repositories.scheduling_repository import SchedulingRepository
from app.schemas.tools import (
    AvailabilitySearchRequest,
    CancelAppointmentRequest,
    CreateAppointmentRequest,
    FollowUpRequest,
    RescheduleAppointmentRequest,
)
from app.services.appointment_service import AppointmentService
from app.services.availability_service import AvailabilityService
from app.services.followup_service import FollowUpService
from app.services.patient_service import PatientService

logger = get_logger(__name__)


class RetellToolDispatcher:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._patients = PatientRepository(session)
        self._scheduling = SchedulingRepository(session)
        self._appointments = AppointmentRepository(session)
        self._followups = FollowUpRepository(session)
        self._calls = CallRepository(session)

        self._patient_service = PatientService(self._patients)
        self._availability_service = AvailabilityService(self._scheduling)
        self._appointment_service = AppointmentService(
            session, self._appointments, self._patients, self._scheduling
        )
        self._followup_service = FollowUpService(session, self._followups)

    async def dispatch(self, invocation: RetellToolInvocation) -> dict[str, Any]:
        name = invocation.name.strip()
        args = dict(invocation.args or {})
        call = invocation.call

        logger.info(
            "retell_tool_invoked",
            tool=name,
            retell_call_id=(call.call_id if call else None),
        )

        try:
            if name == "lookup_patient":
                result = await self._lookup_patient(args, call)
            elif name == "get_clinic_catalog":
                result = await self._get_clinic_catalog()
            elif name == "search_availability":
                result = await self._search_availability(args)
            elif name == "create_appointment":
                result = await self._create_appointment(args, call)
            elif name == "reschedule_appointment":
                result = await self._reschedule_appointment(args, call)
            elif name == "cancel_appointment":
                result = await self._cancel_appointment(args, call)
            elif name == "create_followup":
                result = await self._create_followup(args, call)
            else:
                raise ValidationError(f"Unknown Retell tool: {name}")
            return {"ok": True, "tool": name, "result": result}
        except DomainError as exc:
            logger.warning("retell_tool_domain_error", tool=name, detail=exc.detail)
            return {
                "ok": False,
                "tool": name,
                "error": {"code": exc.code, "detail": exc.detail},
            }
        except (ValueError, KeyError, TypeError) as exc:
            # Retell LLMs often invent names/phones where UUIDs are required.
            # Surface those as tool errors (HTTP 200) so the agent can recover
            # instead of a bare 500 from the webhook.
            detail = str(exc) or "Invalid tool arguments."
            logger.warning("retell_tool_argument_error", tool=name, detail=detail)
            return {
                "ok": False,
                "tool": name,
                "error": {"code": "validation_error", "detail": detail},
            }

    async def _lookup_patient(
        self, args: dict[str, Any], call: RetellCallContext | None
    ) -> dict[str, Any]:
        phone = (args.get("phone") or (call.from_number if call else None) or "").strip()
        name = (args.get("full_name") or args.get("name") or "").strip()

        if phone and name:
            by_phone = await self._patient_service.lookup_by_phone(phone)
            narrowed = [
                patient
                for patient in by_phone.patients
                if name.casefold() in patient.full_name.casefold()
            ]
            return {
                "match_count": len(narrowed),
                "requires_disambiguation": len(narrowed) > 1,
                "patients": [patient.model_dump(mode="json") for patient in narrowed],
                "lookup_strategy": "phone_and_name",
            }

        if phone:
            response = await self._patient_service.lookup_by_phone(phone)
            payload = response.model_dump(mode="json")
            payload["lookup_strategy"] = "phone"
            return payload

        if name:
            response = await self._patient_service.lookup_by_name(name)
            payload = response.model_dump(mode="json")
            payload["lookup_strategy"] = "name"
            return payload

        raise ValidationError("lookup_patient requires phone and/or full_name.")

    async def _get_clinic_catalog(self) -> dict[str, Any]:
        """Voice-side helper so the LLM can map spoken names to UUIDs.

        Not part of the stable `/tools` REST surface; Retell-only.
        """

        branches = list(
            (
                await self._session.scalars(select(Branch).order_by(Branch.name))
            ).all()
        )
        departments = list(
            (
                await self._session.scalars(select(Department).order_by(Department.name))
            ).all()
        )
        practitioners = list(
            (
                await self._session.scalars(
                    select(Practitioner)
                    .options(selectinload(Practitioner.branch_links))
                    .order_by(Practitioner.display_name)
                )
            ).all()
        )
        appointment_types = list(
            (
                await self._session.scalars(
                    select(AppointmentType).order_by(AppointmentType.name)
                )
            ).all()
        )

        return {
            "branches": [
                {
                    "id": str(branch.id),
                    "name": branch.name,
                    "timezone": branch.timezone,
                    "address": branch.address,
                }
                for branch in branches
            ],
            "departments": [
                {"id": str(department.id), "name": department.name}
                for department in departments
            ],
            "practitioners": [
                {
                    "id": str(practitioner.id),
                    "display_name": practitioner.display_name,
                    "title": practitioner.title,
                    "department_id": str(practitioner.department_id),
                    "branch_ids": [
                        str(link.branch_id) for link in practitioner.branch_links
                    ],
                }
                for practitioner in practitioners
            ],
            "appointment_types": [
                {
                    "id": str(appointment_type.id),
                    "name": appointment_type.name,
                    "department_id": str(appointment_type.department_id),
                    "duration_minutes": appointment_type.duration_minutes,
                    "buffer_minutes": appointment_type.buffer_minutes,
                    "currency": appointment_type.currency,
                }
                for appointment_type in appointment_types
            ],
        }

    async def _search_availability(self, args: dict[str, Any]) -> dict[str, Any]:
        request = AvailabilitySearchRequest(
            appointment_type_id=await self._resolve_appointment_type_id(args),
            branch_id=await self._optional_uuid(
                args, "branch_id", name_key="branch_name", resolver=self._resolve_branch_id
            ),
            department_id=await self._optional_uuid(
                args,
                "department_id",
                name_key="department_name",
                resolver=self._resolve_department_id,
            ),
            practitioner_id=await self._optional_uuid(
                args,
                "practitioner_id",
                name_key="practitioner_name",
                resolver=self._resolve_practitioner_id,
            ),
            appointment_date=self._optional_date(args.get("appointment_date")),
            start_time=self._optional_time(args.get("start_time")),
            end_time=self._optional_time(args.get("end_time")),
            earliest_only=bool(args.get("earliest_only", False)),
            limit=int(args.get("limit", 5)),
        )
        response = await self._availability_service.search(request)
        return response.model_dump(mode="json")

    async def _create_appointment(
        self, args: dict[str, Any], call: RetellCallContext | None
    ) -> dict[str, Any]:
        request = CreateAppointmentRequest(
            patient_id=self._require_uuid(args.get("patient_id"), "patient_id"),
            caller_full_name=str(args["caller_full_name"]).strip(),
            practitioner_id=await self._resolve_practitioner_id(args),
            branch_id=await self._resolve_branch_id(args),
            appointment_type_id=await self._resolve_appointment_type_id(args),
            start_time=self._require_datetime(args.get("start_time"), "start_time"),
            notes=args.get("notes"),
        )
        key = self._idempotency_key("create_appointment", call, args)
        response = await self._appointment_service.create(request, key)
        return response.model_dump(mode="json")

    async def _reschedule_appointment(
        self, args: dict[str, Any], call: RetellCallContext | None
    ) -> dict[str, Any]:
        appointment_id = self._require_uuid(args.get("appointment_id"), "appointment_id")
        request = RescheduleAppointmentRequest(
            caller_full_name=str(args["caller_full_name"]).strip(),
            practitioner_id=await self._resolve_practitioner_id(args),
            branch_id=await self._resolve_branch_id(args),
            appointment_type_id=await self._resolve_appointment_type_id(args),
            start_time=self._require_datetime(args.get("start_time"), "start_time"),
            notes=args.get("notes"),
        )
        key = self._idempotency_key("reschedule_appointment", call, args)
        response = await self._appointment_service.reschedule(
            appointment_id, request, key
        )
        return response.model_dump(mode="json")

    async def _cancel_appointment(
        self, args: dict[str, Any], call: RetellCallContext | None
    ) -> dict[str, Any]:
        appointment_id = self._require_uuid(args.get("appointment_id"), "appointment_id")
        request = CancelAppointmentRequest(
            caller_full_name=str(args["caller_full_name"]).strip(),
            reason=args.get("reason"),
        )
        key = self._idempotency_key("cancel_appointment", call, args)
        response = await self._appointment_service.cancel(
            appointment_id, request, key
        )
        return response.model_dump(mode="json")

    async def _create_followup(
        self, args: dict[str, Any], call: RetellCallContext | None
    ) -> dict[str, Any]:
        if call is None or not call.call_id:
            raise ValidationError("create_followup requires Retell call context.")

        phone = (args.get("phone") or call.from_number or "unknown").strip()
        direction = (
            CallDirection.OUTBOUND
            if (call.direction or "").lower() == "outbound"
            else CallDirection.INBOUND
        )

        # Persist Call in its own transaction so FollowUpService can
        # open its own begin()/commit() safely on the same session.
        async with self._session.begin():
            db_call = await self._calls.ensure_from_retell(
                retell_call_id=call.call_id,
                phone=phone,
                direction=direction,
            )
            call_id = db_call.id

        try:
            category = FollowUpCategory(str(args["category"]))
        except (KeyError, ValueError) as exc:
            raise ValidationError(
                "category must be one of: human_requested, clinical_concern, other."
            ) from exc
        request = FollowUpRequest(
            call_id=call_id,
            patient_id=(
                self._require_uuid(args.get("patient_id"), "patient_id")
                if args.get("patient_id")
                else None
            ),
            category=category,
            notes=str(args["notes"]).strip(),
        )
        response = await self._followup_service.create(request)
        payload = response.model_dump(mode="json")
        payload["callback_expectation"] = (
            "A human team member will call the patient back. "
            "Do not imply an immediate live transfer."
        )
        return payload

    async def _resolve_appointment_type_id(self, args: dict[str, Any]) -> UUID:
        if args.get("appointment_type_id"):
            return self._require_uuid(args.get("appointment_type_id"), "appointment_type_id")
        name = (args.get("appointment_type_name") or "").strip()
        if not name:
            raise ValidationError(
                "appointment_type_id or appointment_type_name is required."
            )
        statement = select(AppointmentType).where(
            AppointmentType.name.ilike(f"%{name}%")
        )
        matches = list((await self._session.scalars(statement)).all())
        if not matches:
            raise NotFoundError(f"No appointment type matched {name!r}.")
        if len(matches) > 1:
            raise ValidationError(
                f"Multiple appointment types matched {name!r}; pass appointment_type_id."
            )
        return matches[0].id

    async def _resolve_branch_id(self, args: dict[str, Any]) -> UUID:
        if args.get("branch_id"):
            return self._require_uuid(args.get("branch_id"), "branch_id")
        name = (args.get("branch_name") or "").strip()
        if not name:
            raise ValidationError("branch_id or branch_name is required.")
        statement = select(Branch).where(Branch.name.ilike(f"%{name}%"))
        matches = list((await self._session.scalars(statement)).all())
        if not matches:
            raise NotFoundError(f"No branch matched {name!r}.")
        if len(matches) > 1:
            raise ValidationError(
                f"Multiple branches matched {name!r}; pass branch_id."
            )
        return matches[0].id

    async def _resolve_department_id(self, args: dict[str, Any]) -> UUID:
        if args.get("department_id"):
            return self._require_uuid(args.get("department_id"), "department_id")
        name = (args.get("department_name") or "").strip()
        if not name:
            raise ValidationError("department_id or department_name is required.")
        statement = select(Department).where(Department.name.ilike(f"%{name}%"))
        matches = list((await self._session.scalars(statement)).all())
        if not matches:
            raise NotFoundError(f"No department matched {name!r}.")
        if len(matches) > 1:
            raise ValidationError(
                f"Multiple departments matched {name!r}; pass department_id."
            )
        return matches[0].id

    async def _resolve_practitioner_id(self, args: dict[str, Any]) -> UUID:
        if args.get("practitioner_id"):
            return self._require_uuid(args.get("practitioner_id"), "practitioner_id")
        name = (args.get("practitioner_name") or "").strip()
        if not name:
            raise ValidationError("practitioner_id or practitioner_name is required.")
        statement = select(Practitioner).where(
            Practitioner.display_name.ilike(f"%{name}%")
        )
        matches = list((await self._session.scalars(statement)).all())
        if not matches:
            raise NotFoundError(f"No practitioner matched {name!r}.")
        if len(matches) > 1:
            raise ValidationError(
                f"Multiple practitioners matched {name!r}; pass practitioner_id."
            )
        return matches[0].id

    async def _optional_uuid(
        self,
        args: dict[str, Any],
        id_key: str,
        *,
        name_key: str,
        resolver: Any,
    ) -> UUID | None:
        if args.get(id_key) or args.get(name_key):
            return await resolver(args)
        return None

    @staticmethod
    def _require_uuid(value: Any, field: str) -> UUID:
        if value is None or str(value).strip() == "":
            raise ValidationError(
                f"{field} is required and must be a UUID from lookup_patient / "
                "get_clinic_catalog / search_availability — not a name or phone."
            )
        try:
            return UUID(str(value).strip())
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValidationError(
                f"{field} must be a valid UUID from a prior tool result "
                f"(got {value!r}). Call lookup_patient / get_clinic_catalog / "
                "search_availability first and reuse the id fields exactly."
            ) from exc

    @staticmethod
    def _optional_date(value: Any) -> date | None:
        if value is None or value == "":
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError as exc:
            raise ValidationError(
                f"Invalid date {value!r}; expected YYYY-MM-DD."
            ) from exc

    @staticmethod
    def _optional_time(value: Any) -> time | None:
        if value is None or value == "":
            return None
        if isinstance(value, time):
            return value
        text = str(value)
        if len(text) == 5:
            text = f"{text}:00"
        try:
            return time.fromisoformat(text)
        except ValueError as exc:
            raise ValidationError(
                f"Invalid time {value!r}; expected HH:MM or HH:MM:SS."
            ) from exc

    @staticmethod
    def _require_datetime(value: Any, field: str) -> datetime:
        if value is None:
            raise ValidationError(f"{field} is required.")
        if isinstance(value, datetime):
            parsed = value
        else:
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValidationError(
                    f"{field} must be an ISO-8601 datetime with timezone offset "
                    f"(got {value!r})."
                ) from exc
        if parsed.tzinfo is None:
            raise ValidationError(f"{field} must include a timezone offset.")
        return parsed

    @staticmethod
    def _idempotency_key(
        tool: str, call: RetellCallContext | None, args: dict[str, Any]
    ) -> str:
        retell_call_id = call.call_id if call and call.call_id else "anonymous"
        fingerprint = hashlib.sha256(
            json.dumps(args, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:24]
        return f"retell:{retell_call_id}:{tool}:{fingerprint}"
