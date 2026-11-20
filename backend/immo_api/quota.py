"""Quota de demandes à l'assistant, par visiteur, compté côté serveur.

Pourquoi côté serveur : un compteur tenu par le navigateur (sessionStorage,
cookie, localStorage) se remet à zéro avec un nouvel onglet, une fenêtre
privée ou un autre navigateur, et se modifie à la main. Ici, le visiteur est
identifié par son adresse IP, commune à toutes ses sessions sur un même poste.

Protection des données (RGPD) : l'IP n'est jamais stockée en clair. On garde
seulement une empreinte HMAC-SHA256 (clé secrète QUOTA_SEL), non réversible,
qui expire avec la fenêtre de comptage (24 h par défaut).

Stockage : Redis / Render Key Value (variable REDIS_URL) pour survivre aux
mises en veille de l'API ; à défaut (développement local), en mémoire.
Fenêtre glissante : chaque demande est horodatée dans un ensemble trié.

Réglages : QUOTA_PAR_VISITEUR (20), QUOTA_FENETRE_HEURES (24).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from functools import lru_cache

log = logging.getLogger("immo_api.quota")

PREFIXE = "immo:quota:"


class QuotaIndisponible(RuntimeError):
    """Le stockage des compteurs ne répond pas : on refuse plutôt que de laisser passer."""


@dataclass(frozen=True)
class Etat:
    limite: int
    utilisees: int
    fenetre_heures: int
    prochaine_recharge: float | None  # timestamp Unix, quand une demande se libère

    @property
    def restantes(self) -> int:
        return max(self.limite - self.utilisees, 0)

    def en_json(self) -> dict:
        return {
            "limite": self.limite,
            "restantes": self.restantes,
            "fenetre_heures": self.fenetre_heures,
            "prochaine_recharge": (
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.prochaine_recharge))
                if self.prochaine_recharge
                else None
            ),
        }


def limite() -> int:
    return int(os.environ.get("QUOTA_PAR_VISITEUR", "20"))


def fenetre_s() -> int:
    return int(os.environ.get("QUOTA_FENETRE_HEURES", "24")) * 3600


@lru_cache(maxsize=1)
def _sel() -> bytes:
    sel = os.environ.get("QUOTA_SEL")
    if not sel:
        # Développement : clé aléatoire propre au processus (empreintes non réutilisables)
        log.warning("QUOTA_SEL absente : clé d'empreinte temporaire")
        return secrets.token_bytes(32)
    return sel.encode()


def empreinte(ip: str) -> str:
    """Identifiant du visiteur : HMAC de son IP, l'IP elle-même n'est jamais conservée."""
    return hmac.new(_sel(), ip.strip().encode(), hashlib.sha256).hexdigest()[:32]


# --------------------------------------------------------------------------- #
# Stockages
# --------------------------------------------------------------------------- #
class _Memoire:
    """Stockage local (un seul processus) : pour le développement et les tests."""

    def __init__(self):
        self._donnees: dict[str, dict[str, float]] = {}
        self._verrou = threading.Lock()

    def _purger(self, cle: str, maintenant: float) -> dict[str, float]:
        d = self._donnees.setdefault(cle, {})
        for m in [m for m, t in d.items() if t <= maintenant - fenetre_s()]:
            del d[m]
        return d

    def etat(self, cle: str, maintenant: float) -> tuple[int, float | None]:
        with self._verrou:
            d = self._purger(cle, maintenant)
            return len(d), (min(d.values()) + fenetre_s()) if d else None

    def reserver(self, cle: str, maintenant: float, lim: int) -> tuple[bool, str]:
        with self._verrou:
            d = self._purger(cle, maintenant)
            if len(d) >= lim:
                return False, ""
            jeton = uuid.uuid4().hex
            d[jeton] = maintenant
            return True, jeton

    def rendre(self, cle: str, jeton: str) -> None:
        with self._verrou:
            self._donnees.get(cle, {}).pop(jeton, None)


# Réserve une demande de façon atomique : purge, compte, ajoute si sous la limite
_SCRIPT_RESERVER = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1] - ARGV[2])
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[3]) then return 0 end
redis.call('ZADD', KEYS[1], ARGV[1], ARGV[4])
redis.call('EXPIRE', KEYS[1], ARGV[2])
return 1
"""


class _Redis:
    def __init__(self, url: str):
        import redis

        self._r = redis.Redis.from_url(url, socket_timeout=3, socket_connect_timeout=3)
        self._reserver = self._r.register_script(_SCRIPT_RESERVER)

    def etat(self, cle: str, maintenant: float) -> tuple[int, float | None]:
        try:
            self._r.zremrangebyscore(cle, "-inf", maintenant - fenetre_s())
            n = self._r.zcard(cle)
            premier = self._r.zrange(cle, 0, 0, withscores=True)
        except Exception as exc:
            raise QuotaIndisponible(str(exc)) from exc
        return n, (premier[0][1] + fenetre_s()) if premier else None

    def reserver(self, cle: str, maintenant: float, lim: int) -> tuple[bool, str]:
        jeton = uuid.uuid4().hex
        try:
            ok = self._reserver(keys=[cle], args=[maintenant, fenetre_s(), lim, jeton])
        except Exception as exc:
            raise QuotaIndisponible(str(exc)) from exc
        return bool(ok), jeton

    def rendre(self, cle: str, jeton: str) -> None:
        try:
            self._r.zrem(cle, jeton)
        except Exception as exc:  # une demande non rendue reste comptée : sans gravité
            log.warning("quota : impossible de rendre une demande (%s)", exc)


@lru_cache(maxsize=1)
def _stockage():
    url = os.environ.get("REDIS_URL")
    if url:
        return _Redis(url)
    log.warning("REDIS_URL absente : quotas en mémoire (remis à zéro au redémarrage)")
    return _Memoire()


# --------------------------------------------------------------------------- #
# API du module
# --------------------------------------------------------------------------- #
def etat(visiteur: str) -> Etat:
    utilisees, recharge = _stockage().etat(PREFIXE + visiteur, time.time())
    return Etat(limite(), utilisees, fenetre_s() // 3600, recharge)


def reserver(visiteur: str) -> str | None:
    """Réserve une demande ; renvoie un jeton, ou None si le quota est épuisé."""
    ok, jeton = _stockage().reserver(PREFIXE + visiteur, time.time(), limite())
    return jeton if ok else None


def rendre(visiteur: str, jeton: str) -> None:
    """Annule une réservation (la demande a échoué : elle ne doit pas compter)."""
    _stockage().rendre(PREFIXE + visiteur, jeton)
