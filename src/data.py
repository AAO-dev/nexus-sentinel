"""Adquisición y muestreo del dataset LANL.

Responsabilidades:
- Descarga en streaming de auth.txt.gz (7.2 GB) y redteam.txt.gz (4.8 KB) desde csr.lanl.gov,
  documentando fecha, URL y tamaños. Nota: desde 2026 el sitio antepone un "data fence"
  (email + uso declarado) que devuelve un token de descarga; ver request_download_token().
- Lectura por chunks con pandas (compression='gzip', chunksize=...) sin descomprimir a disco.
- Muestreo documentado: ventana de los primeros 30 días, TODOS los usuarios de
  redteam.txt + muestra estratificada por actividad de usuarios normales (semilla fija),
  excluyendo cuentas de sistema y de máquina del universo muestreable.
- Persistencia del dataset de trabajo en Parquet + metadata JSON con todos los conteos
  (pre y post muestreo) para la verificación contra las cifras publicadas y para el documento.

Cifras publicadas del dataset (para verificación):
- 1,648,275,307 eventos totales en las 5 fuentes; 12,425 usuarios; 17,684 computadoras; 58 días.
- auth.txt.gz: ~1,051M eventos. redteam.txt.gz: 4.8 KB (~749 eventos, ~98 cuentas, con 12 duplicados).
"""

from __future__ import annotations

import gzip
import json
import time as _time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import requests

LANL_BASE_URL = "https://csr.lanl.gov"
LANL_PAGE_URL = f"{LANL_BASE_URL}/data/cyber1/"
TOKEN_URL = f"{LANL_BASE_URL}/data-fence/token"

AUTH_COLUMNS = [
    "time", "src_user", "dst_user", "src_computer", "dst_computer",
    "auth_type", "logon_type", "auth_orientation", "outcome",
]
REDTEAM_COLUMNS = ["time", "user", "src_computer", "dst_computer"]

SECONDS_PER_DAY = 86_400
SEED = 42
SAMPLE_WINDOW_DAYS = 30
N_NORMAL_USERS = 4_000
N_ACTIVITY_STRATA = 4  # cuartiles de actividad para la estratificación
CHUNK_SIZE = 5_000_000

# Cifras publicadas en https://csr.lanl.gov/data/cyber1/ (para verificación de conteos)
PUBLISHED = {
    "total_events_all_sources": 1_648_275_307,
    "users": 12_425,
    "computers": 17_684,
    "days": 58,
    "auth_gz_size": "7.2G",
    "redteam_gz_size": "4.8K",
}


def is_system_account(user: str) -> bool:
    """Criterio de exclusión: cuentas de sistema y de máquina.

    - Cuentas de máquina: la parte local termina en '$' (ej. 'C625$@DOM1').
    - Cuentas de sistema bien conocidas no desidentificadas: SYSTEM, Local Service,
      Network Service, ANONYMOUS LOGON.
    - '?' es el marcador de nulo del dataset.
    """
    local = user.split("@", 1)[0]
    if local.endswith("$"):
        return True
    return local.upper() in {"SYSTEM", "LOCAL SERVICE", "NETWORK SERVICE", "ANONYMOUS LOGON", "?"}


# ---------------------------------------------------------------------------
# Descarga
# ---------------------------------------------------------------------------

def request_download_token(email: str, usage: str) -> str:
    """Solicita el token del data fence de LANL (GET /data-fence/token?email=&usage=).

    El sitio pide email y uso declarado; devuelve el fragmento de ruta que arma la URL
    de descarga: {LANL_BASE_URL}/data-fence/{token}/cyber1/{archivo}.
    """
    resp = requests.get(TOKEN_URL, params={"email": email, "usage": usage}, timeout=30)
    resp.raise_for_status()
    return resp.text.strip()


def download_streaming(filename: str, dest_dir: str | Path, token: str) -> Path:
    """Descarga un archivo del dataset en streaming (chunks de 1 MB) y documenta la descarga.

    Escribe {filename}.download.json junto al archivo con URL, fecha UTC, tamaño y duración,
    para poder citar la procedencia de los datos en el notebook y el documento.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    url = f"{LANL_BASE_URL}/data-fence/{token}/cyber1/{filename}"

    started = _time.time()
    with requests.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                fh.write(chunk)
    elapsed = _time.time() - started

    meta = {
        "filename": filename,
        "url": f"{LANL_BASE_URL}/data-fence/<token>/cyber1/{filename}",  # token no se persiste
        "source_page": LANL_PAGE_URL,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "size_bytes": dest.stat().st_size,
        "elapsed_seconds": round(elapsed, 1),
    }
    (dest_dir / f"{filename}.download.json").write_text(json.dumps(meta, indent=2))
    return dest


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------

def read_auth_chunks(path: str | Path, chunk_size: int = CHUNK_SIZE, usecols: list[str] | None = None):
    """Itera auth.txt.gz por chunks sin descomprimir a disco.

    El dataset usa '?' como marcador de campo sin valor; se preserva como string para que
    los conteos de nulos del EDA sean explícitos: el patrón de ausencias también informa.
    """
    return pd.read_csv(
        path,
        compression="gzip",
        header=None,
        names=AUTH_COLUMNS,
        usecols=usecols,
        dtype={c: "int64" if c == "time" else "object" for c in (usecols or AUTH_COLUMNS)},
        chunksize=chunk_size,
        keep_default_na=False,  # '?' es el nulo del dataset; no inventar NaN
        na_values=[],
    )


def load_redteam(path: str | Path) -> pd.DataFrame:
    """Carga redteam.txt.gz completo (KB), deduplica y añade la columna day.

    El archivo trae 12 líneas duplicadas conocidas; se eliminan aquí y el conteo
    queda registrado en la metadata del muestreo.
    """
    df = pd.read_csv(
        path, compression="gzip", header=None, names=REDTEAM_COLUMNS,
        keep_default_na=False, na_values=[],
    )
    df = df.drop_duplicates().reset_index(drop=True)
    df["day"] = df["time"] // SECONDS_PER_DAY
    return df


# ---------------------------------------------------------------------------
# Muestreo
# ---------------------------------------------------------------------------

def scan_auth(auth_path: str | Path, max_day: int = SAMPLE_WINDOW_DAYS) -> dict:
    """Pasada 1 sobre auth.txt.gz completo: conteos globales + actividad por usuario en ventana.

    Recorre TODO el archivo (para verificar el conteo publicado de eventos de auth) y
    acumula, solo dentro de la ventana [0, max_day), los eventos por src_user — insumo
    del muestreo estratificado. Solo parsea time y src_user (usecols) por velocidad.
    """
    cutoff = max_day * SECONDS_PER_DAY
    total_events = 0
    window_events = 0
    max_time = 0
    user_counts: dict[str, int] = {}

    for chunk in read_auth_chunks(auth_path, usecols=["time", "src_user"]):
        total_events += len(chunk)
        max_time = max(max_time, int(chunk["time"].iloc[-1]))  # archivo ordenado por tiempo
        in_window = chunk[chunk["time"] < cutoff]
        window_events += len(in_window)
        if len(in_window):
            for user, n in in_window["src_user"].value_counts().items():
                user_counts[user] = user_counts.get(user, 0) + int(n)

    return {
        "total_events": total_events,
        "window_events": window_events,
        "max_time": max_time,
        "total_days": max_time // SECONDS_PER_DAY + 1,
        "user_counts_window": user_counts,
    }


def sample_users(
    user_counts: dict[str, int],
    redteam_users: set[str],
    n_normal: int = N_NORMAL_USERS,
    seed: int = SEED,
) -> dict:
    """Selecciona los usuarios del dataset de trabajo.

    - TODOS los usuarios que aparecen en redteam.txt (cuentas comprometidas).
    - Muestra aleatoria de n_normal usuarios humanos normales, estratificada por nivel de
      actividad (cuartiles del nº de eventos en ventana) para no sesgar hacia cuentas
      ruidosas ni hacia cuentas casi inactivas. Semilla fija para reproducibilidad.
    - Se excluyen del universo muestreable las cuentas de sistema/máquina (is_system_account).
    """
    rng = np.random.default_rng(seed)

    human = pd.Series(
        {u: n for u, n in user_counts.items() if not is_system_account(u)}, name="n_events"
    )
    normal_pool = human[~human.index.isin(redteam_users)]

    strata = pd.qcut(normal_pool.rank(method="first"), N_ACTIVITY_STRATA, labels=False)
    per_stratum = n_normal // N_ACTIVITY_STRATA
    selected_normal: list[str] = []
    for s in range(N_ACTIVITY_STRATA):
        members = normal_pool.index[strata == s].to_numpy()
        take = min(per_stratum, len(members))
        selected_normal.extend(rng.choice(members, size=take, replace=False))

    return {
        "redteam_users": sorted(redteam_users),
        "normal_users": sorted(selected_normal),
        "selected_users": set(redteam_users) | set(selected_normal),
        "n_human_users_window": int(len(human)),
        "n_system_accounts_excluded": int(len(user_counts) - len(human)),
        "seed": seed,
        "strata": N_ACTIVITY_STRATA,
    }


def filter_events_to_parquet(
    auth_path: str | Path,
    selected_users: set[str],
    out_parquet: str | Path,
    max_day: int = SAMPLE_WINDOW_DAYS,
) -> dict:
    """Pasada 2: filtra auth.txt.gz a la ventana y usuarios muestreados y escribe Parquet.

    Se conserva un evento si src_user O dst_user está en la muestra: la feature de cadenas
    de saltos (4.2) y el mapeo a eventos crudos de la UI necesitan ver al usuario también
    como destino. El archivo está ordenado por tiempo, así que se corta al llegar a la ventana.
    """
    cutoff = max_day * SECONDS_PER_DAY
    out_parquet = Path(out_parquet)
    out_parquet.parent.mkdir(parents=True, exist_ok=True)

    writer: pq.ParquetWriter | None = None
    kept = 0
    try:
        for chunk in read_auth_chunks(auth_path):
            if int(chunk["time"].iloc[0]) >= cutoff:
                break  # ya salimos de la ventana; el resto del archivo no se necesita
            chunk = chunk[chunk["time"] < cutoff]
            mask = chunk["src_user"].isin(selected_users) | chunk["dst_user"].isin(selected_users)
            sel = chunk[mask].copy()
            if sel.empty:
                continue
            sel["day"] = sel["time"] // SECONDS_PER_DAY
            table = pa.Table.from_pandas(sel, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(out_parquet, table.schema, compression="zstd")
            writer.write_table(table)
            kept += len(sel)
    finally:
        if writer is not None:
            writer.close()

    return {"events_kept": kept, "parquet_path": str(out_parquet)}


def build_working_sample(
    auth_path: str | Path,
    redteam_path: str | Path,
    out_dir: str | Path = "data/work",
    max_day: int = SAMPLE_WINDOW_DAYS,
    n_normal: int = N_NORMAL_USERS,
    seed: int = SEED,
) -> dict:
    """Orquesta el muestreo completo y persiste el dataset de trabajo.

    Salidas en out_dir:
    - auth_sample.parquet  : eventos de auth de la ventana para los usuarios muestreados.
    - redteam.parquet      : redteam deduplicado con columna day.
    - sample_metadata.json : conteos pre/post, criterios, semilla y verificación de cifras.
    Devuelve el dict de metadata.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    redteam = load_redteam(redteam_path)
    redteam_raw = pd.read_csv(redteam_path, compression="gzip", header=None, names=REDTEAM_COLUMNS)
    redteam.to_parquet(out_dir / "redteam.parquet", compression="zstd")
    redteam_users = set(redteam["user"])

    scan = scan_auth(auth_path, max_day=max_day)
    sample = sample_users(scan["user_counts_window"], redteam_users, n_normal=n_normal, seed=seed)
    filtered = filter_events_to_parquet(
        auth_path, sample["selected_users"], out_dir / "auth_sample.parquet", max_day=max_day
    )

    meta = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": LANL_PAGE_URL,
        "published_figures": PUBLISHED,
        "sampling": {
            "window_days": max_day,
            "seed": seed,
            "n_normal_users_target": n_normal,
            "strata": sample["strata"],
            "exclusion_criteria": "cuentas de máquina (local termina en $) y de sistema "
                                  "(SYSTEM, Local Service, Network Service, ANONYMOUS LOGON, ?)",
            "event_keep_rule": "src_user O dst_user en la muestra, time < window_days*86400",
        },
        "counts": {
            "auth_total_events": scan["total_events"],
            "auth_total_days": scan["total_days"],
            "auth_window_events": scan["window_events"],
            "auth_users_in_window": len(scan["user_counts_window"]),
            "human_users_in_window": sample["n_human_users_window"],
            "system_accounts_excluded": sample["n_system_accounts_excluded"],
            "redteam_events_raw": int(len(redteam_raw)),
            "redteam_events_dedup": int(len(redteam)),
            "redteam_duplicates_removed": int(len(redteam_raw) - len(redteam)),
            "redteam_users": len(redteam_users),
            "redteam_days": sorted(int(d) for d in redteam["day"].unique()),
            "sampled_normal_users": len(sample["normal_users"]),
            "sampled_users_total": len(sample["selected_users"]),
            "events_kept": filtered["events_kept"],
        },
        "users": {
            "redteam": sample["redteam_users"],
            "normal_sample": sample["normal_users"],
        },
    }
    (out_dir / "sample_metadata.json").write_text(json.dumps(meta, indent=2))
    return meta


# ---------------------------------------------------------------------------
# CLI: python -m src.data --email ... --usage "..." [--skip-download]
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Descarga y muestreo del dataset LANL")
    parser.add_argument("--email", help="email para el data fence de LANL")
    parser.add_argument("--usage", help="uso declarado de los datos")
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--work-dir", default="data/work")
    parser.add_argument("--skip-download", action="store_true",
                        help="usar archivos ya presentes en raw-dir")
    args = parser.parse_args()

    raw = Path(args.raw_dir)
    if not args.skip_download:
        token = request_download_token(args.email, args.usage)
        print(f"[data] token del data fence obtenido; descargando a {raw}/ ...")
        for fname in ("redteam.txt.gz", "auth.txt.gz"):
            path = download_streaming(fname, raw, token)
            print(f"[data] {fname}: {path.stat().st_size:,} bytes")

    meta = build_working_sample(raw / "auth.txt.gz", raw / "redteam.txt.gz", out_dir=args.work_dir)
    print(json.dumps(meta["counts"], indent=2))


if __name__ == "__main__":
    main()
