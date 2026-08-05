import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from .api.webhooks import router as webhooks_router
from .services.spring_client import get_spring_client
from .agent.guardrails import get_guardrails

# Configuración de Logging en formato JSON
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lógica de inicio (ej. cargar modelo, instanciar HTTPX client)
    logger.info("Inicializando cliente HTTPX y modelo LLM...")
    client = get_spring_client()
    guard = get_guardrails()
    yield
    # Lógica de apagado
    logger.info("Cerrando recursos...")
    await client.close()

app = FastAPI(title="WhatsApp AI Agent", lifespan=lifespan)

app.include_router(webhooks_router, prefix="/api/v1")

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Error global: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor"}
    )
