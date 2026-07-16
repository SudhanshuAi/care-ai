"""HTTP-level smoke coverage for the Bolna webhook adapter."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, get_settings
from app.main import app


@pytest.mark.asyncio
async def test_bolna_tool_rejects_missing_bearer_when_auth_required() -> None:
    def override_settings() -> Settings:
        return Settings(
            bolna_api_token="expected-secret",
            bolna_verify_auth=True,
            env="local",
            retell_verify_signatures=False,
        )

    app.dependency_overrides[get_settings] = override_settings
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/webhooks/bolna/tools/lookup_patient",
                json={"full_name": "Rahul Verma"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


@pytest.mark.asyncio
async def test_bolna_tool_returns_voice_correlation_headers() -> None:
    def override_settings() -> Settings:
        return Settings(
            bolna_verify_auth=False,
            env="local",
            retell_verify_signatures=False,
        )

    app.dependency_overrides[get_settings] = override_settings
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/webhooks/bolna/tools/get_clinic_catalog",
                json={
                    "call_sid": "bolna-correlation-test",
                    "from_number": "+91-98765-10001",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["x-call-id"] == "bolna:bolna-correlation-test"
    assert response.headers["x-conversation-id"]
