"""Pruebas de contrato de la API.

Definición de "listo" del backend: estos tests en verde contra el snapshot
de demo. Verifican el CONTRATO que el frontend React consumirá — códigos de estado, forma de la
respuesta e invariantes de negocio — no la calidad del modelo, que se evalúa en el notebook.

Ejecutar:  pytest api/tests -q
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import SNAPSHOT, app

client = TestClient(app)

NIVELES = {"verde", "naranja", "rojo"}


@pytest.fixture(scope="module")
def empleado_con_alerta() -> dict:
    """Un empleado que sí tiene detalle investigable y al menos un día no verde."""
    return SNAPSHOT["employees"][0]


@pytest.fixture(scope="module")
def dia_de_alerta(empleado_con_alerta) -> tuple[str, int]:
    detail = SNAPSHOT["detail"][empleado_con_alerta["id"]]
    dia = next(int(d) for d, v in detail["days"].items() if v["level"] != "verde")
    return empleado_con_alerta["id"], dia


# --------------------------------------------------------------------------- sistema

def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["snapshot_cargado"] is True
    assert len(body["periodo_dias"]) == 2 and body["usuarios"] > 0


def test_openapi_documenta_los_endpoints():
    """El contrato debe publicarse: de aquí se generan los tipos TS del frontend."""
    rutas = client.get("/openapi.json").json()["paths"]
    for esperado in ("/health", "/overview", "/employees", "/employees/{employee_id}/risk",
                     "/employees/{employee_id}/explanation", "/employees/{employee_id}/activity",
                     "/cases/{case_id}/feedback", "/inference/score"):
        assert esperado in rutas, f"falta {esperado} en el OpenAPI"


# --------------------------------------------------------------------------- triage

def test_overview_kpis_coherentes():
    b = client.get("/overview").json()
    assert b["alertas_activas"] >= b["casos_rojos"] >= 0
    assert 0 <= b["riesgo_organizacional"] <= 100
    assert len(b["tendencia"]) > 0
    assert all(p["alertas"] >= 0 for p in b["tendencia"])


def test_employees_ordenada_por_riesgo_desc():
    items = client.get("/employees", params={"limit": 30}).json()
    assert len(items) <= 30 and len(items) > 0
    riesgos = [e["risk_max"] for e in items]
    assert riesgos == sorted(riesgos, reverse=True), "la cola debe venir priorizada"
    assert all(e["id"].startswith("U-") for e in items), "los IDs deben venir anonimizados"
    assert all(e["motivo"] for e in items), "ninguna entrada sin motivo legible"


def test_employees_filtra_por_nivel():
    rojos = client.get("/employees", params={"level": "rojo", "limit": 100}).json()
    assert all(e["level"] == "rojo" for e in rojos)


def test_employees_rechaza_parametros_invalidos():
    assert client.get("/employees", params={"level": "morado"}).status_code == 422
    assert client.get("/employees", params={"limit": 0}).status_code == 422
    assert client.get("/employees", params={"sort": "aleatorio"}).status_code == 422


# --------------------------------------------------------------------------- empleado

def test_risk_devuelve_serie_temporal(empleado_con_alerta):
    b = client.get(f"/employees/{empleado_con_alerta['id']}/risk").json()
    assert b["id"] == empleado_con_alerta["id"] and len(b["timeline"]) > 0
    dias = [p["day"] for p in b["timeline"]]
    assert dias == sorted(dias), "la línea de tiempo debe venir cronológica"
    assert all(p["level"] in NIVELES and 0 <= p["risk"] <= 100 for p in b["timeline"])


def test_risk_respeta_el_limite_de_dias(empleado_con_alerta):
    b = client.get(f"/employees/{empleado_con_alerta['id']}/risk", params={"days": 3}).json()
    assert len(b["timeline"]) <= 3


def test_explanation_trae_shap_con_comparativas(dia_de_alerta):
    eid, dia = dia_de_alerta
    b = client.get(f"/employees/{eid}/explanation", params={"date": dia}).json()
    assert b["level"] in {"naranja", "rojo"} and b["motivo"]
    assert 1 <= len(b["top_shap"]) <= 5
    # el contrato exige: valor del día + comparación personal y de pares
    for s in b["top_shap"]:
        assert {"feature", "label", "contribucion", "valor"} <= set(s)
        assert "promedio_personal" in s and "promedio_peer" in s
    # invariante del sistema: la puntuación nunca viaja sin explicación
    assert b["risk"] > 0 and len(b["top_shap"]) > 0


def test_activity_resume_autenticaciones(dia_de_alerta):
    eid, dia = dia_de_alerta
    b = client.get(f"/employees/{eid}/activity", params={"date": dia}).json()
    for campo in ("n_eventos", "n_dst", "n_destinos_nuevos", "n_origenes_nuevos",
                  "n_fallos", "ratio_ntlm", "n_fuera_horario"):
        assert campo in b
    assert b["n_eventos"] > 0 and 0 <= b["ratio_ntlm"] <= 1
    assert b["n_destinos_nuevos"] <= b["n_dst"], "los destinos nuevos son subconjunto del día"


def test_empleado_inexistente_da_404():
    assert client.get("/employees/U-9999999/risk").status_code == 404
    assert client.get("/employees/U-9999999/explanation", params={"date": 20}).status_code == 404


def test_dia_inexistente_da_404(empleado_con_alerta):
    r = client.get(f"/employees/{empleado_con_alerta['id']}/activity", params={"date": 999})
    assert r.status_code == 404


# --------------------------------------------------------------------------- feedback

def test_feedback_registra_decision(tmp_path, monkeypatch):
    destino = tmp_path / "feedback.jsonl"
    monkeypatch.setattr("api.main.FEEDBACK_PATH", destino)
    r = client.post("/cases/U-0737-d20/feedback",
                    json={"decision": "falso_positivo", "analista": "ana", "dia": 20,
                          "nota": "cuenta de servicio conocida"})
    assert r.status_code == 201 and r.json()["registrado"] is True
    guardado = json.loads(destino.read_text(encoding="utf-8").strip())
    assert guardado["decision"] == "falso_positivo" and guardado["case_id"] == "U-0737-d20"
    assert guardado["timestamp"]


def test_feedback_rechaza_decision_invalida():
    r = client.post("/cases/X/feedback", json={"decision": "borrar_cuenta"})
    assert r.status_code == 422, "solo se aceptan las 3 decisiones del ciclo human-in-the-loop"


def test_historial_de_feedback_es_consultable(tmp_path, monkeypatch):
    """Trazabilidad para auditoría: lo que se registra debe poder leerse después."""
    destino = tmp_path / "feedback.jsonl"
    monkeypatch.setattr("api.main.FEEDBACK_PATH", destino)
    caso = "U-0001-d21"
    client.post(f"/cases/{caso}/feedback", json={"decision": "investigar", "analista": "luis"})
    client.post(f"/cases/{caso}/feedback", json={"decision": "escalar", "analista": "ana"})
    client.post("/cases/otro-caso/feedback", json={"decision": "falso_positivo"})

    historial = client.get(f"/cases/{caso}/feedback").json()
    assert len(historial) == 2, "debe devolver solo las decisiones de ESE caso"
    assert [h["decision"] for h in historial] == ["investigar", "escalar"]
    assert all(h["timestamp"] for h in historial)


def test_historial_vacio_no_falla(tmp_path, monkeypatch):
    monkeypatch.setattr("api.main.FEEDBACK_PATH", tmp_path / "no-existe.jsonl")
    assert client.get("/cases/sin-decisiones/feedback").json() == []


# --------------------------------------------------------------------------- datos para vistas 2 y 3

def test_activity_incluye_grafo_ego(dia_de_alerta):
    """El mini-grafo alimenta la vista de investigación: sin nodos no se puede dibujar."""
    eid, dia = dia_de_alerta
    b = client.get(f"/employees/{eid}/activity", params={"date": dia}).json()
    ego = b["ego_graph"]
    assert ego is not None, "sin nodos no se puede dibujar el grafo"
    assert isinstance(ego["nodos_nuevos"], list) and isinstance(ego["nodos_conocidos"], list)
    assert ego["n_nuevos"] == len(ego["nodos_nuevos"])
    assert ego["n_nuevos"] == b["n_destinos_nuevos"], "debe cuadrar con la feature del modelo"
    assert ego["n_historicos_totales"] >= ego["n_conocidos"]


def test_overview_trae_datos_de_la_vista_ejecutiva():
    b = client.get("/overview").json()
    assert len(b["tendencia_por_cluster"]) > 0, "el panel ejecutivo necesita la tendencia por rol"
    assert all({"peer_cluster", "day", "riesgo_medio"} <= set(p) for p in b["tendencia_por_cluster"])

    k = b["kpis_soc"]
    assert k is not None and k["alertas_por_dia"] > 0
    assert 0 <= k["pct_falsos_positivos"] <= 100
    assert k["cuentas_comprometidas_detectadas"] <= k["cuentas_comprometidas_totales"]
    assert k["tiempo_resolucion_medio"] is None, "no se estima sin telemetría real de analistas"


# --------------------------------------------------------------------------- asistente

def test_assistant_health_reporta_estado():
    b = client.get("/assistant/health").json()
    assert "disponible" in b and isinstance(b["disponible"], bool)
    assert b["modelo"]  # nombre del modelo DeepSeek configurado


def test_assistant_tools_leen_datos_reales_sin_key():
    """Las herramientas del asistente (function calling) deben devolver los datos del snapshot
    sin necesidad de la API del LLM: es la parte del requerimiento que no depende de la key."""
    from src import assistant as a

    resumen = a.obtener_resumen(SNAPSHOT)
    assert resumen["alertas_activas"] == SNAPSHOT["overview"]["alertas_activas"]

    cola = a.listar_cola_triage(SNAPSHOT, nivel="rojo", limite=3)
    assert len(cola["usuarios"]) <= 3 and all(u["nivel"] == "rojo" for u in cola["usuarios"])

    eid = SNAPSHOT["employees"][0]["id"]
    exp = a.explicar_usuario(SNAPSHOT, eid)
    assert exp["usuario"] == eid and len(exp["principales_factores"]) > 0
    assert "su_promedio" in exp["principales_factores"][0]  # comparativa presente


def test_assistant_chat_degrada_o_responde():
    """Sin key configurada devuelve 503 explícito; con key, responde 200. Nunca falla opaco."""
    r = client.post("/assistant/chat", json={"messages": [{"role": "user", "content": "¿Qué es el riesgo?"}]})
    assert r.status_code in (200, 503)
    if r.status_code == 503:
        assert "DEEPSEEK_API_KEY" in r.json()["detail"]
    else:
        assert isinstance(r.json()["reply"], str)


def test_assistant_chat_valida_el_historial():
    assert client.post("/assistant/chat", json={"messages": []}).status_code == 422
    assert client.post("/assistant/chat",
                       json={"messages": [{"role": "system", "content": "x"}]}).status_code == 422


# --------------------------------------------------------------------------- inferencia

def test_inference_en_vivo_o_degradacion_explicita(dia_de_alerta):
    """La inferencia real debe funcionar o degradar con 503 explícito, nunca fallar opaco."""
    eid, dia = dia_de_alerta
    r = client.post("/inference/score", json={"employee_id": eid, "day": dia})
    assert r.status_code in (200, 503)
    if r.status_code == 200:
        b = r.json()
        assert 0 <= b["risk_score"] <= 100 and b["level"] in NIVELES
        assert b["fuente"] == "modelo_en_vivo" and len(b["top_shap"]) > 0
        # coherencia con el snapshot: el mismo usuario-día debe dar el mismo riesgo
        esperado = SNAPSHOT["detail"][eid]["days"][str(dia)]["risk"]
        assert abs(b["risk_score"] - esperado) < 0.5
    else:
        assert "no disponible" in r.json()["detail"]
