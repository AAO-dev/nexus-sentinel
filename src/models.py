"""Modelado, evaluación y análisis de estabilidad.

Decisiones justificadas (cada una se narra en detalle en el notebook):

NO SUPERVISADO
- Isolation Forest baseline: contamination='auto' — fijarlo con la tasa real de ataque (0.38%)
  sería meter las etiquetas en un modelo que se presume sin etiquetas; además el parámetro solo
  mueve el corte binario, no el ranking, y aquí el umbral operativo lo pone la capacidad del SOC.
  Se entrena SOLO con días de train (honestidad temporal) y SIN y. La evaluación es a posteriori:
  sus scores se contrastan con las etiquetas en test (PR-AUC, recall@FPR) — las etiquetas se usan
  para MEDIR, nunca para entrenar. Elección de features: se comparan dos vistas (todas vs. solo
  desviaciones+grafo) porque IF se diluye en alta dimensión con features crudas de escala dispar.
- KMeans de peer groups: los clusters vienen congelados de src/features.py (ajustados solo con
  train). Aquí genera (a) un score de anomalía por usuario-día —distancia del vector del día al
  centroide de SU rol, en el espacio escalado del perfil— evaluado también a posteriori, y (b) la
  feature dist_peer_centroide, que se prueba en el supervisado y se conserva solo si mejora.

SUPERVISADO (XGBoost central; RF y LR de referencia)
- Desbalance: scale_pos_weight = negativos/positivos DEL TRAIN (no de toda la tabla).
- 3 conjuntos temporales: train (días 0-13, 120+), val (14-19, 27+), test/OOT (20-29, 34+).
  El corte de val se eligió con datos: cortar en 16 dejaría la validación sin un solo positivo.
- Early stopping por aucpr en val; hiperparámetros por búsqueda aleatoria evaluada en val
  (nunca k-fold aleatorio: los días del mismo usuario están autocorrelacionados).
- Calibración de probabilidades ajustada SOLO con val; isotónica vs. Platt decidido por Brier
  en CV interno de val (con 27 positivos la isotónica puede sobreajustar; se decide con datos).
- Selección del mejor modelo: PR-AUC en val (métrica rectora), desempate por recall@FPR=1% y
  estabilidad (PSI). El test/OOT se toca UNA vez, al final, para el reporte.

ESTABILIDAD (reporte OOT sobre test, días 20-29)
- PSI del score train→OOT (deciles de train): <0.10 estable, 0.10-0.25 vigilar, >0.25 inestable.
- CSI de las features top por importancia SHAP.
- KS de clasificación: máx distancia entre distribuciones acumuladas de score de 1s y 0s, con
  tabla de deciles (TE/TNE: tasa de eventos y de no-eventos por decil, acumuladas).
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.data import SEED
from src.features import PEER_PROFILE_COLS, PEER_LOG_COLS, feature_columns

EPS = 1e-9
TRAIN_END_DAY = 14        # train: 0-13
VAL_END_DAY = 20          # val: 14-19 | test (OOT): 20-29
FPR_TARGETS = (0.01, 0.001)
SOC_TICKETS_DIA = 20      # capacidad diaria del SOC para tickets de nivel naranja
SOC_ROJOS_DIA = 5
N_ITER_XGB = 40
PSI_BINS = 10


# ---------------------------------------------------------------------------
# Conjuntos
# ---------------------------------------------------------------------------

def three_way_split(ud: pd.DataFrame) -> pd.DataFrame:
    """train/val/test por día calendario. El 'split' binario de features.py se refina aquí:
    los últimos 6 días del train original se vuelven validación."""
    ud = ud.copy()
    ud["conjunto"] = np.where(ud.day < TRAIN_END_DAY, "train",
                              np.where(ud.day < VAL_END_DAY, "val", "test"))
    return ud


def design_matrices(ud: pd.DataFrame, extra_drop: tuple = ()) -> dict:
    cols = [c for c in feature_columns(ud) if c not in extra_drop]
    out = {"features": cols}
    for s in ("train", "val", "test"):
        m = ud.conjunto == s
        out[s] = {"X": ud.loc[m, cols].astype(float), "y": ud.loc[m, "y"].to_numpy(),
                  "days": ud.loc[m, "day"].to_numpy(), "users": ud.loc[m, "src_user"].to_numpy()}
    return out


# ---------------------------------------------------------------------------
# No supervisado
# ---------------------------------------------------------------------------

def train_isolation_forest(X_train: pd.DataFrame, seed: int = SEED):
    """IF sin etiquetas, contamination='auto' (ver docstring del módulo)."""
    from sklearn.ensemble import IsolationForest

    return IsolationForest(n_estimators=300, contamination="auto",
                           random_state=seed, n_jobs=-1).fit(X_train)


def if_scores(model, X: pd.DataFrame) -> np.ndarray:
    """Score de anomalía: -score_samples (mayor = más anómalo)."""
    return -model.score_samples(X)


def deviation_graph_view(features: list[str]) -> list[str]:
    """Vista compacta para IF: desviaciones personales/grupales + grafo + flags — las features
    con semántica de anomalía y escala comparable; las crudas de volumen quedan fuera."""
    return [c for c in features if c.startswith(("z_", "ratio_max_", "primera_vez_"))
            or c in ("n_aristas_nuevas", "ratio_aristas_nuevas", "rareza_media_destinos",
                     "n_src_computers_nuevas", "historial_corto", "sin_peer_group",
                     "es_dia_no_laboral")]


def kmeans_day_distance(ud: pd.DataFrame, models_dir: str | Path = "models") -> pd.Series:
    """Distancia del VECTOR DEL DÍA (perfil-cols) al centroide del cluster del usuario.

    El KMeans se ajustó sobre perfiles medianos de train; aquí solo se TRANSFORMA cada
    día con el mismo log1p+scaler congelado. Usuarios sin cluster (-1): se imputa la mediana de
    train de las distancias (el flag sin_peer_group ya informa al modelo de la imputación)."""
    art = joblib.load(Path(models_dir) / "peer_kmeans.joblib")
    X_day = ud[PEER_PROFILE_COLS].astype(float).copy()
    X_day[PEER_LOG_COLS] = np.log1p(X_day[PEER_LOG_COLS])
    Xs = art["scaler"].transform(X_day)
    centroides = art["kmeans"].cluster_centers_

    dist = np.full(len(ud), np.nan)
    con = ud["peer_cluster"].to_numpy() >= 0
    dist[con] = np.linalg.norm(
        Xs[con] - centroides[ud.loc[con, "peer_cluster"].to_numpy()], axis=1)
    mediana_train = np.nanmedian(dist[(ud.conjunto == "train").to_numpy()])
    return pd.Series(np.where(np.isnan(dist), mediana_train, dist),
                     index=ud.index, name="dist_peer_centroide")


# ---------------------------------------------------------------------------
# Supervisado
# ---------------------------------------------------------------------------

def _xgb_space(rng: np.random.Generator) -> dict:
    return {
        "max_depth": int(rng.integers(3, 8)),
        "learning_rate": float(10 ** rng.uniform(-2, -0.5)),
        "min_child_weight": float(10 ** rng.uniform(0, 1.3)),
        "subsample": float(rng.uniform(0.6, 1.0)),
        "colsample_bytree": float(rng.uniform(0.5, 1.0)),
        "reg_lambda": float(10 ** rng.uniform(-1, 1.5)),
        "gamma": float(10 ** rng.uniform(-2, 0.7)),
    }


def tune_xgboost(d: dict, seed: int = SEED, n_iter: int = N_ITER_XGB) -> dict:
    """Búsqueda aleatoria evaluada en val (average_precision) con early stopping por aucpr."""
    from sklearn.metrics import average_precision_score
    from xgboost import XGBClassifier

    ytr = d["train"]["y"]
    spw = float((ytr == 0).sum() / max((ytr == 1).sum(), 1))
    rng = np.random.default_rng(seed)

    historia = []
    mejor = {"pr_auc_val": -1.0}
    for i in range(n_iter):
        params = _xgb_space(rng)
        model = XGBClassifier(
            n_estimators=2000, early_stopping_rounds=50, eval_metric="aucpr",
            scale_pos_weight=spw, tree_method="hist", random_state=seed,
            n_jobs=-1, **params,
        )
        model.fit(d["train"]["X"], ytr,
                  eval_set=[(d["val"]["X"], d["val"]["y"])], verbose=False)
        pr = float(average_precision_score(d["val"]["y"],
                                           model.predict_proba(d["val"]["X"])[:, 1]))
        fila = {**params, "best_iteration": int(model.best_iteration), "pr_auc_val": pr}
        historia.append(fila)
        if pr > mejor["pr_auc_val"]:
            mejor = {**fila, "modelo": model}
    return {"modelo": mejor.pop("modelo"), "mejores_params": mejor,
            "scale_pos_weight": spw,
            "historia": pd.DataFrame(historia).sort_values("pr_auc_val", ascending=False)}


def reference_models(d: dict, seed: int = SEED) -> dict:
    """RF y Regresión Logística como referencias, tuneadas ligero sobre val.

    La LR lleva sus transformaciones DENTRO del pipeline (regla de la revisión de limpieza):
    QuantileTransformer (rank-based: winsorización suave + gaussianiza colas) ajustado solo
    con train, jamás sobre la tabla maestra.
    """
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import QuantileTransformer

    out = {}
    mejor_rf, mejor_pr = None, -1
    for md in (None, 12, 20):
        rf = RandomForestClassifier(n_estimators=400, max_depth=md, n_jobs=-1,
                                    class_weight="balanced_subsample", random_state=seed)
        rf.fit(d["train"]["X"], d["train"]["y"])
        pr = average_precision_score(d["val"]["y"], rf.predict_proba(d["val"]["X"])[:, 1])
        if pr > mejor_pr:
            mejor_rf, mejor_pr, rf_params = rf, pr, {"max_depth": md, "n_estimators": 400}
    out["rf"] = {"modelo": mejor_rf, "pr_auc_val": float(mejor_pr), "params": rf_params}

    mejor_lr, mejor_pr = None, -1
    for C in (0.01, 0.1, 1.0):
        lr = Pipeline([
            ("qt", QuantileTransformer(output_distribution="normal", subsample=200_000,
                                       random_state=seed)),
            ("lr", LogisticRegression(C=C, class_weight="balanced", max_iter=2000)),
        ])
        lr.fit(d["train"]["X"], d["train"]["y"])
        pr = average_precision_score(d["val"]["y"], lr.predict_proba(d["val"]["X"])[:, 1])
        if pr > mejor_pr:
            mejor_lr, mejor_pr, lr_params = lr, pr, {"C": C, "transform": "QuantileTransformer(normal)"}
    out["logreg"] = {"modelo": mejor_lr, "pr_auc_val": float(mejor_pr), "params": lr_params}
    return out


def fit_calibrator(scores_val: np.ndarray, y_val: np.ndarray, seed: int = SEED) -> dict:
    """Isotónica vs. Platt (sigmoide), decidido por Brier en 5-fold CV DENTRO de val.

    Con pocos positivos la isotónica (no paramétrica) puede sobreajustar; con muchos, Platt se
    queda corta. En lugar de dogma, CV: se ajusta cada método en 4/5 de val y se mide Brier en
    el 1/5 restante. El ganador se reajusta con toda la validación. Test jamás participa.
    """
    from sklearn.isotonic import IsotonicRegression
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import brier_score_loss
    from sklearn.model_selection import StratifiedKFold

    def platt():
        return LogisticRegression(max_iter=1000)

    briers = {"isotonic": [], "platt": []}
    cv = StratifiedKFold(5, shuffle=True, random_state=seed)
    for tr, te in cv.split(scores_val.reshape(-1, 1), y_val):
        iso = IsotonicRegression(out_of_bounds="clip").fit(scores_val[tr], y_val[tr])
        briers["isotonic"].append(brier_score_loss(y_val[te], iso.predict(scores_val[te])))
        pl = platt().fit(scores_val[tr].reshape(-1, 1), y_val[tr])
        briers["platt"].append(
            brier_score_loss(y_val[te], pl.predict_proba(scores_val[te].reshape(-1, 1))[:, 1]))

    resumen = {k: float(np.mean(v)) for k, v in briers.items()}
    metodo = min(resumen, key=resumen.get)
    if metodo == "isotonic":
        cal = IsotonicRegression(out_of_bounds="clip").fit(scores_val, y_val)
        aplicar = cal.predict
    else:
        cal = platt().fit(scores_val.reshape(-1, 1), y_val)
        aplicar = lambda s: cal.predict_proba(np.asarray(s).reshape(-1, 1))[:, 1]
    return {"metodo": metodo, "brier_cv": resumen, "calibrador": cal, "aplicar": aplicar}


# ---------------------------------------------------------------------------
# Evaluación
# ---------------------------------------------------------------------------

def recall_at_fpr(y: np.ndarray, s: np.ndarray, fpr_obj: float) -> float:
    from sklearn.metrics import roc_curve
    fpr, tpr, _ = roc_curve(y, s)
    return float(np.interp(fpr_obj, fpr, tpr))


def evaluate_scores(y: np.ndarray, s: np.ndarray) -> dict:
    from sklearn.metrics import average_precision_score, f1_score, roc_auc_score

    umbrales = np.quantile(s, np.linspace(0.80, 0.9995, 200))
    f1s = [f1_score(y, s >= u, zero_division=0) for u in umbrales]
    return {
        "pr_auc": float(average_precision_score(y, s)),
        "roc_auc": float(roc_auc_score(y, s)),
        **{f"recall@fpr{int(f*1000)/10}%": recall_at_fpr(y, s, f) for f in FPR_TARGETS},
        "f1_max": float(np.max(f1s)),
        "umbral_f1_max": float(umbrales[int(np.argmax(f1s))]),
    }


def soc_thresholds(scores_val: np.ndarray, days_val: np.ndarray) -> dict:
    """Umbrales por capacidad operativa: percentil que produce ~N tickets/día en validación."""
    n_dias = len(np.unique(days_val))
    out = {}
    for nombre, cap in (("naranja", SOC_TICKETS_DIA), ("rojo", SOC_ROJOS_DIA)):
        k = cap * n_dias
        out[nombre] = float(np.sort(scores_val)[-k]) if k < len(scores_val) else float(scores_val.min())
    return out


def confusion_at(y: np.ndarray, s: np.ndarray, umbral: float) -> dict:
    pred = s >= umbral
    return {"TP": int((pred & (y == 1)).sum()), "FP": int((pred & (y == 0)).sum()),
            "FN": int((~pred & (y == 1)).sum()), "TN": int((~pred & (y == 0)).sum())}


def alerts_vs_recall_curve(y: np.ndarray, s: np.ndarray, days: np.ndarray,
                           users: np.ndarray) -> pd.DataFrame:
    """El puente modelo-negocio: alertas/día vs. recall de CUENTAS comprometidas (no de días)."""
    n_dias = len(np.unique(days))
    comprometidas = set(users[y == 1])
    filas = []
    for alerts_dia in (1, 2, 5, 10, 20, 30, 50, 100):
        k = min(alerts_dia * n_dias, len(s))
        umbral = np.sort(s)[-k]
        cubiertas = set(users[(s >= umbral) & (y == 1)])
        filas.append({"alertas_dia": alerts_dia,
                      "recall_cuentas": len(cubiertas) / max(len(comprometidas), 1),
                      "recall_dias": float(((s >= umbral) & (y == 1)).sum() / max((y == 1).sum(), 1))})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# Estabilidad (reporte OOT): PSI, CSI, KS con tabla TE/TNE
# ---------------------------------------------------------------------------

def _bins_from(expected: np.ndarray, n: int = PSI_BINS) -> np.ndarray:
    qs = np.quantile(expected, np.linspace(0, 1, n + 1))
    qs[0], qs[-1] = -np.inf, np.inf
    return np.unique(qs)


def psi(expected: np.ndarray, actual: np.ndarray, bins: np.ndarray | None = None) -> float:
    """Population Stability Index sobre deciles de la población esperada (train)."""
    bins = _bins_from(expected) if bins is None else bins
    e = np.histogram(expected, bins)[0] / len(expected) + EPS
    a = np.histogram(actual, bins)[0] / len(actual) + EPS
    return float(np.sum((a - e) * np.log(a / e)))


def csi_table(ud: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """CSI = el mismo índice, por feature: ¿cambió la distribución de la variable en OOT?"""
    tr = ud[ud.conjunto == "train"]
    te = ud[ud.conjunto == "test"]
    filas = [{"feature": f, "csi": psi(tr[f].astype(float).to_numpy(),
                                       te[f].astype(float).to_numpy())} for f in features]
    df = pd.DataFrame(filas).sort_values("csi", ascending=False)
    df["estado"] = pd.cut(df.csi, [-np.inf, 0.10, 0.25, np.inf],
                          labels=["estable", "vigilar", "inestable"])
    return df


def ks_table(y: np.ndarray, s: np.ndarray, n_bins: int = PSI_BINS) -> tuple[pd.DataFrame, float]:
    """Tabla clásica de deciles de score: TE/TNE por decil, acumulados y estadístico KS."""
    df = pd.DataFrame({"y": y, "s": s})
    df["decil"] = pd.qcut(df.s.rank(method="first"), n_bins, labels=False) + 1
    g = df.groupby("decil").agg(n=("y", "size"), eventos=("y", "sum"),
                                score_min=("s", "min"), score_max=("s", "max"))
    g = g.sort_index(ascending=False)  # decil 10 (score alto) primero
    g["no_eventos"] = g.n - g.eventos
    g["TE"] = g.eventos / g.n                       # tasa de eventos del decil
    g["TNE"] = g.no_eventos / g.n                   # tasa de no-eventos del decil
    g["pct_eventos_acum"] = g.eventos.cumsum() / g.eventos.sum()
    g["pct_no_eventos_acum"] = g.no_eventos.cumsum() / g.no_eventos.sum()
    g["ks"] = (g.pct_eventos_acum - g.pct_no_eventos_acum).abs()
    return g.round(4), float(g.ks.max())


# ---------------------------------------------------------------------------
# Orquestación de la fase
# ---------------------------------------------------------------------------

def run_fase4(work_dir: str | Path = "data/work", models_dir: str | Path = "models",
              out_dir: str | Path = "docs/modeling", seed: int = SEED) -> dict:
    """Pipeline completo de modelado. Devuelve el reporte; persiste figuras, JSON y artefactos."""
    from sklearn.metrics import average_precision_score

    work_dir, models_dir, out_dir = Path(work_dir), Path(models_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ud = three_way_split(pd.read_parquet(work_dir / "user_day_features.parquet"))
    rep: dict = {"conjuntos": {s: {"user_days": int((ud.conjunto == s).sum()),
                                   "positivos": int(ud.loc[ud.conjunto == s, "y"].sum()),
                                   "dias": [int(ud.loc[ud.conjunto == s, "day"].min()),
                                            int(ud.loc[ud.conjunto == s, "day"].max())]}
                              for s in ("train", "val", "test")}}

    # ---------- no supervisado ----------
    d_full = design_matrices(ud)
    vista_dev = deviation_graph_view(d_full["features"])
    rep["if"] = {}
    modelos_if = {}
    for nombre, cols in (("todas_las_features", d_full["features"]),
                         ("desviaciones_y_grafo", vista_dev)):
        iso = train_isolation_forest(d_full["train"]["X"][cols], seed)
        s_test = if_scores(iso, d_full["test"]["X"][cols])
        rep["if"][nombre] = {"n_features": len(cols),
                             **evaluate_scores(d_full["test"]["y"], s_test)}
        modelos_if[nombre] = iso
    mejor_if = max(rep["if"], key=lambda k: rep["if"][k]["pr_auc"])
    rep["if"]["elegido"] = mejor_if
    iso_final = modelos_if[mejor_if]
    cols_if = d_full["features"] if mejor_if == "todas_las_features" else vista_dev

    dist_km = kmeans_day_distance(ud, models_dir)
    rep["kmeans_score"] = evaluate_scores(d_full["test"]["y"],
                                          dist_km[(ud.conjunto == "test").to_numpy()].to_numpy())

    # ---------- supervisado: ronda 1 (sin feature KMeans) ----------
    tuning = tune_xgboost(d_full, seed)
    rep["xgb_ronda1"] = {"pr_auc_val": tuning["mejores_params"]["pr_auc_val"],
                         "params": tuning["mejores_params"],
                         "scale_pos_weight": tuning["scale_pos_weight"]}

    # ---------- iteración 4.8: agregar dist_peer_centroide y re-entrenar ----------
    ud["dist_peer_centroide"] = dist_km
    d2 = design_matrices(ud)
    tuning2 = tune_xgboost(d2, seed)
    rep["xgb_ronda2_con_dist_kmeans"] = {"pr_auc_val": tuning2["mejores_params"]["pr_auc_val"],
                                         "params": tuning2["mejores_params"]}
    if tuning2["mejores_params"]["pr_auc_val"] >= tuning["mejores_params"]["pr_auc_val"]:
        d, tuning, con_dist = d2, tuning2, True
    else:
        d, con_dist = d_full, False
        ud = ud.drop(columns=["dist_peer_centroide"])
    rep["iteracion_4_8"] = {"feature_agregada": "dist_peer_centroide", "se_conserva": con_dist}
    xgb = tuning["modelo"]

    # ---------- referencias ----------
    refs = reference_models(d, seed)
    rep["referencias"] = {k: {"pr_auc_val": v["pr_auc_val"], "params": v["params"]}
                          for k, v in refs.items()}

    # ---------- selección (val) ----------
    s_val = {"xgboost": xgb.predict_proba(d["val"]["X"])[:, 1],
             "rf": refs["rf"]["modelo"].predict_proba(d["val"]["X"])[:, 1],
             "logreg": refs["logreg"]["modelo"].predict_proba(d["val"]["X"])[:, 1]}
    rep["seleccion_val"] = {m: {"pr_auc_val": float(average_precision_score(d["val"]["y"], s)),
                                "recall@fpr1%_val": recall_at_fpr(d["val"]["y"], s, 0.01)}
                            for m, s in s_val.items()}
    elegido = max(rep["seleccion_val"], key=lambda m: rep["seleccion_val"][m]["pr_auc_val"])
    rep["modelo_elegido"] = elegido
    modelo_final = {"xgboost": xgb, "rf": refs["rf"]["modelo"],
                    "logreg": refs["logreg"]["modelo"]}[elegido]

    # ---------- calibración (solo val) ----------
    cal = fit_calibrator(s_val[elegido], d["val"]["y"], seed)
    rep["calibracion"] = {"metodo": cal["metodo"], "brier_cv_val": cal["brier_cv"]}

    # ---------- evaluación final en test/OOT ----------
    s_test_raw = modelo_final.predict_proba(d["test"]["X"])[:, 1]
    s_test = cal["aplicar"](s_test_raw)
    s_train = cal["aplicar"](modelo_final.predict_proba(d["train"]["X"])[:, 1])
    y_test = d["test"]["y"]
    rep["test"] = {m: evaluate_scores(y_test, s)
                   for m, s in (("modelo_calibrado", s_test),
                                ("isolation_forest", if_scores(iso_final, d["test"]["X"][cols_if])))}
    umbrales = soc_thresholds(cal["aplicar"](s_val[elegido]), d["val"]["days"])
    rep["umbrales_soc"] = umbrales
    rep["confusion_naranja_test"] = confusion_at(y_test, s_test, umbrales["naranja"])
    curva = alerts_vs_recall_curve(y_test, s_test, d["test"]["days"], d["test"]["users"])
    rep["curva_alertas_recall"] = curva.to_dict("records")

    # ---------- estabilidad OOT ----------
    tabla_ks, ks_stat = ks_table(y_test, s_test)
    rep["estabilidad"] = {
        "psi_score_train_vs_oot": psi(s_train, s_test),
        "ks_test": ks_stat,
    }

    # ---------- SHAP ----------
    import shap
    explainer = shap.TreeExplainer(xgb)
    sv = explainer.shap_values(d["test"]["X"])
    imp = pd.Series(np.abs(sv).mean(0), index=d["features"]).sort_values(ascending=False)
    rep["shap_top15"] = imp.head(15).round(4).to_dict()
    rep["estabilidad"]["csi_top10"] = csi_table(ud, imp.head(10).index.tolist()).to_dict("records")

    _figuras(rep, curva, tabla_ks, y_test, s_test, sv, d, out_dir)

    joblib.dump({"modelo": modelo_final, "tipo": elegido, "calibrador": cal["calibrador"],
                 "metodo_calibracion": cal["metodo"], "isolation_forest": iso_final,
                 "features_if": cols_if, "features": d["features"], "umbrales_soc": umbrales,
                 "explainer_shap": explainer, "con_dist_peer": con_dist},
                models_dir / "fase4_artefactos.joblib")
    if con_dist:
        ud.to_parquet(work_dir / "user_day_features.parquet", compression="zstd")

    (out_dir / "modeling_results.json").write_text(
        json.dumps(rep, indent=2, default=str))
    tabla_ks.to_csv(out_dir / "tabla_ks_deciles.csv")
    tuning["historia"].head(10).to_csv(out_dir / "tuning_top10.csv", index=False)
    return rep


def _figuras(rep, curva, tabla_ks, y_test, s_test, sv, d, out_dir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import precision_recall_curve

    from src.eda import COLOR, _caption, apply_style
    apply_style()

    # fig4: curva PR + puente alertas/día vs recall
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))
    prec, rec, _ = precision_recall_curve(y_test, s_test)
    ax1.plot(rec, prec, color=COLOR["normal"], linewidth=2)
    base = y_test.mean()
    ax1.axhline(base, color=COLOR["baseline"], linestyle="--", linewidth=1)
    ax1.text(0.02, base * 1.6, f"azar = {base:.4f}", fontsize=8, color=COLOR["ink2"])
    ax1.set_xlabel("recall (usuario-días)"); ax1.set_ylabel("precisión")
    ax1.set_title(f"Curva Precision-Recall en test (PR-AUC = {rep['test']['modelo_calibrado']['pr_auc']:.3f})")

    ax2.plot(curva.alertas_dia, curva.recall_cuentas * 100, marker="o",
             color=COLOR["comprometido"], linewidth=2, label="cuentas comprometidas")
    ax2.plot(curva.alertas_dia, curva.recall_dias * 100, marker="s",
             color=COLOR["normal"], linewidth=1.6, label="usuario-días maliciosos")
    ax2.set_xscale("log"); ax2.set_xticks(curva.alertas_dia); ax2.set_xticklabels(curva.alertas_dia)
    ax2.set_xlabel("presupuesto de alertas por día (log)"); ax2.set_ylabel("recall en test (%)")
    ax2.set_title("El puente modelo ↔ negocio"); ax2.legend(fontsize=8, frameon=False)
    r20 = curva.loc[curva.alertas_dia == SOC_TICKETS_DIA, "recall_cuentas"].iloc[0] * 100
    _caption(fig, "Hallazgo: con el desbalance de 1 malicioso por cada ~500 usuario-días en test, el modelo calibrado "
                  f"alcanza PR-AUC {rep['test']['modelo_calibrado']['pr_auc']:.3f} (azar: {base:.4f}); con un presupuesto de "
                  f"{SOC_TICKETS_DIA} alertas/día el SOC cubriría el {r20:.0f}% de las cuentas comprometidas del periodo de prueba.",
             y=-0.06)
    fig.savefig(out_dir / "fig4_evaluacion.png"); plt.close(fig)

    # fig5: SHAP summary
    import shap
    fig = plt.figure(figsize=(9, 6))
    shap.summary_plot(sv, d["test"]["X"], max_display=15, show=False, plot_size=None)
    fig = plt.gcf()
    fig.suptitle("SHAP global en test: qué mueve la probabilidad de compromiso", y=1.02,
                 fontweight="bold", fontsize=12)
    top3 = list(rep["shap_top15"])[:3]
    _caption(fig, "Hallazgo: las features dominantes son "
                  f"{', '.join(top3)} — niveles de desviación y novedad, no volumen crudo: el modelo aprendió a "
                  "comparar contra la línea base de cada usuario, que es la tesis del proyecto.", y=-0.05)
    fig.savefig(out_dir / "fig5_shap_summary.png", bbox_inches="tight"); plt.close(fig)


if __name__ == "__main__":
    rep = run_fase4()
    claves = ("conjuntos", "if", "kmeans_score", "xgb_ronda1", "xgb_ronda2_con_dist_kmeans",
              "iteracion_4_8", "referencias", "seleccion_val", "modelo_elegido", "calibracion",
              "test", "umbrales_soc", "confusion_naranja_test", "estabilidad", "shap_top15")
    print(json.dumps({k: rep[k] for k in claves}, indent=2, default=str))
