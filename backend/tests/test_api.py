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
    assert m["bornes"]["annees"] == [2021, 2025]
    assert set(m["zones"]) == {"metropole", "loiret"}


def test_communes_et_geo():
    communes = get("/communes")
    assert len(communes) == 325
    assert sum(c["metropole"] for c in communes) == 22
    assert len(get("/geo/communes", zone="metropole")["features"]) == 22
    assert len(get("/geo/communes", zone="loiret")["features"]) == 325


def test_kpis_metropole_et_loiret():
    k = get("/stats/kpis")
    assert k["n"] == 19_874 and k["n_communes"] == 22
    assert k["Maison"]["pm2_med"] == pytest.approx(2420, abs=1)
    assert get("/stats/kpis", zone="loiret")["n"] == 46_022


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
    r = get(f"/communes/{ORLEANS}/resume", zone="loiret")
    assert r["n"] == 9130 and r["n_sections"] == 82
    v = get(f"/communes/{ORLEANS}/ventes", zone="loiret", limit=10)
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
