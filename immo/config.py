"""Constantes métier partagées par toute l'application."""

from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SALES_FILE = DATA_DIR / "immobilier.parquet"
GEOJSON_FILE = DATA_DIR / "communes_loiret.geojson"

# Code SIREN de l'EPCI Orléans Métropole (22 communes)
METROPOLE_EPCI = "244500468"

# En dessous de ce nombre de ventes, un prix médian est affiché « indicatif »
SEUIL_FIABILITE = 30

# Frais d'acquisition dans l'ancien (droits de mutation + émoluments), estimation
TAUX_FRAIS_NOTAIRE = 0.075

# Périodes comparées pour la question « depuis la hausse des taux »
PERIODE_AVANT = (2021, 2022)
PERIODE_APRES = (2024, 2025)

TYPES = ("Maison", "Appartement")

# Bornes des filtres réglables (= filtres déjà appliqués par la source)
BORNES = {
    "annees": (2021, 2025),
    "prix": (10_000, 2_000_000),
    "surface": (9, 400),
    "prix_m2": (300, 8_000),
}

FILTRES_DEFAUT = {
    "zone": "metropole",
    "annees": list(BORNES["annees"]),
    "prix": list(BORNES["prix"]),
    "surface": list(BORNES["surface"]),
    "prix_m2": list(BORNES["prix_m2"]),
}

ZONES = {
    "metropole": {
        "label": "Orléans Métropole",
        "center": {"lat": 47.895, "lon": 1.915},
        "zoom": 9.4,
    },
    "loiret": {
        "label": "Tout le Loiret",
        "center": {"lat": 47.92, "lon": 2.18},
        "zoom": 7.9,
    },
}
