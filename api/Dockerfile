# Imagen del backend de Nexus Sentinel.
# Desplegado en Render con runtime Docker (ver DEPLOY.md).
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

# Render inyecta $PORT en tiempo de ejecución; 7860 es el valor por defecto en local
# DEEPSEEK_API_KEY se inyecta como secreto en el panel del servicio (NO se hornea en la imagen).
ENV PORT=7860 \
    SNAPSHOT_PATH=/app/docs/demo/snapshot.json \
    FEEDBACK_PATH=/app/data/feedback.jsonl
EXPOSE 7860

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
