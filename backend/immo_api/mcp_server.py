"""Serveur MCP d'Immo Loiret : les prix de l'immobilier du Loiret pour tout client MCP.

Expose aux assistants (Claude Code, Claude Desktop, MCP Inspector…) les mêmes
données que le tableau de bord : ventes DVF du Loiret, janvier 2021 à juin 2026.
Tous les calculs (médianes, écarts, nombre de ventes) sont faits ici ; le
modèle client ne fait que les présenter.

Lancer :
    uv run python -m immo_api.mcp_server                     # stdio (par défaut)
    uv run python -m immo_api.mcp_server --http --port 8020  # HTTP (/mcp)

Inspecter (depuis la racine du dépôt) :
    npx @modelcontextprotocol/inspector --config .mcp.json --server immo-loiret
"""

from __future__ import annotations

import argparse
import json

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from immo_api import data
from immo_api.config import (
    ANNEE_PARTIELLE,
    BORNES,
    PERIODE_APRES,
    PERIODE_AVANT,
    SEUIL_FIABILITE,
    TAUX_FRAIS_NOTAIRE,
    ZONES,
)
from immo_api.data import Filtres
from immo_api.geo import GeocodageIndisponible, geocoder
from immo_api.outils import _bloc_type, outils

INSTRUCTIONS = f"""Données : ventes de logements (maisons, appartements) du Loiret, janvier 2021 à
juin 2026 (DVF, DGFiP). Tous les prix sont des médianes ; chaque résultat donne le nombre de
ventes qui le fonde. En dessous de {SEUIL_FIABILITE} ventes (`fiable: false`), un chiffre n'est
qu'indicatif. Les communes se désignent par leur code INSEE : appelez d'abord
`chercher_commune`. Les données ne disent rien de l'état du bien, de l'étage ni du DPE."""

serveur = MCPServer(
    name="immo-loiret",
    title="Immo Loiret",
    description="Prix médians de l'immobilier dans le Loiret (DVF 2021 - juin 2026)",
    version="1.0.0",
    instructions=INSTRUCTIONS,
)

# Outils en lecture seule sur nos données (aucun effet de bord, aucun appel externe)
LECTURE = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)

for outil in outils(Filtres()):
    serveur.add_tool(outil, annotations=LECTURE)


@serveur.tool(
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)
)
def prix_autour_d_une_adresse(adresse: str, rayon_m: int = 500) -> dict:
    """Prix médians des ventes autour d'une adresse du Loiret, et son quartier.

    L'adresse est localisée par la Base Adresse Nationale (service de l'IGN), puis on retient
    les ventes géolocalisées dans le rayon (celles de 2026 n'ont pas de coordonnées).

    Args:
        adresse: adresse libre, avec la commune (ex. « 12 rue Bannier Orléans »).
        rayon_m: rayon de recherche en mètres, entre 100 et 2000.
    """
    rayon = max(100, min(int(rayon_m), 2000))
    try:
        trouvees = geocoder(adresse.strip(), None, 1)
    except GeocodageIndisponible as exc:
        return {"erreur": f"géocodage indisponible : {exc}"}
    if not trouvees:
        return {"erreur": "adresse introuvable dans le Loiret"}
    a = trouvees[0]
    res = data.autour_adresse(
        Filtres(zone="loiret"), a["code_commune"], a["lat"], a["lon"], float(rayon)
    )
    return {
        "adresse_trouvee": a["label"],
        "code_commune": a["code_commune"],
        "quartier": (res["quartier"] or {}).get("nom_quartier"),
        "rayon_m": rayon,
        "nombre_ventes": res["n"],
        "maison": _bloc_type(res["Maison"]),
        "appartement": _bloc_type(res["Appartement"]),
    }


# --------------------------------------------------------------------------- #
# Ressources : règles de calcul et référentiel
# --------------------------------------------------------------------------- #
@serveur.resource(
    "immo://regles",
    name="regles",
    title="Règles de calcul",
    description="Seuil de fiabilité, frais de notaire, périodes comparées, bornes et sources.",
    mime_type="application/json",
)
def regles() -> str:
    return json.dumps(
        {
            "seuil_fiabilite_ventes": SEUIL_FIABILITE,
            "taux_frais_notaire": TAUX_FRAIS_NOTAIRE,
            "periode_avant_hausse_des_taux": list(PERIODE_AVANT),
            "periode_apres": list(PERIODE_APRES),
            "annee_partielle": ANNEE_PARTIELLE,
            "bornes_des_filtres": {k: list(v) for k, v in BORNES.items()},
            "zones": ZONES,
            "sources": [
                "DGFiP, DVF (2021-2025 : Etalab, géolocalisées ; 2026 S1 : DGFiP, brutes)",
                "Quartiers : IRIS 2024 (IGN / INSEE)",
                "Adresses : Base Adresse Nationale (Géoplateforme IGN)",
            ],
            "licence": "Licence Ouverte 2.0",
        },
        ensure_ascii=False,
    )


@serveur.resource(
    "immo://communes",
    name="communes",
    title="Communes du Loiret",
    description="Code INSEE et nom des 325 communes ayant au moins une vente.",
    mime_type="application/json",
)
def communes() -> str:
    idx = data.communes_index()
    return json.dumps(
        [
            {"code_commune": r.code_commune, "nom": r.nom_commune, "metropole": bool(r.metropole)}
            for r in idx.itertuples()
        ],
        ensure_ascii=False,
    )


@serveur.resource(
    "immo://communes/{code_commune}",
    name="fiche_commune",
    title="Fiche d'une commune",
    description="Prix médians maison / appartement et quartiers d'une commune (code INSEE).",
    mime_type="application/json",
)
def fiche_commune(code_commune: str) -> str:
    f = Filtres(zone="loiret")
    r = data.resume_commune(f, code_commune)
    q = data.stats_quartiers(f, code_commune, None)
    return json.dumps(
        {
            "code_commune": code_commune,
            "nombre_ventes": r["n"],
            "maison": _bloc_type(r["Maison"]),
            "appartement": _bloc_type(r["Appartement"]),
            "quartiers": [
                {
                    "quartier": x.nom_quartier,
                    "prix_m2_median": int(round(x.pm2_med)),
                    "nombre_ventes": int(x.n),
                }
                for x in q.itertuples()
            ],
        },
        ensure_ascii=False,
    )


# --------------------------------------------------------------------------- #
# Prompt : la question métier « ce prix est-il raisonnable ? »
# --------------------------------------------------------------------------- #
@serveur.prompt(
    title="Évaluer une annonce",
    description="Dire si le prix d'une annonce est cohérent avec les ventes comparables.",
)
def evaluer_une_annonce(commune: str, type_bien: str, surface_m2: str, prix_eur: str) -> str:
    return (
        f"Je regarde une annonce : {type_bien} de {surface_m2} m² à {commune}, "
        f"proposé(e) à {prix_eur} €. Ce prix est-il raisonnable ?\n\n"
        "Utilise `chercher_commune` pour obtenir le code INSEE, puis `evaluer_un_prix`. "
        "Réponds en 3 à 5 phrases : écart à la médiane des ventes comparables, place parmi "
        "elles, nombre de ventes et fiabilité, puis une piste concrète (négociation, points à "
        "vérifier). N'invente aucun chiffre ; rappelle que DVF ne dit rien de l'état ni du DPE."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Serveur MCP Immo Loiret")
    parser.add_argument("--http", action="store_true", help="transport HTTP au lieu de stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8020)
    args = parser.parse_args()
    if args.http:
        serveur.run("streamable-http", host=args.host, port=args.port)
    else:
        serveur.run("stdio")


if __name__ == "__main__":
    main()
