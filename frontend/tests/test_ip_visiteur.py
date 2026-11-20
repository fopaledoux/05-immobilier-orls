"""Extraction de l'IP du visiteur : un en-tête forgé par le client ne doit pas compter."""

import pytest
from flask import Flask

from immo import api
from immo import config as cfg

app = Flask(__name__)


def ip(headers=None, remote="10.0.0.5"):
    with app.test_request_context("/", headers=headers or {}, environ_base={"REMOTE_ADDR": remote}):
        return api.ip_visiteur()


def test_derniere_entree_ajoutee_par_le_proxy():
    # Le proxy de l'hébergeur ajoute l'IP réelle en fin de chaîne
    assert ip({"X-Forwarded-For": "203.0.113.7"}) == "203.0.113.7"


def test_entree_forgee_par_le_client_ignoree():
    # Le visiteur envoie « X-Forwarded-For: 1.2.3.4 » ; le proxy y ajoute sa vraie IP
    assert ip({"X-Forwarded-For": "1.2.3.4, 203.0.113.7"}) == "203.0.113.7"
    assert ip({"X-Forwarded-For": "pas-une-ip, 203.0.113.7"}) == "203.0.113.7"


def test_sans_proxy_adresse_de_connexion():
    assert ip(remote="127.0.0.1") == "127.0.0.1"
    assert ip({"X-Forwarded-For": "n'importe quoi"}, remote="192.0.2.1") == "192.0.2.1"


def test_rang_reglable(monkeypatch):
    # Deux proxys de confiance (ex. CDN puis équilibreur) : l'IP client est l'avant-dernière
    monkeypatch.setattr(cfg, "IP_RANG", -2)
    assert ip({"X-Forwarded-For": "1.2.3.4, 203.0.113.7, 198.51.100.1"}) == "203.0.113.7"


def test_jeton_transmis_seulement_s_il_existe(monkeypatch):
    monkeypatch.setattr(cfg, "ASSISTANT_TOKEN", "")
    with app.test_request_context("/"):
        assert "X-Immo-Cle" not in api._entetes_assistant()
    monkeypatch.setattr(cfg, "ASSISTANT_TOKEN", "secret")
    with app.test_request_context("/"):
        assert api._entetes_assistant()["X-Immo-Cle"] == "secret"
