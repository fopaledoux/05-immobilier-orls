"""Fiche commune : drill-down commune → section cadastrale → vente."""

import math
from dataclasses import replace

import dash
import dash_mantine_components as dmc
import pandas as pd
from dash import Input, Output, State, callback, dcc, html, no_update

from immo import api, fmt
from immo.components import chart_card, empty_state, grid, icon, stat_tile
from immo import config as cfg
from immo.api import Filtres
from immo.figures import barres_sections, carte_ventes, figure_vide, tendance_annuelle_commune

dash.register_page(
    __name__,
    path_template="/commune/<code>",
    name="Fiche commune",
    title=lambda code=None, **_: f"{_nom_commune(code)} · Immo Loiret",
    order=9,
)


def _nom_commune(code):
    try:
        idx = api.communes_index()
        m = idx.loc[idx["code_commune"] == code, "nom_commune"]
        return m.iloc[0] if len(m) else "Commune"
    except Exception:  # hors contexte serveur (enregistrement des pages)
        return "Fiche commune"


MAX_LIGNES = 1500  # au-delà, on n'envoie au navigateur que les ventes récentes

COLONNES_VENTES = [
    {
        "field": "date",
        "headerName": "Date",
        "valueFormatter": {"function": "dateFr(params.value)"},
        "sort": "desc",
    },
    {"field": "type", "headerName": "Type"},
    {"field": "section", "headerName": "Section", "maxWidth": 110},
    {"field": "prix", "headerName": "Prix", "valueFormatter": {"function": "euros(params.value)"}},
    {
        "field": "surface",
        "headerName": "Surface",
        "valueFormatter": {"function": "m2(params.value)"},
    },
    {"field": "pieces", "headerName": "Pièces", "maxWidth": 100},
    {
        "field": "prix_m2",
        "headerName": "€/m²",
        "valueFormatter": {"function": "eurM2(params.value)"},
    },
    {
        "field": "terrain",
        "headerName": "Terrain",
        "valueFormatter": {"function": "m2(params.value)"},
    },
]


def layout(code=None, **_):
    idx = api.communes_index()
    match = idx[idx["code_commune"] == code]
    if match.empty:
        return html.Div(
            [
                dmc.Title("Commune introuvable", order=2, mt="xl"),
                dmc.Text("Aucune vente enregistrée pour ce code commune.", c="dimmed", mb="md"),
                dcc.Link("← Retour aux communes", href="/communes"),
            ]
        )
    nom = match.iloc[0]["nom_commune"]
    return html.Div(
        [
            dcc.Store(id="commune-code", data=code),
            dcc.Store(id="commune-section", data=None),
            html.Div(
                className="page-header",
                children=[
                    dmc.Breadcrumbs(
                        id="commune-crumbs",
                        separator="›",
                        className="breadcrumbs",
                        children=_crumbs(nom, None),
                    ),
                    dcc.Store(id="commune-nom", data=nom),
                    dmc.Title(nom, order=1, className="page-title"),
                    dmc.Text(id="commune-subtitle", className="page-subtitle"),
                ],
            ),
            dmc.SimpleGrid(
                cols={"base": 2, "lg": 4},
                spacing="md",
                className="section",
                children=[
                    stat_tile(
                        "Maison · prix médian au m²",
                        "commune-kpi-maison",
                        "commune-kpi-maison-n",
                        "maison",
                    ),
                    stat_tile(
                        "Appartement · prix médian au m²",
                        "commune-kpi-appart",
                        "commune-kpi-appart-n",
                        "appartement",
                    ),
                    stat_tile(
                        "Maison · prix médian", "commune-kpi-prix", "commune-kpi-prix-detail"
                    ),
                    stat_tile(
                        "Par rapport à la zone (maison, €/m²)",
                        "commune-kpi-ecart",
                        "commune-kpi-ecart-detail",
                    ),
                ],
            ),
            dmc.Group(
                justify="space-between",
                className="section drill-bar",
                children=[
                    dmc.Group(
                        gap="sm",
                        children=[
                            dmc.Text("Type de bien", size="sm", fw=600),
                            dmc.SegmentedControl(
                                id="commune-type",
                                data=["Tous", "Maison", "Appartement"],
                                value="Tous",
                                size="xs",
                                radius="xl",
                            ),
                        ],
                    ),
                    dmc.Button(
                        id="commune-section-clear",
                        children="Toutes les sections",
                        leftSection=icon("tabler:x", 14),
                        variant="light",
                        size="xs",
                        radius="xl",
                        style={"display": "none"},
                    ),
                ],
            ),
            dmc.Grid(
                gutter="md",
                className="section",
                children=[
                    dmc.GridCol(
                        span={"base": 12, "lg": 5},
                        children=dmc.Paper(
                            withBorder=True,
                            className="chart-card",
                            children=[
                                dmc.Text(
                                    "Prix médian au m² par section cadastrale",
                                    className="chart-title",
                                ),
                                dmc.Text(
                                    "Une section = un quartier de quelques rues. Le chiffre indique le nombre "
                                    f"de ventes ; en gris, moins de {cfg.SEUIL_FIABILITE}. Cliquez pour filtrer.",
                                    className="chart-subtitle",
                                ),
                                html.Div(
                                    className="scroll-chart",
                                    children=dcc.Loading(
                                        dcc.Graph(
                                            id="commune-sections",
                                            config={"displayModeBar": False, "responsive": True},
                                        ),
                                        type="circle",
                                        delay_show=300,
                                    ),
                                ),
                            ],
                        ),
                    ),
                    dmc.GridCol(
                        span={"base": 12, "lg": 7},
                        children=chart_card(
                            "Les ventes sur la carte",
                            "commune-points",
                            subtitle="Couleur = prix au m². Cliquez sur un point pour sélectionner sa section.",
                            height=480,
                        ),
                    ),
                ],
            ),
            dmc.Grid(
                gutter="md",
                className="section",
                children=[
                    dmc.GridCol(
                        span={"base": 12, "lg": 8},
                        children=dmc.Paper(
                            withBorder=True,
                            className="chart-card",
                            children=[
                                dmc.Text(id="commune-ventes-titre", className="chart-title"),
                                dmc.Text(
                                    "Cliquez sur une vente pour la comparer aux ventes similaires.",
                                    className="chart-subtitle",
                                    mb="sm",
                                ),
                                grid(
                                    "commune-ventes",
                                    COLONNES_VENTES,
                                    row_id="id",
                                    options={
                                        "rowSelection": {
                                            "mode": "singleRow",
                                            "checkboxes": False,
                                            "enableClickSelection": True,
                                        }
                                    },
                                ),
                            ],
                        ),
                    ),
                    dmc.GridCol(
                        span={"base": 12, "lg": 4},
                        children=dmc.Paper(
                            withBorder=True,
                            className="chart-card sale-detail",
                            children=[
                                dmc.Text("La vente sélectionnée", className="chart-title"),
                                html.Div(
                                    id="commune-vente-detail",
                                    children=empty_state("Sélectionnez une vente dans le tableau."),
                                ),
                            ],
                        ),
                    ),
                ],
            ),
            chart_card(
                "Évolution du prix médian au m²",
                "commune-trend",
                subtitle=f"Point creux : moins de {cfg.SEUIL_FIABILITE} ventes cette année-là (valeur indicative).",
                height=300,
            ),
        ]
    )


def _crumbs(nom, section):
    items = [dcc.Link("Communes", href="/communes"), html.Span(nom)]
    if section:
        items.append(html.Span(f"Section {section}"))
    return items


def _filtres_commune(store) -> Filtres:
    """Sur la fiche, la commune est choisie explicitement : on ignore la zone."""
    return replace(Filtres.from_store(store), zone="loiret")


def _type(t):
    return None if t == "Tous" else t


def _vue_carte(df):
    d = df.dropna(subset=["latitude", "longitude"])
    if d.empty:
        return {"lat": 47.9, "lon": 1.9}, 11
    lat0, lat1 = d["latitude"].quantile([0.02, 0.98])
    lon0, lon1 = d["longitude"].quantile([0.02, 0.98])
    span = max((lat1 - lat0) * 1.45, lon1 - lon0, 0.004)
    zoom = min(max(math.log2(360 / span) - 0.4, 10), 15.5)
    return {"lat": float((lat0 + lat1) / 2), "lon": float((lon0 + lon1) / 2)}, zoom


@callback(
    Output("commune-subtitle", "children"),
    Output("commune-kpi-maison", "children"),
    Output("commune-kpi-maison-n", "children"),
    Output("commune-kpi-appart", "children"),
    Output("commune-kpi-appart-n", "children"),
    Output("commune-kpi-prix", "children"),
    Output("commune-kpi-prix-detail", "children"),
    Output("commune-kpi-ecart", "children"),
    Output("commune-kpi-ecart-detail", "children"),
    Input("filters-store", "data"),
    Input("commune-code", "data"),
)
def maj_kpis(store, code):
    f = Filtres.from_store(store)
    r = api.resume_commune(_filtres_commune(store), code)
    zone = api.kpis(f)

    def bloc(t):
        d = r[t]
        if not d["n"]:
            return "–", "Aucune vente"
        suffixe = "" if d["fiable"] else " · indicatif"
        return fmt.eur_m2(d["pm2_med"]), f"sur {fmt.ventes(d['n'])}{suffixe}"

    m_val, m_det = bloc("Maison")
    a_val, a_det = bloc("Appartement")
    m = r["Maison"]
    prix = fmt.euros(m["prix_med"]) if m["n"] else "–"
    prix_det = f"pour {fmt.m2(m['surf_med'])} (médiane)" if m["n"] else ""
    ecart, ecart_det = "–", "Pas de vente de maison"
    if m["n"] and zone["Maison"]["pm2_med"]:
        e = m["pm2_med"] / zone["Maison"]["pm2_med"] - 1
        ecart = fmt.pct(e, decimales=0)
        ecart_det = (
            f"{'plus cher' if e > 0 else 'moins cher'} que la médiane de la zone "
            f"{cfg.ZONES[f.zone]['label']} ({fmt.eur_m2(zone['Maison']['pm2_med'])})"
        )
    n_sections = r["n_sections"]
    sous_titre = (
        f"{fmt.ventes(r['n'])} de {f.annee_min} à {f.annee_max}, réparties sur {n_sections} "
        f"section{'s' if n_sections > 1 else ''} cadastrale{'s' if n_sections > 1 else ''}."
    )
    return sous_titre, m_val, m_det, a_val, a_det, prix, prix_det, ecart, ecart_det


@callback(
    Output("commune-sections", "figure"),
    Output("commune-sections", "style"),
    Input("filters-store", "data"),
    Input("commune-code", "data"),
    Input("commune-type", "value"),
    Input("commune-section", "data"),
    Input("color-scheme-store", "data"),
)
def maj_sections(store, code, type_, section, scheme):
    f = _filtres_commune(store)
    df = api.stats_sections(f, code, _type(type_))
    fig = barres_sections(df, scheme, section, _type(type_))
    hauteur = max(260, 26 * len(df) + 60)
    fig.update_layout(height=hauteur)
    return fig, {"height": f"{hauteur}px"}


@callback(
    Output("commune-points", "figure"),
    Input("filters-store", "data"),
    Input("commune-code", "data"),
    Input("commune-type", "value"),
    Input("commune-section", "data"),
    Input("color-scheme-store", "data"),
)
def maj_points(store, code, type_, section, scheme):
    f = _filtres_commune(store)
    _, df = api.ventes_commune(f, code, geo=True)
    center, zoom = _vue_carte(df[df["section"] == section] if section else df)
    if _type(type_):
        df = df[df["type"] == type_]
    if df.empty:
        return figure_vide(scheme, "Aucune vente avec ces filtres")
    return carte_ventes(df, scheme, section, center, zoom)


@callback(
    Output("commune-section", "data"),
    Input("commune-sections", "clickData"),
    Input("commune-points", "clickData"),
    Input("commune-section-clear", "n_clicks"),
    State("commune-section", "data"),
    prevent_initial_call=True,
)
def choisir_section(bar_click, point_click, _clear, actuelle):
    trig = dash.ctx.triggered_id
    if trig == "commune-section-clear":
        return None
    if trig == "commune-sections" and bar_click:
        s = bar_click["points"][0].get("y")
        return None if s == actuelle else s
    if trig == "commune-points" and point_click:
        cd = point_click["points"][0].get("customdata")
        return cd[4] if cd else no_update
    return no_update


@callback(
    Output("commune-section-clear", "style"),
    Output("commune-section-clear", "children"),
    Output("commune-crumbs", "children"),
    Input("commune-section", "data"),
    State("commune-nom", "data"),
)
def maj_section_ui(section, nom):
    if not section:
        return {"display": "none"}, "", _crumbs(nom, None)
    return {}, f"Section {section} · voir toutes les sections", _crumbs(nom, section)


@callback(
    Output("commune-ventes", "rowData"),
    Output("commune-ventes-titre", "children"),
    Input("filters-store", "data"),
    Input("commune-code", "data"),
    Input("commune-type", "value"),
    Input("commune-section", "data"),
)
def maj_ventes(store, code, type_, section):
    f = _filtres_commune(store)
    n_total, df = api.ventes_commune(
        f, code, type_=_type(type_), section=section, limit=None if section else MAX_LIGNES
    )
    tronque = n_total > len(df)
    rows = [
        {
            "id": r.id_mutation,
            "date": r.date,
            "type": r.type,
            "section": r.section,
            "prix": r.valeur_fonciere,
            "surface": r.surface_reelle_bati,
            "pieces": (
                None if pd.isna(r.nombre_pieces_principales) else int(r.nombre_pieces_principales)
            ),
            "prix_m2": round(r.prix_m2),
            "terrain": (
                None if pd.isna(r.surface_terrain) or r.surface_terrain == 0 else r.surface_terrain
            ),
        }
        for r in df.itertuples()
    ]
    titre = f"{fmt.ventes(n_total)}" + (f" dans la section {section}" if section else "")
    if tronque:
        titre += (
            f" · les {fmt.entier(len(df))} plus récentes (choisissez une section pour tout voir)"
        )
    return rows, titre


@callback(
    Output("commune-vente-detail", "children"),
    Input("commune-ventes", "selectedRows"),
    State("filters-store", "data"),
    State("commune-code", "data"),
    prevent_initial_call=True,
)
def detail_vente(selected, store, code):
    if not selected:
        return empty_state("Sélectionnez une vente dans le tableau.")
    v = selected[0]
    f = _filtres_commune(store)
    comp = api.comparables_stats(f, code, v["type"], float(v["surface"]), v["id"])
    lignes = [
        dmc.Text(f"{v['type']} · {fmt.m2(v['surface'])} · section {v['section']}", fw=600),
        dmc.Text(
            f"Vendu {fmt.euros(v['prix'])} le {v['date'][8:10]}/{v['date'][5:7]}/{v['date'][:4]}",
            size="sm",
            c="dimmed",
        ),
        html.Div(fmt.eur_m2(v["prix_m2"]), className="stat-value"),
    ]
    if comp["n"] < 5:
        lignes.append(
            empty_state(f"Seulement {comp['n']} vente(s) comparable(s) : comparaison impossible.")
        )
        return dmc.Stack(lignes, gap=4)
    med, q1, q3 = comp["pm2_med"], comp["pm2_q1"], comp["pm2_q3"]
    ecart = v["prix_m2"] / med - 1
    if v["prix_m2"] > q3:
        verdict, couleur = "Plus cher que la plupart des ventes similaires", "red"
    elif v["prix_m2"] < q1:
        verdict, couleur = "Moins cher que la plupart des ventes similaires", "teal"
    else:
        verdict, couleur = "Dans la norme des ventes similaires", "gray"
    lignes += [
        dmc.Badge(
            verdict,
            color=couleur,
            variant="light",
            size="lg",
            mt="sm",
            radius="sm",
            className="badge-wrap",
        ),
        dmc.Text(
            [
                html.Strong(fmt.pct(ecart, decimales=0)),
                f" par rapport à la médiane de {fmt.ventes(comp['n'])} comparables ({fmt.eur_m2(med)}).",
            ],
            size="sm",
            mt="sm",
        ),
        dmc.Text(
            f"La moitié des comparables se situe entre {fmt.eur_m2(q1)} et {fmt.eur_m2(q3)}.",
            size="sm",
            c="dimmed",
        ),
        dmc.Text(
            f"Comparables : {v['type'].lower()}s de la commune, surface entre {fmt.m2(v['surface'] * 0.8)} et "
            f"{fmt.m2(v['surface'] * 1.2)}, mêmes filtres. DVF ne dit rien de l'état ni du DPE.",
            size="xs",
            c="dimmed",
            mt="sm",
        ),
    ]
    return dmc.Stack(lignes, gap=4)


@callback(
    Output("commune-trend", "figure"),
    Input("filters-store", "data"),
    Input("commune-code", "data"),
    Input("color-scheme-store", "data"),
)
def maj_tendance(store, code, scheme):
    df = api.annuel_commune(_filtres_commune(store), code)
    if df.empty:
        return figure_vide(scheme, "Aucune vente avec ces filtres")
    return tendance_annuelle_commune(df, scheme)
