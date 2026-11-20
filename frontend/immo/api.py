"""Client HTTP de l'API Immo Loiret.

Expose des fonctions qui renvoient des DataFrames ou des dicts prêts pour les
figures. Chaque réponse est mise en cache côté serveur Dash (flask-caching),
avec une clé qui inclut le chemin et tous les paramètres de la requête.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd
import requests

from immo import config as cfg
from immo.cache import cache


class ApiError(RuntimeError):
    """L'API a répondu une erreur ou n'est pas joignable."""


@dataclass(frozen=True)
class Filtres:
    """Filtres globaux (issus du dcc.Store « filters-store »)."""

    zone: str
    annee_min: int
    annee_max: int
    prix_min: float
    prix_max: float
    surf_min: float
    surf_max: float
    pm2_min: float
    pm2_max: float

    @classmethod
    def from_store(cls, store: dict | None) -> "Filtres":
        s = {**cfg.FILTRES_DEFAUT, **(store or {})}
        return cls(
            zone=s["zone"],
            annee_min=int(s["annees"][0]),
            annee_max=int(s["annees"][1]),
            prix_min=float(s["prix"][0]),
            prix_max=float(s["prix"][1]),
            surf_min=float(s["surface"][0]),
            surf_max=float(s["surface"][1]),
            pm2_min=float(s["prix_m2"][0]),
            pm2_max=float(s["prix_m2"][1]),
        )

    def params(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Transport
# --------------------------------------------------------------------------- #
@cache.memoize()
def _get(path: str, params: tuple) -> object:
    url = f"{cfg.API_URL}{path}"
    try:
        r = requests.get(url, params=dict(params), timeout=cfg.API_TIMEOUT)
    except requests.RequestException as exc:
        raise ApiError(f"API injoignable ({url}) : {exc}") from exc
    if r.status_code >= 400:
        raise ApiError(f"API {r.status_code} sur {path} : {r.text[:300]}")
    return r.json()


def get(path: str, f: Filtres | None = None, **params):
    tous = {**(f.params() if f else {}), **{k: v for k, v in params.items() if v is not None}}
    return _get(path, tuple(sorted(tous.items())))


def _df(rows: list[dict], colonnes: list[str]) -> pd.DataFrame:
    """Toujours les mêmes colonnes, même sans ligne (filtres trop serrés)."""
    return pd.DataFrame(rows, columns=colonnes) if not rows else pd.DataFrame(rows)


AGG = ["n", "pm2_med", "prix_med", "surf_med", "fiable"]


# --------------------------------------------------------------------------- #
# Référentiel
# --------------------------------------------------------------------------- #
def meta() -> dict:
    return get("/meta")


def communes_index() -> pd.DataFrame:
    return _df(get("/communes"), ["code_commune", "nom_commune", "metropole"])


def geojson_zone(zone: str) -> dict:
    return get("/geo/communes", zone=zone)


# --------------------------------------------------------------------------- #
# Statistiques de zone
# --------------------------------------------------------------------------- #
def kpis(f: Filtres) -> dict:
    return get("/stats/kpis", f)


def stats_communes(f: Filtres, type_: str) -> pd.DataFrame:
    return _df(get("/stats/communes", f, type=type_), ["code_commune", "nom_commune", *AGG])


def stats_communes_comparees(f: Filtres) -> pd.DataFrame:
    cols = ["code_commune", "nom_commune"]
    for suffixe in ("_maison", "_appart"):
        cols += [c + suffixe for c in AGG]
    return _df(get("/stats/communes/comparees", f), [*cols, "n_total"])


def stats_annuelles(f: Filtres) -> pd.DataFrame:
    return _df(get("/stats/annuelles", f), ["annee", "type", *AGG])


def stats_trimestrielles(f: Filtres) -> pd.DataFrame:
    cols = ["annee", "trimestre", "type", "n", "pm2_med", "label", "ordre"]
    return _df(get("/stats/trimestrielles", f), cols)


def evolution_globale(f: Filtres) -> dict:
    return get("/stats/evolution", f)


def evolution_communes(f: Filtres, type_: str) -> pd.DataFrame:
    cols = ["code_commune", "nom_commune", "n_avant", "pm2_med_avant", "n_apres"]
    cols += ["pm2_med_apres", "var", "fiable"]
    return _df(get("/stats/evolution/communes", f, type=type_), cols)


def budget_communes(
    f: Filtres, type_: str, prix_max_bien: float, surf_min: float, pieces_min: int
) -> pd.DataFrame:
    rows = get(
        "/budget/communes",
        f,
        type=type_,
        prix_max_bien=round(prix_max_bien, 2),
        surf_min=surf_min,
        pieces_min=pieces_min,
    )
    cols = ["code_commune", "nom_commune", *AGG, "n_sous_budget", "part_sous_budget"]
    return _df(rows, [*cols, "dans_budget"])


# --------------------------------------------------------------------------- #
# Fiche commune
# --------------------------------------------------------------------------- #
def resume_commune(f: Filtres, code: str) -> dict:
    return get(f"/communes/{code}/resume", f)


def stats_quartiers(f: Filtres, code: str, type_: str | None) -> pd.DataFrame:
    rows = get(f"/communes/{code}/quartiers", f, type=type_)
    return _df(rows, ["code_iris", "nom_quartier", *AGG])


def quartiers_geo(code: str) -> dict:
    return get(f"/communes/{code}/quartiers/geo")


def annuel_commune(f: Filtres, code: str) -> pd.DataFrame:
    return _df(get(f"/communes/{code}/annuel", f), ["annee", "type", *AGG])


COLONNES_VENTES = [
    "id_mutation",
    "date",
    "type",
    "code_iris",
    "nom_quartier",
    "section",
    "valeur_fonciere",
    "surface_reelle_bati",
    "nombre_pieces_principales",
    "prix_m2",
    "surface_terrain",
    "latitude",
    "longitude",
]


def ventes_commune(
    f: Filtres,
    code: str,
    type_: str | None = None,
    section: str | None = None,
    quartier: str | None = None,
    geo: bool = False,
    limit: int | None = None,
) -> tuple[int, pd.DataFrame]:
    """(nombre total de ventes, ventes les plus récentes d'abord)."""
    res = get(
        f"/communes/{code}/ventes",
        f,
        type=type_,
        section=section,
        quartier=quartier,
        geo=geo or None,
        limit=limit,
    )
    df = _df(res["ventes"], COLONNES_VENTES)
    df["date_mutation"] = pd.to_datetime(df["date"])
    return res["total"], df


def comparables_stats(f: Filtres, code: str, type_: str, surface: float, exclure: str) -> dict:
    return get(f"/communes/{code}/comparables", f, type=type_, surface=surface, exclure=exclure)
