from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Equivale a {{URL_BASE}} de la colección Postman (dominio, sin /api).
    backend_url: str = "https://inmoboot-gestiona-tu-propiedad.onrender.com"
    backend_user: str = "app@inmobot.com"
    # Sin default: no dejar credenciales en el código fuente versionado.
    # Debe venir de la variable de entorno BACKEND_PASSWORD (ver .env).
    backend_password: str
    google_api_key: str

    # --- Meta WhatsApp Cloud API ---
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_business_account_id: str = ""
    whatsapp_verify_token: str = "inmobot_verify_2024"

    # --- Twilio WhatsApp (Opcional / Legacy) ---
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    # --- Configuración de respuestas rápidas y caché ---
    faq_cache_ttl: int = 3600  # TTL FAQs: 1 hora
    property_cache_ttl: int = 300  # TTL propiedades: 5 minutos
    enable_quick_responses: bool = True  # FAQ sin LLM

    class Config:
        env_file = ".env"
        extra = "allow"



settings = Settings()
