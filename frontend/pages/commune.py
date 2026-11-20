"""Fiche commune : drill-down commune → quartier (IRIS) → vente, ou autour d'une adresse."""

from dataclasses import replace

import dash
import dash_mantine_components as dmc
import pandas as pd
from dash import Input, Output, State, callback, dcc, html, no_update

from immo import adresse, api, assistant, fmt
from immo import config as cfg
from immo.api import Filtres
from immo.components import chart_card, empty_state, grid, icon, stat_tile
from immo.figures import (
    barres_quartiers,
    carte_autour,
    carte_quartiers,
    carte_ventes,
    figure_vide,
    tendance_annuelle_commune,
    vue_geo,
)

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
    {"field": "quartier", "headerName": "Quartier", "minWidth": 170},
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
    {
        "field": "section",
        "headerName": "Section cad.",
        "maxWidth": 120,
        "headerTooltip": "Section cadastrale : découpage fiscal, pour les utilisateurs avertis",
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
            dcc.Store(id="commune-quartier", data=None),
            dcc.Store(id="commune-nom", data=nom),
            dcc.Store(id="commune-adresse-point", data=None),
            dcc.Store(id="commune-adresse-preset", data=None),
            html.Div(
                className="page-header",
                children=[
                    dmc.Breadcrumbs(
                        id="commune-crumbs",
                        separator="›",
                        className="breadcrumbs",
                        children=_crumbs(nom, None),
                    ),
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
                        gap="lg",
                        wrap="wrap",
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
                            dmc.Group(
                                gap="xs",
                                wrap="wrap",
                                children=[
                                    adresse.champ_adresse(
                                        "commune-adresse",
                                        f"Autour d'une adresse à {nom}…",
                                        size="xs",
                                        radius="xl",
                                    ),
                                    dmc.SegmentedControl(
                                        id="commune-rayon",
                                        data=adresse.RAYONS,
                                        value="500",
                                        size="xs",
                                        radius="xl",
                                    ),
                                ],
                            ),
                        ],
                    ),
                    dmc.Button(
                        id="commune-quartier-clear",
                        children="Tous les quartiers",
                        leftSection=icon("tabler:x", 14),
                        variant="light",
                        size="xs",
                        radius="xl",
                        style={"display": "none"},
                    ),
                ],
            ),
            html.Div(id="commune-autour"),
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
                                dmc.Text("Prix médian au m² par quartier", className="chart-title"),
                                dmc.Text(
                                    "Quartiers officiels de l'INSEE. Le chiffre indique le nombre de "
                                    f"ventes ; en gris, moins de {cfg.SEUIL_FIABILITE}. "
                                    "Cliquez sur un quartier pour voir ses ventes.",
                                    className="chart-subtitle",
                                ),
                                html.Div(
                                    className="scroll-chart",
                                    children=dcc.Loading(
                                        dcc.Graph(
                                            id="commune-quartiers",
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
                            "Les quartiers sur la carte",
                            "commune-carte",
                            subtitle="Couleur = prix médian au m². Cliquez sur un quartier pour "
                            "afficher ses ventes (celles de 2026, sans coordonnées, n'y figurent pas).",
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
                                        },
                                        "tooltipShowDelay": 300,
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
                                dmc.Button(
                                    "Expliquer ce prix",
                                    id="commune-expliquer",
                                    variant="light",
                                    size="xs",
                                    mt="md",
                                    leftSection=icon("tabler:sparkles", 14),
                                    style={"display": "none"},
                                ),
                                dcc.Loading(
                                    html.Div(id="commune-explication", className="explication"),
                                    type="dot",
                                ),
                            ],
                        ),
                    ),
                ],
            ),
            chart_card(
                "Évolution du prix médian au m²",
                "commune-trend",
                subtitle=f"Point creux : moins de {cfg.SEUIL_FIABILITE} ventes cette année-là "
                "(valeur indicative).",
                height=300,
            ),
        ]
    )


def _crumbs(nom, quartier_nom):
    items = [dcc.Link("Communes", href="/communes"), html.Span(nom)]
    if quartier_nom:
        items.append(html.Span(quartier_nom))
    return items


def _filtres_commune(store) -> Filtres:
    """Sur la fiche, la commune est choisie explicitement : on ignore la zone."""
    return replace(Filtres.from_store(store), zone="loiret")


def _type(t):
    return None if t == "Tous" else t


def _nom_quartier(code_commune, code_iris):
    for f in api.quartiers_geo(code_commune)["features"]:
        if f["properties"]["code_iris"] == code_iris:
            return f["properties"]["nom_quartier"]
    return None


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
    nq = r["n_quartiers"]
    decoupage = f"réparties dans {nq} quartiers" if nq > 1 else "commune non découpée en quartiers"
    sous_titre = f"{fmt.ventes(r['n'])} de {f.annee_min} à {f.annee_max}, {decoupage}."
    return sous_titre, m_val, m_det, a_val, a_det, prix, prix_det, ecart, ecart_det


@callback(
    Output("commune-quartiers", "figure"),
    Output("commune-quartiers", "style"),
    Input("filters-store", "data"),
    Input("commune-code", "data"),
    Input("commune-type", "value"),
    Input("commune-quartier", "data"),
    Input("color-scheme-store", "data"),
    State("commune-nom", "data"),
)
def maj_quartiers(store, code, type_, quartier, scheme, nom):
    if len(api.quartiers_geo(code)["features"]) <= 1:
        fig = figure_vide(
            scheme,
            f"{nom} est trop petite pour être découpée en quartiers :<br>"
            "toutes ses ventes sont sur la carte et dans le tableau.",
        )
        fig.update_layout(height=200)
        return fig, {"height": "200px"}
    df = api.stats_quartiers(_filtres_commune(store), code, _type(type_))
    fig = barres_quartiers(df, scheme, quartier, _type(type_))
    hauteur = max(260, 28 * len(df) + 60)
    fig.update_layout(height=hauteur)
    return fig, {"height": f"{hauteur}px"}


@callback(
    Output("commune-carte", "figure"),
    Input("filters-store", "data"),
    Input("commune-code", "data"),
    Input("commune-type", "value"),
    Input("commune-quartier", "data"),
    Input("commune-adresse-point", "data"),
    Input("commune-rayon", "value"),
    Input("color-scheme-store", "data"),
)
def maj_carte(store, code, type_, quartier, point, rayon, scheme):
    f = _filtres_commune(store)
    if point:
        _, df = api.ventes_commune(f, code, type_=_type(type_), point=point, rayon=int(rayon))
        return carte_autour(df, scheme, point, int(rayon), point["label"])
    geo = api.quartiers_geo(code)
    if len(geo["features"]) <= 1:
        # Commune sans quartiers : le nuage des ventes, cadré sur la commune
        _, df = api.ventes_commune(f, code, type_=_type(type_), geo=True)
        if df.empty:
            message = "Aucune vente géolocalisée avec ces filtres"
            if f.annee_max >= cfg.ANNEE_PARTIELLE["annee"]:
                message += "<br>(les ventes de 2026 n'ont pas de coordonnées)"
            return figure_vide(scheme, message)
        center, zoom = vue_geo(geo["features"])
        return carte_ventes(df, scheme, center, zoom)
    stats = api.stats_quartiers(f, code, _type(type_))
    ventes_q = pd.DataFrame(columns=api.COLONNES_VENTES + ["date_mutation"])
    if quartier:
        _, ventes_q = api.ventes_commune(f, code, type_=_type(type_), quartier=quartier, geo=True)
    return carte_quartiers(stats, geo, scheme, quartier, ventes_q)


@callback(
    Output("commune-adresse", "data", allow_duplicate=True),
    Input("commune-adresse", "searchValue"),
    State("commune-code", "data"),
    State("commune-adresse", "value"),
    prevent_initial_call=True,
)
def suggerer_adresses(saisie, code, valeur):
    return adresse.options(saisie, code, valeur)


@callback(
    Output("commune-adresse-preset", "data"),
    Input("commune-code", "data"),
    State("adresse-recherchee", "data"),
)
def reprendre_adresse(code, recherchee):
    """Au chargement : reprend l'adresse cherchée sur la page Communes, si c'est ici."""
    if recherchee and recherchee.get("code_commune") == code:
        return recherchee
    return no_update


@callback(
    Output("commune-quartier", "data"),
    Output("commune-adresse-point", "data"),
    Output("commune-adresse", "value"),
    Output("commune-adresse", "data"),
    Input("commune-quartiers", "clickData"),
    Input("commune-carte", "clickData"),
    Input("commune-quartier-clear", "n_clicks"),
    Input("commune-adresse", "value"),
    Input("commune-adresse-preset", "data"),
    State("commune-quartier", "data"),
    prevent_initial_call=True,
)
def choisir(bar_click, carte_click, _clear, valeur, preset, actuel):
    """Un seul filtre de lieu à la fois : un quartier, ou les abords d'une adresse."""
    trig = dash.ctx.triggered_id
    rien = (no_update, no_update, no_update, no_update)
    if trig == "commune-adresse-preset":
        if not preset:
            return rien
        v = adresse.encoder(preset)
        return None, preset, v, [{"value": v, "label": preset["label"]}]
    if trig == "commune-quartier-clear":
        return None, None, None, no_update
    if trig == "commune-adresse":
        point = adresse.decoder(valeur)
        return (None if point else no_update), point, no_update, no_update
    if trig == "commune-quartiers" and bar_click:
        cd = bar_click["points"][0].get("customdata")
        choix = cd[4] if cd else None
    elif trig == "commune-carte" and carte_click:
        p = carte_click["points"][0]
        cd = p.get("customdata")
        # clic sur un quartier (location) ou sur une vente (customdata[6])
        choix = p.get("location") or (cd[6] if cd and len(cd) > 6 else None)
    else:
        return rien
    if not choix:
        return rien
    return (None if choix == actuel else choix), None, None, no_update


@callback(
    Output("commune-quartier-clear", "style"),
    Output("commune-quartier-clear", "children"),
    Output("commune-crumbs", "children"),
    Input("commune-quartier", "data"),
    Input("commune-adresse-point", "data"),
    State("commune-code", "data"),
    State("commune-nom", "data"),
)
def maj_selection_ui(quartier, point, code, nom):
    if point:
        return {}, "Effacer l'adresse", _crumbs(nom, f"Autour de « {point['label']} »")
    if not quartier:
        return {"display": "none"}, "", _crumbs(nom, None)
    nom_q = _nom_quartier(code, quartier) or "Quartier"
    return {}, f"{nom_q} · voir tous les quartiers", _crumbs(nom, nom_q)


@callback(
    Output("commune-autour", "children"),
    Input("filters-store", "data"),
    Input("commune-code", "data"),
    Input("commune-adresse-point", "data"),
    Input("commune-rayon", "value"),
)
def maj_autour(store, code, point, rayon):
    """Encadré : prix médians autour de l'adresse, comparés à la commune."""
    if not point:
        return None
    f = _filtres_commune(store)
    a = api.autour(f, code, point, int(rayon))
    commune = api.resume_commune(f, code)
    distance = "1 km" if rayon == "1000" else f"{rayon} m"
    quartier = a["quartier"]["nom_quartier"] if a.get("quartier") else None

    def tuile(t):
        d, c = a[t], commune[t]
        if not d["n"]:
            valeur, detail = "–", "Aucune vente"
        else:
            valeur = fmt.eur_m2(d["pm2_med"])
            detail = f"sur {fmt.ventes(d['n'])}" + ("" if d["fiable"] else " · indicatif")
            if c["pm2_med"]:
                e = d["pm2_med"] / c["pm2_med"] - 1
                detail += f" · {fmt.pct(e, decimales=0)} vs la commune"
        return dmc.Paper(
            withBorder=True,
            className=f"stat-tile stat-tile--{'maison' if t == 'Maison' else 'appartement'}",
            children=[
                dmc.Text(f"{t} · médiane au m²", className="stat-label"),
                html.Div(valeur, className="stat-value"),
                dmc.Text(detail, className="stat-detail"),
            ],
        )

    entete = [
        html.Strong(point["label"]),
        f" · {fmt.ventes(a['n'])} à moins de {distance}",
    ]
    if quartier:
        entete.append(f" · quartier {quartier}")
    return dmc.Paper(
        withBorder=True,
        className="chart-card section autour-card",
        children=[
            dmc.Group(
                gap="xs",
                children=[
                    html.Span(icon("tabler:map-pin", 18), className="answer-icon"),
                    dmc.Text(entete, size="sm"),
                ],
            ),
            dmc.SimpleGrid(
                cols={"base": 1, "sm": 2},
                spacing="md",
                mt="sm",
                children=[
                    tuile("Maison"),
                    tuile("Appartement"),
                ],
            ),
            dmc.Text(
                "Ventes géolocalisées seulement : celles de 2026 n'ont pas de coordonnées. "
                "DVF ne publie pas les adresses : on mesure la distance à chaque vente.",
                size="xs",
                c="dimmed",
                mt="sm",
            ),
        ],
    )


COLONNE_DISTANCE = {
    "field": "distance",
    "headerName": "Distance",
    "valueFormatter": {"function": "metres(params.value)"},
    "sort": "asc",
    "maxWidth": 120,
}


@callback(
    Output("commune-ventes", "rowData"),
    Output("commune-ventes", "columnDefs"),
    Output("commune-ventes-titre", "children"),
    Input("filters-store", "data"),
    Input("commune-code", "data"),
    Input("commune-type", "value"),
    Input("commune-quartier", "data"),
    Input("commune-adresse-point", "data"),
    Input("commune-rayon", "value"),
)
def maj_ventes(store, code, type_, quartier, point, rayon):
    f = _filtres_commune(store)
    n_total, df = api.ventes_commune(
        f,
        code,
        type_=_type(type_),
        quartier=None if point else quartier,
        point=point,
        rayon=int(rayon),
        limit=None if (quartier or point) else MAX_LIGNES,
    )
    tronque = n_total > len(df)
    rows = [
        {
            "id": r.id_mutation,
            "date": r.date,
            "type": r.type,
            "quartier": r.nom_quartier,
            "section": r.section,
            "distance": None if pd.isna(r.distance_m) else r.distance_m,
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
    if point:
        colonnes = [{**c, "sort": None} if c["field"] == "date" else c for c in COLONNES_VENTES]
        colonnes = [COLONNE_DISTANCE, *colonnes]
        distance = "1 km" if rayon == "1000" else f"{rayon} m"
        titre = f"{fmt.ventes(n_total)} à moins de {distance} de « {point['label']} »"
        return rows, colonnes, titre
    titre = fmt.ventes(n_total)
    if quartier:
        titre += f" dans le quartier {_nom_quartier(code, quartier) or ''}"
    if tronque:
        titre += (
            f" · les {fmt.entier(len(df))} plus récentes (choisissez un quartier pour tout voir)"
        )
    return rows, COLONNES_VENTES, titre


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
        dmc.Text(f"{v['type']} · {fmt.m2(v['surface'])} · {v['quartier']}", fw=600),
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
                f" par rapport à la médiane de {fmt.ventes(comp['n'])} comparables "
                f"({fmt.eur_m2(med)}).",
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
            f"Comparables : {v['type'].lower()}s de la commune, surface entre "
            f"{fmt.m2(v['surface'] * 0.8)} et {fmt.m2(v['surface'] * 1.2)}, mêmes filtres. "
            "DVF ne dit rien de l'état ni du DPE.",
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


@callback(
    Output("commune-expliquer", "style"),
    Output("commune-explication", "children"),
    Input("commune-ventes", "selectedRows"),
)
def preparer_explication(selected):
    """Le bouton n'apparaît qu'avec une vente sélectionnée et si l'assistant est actif."""
    try:
        actif = api.assistant_statut().get("actif")
    except api.ApiError:
        actif = False
    return ({} if selected and actif else {"display": "none"}), None


@callback(
    Output("commune-explication", "children", allow_duplicate=True),
    Output("llm-quota", "data", allow_duplicate=True),
    Input("commune-expliquer", "n_clicks"),
    State("commune-ventes", "selectedRows"),
    State("filters-store", "data"),
    State("commune-code", "data"),
    prevent_initial_call=True,
)
def expliquer_vente(_clic, selected, store, code):
    if not _clic or not selected:  # n_clicks vaut 0 au montage du bouton : pas un clic
        return no_update, no_update
    v = selected[0]
    return assistant.appeler(
        api.expliquer_prix,
        _filtres_commune(store),
        code,
        v["type"],
        float(v["surface"]),
        float(v["prix"]),
        "vente",
    )
