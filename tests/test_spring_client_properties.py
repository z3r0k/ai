import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.cache import get_cache
from app.services.spring_client import SpringBootClient


@pytest.fixture(autouse=True)
def limpiar_cache():
    # La caché es global: sin esto un test recibe el resultado de otro.
    get_cache().clear()
    yield
    get_cache().clear()


def make_registro(propiedad_id, info):
    # Formato real de /api/v1/propiedades-chatbot: informacionConsolidada
    # llega como string JSON, no como objeto.
    return {
        "id": propiedad_id,
        "propiedadId": propiedad_id,
        "disponibilidadStatus": "DISPONIBLE",
        "informacionConsolidada": json.dumps(info),
        "fechaActualizacion": "2026-10-14T03:26:46.504728Z",
    }


SAMPLE_PROPERTIES = [
    make_registro(1, {
        "nombre": "Conjunto Residencial Bosques de la Colina",
        "categoria": "CONJUNTO RESIDENCIAL",
        "tipo_propiedad": {"id": 1, "descripcion": "Conjunto residencial"},
        "resumen": "Conjunto Residencial en Teusaquillo, BOGOTA, D.C.",
        "areas": {"area_total_m2": 6670.00},
        "ubicacion": {
            "municipio": "BOGOTA, D.C.",
            "departamento": "BOGOTA, D.C.",
            "barrio_vereda": "Teusaquillo",
            "direccion": "Diagonal 24A # 70-6",
        },
        "distribucion": {"estacionamientos": 157},
        "zonas_comunes": {"piscina": True, "ascensor": True, "gimnasio": False},
        "contacto": {"empresa": "Administración PH Magdalena", "celular": "3017287910"},
    }),
    make_registro(2, {
        "nombre": "Apartamento Laureles 302",
        "categoria": "APARTAMENTO",
        "tipo_propiedad": {"id": 2, "descripcion": "Apartamento"},
        "ubicacion": {"municipio": "MEDELLIN", "departamento": "ANTIOQUIA", "barrio_vereda": "Laureles"},
        "distribucion": {"habitaciones": 3, "banos": 2},
        "zonas_comunes": {"gimnasio": True},
        "comercial": {"precio": 2500000.0, "tipo_operacion": "ARRIENDO", "en_arriendo": True},
    }),
    make_registro(3, {
        "nombre": "Apartaestudio Poblado",
        "categoria": "APARTAMENTO",
        "tipo_propiedad": {"id": 2, "descripcion": "Apartamento"},
        "ubicacion": {"municipio": "MEDELLIN", "departamento": "ANTIOQUIA", "barrio_vereda": "El Poblado"},
        "distribucion": {"habitaciones": 1},
        "comercial": {"precio": 350000000.0, "tipo_operacion": "VENTA", "en_venta": True},
    }),
]


def make_client(payload, status_code=200):
    client = SpringBootClient()
    fake_response = SimpleNamespace(
        status_code=status_code,
        raise_for_status=lambda: None,
        json=lambda: payload,
    )
    client._get = AsyncMock(return_value=fake_response)
    return client


@pytest.mark.asyncio
async def test_usa_endpoint_filtros_con_disponibilidad_y_operacion():
    client = make_client(SAMPLE_PROPERTIES)
    await client.get_properties_compact(tipo_operacion="arriendo")
    client._get.assert_awaited_once_with(
        "/api/v1/propiedades-chatbot/filtros",
        params={"disponibilidad": "DISPONIBLE", "operacion": "ARRIENDO"},
    )


@pytest.mark.asyncio
async def test_ciudad_con_tildes_coincide_con_municipio_del_backend():
    client = make_client(SAMPLE_PROPERTIES)
    result = await client.get_properties_compact(ciudad="Bogotá")
    assert "Bosques de la Colina" in result
    assert "Laureles" not in result


@pytest.mark.asyncio
async def test_habitaciones_min_descarta_las_sin_dato():
    client = make_client(SAMPLE_PROPERTIES)
    result = await client.get_properties_compact(habitaciones_min=2)
    assert "Apartamento Laureles 302" in result
    assert "Apartaestudio Poblado" not in result
    # Conjuntos, torres y locales no informan habitaciones: no aplican.
    assert "Bosques de la Colina" not in result


@pytest.mark.asyncio
async def test_tipo_propiedad_y_zonas_comunes():
    client = make_client(SAMPLE_PROPERTIES)
    result = await client.get_properties_compact(tipo_propiedad="apartamento", zona_o_caracteristicas="gimnasio")
    assert "Apartamento Laureles 302" in result
    assert "Apartaestudio Poblado" not in result
    assert "Bosques de la Colina" not in result


@pytest.mark.asyncio
async def test_formato_compacto_sin_contacto_ni_resumen():
    client = make_client(SAMPLE_PROPERTIES)
    result = await client.get_properties_compact(ciudad="bogota")
    assert "[ID 1]" in result
    assert "hab: N/D" in result
    assert "Teusaquillo, BOGOTA, D.C." in result
    assert "6670 m²" in result
    assert "piscina" in result and "gimnasio" not in result
    assert "3017287910" not in result


@pytest.mark.asyncio
async def test_limita_a_cinco_resultados():
    muchas = [make_registro(i, {"nombre": f"Prop {i}"}) for i in range(1, 9)]
    client = make_client(muchas)
    result = await client.get_properties_compact()
    assert "[ID 5]" in result
    assert "[ID 6]" not in result
    assert "3 más" in result


@pytest.mark.asyncio
async def test_sin_resultados():
    client = make_client([], status_code=204)
    result = await client.get_properties_compact(ciudad="Cali")
    assert result == "No se encontraron propiedades con esos criterios."


@pytest.mark.asyncio
async def test_detalle_de_propiedad_incluye_resumen_y_contacto():
    client = make_client([SAMPLE_PROPERTIES[0]])
    result = await client.get_property_detail(1)
    client._get.assert_awaited_once_with("/api/v1/propiedades-chatbot/propiedad/1")
    assert "Teusaquillo" in result
    assert "piscina" in result
    assert "3017287910" in result


@pytest.mark.asyncio
async def test_login_envia_clave_y_lee_access_token():
    client = SpringBootClient()
    fake_response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"accessToken": "abc123"},
    )
    client.client.post = AsyncMock(return_value=fake_response)
    await client._ensure_token()
    args, kwargs = client.client.post.call_args
    assert args[0] == "/api/v1/auth/login"
    assert set(kwargs["json"]) == {"email", "clave"}
    assert client.client.headers["Authorization"] == "Bearer abc123"


@pytest.mark.asyncio
async def test_muestra_precio_formateado_y_prioriza_las_que_tienen_precio():
    client = make_client(SAMPLE_PROPERTIES)
    result = await client.get_properties_compact()
    assert "ARRIENDO $2.500.000/mes" in result
    assert "VENTA $350.000.000" in result
    # El conjunto (sin precio) queda al final del listado.
    assert result.index("Bosques de la Colina") > result.index("Laureles")


@pytest.mark.asyncio
async def test_filtro_precio_max_descarta_caras_y_sin_precio():
    client = make_client(SAMPLE_PROPERTIES)
    result = await client.get_properties_compact(precio_max=3000000)
    assert "Apartamento Laureles 302" in result
    assert "Apartaestudio Poblado" not in result
    assert "Bosques de la Colina" not in result


@pytest.mark.asyncio
async def test_detalle_incluye_precio():
    client = make_client(SAMPLE_PROPERTIES[1])
    result = await client.get_property_detail(2)
    # Sin resumen del backend, el detalle se arma con los campos sueltos.
    assert "Precio: ARRIENDO $2.500.000/mes." in result
    assert "Baños: 2." in result


@pytest.mark.asyncio
async def test_detalle_con_resumen_no_repite_precio_ni_habitaciones():
    registro = make_registro(9, {
        "nombre": "Casa X",
        "resumen": "Casa X. En venta. Precio: $696,000,000. 6 habitación(es). 5 baño(s).",
        "comercial": {"precio": 696000000.0, "tipo_operacion": "VENTA"},
        "distribucion": {"habitaciones": 6, "banos": 5},
    })
    client = make_client(registro)
    result = await client.get_property_detail(9)
    assert "Casa X. En venta." in result
    assert "Precio: VENTA" not in result
    assert "Habitaciones:" not in result


def test_base_url_es_el_dominio_como_url_base_de_postman(monkeypatch):
    from app.services import spring_client as module

    monkeypatch.setattr(module.settings, "backend_url", "https://ejemplo.com/")
    assert str(SpringBootClient().client.base_url).rstrip("/") == "https://ejemplo.com"
    # .env antiguo con /api al final: no debe quedar /api/api/v1/...
    monkeypatch.setattr(module.settings, "backend_url", "https://ejemplo.com/api")
    assert str(SpringBootClient().client.base_url).rstrip("/") == "https://ejemplo.com"
