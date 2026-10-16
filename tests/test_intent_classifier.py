import pytest

from app.agent.intent_classifier import IntentClassifier


@pytest.mark.asyncio
async def test_busqueda_especifica_de_propiedad_va_al_llm():
    classifier = IntentClassifier()
    result = await classifier.classify("Necesito un apartamento en bogota con 3 habitaciones")
    assert result is None


@pytest.mark.asyncio
async def test_saludo_simple_responde_sin_llm():
    classifier = IntentClassifier()
    result = await classifier.classify("Buenos días!")
    assert result is not None and "InmoBot" in result


@pytest.mark.asyncio
async def test_saludo_con_consulta_va_al_llm():
    classifier = IntentClassifier()
    assert await classifier.classify("hola, busco casa en arriendo en Medellín") is None


@pytest.mark.asyncio
async def test_pedir_asesor_devuelve_contacto():
    classifier = IntentClassifier()
    result = await classifier.classify("quiero hablar con un asesor")
    assert result is not None and "(601) 123-4567" in result


@pytest.mark.asyncio
async def test_palabra_suelta_no_clave_va_al_llm():
    classifier = IntentClassifier()
    assert await classifier.classify("quiero") is None
