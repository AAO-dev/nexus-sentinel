# Imagen del backend Nexus Sentinel (Fase 6).
# Despliegue objetivo: HF Spaces (Docker) o Render free.
# Construir desde la RAÍZ del repo:  docker build -f api/Dockerfile -t nexus-sentinel-api .

FROM python:3.11-slim

WORKDIR /app

# Dependencias mínimas primero (capa cacheable)
COPY api/requirements.txt ./api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

# Código del backend y del pipeline (src/ lo importa /inference/score si hay artefactos)
COPY api/ ./api/
COPY src/ ./src/

# El snapshot precomputado ES el dato que sirve la API (1.3 MB, versionado en el repo)
COPY docs/demo/snapshot.json ./docs/demo/snapshot.json

# HF Spaces expone 7860; Render inyecta $PORT
# DEEPSEEK_API_KEY se inyecta como secreto en el panel del servicio (NO se hornea en la imagen).
ENV PORT=7860 \
    SNAPSHOT_PATH=/app/docs/demo/snapshot.json \
    FEEDBACK_PATH=/app/data/feedback.jsonl
EXPOSE 7860

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
