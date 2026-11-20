"""Tests du serveur MCP (en mémoire, sans transport ni réseau)."""

import asyncio
import json

from immo_api import geo
from immo_api.mcp_server import serveur


def _texte(resultat) -> dict:
    return json.loads(resultat.content[0].text)


def test_inventaire():
    async def lister():
        return (
            {t.name: t for t in await serveur.list_tools()},
            [str(r.uri) for r in await serveur.list_resources()],
            [p.name for p in await serveur.list_prompts()],
        )

    outils, ressources, prompts = asyncio.run(lister())
    assert {"chercher_commune", "evaluer_un_prix", "prix_autour_d_une_adresse"} <= set(outils)
    assert len(outils) == 9
    assert outils["prix_commune"].annotations.read_only_hint is True
    assert ressources == ["immo://regles", "immo://communes"]
    assert prompts == ["evaluer_une_annonce"]


def test_appel_d_outil():
    r = asyncio.run(
        serveur.call_tool(
            "evaluer_un_prix",
            {"code_commune": "45234", "type_bien": "Appartement", "surface": 60, "prix": 180_000},
        )
    )
    d = _texte(r)
    assert d["position"] == "au-dessus" and d["nombre_ventes_comparables"] > 30


def test_adresse_avec_geocodeur_simule(monkeypatch):
    import immo_api.mcp_server as m

    point = {
        "label": "12 Rue Bannier 45000 Orléans",
        "lat": 47.903305,
        "lon": 1.903493,
        "code_commune": "45234",
        "nom_commune": "Orléans",
        "type": "housenumber",
    }
    monkeypatch.setattr(m, "geocoder", lambda q, commune, limite: (point,))
    d = _texte(
        asyncio.run(
            serveur.call_tool("prix_autour_d_une_adresse", {"adresse": "x", "rayon_m": 500})
        )
    )
    assert d["adresse_trouvee"] == point["label"] and d["nombre_ventes"] > 0
    assert d["quartier"]

    def panne(*_):
        raise geo.GeocodageIndisponible("délai")

    monkeypatch.setattr(m, "geocoder", panne)
    d = _texte(asyncio.run(serveur.call_tool("prix_autour_d_une_adresse", {"adresse": "x"})))
    assert "indisponible" in d["erreur"]


def test_ressources():
    regles = json.loads(asyncio.run(serveur.read_resource("immo://regles"))[0].content)
    assert regles["seuil_fiabilite_ventes"] == 30
    fiche = json.loads(asyncio.run(serveur.read_resource("immo://communes/45234"))[0].content)
    assert len(fiche["quartiers"]) == 45
