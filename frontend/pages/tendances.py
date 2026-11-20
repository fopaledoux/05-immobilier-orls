"""Tendances : les prix ont-ils baissé depuis la hausse des taux de 2022, et où ?"""

import dash
import dash_mantine_components as dmc
from dash import Input, Output, callback, dcc, html, no_update

from immo import api, fmt
from immo.components import chart_card, legende_fiabilite, page_header, stat_tile, type_control
from immo import config as cfg
from immo.api import Filtres
from immo.figures import barres_evolution, carte_communes, tendance_trimestrielle, volumes_annuels

dash.register_page(__name__, path="/tendances", name="Tendances", order=3)


def _av():
    return f"{cfg.PERIODE_AVANT[0]}-{cfg.PERIODE_AVANT[1]}"


def _ap():
    return f"{cfg.PERIODE_APRES[0]}-{cfg.PERIODE_APRES[1]}"


def layout(**_):
    return html.Div(
        [
            dcc.Location(id="tendances-nav", refresh="callback-nav"),
            page_header(
                "Les prix ont-ils baissé depuis la hausse des taux ?",
                f"On compare {_av()} (avant la remontée des taux, été 2022) à {_ap()}. "
                "Ces graphiques couvrent toujours les 5 années, quel que soit le filtre d'années.",
                eyebrow="Tendances",
            ),
            dmc.SimpleGrid(
                cols={"base": 2, "lg": 4},
                spacing="md",
                className="section",
                children=[
                    stat_tile(
                        "Maison · €/m² médian", "tend-maison-pm2", "tend-maison-pm2-d", "maison"
                    ),
                    stat_tile(
                        "Appartement · €/m² médian",
                        "tend-appart-pm2",
                        "tend-appart-pm2-d",
                        "appartement",
                    ),
                    stat_tile("Maison · ventes par an", "tend-maison-vol", "tend-maison-vol-d"),
                    stat_tile(
                        "Appartement · ventes par an", "tend-appart-vol", "tend-appart-vol-d"
                    ),
                ],
            ),
            dmc.Grid(
                gutter="md",
                className="section",
                children=[
                    dmc.GridCol(
                        span={"base": 12, "lg": 7},
                        children=chart_card(
                            "Prix médian au m² sur 12 mois glissants",
                            "tend-trend",
                            subtitle="Chaque point : médiane des ventes des 12 mois précédents, toutes communes de la zone.",
                            height=360,
                        ),
                    ),
                    dmc.GridCol(
                        span={"base": 12, "lg": 5},
                        children=chart_card(
                            "Nombre de ventes par an",
                            "tend-volumes",
                            subtitle="Un marché qui ralentit : moins de choix, mais plus de marge de négociation.",
                            height=360,
                        ),
                    ),
                ],
            ),
            dmc.Grid(
                gutter="md",
                className="section",
                children=[
                    dmc.GridCol(
                        span={"base": 12, "lg": 7},
                        children=chart_card(
                            f"Variation du €/m² médian, {_av()} → {_ap()}",
                            "tend-map",
                            subtitle=f"Bleu : baisse · rouge : hausse. Gris : moins de {cfg.SEUIL_FIABILITE} ventes sur l'une des périodes.",
                            controls=type_control("tend-type"),
                            height=480,
                            footer=legende_fiabilite(),
                        ),
                    ),
                    dmc.GridCol(
                        span={"base": 12, "lg": 5},
                        children=chart_card(
                            "Les plus fortes baisses et hausses",
                            "tend-bars",
                            subtitle=f"Communes avec au moins {cfg.SEUIL_FIABILITE} ventes sur chaque période.",
                            height=480,
                        ),
                    ),
                ],
            ),
        ]
    )


@callback(
    Output("tend-maison-pm2", "children"),
    Output("tend-maison-pm2-d", "children"),
    Output("tend-appart-pm2", "children"),
    Output("tend-appart-pm2-d", "children"),
    Output("tend-maison-vol", "children"),
    Output("tend-maison-vol-d", "children"),
    Output("tend-appart-vol", "children"),
    Output("tend-appart-vol-d", "children"),
    Input("filters-store", "data"),
)
def maj_kpis(store):
    evo = api.evolution_globale(Filtres.from_store(store))
    out = []
    for t in ("Maison", "Appartement"):
        e = evo.get(t)
        if not e:
            out += ["–", "Pas assez de ventes"]
            continue
        out += [
            fmt.pct(e["pm2_var"]),
            f"{fmt.eur_m2(e['pm2_avant'])} → {fmt.eur_m2(e['pm2_apres'])}",
        ]
    for t in ("Maison", "Appartement"):
        e = evo.get(t)
        if not e:
            out += ["–", ""]
            continue
        out += [
            fmt.pct(e["ventes_var"], decimales=0),
            f"{fmt.entier(e['ventes_an_avant'])} → {fmt.entier(e['ventes_an_apres'])} ventes/an",
        ]
    return out


@callback(
    Output("tend-trend", "figure"),
    Output("tend-volumes", "figure"),
    Input("filters-store", "data"),
    Input("color-scheme-store", "data"),
)
def maj_courbes(store, scheme):
    f = Filtres.from_store(store)
    return (
        tendance_trimestrielle(api.stats_trimestrielles(f), scheme),
        volumes_annuels(api.stats_annuelles(f), scheme),
    )


@callback(
    Output("tend-map", "figure"),
    Output("tend-bars", "figure"),
    Input("filters-store", "data"),
    Input("tend-type", "value"),
    Input("color-scheme-store", "data"),
)
def maj_carte(store, type_, scheme):
    f = Filtres.from_store(store)
    df = api.evolution_communes(f, type_)
    fig = carte_communes(
        df,
        scheme,
        f.zone,
        valeur="var",
        titre_echelle="Variation",
        format_valeur=lambda v: fmt.pct(v, decimales=0),
        lignes_hover=lambda r: [
            f"{type_} : <b>{fmt.pct(r['var'])}</b>",
            f"{_av()} : {fmt.eur_m2(r['pm2_med_avant'])} ({fmt.ventes(r['n_avant'])})",
            f"{_ap()} : {fmt.eur_m2(r['pm2_med_apres'])} ({fmt.ventes(r['n_apres'])})",
        ],
        divergente=True,
    )
    return fig, barres_evolution(df, scheme)


@callback(
    Output("tendances-nav", "href"),
    Input("tend-map", "clickData"),
    prevent_initial_call=True,
)
def ouvrir_commune(click):
    if not click or not click.get("points"):
        return no_update
    code = click["points"][0].get("location")
    return f"/commune/{code}" if code else no_update
