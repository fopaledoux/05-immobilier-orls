"""Client Gemini : rédaction de textes et discussion avec appels d'outils.

Principe : le LLM ne calcule rien. L'API calcule les chiffres (médianes,
écarts, nombre de ventes) ; Gemini les explique en français clair, sans rien
inventer. En cas d'échec (pas de clé, quota, panne), `LLMIndisponible` est
levée et les endpoints renvoient quand même les chiffres (repli sans LLM).

Configuration (variables d'environnement, jamais dans le code) :
- GEMINI_API_KEY : clé de l'API Gemini (obligatoire pour activer le LLM) ;
- GEMINI_MODEL : modèle (défaut : gemini-3.5-flash-lite, offre gratuite) ;
- LLM_QUOTA_HEURE : plafond global de requêtes LLM par heure (défaut : 300).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from collections.abc import Callable
from functools import lru_cache

from google import genai
from google.genai import types

log = logging.getLogger("immo_api.llm")

MODELE_DEFAUT = "gemini-3.5-flash-lite"

REGLES = """Tu es l'assistant d'Immo Loiret, un outil qui aide un couple à acheter un logement
dans le Loiret à partir des ventes réellement conclues (DVF, 2021 à juin 2026).

Règles impératives :
1. N'utilise QUE les chiffres fournis (données JSON ou résultats d'outils). N'invente jamais
   un prix, un nombre de ventes, une tendance ou un nom de quartier.
2. Chaque prix est une médiane : cite le nombre de ventes qui la fonde. Si `fiable` vaut
   false (moins de 30 ventes), précise que le chiffre est seulement indicatif.
3. Les données ne disent rien de l'état du bien, de l'étage ni du DPE : rappelle-le quand tu
   juges un prix.
4. S'il te manque une donnée pour répondre, dis-le simplement et propose ce que tu peux
   calculer à la place.
5. Réponds en français clair, en vouvoyant, avec des phrases courtes et sans jargon.
   Formate les nombres à la française : montants en euros (238 000 €), prix au m²
   (2 450 €/m²), pourcentages (12 %). Les champs suffixés _eur sont des euros, _pct des %.
6. Pas de conseil financier, fiscal ou juridique personnalisé (crédit, impôts) : renvoie
   vers un professionnel si on te le demande.
7. Reste sur le sujet de l'immobilier dans le Loiret."""


class LLMIndisponible(RuntimeError):
    """Le LLM n'a pas pu répondre (pas de clé, quota atteint, panne réseau...)."""


def modele() -> str:
    return os.environ.get("GEMINI_MODEL", MODELE_DEFAUT)


def actif() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


@lru_cache(maxsize=1)
def _client() -> genai.Client:
    return genai.Client(
        api_key=os.environ["GEMINI_API_KEY"],
        http_options=types.HttpOptions(
            timeout=25_000,  # ms par requête : on préfère le repli à une attente sans fin
            retry_options=types.HttpRetryOptions(attempts=2, initial_delay=1.0, max_delay=4.0),
        ),
    )


class _Plafond:
    """Plafond global de requêtes par heure, pour préserver le quota gratuit."""

    def __init__(self):
        self._dates: deque[float] = deque()
        self._verrou = threading.Lock()

    def prendre(self) -> None:
        limite = int(os.environ.get("LLM_QUOTA_HEURE", "300"))
        maintenant = time.monotonic()
        with self._verrou:
            while self._dates and maintenant - self._dates[0] > 3600:
                self._dates.popleft()
            if len(self._dates) >= limite:
                raise LLMIndisponible("plafond horaire de l'assistant atteint, réessayez plus tard")
            self._dates.append(maintenant)


_plafond = _Plafond()


def _appeler(contents, config: types.GenerateContentConfig):
    if not actif():
        raise LLMIndisponible("assistant non configuré (GEMINI_API_KEY absente)")
    _plafond.prendre()
    try:
        return _client().models.generate_content(model=modele(), contents=contents, config=config)
    except Exception as exc:  # quota (429), clé invalide, réseau, modèle retiré...
        message = str(exc)
        log.warning("Gemini indisponible : %s", message[:300])
        if "429" in message or "RESOURCE_EXHAUSTED" in message:
            raise LLMIndisponible("quota gratuit de Gemini atteint, réessayez plus tard") from exc
        raise LLMIndisponible("Gemini n'a pas répondu") from exc


def _texte(reponse) -> str:
    texte = (reponse.text or "").strip()
    if not texte:
        raise LLMIndisponible("réponse vide de Gemini")
    return texte


def rediger(consigne: str, donnees: dict) -> str:
    """Texte court qui explique des chiffres déjà calculés."""
    contenu = f"{consigne}\n\nDonnées (JSON) :\n{json.dumps(donnees, ensure_ascii=False)}"
    config = types.GenerateContentConfig(
        system_instruction=REGLES, temperature=0.3, max_output_tokens=700
    )
    return _texte(_appeler(contenu, config))


def discuter(
    historique: list[dict], contexte: str, outils: list[Callable]
) -> tuple[str, list[str]]:
    """Réponse de l'assistant ; Gemini peut appeler les `outils` (fonctions Python).

    Renvoie (texte, noms des outils appelés).
    """
    passe = [
        types.Content(
            role="model" if m["role"] == "assistant" else "user",
            parts=[types.Part(text=m["content"])],
        )
        for m in historique[:-1]
    ]
    config = types.GenerateContentConfig(
        system_instruction=f"{REGLES}\n\nContexte de l'utilisateur :\n{contexte}",
        temperature=0.2,
        max_output_tokens=900,
        tools=outils,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(maximum_remote_calls=6),
    )
    if not actif():
        raise LLMIndisponible("assistant non configuré (GEMINI_API_KEY absente)")
    _plafond.prendre()
    try:
        conversation = _client().chats.create(model=modele(), config=config, history=passe)
        reponse = conversation.send_message(historique[-1]["content"])
    except Exception as exc:
        log.warning("Gemini indisponible : %s", str(exc)[:300])
        if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
            raise LLMIndisponible("quota gratuit de Gemini atteint, réessayez plus tard") from exc
        raise LLMIndisponible("Gemini n'a pas répondu") from exc
    appels = []
    for c in conversation.get_history()[len(passe) :]:
        for p in c.parts or []:
            if p.function_call:
                appels.append(p.function_call.name)
    return _texte(reponse), appels
