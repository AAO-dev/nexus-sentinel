# API — Nexus Sentinel (Fase 6)

Backend FastAPI que expone la cola de triage priorizada y explicada. Es el **dueño de todo el
conocimiento de ML** (puntuaciones, niveles, umbrales, SHAP); el frontend React consume y presenta,
nunca recalcula (división de responsabilidades, sección 8.0 del plan).

## Contrato (7 endpoints + inferencia en vivo)

| Método | Ruta | Respuesta |
|---|---|---|
| GET | `/health` | Estado del servicio y del snapshot cargado |
| GET | `/overview` | KPIs: alertas activas, casos rojos, riesgo organizacional, tendencia diaria |
| GET | `/employees?sort=risk&level=rojo&limit=50` | Cola de triage (IDs anonimizados `U-####`) |
| GET | `/employees/{id}/risk?days=30` | Serie temporal de la puntuación 0-100 |
| GET | `/employees/{id}/explanation?date=D` | Top-5 SHAP + valor vs. promedio personal y vs. peer group |
| GET | `/employees/{id}/activity?date=D` | Destinos nuevos, fallos, NTLM, horario **+ nodos del mini-grafo ego** |
| POST | `/cases/{id}/feedback` | Decisión del analista (`falso_positivo` / `investigar` / `escalar`) |
| GET | `/cases/{id}/feedback` | Historial de decisiones del caso (trazabilidad para Cumplimiento) |
| POST | `/inference/score` | **Inferencia real** sobre un usuario-día (demuestra el flujo completo) |
| GET | `/assistant/health` | Si el asistente conversacional está configurado |
| POST | `/assistant/chat` | **Asistente conversacional** (DeepSeek + function calling) |

### Asistente conversacional

`POST /assistant/chat` implementa el asistente (requerimiento del profesor) adaptando la técnica de
**function calling** de sus notebooks de ejemplo: el modelo (DeepSeek, compatible con el SDK de
OpenAI) responde preguntas del usuario y, cuando necesita datos, llama a herramientas que consultan
el snapshot —resumen, cola de triage, explicación y actividad de un usuario— para no inventar
cifras. Sirve de guía (conceptos, cómo navegar) y de consulta sobre el periodo analizado.

- La **API key vive solo en el backend** (`DEEPSEEK_API_KEY`), nunca en el frontend.
- Sin key, `/assistant/chat` responde **503** y el widget de la UI queda deshabilitado con un aviso;
  el resto de la consola funciona igual. Ver [DEPLOY.md](../DEPLOY.md) para obtener la key gratuita.

### Cómo el modelado llega a la interfaz

```
Fase 4  entrena          → models/*.joblib          (binarios, NO versionados: se regeneran)
Fase 5  puntúa y guarda  → docs/demo/snapshot.json  (1.3 MB, SÍ versionado: el puente)
Fase 6  sirve            → esta API                 (carga el snapshot al arrancar)
Fase 7  consume          → UI React                 (fetch a los endpoints)
```

El snapshot es el artefacto que **materializa los resultados del modelo**: contiene, por cada
usuario-día del periodo de prueba, la puntuación 0-100, el nivel del semáforo, la probabilidad
calibrada, el top-5 SHAP con comparativas, el resumen de actividad y los nodos del grafo ego.
Regenerarlo: `python -m src.inference`.

| Vista del plan | Endpoints que la alimentan |
|---|---|
| **V1 Triage** | `/overview`, `/employees`, `/employees/{id}/risk`, `/employees/{id}/explanation`, `POST /cases/{id}/feedback` |
| **V2 Investigación** | `/employees/{id}/activity` (incluye `ego_graph`), `/employees/{id}/explanation` (comparativas personal/pares), `GET /cases/{id}/feedback` |
| **V3 Panel ejecutivo** | `/overview` → `tendencia_por_cluster` y `kpis_soc` |

OpenAPI interactivo en **`/docs`**. De ese esquema el frontend genera sus tipos TypeScript
(`openapi-typescript`), de modo que un cambio de contrato rompe el build y no la demo.

### Códigos de estado con significado
- **404** — empleado o día inexistente en el periodo servido.
- **409** — el día existe pero es **nivel verde**: registro pasivo sin explicación ni detalle
  (decisión de diseño de la sección 1, no un error).
- **422** — parámetros fuera de contrato (nivel inválido, decisión no permitida...).
- **503** — `/inference/score` sin artefactos en este despliegue; degradación explícita, nunca
  un fallo opaco.

## Ejecutar en local

```bash
pip install -r api/requirements.txt
uvicorn api.main:app --reload          # http://127.0.0.1:8000/docs
```

Requiere `docs/demo/snapshot.json` (se genera en la Fase 5 con `python -m src.inference`).

## Pruebas de contrato

```bash
pytest api/tests -q      # 15 tests
```

Son la **definición de "listo"** del backend: verifican códigos de estado, forma de la respuesta e
invariantes de negocio (cola priorizada, IDs anonimizados, ninguna puntuación sin explicación,
coherencia entre la inferencia en vivo y el snapshot).

## Despliegue

```bash
docker build -f api/Dockerfile -t nexus-sentinel-api .
docker run -p 7860:7860 nexus-sentinel-api
```

- **Hugging Face Spaces (Docker):** puerto 7860 por defecto.
- **Render free:** inyecta `$PORT`, ya contemplado en el `CMD`.

### Variables de entorno

| Variable | Default | Uso |
|---|---|---|
| `SNAPSHOT_PATH` | `docs/demo/snapshot.json` | Datos que sirve la API |
| `FEEDBACK_PATH` | `data/feedback.jsonl` | Persistencia del feedback del analista |
| `MODELS_DIR` | `models/` | Artefactos para `/inference/score` |
| `CORS_ORIGINS` | `*` | **Restringir al dominio del frontend en producción** |

### Notas de despliegue
- La imagen instala solo las dependencias mínimas: los endpoints del snapshot funcionan y
  `/inference/score` responde 503. Para habilitar la inferencia en vivo hay que añadir el stack de
  modelado completo (xgboost, shap, scikit-learn) y montar `models/` — encarece bastante la imagen.
- El feedback se guarda en disco: en los planes gratuitos el almacenamiento es **efímero** y se
  pierde al reiniciar. Suficiente para la demo; en producción iría a una base de datos.
