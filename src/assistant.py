"""Asistente conversacional del proyecto (requerimiento del profesor).

Adapta la técnica de **function calling** de los notebooks de ejemplo del profesor (Finova) al
dominio de Nexus Sentinel. En vez de traer transcripciones financieras con una tool, aquí las
tools consultan el snapshot del modelo — así el asistente responde con los datos REALES que produjo
el pipeline (no inventa) y además guía al usuario sobre cómo usar la consola y qué significan los
conceptos (riesgo, semáforo, SHAP, movimiento lateral).

Proveedor: **DeepSeek** (API gratuita, compatible con el SDK de OpenAI). Solo cambian `base_url` y
el nombre del modelo respecto al ejemplo del profesor; el patrón `chat(message, history)` +
`handle_tool_calls` es el mismo.

Seguridad: la API key vive SOLO en el backend (variable de entorno DEEPSEEK_API_KEY). Nunca se
expone al frontend. Si la key no está configurada, el orquestador lo indica y el endpoint degrada
con un 503 explícito (mismo criterio que /inference/score).
"""

from __future__ import annotations

import json
import os
from typing import Any

DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
MAX_TOOL_ROUNDS = 4  # cota de seguridad del loop de tool-calling

SYSTEM_PROMPT = """\
Eres el asistente de Nexus Sentinel, una consola de ciberseguridad que detecta el USO INDEBIDO DE
CREDENCIALES (cuentas comprometidas o abuso interno) analizando el comportamiento de autenticación
de los usuarios de una red. Tu público es el analista de un SOC y usuarios que exploran la demo.

TIENES DOS FUNCIONES:
1) GUÍA: explicar con claridad qué hace la aplicación y sus conceptos —puntuación de riesgo (0-100),
   los niveles del semáforo (verde=registro pasivo, naranja=ticket a revisar, rojo=prioritario),
   qué es una explicación SHAP, qué es el movimiento lateral, qué significan las features
   (destinos nuevos, ratio NTLM, desviación vs. su base y vs. sus pares)— y cómo navegar las tres
   vistas (Triage, Investigación, Ejecutivo).
2) CONSULTA DE DATOS: responder preguntas concretas sobre el periodo analizado LLAMANDO A LAS
   HERRAMIENTAS disponibles. Nunca inventes cifras: si la pregunta requiere un dato (cuántas
   alertas, quién tiene más riesgo, por qué se marcó a un usuario), llama a la herramienta adecuada
   y responde con lo que devuelva.

REGLAS:
- Responde en español, de forma breve y concreta. Usa los términos del dominio con naturalidad.
- Cuando cites datos, deja claro que provienen del periodo analizado (días 20-29 de la demo).
- Recuerda el principio del sistema: ninguna acción sobre cuentas es automática; el sistema prioriza
  y explica, la decisión final es de una persona (human-in-the-loop). Si te piden bloquear, aislar o
  castigar a un usuario, aclara que eso lo decide y ejecuta el analista, no tú.
- No des consejos de seguridad ofensiva ni ayudes a evadir la detección. Si te preguntan algo fuera
  del alcance de la consola (temas ajenos al proyecto), recondúcelo amablemente a tu propósito.
- Los identificadores de usuario son anónimos (formato U-####); no hay datos personales reales.
"""

# --- Definición de herramientas (esquema de function calling, formato OpenAI/DeepSeek) ----------

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "obtener_resumen",
            "description": "KPIs generales del periodo: alertas activas, casos rojos, riesgo "
                           "organizacional, usuarios monitoreados, cuentas comprometidas y "
                           "eficiencia del SOC (alertas/día, % de falsos positivos).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_cola_triage",
            "description": "Lista los usuarios de mayor riesgo (cola de triage), ordenados de "
                           "más a menos riesgo. Úsala para 'quién tiene más riesgo', 'cuántos "
                           "casos rojos', 'top usuarios'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nivel": {"type": "string", "enum": ["verde", "naranja", "rojo"],
                              "description": "Filtra por nivel del semáforo (opcional)."},
                    "limite": {"type": "integer", "description": "Cuántos usuarios devolver (máx 20).",
                               "default": 5},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explicar_usuario",
            "description": "Explica POR QUÉ el modelo asignó riesgo a un usuario en su día de mayor "
                           "riesgo (o en un día concreto): puntuación, nivel y las principales "
                           "contribuciones SHAP con el valor del día vs. su promedio personal y el "
                           "de sus pares.",
            "parameters": {
                "type": "object",
                "properties": {
                    "usuario": {"type": "string", "description": "ID anonimizado, ej. 'U-0737'."},
                    "dia": {"type": "integer", "description": "Día concreto (opcional; por defecto "
                                                              "el de mayor riesgo)."},
                },
                "required": ["usuario"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "actividad_usuario",
            "description": "Resumen de la actividad de autenticación de un usuario en un día: "
                           "número de eventos, computadoras destino, destinos y orígenes nuevos, "
                           "fallos, ratio NTLM y eventos fuera de horario.",
            "parameters": {
                "type": "object",
                "properties": {
                    "usuario": {"type": "string", "description": "ID anonimizado, ej. 'U-0737'."},
                    "dia": {"type": "integer", "description": "Día concreto (opcional)."},
                },
                "required": ["usuario"],
            },
        },
    },
]


# --- Implementación de las herramientas (leen el snapshot; sin red, sin claves) -----------------

def _dia_pico(detalle: dict) -> str | None:
    dias = detalle.get("days", {})
    if not dias:
        return None
    return max(dias, key=lambda d: dias[d]["risk"])


def _resolver_dia(detalle: dict, dia: int | None) -> str | None:
    return str(dia) if dia is not None else _dia_pico(detalle)


def obtener_resumen(snapshot: dict) -> dict:
    ov = snapshot["overview"]
    return {
        "alertas_activas": ov["alertas_activas"], "casos_rojos": ov["casos_rojos"],
        "usuarios_monitoreados": ov["usuarios_monitoreados"],
        "riesgo_organizacional": ov["riesgo_organizacional"],
        "cuentas_comprometidas_periodo": ov["cuentas_comprometidas_periodo"],
        "kpis_soc": ov.get("kpis_soc"),
        "periodo_dias": snapshot["meta"]["periodo_dias"],
    }


def listar_cola_triage(snapshot: dict, nivel: str | None = None, limite: int = 5) -> dict:
    items = snapshot["employees"]
    if nivel:
        items = [e for e in items if e["level"] == nivel]
    limite = max(1, min(int(limite), 20))
    top = [{"id": e["id"], "riesgo": e["risk_max"], "nivel": e["level"], "motivo": e["motivo"],
            "dias_en_alerta": e["n_dias_alerta"]} for e in items[:limite]]
    return {"total_en_filtro": len(items), "usuarios": top}


def explicar_usuario(snapshot: dict, usuario: str, dia: int | None = None) -> dict:
    detalle = snapshot["detail"].get(usuario)
    if detalle is None:
        return {"error": f"{usuario} no tuvo días con alerta en el periodo (o no existe)."}
    clave = _resolver_dia(detalle, dia)
    info = detalle["days"].get(clave) if clave else None
    if not info or "shap_top" not in info:
        return {"error": f"Sin explicación para {usuario} en ese día (posible día verde)."}
    return {
        "usuario": usuario, "dia": int(clave), "riesgo": info["risk"], "nivel": info["level"],
        "motivo": info["motivo"],
        "principales_factores": [
            {"factor": s["label"], "empuje": s["contribucion"], "valor_hoy": s["valor"],
             "su_promedio": s.get("promedio_personal"), "promedio_pares": s.get("promedio_peer")}
            for s in info["shap_top"]
        ],
    }


def actividad_usuario(snapshot: dict, usuario: str, dia: int | None = None) -> dict:
    detalle = snapshot["detail"].get(usuario)
    if detalle is None:
        return {"error": f"{usuario} no tuvo días con alerta en el periodo (o no existe)."}
    clave = _resolver_dia(detalle, dia)
    info = detalle["days"].get(clave) if clave else None
    if not info or "activity" not in info:
        return {"error": f"Sin detalle de actividad para {usuario} en ese día."}
    return {"usuario": usuario, "dia": int(clave), **info["activity"]}


_TOOL_IMPL = {
    "obtener_resumen": obtener_resumen,
    "listar_cola_triage": listar_cola_triage,
    "explicar_usuario": explicar_usuario,
    "actividad_usuario": actividad_usuario,
}


def handle_tool_calls(tool_calls, snapshot: dict) -> tuple[list[dict], list[str]]:
    """Ejecuta las tools que pidió el modelo y devuelve (mensajes_tool, nombres_usados).

    Estructura idéntica a la del profesor, adaptada: la tool recibe el snapshot y sus argumentos.
    """
    mensajes, usados = [], []
    for tc in tool_calls:
        nombre = tc.function.name
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        impl = _TOOL_IMPL.get(nombre)
        resultado = impl(snapshot, **args) if impl else {"error": f"herramienta '{nombre}' desconocida"}
        usados.append(nombre)
        mensajes.append({"role": "tool", "tool_call_id": tc.id,
                         "content": json.dumps(resultado, ensure_ascii=False)})
    return mensajes, usados


# --- Orquestador principal ----------------------------------------------------------------------

def assistant_available() -> bool:
    return bool(os.getenv("DEEPSEEK_API_KEY"))


def chat(messages: list[dict], snapshot: dict, api_key: str | None = None) -> dict:
    """Conversa con el usuario. `messages` es el historial [{role, content}, ...] SIN el system.

    Devuelve {"reply": str, "tools_used": [str]}. El loop llama a DeepSeek, ejecuta las tools que
    pida y vuelve a llamar hasta que el modelo produce una respuesta final (o se alcanza la cota).
    """
    api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta DEEPSEEK_API_KEY. Obtén una key gratuita en https://platform.deepseek.com "
            "y expórtala como variable de entorno del backend.")

    from openai import OpenAI  # import perezoso: el backend arranca sin la dependencia si no se usa

    client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
    conversacion: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}, *messages]
    tools_usadas: list[str] = []

    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL, messages=conversacion, tools=TOOLS, temperature=0.2)
        msg = resp.choices[0].message
        if resp.choices[0].finish_reason == "tool_calls" and msg.tool_calls:
            resultados, usados = handle_tool_calls(msg.tool_calls, snapshot)
            tools_usadas.extend(usados)
            conversacion.append(msg.model_dump())
            conversacion.extend(resultados)
        else:
            return {"reply": msg.content or "", "tools_used": tools_usadas}

    # si se agotan las rondas, se fuerza una respuesta final sin más tools
    resp = client.chat.completions.create(model=DEEPSEEK_MODEL, messages=conversacion, temperature=0.2)
    return {"reply": resp.choices[0].message.content or "", "tools_used": tools_usadas}
