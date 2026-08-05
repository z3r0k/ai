import pytest
from app.agent.guardrails import sanitize_input


@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_guardrails_sanitize():
    safe_text_input = "Hola, estoy buscando un apartamento en renta"
    safe_text_output = sanitize_input(safe_text_input)
    assert isinstance(safe_text_output, str)
