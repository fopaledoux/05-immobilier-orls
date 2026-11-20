"""API Immo Loiret : prix médians des ventes DVF du Loiret (2021 - juin 2026).

Lancer en local : `uv run uvicorn immo_api.main:app --reload --port 8000`
Documentation interactive : http://localhost:8000/docs
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Annotated, Literal

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from immo_api import data
from immo_api.config import (
    ANNEE_PARTIELLE,
    BORNES,
    FILTRES_DEFAUT,
    PERIODE_APRES,
    PERIODE_AVANT,
    SEUIL_FIABILITE,
    TAUX_FRAIS_NOTAIRE,
    TYPES,
    ZONES,
)
from immo_api.data import Filtres
from immo_api.geo import GeocodageIndisponible, geocoder

app = FastAPI(
    title="Immo Loiret API",
    version="1.0.0",
    description=(
        "Prix médians des ventes de logements dans le Loiret (DVF 2021 - juin 2026, DGFiP). "
        f"Toutes les médianes sont accompagnées du nombre de ventes ; en dessous de "
        f"{SEUIL_FIABILITE} ventes, `fiable` vaut `false`."
    ),
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o],
    allow_methods=["GET"],
    allow_headers=["*"],
)

Zone = Literal["metropole", "loiret"]
TypeBien = Literal["Maison", "Appartement"]
CodeCommune = Annotated[str, Path(pattern=r"^\d[\dAB]\d{3}$", examples=["45234"])]


# --------------------------------------------------------------------------- #
# Utilitaires
# --------------------------------------------------------------------------- #
def filtres(
    zone: Zone = "metropole",
    annee_min: Annotated[int, Query(ge=BORNES["annees"][0], le=BORNES["annees"][1])] = BORNES[
        "annees"
    ][0],
    annee_max: Annotated[int, Query(ge=BORNES["annees"][0], le=BORNES["annees"][1])] = BORNES[
        "annees"
    ][1],
    prix_min: Annotated[float, Query(ge=0)] = BORNES["prix"][0],
    prix_max: Annotated[float, Query(gt=0)] = BORNES["prix"][1],
    surf_min: Annotated[float, Query(ge=0)] = BORNES["surface"][0],
    surf_max: Annotated[float, Query(gt=0)] = BORNES["surface"][1],
    pm2_min: Annotated[float, Query(ge=0)] = BORNES["prix_m2"][0],
    pm2_max: Annotated[float, Query(gt=0)] = BORNES["prix_m2"][1],
) -> Filtres:
    """Filtres globaux, communs à presque tous les endpoints."""
    if annee_min > annee_max or prix_min > prix_max or surf_min > surf_max or pm2_min > pm2_max:
        raise HTTPException(422, "Chaque borne minimale doit être inférieure à la maximale.")
    return Filtres(
        zone, annee_min, annee_max, prix_min, prix_max, surf_min, surf_max, pm2_min, pm2_max
    )


FiltresDep = Annotated[Filtres, Depends(filtres)]


@dataclass(frozen=True)
class Autour:
    lat: float
    lon: float
    rayon: float


def autour_param(
    lat: Annotated[float | None, Query(ge=46.5, le=48.5, description="Latitude du point")] = None,
    lon: Annotated[float | None, Query(ge=0.5, le=3.5, description="Longitude du point")] = None,
    rayon: Annotated[float, Query(ge=50, le=3000, description="Rayon en mètres")] = 500,
) -> Autour | None:
    """Point (adresse géocodée) et rayon de recherche, facultatifs."""
    if lat is None and lon is None:
        return None
    if lat is None or lon is None:
        raise HTTPException(422, "lat et lon vont ensemble.")
    return Autour(round(lat, 6), round(lon, 6), rayon)


def records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> liste de dicts JSON (NaN -> null, types numpy -> natifs)."""
    return json.loads(df.to_json(orient="records", date_format="iso", force_ascii=False))


def propre(obj):
    """Convertit récursivement NaN et types numpy en valeurs JSON valides."""
    if isinstance(obj, dict):
        return {k: propre(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [propre(v) for v in obj]
    if hasattr(obj, "item"):  # scalaires numpy
        obj = obj.item()
    if isinstance(obj, float) and math.isnan(obj):
        return None
    return obj


def commune_connue(code: str) -> str:
    idx = data.communes_index()
    if not (idx["code_commune"] == code).any():
        raise HTTPException(404, f"Aucune vente pour la commune {code}.")
    return code


# --------------------------------------------------------------------------- #
# Référentiel
# --------------------------------------------------------------------------- #
@app.get("/health", tags=["référentiel"])
def health():
    return {"status": "ok"}


@app.get("/meta", tags=["référentiel"], summary="Constantes métier et bornes des filtres")
def meta():
    return {
        "seuil_fiabilite": SEUIL_FIABILITE,
        "taux_frais_notaire": TAUX_FRAIS_NOTAIRE,
        "periode_avant": list(PERIODE_AVANT),
        "periode_apres": list(PERIODE_APRES),
        "types": list(TYPES),
        "bornes": {k: list(v) for k, v in BORNES.items()},
        "filtres_defaut": FILTRES_DEFAUT,
        "zones": ZONES,
        "annee_partielle": ANNEE_PARTIELLE,
        "source": "DGFiP, DVF (2021-2025 : Etalab, géolocalisées ; 2026 S1 : DGFiP, brutes), "
        "Licence Ouverte 2.0",
    }


@app.get("/communes", tags=["référentiel"], summary="Communes ayant au moins une vente")
def communes():
    return records(data.communes_index())


@app.get("/geo/communes", tags=["référentiel"], summary="Contours des communes (GeoJSON)")
def geo_communes(zone: Zone = "metropole"):
    return data.geojson_zone(zone)


# --------------------------------------------------------------------------- #
# Statistiques de zone
# --------------------------------------------------------------------------- #
@app.get("/stats/kpis", tags=["statistiques"], summary="Chiffres clés de la zone")
def kpis(f: FiltresDep):
    return propre(data.kpis(f))


@app.get("/stats/communes", tags=["statistiques"], summary="Médianes par commune pour un type")
def stats_communes(f: FiltresDep, type: TypeBien = "Maison"):
    return records(data.stats_communes(f, type))


@app.get(
    "/stats/communes/comparees",
    tags=["statistiques"],
    summary="Médianes maison et appartement côte à côte, par commune",
)
def stats_communes_comparees(f: FiltresDep):
    return records(data.stats_communes_comparees(f))


@app.get("/stats/annuelles", tags=["statistiques"], summary="Médianes et volumes par année")
def stats_annuelles(f: FiltresDep):
    return records(data.stats_annuelles(f))


@app.get(
    "/stats/trimestrielles",
    tags=["statistiques"],
    summary="Médiane glissante sur 12 mois, à chaque trimestre",
)
def stats_trimestrielles(f: FiltresDep):
    return records(data.stats_trimestrielles(f))


@app.get(
    "/stats/evolution",
    tags=["statistiques"],
    summary="Variation avant/après la hausse des taux (toute la zone)",
)
def evolution(f: FiltresDep):
    return propre(data.evolution_globale(f))


@app.get(
    "/stats/evolution/communes",
    tags=["statistiques"],
    summary="Variation avant/après la hausse des taux, par commune",
)
def evolution_communes(f: FiltresDep, type: TypeBien = "Maison"):
    return records(data.evolution_communes(f, type))


@app.get("/budget/communes", tags=["budget"], summary="Communes accessibles pour un budget")
def budget_communes(
    f: FiltresDep,
    prix_max_bien: Annotated[float, Query(gt=0, description="Prix maximum du bien, hors frais")],
    type: TypeBien = "Maison",
    surf_min: Annotated[float, Query(ge=0)] = 0,
    pieces_min: Annotated[int, Query(ge=0, le=20)] = 0,
):
    return records(data.budget_communes(f, type, prix_max_bien, surf_min, pieces_min))


# --------------------------------------------------------------------------- #
# Fiche commune
# --------------------------------------------------------------------------- #
@app.get("/communes/{code}/resume", tags=["commune"], summary="Chiffres clés d'une commune")
def resume_commune(f: FiltresDep, code: CodeCommune):
    return propre(data.resume_commune(f, commune_connue(code)))


@app.get(
    "/communes/{code}/quartiers",
    tags=["commune"],
    summary="Médianes par quartier nommé (IRIS de l'INSEE)",
)
def quartiers(f: FiltresDep, code: CodeCommune, type: TypeBien | None = None):
    return records(data.stats_quartiers(f, commune_connue(code), type))


@app.get(
    "/communes/{code}/quartiers/geo",
    tags=["commune"],
    summary="Contours des quartiers d'une commune (GeoJSON)",
)
def quartiers_geo(code: CodeCommune):
    return data.quartiers_geo(commune_connue(code))


@app.get("/communes/{code}/sections", tags=["commune"], summary="Médianes par section cadastrale")
def sections(f: FiltresDep, code: CodeCommune, type: TypeBien | None = None):
    return records(data.stats_sections(f, commune_connue(code), type))


@app.get("/communes/{code}/annuel", tags=["commune"], summary="Médianes par année et type")
def annuel(f: FiltresDep, code: CodeCommune):
    return records(data.annuel_commune(f, commune_connue(code)))


@app.get("/communes/{code}/ventes", tags=["commune"], summary="Ventes d'une commune")
def ventes_commune(
    f: FiltresDep,
    code: CodeCommune,
    type: TypeBien | None = None,
    section: Annotated[str | None, Query(max_length=4)] = None,
    quartier: Annotated[str | None, Query(max_length=12, description="code_iris")] = None,
    geo: Annotated[bool, Query(description="Ne garder que les ventes géolocalisées")] = False,
    autour: Annotated[Autour | None, Depends(autour_param)] = None,
    limit: Annotated[int, Query(ge=1, le=20_000)] = 20_000,
):
    """Les plus récentes d'abord. `total` donne le nombre avant `limit`.

    Avec `lat`, `lon` et `rayon` : seulement les ventes géolocalisées à moins de
    `rayon` mètres du point, avec leur distance (`distance_m`).
    """
    code = commune_connue(code)
    if autour:
        df = data.ventes_autour(f, code, autour.lat, autour.lon, autour.rayon)
    else:
        df = data.ventes_commune(f, code).assign(distance_m=float("nan"))
    if type:
        df = df[df["type"] == type]
    if section:
        df = df[df["section"] == section]
    if quartier:
        df = df[df["code_iris"] == quartier]
    if geo:
        df = df.dropna(subset=["latitude", "longitude"])
    total = len(df)
    df = df.sort_values("date_mutation", ascending=False).head(limit)
    out = df.assign(date=df["date_mutation"].dt.strftime("%Y-%m-%d"), type=df["type"].astype(str))
    cols = [
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
        "distance_m",
    ]
    return {"total": total, "ventes": records(out[cols])}


@app.get(
    "/communes/{code}/autour",
    tags=["adresse"],
    summary="Prix médians des ventes autour d'un point de la commune",
)
def autour_adresse(
    f: FiltresDep,
    code: CodeCommune,
    autour: Annotated[Autour | None, Depends(autour_param)],
):
    if autour is None:
        raise HTTPException(422, "Paramètres lat, lon (et rayon) requis.")
    return propre(
        data.autour_adresse(f, commune_connue(code), autour.lat, autour.lon, autour.rayon)
    )


@app.get("/adresses", tags=["adresse"], summary="Rechercher une adresse du Loiret")
def adresses(
    q: Annotated[str, Query(min_length=3, max_length=200, description="Saisie libre")],
    commune: Annotated[str | None, Query(pattern=r"^\d[\dAB]\d{3}$")] = None,
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
):
    """Géocodage par la Base Adresse Nationale (Géoplateforme IGN), limité au Loiret."""
    try:
        return list(geocoder(q.strip(), commune, limit))
    except GeocodageIndisponible as exc:
        raise HTTPException(502, f"Service de géocodage indisponible : {exc}") from exc


@app.get(
    "/communes/{code}/comparables",
    tags=["commune"],
    summary="Ventes comparables à un bien (même type, surface ±20 %)",
)
def comparables(
    f: FiltresDep,
    code: CodeCommune,
    type: TypeBien,
    surface: Annotated[float, Query(gt=0)],
    exclure: Annotated[str, Query(description="id_mutation à exclure")] = "",
):
    return propre(data.comparables_stats(f, commune_connue(code), type, surface, exclure))
