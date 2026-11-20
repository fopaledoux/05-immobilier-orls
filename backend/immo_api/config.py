"""Constantes métier : source de vérité, exposées au frontend par /meta."""

from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
# Ventes 2021-2025 : DVF géolocalisées (Etalab). 1er semestre 2026 : DVF brutes
# (DGFiP), préparées par scripts/prepare_dvf_2026s1.py, sans coordonnées.
SALES_FILES = (
    DATA_DIR / "immobilier.parquet",
    DATA_DIR / "immobilier_2026s1.parquet",
)
GEOJSON_FILE = DATA_DIR / "communes_loiret.geojson"

# Code SIREN de l'EPCI Orléans Métropole (22 communes)
METROPOLE_EPCI = "244500468"

# En dessous de ce nombre de ventes, un prix médian est affiché « indicatif »
SEUIL_FIABILITE = 30

# Frais d'acquisition dans l'ancien (droits de mutation + émoluments), estimation
TAUX_FRAIS_NOTAIRE = 0.075

# Périodes comparées pour la question « depuis la hausse des taux »
PERIODE_AVANT = (2021, 2022)
PERIODE_APRES = (2024, 2025)  # années complètes uniquement

# Dernière année disponible, incomplète : à signaler dans les graphiques
ANNEE_PARTIELLE = {"annee": 2026, "label": "2026 (janv.-juin)", "fin": "2026-06-30"}

TYPES = ("Maison", "Appartement")

# Bornes des filtres réglables (= filtres déjà appliqués par la source)
BORNES = {
    "annees": (2021, 2026),
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
    "metropole": "Orléans Métropole",
    "loiret": "Tout le Loiret",
}
