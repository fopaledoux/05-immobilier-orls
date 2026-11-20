"""Évaluer un prix : situer une annonce parmi les ventes comparables, puis l'expliquer."""

from dataclasses import replace

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html, no_update

from immo import api, assistant, fmt
from immo import config as cfg
from immo.api import Filtres
from immo.components import chart_card, icon, page_header
from immo.figures import distribution_prix

dash.register_page(__name__, path="/evaluer", name="Évaluer un prix", order=4)


def layout(**_):
    communes = api.communes_index()
    return html.Div(
        [
            dcc.Store(id="evaluer-demande"),
            page_header(
                "Ce prix est-il raisonnable ?",
                "Saisissez une annonce : on la compare aux ventes réellement conclues pour des biens "
                "semblables dans la même commune (même type, surface à ±20 %).",
                eyebrow="Évaluer un prix",
            ),
            dmc.Paper(
                withBorder=True,
                className="controls-card section",
                children=[
                    dmc.SimpleGrid(
                        cols={"base": 1, "sm": 2, "lg": 4},
                        spacing="lg",
                        children=[
                            dmc.Select(
                                id="evaluer-commune",
                                label="Commune",
                                data=[
                                    {"value": r.code_commune, "label": r.nom_commune}
                                    for r in communes.itertuples()
                                ],
                                value="45234",
                                searchable=True,
                                allowDeselect=False,
                                nothingFoundMessage="Aucune commune",
                                leftSection=icon("tabler:map-pin", 16),
                            ),
                            html.Div(
                                [
                                    dmc.Text("Type de bien", size="sm", fw=500, mb=4),
                                    dmc.SegmentedControl(
                                        id="evaluer-type",
                                        data=list(cfg.TYPES),
                                        value="Appartement",
                                        fullWidth=True,
                                    ),
                                ]
                            ),
                            dmc.NumberInput(
                                id="evaluer-surface",
                                label="Surface habitable",
                                value=60,
                                min=9,
                                max=400,
                                suffix=" m²",
                                allowNegative=False,
                            ),
                            dmc.NumberInput(
                                id="evaluer-prix",
                                label="Prix demandé",
                                value=180_000,
                                min=10_000,
                                max=5_000_000,
                                step=1_000,
                                thousandSeparator=" ",
                                suffix=" €",
                                allowNegative=False,
                                allowDecimal=False,
                            ),
                        ],
                    ),
                    dmc.Group(
                        justify="space-between",
                        mt="md",
                        children=[
                            dmc.Text(
                                "Les annonces incluent souvent les frais d'agence, que les prix de "
                                "vente DVF n'intègrent pas toujours.",
                                size="xs",
                                c="dimmed",
                            ),
                            dmc.Button(
                                "Évaluer",
                                id="evaluer-lancer",
                                leftSection=icon("tabler:scale", 16),
                            ),
                        ],
                    ),
                ],
            ),
            dcc.Loading(html.Div(id="evaluer-resultat", className="section"), type="dot"),
            html.Div(
                id="evaluer-zone-assistant",
                className="section",
                style={"display": "none"},
                children=[
                    dmc.Button(
                        "Demander l'avis de l'assistant",
                        id="evaluer-expliquer",
                        variant="light",
                        leftSection=icon("tabler:sparkles", 16),
                    ),
                    dcc.Loading(
                        html.Div(id="evaluer-explication", className="section"), type="dot"
                    ),
                ],
            ),
        ]
    )


@callback(
    Output("evaluer-resultat", "children"),
    Output("evaluer-demande", "data"),
    Output("evaluer-zone-assistant", "style"),
    Output("evaluer-explication", "children"),
    Input("evaluer-lancer", "n_clicks"),
    Input("filters-store", "data"),
    Input("color-scheme-store", "data"),
    State("evaluer-commune", "value"),
    State("evaluer-type", "value"),
    State("evaluer-surface", "value"),
    State("evaluer-prix", "value"),
)
def evaluer(_clic, store, scheme, code, type_, surface, prix):
    if not (code and surface and prix):
        return (
            dmc.Alert("Renseignez la commune, la surface et le prix.", color="gray"),
            None,
            {"display": "none"},
            None,
        )
    f = replace(Filtres.from_store(store), zone="loiret")
    e = api.evaluer(f, code, type_, float(surface), float(prix))
    demande = {"code": code, "type": type_, "surface": float(surface), "prix": float(prix)}
    if not e["evaluable"]:
        return (
            dmc.Alert(
                f"Seulement {e['n']} vente(s) comparable(s) ({type_.lower()}s de "
                f"{fmt.m2(e['surf_min'])} à {fmt.m2(e['surf_max'])}) : pas assez pour juger ce "
                "prix. Essayez une commune voisine plus active.",
                color="gray",
                title="Comparaison impossible",
                icon=icon("tabler:info-circle"),
            ),
            None,
            {"display": "none"},
            None,
        )
    couleur = {"au-dessus": "red", "en dessous": "teal", "dans la norme": "blue"}[e["position"]]
    titre = {
        "au-dessus": "Plus cher que la plupart des ventes comparables",
        "en dessous": "Moins cher que la plupart des ventes comparables",
        "dans la norme": "Dans la norme des ventes comparables",
    }[e["position"]]

    def tuile(label, valeur, detail):
        return dmc.Paper(
            withBorder=True,
            className="stat-tile",
            children=[
                dmc.Text(label, className="stat-label"),
                html.Div(valeur, className="stat-value"),
                dmc.Text(detail, className="stat-detail"),
            ],
        )

    fiabilite = "" if e["fiable"] else " · indicatif (moins de 30 ventes)"
    resultat = html.Div(
        [
            dmc.Alert(
                [
                    html.Strong(fmt.pct(e["ecart"], decimales=0)),
                    f" par rapport au prix médian au m² des {fmt.ventes(e['n'])} comparables ; "
                    f"{fmt.pct(e['rang'], signe=False, decimales=0)} d'entre elles se sont vendues "
                    "moins cher au m².",
                ],
                title=titre,
                color=couleur,
                icon=icon("tabler:scale", 22),
                className="verdict",
            ),
            dmc.SimpleGrid(
                cols={"base": 2, "lg": 4},
                spacing="md",
                className="section",
                children=[
                    tuile(
                        "Ce bien",
                        fmt.eur_m2(e["pm2"]),
                        f"{fmt.euros(e['prix'])} pour {fmt.m2(e['surface'])}",
                    ),
                    tuile(
                        "Médiane des comparables",
                        fmt.eur_m2(e["pm2_med"]),
                        f"sur {fmt.ventes(e['n'])}{fiabilite}",
                    ),
                    tuile(
                        "Moitié des comparables",
                        f"{fmt.entier(e['pm2_q1'])} – {fmt.eur_m2(e['pm2_q3'])}",
                        "entre le 1er et le 3e quartile",
                    ),
                    tuile(
                        "Prix au niveau de la médiane",
                        fmt.euros(round(e["prix_equivalent"], -2)),
                        f"soit {fmt.euros(round(e['prix'] - e['prix_equivalent'], -2))} d'écart",
                    ),
                ],
            ),
            html.Div(
                className="section",
                children=chart_card(
                    "Où se situe ce prix parmi les ventes comparables ?",
                    "evaluer-graphique",
                    subtitle=f"{type_}s de la commune entre {fmt.m2(e['surf_min'])} et "
                    f"{fmt.m2(e['surf_max'])}, {Filtres.from_store(store).annee_min}-"
                    f"{Filtres.from_store(store).annee_max}.",
                    height=320,
                ),
            ),
            dcc.Store(
                id="evaluer-figure-data",
                data={"e": {k: e[k] for k in ("valeurs", "pm2", "pm2_med")}},
            ),
        ]
    )
    return resultat, demande, {}, None


@callback(
    Output("evaluer-graphique", "figure"),
    Input("evaluer-figure-data", "data"),
    Input("color-scheme-store", "data"),
)
def graphique(donnees, scheme):
    e = donnees["e"]
    return distribution_prix(e["valeurs"], e["pm2"], e["pm2_med"], scheme)


@callback(
    Output("evaluer-explication", "children", allow_duplicate=True),
    Output("llm-usage", "data", allow_duplicate=True),
    Input("evaluer-expliquer", "n_clicks"),
    State("evaluer-demande", "data"),
    State("filters-store", "data"),
    State("llm-usage", "data"),
    prevent_initial_call=True,
)
def expliquer(_clic, demande, store, usage):
    if not _clic or not demande:  # n_clicks vaut 0 au montage du bouton : pas un clic
        return no_update, no_update
    f = Filtres.from_store(store)
    return assistant.appeler(
        usage,
        api.expliquer_prix,
        f,
        demande["code"],
        demande["type"],
        demande["surface"],
        demande["prix"],
        "annonce",
    )
