"""Nexus Sentinel — API de consumo de modelos.

Responsabilidad del backend: es el dueño de TODO el conocimiento de
ML — puntuaciones, niveles, umbrales y explicaciones SHAP — y lo expone por un contrato OpenAPI
tipado. El frontend consume y presenta; jamás recalcula riesgo.

Estrategia de servicio:
- Los 6 endpoints de lectura sirven el **snapshot precomputado** del periodo de prueba
  (`docs/demo/snapshot.json`): estable y rápido para la demo en vivo, sin dependencia de modelos
  en memoria.
- `POST /inference/score` ejecuta **inferencia real** sobre un usuario-día para demostrar el flujo
  completo. Carga los artefactos de forma perezosa; si no están disponibles (despliegue ligero),
  responde 503 con un mensaje explícito en lugar de fallar de forma opaca.
- `POST /cases/{id}/feedback` cierra el ciclo human-in-the-loop: el analista decide, el sistema
  solo registra.

Ejecutar en local:  uvicorn api.main:app --reload    → OpenAPI en /docs
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = Path(os.getenv("SNAPSHOT_PATH", REPO_ROOT / "docs" / "demo" / "snapshot.json"))
FEEDBACK_PATH = Path(os.getenv("FEEDBACK_PATH", REPO_ROOT / "data" / "feedback.jsonl"))
MODELS_DIR = Path(os.getenv("MODELS_DIR", REPO_ROOT / "models"))
# CORS: en despliegue se restringe al dominio del frontend (variable de entorno)
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

app = FastAPI(
    title="Nexus Sentinel API",
    version="1.0.0",
    description=(
        "UEBA sobre datos reales de LANL. Sirve la cola de triage priorizada por riesgo (0-100), "
        "siempre acompañada de su explicación SHAP. Ninguna acción sobre cuentas es automática: "
        "el sistema prioriza y explica, la decisión es humana."
    ),
)
app.add_middleware(
    CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=False,
    allow_methods=["GET", "POST"], allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Carga del snapshot (una vez, en memoria)
# ---------------------------------------------------------------------------

def _load_snapshot() -> dict:
    if not SNAPSHOT_PATH.exists():
        raise RuntimeError(
            f"No se encontró el snapshot en {SNAPSHOT_PATH}. Genéralo con "
            "`python -m src.inference` o define SNAPSHOT_PATH."
        )
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


SNAPSHOT: dict = _load_snapshot()
_ARTIFACTS: dict | None = None  # carga perezosa para /inference/score


def _get_employee(employee_id: str) -> dict:
    """Detalle de un empleado o 404 explícito (solo hay detalle de los investigables)."""
    detail = SNAPSHOT["detail"].get(employee_id)
    if detail is None:
        conocido = any(e["id"] == employee_id for e in SNAPSHOT["employees"])
        raise HTTPException(
            status_code=404,
            detail=(f"{employee_id} no tuvo días con alerta en el periodo (solo registro pasivo)."
                    if conocido else f"Empleado {employee_id} no existe en el periodo servido."),
        )
    return detail


def _get_day(detail: dict, date: int) -> dict:
    dia = detail["days"].get(str(date))
    if dia is None:
        raise HTTPException(status_code=404,
                            detail=f"Sin datos de {detail['id']} para el día {date}.")
    return dia


# ---------------------------------------------------------------------------
# Esquemas de respuesta (tipan el OpenAPI que consume el frontend)
# ---------------------------------------------------------------------------

class Nivel(str, Enum):
    verde = "verde"
    naranja = "naranja"
    rojo = "rojo"


class Decision(str, Enum):
    falso_positivo = "falso_positivo"
    investigar = "investigar"
    escalar = "escalar"


class Health(BaseModel):
    status: str = "ok"
    snapshot_cargado: bool
    periodo_dias: list[int]
    usuarios: int


class PuntoTendencia(BaseModel):
    day: int
    alertas: int
    riesgo_medio: float


class PuntoCluster(BaseModel):
    peer_cluster: int
    day: int
    riesgo_medio: float
    alertas: int
    usuarios: int


class KpisSoc(BaseModel):
    alertas_por_dia: float
    casos_rojos_por_dia: float
    pct_falsos_positivos: float = Field(..., description="Sobre las alertas emitidas (ground truth)")
    cuentas_comprometidas_detectadas: int
    cuentas_comprometidas_totales: int
    carga_revisable: str
    tiempo_resolucion_medio: float | None = Field(
        None, description="Requiere telemetría real de analistas; null en la demo (no se estima)")


class Overview(BaseModel):
    alertas_activas: int = Field(..., description="Usuario-días en nivel naranja o rojo")
    casos_rojos: int
    usuarios_monitoreados: int
    riesgo_organizacional: float = Field(..., description="Riesgo medio 0-100 del periodo")
    cuentas_comprometidas_periodo: int = Field(
        ..., description="Ground truth del red team (solo para la demo académica)")
    tendencia: list[PuntoTendencia]
    tendencia_por_cluster: list[PuntoCluster] = Field(
        default_factory=list, description="Riesgo por rol conductual (vista ejecutiva)")
    kpis_soc: KpisSoc | None = None


class EmpleadoCola(BaseModel):
    id: str = Field(..., examples=["U-0737"], description="ID anonimizado")
    risk_max: float
    level: Nivel
    dia_pico: int
    n_dias_alerta: int
    motivo: str = Field(..., description="Razón principal en una línea, derivada del top SHAP")
    es_comprometida: int = Field(..., description="Ground truth (demo académica)")


class PuntoRiesgo(BaseModel):
    day: int
    risk: float
    level: Nivel


class SerieRiesgo(BaseModel):
    id: str
    peer_cluster: int
    timeline: list[PuntoRiesgo]


class ContribucionShap(BaseModel):
    feature: str
    label: str
    contribucion: float = Field(..., description="Aporte SHAP (signo = dirección)")
    valor: float
    promedio_personal: float | None = Field(None, description="Media histórica del propio usuario")
    promedio_peer: float | None = Field(None, description="Media de su peer group ese día")


class Explicacion(BaseModel):
    id: str
    day: int
    risk: float
    level: Nivel
    prob: float
    motivo: str
    top_shap: list[ContribucionShap]


class EgoGraph(BaseModel):
    """Nodos del mini-grafo usuario→computadoras que dibuja la vista de investigación."""
    nodos_nuevos: list[str] = Field(..., description="Destinos tocados por primera vez (en rojo)")
    nodos_conocidos: list[str] = Field(..., description="Destinos ya conocidos (en gris)")
    n_nuevos: int
    n_conocidos: int
    n_historicos_totales: int
    conocidos_truncados: bool = Field(..., description="True si se recortó la lista por legibilidad")


class Actividad(BaseModel):
    id: str
    day: int
    n_eventos: int
    n_dst: int
    n_destinos_nuevos: int
    n_origenes_nuevos: int
    n_fallos: int
    ratio_ntlm: float
    n_fuera_horario: int
    ego_graph: EgoGraph | None = None


class FeedbackIn(BaseModel):
    decision: Decision
    analista: str = Field("anonimo", max_length=64)
    dia: int | None = None
    nota: str | None = Field(None, max_length=500)


class FeedbackOut(BaseModel):
    registrado: bool
    case_id: str
    decision: Decision
    timestamp: str


class FeedbackRegistro(BaseModel):
    """Una decisión registrada, tal como se consulta en el historial del caso."""
    case_id: str
    decision: Decision
    analista: str
    timestamp: str
    dia: int | None = None
    nota: str | None = None


class MensajeChat(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=2000)


class ChatIn(BaseModel):
    messages: list[MensajeChat] = Field(..., min_length=1, max_length=20,
                                        description="Historial de la conversación, sin el system.")


class ChatOut(BaseModel):
    reply: str
    tools_used: list[str] = Field(default_factory=list,
                                  description="Herramientas de datos que el asistente consultó")


class InferenciaIn(BaseModel):
    employee_id: str = Field(..., examples=["U-0737"])
    day: int = Field(..., examples=[29])


class InferenciaOut(BaseModel):
    id: str
    day: int
    risk_score: float
    level: Nivel
    prob: float
    anomaly: float
    motivo: str
    top_shap: list[ContribucionShap]
    fuente: str = Field(..., description="'modelo_en_vivo' o el motivo de la degradación")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=Health, tags=["sistema"])
def health() -> Health:
    """Estado del servicio y del snapshot cargado."""
    return Health(
        snapshot_cargado=bool(SNAPSHOT),
        periodo_dias=SNAPSHOT["meta"]["periodo_dias"],
        usuarios=len(SNAPSHOT["employees"]),
    )


@app.get("/overview", response_model=Overview, tags=["triage"])
def overview() -> Overview:
    """KPIs del panel: alertas activas, casos rojos, riesgo organizacional y tendencia diaria."""
    return Overview(**SNAPSHOT["overview"])


@app.get("/employees", response_model=list[EmpleadoCola], tags=["triage"])
def employees(
    sort: str = Query("risk", pattern="^(risk|alertas)$"),
    level: Nivel | None = Query(None, description="Filtra por nivel del semáforo"),
    limit: int = Query(50, ge=1, le=500),
) -> list[EmpleadoCola]:
    """Cola de triage priorizada (usuarios anonimizados U-####)."""
    items = SNAPSHOT["employees"]
    if level is not None:
        items = [e for e in items if e["level"] == level.value]
    clave = "risk_max" if sort == "risk" else "n_dias_alerta"
    items = sorted(items, key=lambda e: e[clave], reverse=True)[:limit]
    return [EmpleadoCola(**e) for e in items]


@app.get("/employees/{employee_id}/risk", response_model=SerieRiesgo, tags=["empleado"])
def employee_risk(employee_id: str, days: int = Query(30, ge=1, le=60)) -> SerieRiesgo:
    """Serie temporal de la puntuación de riesgo (últimos `days` días disponibles)."""
    detail = _get_employee(employee_id)
    return SerieRiesgo(id=detail["id"], peer_cluster=detail["peer_cluster"],
                       timeline=[PuntoRiesgo(**p) for p in detail["timeline"][-days:]])


@app.get("/employees/{employee_id}/explanation", response_model=Explicacion, tags=["empleado"])
def employee_explanation(employee_id: str, date: int) -> Explicacion:
    """Top-5 SHAP del día, con el valor del usuario vs. su promedio personal y vs. su peer group.

    Solo hay explicación para días con alerta: los verdes son registro pasivo.
    """
    detail = _get_employee(employee_id)
    dia = _get_day(detail, date)
    if "shap_top" not in dia:
        raise HTTPException(
            status_code=409,
            detail=f"El día {date} de {employee_id} es nivel verde (registro pasivo, sin explicación).")
    return Explicacion(id=detail["id"], day=date, risk=dia["risk"], level=dia["level"],
                       prob=dia["prob"], motivo=dia["motivo"],
                       top_shap=[ContribucionShap(**s) for s in dia["shap_top"]])


@app.get("/employees/{employee_id}/activity", response_model=Actividad, tags=["empleado"])
def employee_activity(employee_id: str, date: int) -> Actividad:
    """Resumen de autenticaciones del día: destinos nuevos, fallos, NTLM y horario."""
    detail = _get_employee(employee_id)
    dia = _get_day(detail, date)
    if "activity" not in dia:
        raise HTTPException(status_code=409,
                            detail=f"El día {date} de {employee_id} es nivel verde (sin detalle).")
    ego = dia.get("ego_graph")
    return Actividad(id=detail["id"], day=date, **dia["activity"],
                     ego_graph=EgoGraph(**ego) if ego else None)


@app.post("/cases/{case_id}/feedback", response_model=FeedbackOut, status_code=201, tags=["triage"])
def case_feedback(case_id: str, body: FeedbackIn) -> FeedbackOut:
    """Registra la decisión del analista (falso positivo / investigar / escalar).

    Cierra el ciclo human-in-the-loop: ninguna acción sobre la cuenta es automática, y la decisión
    queda trazada para auditoría.
    Nota de despliegue: en planes gratuitos el almacenamiento es efímero.
    """
    registro = {"case_id": case_id, **body.model_dump(),
                "timestamp": datetime.now(timezone.utc).isoformat()}
    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FEEDBACK_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(registro, ensure_ascii=False) + "\n")
    return FeedbackOut(registrado=True, case_id=case_id, decision=body.decision,
                       timestamp=registro["timestamp"])


@app.get("/cases/{case_id}/feedback", response_model=list[FeedbackRegistro], tags=["triage"])
def case_feedback_history(case_id: str) -> list[FeedbackRegistro]:
    """Historial de decisiones del analista sobre un caso.

    Cierra la trazabilidad que exige un perfil de cumplimiento: toda decisión sobre
    una cuenta queda registrada y es consultable.
    """
    if not FEEDBACK_PATH.exists():
        return []
    registros = []
    for linea in FEEDBACK_PATH.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        try:
            r = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if r.get("case_id") == case_id:
            registros.append(FeedbackRegistro(**r))
    return registros


@app.get("/assistant/health", tags=["asistente"])
def assistant_health() -> dict:
    """Indica si el asistente conversacional está configurado (DEEPSEEK_API_KEY presente)."""
    from src.assistant import DEEPSEEK_MODEL, assistant_available

    return {"disponible": assistant_available(), "modelo": DEEPSEEK_MODEL}


@app.post("/assistant/chat", response_model=ChatOut, tags=["asistente"])
def assistant_chat(body: ChatIn) -> ChatOut:
    """Asistente conversacional: guía al usuario y responde preguntas sobre los datos
    consultando el modelo mediante function calling (DeepSeek).

    La API key vive solo en el backend. Sin ella, degrada con 503 explícito.
    """
    from src.assistant import assistant_available, chat

    if not assistant_available():
        raise HTTPException(
            status_code=503,
            detail=("El asistente no está configurado en este despliegue. Define DEEPSEEK_API_KEY "
                    "en el backend (key gratuita en https://platform.deepseek.com)."))
    try:
        resultado = chat([m.model_dump() for m in body.messages], SNAPSHOT)
        return ChatOut(**resultado)
    except HTTPException:
        raise
    except Exception as exc:  # error de red o de la API de DeepSeek
        raise HTTPException(status_code=502,
                            detail=f"El asistente no pudo responder: {exc}") from exc


@app.post("/inference/score", response_model=InferenciaOut, tags=["inferencia"])
def inference_score(body: InferenciaIn) -> InferenciaOut:
    """Inferencia REAL sobre un usuario-día: ejecuta el modelo en vivo.

    Demuestra el flujo completo frente al snapshot precomputado. Requiere los artefactos
    serializados; si no están presentes responde 503 en lugar de fallar de forma opaca.
    """
    global _ARTIFACTS
    try:
        import pandas as pd

        from src import inference as inf
        from src.models import three_way_split

        if _ARTIFACTS is None:
            _ARTIFACTS = inf.load_artifacts(MODELS_DIR)
        tabla = REPO_ROOT / "data" / "work" / "user_day_features.parquet"
        if not tabla.exists():
            raise FileNotFoundError(tabla)
        ud = three_way_split(pd.read_parquet(tabla))
        ud["display_id"] = ud["src_user"].map(inf.display_id)
        fila = ud[(ud.display_id == body.employee_id) & (ud.day == body.day)]
        if fila.empty:
            raise HTTPException(status_code=404,
                                detail=f"Sin features para {body.employee_id} en el día {body.day}.")
        res = inf.score_user_day(_ARTIFACTS, fila.iloc[0])
        return InferenciaOut(**res, fuente="modelo_en_vivo")
    except HTTPException:
        raise
    except Exception as exc:  # artefactos o tabla no disponibles en este despliegue
        raise HTTPException(
            status_code=503,
            detail=("Inferencia en vivo no disponible en este despliegue (faltan artefactos o la "
                    f"tabla de features). Usa los endpoints del snapshot. Detalle: {exc}"),
        ) from exc
