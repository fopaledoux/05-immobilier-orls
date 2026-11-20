"""Configuration du frontend.

- Constantes d'interface (adresse de l'API, centrage des cartes, budget
  d'exemple) : définies ici.
- Constantes métier (seuil de fiabilité, frais de notaire, périodes, bornes
  des filtres) : lues sur l'API (`/meta`), qui en est la source de vérité.
  Elles se lisent par attribut au moment de l'appel (`cfg.SEUIL_FIABILITE`),
  jamais à l'import : l'appli démarre même si l'API n'est pas encore prête.
"""

import os

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
# L'offre gratuite de Render met l'API en veille : le premier appel peut être long
API_TIMEOUT = float(os.environ.get("API_TIMEOUT", "60"))

# Jeton partagé avec l'API : seul le tableau de bord peut appeler l'assistant.
# En ligne, Render le copie depuis le service API ; en local, il peut rester vide.
ASSISTANT_TOKEN = os.environ.get("ASSISTANT_TOKEN", "")

# Où lire l'IP du visiteur derrière le proxy de l'hébergeur (voir api.ip_visiteur) :
# en-tête et position de l'entrée ajoutée par le proxy de confiance (-1 = la dernière).
IP_EN_TETE = os.environ.get("IP_EN_TETE", "X-Forwarded-For")
IP_RANG = int(os.environ.get("IP_RANG", "-1"))

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

BUDGET_DEFAUT = 300_000
SURFACE_DEFAUT = 100

_META = {
    "SEUIL_FIABILITE": lambda m: m["seuil_fiabilite"],
    "TAUX_FRAIS_NOTAIRE": lambda m: m["taux_frais_notaire"],
    "PERIODE_AVANT": lambda m: tuple(m["periode_avant"]),
    "PERIODE_APRES": lambda m: tuple(m["periode_apres"]),
    "TYPES": lambda m: tuple(m["types"]),
    "BORNES": lambda m: {k: tuple(v) for k, v in m["bornes"].items()},
    "FILTRES_DEFAUT": lambda m: m["filtres_defaut"],
    "ANNEE_PARTIELLE": lambda m: m["annee_partielle"],
}


def __getattr__(name):
    """Constantes métier résolues paresseusement depuis l'API (mise en cache)."""
    if name in _META:
        from immo import api

        return _META[name](api.meta())
    raise AttributeError(f"module 'immo.config' has no attribute {name!r}")
