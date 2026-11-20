"""Tests de l'assistant : Gemini est simulé (pas de réseau, pas de quota consommé)."""

import pytest
from fastapi.testclient import TestClient

import immo_api.main as main
from immo_api import llm
from immo_api.data import Filtres
from immo_api.outils import outils

# Le tableau de bord transmet l'IP de son visiteur ; adresse de documentation (RFC 5737)
client = TestClient(main.app, headers={"X-Visiteur-IP": "203.0.113.7"})


@pytest.fixture(autouse=True)
def environnement_isole(monkeypatch):
    """Pas de jeton ni de Redis : quota en mémoire, remis à neuf à chaque test."""
    from immo_api import quota

    monkeypatch.delenv("ASSISTANT_TOKEN", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    quota._stockage.cache_clear()
    yield
    quota._stockage.cache_clear()


ORLEANS = "45234"
PRIX = {"code_commune": ORLEANS, "type": "Appartement", "surface": 60, "prix": 180_000}


def test_evaluer_un_prix():
    r = client.get(
        f"/communes/{ORLEANS}/evaluer",
        params={"type": "Appartement", "surface": 60, "prix": 180_000, "zone": "loiret"},
    ).json()
    assert r["evaluable"] and r["n"] >= 30
    assert r["pm2"] == pytest.approx(3000)
    assert r["pm2_q1"] <= r["pm2_med"] <= r["pm2_q3"]
    assert r["position"] == "au-dessus" and 0 <= r["rang"] <= 1
    assert len(r["valeurs"]) == r["n"]


def test_repli_sans_llm(monkeypatch):
    """Sans clé (ou en panne), les chiffres arrivent quand même, sans texte."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert client.get("/assistant/statut").json()["actif"] is False
    r = client.post("/assistant/expliquer-prix", json=PRIX).json()
    assert r["texte"] is None and "non configuré" in r["erreur"]
    assert r["chiffres"]["position"] == "au-dessus"
    r = client.post("/assistant/chat", json={"messages": [{"role": "user", "content": "Bonjour"}]})
    assert r.json()["reponse"] is None


def test_explication_ne_recoit_que_nos_chiffres(monkeypatch):
    recu = {}

    def faux_rediger(consigne, donnees):
        recu.update(donnees)
        return "Texte simulé."

    monkeypatch.setattr(llm, "rediger", faux_rediger)
    r = client.post("/assistant/expliquer-prix", json=PRIX).json()
    assert r["texte"] == "Texte simulé." and r["erreur"] is None
    assert recu["commune"] == "Orléans"
    assert recu["prix_m2_median_comparables"] == r["chiffres"]["prix_m2_median_comparables"]
    assert "valeurs" not in recu  # liste brute non envoyée au LLM


def test_conseil_budget(monkeypatch):
    monkeypatch.setattr(llm, "rediger", lambda consigne, donnees: "Conseil simulé.")
    r = client.post(
        "/assistant/conseil-budget",
        json={"budget_total": 300_000, "type": "Maison", "surface_min": 100},
    ).json()
    assert r["texte"] == "Conseil simulé."
    assert r["chiffres"]["communes_dans_le_budget"]


def test_chat(monkeypatch):
    def faux_discuter(historique, contexte, liste_outils):
        assert historique[-1]["content"] == "Prix à Olivet ?"
        assert "Orléans Métropole" in contexte
        assert {o.__name__ for o in liste_outils} >= {"chercher_commune", "prix_commune"}
        return "Réponse simulée.", ["chercher_commune"]

    monkeypatch.setattr(llm, "discuter", faux_discuter)
    r = client.post(
        "/assistant/chat", json={"messages": [{"role": "user", "content": "Prix à Olivet ?"}]}
    ).json()
    assert r["reponse"] == "Réponse simulée." and r["outils"] == ["chercher_commune"]
    assert r["erreur"] is None and r["quota"]["restantes"] == 19
    fin_assistant = {"messages": [{"role": "assistant", "content": "Bonjour"}]}
    assert client.post("/assistant/chat", json=fin_assistant).status_code == 422


def test_outils_renvoient_nos_chiffres():
    o = {f.__name__: f for f in outils(Filtres(zone="metropole"))}
    assert o["chercher_commune"]("st jean de braye")["communes"][0]["code_commune"] == "45284"
    assert o["prix_commune"]("45234")["maison"]["nombre_ventes"] > 0
    assert o["prix_par_quartier"]("45234", "Appartement")["quartiers"]
    assert o["communes_pour_budget"](300_000, "Maison", 100)["communes_dans_le_budget"]
    assert len(o["classement_communes"]("Maison", "metropole")["communes"]) == 10
    assert o["evolution_des_prix"]()["maison"]["variation_prix_pct"] == pytest.approx(-1.8, abs=0.1)
    assert o["evolution_commune"]("45284")["maison"]["variation_pct"] == pytest.approx(
        -1.7, abs=0.1
    )
    assert o["evaluer_un_prix"]("45234", "Appartement", 60, 180_000)["position"] == "au-dessus"


def test_plafond_horaire(monkeypatch):
    monkeypatch.setenv("LLM_QUOTA_HEURE", "1")
    plafond = llm._Plafond()
    plafond.prendre()
    with pytest.raises(llm.LLMIndisponible):
        plafond.prendre()
