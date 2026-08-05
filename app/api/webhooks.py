from fastapi import APIRouter, Request, HTTPException, Form, BackgroundTasks
from fastapi.responses import PlainTextResponse
import logging
from ..core.config import settings
from ..agent.graph import process_message
from ..services.whatsapp import send_whatsapp_message

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/webhook")
async def verify_webhook(request: Request):
    """Verificación de Webhook para WhatsApp Cloud API (Meta)."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == settings.whatsapp_verify_token:
            logger.info("Webhook verificado correctamente.")
            return int(challenge)
        else:
            raise HTTPException(
                status_code=403, detail="Token de verificación inválido"
            )
    raise HTTPException(status_code=400, detail="Faltan parámetros")


@router.post("/webhook")
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    """
    Recepción de mensajes de WhatsApp.
    Soporta ambos formatos: Twilio (form-encoded) y Meta Cloud API (JSON).
    """
    content_type = request.headers.get("content-type", "")

    try:
        if "application/x-www-form-urlencoded" in content_type:
            # ========== FORMATO TWILIO ==========
            form = await request.form()
            from_number = form.get("From", "")  # whatsapp:+573001234567
            body = form.get("Body", "")
            profile_name = form.get("ProfileName", "")

            # Limpiar el prefijo whatsapp: del número
            clean_number = from_number.replace("whatsapp:", "").strip()

            if not body:
                logger.info("Mensaje vacío de Twilio, ignorando.")
                return PlainTextResponse("", status_code=200)

            logger.info(f"Mensaje Twilio de {profile_name} ({clean_number}): {body}")

            # Procesar con el agente en segundo plano para evitar timeout de Twilio
            background_tasks.add_task(process_message, body, clean_number)

            # Twilio espera respuesta vacía o TwiML de inmediato
            return PlainTextResponse("", status_code=200)

        else:
            # ========== FORMATO META CLOUD API ==========
            payload = await request.json()
            logger.info(f"Mensaje recibido: {payload}")

            entry = payload.get("entry", [])[0]
            changes = entry.get("changes", [])[0]
            value = changes.get("value", {})
            messages = value.get("messages", [])

            if messages:
                msg = messages[0]
                from_number = msg.get("from")
                text = msg.get("text", {}).get("body", "")

                # Procesar con el agente en segundo plano para evitar timeout
                background_tasks.add_task(process_message, text, from_number)

    except Exception as e:
        logger.error(f"Error procesando mensaje: {str(e)}", exc_info=True)

    return {"status": "ok"}
