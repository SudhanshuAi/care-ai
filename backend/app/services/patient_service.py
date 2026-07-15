from app.repositories.patient_repository import PatientRepository
from app.schemas.tools import PatientLookupResponse, PatientSummary


class PatientService:
    def __init__(self, repository: PatientRepository) -> None:
        self._repository = repository

    async def lookup_by_phone(self, phone: str) -> PatientLookupResponse:
        patients = await self._repository.by_phone(phone)
        return PatientLookupResponse(
            match_count=len(patients),
            requires_disambiguation=len(patients) > 1,
            patients=[PatientSummary.model_validate(patient) for patient in patients],
        )

    async def lookup_by_name(self, name: str) -> PatientLookupResponse:
        patients = await self._repository.by_name(name)
        return PatientLookupResponse(
            match_count=len(patients),
            requires_disambiguation=len(patients) > 1,
            patients=[PatientSummary.model_validate(patient) for patient in patients],
        )
