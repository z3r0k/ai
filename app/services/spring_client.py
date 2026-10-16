import json
import httpx
import logging
import unicodedata
from typing import Optional
from ..core.config import settings
from ..core.cache import get_cache, make_cache_key

logger = logging.getLogger(__name__)

# Rutas relativas a settings.backend_url, que equivale a {{URL_BASE}} de la
# colección Postman (solo el dominio, sin /api).
LOGIN_ENDPOINT = "/api/v1/auth/login"
CHATBOT_ENDPOINT = "/api/v1/propiedades-chatbot"

# Máximo de propiedades que se le pasan al LLM por búsqueda (ahorro de tokens).
MAX_RESULTADOS = 5


def _normalize(text) -> str:
    text = str(text).lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def _parse_info(registro: dict) -> dict:
    """
    Cada registro de /propiedades-chatbot trae `informacionConsolidada` como
    string JSON (nombre, resumen, ubicacion, distribucion, zonas_comunes...).
    Lo convierte a dict de forma tolerante.
    """
    info = registro.get("informacionConsolidada")
    if isinstance(info, dict):
        return info
    if isinstance(info, str) and info.strip():
        try:
            parsed = json.loads(info)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            logger.warning(
                f"informacionConsolidada inválida para propiedad {registro.get('propiedadId')}"
            )
    return {}


def _sub(info: dict, key: str) -> dict:
    value = info.get(key)
    return value if isinstance(value, dict) else {}


def _zonas_comunes(info: dict) -> list:
    return [k.replace("_", " ") for k, v in _sub(info, "zonas_comunes").items() if v is True]


def _tipo(info: dict) -> str:
    return _sub(info, "tipo_propiedad").get("descripcion") or info.get("categoria") or ""


def _habitaciones(info: dict) -> Optional[int]:
    value = _sub(info, "distribucion").get("habitaciones")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _precio(info: dict) -> Optional[float]:
    value = _sub(info, "comercial").get("precio")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _tipo_operacion(info: dict) -> str:
    return str(_sub(info, "comercial").get("tipo_operacion") or "").upper()


def _formato_precio(info: dict) -> Optional[str]:
    """Ej: 'ARRIENDO $2.500.000/mes' o 'VENTA $696.000.000'."""
    precio = _precio(info)
    if precio is None:
        return None
    operacion = _tipo_operacion(info)
    texto = "$" + f"{precio:,.0f}".replace(",", ".")
    if operacion == "ARRIENDO":
        texto += "/mes"
    return f"{operacion} {texto}" if operacion else texto


def _propiedad_id(registro: dict, info: dict):
    return registro.get("propiedadId") or info.get("propiedad_id") or registro.get("id")


def _linea_compacta(registro: dict, info: dict) -> str:
    """Una línea por propiedad con solo los datos útiles para el LLM."""
    ubicacion = _sub(info, "ubicacion")
    partes = []

    nombre = info.get("nombre", "Sin nombre")
    tipo = _tipo(info)
    partes.append(f"{nombre} ({tipo})" if tipo else nombre)

    precio = _formato_precio(info)
    if precio:
        partes.append(precio)

    lugar = ", ".join(
        x for x in (ubicacion.get("barrio_vereda"), ubicacion.get("municipio")) if x
    )
    if lugar:
        partes.append(lugar)

    area = _sub(info, "areas").get("area_total_m2")
    if area:
        partes.append(f"{float(area):g} m²")

    hab = _habitaciones(info)
    partes.append(f"hab: {hab}" if hab is not None else "hab: N/D")

    banos = _sub(info, "distribucion").get("banos")
    if banos:
        partes.append(f"baños: {banos}")

    zonas = _zonas_comunes(info)
    if zonas:
        partes.append(", ".join(zonas))

    return f"- [ID {_propiedad_id(registro, info)}] " + " · ".join(partes)


class SpringBootClient:
    def __init__(self):
        # Compatibilidad con .env antiguos donde BACKEND_URL terminaba en /api.
        base_url = settings.backend_url.rstrip("/").removesuffix("/api")
        self.client = httpx.AsyncClient(base_url=base_url, timeout=10.0)
        self._cache = get_cache()
        self._token = None

    async def _ensure_token(self):
        if not self._token:
            logger.info("Autenticando contra el backend...")

            payload = {
                "email": settings.backend_user,
                "clave": settings.backend_password,
            }

            try:
                resp = await self.client.post(LOGIN_ENDPOINT, json=payload)
                resp.raise_for_status()
                data = resp.json()
                self._token = (
                    data.get("accessToken") or data.get("token") or data.get("jwt")
                )
                if self._token:
                    self.client.headers["Authorization"] = f"Bearer {self._token}"
                    logger.info("Token JWT obtenido exitosamente.")
                else:
                    logger.error(f"Estructura de token desconocida: {list(data.keys())}")
            except Exception as e:
                logger.error(f"Error en login: {e}")

    async def _get(self, endpoint: str, params: dict = None):
        await self._ensure_token()
        resp = await self.client.get(endpoint, params=params)
        if resp.status_code == 401:
            logger.warning("Token expirado o inválido. Re-autenticando...")
            self._token = None
            self.client.headers.pop("Authorization", None)
            await self._ensure_token()
            resp = await self.client.get(endpoint, params=params)
        return resp

    # ==================== PROPIEDADES (CHATBOT) ====================

    async def get_properties_compact(
        self,
        tipo_operacion: Optional[str] = None,
        ciudad: Optional[str] = None,
        habitaciones_min: Optional[int] = None,
        tipo_propiedad: Optional[str] = None,
        zona_o_caracteristicas: Optional[str] = None,
        precio_min: Optional[float] = None,
        precio_max: Optional[float] = None,
    ) -> str:
        """
        Busca propiedades disponibles en /propiedades-chatbot/filtros y retorna
        un texto resumido (optimizado para LLM).

        Disponibilidad y tipo de operación se filtran en el backend. Precio
        (informacionConsolidada.comercial.precio), ciudad y demás criterios se
        filtran localmente; ciudad no va como jsonValor porque el backend compara por igualdad exacta y
        guarda valores como "BOGOTA, D.C.", que no coincidirían con "Bogotá".
        """
        cache_key = make_cache_key(
            "properties_compact",
            tipo_operacion,
            ciudad,
            habitaciones_min,
            tipo_propiedad,
            zona_o_caracteristicas,
            precio_min,
            precio_max,
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.info("Propiedades servidas desde caché")
            return cached

        try:
            params = {"disponibilidad": "DISPONIBLE"}
            if tipo_operacion and tipo_operacion.strip():
                params["operacion"] = tipo_operacion.strip().upper()

            response = await self._get(f"{CHATBOT_ENDPOINT}/filtros", params=params)
            if response.status_code == 204:
                registros = []
            else:
                response.raise_for_status()
                registros = response.json() or []
            if isinstance(registros, dict):
                registros = [registros]

            logger.debug(
                f"[IA-FILTRO] Se descargaron {len(registros)} propiedades desde el backend."
            )

            propiedades = [(r, _parse_info(r)) for r in registros]

            if ciudad and ciudad.strip():
                ciudad_norm = _normalize(ciudad.strip())

                def en_ciudad(info):
                    ubicacion = _sub(info, "ubicacion")
                    texto = _normalize(
                        f"{ubicacion.get('municipio', '')} {ubicacion.get('departamento', '')}"
                    )
                    return ciudad_norm in texto

                propiedades = [(r, i) for r, i in propiedades if en_ciudad(i)]

            if habitaciones_min:
                # Conjuntos, torres y locales no informan habitaciones: no aplican.
                propiedades = [
                    (r, i)
                    for r, i in propiedades
                    if _habitaciones(i) is not None and _habitaciones(i) >= habitaciones_min
                ]

            if tipo_propiedad and tipo_propiedad.strip():
                tipo_norm = _normalize(tipo_propiedad.strip())
                propiedades = [
                    (r, i)
                    for r, i in propiedades
                    if tipo_norm in _normalize(f"{i.get('categoria', '')} {_tipo(i)}")
                ]

            # Con filtro de precio se descartan las que no tienen precio
            # (conjuntos y torres, que son propiedades padre).
            if precio_min is not None or precio_max is not None:
                propiedades = [
                    (r, i)
                    for r, i in propiedades
                    if _precio(i) is not None
                    and (precio_min is None or _precio(i) >= precio_min)
                    and (precio_max is None or _precio(i) <= precio_max)
                ]

            # Coincidencia OR (basta una palabra) para no descartar todo por
            # una sola palabra que no aparezca literalmente.
            if zona_o_caracteristicas and zona_o_caracteristicas.strip():
                keywords = [
                    w for w in _normalize(zona_o_caracteristicas).split() if len(w) > 2
                ]
                if keywords:

                    def matches_any(info):
                        ubicacion = _sub(info, "ubicacion")
                        texto = _normalize(
                            " ".join(
                                str(x)
                                for x in (
                                    info.get("nombre", ""),
                                    ubicacion.get("barrio_vereda", ""),
                                    ubicacion.get("direccion", ""),
                                    info.get("resumen", ""),
                                    " ".join(_zonas_comunes(info)),
                                )
                            )
                        )
                        return any(kw in texto for kw in keywords)

                    propiedades = [(r, i) for r, i in propiedades if matches_any(i)]

            logger.debug(
                f"[IA-FILTRO] params={params} ciudad={ciudad!r} habitaciones_min={habitaciones_min!r} "
                f"tipo_propiedad={tipo_propiedad!r} zona_o_caracteristicas={zona_o_caracteristicas!r} "
                f"precio_min={precio_min!r} precio_max={precio_max!r} "
                f"-> quedaron {len(propiedades)} propiedades."
            )

            # Primero las que se ofrecen con precio (unidades en venta/arriendo);
            # los conjuntos y torres sin precio quedan al final.
            propiedades.sort(key=lambda ri: _precio(ri[1]) is None)
            final_list = propiedades[:MAX_RESULTADOS]

            if not final_list:
                result_text = "No se encontraron propiedades con esos criterios."
            else:
                result_text = "Propiedades disponibles:\n" + "\n".join(
                    _linea_compacta(r, i) for r, i in final_list
                )
                if len(propiedades) > MAX_RESULTADOS:
                    result_text += (
                        f"\n(Hay {len(propiedades) - MAX_RESULTADOS} más; "
                        "pide al usuario más criterios para afinar.)"
                    )

            self._cache.set(
                cache_key, result_text, ttl_seconds=settings.property_cache_ttl
            )
            return result_text

        except Exception as e:
            logger.error(f"Error obteniendo propiedades: {e}")
            return "Ocurrió un error al consultar las propiedades."

    async def get_property_detail(self, propiedad_id: int) -> str:
        """Detalle de una propiedad (resumen, zonas comunes, área y contacto)."""
        cache_key = make_cache_key("property_detail", propiedad_id)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            response = await self._get(f"{CHATBOT_ENDPOINT}/propiedad/{propiedad_id}")
            if response.status_code in (204, 404):
                return f"No se encontró la propiedad con ID {propiedad_id}."
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                data = data[0] if data else None
            if not data:
                return f"No se encontró la propiedad con ID {propiedad_id}."

            info = _parse_info(data)
            resumen = info.get("resumen")
            lineas = [resumen or _linea_compacta(data, info)]

            # El resumen del backend ya trae precio, habitaciones y baños.
            precio = _formato_precio(info)
            if precio and not resumen:
                lineas.append(f"Precio: {precio}.")

            zonas = _zonas_comunes(info)
            if zonas:
                lineas.append(f"Zonas comunes: {', '.join(zonas)}.")

            hab = _habitaciones(info)
            if hab is not None and not resumen:
                lineas.append(f"Habitaciones: {hab}.")

            banos = _sub(info, "distribucion").get("banos")
            if banos and not resumen:
                lineas.append(f"Baños: {banos}.")

            if _sub(info, "comercial").get("paga_administracion"):
                lineas.append("Paga administración.")

            antiguedad = info.get("antiguedad")
            if antiguedad:
                lineas.append(f"Antigüedad: {antiguedad}.")

            contacto = _sub(info, "contacto")
            datos_contacto = ", ".join(
                x for x in (contacto.get("empresa"), contacto.get("celular")) if x
            )
            if datos_contacto:
                lineas.append(f"Contacto: {datos_contacto}.")

            result_text = "\n".join(lineas)
            self._cache.set(
                cache_key, result_text, ttl_seconds=settings.property_cache_ttl
            )
            return result_text

        except Exception as e:
            logger.error(f"Error obteniendo detalle de propiedad {propiedad_id}: {e}")
            return "Ocurrió un error al consultar el detalle de la propiedad."

    async def close(self):
        await self.client.aclose()

    # ==================== USUARIOS / VALIDACIÓN ====================

    async def validate_user(self, phone: str) -> Optional[dict]:
        """
        Consulta si el usuario tiene contratos activos basado en su número de teléfono.
        NOTA: el backend aún no expone un endpoint de validación por teléfono,
        así que se trata a todos como prospectos.
        """
        # TODO: Implementar cuando el backend agregue esta ruta
        return None


# Singleton
_client_instance = None


def get_spring_client() -> SpringBootClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = SpringBootClient()
    return _client_instance
