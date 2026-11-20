"""Outils géographiques : distance, point dans un polygone, géocodage d'adresses."""

from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from functools import lru_cache

import numpy as np
import pandas as pd

# Géocodeur national (Base Adresse Nationale, servie par la Géoplateforme de l'IGN)
GEOCODEUR_URL = "https://data.geopf.fr/geocodage/search"
DEPARTEMENT = "45"
RAYON_TERRE_M = 6_371_000


class GeocodageIndisponible(RuntimeError):
    """Le service de géocodage n'a pas répondu."""


def distance_m(lat0: float, lon0: float, lats: pd.Series, lons: pd.Series) -> pd.Series:
    """Distance (mètres, formule de haversine) entre un point et une série de points."""
    p0, l0 = math.radians(lat0), math.radians(lon0)
    p, l = np.radians(lats), np.radians(lons)
    a = np.sin((p - p0) / 2) ** 2 + math.cos(p0) * np.cos(p) * np.sin((l - l0) / 2) ** 2
    return 2 * RAYON_TERRE_M * np.arcsin(np.sqrt(a))


def _dans_anneau(x: float, y: float, ring) -> bool:
    dedans = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            dedans = not dedans
        j = i
    return dedans


def contient(geometry: dict, lon: float, lat: float) -> bool:
    """Vrai si le point (lon, lat) est dans le Polygon / MultiPolygon GeoJSON."""
    coords = geometry["coordinates"]
    polys = coords if geometry["type"] == "MultiPolygon" else [coords]
    return any(
        _dans_anneau(lon, lat, poly[0]) and not any(_dans_anneau(lon, lat, h) for h in poly[1:])
        for poly in polys
    )


@lru_cache(maxsize=2048)
def geocoder(q: str, code_commune: str | None = None, limite: int = 5) -> tuple[dict, ...]:
    """Adresses du Loiret correspondant à la saisie (rues ou numéros)."""
    params = {"q": q, "limit": 15, "autocomplete": 1}
    if code_commune:
        params["citycode"] = code_commune
    url = f"{GEOCODEUR_URL}?{urllib.parse.urlencode(params)}"
    requete = urllib.request.Request(url, headers={"User-Agent": "immo-loiret-api"})
    try:
        with urllib.request.urlopen(requete, timeout=8) as r:
            data = json.load(r)
    except Exception as exc:  # réseau, délai, réponse invalide
        raise GeocodageIndisponible(str(exc)) from exc
    resultats = []
    for f in data.get("features", []):
        p = f["properties"]
        if p.get("depcode") != DEPARTEMENT and not str(p.get("citycode", "")).startswith(
            DEPARTEMENT
        ):
            continue
        lon, lat = f["geometry"]["coordinates"]
        resultats.append(
            {
                "label": p["label"],
                "lat": lat,
                "lon": lon,
                "code_commune": p["citycode"],
                "nom_commune": p.get("city"),
                "type": p.get("type"),
            }
        )
        if len(resultats) >= limite:
            break
    return tuple(resultats)
