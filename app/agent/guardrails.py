import logging

from pytector.detector import PromptInjectionDetector

logger = logging.getLogger(__name__)

# El modelo (protectai/deberta-v3-base-prompt-injection) no fue entrenado
# principalmente en español y da falsos positivos severos (score ~1.0) en
# frases inocuas como "Me indicas la dirección". Por eso, hoy NO bloqueamos
# automáticamente en base a su score: solo se registra en logs para poder
# decidir con datos reales (falsos positivos vs. detecciones reales) si vale
# la pena activar el bloqueo o evaluar un modelo/librería que generalice
# mejor a español.
THRESHOLD = 0.999

_detector_instance = None


def get_guardrails() -> PromptInjectionDetector:
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = PromptInjectionDetector()
    return _detector_instance


def sanitize_input(text: str) -> str:
    """
    Evalúa el texto contra el detector de prompt injection y registra el
    score obtenido, sin bloquear el mensaje (ver nota sobre THRESHOLD arriba).
    """
    detector = get_guardrails()
    try:
        is_injection, score = detector.detect_injection(text, threshold=THRESHOLD)
    except Exception as e:
        logger.warning(f"No se pudo evaluar prompt injection, continuando sin bloquear: {e}")
        return text

    if is_injection:
        score_text = "unknown" if score is None else f"{score:.4f}"
        logger.warning(
            f"Posible prompt injection detectado (score={score_text}, threshold={THRESHOLD:.4f}) "
            f"en texto: {text[:100]!r}. No se bloquea (ver nota en este archivo)."
        )
    return text
