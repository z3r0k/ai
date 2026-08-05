import httpx
import logging
from ..core.config import settings

logger = logging.getLogger(__name__)


async def send_whatsapp_message(to_number: str, message_text: str):
    """
    Envía un mensaje de WhatsApp usando la API de Twilio.
    """
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"

    # Twilio requiere formato whatsapp:+<numero>
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
            logger.info(f"Mensaje enviado a {to_number} | SID: {result.get('sid', 'N/A')}")
            return result
        except httpx.HTTPStatusError as e:
            logger.error(f"Error enviando mensaje ({e.response.status_code}): {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Error enviando mensaje: {e}")
            return None
