"""Ingeniería de variables usuario-día (Fase 3, secciones 4.1-4.4 y 4.6-4.7 del plan).

Principio rector: el modelo no ve logs, ve desviaciones. Cada feature responde una de estas
preguntas, y cada nivel existe porque el anterior no basta:

(a) ¿Qué hizo hoy?             -> features crudas (build_raw_user_day)
(b) ¿Qué tan distinto de SU pasado?  -> desviación personal (add_personal_deviation)
(c) ¿Qué tan distinto de SUS PARES?  -> peer groups KMeans + desviación grupal (add_peer_deviation)
(d) ¿Qué tan nuevo es su grafo?      -> src/graph.py (add_graph_features)

Reglas anti-fuga aplicadas en este módulo (auditables con la skill /revisar-fugas):
- Desviación personal: estadísticas sobre los días previos del usuario vía shift(1) + rolling —
  el día evaluado JAMÁS entra en su propia media/desviación/máximo.
- Peer groups: los perfiles y el KMeans se ajustan SOLO con días de entrenamiento (day < SPLIT_DAY);
  en test solo se asigna el cluster ya congelado.
- La desviación grupal del día D usa la distribución del cluster ese mismo día D (información
  contemporánea disponible al cerrar el día, sin etiquetas — no es fuga temporal).
- Ninguna feature deriva de redteam.txt: el etiquetado (label_user_days) solo produce y,
  n_eventos_redteam y el mapeo para la UI, nunca insumos del modelo.
- Partición temporal estricta por día calendario (temporal_split), nunca aleatoria.

Nota metodológica (auditoría /revisar-fugas): las fronteras circadianas (work_hours,
nonwork_days) se infieren de la actividad AGREGADA de la red en la ventana completa. Es
información contemporánea sin etiquetas — el nivel de actividad global de un día es observable
al cierre de ese día en un SOC real, igual que las estadísticas de peers del mismo día — y de
estructura de calendario (periodicidad semanal), no de comportamiento individual. Se acepta bajo
el mismo estándar que la desviación grupal same-day; NO usa redteam.txt en ningún punto.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

from src.data import SECONDS_PER_DAY, SEED

EPS = 1e-6
HISTORY_WINDOW_DAYS = 30   # ventana móvil de días ACTIVOS previos del usuario (4.3)
MIN_HISTORY_DAYS = 7       # menos que esto: desviaciones imputadas a 0 + flag historial_corto (4.7)
SPLIT_DAY = 20             # train: días 0-19 (67%), test: días 20-29 (33%) — partición 4.7
KMEANS_K_RANGE = range(2, 11)

# Features a las que se aplica desviación personal (z, ratio_max) — las señales del EDA
DEVIATION_COLS = [
    "n_eventos", "n_dst_computers", "n_src_computers", "n_fallos", "ratio_fallos",
    "n_ntlm", "ratio_ntlm", "n_fuera_horario", "amplitud_horaria", "n_tgs",
    "n_uso_como_identidad_destino",
]
FIRST_TIME_COLS = ["n_ntlm", "n_fuera_horario", "n_fallos"]  # flags de primera vez (4.3)

# Perfil estático por usuario para peer groups (medianas históricas de train, 4.4)
PEER_PROFILE_COLS = [
    "n_eventos", "n_dst_computers", "n_src_computers", "ratio_ntlm", "ratio_fallos",
    "n_fuera_horario", "amplitud_horaria",
]
# Desviación grupal del día contra el cluster (4.4.3)
PEER_Z_COLS = ["n_eventos", "n_dst_computers", "ratio_ntlm", "ratio_fallos"]


# ---------------------------------------------------------------------------
# (a) Features crudas — sección 4.2
# ---------------------------------------------------------------------------

def build_raw_user_day(
    auth_lf: pl.LazyFrame,
    sampled_users: set[str],
    work_hours: list[int],
    nonwork_days: list[int],
) -> pd.DataFrame:
    """Tabla maestra (user, day) con las features crudas de la sección 4.2.

    Grano: una fila por usuario muestreado y día en que tuvo >=1 evento como origen.
    Las fronteras temporales (work_hours, nonwork_days) vienen inferidas del EDA.
    """
    users = sorted(sampled_users)
    wh_min, wh_max = work_hours[0], work_hours[-1]

    base = (
        auth_lf.filter(pl.col("src_user").is_in(users))
        .with_columns(hora=(pl.col("time") % SECONDS_PER_DAY) // 3600)
    )

    ud = (
        base.group_by("src_user", "day")
        .agg(
            n_eventos=pl.len(),
            n_logons=(pl.col("auth_orientation") == "LogOn").sum(),
            n_logoffs=(pl.col("auth_orientation") == "LogOff").sum(),
            n_dst_computers=pl.col("dst_computer").n_unique(),
            n_src_computers=pl.col("src_computer").n_unique(),
            n_fallos=(pl.col("outcome") == "Fail").sum(),
            n_ntlm=(pl.col("auth_type") == "NTLM").sum(),
            n_kerberos=(pl.col("auth_type") == "Kerberos").sum(),
            n_tgt=(pl.col("auth_orientation") == "TGT").sum(),
            n_tgs=(pl.col("auth_orientation") == "TGS").sum(),
            n_auth_type_nulo=(pl.col("auth_type") == "?").sum(),
            n_network=(pl.col("logon_type") == "Network").sum(),
            n_interactive=(pl.col("logon_type") == "Interactive").sum(),
            n_remote_interactive=(pl.col("logon_type") == "RemoteInteractive").sum(),
            n_batch_service=pl.col("logon_type").is_in(["Batch", "Service"]).sum(),
            n_fuera_horario=(~pl.col("hora").is_between(wh_min, wh_max)).sum(),
            hora_min=pl.col("hora").min(),
            hora_max=pl.col("hora").max(),
        )
        .collect()
    )

    # eventos por hora pico: máximo de eventos en una sola hora del día
    pico = (
        base.group_by("src_user", "day", "hora").len()
        .group_by("src_user", "day").agg(n_eventos_hora_pico=pl.col("len").max())
        .collect()
    )

    # ráfaga máxima de fallos consecutivos (fuerza bruta / password spray)
    consec = (
        base.sort("time")
        .with_columns(fallo=(pl.col("outcome") == "Fail"))
        .with_columns(
            cambio=(pl.col("fallo") != pl.col("fallo").shift(1).over(["src_user", "day"]))
            .fill_null(True).cast(pl.Int32)
        )
        .with_columns(racha_id=pl.col("cambio").cum_sum().over(["src_user", "day"]))
        .filter(pl.col("fallo"))
        .group_by("src_user", "day", "racha_id").len()
        .group_by("src_user", "day").agg(n_fallos_consecutivos_max=pl.col("len").max())
        .collect()
    )

    # veces que la cuenta aparece como IDENTIDAD DESTINO de otra identidad origen:
    # la firma de credenciales usadas en cadenas de saltos máquina-a-máquina (sección 4.2,
    # "dirección"). Se calcula sobre TODOS los eventos retenidos (por eso la regla de
    # muestreo conserva eventos donde el usuario es destino).
    como_dst = (
        auth_lf.filter(
            pl.col("dst_user").is_in(users) & (pl.col("dst_user") != pl.col("src_user"))
        )
        .group_by("dst_user", "day").len()
        .rename({"dst_user": "src_user", "len": "n_uso_como_identidad_destino"})
        .collect()
    )

    df = (
        ud.join(pico, on=["src_user", "day"], how="left")
        .join(consec, on=["src_user", "day"], how="left")
        .join(como_dst, on=["src_user", "day"], how="left")
        .sort("src_user", "day")
        .to_pandas()
    )
    for col in ("n_fallos_consecutivos_max", "n_uso_como_identidad_destino"):
        df[col] = df[col].fillna(0).astype("int64")

    df["ratio_fallos"] = df["n_fallos"] / df["n_eventos"]
    df["ratio_ntlm"] = df["n_ntlm"] / df["n_eventos"]
    df["ratio_dst_por_evento"] = df["n_dst_computers"] / df["n_eventos"]
    df["ratio_auth_type_nulo"] = df["n_auth_type_nulo"] / df["n_eventos"]
    df["ratio_tgs_por_tgt"] = df["n_tgs"] / (df["n_tgt"] + 1)  # +1: evita división por 0
    df["amplitud_horaria"] = df["hora_max"] - df["hora_min"]
    df["es_dia_no_laboral"] = df["day"].isin(nonwork_days).astype("int8")
    df = df.drop(columns=["hora_min", "hora_max"])
    return df


# ---------------------------------------------------------------------------
# (b) Desviación personal — sección 4.3 (corazón del proyecto)
# ---------------------------------------------------------------------------

def add_personal_deviation(ud: pd.DataFrame) -> pd.DataFrame:
    """z-score, ratio vs. máximo histórico y flags de primera vez contra el propio pasado.

    REGLA ANTI-FUGA: todas las estadísticas históricas se calculan sobre la serie del usuario
    DESPLAZADA UN DÍA ACTIVO (shift(1)) con ventana móvil de HISTORY_WINDOW_DAYS días activos:
    el día evaluado nunca participa en su propia línea base. La ventana es sobre días ACTIVOS
    (filas de la tabla), la aproximación honesta cuando los usuarios tienen días sin actividad.

    Días con historial < MIN_HISTORY_DAYS: desviaciones imputadas a 0 + flag historial_corto
    (sección 4.7) — el modelo aprende a no confiar en desviaciones sin línea base.
    """
    ud = ud.sort_values(["src_user", "day"]).reset_index(drop=True)
    g = ud.groupby("src_user", sort=False)

    ud["historial_dias"] = g.cumcount()
    ud["historial_corto"] = (ud["historial_dias"] < MIN_HISTORY_DAYS).astype("int8")
    sin_historial = ud["historial_dias"] == 0
    con_historial_util = ud["historial_dias"] >= MIN_HISTORY_DAYS

    for col in DEVIATION_COLS:
        shifted = g[col].shift(1)
        ud["_s"] = shifted
        roll = ud.groupby("src_user", sort=False)["_s"].rolling(
            HISTORY_WINDOW_DAYS, min_periods=1
        )
        mu = roll.mean().reset_index(level=0, drop=True)
        sigma = roll.std().reset_index(level=0, drop=True)
        mx = roll.max().reset_index(level=0, drop=True)

        z = (ud[col] - mu) / (sigma.fillna(0) + EPS)
        ratio_max = ud[col] / (mx + EPS)
        # imputación 4.7: sin línea base suficiente, la desviación no es confiable
        ud[f"z_{col}"] = np.where(con_historial_util, z, 0.0)
        ud[f"ratio_max_{col}"] = np.where(con_historial_util, ratio_max, 0.0)

    for col in FIRST_TIME_COLS:
        hist_sum = g[col].transform(lambda s: s.shift(1).cumsum())
        primera_vez = (ud[col] > 0) & (hist_sum.fillna(0) == 0) & ~sin_historial
        ud[f"primera_vez_{col}"] = primera_vez.astype("int8")

    ud = ud.drop(columns=["_s"])
    # los z con sigma≈0 explotan; se recortan a un rango informativo pero acotado
    zcols = [f"z_{c}" for c in DEVIATION_COLS]
    ud[zcols] = ud[zcols].clip(-50, 50)
    return ud


# ---------------------------------------------------------------------------
# (c) Peer groups conductuales — sección 4.4
# ---------------------------------------------------------------------------

def build_peer_profiles(ud: pd.DataFrame) -> pd.DataFrame:
    """Perfil estático por usuario: medianas de sus días de ENTRENAMIENTO (day < SPLIT_DAY).

    Anti-fuga: el perfil jamás ve días de test. Usuarios sin días de train quedan fuera
    (recibirán cluster -1 y desviación grupal imputada a 0).
    """
    train = ud[ud["day"] < SPLIT_DAY]
    profiles = train.groupby("src_user")[PEER_PROFILE_COLS].median()
    profiles["n_dias_activos"] = train.groupby("src_user").size()
    return profiles


MIN_CLUSTER_FRAC = 0.01  # un "rol conductual" con <1% de los usuarios no es un rol, es un outlier

# features de perfil con cola pesada: se comprimen con log1p ANTES de escalar para que una
# cuenta monstruo no secuestre el clustering (detectado en la rectificación de la fase:
# sin esto, KMeans producía un cluster de 1 usuario con silhouette engañoso de 0.997)
PEER_LOG_COLS = ["n_eventos", "n_dst_computers", "n_src_computers", "n_fuera_horario"]


def _peer_design_matrix(profiles: pd.DataFrame, scaler=None):
    """log1p en las features de volumen + RobustScaler. Devuelve (X, scaler)."""
    from sklearn.preprocessing import RobustScaler

    X_raw = profiles[PEER_PROFILE_COLS].copy()
    X_raw[PEER_LOG_COLS] = np.log1p(X_raw[PEER_LOG_COLS])
    if scaler is None:
        scaler = RobustScaler().fit(X_raw)
    return scaler.transform(X_raw), scaler


def fit_peer_kmeans(profiles: pd.DataFrame) -> dict:
    """KMeans sobre perfiles escalados; k elegido por silhouette (sección 4.4.2).

    Dos salvaguardas contra soluciones degeneradas:
    - log1p en las features de volumen (colas pesadas) antes del RobustScaler.
    - k solo es candidato si su cluster más chico agrupa >= MIN_CLUSTER_FRAC de los usuarios:
      el silhouette premia aislar outliers extremos en clusters unipersonales, y un cluster
      de 1 usuario no es un peer group (nadie contra quién compararse).
    """
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    X, scaler = _peer_design_matrix(profiles)
    min_size = max(10, int(MIN_CLUSTER_FRAC * len(profiles)))

    resultados = {}
    for k in KMEANS_K_RANGE:
        km = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit(X)
        sizes = np.bincount(km.labels_)
        resultados[k] = {
            "silhouette": float(silhouette_score(X, km.labels_)),
            "min_cluster": int(sizes.min()),
            "valido": bool(sizes.min() >= min_size),
            "modelo": km,
        }
    validos = {k: v for k, v in resultados.items() if v["valido"]}
    elegibles = validos if validos else resultados
    mejor_k = max(elegibles, key=lambda k: elegibles[k]["silhouette"])
    kmeans = resultados[mejor_k]["modelo"]

    return {
        "kmeans": kmeans,
        "scaler": scaler,
        "k": mejor_k,
        "silhouette_por_k": {k: {kk: v[kk] for kk in ("silhouette", "min_cluster", "valido")}
                             for k, v in resultados.items()},
        "user_cluster": pd.Series(kmeans.labels_, index=profiles.index, name="peer_cluster"),
        "profile_cols": PEER_PROFILE_COLS,
    }


def add_peer_deviation(ud: pd.DataFrame, user_cluster: pd.Series) -> pd.DataFrame:
    """z-score del día contra la distribución de su cluster ESE MISMO DÍA (sección 4.4.3).

    Responde: "hoy, ¿se comportó distinto a la gente que se comporta como él?". Usa información
    contemporánea de otros usuarios (sin etiquetas), disponible al cierre del día en un SOC real;
    no es fuga temporal. Usuarios sin perfil de train: cluster -1, desviación imputada a 0 +
    flag sin_peer_group.
    """
    ud = ud.merge(user_cluster, left_on="src_user", right_index=True, how="left")
    ud["sin_peer_group"] = ud["peer_cluster"].isna().astype("int8")
    ud["peer_cluster"] = ud["peer_cluster"].fillna(-1).astype("int32")

    grp = ud[ud["peer_cluster"] >= 0].groupby(["peer_cluster", "day"])
    for col in PEER_Z_COLS:
        stats = grp[col].agg(["mean", "std"]).rename(
            columns={"mean": f"_mu_{col}", "std": f"_sd_{col}"}
        )
        ud = ud.merge(stats, left_on=["peer_cluster", "day"], right_index=True, how="left")
        z = (ud[col] - ud[f"_mu_{col}"]) / (ud[f"_sd_{col}"].fillna(0) + EPS)
        ud[f"z_peer_{col}"] = np.where(ud["peer_cluster"] >= 0, z, 0.0)
        ud = ud.drop(columns=[f"_mu_{col}", f"_sd_{col}"])

    zcols = [f"z_peer_{c}" for c in PEER_Z_COLS]
    ud[zcols] = ud[zcols].clip(-50, 50)
    return ud


# ---------------------------------------------------------------------------
# (4.6) Etiquetado y (4.7) partición temporal
# ---------------------------------------------------------------------------

def label_user_days(ud: pd.DataFrame, redteam: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """y = 1 si el usuario-día tiene >=1 evento red team. Guarda n_eventos_redteam (severidad).

    Las etiquetas NO son features: solo salen de aquí y, n_eventos_redteam (para análisis,
    excluida de la lista de features del modelo) y el reporte de cobertura.
    """
    rt = redteam.groupby(["user", "day"]).size().rename("n_eventos_redteam").reset_index()
    ud = ud.merge(rt, left_on=["src_user", "day"], right_on=["user", "day"], how="left")
    ud = ud.drop(columns=["user"])
    ud["n_eventos_redteam"] = ud["n_eventos_redteam"].fillna(0).astype("int64")
    ud["y"] = (ud["n_eventos_redteam"] > 0).astype("int8")

    cobertura = {
        "pares_redteam_distintos": int(len(rt)),
        "pares_capturados_en_tabla": int(ud["y"].sum()),
        "pares_sin_fila_usuario_dia": int(len(rt) - ud["y"].sum()),
    }
    return ud, cobertura


def temporal_split(ud: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Partición temporal estricta (4.7): train = días 0..SPLIT_DAY-1, test = resto.

    Nunca k-fold aleatorio: los días de un usuario están autocorrelacionados y las features
    históricas cruzarían el corte. Verifica que ambos lados contengan días de ataque.
    """
    ud["split"] = np.where(ud["day"] < SPLIT_DAY, "train", "test")
    resumen = {
        "split_day": SPLIT_DAY,
        "train": {"user_days": int((ud.split == "train").sum()),
                  "maliciosos": int(ud.loc[ud.split == "train", "y"].sum()),
                  "dias_ataque": sorted(ud.loc[(ud.split == "train") & (ud.y == 1), "day"].unique().tolist())},
        "test": {"user_days": int((ud.split == "test").sum()),
                 "maliciosos": int(ud.loc[ud.split == "test", "y"].sum()),
                 "dias_ataque": sorted(ud.loc[(ud.split == "test") & (ud.y == 1), "day"].unique().tolist())},
    }
    assert resumen["train"]["maliciosos"] > 0 and resumen["test"]["maliciosos"] > 0, \
        "ambos lados de la partición deben contener días de ataque (sección 4.7)"
    return ud, resumen


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------

NO_FEATURE_COLS = {"src_user", "day", "y", "n_eventos_redteam", "split", "conjunto",
                   "peer_cluster", "historial_dias"}


def feature_columns(ud: pd.DataFrame) -> list[str]:
    """Columnas que el modelo puede ver (excluye identificadores, etiquetas y auxiliares)."""
    return [c for c in ud.columns if c not in NO_FEATURE_COLS]


def build_master_table(
    work_dir: str | Path = "data/work",
    eda_results: str | Path = "docs/eda/eda_results.json",
    models_dir: str | Path = "models",
) -> tuple[pd.DataFrame, dict]:
    """Pipeline completo de la Fase 3. Persiste user_day_features.parquet + metadata + KMeans.

    Orden: crudas -> desviación personal -> grafo (src/graph.py) -> peers -> etiquetas -> split.
    """
    import joblib

    from src.graph import add_graph_features

    work_dir, models_dir = Path(work_dir), Path(models_dir)
    auth_lf = pl.scan_parquet(work_dir / "auth_sample.parquet")
    redteam = pd.read_parquet(work_dir / "redteam.parquet")
    meta = json.loads((work_dir / "sample_metadata.json").read_text())
    circ = json.loads(Path(eda_results).read_text())["circadiano"]
    sampled = set(meta["users"]["redteam"]) | set(meta["users"]["normal_sample"])

    ud = build_raw_user_day(auth_lf, sampled, circ["work_hours"], circ["nonwork_days"])
    ud = add_personal_deviation(ud)
    ud = add_graph_features(ud, auth_lf, sampled)
    peers = fit_peer_kmeans(build_peer_profiles(ud))
    ud = add_peer_deviation(ud, peers["user_cluster"])
    ud, cobertura = label_user_days(ud, redteam)
    ud, split_info = temporal_split(ud)

    models_dir.mkdir(exist_ok=True)
    joblib.dump({k: peers[k] for k in ("kmeans", "scaler", "k", "profile_cols")},
                models_dir / "peer_kmeans.joblib")
    ud.to_parquet(work_dir / "user_day_features.parquet", compression="zstd")

    info = {
        "n_user_days": int(len(ud)),
        "n_features": len(feature_columns(ud)),
        "feature_cols": feature_columns(ud),
        "kmeans_k": peers["k"],
        "silhouette_por_k": peers["silhouette_por_k"],
        "cluster_sizes": peers["user_cluster"].value_counts().sort_index().to_dict(),
        "cobertura_etiquetas": cobertura,
        "split": split_info,
        "constantes": {"HISTORY_WINDOW_DAYS": HISTORY_WINDOW_DAYS,
                       "MIN_HISTORY_DAYS": MIN_HISTORY_DAYS, "SPLIT_DAY": SPLIT_DAY,
                       "SEED": SEED},
    }
    (work_dir / "features_metadata.json").write_text(json.dumps(info, indent=2))
    return ud, info


if __name__ == "__main__":
    ud, info = build_master_table()
    print(json.dumps({k: info[k] for k in
                      ("n_user_days", "n_features", "kmeans_k", "silhouette_por_k",
                       "cluster_sizes", "cobertura_etiquetas", "split")}, indent=2))
