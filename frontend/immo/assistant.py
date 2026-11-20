"""Assistant (Gemini, via l'API) : bulle de discussion et rendu des textes.

- Le LLM est appelé par le backend, qui seul détient la clé ; ici on n'envoie
  que la question, l'historique récent et le contexte de la page.
- Garde-fou « par visiteur » : le quota (20 demandes par 24 h) est compté par
  l'API, par IP du visiteur : il vaut pour tous ses onglets, fenêtres et
  navigateurs. Ici, on ne fait qu'afficher l'état renvoyé (store `llm-quota`).
- Repli : si l'assistant ne répond pas, on l'indique sans masquer les chiffres.
"""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update

from immo import api
from immo.api import Filtres
from immo.components import icon

HISTORIQUE_MAX = 10  # messages renvoyés au modèle

SUGGESTIONS = [
    "Avec 280 000 € frais compris, où trouver une maison de 100 m² ?",
    "Les prix ont-ils baissé à Olivet depuis 2022 ?",
    "Quel est le quartier le moins cher d'Orléans pour un appartement ?",
]

LIBELLES_OUTILS = {
    "chercher_commune": "communes",
    "prix_commune": "prix de la commune",
    "prix_par_quartier": "prix par quartier",
    "communes_pour_budget": "simulation de budget",
    "classement_communes": "classement des communes",
    "evolution_des_prix": "tendances",
    "evolution_commune": "tendance de la commune",
    "evaluer_un_prix": "ventes comparables",
}


# --------------------------------------------------------------------------- #
# Rendu partagé (explications de prix, conseil budget)
# --------------------------------------------------------------------------- #
def _heure_recharge(quota: dict | None) -> str:
    """« vers 14 h 05 » (heure de Paris) : quand la prochaine demande se libère."""
    iso = (quota or {}).get("prochaine_recharge")
    if not iso:
        return "dans 24 heures au plus"
    from datetime import datetime
    from zoneinfo import ZoneInfo

    instant = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(
        ZoneInfo("Europe/Paris")
    )
    jour = "" if instant.date() == datetime.now(ZoneInfo("Europe/Paris")).date() else " demain"
    return f"{jour} vers {instant:%H} h {instant:%M}".strip()


def message_limite(quota: dict | None) -> str:
    limite = (quota or {}).get("limite", 20)
    heures = (quota or {}).get("fenetre_heures", 24)
    return (
        f"Vous avez utilisé vos {limite} demandes à l'assistant sur {heures} heures "
        f"(tous onglets et navigateurs confondus). Prochaine demande disponible "
        f"{_heure_recharge(quota)}."
    )


def limite_atteinte(quota: dict | None = None):
    return dmc.Alert(
        message_limite(quota)
        + " Les chiffres et graphiques du tableau de bord restent disponibles.",
        color="gray",
        icon=icon("tabler:hourglass"),
        title="Limite atteinte",
    )


def texte_assistant(res: dict | None, erreur: str | None = None):
    """Texte rédigé par l'assistant, ou message de repli s'il n'a pas répondu."""
    texte = (res or {}).get("texte")
    erreur = erreur or (res or {}).get("erreur")
    if not texte:
        return dmc.Alert(
            f"L'assistant n'a pas pu répondre ({erreur or 'raison inconnue'}). "
            "Les chiffres affichés restent valables.",
            color="gray",
            icon=icon("tabler:robot-off"),
        )
    return dmc.Paper(
        className="assistant-texte",
        children=[
            dmc.Group(
                gap=6,
                mb=6,
                children=[
                    icon("tabler:sparkles", 16, className="assistant-icone"),
                    dmc.Text("L'avis de l'assistant", size="sm", fw=700),
                ],
            ),
            dcc.Markdown(texte, className="assistant-markdown"),
        ],
    )


def appeler(fonction, *args):
    """Appelle l'assistant ; le quota est vérifié et décompté par l'API.

    Renvoie (composant, état du quota pour le store `llm-quota`).
    """
    try:
        res = fonction(*args)
    except api.ApiError as exc:
        return texte_assistant(None, f"API injoignable : {exc}"), no_update
    quota = res.get("quota") or no_update
    if res.get("limite_atteinte"):
        return limite_atteinte(res.get("quota")), quota
    return texte_assistant(res), quota


# --------------------------------------------------------------------------- #
# Bulle de discussion (présente sur toutes les pages)
# --------------------------------------------------------------------------- #
def bulle():
    return html.Div(
        [
            dcc.Store(id="assistant-historique", storage_type="session", data=[]),
            dcc.Store(id="assistant-attente", data=0),
            dmc.Affix(
                position={"bottom": 24, "right": 24},
                zIndex=150,  # sous le panneau (Drawer : 200), qui le recouvre une fois ouvert
                children=dmc.Tooltip(
                    label="Poser une question à l'assistant",
                    position="left",
                    children=dmc.ActionIcon(
                        icon("tabler:message-chatbot", 28),
                        id="assistant-ouvrir",
                        size=58,
                        radius="xl",
                        variant="filled",
                        className="assistant-bouton",
                        **{"aria-label": "Ouvrir l'assistant"},
                    ),
                ),
            ),
            dmc.Drawer(
                id="assistant-panneau",
                position="right",
                size="md",
                padding="md",
                title=dmc.Group(
                    gap="xs",
                    children=[
                        icon("tabler:sparkles", 20, className="assistant-icone"),
                        dmc.Text("Assistant Immo Loiret", fw=700),
                    ],
                ),
                children=dmc.Stack(
                    className="assistant-corps",
                    gap="sm",
                    children=[
                        dmc.Text(
                            "Posez une question sur les prix, les communes, les quartiers ou votre "
                            "budget : l'assistant répond avec les ventes réelles du Loiret.",
                            size="sm",
                            c="dimmed",
                        ),
                        html.Div(id="assistant-messages", className="assistant-messages"),
                        html.Div(
                            id="assistant-ecrit",
                            className="assistant-ecrit",
                            style={"display": "none"},
                            children=[
                                dmc.Loader(size="xs", type="dots"),
                                "L'assistant consulte les données…",
                            ],
                        ),
                        dmc.Textarea(
                            id="assistant-saisie",
                            placeholder="Votre question…",
                            autosize=True,
                            minRows=2,
                            maxRows=5,
                            inputProps={"maxLength": 1000},
                        ),
                        dmc.Group(
                            justify="space-between",
                            children=[
                                dmc.Text(id="assistant-compteur", size="xs", c="dimmed"),
                                dmc.Group(
                                    gap="xs",
                                    children=[
                                        dmc.Button(
                                            "Effacer",
                                            id="assistant-effacer",
                                            variant="subtle",
                                            color="gray",
                                            size="xs",
                                        ),
                                        dmc.Button(
                                            "Envoyer",
                                            id="assistant-envoyer",
                                            size="xs",
                                            rightSection=icon("tabler:send", 14),
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
            ),
        ]
    )


def _bulle_message(m: dict):
    if m["role"] == "user":
        return html.Div(m["content"], className="msg msg--user")
    if m.get("erreur"):
        return html.Div(
            [icon("tabler:robot-off", 16), f" {m['content']}"], className="msg msg--erreur"
        )
    sources = [LIBELLES_OUTILS.get(o, o) for o in dict.fromkeys(m.get("outils") or [])]
    return html.Div(
        className="msg msg--assistant",
        children=[
            dcc.Markdown(m["content"], className="assistant-markdown"),
            (
                html.Div(f"Données consultées : {', '.join(sources)}", className="msg-sources")
                if sources
                else None
            ),
        ],
    )


def _contexte(pathname: str | None) -> str:
    chemin = pathname or "/"
    pages = {
        "/": "vue d'ensemble",
        "/budget": "simulation de budget",
        "/communes": "comparaison des communes",
        "/tendances": "tendances des prix",
        "/evaluer": "évaluation d'un prix demandé",
        "/methodologie": "méthodologie",
    }
    if chemin.startswith("/commune/"):
        code = chemin.rsplit("/", 1)[-1]
        try:
            idx = api.communes_index()
            nom = idx.loc[idx["code_commune"] == code, "nom_commune"].iloc[0]
            return f"Page : fiche de la commune {nom} (code INSEE {code})."
        except (api.ApiError, IndexError):
            return f"Page : fiche de la commune de code INSEE {code}."
    return f"Page : {pages.get(chemin, chemin)}."


@callback(
    Output("assistant-panneau", "opened"),
    Input("assistant-ouvrir", "n_clicks"),
    prevent_initial_call=True,
)
def ouvrir(clic):
    return True if clic else no_update


@callback(
    Output("llm-quota", "data"),
    Input("assistant-panneau", "opened"),
    prevent_initial_call=True,
)
def lire_quota(ouvert):
    """À l'ouverture du panneau : demandes restantes selon l'API (toutes sessions confondues)."""
    if not ouvert:
        return no_update
    try:
        return api.quota_visiteur()
    except api.ApiError:
        return no_update


@callback(
    Output("assistant-messages", "children"),
    Output("assistant-compteur", "children"),
    Input("assistant-historique", "data"),
    Input("llm-quota", "data"),
)
def afficher(historique, quota):
    if quota and "restantes" in quota:
        reste = quota["restantes"]
        compteur = (
            f"{reste} demande{'s' if reste > 1 else ''} restante{'s' if reste > 1 else ''} "
            f"sur {quota['limite']} (24 h)"
        )
    else:
        compteur = ""
    if not historique:
        return (
            html.Div(
                [
                    dmc.Text("Exemples :", size="xs", c="dimmed", mb=4),
                    *[
                        dmc.Button(
                            q,
                            id={"type": "assistant-suggestion", "index": i},
                            variant="light",
                            size="xs",
                            radius="xl",
                            className="assistant-suggestion",
                        )
                        for i, q in enumerate(SUGGESTIONS)
                    ],
                ],
                className="assistant-suggestions",
            ),
            compteur,
        )
    return [_bulle_message(m) for m in historique], compteur


@callback(
    Output("assistant-historique", "data", allow_duplicate=True),
    Output("assistant-saisie", "value"),
    Output("assistant-attente", "data"),
    Input("assistant-envoyer", "n_clicks"),
    Input({"type": "assistant-suggestion", "index": ALL}, "n_clicks"),
    Input("assistant-effacer", "n_clicks"),
    State("assistant-saisie", "value"),
    State("assistant-historique", "data"),
    State("assistant-attente", "data"),
    State("llm-quota", "data"),
    prevent_initial_call=True,
)
def poser(_envoi, suggestions, _effacer, saisie, historique, attente, quota):
    """Étape 1 (immédiate) : affiche la question, puis déclenche la réponse."""
    trig = ctx.triggered_id
    if not ctx.triggered or not ctx.triggered[0]["value"]:
        return no_update, no_update, no_update  # montage d'un bouton (n_clicks = 0), pas un clic
    if trig == "assistant-effacer":
        return [], "", no_update
    if isinstance(trig, dict):
        if not any(suggestions):
            return no_update, no_update, no_update
        question = SUGGESTIONS[trig["index"]]
    else:
        question = (saisie or "").strip()
    if not question:
        return no_update, no_update, no_update
    historique = list(historique or []) + [{"role": "user", "content": question}]
    if quota and quota.get("restantes") == 0:
        # Affichage immédiat ; l'API refuserait de toute façon (elle seule fait foi)
        historique.append({"role": "assistant", "erreur": True, "content": message_limite(quota)})
        return historique, "", no_update
    return historique, "", (attente or 0) + 1


@callback(
    Output("assistant-historique", "data", allow_duplicate=True),
    Output("llm-quota", "data", allow_duplicate=True),
    Input("assistant-attente", "data"),
    State("assistant-historique", "data"),
    State("filters-store", "data"),
    State("_pages_location", "pathname"),
    running=[(Output("assistant-ecrit", "style"), {}, {"display": "none"})],
    prevent_initial_call=True,
)
def repondre(_attente, historique, store, pathname):
    """Étape 2 : interroge l'assistant (via l'API) et ajoute sa réponse."""
    historique = list(historique or [])
    if not historique or historique[-1]["role"] != "user":
        return no_update, no_update
    messages = [
        {"role": m["role"], "content": m["content"]} for m in historique if not m.get("erreur")
    ][-HISTORIQUE_MAX:]
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    try:
        res = api.chat(Filtres.from_store(store), messages, _contexte(pathname))
    except api.ApiError as exc:
        res = {"reponse": None, "erreur": f"API injoignable : {exc}"}
    quota = res.get("quota") or no_update
    if res.get("reponse"):
        historique.append(
            {"role": "assistant", "content": res["reponse"], "outils": res.get("outils")}
        )
        return historique, quota
    if res.get("limite_atteinte"):
        message = message_limite(res.get("quota"))
    else:
        message = f"L'assistant ne peut pas répondre pour le moment ({res.get('erreur')})."
    historique.append({"role": "assistant", "erreur": True, "content": message})
    return historique, quota
