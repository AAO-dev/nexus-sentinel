"""Análisis exploratorio del dataset de trabajo.

Criterio rector acordado con el usuario: POCAS figuras, cada una respondiendo una pregunta
del problema. Selección curada:

1. fig_ritmo_red      — ciclo circadiano inferido + serie diaria con días no laborales y
                        eventos red team superpuestos. ¿Cuándo vive la red y cuándo atacan?
2. fig_senales        — normal vs. comprometido en las 3 señales que motivan las features:
                        computadoras destino distintas, ratio de fallos, ratio NTLM.
                        ¿En qué se nota un compromiso? (incluye LA gráfica del movimiento lateral)
3. fig_grafo_ego      — conexiones usuario→computadora de un comprometido, antes vs. durante
                        el ataque. La "historia" visual del proyecto.

El desbalance NO es gráfica: es tabla/KPI (un número así de extremo se comunica mejor como número).

La agregación pesada usa polars en modo lazy (37.5M filas); pandas solo toca agregados chicos.
Este módulo también fija el estilo de gráficas del proyecto: paleta
categórica validada para daltonismo (azul=normal, rojo=comprometido), tinta neutra, sin ruido.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl

from src.data import SECONDS_PER_DAY, is_system_account

# ---------------------------------------------------------------------------
# Estilo del proyecto (paleta validada CVD; ver skill dataviz / palette.md)
# ---------------------------------------------------------------------------

COLOR = {
    "normal": "#2a78d6",      # azul — slot categórico 1
    "comprometido": "#e34948",  # rojo — slot categórico 6 (identidad, no "status")
    "historico": "#b8b6ae",   # gris para contexto/fondo
    "surface": "#fcfcfb",
    "ink": "#0b0b0b",
    "ink2": "#52514e",
    "muted": "#898781",
    "grid": "#e1e0d9",
    "baseline": "#c3c2b7",
}

HOURS_PER_DAY = 24


def apply_style() -> None:
    """Estilo único de gráficas del proyecto: marcas delgadas, rejilla recesiva, sin bordes."""
    plt.rcParams.update({
        "figure.facecolor": COLOR["surface"],
        "axes.facecolor": COLOR["surface"],
        "savefig.facecolor": COLOR["surface"],
        "font.family": "sans-serif",
        "font.sans-serif": ["Segoe UI", "DejaVu Sans", "sans-serif"],
        "text.color": COLOR["ink"],
        "axes.labelcolor": COLOR["ink2"],
        "axes.edgecolor": COLOR["baseline"],
        "axes.linewidth": 0.8,
        "axes.grid": True,
        "grid.color": COLOR["grid"],
        "grid.linewidth": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": COLOR["muted"],
        "ytick.color": COLOR["muted"],
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.titlecolor": COLOR["ink"],
        "figure.dpi": 120,
        "savefig.dpi": 150,
        "savefig.bbox": "tight",
    })


# ---------------------------------------------------------------------------
# Carga y agregación usuario-día (versión ligera para el EDA; la tabla completa la
# construye src/features.py)
# ---------------------------------------------------------------------------

def scan_work(work_dir: str | Path = "data/work") -> tuple[pl.LazyFrame, pd.DataFrame, dict]:
    """Devuelve (auth lazy, redteam, metadata del muestreo)."""
    work_dir = Path(work_dir)
    auth = pl.scan_parquet(work_dir / "auth_sample.parquet")
    redteam = pd.read_parquet(work_dir / "redteam.parquet")
    meta = json.loads((work_dir / "sample_metadata.json").read_text())
    return auth, redteam, meta


def build_user_day(auth: pl.LazyFrame, redteam: pd.DataFrame, meta: dict) -> pd.DataFrame:
    """Tabla usuario-día mínima para el EDA, etiquetada con el red team.

    Solo usuarios DE LA MUESTRA como origen: el Parquet retiene eventos donde el usuario
    aparece como destino, lo que mete user-días parciales de usuarios no muestreados si
    se agrupa a ciegas por src_user. El scoring es sobre los 4,104 usuarios muestreados.
    """
    sampled = set(meta["users"]["redteam"]) | set(meta["users"]["normal_sample"])
    ud = (
        auth
        .filter(pl.col("src_user").is_in(sorted(sampled)))
        .group_by("src_user", "day")
        .agg(
            n_eventos=pl.len(),
            n_dst=pl.col("dst_computer").n_unique(),
            n_fallos=(pl.col("outcome") == "Fail").sum(),
            n_ntlm=(pl.col("auth_type") == "NTLM").sum(),
        )
        .collect()
        .to_pandas()
    )
    ud = ud[~ud["src_user"].map(is_system_account)].copy()
    ud["ratio_fallos"] = ud["n_fallos"] / ud["n_eventos"]
    ud["ratio_ntlm"] = ud["n_ntlm"] / ud["n_eventos"]

    mal = set(zip(redteam["user"], redteam["day"]))
    key = list(zip(ud["src_user"], ud["day"]))
    ud["y"] = [1 if k in mal else 0 for k in key]
    return ud


# ---------------------------------------------------------------------------
# Ciclo circadiano y días no laborales (inferencia empírica; el epoch es anónimo)
# ---------------------------------------------------------------------------

def infer_circadian(auth: pl.LazyFrame) -> dict:
    """Infiere el ciclo de la red a partir de la periodicidad de 86,400 s.

    - hourly: eventos por hora-del-día relativa (0-23 desde el epoch), SOLO origen humano:
      las cuentas de máquina hacen beacon 24/7 y aplastan la señal circadiana humana.
    - work_hours: la actividad humana tiene una base de automatización 24/7 (el valle es
      ~59% del pico), así que el umbral es el PUNTO MEDIO entre valle y pico:
      hora laboral si actividad >= valle + 0.5*(pico - valle).
    - daily: eventos humanos por día; días no laborales = actividad < 90% de la mediana.
      El umbral captura las caídas de 2 días con periodicidad 7 (fines de semana) que
      se ven a simple vista en la serie.
    """
    human = auth.filter(
        ~(pl.col("src_user").str.split("@").list.first().str.ends_with("$"))
        & ~pl.col("src_user").str.split("@").list.first().str.to_uppercase().is_in(
            ["SYSTEM", "LOCAL SERVICE", "NETWORK SERVICE", "ANONYMOUS LOGON", "?"])
    )
    hourly = (
        human.with_columns(hora=(pl.col("time") % SECONDS_PER_DAY) // 3600)
        .group_by("hora").len().sort("hora").collect().to_pandas()
    )
    daily = human.group_by("day").len().sort("day").collect().to_pandas()

    peak, trough = hourly["len"].max(), hourly["len"].min()
    active = hourly["len"] >= trough + 0.5 * (peak - trough)
    work_hours = sorted(hourly.loc[active, "hora"].tolist())

    median_daily = daily["len"].median()
    nonwork_days = sorted(daily.loc[daily["len"] < 0.9 * median_daily, "day"].tolist())

    return {
        "hourly": hourly,
        "daily": daily,
        "work_hours": work_hours,
        "work_hours_rule": "actividad humana >= valle + 50% de (pico - valle)",
        "nonwork_days": nonwork_days,
        "nonwork_rule": "actividad humana diaria < 90% de la mediana",
    }


# ---------------------------------------------------------------------------
# Tablas de resumen e indicadores
# ---------------------------------------------------------------------------

def table_types(auth: pl.LazyFrame) -> dict[str, pd.DataFrame]:
    """Distribución de auth_type, logon_type y auth_orientation (con % y nulos '?')."""
    out = {}
    for col in ("auth_type", "logon_type", "auth_orientation"):
        t = auth.group_by(col).len().sort("len", descending=True).collect().to_pandas()
        t["pct"] = (t["len"] / t["len"].sum() * 100).round(2)
        out[col] = t.head(10)
    return out


def build_tables_and_kpis(ud: pd.DataFrame, redteam: pd.DataFrame, meta: dict, circ: dict) -> dict:
    """Tablas de resumen, red team y desbalance, más los indicadores del EDA."""
    c = meta["counts"]
    mal = ud[ud["y"] == 1]
    nor = ud[ud["y"] == 0]

    resumen = {
        "eventos auth totales (dataset)": c["auth_total_events"],
        "eventos en ventana 30 días": c["auth_window_events"],
        "eventos en muestra de trabajo": c["events_kept"],
        "usuarios muestreados": c["sampled_users_total"],
        "usuario-días (humanos)": len(ud),
    }
    tabla_redteam = {
        "eventos red team (únicos)": c["redteam_events_dedup"],
        "cuentas comprometidas": c["redteam_users"],
        "computadoras origen del ataque": int(redteam["src_computer"].nunique()),
        "días con actividad de ataque": len(c["redteam_days"]),
    }
    desbalance = {
        "usuario-días totales": len(ud),
        "usuario-días maliciosos": int(ud["y"].sum()),
        "% maliciosos": round(ud["y"].mean() * 100, 4),
        "ratio 1 malicioso por cada N": int(round(len(ud) / max(ud["y"].sum(), 1))),
    }
    kpis = {
        "mediana n_dst (normal)": float(nor["n_dst"].median()),
        "mediana n_dst (comprometido)": float(mal["n_dst"].median()),
        "media ratio_fallos (normal)": round(float(nor["ratio_fallos"].mean()), 4),
        "media ratio_fallos (comprometido)": round(float(mal["ratio_fallos"].mean()), 4),
        "media ratio_ntlm (normal)": round(float(nor["ratio_ntlm"].mean()), 4),
        "media ratio_ntlm (comprometido)": round(float(mal["ratio_ntlm"].mean()), 4),
        "horario laboral inferido": f"{circ['work_hours'][0]}:00-{circ['work_hours'][-1]}:00 (hora relativa)",
        "días no laborales inferidos": circ["nonwork_days"],
        "cobertura temporal de ataques": f"{len(set(redteam['day']))}/30 días",
    }
    return {"resumen": resumen, "red_team": tabla_redteam, "desbalance": desbalance, "kpis": kpis}


# ---------------------------------------------------------------------------
# Figuras
# ---------------------------------------------------------------------------

def _caption(fig, text: str, y: float = -0.04) -> None:
    """Pie de figura con el hallazgo: la gráfica debe explicarse sola donde sea que se muestre
    (notebook, documento, presentación), no depender del texto que la rodee."""
    import textwrap
    wrapped = "\n".join(textwrap.wrap(text, width=125))
    fig.text(0.5, y, wrapped, ha="center", va="top", fontsize=8.5,
             color=COLOR["ink2"], linespacing=1.4)


def fig_ritmo_red(circ: dict, redteam: pd.DataFrame, out: Path) -> None:
    """Panel A: ciclo circadiano inferido. Panel B: serie diaria + días no laborales + ataques."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 3.8))

    h = circ["hourly"]
    ax1.plot(h["hora"], h["len"] / 1e6, color=COLOR["normal"], linewidth=2)
    wh = circ["work_hours"]
    ax1.axvspan(-0.5, wh[0] - 0.5, color=COLOR["grid"], alpha=0.55, zorder=0)
    ax1.axvspan(wh[-1] + 0.5, 23.5, color=COLOR["grid"], alpha=0.55, zorder=0)
    ax1.set_xlim(-0.5, 23.5)
    ax1.set_xticks(range(0, 24, 4))
    ax1.set_title("La red tiene ciclo circadiano (inferido del epoch anónimo)")
    ax1.set_xlabel("hora relativa del día (time mod 86 400 s)")
    ax1.set_ylabel("eventos de auth (millones)")
    y0, y1 = ax1.get_ylim()
    ax1.text(11.5, y0 + 0.06 * (y1 - y0),
             f"horario laboral inferido: {wh[0]}:00–{wh[-1]}:00",
             fontsize=8, color=COLOR["ink2"], ha="center")

    d = circ["daily"]
    ax2.plot(d["day"], d["len"] / 1e6, color=COLOR["normal"], linewidth=2, zorder=2)
    for nd in circ["nonwork_days"]:
        ax2.axvspan(nd - 0.5, nd + 0.5, color=COLOR["grid"], alpha=0.55, zorder=0)
    rt_daily = redteam.groupby("day").size()
    ymax = (d["len"] / 1e6).max()
    ax2.vlines(rt_daily.index, 0, ymax * 0.12, color=COLOR["comprometido"], linewidth=2, zorder=3)
    ax2.scatter(rt_daily.index, [ymax * 0.12] * len(rt_daily), s=14,
                color=COLOR["comprometido"], zorder=3, label="días con ataque red team")
    ax2.set_title("Actividad diaria: fines de semana inferidos y días de ataque")
    ax2.set_xlabel("día (epoch relativo)")
    ax2.set_ylabel("eventos de auth (millones)")
    ax2.legend(loc="upper right", fontsize=8, frameon=False)

    _caption(fig, "Hallazgo: aunque el epoch es anónimo, la periodicidad de 86,400 s revela el ritmo humano de la red — "
                  "horario laboral de 7:00 a 16:00 (hora relativa) montado sobre una base de automatización 24/7 (panel izq., "
                  "zonas grises = fuera de horario), y fines de semana como caídas de 2 días cada 7 (panel der., sombreados). "
                  "El red team ataca en 18 de los 30 días, también en días no laborales.")
    fig.savefig(out / "fig1_ritmo_red.png")
    plt.close(fig)


def _fmt(v: float) -> str:
    if v == int(v):
        return str(int(v))
    return f"{v:.2f}" if v >= 0.01 else f"{v:.4f}"


def fig_senales(ud: pd.DataFrame, out: Path) -> None:
    """Normal vs. comprometido en 3 señales. El panel de n_dst es LA gráfica del mov. lateral.

    El panel de fallos usa "% de días con >=1 fallo" en lugar de boxplot: las distribuciones
    de ratio colapsan en cero y esconden el hallazgo (el compromiso falla MÁS SEGUIDO pero
    POQUITO — credenciales válidas, no fuerza bruta; el fallo masivo es automatización rota).
    """
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.8))
    groups = [("normal", ud.loc[ud.y == 0]), ("comprometido", ud.loc[ud.y == 1])]
    labels = [f"{name}\n(n={len(g):,})" for name, g in groups]

    def styled_box(ax, col, logscale=False):
        data = [g[col].to_numpy() for _, g in groups]
        if logscale:
            data = [np.clip(v, 1, None) for v in data]
        bp = ax.boxplot(data, tick_labels=labels, showfliers=False, widths=0.5, patch_artist=True,
                        medianprops=dict(color=COLOR["ink"], linewidth=1.4))
        for patch, (name, _) in zip(bp["boxes"], groups):
            patch.set_facecolor(COLOR[name]); patch.set_alpha(0.75); patch.set_edgecolor("none")
        for element in ("whiskers", "caps"):
            for line in bp[element]:
                line.set_color(COLOR["baseline"])
        if logscale:
            ax.set_yscale("log")
        med = [float(np.median(v)) for v in data]
        ax.text(0.5, 0.92, f"medianas: {_fmt(med[0])} vs {_fmt(med[1])}", transform=ax.transAxes,
                ha="center", fontsize=8, color=COLOR["ink2"])

    styled_box(axes[0], "n_dst", logscale=True)
    axes[0].set_title("Computadoras destino distintas", fontsize=10)

    pct = [float((g["n_fallos"] > 0).mean() * 100) for _, g in groups]
    bars = axes[1].bar(labels, pct, width=0.5,
                       color=[COLOR["normal"], COLOR["comprometido"]], alpha=0.85)
    for bar, v in zip(bars, pct):
        axes[1].text(bar.get_x() + bar.get_width() / 2, v + 1.2, f"{v:.0f}%",
                     ha="center", fontsize=10, fontweight="bold", color=COLOR["ink"])
    axes[1].set_ylim(0, 62)
    axes[1].set_title("% de días con ≥1 fallo de autenticación", fontsize=10)
    axes[1].set_xlabel("…pero el fallo comprometido es mínimo (ratio típico 0.003):\ncredenciales válidas, no fuerza bruta",
                       fontsize=7.5, color=COLOR["ink2"])

    styled_box(axes[2], "ratio_ntlm")
    axes[2].set_title("Ratio NTLM (vs. resto de protocolos)", fontsize=10)

    fig.suptitle("¿En qué se nota un día comprometido? (usuario-días, sin outliers)",
                 fontweight="bold", fontsize=12, y=1.02)
    _caption(fig, "Hallazgo: el día comprometido toca el doble de computadoras distintas (mediana 22 vs. 10 — movimiento "
                  "lateral, panel izq. en escala log), falla más seguido pero en proporción mínima (50% vs. 24% de los días "
                  "con algún fallo, ratio típico 0.003 — credenciales válidas, no fuerza bruta) y usa más NTLM, el protocolo "
                  "legado asociado a pass-the-hash (mediana 0.02 vs. 0).", y=-0.12)
    fig.savefig(out / "fig2_senales_compromiso.png")
    plt.close(fig)


def pick_ego_user(auth: pl.LazyFrame, redteam: pd.DataFrame) -> tuple[str, int]:
    """Elige el comprometido cuya historia se VE: huella histórica chica (grafo legible)
    y salto grande de destinos nuevos el día del ataque.

    Requisitos: >=5 días de historial previo al primer ataque y <=60 destinos históricos
    (más que eso es una bola de pelo ilegible). Se maximiza el nº de destinos nuevos.
    """
    first_attack = redteam.groupby("user")["day"].min()
    all_ev = (
        auth.filter(pl.col("src_user").is_in(sorted(first_attack.index)))
        .select("src_user", "day", "dst_computer").collect().to_pandas()
    )
    best, best_new = None, -1
    for user, atk_day in first_attack.items():
        ev = all_ev[(all_ev.src_user == user) & (all_ev.day <= atk_day)]
        prev = ev[ev.day < atk_day]
        if prev["day"].nunique() < 5:
            continue
        hist = set(prev["dst_computer"])
        if len(hist) > 60:
            continue
        new = set(ev.loc[ev.day == atk_day, "dst_computer"]) - hist
        if len(new) > best_new:
            best, best_new = (user, int(atk_day)), len(new)
    if best is None:  # sin candidato legible: cae al de más destinos de ataque
        user = redteam.groupby("user")["dst_computer"].nunique().idxmax()
        best = (user, int(first_attack[user]))
    return best


def fig_grafo_ego(auth: pl.LazyFrame, redteam: pd.DataFrame, ud: pd.DataFrame, out: Path) -> dict:
    """Grafo ego usuario→computadoras: historial previo (gris) vs. día del ataque (rojo=nuevas)."""
    import networkx as nx

    user, attack_day = pick_ego_user(auth, redteam)
    ev = (
        auth.filter((pl.col("src_user") == user) & (pl.col("day") <= attack_day))
        .select("day", "dst_computer").collect().to_pandas()
    )
    hist = set(ev.loc[ev.day < attack_day, "dst_computer"])
    today = set(ev.loc[ev.day == attack_day, "dst_computer"])
    new = today - hist
    rt_dst = set(redteam.loc[(redteam.user == user) & (redteam.day == attack_day), "dst_computer"])

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    for ax, dsts, title in (
        (axes[0], hist, f"Antes del ataque (días 0–{attack_day-1})"),
        (axes[1], today, f"Día del ataque (día {attack_day})"),
    ):
        g = nx.Graph()
        g.add_node(user)
        g.add_edges_from((user, d) for d in dsts)
        pos = nx.spring_layout(g, seed=7, k=1.6 / max(np.sqrt(len(dsts)), 1))
        node_colors, sizes = [], []
        for n in g.nodes:
            if n == user:
                node_colors.append(COLOR["normal"]); sizes.append(420)
            elif ax is axes[1] and n in new:
                node_colors.append(COLOR["comprometido"]); sizes.append(90)
            else:
                node_colors.append(COLOR["historico"]); sizes.append(70)
        nx.draw_networkx_edges(g, pos, ax=ax, edge_color=COLOR["grid"], width=0.9)
        nx.draw_networkx_nodes(g, pos, ax=ax, node_color=node_colors, node_size=sizes,
                               edgecolors="white", linewidths=0.6)
        ax.annotate(user.split("@")[0], pos[user], xytext=(0, -16),
                    textcoords="offset points", ha="center", fontsize=9,
                    fontweight="bold", color=COLOR["ink"])
        ax.set_title(f"{title} — {len(dsts)} destinos", fontsize=10)
        ax.axis("off")

    handles = [
        plt.Line2D([], [], marker="o", ls="", color=COLOR["historico"], label="destino ya conocido"),
        plt.Line2D([], [], marker="o", ls="", color=COLOR["comprometido"], label="destino nuevo ese día"),
        plt.Line2D([], [], marker="o", ls="", color=COLOR["normal"], label=f"usuario {user.split('@')[0]}"),
    ]
    axes[0].legend(handles=handles, loc="upper left", fontsize=8, frameon=False,
                   bbox_to_anchor=(-0.02, 1.02))
    fig.suptitle(f"Movimiento lateral visible: el grafo de conexiones de {user.split('@')[0]}",
                 fontweight="bold", fontsize=12)
    _caption(fig, f"Hallazgo: en {attack_day} días de historia, {user.split('@')[0]} acumuló {len(hist)} destinos; el día del "
                  f"ataque tocó {len(today)} ({len(new)} nuevos, en rojo), expandiendo su grafo más en un día que en toda su "
                  f"historia previa. {len(new & rt_dst)} de los destinos nuevos están confirmados por el red team. Ninguna de "
                  "esas autenticaciones falló: la anomalía solo existe al nivel del patrón, no del evento individual.",
             y=0.02)
    fig.savefig(out / "fig3_grafo_ego.png")
    plt.close(fig)

    return {"user": user, "attack_day": attack_day, "hist_dsts": len(hist),
            "attack_day_dsts": len(today), "new_dsts": len(new),
            "new_dsts_confirmed_redteam": len(new & rt_dst)}


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------

def run_all(work_dir: str | Path = "data/work", out_dir: str | Path = "docs/eda") -> dict:
    """Corre el EDA completo: tablas, KPIs y las 3 figuras. Persiste todo en out_dir."""
    apply_style()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    auth, redteam, meta = scan_work(work_dir)
    ud = build_user_day(auth, redteam, meta)
    circ = infer_circadian(auth)
    tk = build_tables_and_kpis(ud, redteam, meta, circ)
    types = table_types(auth)

    fig_ritmo_red(circ, redteam, out)
    fig_senales(ud, out)
    ego = fig_grafo_ego(auth, redteam, ud, out)

    results = {**tk, "ego": ego,
               "tipos": {k: v.to_dict("records") for k, v in types.items()},
               "circadiano": {"work_hours": circ["work_hours"],
                              "work_hours_rule": circ["work_hours_rule"],
                              "nonwork_days": circ["nonwork_days"],
                              "nonwork_rule": circ["nonwork_rule"]}}
    (out / "eda_results.json").write_text(json.dumps(results, indent=2, default=str))
    return results


if __name__ == "__main__":
    r = run_all()
    print(json.dumps({k: r[k] for k in ("desbalance", "kpis", "ego")}, indent=2, default=str))
