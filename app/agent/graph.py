import asyncio

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from .tools import search_properties, get_property_detail
from .guardrails import sanitize_input
from .intent_classifier import get_intent_classifier
from ..core.config import settings
from ..services.whatsapp import send_whatsapp_message
from ..services.spring_client import get_spring_client
import logging

logger = logging.getLogger(__name__)

# Tiempo máximo total (en segundos) que esperamos al agente (Gemini + tools)
# antes de responderle al usuario que hay alta demanda, en vez de dejarlo
# esperando varios minutos mientras la librería agota sus reintentos.
AGENT_TIMEOUT_SECONDS = 30

# Configuración básica de Gemini. max_retries y timeout bajos a propósito:
# el default de la librería (6 intentos con backoff hasta 60s) puede hacer
# que una sola llamada tarde varios minutos ante un 503 de alta demanda.
llm = ChatGoogleGenerativeAI(
    model="gemini-flash-latest",
    google_api_key=settings.google_api_key,
    temperature=0.3,
    max_retries=2,
    timeout=15,
)

# Integración con herramientas usando LangGraph
agent_executor = create_react_agent(llm, [search_properties, get_property_detail])

# Prompt optimizado: instruye respuestas cortas para reducir tokens de salida ~30%
SYSTEM_PROMPT = """Eres InmoBot, asistente inmobiliario por WhatsApp. 
REGLAS ESTRICTAS:
- Máximo 3 oraciones por respuesta, excepto si muestras listados de propiedades.
- Usa emojis moderadamente (1-2 por mensaje).
- Si muestras propiedades, usa formato lista con bullet points e incluye el ID de cada una para que el usuario pueda pedir más detalles. NO repitas datos que ya están en el resultado de la herramienta, solo preséntalos organizados.
- Si el usuario pide más información de una propiedad, usa get_property_detail con su ID.
- Muestra el precio tal como viene en el resultado (en arriendo es el canon mensual). Si el usuario da un presupuesto, pásalo en pesos a search_properties (precio_max / precio_min).
- NUNCA inventes ni des por hecho datos que no estén literalmente en el resultado de las herramientas (precio, número de habitaciones, etc.). Si un dato aparece como N/D o no aparece, dilo así y sugiere contactar al asesor.
- Si el usuario pide algo que no puedes hacer, sugiere contactar al asesor humano al (601) 123-4567.
- Responde siempre en español colombiano, de forma cálida y profesional.
- NO hagas preámbulos largos, ve directo a la respuesta."""

# Clasificador de intención (FAQ sin LLM)
intent_classifier = get_intent_classifier()


async def process_message(text: str, from_number: str) -> str:
    """Función de orquestación con interceptor de respuestas rápidas."""
    try:
        # 1. Evaluar input con Pytector (solo registra en logs, no bloquea; ver guardrails.py)
        safe_text = sanitize_input(text)
        # 2. ¿Respuesta rápida disponible? (0 tokens LLM)
        if settings.enable_quick_responses:
            quick_response = await intent_classifier.classify(safe_text)
            if quick_response:
                logger.info(f"Respuesta rápida (sin LLM) para: '{safe_text[:50]}...'")
                await send_whatsapp_message(from_number, quick_response)
                return quick_response
        
        # 3. Validar usuario contra el backend para determinar flujo (Tickets vs Comercial)
        spring_client = get_spring_client()
        user_info = await spring_client.validate_user(from_number)
        
        if user_info and user_info.get("has_active_contract"):
            user_name = user_info.get("name", "Cliente")
            context_prompt = f"\n\nCONTEXTO ACTUAL DEL USUARIO:\nEl usuario se llama {user_name} y ES un cliente actual con contratos activos. Debes saludarlo por su nombre y guiarlo en el flujo de atención al cliente / tickets de soporte."
        else:
            context_prompt = f"\n\nCONTEXTO ACTUAL DEL USUARIO:\nEl usuario NO tiene contratos activos y es un Prospecto (Lead). Debes tratarlo con un enfoque comercial para ofrecerle nuestros servicios inmobiliarios."

        # 4. No hay FAQ match → usar LLM con prompt optimizado + contexto
        messages = [
            SystemMessage(content=SYSTEM_PROMPT + context_prompt),
            HumanMessage(content=safe_text)
        ]
        
        # 4. Ejecutar el grafo del agente (esto invoca herramientas si es necesario),
        # con un timeout total para no dejar al usuario esperando varios minutos
        # si Gemini está con alta demanda (503) y agota sus reintentos.
        try:
            response_state = await asyncio.wait_for(
                agent_executor.ainvoke({"messages": messages}),
                timeout=AGENT_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.error("Timeout esperando respuesta del agente/Gemini")
            error_msg = "Estamos con alta demanda en este momento. Por favor intenta de nuevo en un minuto 🙏"
            await send_whatsapp_message(from_number, error_msg)
            return error_msg
        last_msg = response_state["messages"][-1]
        
        # Extraer solo el texto limpio (sin signatures ni metadata de Gemini)
        if hasattr(last_msg, 'content'):
            content = last_msg.content
            if isinstance(content, list):
                # Gemini a veces devuelve lista de bloques [{text: ..., extras: ...}]
                parts = []
                for block in content:
                    if isinstance(block, dict) and 'text' in block:
                        parts.append(block['text'])
                    elif isinstance(block, str):
                        parts.append(block)
                response_text = "\n".join(parts)
            else:
                response_text = str(content)
        else:
            response_text = str(last_msg)
        
        # 5. Enviar respuesta a WhatsApp
        await send_whatsapp_message(from_number, response_text)
        
        return response_text
    except Exception as e:
        logger.error(f"Error en process_message: {e}")
        error_msg = "Lo siento, tuve un problema interno. Intenta de nuevo más tarde."
        await send_whatsapp_message(from_number, error_msg)
        return error_msg
