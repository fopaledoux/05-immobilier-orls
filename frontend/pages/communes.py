"""Communes : prix médian au m², maison contre appartement, et classement."""

import dash
import dash_mantine_components as dmc
from dash import Input, Output, callback, dcc, html, no_update

from immo import api, fmt
from immo.components import chart_card, grid, icon, legende_fiabilite, page_header, type_control
from immo import config as cfg
from immo.api import Filtres
from immo.figures import carte_communes, maison_vs_appart

dash.register_page(__name__, path="/communes", name="Communes", order=2)

_fiab = {"cellClassRules": {"cell-indicatif": "params.value < 30"}}
COLONNES = [
    {
        "field": "nom_commune",
        "headerName": "Commune",
        "minWidth": 170,
        "pinned": "left",
        "cellClass": "cell-link",
    },
    {
        "headerName": "Maison",
        "children": [
            {
                "field": "pm2_med_maison",
                "headerName": "€/m²",
                "valueFormatter": {"function": "eurM2(params.value)"},
            },
            {
                "field": "prix_med_maison",
                "headerName": "Prix médian",
                "valueFormatter": {"function": "euros(params.value)"},
            },
            {
                "field": "n_maison",
                "headerName": "Ventes",
                "valueFormatter": {"function": "entier(params.value)"},
                **_fiab,
            },
        ],
    },
    {
        "headerName": "Appartement",
        "children": [
            {
                "field": "pm2_med_appart",
                "headerName": "€/m²",
                "valueFormatter": {"function": "eurM2(params.value)"},
            },
            {
                "field": "prix_med_appart",
                "headerName": "Prix médian",
                "valueFormatter": {"function": "euros(params.value)"},
            },
            {
                "field": "n_appart",
                "headerName": "Ventes",
                "valueFormatter": {"function": "entier(params.value)"},
                **_fiab,
            },
        ],
    },
    {
        "field": "n_total",
        "headerName": "Total ventes",
        "sort": "desc",
        "valueFormatter": {"function": "entier(params.value)"},
    },
]


def layout(**_):
    communes = api.communes_index()
    return html.Div(
        [
            dcc.Location(id="communes-nav", refresh="callback-nav"),
            page_header(
                "Combien coûte le m², commune par commune ?",
                "Prix médian au m² des ventes de 2021 à 2025. Les communes avec moins de "
                f"{cfg.SEUIL_FIABILITE} ventes restent grises : leur prix n'est qu'indicatif.",
                eyebrow="Communes",
                extra=dmc.Select(
                    id="communes-search",
                    placeholder="Ouvrir la fiche d'une commune…",
                    data=[
                        {"value": r.code_commune, "label": r.nom_commune}
                        for r in communes.itertuples()
                    ],
                    searchable=True,
                    clearable=True,
                    leftSection=icon("tabler:search", 16),
                    nothingFoundMessage="Aucune commune",
                    maw=360,
                    mt="md",
                ),
            ),
            dmc.Grid(
                gutter="md",
                className="section",
                children=[
                    dmc.GridCol(
                        span={"base": 12, "lg": 7},
                        children=chart_card(
                            "Prix médian au m²",
                            "communes-map",
                            subtitle="Cliquez sur une commune pour ouvrir sa fiche.",
                            controls=type_control("communes-map-type"),
                            height=520,
                            footer=legende_fiabilite(),
                        ),
                    ),
                    dmc.GridCol(
                        span={"base": 12, "lg": 5},
                        children=chart_card(
                            "Maison ou appartement : l'écart au m²",
                            "communes-dumbbell",
                            subtitle=f"Les 15 communes les plus actives ayant {cfg.SEUIL_FIABILITE} ventes de chaque type.",
                            height=520,
                        ),
                    ),
                ],
            ),
            dmc.Paper(
                withBorder=True,
                className="chart-card section",
                children=[
                    dmc.Text("Toutes les communes de la zone", className="chart-title"),
                    dmc.Text(
                        f"Nombre de ventes en gris : moins de {cfg.SEUIL_FIABILITE}, prix indicatif. "
                        "Cliquez sur un nom pour la fiche commune.",
                        className="chart-subtitle",
                        mb="sm",
                    ),
                    grid("communes-grid", COLONNES, row_id="code_commune", page_size=15),
                ],
            ),
        ]
    )


@callback(
    Output("communes-map", "figure"),
    Input("filters-store", "data"),
    Input("communes-map-type", "value"),
    Input("color-scheme-store", "data"),
)
def maj_carte(store, type_, scheme):
    f = Filtres.from_store(store)
    stats = api.stats_communes(f, type_)
    return carte_communes(
        stats,
        scheme,
        f.zone,
        valeur="pm2_med",
        titre_echelle="€/m²",
        format_valeur=fmt.entier,
        lignes_hover=lambda r: [
            f"{type_} : <b>{fmt.eur_m2(r['pm2_med'])}</b>",
            f"Prix médian {fmt.euros(r['prix_med'])} · surface {fmt.m2(r['surf_med'])}",
            fmt.ventes(r["n"]),
        ],
    )


@callback(
    Output("communes-dumbbell", "figure"),
    Output("communes-grid", "rowData"),
    Input("filters-store", "data"),
    Input("color-scheme-store", "data"),
)
def maj_comparaison(store, scheme):
    f = Filtres.from_store(store)
    df = api.stats_communes_comparees(f)
    cols = [
        "code_commune",
        "nom_commune",
        "pm2_med_maison",
        "prix_med_maison",
        "n_maison",
        "pm2_med_appart",
        "prix_med_appart",
        "n_appart",
        "n_total",
    ]
    rows = df[cols].astype(object).where(df[cols].notna(), None).to_dict("records")
    return maison_vs_appart(df, scheme), rows


@callback(
    Output("communes-nav", "href"),
    Input("communes-map", "clickData"),
    Input("communes-grid", "cellClicked"),
    Input("communes-search", "value"),
    prevent_initial_call=True,
)
def ouvrir_commune(click, cell, recherche):
    trig = dash.ctx.triggered_id
    if trig == "communes-map" and click and click.get("points"):
        code = click["points"][0].get("location")
        return f"/commune/{code}" if code else no_update
    if trig == "communes-grid" and cell and cell.get("colId") == "nom_commune":
        return f"/commune/{cell.get('rowId')}"
    if trig == "communes-search" and recherche:
        return f"/commune/{recherche}"
    return no_update
