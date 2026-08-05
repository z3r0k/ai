from langchain.tools import tool
from ..services.spring_client import get_spring_client
import logging

logger = logging.getLogger(__name__)


@tool("search_properties")
async def search_properties(query: str) -> str:
    """Útil para buscar propiedades inmobiliarias disponibles basado en una consulta del usuario."""
    logger.info(f"Tool search_properties llamado con query: {query}")
    client = get_spring_client()
    try:
        # Usa el endpoint compacto que retorna texto plano optimizado para LLM.
        # Esto consume ~40% menos tokens que el JSON original.
        data = await client.get_properties_compact(query)
        return data if data else "No se encontraron propiedades con esos criterios."
    except Exception as e:
        logger.error(f"Error buscando propiedades: {e}")
        return "Hubo un error al consultar las propiedades disponibles."
