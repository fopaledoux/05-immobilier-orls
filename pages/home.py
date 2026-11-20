"""Vue d'ensemble : les trois questions métier, répondues dès le premier écran."""

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html, no_update

from immo import data, fmt
from immo.components import answer_card, chart_card, legende_fiabilite, stat_tile, type_control
from immo.config import PERIODE_APRES, PERIODE_AVANT, SEUIL_FIABILITE, TAUX_FRAIS_NOTAIRE, ZONES
from immo.data import Filtres
from immo.figures import carte_communes, tendance_trimestrielle

dash.register_page(__name__, path="/", name="Vue d'ensemble", order=0)

BUDGET_EXEMPLE = 300_000
SURFACE_EXEMPLE = 100
AV = f"{PERIODE_AVANT[0]}-{PERIODE_AVANT[1] % 100}"
AP = f"{PERIODE_APRES[0]}-{PERIODE_APRES[1] % 100}"


def layout(**_):
    return html.Div(
        [
            dcc.Location(id="home-nav", refresh="callback-nav"),
            html.Div(
                className="hero",
                children=[
                    dmc.Text(id="home-eyebrow", className="eyebrow"),
                    dmc.Title(
                        "Où acheter autour d'Orléans, et à quel prix ?",
                        order=1,
                        className="page-title",
                    ),
                    dmc.Text(
                        "Les prix réellement payés pour une maison ou un appartement, commune par commune, "
                        "pour savoir où chercher avec votre budget.",
                        className="page-subtitle",
                    ),
                ],
            ),
            dmc.SimpleGrid(
                cols={"base": 2, "lg": 4},
                spacing="md",
                className="section",
                children=[
                    stat_tile(
                        "Maison · prix médian au m²", "kpi-maison-pm2", "kpi-maison-n", "maison"
                    ),
                    stat_tile(
                        "Appartement · prix médian au m²",
                        "kpi-appart-pm2",
                        "kpi-appart-n",
                        "appartement",
                    ),
                    stat_tile("Prix médian d'une maison", "kpi-maison-prix", "kpi-maison-surf"),
                    stat_tile(f"Évolution €/m² maison, {AV} → {AP}", "kpi-evol", "kpi-evol-detail"),
                ],
            ),
            dmc.SimpleGrid(
                cols={"base": 1, "md": 3},
                spacing="md",
                className="section",
                children=[
                    answer_card(
                        f"Quel budget pour une maison d'au moins {SURFACE_EXEMPLE} m² ?",
                        "answer-budget",
                        "/budget",
                        "Simuler mon budget",
                        "tabler:wallet",
                    ),
                    answer_card(
                        "Où est-ce le moins cher, et le plus cher ?",
                        "answer-prix",
                        "/communes",
                        "Comparer les communes",
                        "tabler:map-2",
                    ),
                    answer_card(
                        "Les prix ont-ils baissé depuis la hausse des taux ?",
                        "answer-tendance",
                        "/tendances",
                        "Voir les tendances",
                        "tabler:chart-line",
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
                            "Prix médian au m² par commune",
                            "home-map",
                            subtitle="Cliquez sur une commune pour ouvrir sa fiche (sections, ventes).",
                            controls=type_control("home-map-type"),
                            height=460,
                            footer=legende_fiabilite(),
                        ),
                    ),
                    dmc.GridCol(
                        span={"base": 12, "lg": 5},
                        children=chart_card(
                            "Prix médian au m² sur 12 mois glissants",
                            "home-trend",
                            subtitle="Chaque point : médiane des ventes des 12 mois précédents, toutes communes de la zone.",
                            height=460,
                        ),
                    ),
                ],
            ),
        ]
    )


@callback(
    Output("home-eyebrow", "children"),
    Output("kpi-maison-pm2", "children"),
    Output("kpi-maison-n", "children"),
    Output("kpi-appart-pm2", "children"),
    Output("kpi-appart-n", "children"),
    Output("kpi-maison-prix", "children"),
    Output("kpi-maison-surf", "children"),
    Output("kpi-evol", "children"),
    Output("kpi-evol-detail", "children"),
    Input("filters-store", "data"),
)
def maj_kpis(store):
    f = Filtres.from_store(store)
    k = data.kpis(f)
    evo = data.evolution_globale(f).get("Maison")
    m, a = k["Maison"], k["Appartement"]
    periode = f"{f.annee_min}" if f.annee_min == f.annee_max else f"{f.annee_min}-{f.annee_max}"
    eyebrow = (
        f"{ZONES[f.zone]['label']} · {fmt.ventes(k['n'])} · {k['n_communes']} communes · {periode}"
    )
    evo_val = fmt.pct(evo["pm2_var"]) if evo else "–"
    evo_det = (
        f"{fmt.eur_m2(evo['pm2_avant'])} → {fmt.eur_m2(evo['pm2_apres'])}"
        if evo
        else "Pas assez de ventes"
    )
    return (
        eyebrow,
        fmt.eur_m2(m["pm2_med"]),
        f"sur {fmt.ventes(m['n'])}",
        fmt.eur_m2(a["pm2_med"]),
        f"sur {fmt.ventes(a['n'])}",
        fmt.euros(m["prix_med"]),
        f"pour {fmt.m2(m['surf_med'])} habitables (médiane)",
        evo_val,
        evo_det,
    )


def _liste(noms):
    noms = list(noms)
    if len(noms) <= 1:
        return "".join(noms)
    return ", ".join(noms[:-1]) + " et " + noms[-1]


@callback(
    Output("answer-budget", "children"),
    Output("answer-prix", "children"),
    Output("answer-tendance", "children"),
    Input("filters-store", "data"),
)
def maj_reponses(store):
    f = Filtres.from_store(store)

    # 1. Budget : combien faut-il prévoir, et que permet le budget exemple ?
    prix_bien = BUDGET_EXEMPLE / (1 + TAUX_FRAIS_NOTAIRE)
    b = data.budget_communes(f, "Maison", prix_bien, SURFACE_EXEMPLE, 0)
    fiables = b[b["fiable"]].sort_values("prix_med")
    if fiables.empty:
        budget = html.P("Pas assez de ventes comparables avec ces filtres.")
    else:
        bas, haut = fiables.iloc[0], fiables.iloc[-1]
        frais = 1 + TAUX_FRAIS_NOTAIRE
        ok = fiables[fiables["dans_budget"]].sort_values("n", ascending=False)
        if len(ok):
            detail = [
                f"Avec {fmt.euros(BUDGET_EXEMPLE)} : ",
                html.Strong(f"{len(ok)} commune{'s' if len(ok) > 1 else ''}"),
                " accessible" + ("s" if len(ok) > 1 else "") + " en médiane, dont ",
                html.Strong(_liste(ok["nom_commune"].head(3))),
                ".",
            ]
        else:
            detail = [
                f"Avec {fmt.euros(BUDGET_EXEMPLE)}, aucune commune ne l'est en médiane ; à {bas['nom_commune']}, ",
                html.Strong(fmt.pct(bas["part_sous_budget"], signe=False, decimales=0)),
                " des ventes tenaient dans ce budget.",
            ]
        budget = [
            html.P(
                [
                    "Comptez ",
                    html.Strong(fmt.euros_k(bas["prix_med"] * frais)),
                    f" à {bas['nom_commune']}, jusqu'à ",
                    html.Strong(fmt.euros_k(haut["prix_med"] * frais)),
                    f" à {haut['nom_commune']}.",
                ],
                className="answer-headline",
            ),
            html.P(detail, className="answer-detail"),
            html.P(
                f"Prix médians, frais de notaire (~{TAUX_FRAIS_NOTAIRE:.1%}) inclus, sur les {len(fiables)} "
                f"communes ayant au moins {SEUIL_FIABILITE} ventes comparables.".replace(
                    ".5%", ",5 %"
                ),
                className="answer-foot",
            ),
        ]

    # 2. Prix par commune
    sm = data.stats_communes(f, "Maison")
    sm = sm[sm["fiable"]]
    k = data.kpis(f)
    if sm.empty:
        prix = html.P("Pas assez de ventes de maisons avec ces filtres.")
    else:
        bas, haut = sm.iloc[0], sm.iloc[-1]
        ecart = None
        if k["Maison"]["pm2_med"] and k["Appartement"]["pm2_med"]:
            ecart = k["Appartement"]["pm2_med"] / k["Maison"]["pm2_med"] - 1
        prix = [
            html.P(
                [
                    "Maisons : de ",
                    html.Strong(fmt.eur_m2(bas["pm2_med"])),
                    f" à {bas['nom_commune']} à ",
                    html.Strong(fmt.eur_m2(haut["pm2_med"])),
                    f" à {haut['nom_commune']}.",
                ],
                className="answer-headline",
            ),
            html.P(
                (
                    [
                        "Au m², un appartement coûte en médiane ",
                        html.Strong(fmt.pct(abs(ecart), signe=False, decimales=0)),
                        " de plus qu'une maison." if ecart >= 0 else " de moins qu'une maison.",
                    ]
                    if ecart is not None
                    else ""
                ),
                className="answer-detail",
            ),
            html.P(
                f"Classement sur {len(sm)} communes ayant au moins {SEUIL_FIABILITE} ventes de maisons.",
                className="answer-foot",
            ),
        ]

    # 3. Tendance
    evo = data.evolution_globale(f)
    em, ea = evo.get("Maison"), evo.get("Appartement")
    if not em:
        tendance = html.P("Pas assez de ventes sur les deux périodes.")
    else:
        ec = data.evolution_communes(f, "Maison")
        ec = ec[ec["fiable"]]
        detail = []
        if ea:
            detail = [
                "Appartements : ",
                html.Strong(fmt.pct(ea["pm2_var"])),
                " au m². Nombre de ventes de maisons par an : ",
                html.Strong(fmt.pct(em["ventes_var"], decimales=0)),
                ".",
            ]
        tendance = [
            html.P(
                [
                    "Maisons : ",
                    html.Strong(fmt.pct(em["pm2_var"])),
                    f" sur le prix médian au m² entre {AV} et {AP}.",
                ],
                className="answer-headline",
            ),
            html.P(detail, className="answer-detail"),
            html.P(
                (
                    f"Plus forte baisse : {ec.iloc[0]['nom_commune']} ({fmt.pct(ec.iloc[0]['var'])}) ; "
                    f"plus forte hausse : {ec.iloc[-1]['nom_commune']} ({fmt.pct(ec.iloc[-1]['var'])})."
                    if len(ec) >= 2
                    else ""
                ),
                className="answer-foot",
            ),
        ]
    return budget, prix, tendance


@callback(
    Output("home-map", "figure"),
    Input("filters-store", "data"),
    Input("home-map-type", "value"),
    Input("color-scheme-store", "data"),
)
def maj_carte(store, type_, scheme):
    f = Filtres.from_store(store)
    stats = data.stats_communes(f, type_)
    return carte_communes(
        stats,
        scheme,
        f.zone,
        valeur="pm2_med",
        titre_echelle="€/m²",
        format_valeur=fmt.entier,
        lignes_hover=lambda r: [
            f"{type_} : <b>{fmt.eur_m2(r['pm2_med'])}</b>",
            f"Prix médian {fmt.euros(r['prix_med'])} · {fmt.ventes(r['n'])}",
        ],
    )


@callback(
    Output("home-trend", "figure"),
    Input("filters-store", "data"),
    Input("color-scheme-store", "data"),
)
def maj_tendance(store, scheme):
    f = Filtres.from_store(store)
    return tendance_trimestrielle(data.stats_trimestrielles(f), scheme)


@callback(
    Output("home-nav", "href"),
    Input("home-map", "clickData"),
    prevent_initial_call=True,
)
def ouvrir_commune(click):
    if not click or not click.get("points"):
        return no_update
    code = click["points"][0].get("location")
    return f"/commune/{code}" if code else no_update
