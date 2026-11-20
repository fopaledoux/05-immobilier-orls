"""Tests de l'API : contrats des endpoints et quelques chiffres de référence."""

import pytest
from fastapi.testclient import TestClient

from immo_api.main import app

client = TestClient(app)
ORLEANS = "45234"


def get(path, **params):
    r = client.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_health_et_meta():
    assert get("/health") == {"status": "ok"}
    m = get("/meta")
    assert m["seuil_fiabilite"] == 30
    assert m["bornes"]["annees"] == [2021, 2026]
    assert m["annee_partielle"]["annee"] == 2026
    assert set(m["zones"]) == {"metropole", "loiret"}


def test_communes_et_geo():
    communes = get("/communes")
    assert len(communes) == 325
    assert sum(c["metropole"] for c in communes) == 22
    assert len(get("/geo/communes", zone="metropole")["features"]) == 22
    assert len(get("/geo/communes", zone="loiret")["features"]) == 325


def test_kpis_2021_2025_inchanges():
    """Les chiffres de référence du fichier Etalab 2021-2025 restent identiques."""
    k = get("/stats/kpis", annee_max=2025)
    assert k["n"] == 19_874 and k["n_communes"] == 22
    assert k["Maison"]["pm2_med"] == pytest.approx(2420, abs=1)
    assert get("/stats/kpis", zone="loiret", annee_max=2025)["n"] == 46_022


def test_premier_semestre_2026():
    k = get("/stats/kpis", zone="loiret", annee_min=2026)
    assert k["n"] == 3_841
    assert k["Maison"]["pm2_med"] == pytest.approx(1806, abs=1)
    assert get("/stats/kpis", zone="loiret")["n"] == 46_022 + 3_841
    annuel = get("/stats/annuelles", zone="loiret")
    assert max(r["annee"] for r in annuel) == 2026
    trim = get("/stats/trimestrielles", zone="loiret")
    assert trim[-1]["label"] == "T2 2026"
    # Ventes 2026 sans coordonnées : absentes de la carte, présentes dans le tableau
    v = get(f"/communes/{ORLEANS}/ventes", annee_min=2026, limit=5)
    assert v["total"] > 0 and v["ventes"][0]["latitude"] is None
    assert get(f"/communes/{ORLEANS}/ventes", annee_min=2026, geo=True)["total"] == 0


def test_filtres_annees_reduisent_les_ventes():
    assert get("/stats/kpis", zone="loiret", annee_max=2024)["n"] == 37_595


@pytest.mark.parametrize(
    "path,params",
    [
        ("/stats/communes", {"type": "Appartement"}),
        ("/stats/communes/comparees", {}),
        ("/stats/annuelles", {}),
        ("/stats/trimestrielles", {}),
        ("/stats/evolution/communes", {"type": "Maison"}),
        ("/budget/communes", {"prix_max_bien": 250_000, "surf_min": 100}),
        (f"/communes/{ORLEANS}/sections", {"type": "Maison"}),
        (f"/communes/{ORLEANS}/annuel", {}),
    ],
)
def test_endpoints_tabulaires(path, params):
    rows = get(path, **params)
    assert isinstance(rows, list) and rows
    assert all(isinstance(r, dict) for r in rows)


def test_evolution_globale():
    e = get("/stats/evolution")
    assert e["Maison"]["pm2_var"] == pytest.approx(-0.018, abs=0.001)
    assert e["Maison"]["ventes_var"] < 0


def test_budget_tri_fiables_en_premier():
    rows = get("/budget/communes", prix_max_bien=232_558, surf_min=100)
    fiables = [r["fiable"] for r in rows]
    assert fiables == sorted(fiables, reverse=True)
    assert all(0 <= r["part_sous_budget"] <= 1 for r in rows)


def test_fiche_commune():
    r = get(f"/communes/{ORLEANS}/resume", zone="loiret", annee_max=2025)
    assert r["n"] == 9130 and r["n_sections"] == 82
    v = get(f"/communes/{ORLEANS}/ventes", zone="loiret", annee_max=2025, limit=10)
    assert v["total"] == 9130 and len(v["ventes"]) == 10
    dates = [x["date"] for x in v["ventes"]]
    assert dates == sorted(dates, reverse=True)
    vente = v["ventes"][0]
    c = get(
        f"/communes/{ORLEANS}/comparables",
        zone="loiret",
        type=vente["type"],
        surface=vente["surface_reelle_bati"],
        exclure=vente["id_mutation"],
    )
    assert c["n"] > 0 and c["pm2_q1"] <= c["pm2_med"] <= c["pm2_q3"]


def test_erreurs():
    assert client.get("/communes/99999/resume").status_code == 404
    assert client.get("/stats/kpis", params={"zone": "france"}).status_code == 422
    assert (
        client.get("/stats/kpis", params={"annee_min": 2025, "annee_max": 2021}).status_code == 422
    )


def test_quartiers_nommes():
    q = get(f"/communes/{ORLEANS}/quartiers", zone="loiret")
    noms = {r["nom_quartier"] for r in q}
    assert {"Carmes-République", "Faubourg Bourgogne"} <= noms
    assert sum(r["n"] for r in q) == get(f"/communes/{ORLEANS}/resume", zone="loiret")["n"]
    geo = get(f"/communes/{ORLEANS}/quartiers/geo")
    assert len(geo["features"]) == 45
    assert get(f"/communes/{ORLEANS}/resume")["n_quartiers"] == 45
    # Petite commune : un seul « quartier », la commune elle-même
    assert get("/communes/45006/resume", zone="loiret")["n_quartiers"] == 1
    # Filtre des ventes par quartier, nom présent sur chaque vente
    code = next(r["code_iris"] for r in q if r["nom_quartier"] == "Carmes-République")
    v = get(f"/communes/{ORLEANS}/ventes", zone="loiret", quartier=code, limit=5)
    assert v["total"] > 0 and {x["nom_quartier"] for x in v["ventes"]} == {"Carmes-République"}


# Rue de la République, Orléans (coordonnées de la Base Adresse Nationale)
REPUBLIQUE = {"lat": 47.904773, "lon": 1.904538}


def test_ventes_autour_d_une_adresse():
    a = get(f"/communes/{ORLEANS}/autour", zone="loiret", rayon=500, **REPUBLIQUE)
    assert a["n"] > 0 and a["rayon"] == 500
    assert a["quartier"]["nom_quartier"]  # le point tombe dans un quartier nommé
    proche = get(f"/communes/{ORLEANS}/autour", zone="loiret", rayon=200, **REPUBLIQUE)
    assert proche["n"] < a["n"]
    v = get(f"/communes/{ORLEANS}/ventes", zone="loiret", rayon=500, **REPUBLIQUE)
    assert v["total"] == a["n"]
    assert all(0 <= x["distance_m"] <= 500 for x in v["ventes"])


def test_autour_parametres_invalides():
    assert client.get(f"/communes/{ORLEANS}/autour").status_code == 422
    assert client.get(f"/communes/{ORLEANS}/autour", params={"lat": 47.9}).status_code == 422
    params = {**REPUBLIQUE, "rayon": 10_000}
    assert client.get(f"/communes/{ORLEANS}/autour", params=params).status_code == 422


def test_recherche_adresse(monkeypatch):
    import immo_api.main as main

    def faux_geocoder(q, commune, limite):
        assert commune == ORLEANS
        return (
            {
                "label": "Rue de la République 45000 Orléans",
                **REPUBLIQUE,
                "code_commune": ORLEANS,
                "nom_commune": "Orléans",
                "type": "street",
            },
        )

    monkeypatch.setattr(main, "geocoder", faux_geocoder)
    r = get("/adresses", q="rue de la rep", commune=ORLEANS)
    assert r[0]["label"].startswith("Rue de la République")
    assert client.get("/adresses", params={"q": "ru"}).status_code == 422

    def panne(*_):
        raise main.GeocodageIndisponible("délai dépassé")

    monkeypatch.setattr(main, "geocoder", panne)
    assert client.get("/adresses", params={"q": "rue bannier"}).status_code == 502
