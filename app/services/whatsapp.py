import httpx
import logging
from ..core.config import settings

logger = logging.getLogger(__name__)


async def send_whatsapp_message(to_number: str, message_text: str):
    """
    Envía un mensaje de WhatsApp usando Meta WhatsApp Cloud API.
    Si Meta no está configurado, intenta usar Twilio como fallback.
    """
    clean_number = to_number.replace("whatsapp:", "").replace("+", "").replace(" ", "").strip()

    # 1. Usar Meta WhatsApp Cloud API
    if settings.whatsapp_token and settings.whatsapp_phone_number_id and settings.whatsapp_token != "not_used":
        url = f"https://graph.facebook.com/v18.0/{settings.whatsapp_phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {settings.whatsapp_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_number,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message_text
            }
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()
                msg_id = result.get("messages", [{}])[0].get("id", "N/A")
                logger.info(f"Mensaje enviado vía Meta Cloud API a {clean_number} | ID: {msg_id}")
                return result
            except httpx.HTTPStatusError as e:
                logger.error(f"Error enviando mensaje por Meta ({e.response.status_code}): {e.response.text}")
                return None
            except Exception as e:
                logger.error(f"Error enviando mensaje por Meta: {e}")
                return None

    # 2. Fallback a Twilio si estuviera configurado
    elif settings.twilio_account_sid and settings.twilio_auth_token:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
        from_whatsapp = f"whatsapp:{settings.twilio_phone_number}"
        to_whatsapp = f"whatsapp:{to_number}" if not to_number.startswith("whatsapp:") else to_number

        payload = {
            "From": from_whatsapp,
            "To": to_whatsapp,
            "Body": message_text
        }
        auth = httpx.BasicAuth(settings.twilio_account_sid, settings.twilio_auth_token)

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, auth=auth, data=payload)
                response.raise_for_status()
                result = response.json()
                logger.info(f"Mensaje enviado vía Twilio a {to_number} | SID: {result.get('sid', 'N/A')}")
                return result
            except Exception as e:
                logger.error(f"Error enviando mensaje por Twilio: {e}")
                return None

    else:
        logger.error("No hay credenciales configuradas para WhatsApp (Meta o Twilio).")
        return None

