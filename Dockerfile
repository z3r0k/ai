FROM python:3.11-slim
WORKDIR /app

# Forzar logs inmediatos y prevenir escritura de archivos .pyc
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Precargar en el build el modelo de detección de prompt-injection
# (protectai/deberta-v3-base-prompt-injection) para que quede horneado en la
# imagen. Render usa disco efímero, así que sin esto el modelo se
# re-descargaba desde HuggingFace Hub en cada restart, alargando el arranque.
RUN python -c "from transformers import AutoTokenizer, AutoModelForSequenceClassification; \
    AutoTokenizer.from_pretrained('protectai/deberta-v3-base-prompt-injection'); \
    AutoModelForSequenceClassification.from_pretrained('protectai/deberta-v3-base-prompt-injection')"

COPY ./app ./app

EXPOSE 8000

# Levantar el servidor usando el puerto que inyecta la plataforma (Render usa
# $PORT, no siempre 8000); se conserva 8000 como valor por defecto local.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
