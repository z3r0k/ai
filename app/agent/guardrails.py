from pytector import PytectorGuard

_guard_instance = None

def get_guardrails() -> PytectorGuard:
    global _guard_instance
    if _guard_instance is None:
        # Inicializar pytector con un umbral muy alto para evitar falsos positivos en español
        _guard_instance = PytectorGuard(
            threshold=0.999
        )
    return _guard_instance

def sanitize_input(text: str) -> str:
    guard = get_guardrails()
    return guard.invoke(text)
