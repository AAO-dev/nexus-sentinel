"""Features de grafo usuario→computadora (Fase 3, sección 4.5 del plan — nuevas en v2).

Qué resuelven que los otros niveles no pueden: un atacante puede mantener su VOLUMEN dentro de lo
normal (pocas autenticaciones, sin fallos, en horario laboral) y aun así necesita tocar máquinas
que la cuenta jamás tocó — el movimiento lateral es, por definición, novedad de conexiones. El EDA
lo confirmó (U3635: 28 destinos nuevos el día del ataque). Estas features miden esa novedad de
forma sistemática.

REGLA ANTI-FUGA ESTRICTA: el grafo de referencia del día D se congela al final del día D-1.
La implementación itera los días en orden y, para cada día, PRIMERO calcula las features contra el
estado acumulado y DESPUÉS incorpora los eventos del día al estado. El día evaluado jamás está
dentro de su propio grafo de referencia.

Implementación con dicts/sets sobre pares distintos (user, day, computadora) — el grafo bipartito
completo en networkx sería más lento sin aportar nada aquí; networkx se reserva para la
visualización (EDA/UI).
"""

from __future__ import annotations

import pandas as pd
import polars as pl


def _distinct_pairs(auth_lf: pl.LazyFrame, users: list[str], col: str) -> pd.DataFrame:
    """Pares distintos (src_user, day, col) de los eventos originados por los usuarios."""
    return (
        auth_lf.filter(pl.col("src_user").is_in(users))
        .select("src_user", "day", col)
        .unique()
        .sort("day")
        .collect()
        .to_pandas()
    )


def add_graph_features(
    ud: pd.DataFrame, auth_lf: pl.LazyFrame, sampled_users: set[str]
) -> pd.DataFrame:
    """Añade a la tabla usuario-día las 4 features de novedad de la sección 4.5:

    - n_aristas_nuevas: computadoras destino que el usuario JAMÁS había tocado (hasta D-1).
    - ratio_aristas_nuevas: nuevas / destinos_del_día — separa "un servidor nuevo" (rutina)
      de "casi todo lo que tocó hoy es nuevo" (expansión).
    - rareza_media_destinos: promedio de 1/(1 + nº de usuarios distintos que habían tocado el
      destino hasta D-1) — tocar el file server común no es como tocar un servidor que casi
      nadie visita; un destino jamás visto por nadie vale 1.0.
    - n_src_computers_nuevas: máquinas ORIGEN nuevas — autenticarse desde equipos ajenos es la
      otra cara del movimiento lateral (la credencial viaja a máquinas donde nunca vivió).
    """
    users = sorted(sampled_users)
    pares_dst = _distinct_pairs(auth_lf, users, "dst_computer")
    pares_src = _distinct_pairs(auth_lf, users, "src_computer")

    vistos_dst: dict[str, set] = {}     # user -> destinos tocados hasta D-1
    vistos_src: dict[str, set] = {}     # user -> orígenes usados hasta D-1
    popularidad: dict[str, set] = {}    # dst -> usuarios distintos que lo tocaron hasta D-1

    filas = []
    grupos_dst = {d: g for d, g in pares_dst.groupby("day", sort=True)}
    grupos_src = {d: g for d, g in pares_src.groupby("day", sort=True)}

    for day in sorted(grupos_dst):
        g_dst = grupos_dst[day].groupby("src_user")["dst_computer"].agg(set)
        g_src = grupos_src.get(day)
        g_src = g_src.groupby("src_user")["src_computer"].agg(set) if g_src is not None else {}

        # 1) features del día contra el estado congelado a D-1
        for user, dsts in g_dst.items():
            previos = vistos_dst.get(user, set())
            nuevas = dsts - previos
            rareza = sum(1.0 / (1 + len(popularidad.get(d, ()))) for d in dsts) / len(dsts)
            srcs = g_src.get(user, set()) if len(g_src) else set()
            src_nuevas = srcs - vistos_src.get(user, set())
            filas.append((user, day, len(nuevas), len(nuevas) / len(dsts), rareza, len(src_nuevas)))

        # 2) SOLO DESPUÉS se incorpora el día al estado (regla D-1)
        for user, dsts in g_dst.items():
            vistos_dst.setdefault(user, set()).update(dsts)
            for d in dsts:
                popularidad.setdefault(d, set()).add(user)
        for user, srcs in (g_src.items() if len(g_src) else ()):
            vistos_src.setdefault(user, set()).update(srcs)

    graf = pd.DataFrame(
        filas,
        columns=["src_user", "day", "n_aristas_nuevas", "ratio_aristas_nuevas",
                 "rareza_media_destinos", "n_src_computers_nuevas"],
    )
    ud = ud.merge(graf, on=["src_user", "day"], how="left")

    # el primer día activo de un usuario todo es "nuevo" por construcción, no por conducta:
    # se neutraliza igual que las desviaciones sin historial (flag historial_corto ya existe)
    primer_dia = ud["historial_dias"] == 0
    ud.loc[primer_dia, ["n_aristas_nuevas", "ratio_aristas_nuevas", "n_src_computers_nuevas"]] = 0
    ud.loc[primer_dia, "rareza_media_destinos"] = 0.0
    return ud
