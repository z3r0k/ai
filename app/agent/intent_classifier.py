"""
Clasificador de intención SIN LLM.
Intercepta consultas frecuentes y las responde directamente desde el backend FAQ,
ahorrando el 100% de los tokens para esas interacciones.
"""
import logging
from typing import Optional

from ..services.spring_client import get_spring_client
from ..core.cache import get_cache, make_cache_key
from ..core.config import settings

logger = logging.getLogger(__name__)


class IntentClassifier:
    """
    Clasifica la intención del mensaje del usuario sin usar LLM.
    
    Flujo:
    1. Consulta el endpoint /api/bot/faq/match del backend
    2. Si hay coincidencia → retorna la respuesta FAQ (0 tokens LLM)
    3. Si no hay coincidencia → retorna None (el mensaje pasa al LLM)
    """

    def __init__(self):
        self._cache = get_cache()

    async def classify(self, text: str) -> Optional[str]:
        """
        Intenta clasificar y responder el mensaje sin LLM.
        
        Args:
            text: Mensaje del usuario (ya sanitizado)
            
        Returns:
            Respuesta directa si hay match FAQ, o None si debe ir al LLM
        """
        if not text or not text.strip():
            return None

        normalized = text.strip().lower()

        # 1. Verificar caché de FAQs
        cache_key = make_cache_key("faq_match", normalized)
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.info(f"FAQ respondida desde caché: '{normalized}' → intent={cached.get('intent', 'N/A')}")
            return cached.get("response")

        # 2. Consultar backend
        try:
            client = get_spring_client()
            result = await client.match_faq(normalized)

            if result and result.get("response"):
                # Guardar en caché por 1 hora (las FAQs no cambian frecuentemente)
                self._cache.set(cache_key, result, ttl_seconds=settings.faq_cache_ttl)
                logger.info(f"FAQ match: '{normalized}' → intent={result.get('intent', 'N/A')}")
                return result["response"]
            else:
                # Cachear el "miss" también para evitar queries repetidas (TTL corto)
                self._cache.set(cache_key, {"response": None}, ttl_seconds=60)
                logger.debug(f"No FAQ match para: '{normalized}'")
                return None

        except Exception as e:
            logger.warning(f"Error consultando FAQ backend: {e}. Pasando al LLM.")
            return None


# Singleton
_classifier_instance: Optional[IntentClassifier] = None


def get_intent_classifier() -> IntentClassifier:
    """Retorna la instancia singleton del clasificador."""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = IntentClassifier()
    return _classifier_instance
