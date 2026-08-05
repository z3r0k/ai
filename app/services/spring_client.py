import httpx
import logging
from typing import Optional
from ..core.config import settings
from ..core.cache import get_cache, make_cache_key

logger = logging.getLogger(__name__)


class SpringBootClient:
    def __init__(self):
        self.client = httpx.AsyncClient(base_url=settings.backend_url, timeout=10.0)
        self._cache = get_cache()
        self._token = None

    async def _ensure_token(self):
        if not self._token:
            logger.info("Autenticando contra el backend...")

            payload = {
                "email": settings.backend_user,
                "password": settings.backend_password,
            }

            try:
                resp = await self.client.post("/auth/login", json=payload)
                resp.raise_for_status()
                data = resp.json()
                self._token = (
                    data.get("token") or data.get("accessToken") or data.get("jwt")
                )
                if self._token:
                    self.client.headers["Authorization"] = f"Bearer {self._token}"
                    logger.info("Token JWT obtenido exitosamente.")
                else:
                    logger.error(f"Estructura de token desconocida: {data}")
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

    # ==================== FAQ ====================

    async def match_faq(self, text: str) -> Optional[dict]:
        """
        Consulta el endpoint de FAQ match del backend.
        Retorna {"intent": "...", "response": "..."} o None.
        """
        try:
            response = await self._get("/bot/faq/match", params={"q": text})
            if response.status_code == 204:
                return None
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error consultando FAQ: {e}")
            return None

    async def get_all_faqs(self) -> list:
        """Obtiene todas las FAQs activas (para precargar caché)."""
        try:
            response = await self._get("/bot/faq")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error obteniendo FAQs: {e}")
            return []

    # ==================== PROPIEDADES ====================

    async def get_properties_compact(self, query: str = "", tipo: str = "") -> str:
        """
        Obtiene propiedades del backend y retorna un texto resumido (optimizado para LLM).
        """
        # Intentar caché primero
        cache_key = make_cache_key("properties_compact", query, tipo)
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.info("Propiedades servidas desde caché")
            return cached

        try:
            # El backend actual solo tiene GET /api/properties (que devuelve todas)
            response = await self._get("/properties")
            response.raise_for_status()
            properties = response.json()

            # IMPRIMIR LOG PARA EL USUARIO EN CONSOLA
            print(
                f"\n[DEBUG BACKEND] Conexión exitosa. Se descargaron {len(properties)} propiedades desde la base de datos."
            )

            # Limpiar y reducir el tamaño adaptándose a la estructura de la base de datos (tb_propiedad y tb_detalle_propiedad)
            cleaned_properties = []
            for p in properties:
                # Intentar extraer precio (puede venir en la raíz o dentro de detallePropiedad)
                detalle = p.get("detallePropiedad") or p.get("detalle") or {}
                precio = p.get("precio") or detalle.get("precio") or 0

                # Intentar extraer municipio/ciudad
                municipio_obj = (
                    p.get("municipio")
                    or detalle.get("municipio")
                    or p.get("ciudad")
                    or {}
                )
                if isinstance(municipio_obj, dict):
                    ciudad = (
                        municipio_obj.get("descripcionMunicipio")
                        or municipio_obj.get("nombre")
                        or municipio_obj.get("descripcion_municipio")
                        or "Desconocida"
                    )
                else:
                    ciudad = str(municipio_obj)

                tipo_obj = (
                    p.get("tipoPropiedad")
                    or p.get("tipoInmueble")
                    or p.get("tipo")
                    or detalle.get("tipoPropiedad")
                    or detalle.get("tipoInmueble")
                    or detalle.get("tipo")
                    or ""
                )
                if isinstance(tipo_obj, dict):
                    tipo = (
                        tipo_obj.get("descripcion")
                        or tipo_obj.get("nombre")
                        or tipo_obj.get("descripcionTipo")
                        or ""
                    )
                else:
                    tipo = str(tipo_obj)

                cleaned_properties.append(
                    {
                        "nombre": p.get("nombrePropiedad", "Desconocido"),
                        "descripcion": (p.get("descripcion", "")[:150] + "...")
                        if p.get("descripcion")
                        else "",
                        "direccion": p.get("direccionCompleta", "No especificada"),
                        "precio": precio,
                        "tipo": tipo,
                        "ciudad": ciudad,
                    }
                )

            # Filtrar por query si existe
            if query and query.strip():
                import unicodedata

                def normalize(t):
                    t = str(t).lower()
                    return "".join(
                        c
                        for c in unicodedata.normalize("NFD", t)
                        if unicodedata.category(c) != "Mn"
                    )

                query_norm = normalize(query)
                stop_words = [
                    "busco",
                    "quiero",
                    "necesito",
                    "arriendo",
                    "propiedad",
                    "inmuebles",
                    "inmueble",
                    "en",
                    "de",
                    "para",
                    "con",
                    "un",
                    "una",
                    "los",
                    "las",
                ]
                keywords = [
                    w for w in query_norm.split() if w not in stop_words and len(w) > 2
                ]

                print(
                    f"[DEBUG BACKEND] La IA intentó buscar: '{query}'. Palabras clave extraídas: {keywords}"
                )

                filtered = []
                for p in cleaned_properties:
                    text_to_search = normalize(
                        f"{p.get('nombre')} {p.get('descripcion')} {p.get('direccion')} {p.get('ciudad')} {p.get('tipo')}"
                    )

                    # Si tiene keywords, requerimos que todas las keywords (o su forma singular) estén en el texto
                    match = True
                    for kw in keywords:
                        kw_sing = kw[:-1] if (kw.endswith("s") and len(kw) > 3) else kw
                        kw_sing_es = kw[:-2] if (kw.endswith("es") and len(kw) > 4) else kw_sing
                        if (
                            kw not in text_to_search
                            and kw_sing not in text_to_search
                            and kw_sing_es not in text_to_search
                        ):
                            match = False
                            break
                    if match or not keywords:
                        filtered.append(p)
                cleaned_properties = filtered

            print(
                f"[DEBUG BACKEND] Quedaron {len(cleaned_properties)} propiedades después de aplicar el filtro."
            )

            # Limitar a 5 resultados para no saturar tokens
            final_list = cleaned_properties[:5]

            if not final_list:
                return "No se encontraron propiedades."

            # Formatear a texto plano para el LLM
            result_text = "Propiedades disponibles:\n"
            for p in final_list:
                tipo_str = f" ({p['tipo']})" if p.get("tipo") else ""
                result_text += f"- {p['nombre']}{tipo_str} en {p['ciudad']}. Precio: {p['precio']}. Dir: {p['direccion']}. Detalle: {p['descripcion']}\n"

            # Guardar en caché
            self._cache.set(
                cache_key, result_text, ttl_seconds=settings.property_cache_ttl
            )
            return result_text

        except Exception as e:
            logger.error(f"Error obteniendo propiedades: {e}")
            return "Ocurrió un error al consultar las propiedades."

    async def close(self):
        await self.client.aclose()

    # ==================== USUARIOS / VALIDACIÓN ====================

    async def validate_user(self, phone: str) -> Optional[dict]:
        """
        Consulta si el usuario tiene contratos activos basado en su número de teléfono.
        NOTA: Actualmente el backend no tiene implementado /api/bot/users/validate
        por lo que simulamos que no se encuentra para evitar el error 404.
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
