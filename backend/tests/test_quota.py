"""Sécurité du quota de l'assistant : contournement, usurpation, persistance.

Gemini est simulé : aucun appel réseau, aucun quota réel consommé.
"""

import fakeredis
import pytest
from fastapi.testclient import TestClient

import immo_api.main as main
from immo_api import llm, quota

JETON = "jeton-de-test-partage-entre-tableau-de-bord-et-api"
IP_A, IP_B = "203.0.113.7", "198.51.100.42"  # adresses de documentation (RFC 5737)
CHAT = {"messages": [{"role": "user", "content": "Prix à Orléans ?"}]}


@pytest.fixture(autouse=True)
def environnement(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("ASSISTANT_TOKEN", JETON)
    monkeypatch.setenv("QUOTA_SEL", "sel-de-test")
    monkeypatch.setenv("QUOTA_PAR_VISITEUR", "3")
    monkeypatch.setattr(llm, "discuter", lambda *a: ("Réponse simulée.", []))
    quota._stockage.cache_clear()
    quota._sel.cache_clear()
    yield
    # le test a pu remplacer _stockage par un faux sans cache
    getattr(quota._stockage, "cache_clear", lambda: None)()
    quota._sel.cache_clear()


def tableau_de_bord(ip: str) -> TestClient:
    """Une « session de navigation » : le tableau de bord appelle l'API pour ce visiteur."""
    return TestClient(main.app, headers={"X-Immo-Cle": JETON, "X-Visiteur-IP": ip})


def test_appel_direct_sans_jeton_refuse():
    """Contournement : appeler l'API de l'assistant directement, sans passer par le site."""
    anonyme = TestClient(main.app)
    assert anonyme.post("/assistant/chat", json=CHAT).status_code == 401
    assert anonyme.get("/assistant/quota").status_code == 401
    # Choisir son IP sans le jeton ne sert à rien non plus
    r = anonyme.post("/assistant/chat", json=CHAT, headers={"X-Visiteur-IP": IP_B})
    assert r.status_code == 401
    faux = TestClient(main.app, headers={"X-Immo-Cle": "mauvais", "X-Visiteur-IP": IP_A})
    assert faux.post("/assistant/chat", json=CHAT).status_code == 401


def test_ip_invalide_refusee():
    r = TestClient(main.app, headers={"X-Immo-Cle": JETON, "X-Visiteur-IP": "pas-une-ip"})
    assert r.post("/assistant/chat", json=CHAT).status_code == 400


def test_quota_partage_entre_sessions_d_un_meme_poste():
    """Plusieurs onglets / fenêtres / navigateurs = même IP = même compteur."""
    onglet_1, fenetre_privee, autre_navigateur = (tableau_de_bord(IP_A) for _ in range(3))
    assert onglet_1.post("/assistant/chat", json=CHAT).json()["quota"]["restantes"] == 2
    assert fenetre_privee.post("/assistant/chat", json=CHAT).json()["quota"]["restantes"] == 1
    assert autre_navigateur.post("/assistant/chat", json=CHAT).json()["quota"]["restantes"] == 0
    epuise = onglet_1.post("/assistant/chat", json=CHAT)
    assert epuise.status_code == 429
    detail = epuise.json()["detail"]
    assert detail["quota"]["restantes"] == 0 and detail["quota"]["prochaine_recharge"]
    assert fenetre_privee.get("/assistant/quota").json()["restantes"] == 0
    # Un autre visiteur garde son propre quota
    assert tableau_de_bord(IP_B).get("/assistant/quota").json()["restantes"] == 3


def test_echec_du_llm_ne_consomme_pas(monkeypatch):
    def panne(*_):
        raise llm.LLMIndisponible("quota gratuit de Gemini atteint")

    monkeypatch.setattr(llm, "discuter", panne)
    r = tableau_de_bord(IP_A).post("/assistant/chat", json=CHAT).json()
    assert r["reponse"] is None and r["quota"]["restantes"] == 3


def test_fenetre_glissante(monkeypatch):
    import time

    instant = [1_000_000.0]
    monkeypatch.setattr(time, "time", lambda: instant[0])
    s = tableau_de_bord(IP_A)
    for _ in range(3):
        s.post("/assistant/chat", json=CHAT)
    assert s.post("/assistant/chat", json=CHAT).status_code == 429
    instant[0] += 24 * 3600 + 1  # 24 h plus tard, les demandes sont rechargées
    assert s.get("/assistant/quota").json()["restantes"] == 3


def test_ip_jamais_stockee_en_clair():
    e = quota.empreinte(IP_A)
    assert IP_A not in e and len(e) == 32
    assert e == quota.empreinte(IP_A) != quota.empreinte(IP_B)


def test_stockage_redis(monkeypatch):
    """Même comportement avec le stockage Redis / Render Key Value (simulé)."""
    faux = fakeredis.FakeRedis()
    monkeypatch.setattr("redis.Redis.from_url", lambda *a, **k: faux)
    monkeypatch.setenv("REDIS_URL", "redis://simule:6379")
    quota._stockage.cache_clear()
    s = tableau_de_bord(IP_A)
    for attendu in (2, 1, 0):
        assert s.post("/assistant/chat", json=CHAT).json()["quota"]["restantes"] == attendu
    assert s.post("/assistant/chat", json=CHAT).status_code == 429
    cles = [k.decode() for k in faux.keys("*")]
    assert len(cles) == 1 and IP_A not in cles[0]  # une clé par visiteur, sans IP en clair
    assert 0 < faux.ttl(cles[0]) <= 24 * 3600  # effacée au bout de 24 h


def test_stockage_en_panne_refuse(monkeypatch):
    """Si le compteur ne répond pas, on refuse (503) plutôt que d'ouvrir sans limite."""

    class Panne:
        def etat(self, *a):
            raise quota.QuotaIndisponible("connexion refusée")

        reserver = etat

    monkeypatch.setattr(quota, "_stockage", lambda: Panne())
    assert tableau_de_bord(IP_A).post("/assistant/chat", json=CHAT).status_code == 503
