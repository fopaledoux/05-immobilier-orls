"""Recherche d'adresse : champ avec suggestions (Base Adresse Nationale, via l'API).

La valeur d'une option encode le point : « lat;lon;code_commune;libellé ».
"""

from __future__ import annotations

import dash_mantine_components as dmc

from immo import api
from immo.components import icon

LONGUEUR_MIN = 4
RAYONS = [
    {"value": "300", "label": "300 m"},
    {"value": "500", "label": "500 m"},
    {"value": "1000", "label": "1 km"},
]


def champ_adresse(id_: str, placeholder: str, w=320, **kwargs):
    return dmc.Select(
        id=id_,
        placeholder=placeholder,
        data=[],
        searchable=True,
        clearable=True,
        leftSection=icon("tabler:map-pin", 16),
        nothingFoundMessage=f"Tapez au moins {LONGUEUR_MIN} caractères (numéro et rue)",
        # Les suggestions viennent du géocodeur : pas de filtrage côté navigateur
        filter={"function": "sansFiltre"},
        w=w,
        maxDropdownHeight=280,
        debounce=350,  # attend la fin de la frappe avant d'interroger le géocodeur
        comboboxProps={"withinPortal": True},
        **kwargs,
    )


def encoder(a: dict) -> str:
    return f"{a['lat']};{a['lon']};{a['code_commune']};{a['label']}"


def decoder(valeur: str | None) -> dict | None:
    if not valeur:
        return None
    try:
        lat, lon, code, label = valeur.split(";", 3)
        return {"lat": float(lat), "lon": float(lon), "code_commune": code, "label": label}
    except ValueError:
        return None


def options(saisie: str | None, commune: str | None, valeur_actuelle: str | None) -> list[dict]:
    """Suggestions pour la saisie, en gardant l'option déjà choisie."""
    garder = []
    actuelle = decoder(valeur_actuelle)
    if actuelle:
        garder = [{"value": valeur_actuelle, "label": actuelle["label"]}]
    if not saisie or len(saisie.strip()) < LONGUEUR_MIN:
        return garder
    try:
        trouvees = api.adresses(saisie, commune)
    except api.ApiError:
        return garder
    vues = {o["value"] for o in garder}
    return garder + [
        {"value": encoder(a), "label": a["label"]} for a in trouvees if encoder(a) not in vues
    ]
