from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    backend_url: str = "https://backend-inmoboot.onrender.com/api"
    backend_user: str = "app@inmobot.com"
    backend_password: str = "SW5tb2Jvb3QyMDI2KiM="
    google_api_key: str

    # --- Twilio WhatsApp ---
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""  # Ej: +14155238886

    # --- Meta WhatsApp Cloud API (legacy, opcional) ---
    whatsapp_token: str = ""
    whatsapp_verify_token: str = "inmobot_verify_2024"
    whatsapp_phone_number_id: str = ""

    # --- Configuración de respuestas rápidas y caché ---
    faq_cache_ttl: int = 3600  # TTL FAQs: 1 hora
    property_cache_ttl: int = 300  # TTL propiedades: 5 minutos
    enable_quick_responses: bool = True  # FAQ sin LLM

    class Config:
        env_file = ".env"


settings = Settings()
