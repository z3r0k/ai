import hmac
import hashlib
from fastapi import Request, HTTPException
from .config import settings

async def verify_whatsapp_signature(request: Request):
    """Valida la firma HMAC X-Hub-Signature-256 de WhatsApp."""
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not signature:
        raise HTTPException(status_code=403, detail="Firma ausente")

    body = await request.body()
    # Genera la firma localmente con el APP_SECRET (para efectos prácticos usaremos verify_token por ahora)
    # En producción deberías usar el App Secret de Facebook Developer
    expected_signature = hmac.new(
        settings.whatsapp_verify_token.encode("utf-8"), 
        body, 
        hashlib.sha256
    ).hexdigest()
    
    expected_signature_header = f"sha256={expected_signature}"
    
    if not hmac.compare_digest(expected_signature_header, signature):
        raise HTTPException(status_code=403, detail="Firma inválida")
    return True
