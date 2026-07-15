from datetime import date
from uuid import uuid4

import pytest

from app.db.models.patient import Patient
from app.services.patient_service import PatientService


class StubPatientRepository:
    def __init__(self, patients: list[Patient]) -> None:
        self.patients = patients

    async def by_phone(self, _: str) -> list[Patient]:
        return self.patients

    async def by_name(self, _: str) -> list[Patient]:
        return self.patients


@pytest.mark.asyncio
async def test_shared_phone_number_requires_disambiguation() -> None:
    service = PatientService(
        StubPatientRepository(  # type: ignore[arg-type]
            [
                Patient(
                    id=uuid4(),
                    full_name="Arjun Mehta",
                    phone="+91-98765-11111",
                    date_of_birth=date(1978, 6, 23),
                ),
                Patient(
                    id=uuid4(),
                    full_name="Kavya Mehta",
                    phone="+91-98765-11111",
                    date_of_birth=date(1980, 9, 15),
                ),
            ]
        )
    )

    response = await service.lookup_by_phone("+91-98765-11111")

    assert response.match_count == 2
    assert response.requires_disambiguation is True
    assert [patient.full_name for patient in response.patients] == [
        "Arjun Mehta",
        "Kavya Mehta",
    ]
