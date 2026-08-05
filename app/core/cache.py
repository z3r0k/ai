"""
Caché en memoria con expiración automática (TTL).
Evita llamadas repetidas al backend y al LLM para consultas idénticas.
"""
import time
import hashlib
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SimpleCache:
    """
    Caché key-value en memoria con Time-To-Live (TTL) por entrada.
    
    Uso:
        cache = SimpleCache()
        cache.set("propiedades_all", data, ttl_seconds=300)
        result = cache.get("propiedades_all")  # None si expiró
    """

    def __init__(self):
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        """Obtiene un valor del caché. Retorna None si no existe o expiró."""
        if key not in self._store:
            return None
        value, expires_at = self._store[key]
        if time.time() > expires_at:
            del self._store[key]
            logger.debug(f"Cache EXPIRED: {key}")
            return None
        logger.debug(f"Cache HIT: {key}")
        return value

    def set(self, key: str, value: Any, ttl_seconds: int = 300):
        """Almacena un valor con TTL en segundos (default: 5 minutos)."""
        expires_at = time.time() + ttl_seconds
        self._store[key] = (value, expires_at)
        logger.debug(f"Cache SET: {key} (TTL={ttl_seconds}s)")

    def invalidate(self, key: str):
        """Elimina una entrada específica del caché."""
        self._store.pop(key, None)

    def clear(self):
        """Limpia todo el caché."""
        self._store.clear()
        logger.info("Cache CLEARED")

    def cleanup_expired(self):
        """Elimina todas las entradas expiradas. Útil para mantenimiento periódico."""
        now = time.time()
        expired_keys = [k for k, (_, exp) in self._store.items() if now > exp]
        for key in expired_keys:
            del self._store[key]
        if expired_keys:
            logger.debug(f"Cache cleanup: {len(expired_keys)} entradas expiradas eliminadas")

    @property
    def size(self) -> int:
        """Número de entradas en el caché (incluyendo potencialmente expiradas)."""
        return len(self._store)


def make_cache_key(*args) -> str:
    """Genera una clave de caché determinista a partir de argumentos."""
    raw = "|".join(str(a) for a in args if a is not None)
    return hashlib.md5(raw.encode()).hexdigest()


# Singleton global
_cache_instance: Optional[SimpleCache] = None


def get_cache() -> SimpleCache:
    """Retorna la instancia singleton del caché."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = SimpleCache()
    return _cache_instance
