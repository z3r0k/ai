"""
Clasificador de intención SIN LLM.
Intercepta mensajes triviales (saludos, agradecimientos, pedir un asesor) y
los responde con textos locales, ahorrando el 100% de los tokens para esas
interacciones. El backend no expone endpoints de FAQ, así que todo lo demás
pasa al LLM.
"""
import logging
import re
import unicodedata
from typing import Optional

logger = logging.getLogger(__name__)

# Si el mensaje menciona un tipo de propiedad junto con un número
# (típicamente de habitaciones), es una búsqueda real y debe ir al LLM
# (que consulta search_properties), nunca a una respuesta rápida.
_TIPOS_PROPIEDAD_KEYWORDS = {
    "apartamento", "apartaestudio", "casa", "oficina", "local", "bodega",
    "finca", "lote", "terreno", "duplex", "triplex", "penthouse",
    "hacienda", "quinta", "taller", "fabrica", "almacen", "campestre",
    "inmueble", "propiedad",
}
_NUMEROS_PALABRA = {
    "uno", "una", "dos", "tres", "cuatro", "cinco", "seis", "siete",
    "ocho", "nueve", "diez",
}

_CONTACTO_ASESOR = "(601) 123-4567"

# Respuestas rápidas locales: (vocabulario, palabras clave, respuesta).
# Solo aplican si TODAS las palabras del mensaje pertenecen al vocabulario y
# al menos una es palabra clave (ej: "hola", "buenos días"), para no
# interceptar mensajes como "hola, busco apartamento en Bogotá".
_RESPUESTAS_RAPIDAS = [
    (
        {"hola", "buenas", "buenos", "buen", "dias", "dia", "tardes", "noches",
         "saludos", "hey", "que", "tal", "ola"},
        {"hola", "buenas", "buenos", "buen", "saludos", "hey", "ola"},
        "¡Hola! 👋 Soy InmoBot. Cuéntame qué buscas: ¿arriendo o compra, en qué ciudad y cuántas habitaciones?",
    ),
    (
        {"gracias", "muchas", "mil", "ok", "listo", "vale", "perfecto", "chao",
         "adios", "hasta", "luego", "pronto", "bueno"},
        {"gracias", "chao", "adios", "luego", "pronto"},
        "¡Con gusto! 😊 Si necesitas algo más, aquí estoy.",
    ),
    (
        {"asesor", "humano", "persona", "agente", "hablar", "con", "un", "una",
         "quiero", "necesito", "comunicarme", "contacto", "llamar", "numero",
         "telefono", "de", "el", "por", "favor"},
        {"asesor", "humano", "persona", "agente", "contacto", "llamar", "telefono"},
        f"Puedes comunicarte con un asesor al {_CONTACTO_ASESOR} 📞",
    ),
]


def _normalize(text: str) -> str:
    text = text.lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def _parece_busqueda_de_propiedad_especifica(text_norm: str) -> bool:
    tiene_tipo = any(k in text_norm for k in _TIPOS_PROPIEDAD_KEYWORDS)
    tiene_numero = bool(re.search(r"\d", text_norm)) or any(
        f" {n} " in f" {text_norm} " for n in _NUMEROS_PALABRA
    )
    return tiene_tipo and tiene_numero


class IntentClassifier:
    """
    Clasifica la intención del mensaje del usuario sin usar LLM.

    Flujo:
    1. Si parece una búsqueda de propiedad → None (va al LLM)
    2. Si coincide con una respuesta rápida local → la retorna (0 tokens LLM)
    3. En otro caso → None (el mensaje pasa al LLM)
    """

    async def classify(self, text: str) -> Optional[str]:
        """
        Intenta clasificar y responder el mensaje sin LLM.

        Args:
            text: Mensaje del usuario (ya sanitizado)

        Returns:
            Respuesta directa si hay match local, o None si debe ir al LLM
        """
        if not text or not text.strip():
            return None

        normalized = _normalize(text.strip())

        if _parece_busqueda_de_propiedad_especifica(normalized):
            logger.debug(
                f"'{normalized}' parece una búsqueda de propiedad específica; pasa al LLM."
            )
            return None

        palabras = re.findall(r"[a-z0-9]+", normalized)
        if not palabras:
            return None

        for vocabulario, claves, respuesta in _RESPUESTAS_RAPIDAS:
            if all(p in vocabulario for p in palabras) and any(p in claves for p in palabras):
                logger.info(f"Respuesta rápida local para: '{normalized}'")
                return respuesta

        return None


# Singleton
_classifier_instance: Optional[IntentClassifier] = None


def get_intent_classifier() -> IntentClassifier:
    """Retorna la instancia singleton del clasificador."""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = IntentClassifier()
    return _classifier_instance
