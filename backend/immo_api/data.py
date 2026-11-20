"""Accès aux données DVF : chargement, filtres et agrégats (médianes).

Les fonctions coûteuses sont mémoïsées (functools.lru_cache) : la clé de cache
est faite des arguments, dont les filtres (dataclass figée, donc hashable).
Les résultats en cache sont partagés entre requêtes : ne jamais les modifier
sur place (utiliser .assign / des copies).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

import pandas as pd

from immo_api.config import (
    BORNES,
    GEOJSON_FILE,
    METROPOLE_EPCI,
    PERIODE_APRES,
    PERIODE_AVANT,
    SALES_FILE,
    SEUIL_FIABILITE,
)

COLONNES = [
    "id_mutation",
    "date_mutation",
    "annee",
    "valeur_fonciere",
    "type",
    "surface_reelle_bati",
    "nombre_pieces_principales",
    "prix_m2",
    "surface_terrain",
    "code_commune",
    "nom_commune",
    "section",
    "longitude",
    "latitude",
]


@dataclass(frozen=True)
class Filtres:
    """Filtres globaux choisis par l'utilisateur (hashables pour le cache)."""

    zone: str = "metropole"
    annee_min: int = BORNES["annees"][0]
    annee_max: int = BORNES["annees"][1]
    prix_min: float = BORNES["prix"][0]
    prix_max: float = BORNES["prix"][1]
    surf_min: float = BORNES["surface"][0]
    surf_max: float = BORNES["surface"][1]
    pm2_min: float = BORNES["prix_m2"][0]
    pm2_max: float = BORNES["prix_m2"][1]


# --------------------------------------------------------------------------- #
# Chargement
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def load_sales() -> pd.DataFrame:
    df = pd.read_parquet(SALES_FILE, columns=COLONNES)
    df["type"] = df["type"].astype("category")
    return df


@lru_cache(maxsize=1)
def load_geojson() -> dict:
    return json.loads(GEOJSON_FILE.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def metropole_codes() -> frozenset[str]:
    return frozenset(
        f["properties"]["code"]
        for f in load_geojson()["features"]
        if f["properties"].get("codeEpci") == METROPOLE_EPCI
    )


@lru_cache(maxsize=4)
def geojson_zone(zone: str) -> dict:
    geo = load_geojson()
    if zone != "metropole":
        return geo
    codes = metropole_codes()
    return {
        "type": "FeatureCollection",
        "features": [f for f in geo["features"] if f["properties"]["code"] in codes],
    }


@lru_cache(maxsize=1)
def communes_index() -> pd.DataFrame:
    """Code -> nom de toutes les communes ayant au moins une vente."""
    df = load_sales()
    idx = df.groupby("code_commune", observed=True)["nom_commune"].first()
    out = idx.reset_index()
    out["metropole"] = out["code_commune"].isin(metropole_codes())
    return out.sort_values("nom_commune")


# --------------------------------------------------------------------------- #
# Filtres
# --------------------------------------------------------------------------- #
def _filtrer_hors_annees(df: pd.DataFrame, f: Filtres) -> pd.DataFrame:
    mask = (
        df["valeur_fonciere"].between(f.prix_min, f.prix_max)
        & df["surface_reelle_bati"].between(f.surf_min, f.surf_max)
        & df["prix_m2"].between(f.pm2_min, f.pm2_max)
    )
    if f.zone == "metropole":
        mask &= df["code_commune"].isin(metropole_codes())
    return df[mask]


@lru_cache(maxsize=256)
def ventes(f: Filtres) -> pd.DataFrame:
    """Ventes après filtres globaux (zone, années, prix, surface, €/m²)."""
    df = _filtrer_hors_annees(load_sales(), f)
    return df[df["annee"].between(f.annee_min, f.annee_max)]


@lru_cache(maxsize=256)
def ventes_toutes_annees(f: Filtres) -> pd.DataFrame:
    """Comme `ventes` mais sans le filtre d'années (pour les tendances)."""
    return _filtrer_hors_annees(load_sales(), f)


# --------------------------------------------------------------------------- #
# Agrégats
# --------------------------------------------------------------------------- #
def _agg(g) -> pd.DataFrame:
    out = g.agg(
        n=("prix_m2", "size"),
        pm2_med=("prix_m2", "median"),
        prix_med=("valeur_fonciere", "median"),
        surf_med=("surface_reelle_bati", "median"),
    )
    out["fiable"] = out["n"] >= SEUIL_FIABILITE
    return out


@lru_cache(maxsize=256)
def kpis(f: Filtres) -> dict:
    df = ventes(f)
    res = {"n": len(df), "n_communes": df["code_commune"].nunique()}
    for t in ("Maison", "Appartement"):
        d = df[df["type"] == t]
        res[t] = {
            "n": len(d),
            "pm2_med": d["prix_m2"].median() if len(d) else None,
            "prix_med": d["valeur_fonciere"].median() if len(d) else None,
            "surf_med": d["surface_reelle_bati"].median() if len(d) else None,
        }
    return res


@lru_cache(maxsize=256)
def stats_communes(f: Filtres, type_: str) -> pd.DataFrame:
    df = ventes(f)
    df = df[df["type"] == type_]
    out = _agg(df.groupby(["code_commune", "nom_commune"], observed=True))
    return out.reset_index().sort_values("pm2_med")


@lru_cache(maxsize=256)
def stats_communes_comparees(f: Filtres) -> pd.DataFrame:
    """Une ligne par commune : maisons et appartements côte à côte."""
    m = stats_communes(f, "Maison").set_index(["code_commune", "nom_commune"])
    a = stats_communes(f, "Appartement").set_index(["code_commune", "nom_commune"])
    out = m.join(a, how="outer", lsuffix="_maison", rsuffix="_appart").reset_index()
    for c in ("n_maison", "n_appart"):
        out[c] = out[c].fillna(0).astype(int)
    out["n_total"] = out["n_maison"] + out["n_appart"]
    for c in ("fiable_maison", "fiable_appart"):
        out[c] = out[c].eq(True)
    return out.sort_values("n_total", ascending=False)


@lru_cache(maxsize=256)
def stats_annuelles(f: Filtres) -> pd.DataFrame:
    df = ventes_toutes_annees(f)
    return _agg(df.groupby(["annee", "type"], observed=True)).reset_index()


@lru_cache(maxsize=256)
def stats_trimestrielles(f: Filtres) -> pd.DataFrame:
    """Médiane glissante sur 12 mois (4 trimestres), calculée à chaque trimestre.

    Une médiane trimestrielle brute est bruitée ; la fenêtre de 12 mois
    lisse la saisonnalité sans masquer les retournements.
    """
    df = ventes_toutes_annees(f)
    idx = (df["annee"] - 2021) * 4 + df["date_mutation"].dt.quarter - 1
    df = df.assign(_q=idx)
    lignes = []
    for q in range(3, int(idx.max()) + 1 if len(idx) else 0):
        fen = df[df["_q"].between(q - 3, q)]
        annee, trimestre = 2021 + q // 4, q % 4 + 1
        for t, d in fen.groupby("type", observed=True):
            lignes.append(
                {
                    "annee": annee,
                    "trimestre": trimestre,
                    "type": t,
                    "n": len(d),
                    "pm2_med": d["prix_m2"].median(),
                    "label": f"T{trimestre} {annee}",
                    "ordre": annee * 10 + trimestre,
                }
            )
    return pd.DataFrame(
        lignes, columns=["annee", "trimestre", "type", "n", "pm2_med", "label", "ordre"]
    )


def _periode(df: pd.DataFrame, periode: tuple[int, int]) -> pd.DataFrame:
    return df[df["annee"].between(*periode)]


@lru_cache(maxsize=256)
def evolution_globale(f: Filtres) -> dict:
    """Variation du €/m² médian et du nombre de ventes annuel, avant/après 2022."""
    df = ventes_toutes_annees(f)
    av, ap = _periode(df, PERIODE_AVANT), _periode(df, PERIODE_APRES)
    n_annees_av = PERIODE_AVANT[1] - PERIODE_AVANT[0] + 1
    n_annees_ap = PERIODE_APRES[1] - PERIODE_APRES[0] + 1
    res = {}
    for t in ("Maison", "Appartement"):
        a, b = av[av["type"] == t], ap[ap["type"] == t]
        if len(a) == 0 or len(b) == 0:
            res[t] = None
            continue
        pa, pb = a["prix_m2"].median(), b["prix_m2"].median()
        va, vb = len(a) / n_annees_av, len(b) / n_annees_ap
        res[t] = {
            "pm2_avant": pa,
            "pm2_apres": pb,
            "pm2_var": pb / pa - 1,
            "ventes_an_avant": va,
            "ventes_an_apres": vb,
            "ventes_var": vb / va - 1,
        }
    return res


@lru_cache(maxsize=256)
def evolution_communes(f: Filtres, type_: str) -> pd.DataFrame:
    df = ventes_toutes_annees(f)
    df = df[df["type"] == type_]
    keys = ["code_commune", "nom_commune"]
    a = _agg(_periode(df, PERIODE_AVANT).groupby(keys, observed=True))
    b = _agg(_periode(df, PERIODE_APRES).groupby(keys, observed=True))
    out = a[["n", "pm2_med"]].join(
        b[["n", "pm2_med"]], how="inner", lsuffix="_avant", rsuffix="_apres"
    )
    out["var"] = out["pm2_med_apres"] / out["pm2_med_avant"] - 1
    out["fiable"] = (out["n_avant"] >= SEUIL_FIABILITE) & (out["n_apres"] >= SEUIL_FIABILITE)
    return out.reset_index().sort_values("var")


@lru_cache(maxsize=256)
def budget_communes(
    f: Filtres, type_: str, prix_max_bien: float, surf_min: float, pieces_min: int
) -> pd.DataFrame:
    """Par commune : biens comparables au projet et part vendue dans le budget.

    Comparables = même type, surface >= surf_min, pièces >= pieces_min.
    Une commune est « dans le budget » si le prix médian des comparables
    est inférieur ou égal au prix maximum du bien.
    """
    df = ventes(f)
    df = df[
        (df["type"] == type_)
        & (df["surface_reelle_bati"] >= surf_min)
        & (df["nombre_pieces_principales"] >= pieces_min)
    ]
    df = df.assign(sous_budget=df["valeur_fonciere"] <= prix_max_bien)
    g = df.groupby(["code_commune", "nom_commune"], observed=True)
    out = _agg(g)
    out["n_sous_budget"] = g["sous_budget"].sum().astype(int)
    out["part_sous_budget"] = out["n_sous_budget"] / out["n"]
    out["dans_budget"] = out["prix_med"] <= prix_max_bien
    out = out.reset_index()
    return out.sort_values(["fiable", "part_sous_budget", "n_sous_budget"], ascending=False)


@lru_cache(maxsize=256)
def stats_sections(f: Filtres, code_commune: str, type_: str | None) -> pd.DataFrame:
    df = ventes(f)
    df = df[df["code_commune"] == code_commune]
    if type_:
        df = df[df["type"] == type_]
    out = _agg(df.groupby("section", observed=True)).reset_index()
    return out.sort_values("pm2_med")


@lru_cache(maxsize=256)
def ventes_commune(f: Filtres, code_commune: str) -> pd.DataFrame:
    df = ventes(f)
    return df[df["code_commune"] == code_commune]


@lru_cache(maxsize=256)
def comparables(
    f: Filtres, code_commune: str, type_: str, surface: float, exclure: str
) -> pd.DataFrame:
    """Ventes comparables : même commune, même type, surface à ±20 %."""
    df = ventes_commune(f, code_commune)
    return df[
        (df["type"] == type_)
        & df["surface_reelle_bati"].between(surface * 0.8, surface * 1.2)
        & (df["id_mutation"] != exclure)
    ]


# --------------------------------------------------------------------------- #
# Fiche commune
# --------------------------------------------------------------------------- #
def _par_type(df: pd.DataFrame) -> dict:
    out = {}
    for t in ("Maison", "Appartement"):
        d = df[df["type"] == t]
        out[t] = {
            "n": len(d),
            "pm2_med": d["prix_m2"].median() if len(d) else None,
            "prix_med": d["valeur_fonciere"].median() if len(d) else None,
            "surf_med": d["surface_reelle_bati"].median() if len(d) else None,
            "fiable": len(d) >= SEUIL_FIABILITE,
        }
    return out


@lru_cache(maxsize=256)
def resume_commune(f: Filtres, code_commune: str) -> dict:
    df = ventes_commune(f, code_commune)
    return {
        "code_commune": code_commune,
        "n": len(df),
        "n_sections": int(df["section"].nunique()),
        **_par_type(df),
    }


@lru_cache(maxsize=256)
def annuel_commune(f: Filtres, code_commune: str) -> pd.DataFrame:
    df = ventes_commune(f, code_commune)
    out = _agg(df.groupby(["annee", "type"], observed=True)).reset_index()
    return out.sort_values(["type", "annee"])


@lru_cache(maxsize=256)
def comparables_stats(
    f: Filtres, code_commune: str, type_: str, surface: float, exclure: str
) -> dict:
    """Médiane et quartiles du €/m² des ventes comparables (surface ±20 %)."""
    d = comparables(f, code_commune, type_, surface, exclure)
    if d.empty:
        return {"n": 0, "pm2_med": None, "pm2_q1": None, "pm2_q3": None}
    q1, med, q3 = d["prix_m2"].quantile([0.25, 0.5, 0.75])
    return {
        "n": len(d),
        "pm2_med": med,
        "pm2_q1": q1,
        "pm2_q3": q3,
        "surf_min": surface * 0.8,
        "surf_max": surface * 1.2,
    }
