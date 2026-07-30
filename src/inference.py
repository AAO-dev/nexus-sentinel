"""Flujo de inferencia, explicación SHAP local y construcción del snapshot de demo.

Flujo:
  eventos de auth del día → misma tubería de features (grafo congelado a D-1)
  → prob supervisada + anomaly_score → puntuación 0-100 → nivel verde/naranja/rojo
  → top-5 SHAP → JSON para la API

Decisiones heredadas del modelado, y por qué no se usan valores por defecto:
- Puntuación de riesgo: riesgo = 100·(w·prob_calibrada + (1-w)·anomaly_norm). El diseño inicial
  proponía un w fijo de 0.7; aquí se ELIGE en validación por PR-AUC (select_blend_weight), y el
  resultado quedó cerca de 1.0 porque el supervisado domina. El componente de anomalía aporta
  robustez marginal, pero se conserva por el diseño híbrido del sistema.
- Componente de anomalía: Isolation Forest normalizado con referencia AJUSTADA EN TRAIN
  (min/max de los scores de train), para no filtrar la distribución de test.
- Agregación por usuario (K días): K=1 — agregar no generaliza (verificado en validación). El
  ranking usa el riesgo del día; la línea de tiempo muestra la serie completa para el analista.
- Umbrales verde/naranja/rojo: recomputados en el espacio 0-100 sobre la validación por capacidad
  operativa del SOC (percentiles ~N tickets/día).

El snapshot de demo precomputa TODO el periodo de prueba en un JSON que la API sirve tal
cual — estable en vivo — y el mismo módulo puntúa un usuario-día individual (inferencia real).
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.features import feature_columns
from src.models import SOC_ROJOS_DIA, SOC_TICKETS_DIA, three_way_split

LEVELS = ("verde", "naranja", "rojo")

# Etiquetas legibles para la explicación SHAP y el "motivo" de la cola de triage.
FEATURE_LABELS = {
    "ratio_ntlm": "Ratio NTLM", "n_ntlm": "Autenticaciones NTLM", "z_n_ntlm": "NTLM vs. su base",
    "n_src_computers_nuevas": "Máquinas origen nuevas", "n_aristas_nuevas": "Destinos nuevos",
    "ratio_aristas_nuevas": "Fracción de destinos nuevos", "rareza_media_destinos": "Destinos poco comunes",
    "n_dst_computers": "Computadoras destino", "z_n_dst_computers": "Alcance vs. su base",
    "ratio_max_n_dst_computers": "Alcance vs. su máximo", "z_peer_n_dst_computers": "Alcance vs. sus pares",
    "z_peer_n_eventos": "Volumen vs. sus pares", "z_n_eventos": "Volumen vs. su base",
    "n_uso_como_identidad_destino": "Uso como identidad destino", "n_fallos_consecutivos_max": "Ráfaga de fallos",
    "z_peer_ratio_fallos": "Fallos vs. sus pares", "ratio_fallos": "Ratio de fallos",
    "n_fuera_horario": "Eventos fuera de horario", "ratio_tgs_por_tgt": "Anomalía de tickets Kerberos",
    "ratio_auth_type_nulo": "Tipo de auth desconocido", "z_amplitud_horaria": "Amplitud horaria vs. su base",
    "n_src_computers": "Máquinas origen", "z_n_src_computers": "Máquinas origen vs. su base",
    "n_logoffs": "Cierres de sesión", "es_dia_no_laboral": "Día no laboral",
}


def display_id(src_user: str) -> str:
    """U66@DOM1 -> 'U-0066' (identificador anonimizado para la interfaz)."""
    local = src_user.split("@", 1)[0]
    num = "".join(ch for ch in local if ch.isdigit())
    return f"U-{int(num):04d}" if num else local


def human_label(feature: str) -> str:
    return FEATURE_LABELS.get(feature, feature.replace("_", " "))


# ---------------------------------------------------------------------------
# Carga de artefactos y scoring de bajo nivel
# ---------------------------------------------------------------------------

def load_artifacts(models_dir: str | Path = "models") -> dict:
    """Carga los artefactos del modelado (+ KMeans de pares y bundle de inferencia si existe)."""
    models_dir = Path(models_dir)
    art = joblib.load(models_dir / "fase4_artefactos.joblib")
    art["peer_kmeans"] = joblib.load(models_dir / "peer_kmeans.joblib")
    infer_path = models_dir / "inference_bundle.joblib"
    if infer_path.exists():
        art.update(joblib.load(infer_path))
    return art


def supervised_prob(art: dict, X: pd.DataFrame) -> np.ndarray:
    """Probabilidad calibrada de compromiso."""
    raw = art["modelo"].predict_proba(X[art["features"]].astype(float))[:, 1]
    if art["metodo_calibracion"] == "isotonic":
        return art["calibrador"].predict(raw)
    return art["calibrador"].predict_proba(raw.reshape(-1, 1))[:, 1]


def anomaly_raw(art: dict, X: pd.DataFrame) -> np.ndarray:
    """Score de anomalía del Isolation Forest (mayor = más anómalo)."""
    return -art["isolation_forest"].score_samples(X[art["features_if"]].astype(float))


def anomaly_norm(scores: np.ndarray, ref_min: float, ref_max: float) -> np.ndarray:
    """Normaliza el score de anomalía a [0,1] con referencia (min/max) ajustada en train."""
    return np.clip((scores - ref_min) / (ref_max - ref_min + 1e-9), 0.0, 1.0)


def risk_0_100(prob: np.ndarray, anomaly01: np.ndarray, w: float) -> np.ndarray:
    """Puntuación de riesgo 0-100, con el peso w elegido en validación."""
    return 100.0 * (w * prob + (1.0 - w) * anomaly01)


def assign_level(risk: np.ndarray | float, thr_naranja: float, thr_rojo: float):
    """verde < naranja <= naranja < rojo <= rojo (umbrales por capacidad del SOC)."""
    risk = np.asarray(risk)
    lvl = np.where(risk >= thr_rojo, "rojo", np.where(risk >= thr_naranja, "naranja", "verde"))
    return lvl if lvl.ndim else str(lvl)


def local_shap_top(art: dict, X_row: pd.DataFrame, k: int = 5) -> list[dict]:
    """Top-k contribuciones SHAP del usuario-día (explicación local)."""
    sv = art["explainer_shap"].shap_values(X_row[art["features"]].astype(float))
    sv = np.asarray(sv).reshape(-1)
    orden = np.argsort(np.abs(sv))[::-1][:k]
    return [{"feature": art["features"][i], "label": human_label(art["features"][i]),
             "contribucion": round(float(sv[i]), 3),
             "valor": round(float(X_row.iloc[0][art["features"][i]]), 3)} for i in orden]


def enrich_shap_comparisons(shap_top: list[dict], row: pd.Series, hist_usuario: pd.DataFrame,
                            peer_means: pd.DataFrame) -> list[dict]:
    """Añade a cada contribución SHAP el valor del día vs. su promedio personal y vs. su peer group.

    Es el contrato del endpoint `/employees/{id}/explanation`: el analista no
    necesita el número SHAP crudo, necesita "tocó 49 destinos; tú promedias 12, tu grupo 8".
    El promedio personal usa SOLO días previos al evaluado (coherente con la regla anti-fuga).
    """
    dia = int(row["day"])
    previos = hist_usuario[hist_usuario["day"] < dia]
    for s in shap_top:
        f = s["feature"]
        s["promedio_personal"] = (round(float(previos[f].mean()), 3)
                                  if len(previos) and f in previos else None)
        try:
            s["promedio_peer"] = round(float(peer_means.loc[(int(row["peer_cluster"]), dia), f]), 3)
        except (KeyError, TypeError):
            s["promedio_peer"] = None
    return shap_top


def build_ego_graphs(auth_path: str | Path, pares_alerta: list[tuple[str, int]],
                     max_historicos: int = 40) -> dict[tuple[str, int], dict]:
    """Nodos del grafo ego usuario→computadora para los días con alerta (vista de investigación).

    El mini-grafo es el elemento visual diferenciador del proyecto: muestra en gris los destinos
    que el usuario ya conocía y en rojo los que tocó por primera vez ese día. El snapshot guardaba
    solo el CONTEO de destinos nuevos; sin la lista de nodos la UI no puede dibujarlo.

    Coherente con la regla anti-fuga del grafo: "histórico" = tocado en días ANTERIORES.
    Los destinos históricos se recortan a `max_historicos` (el grafo debe ser legible, y la
    historia visual está en los nuevos); se reporta el total real aparte.
    """
    import polars as pl

    usuarios = sorted({u for u, _ in pares_alerta})
    ev = (
        pl.scan_parquet(auth_path)
        .filter(pl.col("src_user").is_in(usuarios))
        .select("src_user", "day", "dst_computer")
        .unique()
        .collect()
        .to_pandas()
    )

    salida: dict[tuple[str, int], dict] = {}
    for user, g_user in ev.groupby("src_user"):
        dias_user = sorted({d for u, d in pares_alerta if u == user})
        for dia in dias_user:
            previos = set(g_user.loc[g_user.day < dia, "dst_computer"])
            hoy = set(g_user.loc[g_user.day == dia, "dst_computer"])
            nuevos = sorted(hoy - previos)
            conocidos = sorted(hoy & previos)
            salida[(user, dia)] = {
                "nodos_nuevos": nuevos,
                "nodos_conocidos": conocidos[:max_historicos],
                "n_nuevos": len(nuevos),
                "n_conocidos": len(conocidos),
                "n_historicos_totales": len(previos),
                "conocidos_truncados": len(conocidos) > max_historicos,
            }
    return salida


def motivo_una_linea(shap_top: list[dict], row: pd.Series) -> str:
    """Motivo en una línea para la cola de triage (ej. '18 destinos nuevos en un día')."""
    top = shap_top[0]
    f = top["feature"]
    if f in ("n_aristas_nuevas", "n_src_computers_nuevas", "n_dst_computers", "n_fuera_horario"):
        return f"{int(row[f])} {human_label(f).lower()} en un día"
    if f == "ratio_ntlm":
        return f"NTLM al {row[f]*100:.0f}% de sus autenticaciones"
    if f == "n_uso_como_identidad_destino":
        return f"usada como destino {int(row[f])} veces (cadenas de salto)"
    if f.startswith("z_"):
        return f"{human_label(f)}: {row[f]:+.1f}σ sobre lo normal"
    return f"{human_label(f)}: señal dominante"


# ---------------------------------------------------------------------------
# Inferencia sobre un usuario-día (endpoint de inferencia real de la demo)
# ---------------------------------------------------------------------------

def score_user_day(art: dict, row: pd.Series) -> dict:
    """Puntúa una fila de features usuario-día y devuelve el JSON que consume la API."""
    X = row.to_frame().T
    prob = float(supervised_prob(art, X)[0])
    anom = float(anomaly_norm(anomaly_raw(art, X), art["if_ref_min"], art["if_ref_max"])[0])
    risk = float(risk_0_100(np.array([prob]), np.array([anom]), art["w_blend"])[0])
    shap_top = local_shap_top(art, X)
    return {
        "id": display_id(row["src_user"]), "src_user": row["src_user"], "day": int(row["day"]),
        "risk_score": round(risk, 1), "level": assign_level(risk, *art["umbrales_riesgo"].values()),
        "prob": round(prob, 4), "anomaly": round(anom, 4),
        "top_shap": shap_top, "motivo": motivo_una_linea(shap_top, row),
    }


# ---------------------------------------------------------------------------
# Construcción del snapshot de demo (lo que sirve la API)
# ---------------------------------------------------------------------------

def select_blend_weight(prob_val: np.ndarray, anom_val: np.ndarray, y_val: np.ndarray) -> tuple[float, dict]:
    """Elige w por PR-AUC en validación (nunca en test). Devuelve (w, barrido)."""
    from sklearn.metrics import average_precision_score

    barrido = {round(w, 2): float(average_precision_score(y_val, w * prob_val + (1 - w) * anom_val))
               for w in np.arange(0.0, 1.01, 0.05)}
    return max(barrido, key=barrido.get), barrido


def soc_thresholds_riesgo(risk_val: np.ndarray, days_val: np.ndarray) -> dict:
    """Umbrales naranja/rojo en el espacio 0-100 por capacidad del SOC (percentiles)."""
    n_dias = len(np.unique(days_val))
    out = {}
    for nombre, cap in (("naranja", SOC_TICKETS_DIA), ("rojo", SOC_ROJOS_DIA)):
        k = cap * n_dias
        out[nombre] = float(np.sort(risk_val)[-k]) if k < len(risk_val) else 0.0
    return out


def build_demo_snapshot(work_dir: str | Path = "data/work", models_dir: str | Path = "models",
                        out_path: str | Path = "docs/demo/snapshot.json") -> dict:
    """Precomputa el periodo de prueba y arma el JSON que consumen los endpoints de la API.

    Además calibra y persiste en inference_bundle.joblib los parámetros de scoring (w, referencia
    de anomalía, umbrales 0-100) para que score_user_day funcione en vivo.
    """
    work_dir, models_dir, out_path = Path(work_dir), Path(models_dir), Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    art = load_artifacts(models_dir)
    ud = three_way_split(pd.read_parquet(work_dir / "user_day_features.parquet"))
    redteam = pd.read_parquet(work_dir / "redteam.parquet")

    # scores base sobre toda la tabla
    prob = supervised_prob(art, ud)
    anom_raw_all = anomaly_raw(art, ud)
    tr = (ud.conjunto == "train").to_numpy()
    ref_min, ref_max = float(anom_raw_all[tr].min()), float(anom_raw_all[tr].max())
    anom = anomaly_norm(anom_raw_all, ref_min, ref_max)

    va = (ud.conjunto == "val").to_numpy()
    w, barrido = select_blend_weight(prob[va], anom[va], ud.loc[va, "y"].to_numpy())
    ud["prob"], ud["anomaly"] = prob, anom
    ud["risk"] = risk_0_100(prob, anom, w)
    umbrales = soc_thresholds_riesgo(ud.loc[va, "risk"].to_numpy(), ud.loc[va, "day"].to_numpy())
    ud["level"] = assign_level(ud["risk"].to_numpy(), umbrales["naranja"], umbrales["rojo"])

    # persistir parámetros de scoring para inferencia en vivo
    art_infer = {"w_blend": w, "if_ref_min": ref_min, "if_ref_max": ref_max,
                 "umbrales_riesgo": umbrales}
    joblib.dump(art_infer, models_dir / "inference_bundle.joblib")
    art.update(art_infer)

    # ---- snapshot del periodo de prueba ----
    test = ud[ud.conjunto == "test"].copy()
    dias = sorted(test["day"].unique().tolist())
    # medias por (cluster, día) para la comparativa "vs. sus pares" del endpoint /explanation
    peer_means = ud.groupby(["peer_cluster", "day"])[art["features"]].mean()
    # nodos del grafo ego para los días con alerta (vista 2 de la UI)
    pares_alerta = [(r.src_user, int(r.day)) for r in
                    test[test.level != "verde"].itertuples()]
    egos = build_ego_graphs(work_dir / "auth_sample.parquet", pares_alerta)

    detail, employees = {}, []
    for user, g in test.groupby("src_user"):
        did = display_id(user)
        g = g.sort_values("day")
        tiene_alerta = bool((g["level"] != "verde").any())
        dias_user = {}
        for _, row in g.iterrows():
            dia = {
                "risk": round(float(row["risk"]), 1), "level": row["level"],
                "prob": round(float(row["prob"]), 4), "anomaly": round(float(row["anomaly"]), 4),
                "es_ataque_real": int(row["y"]),
            }
            # SHAP y detalle de actividad solo para días con alerta: los verdes son registro
            # pasivo y no se investigan; esto mantiene el snapshot ligero.
            if row["level"] != "verde":
                shap_top = enrich_shap_comparisons(
                    local_shap_top(art, row.to_frame().T), row,
                    ud[ud.src_user == user], peer_means)
                dia["shap_top"] = shap_top
                dia["motivo"] = motivo_una_linea(shap_top, row)
                dia["activity"] = {
                    "n_eventos": int(row["n_eventos"]), "n_dst": int(row["n_dst_computers"]),
                    "n_destinos_nuevos": int(row["n_aristas_nuevas"]),
                    "n_origenes_nuevos": int(row["n_src_computers_nuevas"]),
                    "n_fallos": int(row["n_fallos"]), "ratio_ntlm": round(float(row["ratio_ntlm"]), 4),
                    "n_fuera_horario": int(row["n_fuera_horario"]),
                }
                dia["ego_graph"] = egos.get((user, int(row["day"])))
            dias_user[str(int(row["day"]))] = dia
        peor = g.loc[g["risk"].idxmax()]
        # detalle completo solo para empleados con al menos un día de alerta (los investigables)
        if tiene_alerta:
            detail[did] = {
                "id": did, "peer_cluster": int(g["peer_cluster"].iloc[0]),
                "timeline": [{"day": int(r.day), "risk": round(float(r.risk), 1), "level": r.level}
                             for r in g.itertuples()],
                "days": dias_user,
            }
        employees.append({
            "id": did, "risk_max": round(float(g["risk"].max()), 1),
            "level": assign_level(g["risk"].max(), umbrales["naranja"], umbrales["rojo"]),
            "dia_pico": int(peor["day"]), "n_dias_alerta": int((g["level"] != "verde").sum()),
            "motivo": motivo_una_linea(local_shap_top(art, peor.to_frame().T), peor),
            "es_comprometida": int(g["y"].max()),
        })
    employees.sort(key=lambda e: e["risk_max"], reverse=True)

    # ---- overview (KPIs) y tendencia ----
    por_dia = test.groupby("day").agg(alertas=("level", lambda s: int((s != "verde").sum())),
                                      riesgo_medio=("risk", "mean")).reset_index()
    # tendencia por cluster conductual (vista 3: ¿qué rol concentra el riesgo?)
    por_cluster = (test.groupby(["peer_cluster", "day"])
                   .agg(riesgo_medio=("risk", "mean"),
                        alertas=("level", lambda s: int((s != "verde").sum())),
                        usuarios=("src_user", "nunique")).reset_index())
    # KPIs operativos del SOC (vista 3). Solo se reporta lo medible con estos datos:
    # el tiempo de resolución exige uso real de analistas y NO se inventa.
    alertas = test[test.level != "verde"]
    n_dias = len(dias)
    kpis_soc = {
        "alertas_por_dia": round(len(alertas) / n_dias, 1),
        "casos_rojos_por_dia": round(int((test.level == "rojo").sum()) / n_dias, 1),
        "pct_falsos_positivos": round(float((alertas.y == 0).mean() * 100), 1) if len(alertas) else 0.0,
        "cuentas_comprometidas_detectadas": int(alertas.loc[alertas.y == 1, "src_user"].nunique()),
        "cuentas_comprometidas_totales": int(test.loc[test.y == 1, "src_user"].nunique()),
        "carga_revisable": f"{round(len(alertas) / n_dias)} tickets/día vs. capacidad objetivo de 20",
        "tiempo_resolucion_medio": None,  # requiere telemetría real de analistas (no se fabrica)
    }
    overview = {
        "alertas_activas": int((test["level"] != "verde").sum()),
        "casos_rojos": int((test["level"] == "rojo").sum()),
        "usuarios_monitoreados": int(test["src_user"].nunique()),
        "riesgo_organizacional": round(float(test["risk"].mean()), 2),
        "tendencia": [{"day": int(r.day), "alertas": int(r.alertas),
                       "riesgo_medio": round(float(r.riesgo_medio), 2)} for r in por_dia.itertuples()],
        "cuentas_comprometidas_periodo": int(test.loc[test.y == 1, "src_user"].nunique()),
        "tendencia_por_cluster": [
            {"peer_cluster": int(r.peer_cluster), "day": int(r.day),
             "riesgo_medio": round(float(r.riesgo_medio), 2), "alertas": int(r.alertas),
             "usuarios": int(r.usuarios)} for r in por_cluster.itertuples()],
        "kpis_soc": kpis_soc,
    }

    snapshot = {
        "meta": {"periodo_dias": [dias[0], dias[-1]], "n_user_days": int(len(test)),
                 "modelo": art["tipo"], "w_blend": w, "umbrales_riesgo": umbrales,
                 "seleccion_w_val": barrido},
        "overview": overview, "employees": employees, "detail": detail,
    }
    out_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"snapshot_path": str(out_path), "w_blend": w, "umbrales_riesgo": umbrales,
            "n_employees": len(employees), "n_user_days": int(len(test)),
            "alertas_activas": overview["alertas_activas"],
            "cuentas_comprometidas": overview["cuentas_comprometidas_periodo"]}


if __name__ == "__main__":
    info = build_demo_snapshot()
    print(json.dumps(info, indent=2, ensure_ascii=False))
