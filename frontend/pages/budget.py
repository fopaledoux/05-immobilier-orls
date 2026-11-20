"""Mon budget : quelles communes sont accessibles pour le bien recherché ?"""

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html, no_update

from immo import api, assistant, fmt
from immo.components import chart_card, grid, icon, legende_fiabilite, page_header
from immo import config as cfg
from immo.api import Filtres
from immo.figures import carte_communes

dash.register_page(__name__, path="/budget", name="Mon budget", order=1)

COLONNES = [
    {
        "field": "nom_commune",
        "headerName": "Commune",
        "minWidth": 160,
        "pinned": "left",
        "cellClass": "cell-link",
    },
    {
        "field": "part_sous_budget",
        "headerName": "Part dans le budget",
        "valueFormatter": {"function": "pct(params.value)"},
    },
    {
        "field": "n_sous_budget",
        "headerName": "Ventes dans le budget",
        "valueFormatter": {"function": "entier(params.value)"},
    },
    {
        "field": "n",
        "headerName": "Ventes comparables",
        "valueFormatter": {"function": "entier(params.value)"},
    },
    {
        "field": "prix_med",
        "headerName": "Prix médian",
        "valueFormatter": {"function": "euros(params.value)"},
    },
    {
        "field": "pm2_med",
        "headerName": "€/m² médian",
        "valueFormatter": {"function": "eurM2(params.value)"},
    },
    {
        "field": "surf_med",
        "headerName": "Surface médiane",
        "valueFormatter": {"function": "m2(params.value)"},
    },
    {
        "field": "fiabilite",
        "headerName": "Fiabilité",
        "cellClassRules": {
            "cell-indicatif": "params.value === 'Indicatif'",
            "cell-fiable": "params.value === 'Fiable'",
        },
    },
]


def layout(**_):
    return html.Div(
        [
            dcc.Location(id="budget-nav", refresh="callback-nav"),
            page_header(
                "Où chercher avec mon budget ?",
                "Indiquez votre budget et le bien recherché : pour chaque commune, on regarde les ventes "
                "comparables de 2021 à juin 2026 et la part d'entre elles qui tenait dans votre budget.",
                eyebrow="Mon budget",
            ),
            dmc.Paper(
                withBorder=True,
                className="controls-card section",
                children=dmc.SimpleGrid(
                    cols={"base": 1, "sm": 2, "lg": 5},
                    spacing="lg",
                    children=[
                        html.Div(
                            [
                                dmc.NumberInput(
                                    id="budget-montant",
                                    label="Mon budget",
                                    value=300_000,
                                    min=20_000,
                                    max=2_000_000,
                                    step=5_000,
                                    thousandSeparator=" ",
                                    suffix=" €",
                                    allowNegative=False,
                                    allowDecimal=False,
                                    leftSection=icon("tabler:wallet", 16),
                                    debounce=400,
                                ),
                                dmc.Checkbox(
                                    id="budget-frais",
                                    label=f"Frais de notaire inclus (~{cfg.TAUX_FRAIS_NOTAIRE:.1%})".replace(
                                        ".", ","
                                    ),
                                    checked=True,
                                    mt="xs",
                                    size="xs",
                                ),
                            ]
                        ),
                        html.Div(
                            [
                                dmc.Text("Type de bien", size="sm", fw=500, mb=4),
                                dmc.SegmentedControl(
                                    id="budget-type",
                                    data=list(cfg.TYPES),
                                    value="Maison",
                                    fullWidth=True,
                                ),
                            ]
                        ),
                        dmc.NumberInput(
                            id="budget-surface",
                            label="Surface minimale",
                            value=100,
                            min=9,
                            max=400,
                            step=5,
                            suffix=" m²",
                            allowNegative=False,
                            allowDecimal=False,
                            debounce=400,
                        ),
                        dmc.Select(
                            id="budget-pieces",
                            label="Nombre de pièces minimum",
                            data=[{"value": "0", "label": "Peu importe"}]
                            + [
                                {"value": str(i), "label": f"{i} pièces ou plus"}
                                for i in range(2, 7)
                            ],
                            value="0",
                            allowDeselect=False,
                        ),
                        html.Div(
                            className="budget-prix-bien",
                            children=[
                                dmc.Text("Prix maximum du bien", size="sm", fw=500),
                                html.Div(
                                    id="budget-prix-bien", className="stat-value stat-value--sm"
                                ),
                                dmc.Text(id="budget-prix-bien-detail", size="xs", c="dimmed"),
                            ],
                        ),
                    ],
                ),
            ),
            dcc.Loading(
                html.Div(id="budget-verdict", className="section"), type="dot", delay_show=300
            ),
            html.Div(
                className="section",
                children=[
                    dmc.Button(
                        "Demander conseil à l'assistant",
                        id="budget-conseil",
                        variant="light",
                        leftSection=icon("tabler:sparkles", 16),
                        style={} if _assistant_actif() else {"display": "none"},
                    ),
                    dcc.Loading(
                        html.Div(id="budget-conseil-texte", className="section"), type="dot"
                    ),
                ],
            ),
            dmc.Grid(
                gutter="md",
                className="section",
                children=[
                    dmc.GridCol(
                        span={"base": 12, "lg": 6},
                        children=chart_card(
                            "Part des ventes comparables dans votre budget",
                            "budget-map",
                            subtitle="Plus la commune est foncée, plus vous aviez de choix. Cliquez pour la fiche commune.",
                            height=480,
                            footer=legende_fiabilite(),
                        ),
                    ),
                    dmc.GridCol(
                        span={"base": 12, "lg": 6},
                        children=dmc.Paper(
                            withBorder=True,
                            className="chart-card",
                            children=[
                                dmc.Text("Classement des communes", className="chart-title"),
                                dmc.Text(
                                    "Triez ou filtrez chaque colonne. Cliquez sur une commune pour sa fiche.",
                                    className="chart-subtitle",
                                    mb="sm",
                                ),
                                grid("budget-grid", COLONNES, row_id="code_commune"),
                            ],
                        ),
                    ),
                ],
            ),
        ]
    )


def _params(montant, frais):
    montant = float(montant or 0)
    return montant / (1 + cfg.TAUX_FRAIS_NOTAIRE) if frais else montant


@callback(
    Output("budget-prix-bien", "children"),
    Output("budget-prix-bien-detail", "children"),
    Input("budget-montant", "value"),
    Input("budget-frais", "checked"),
)
def maj_prix_bien(montant, frais):
    prix = _params(montant, frais)
    detail = (
        f"dont {fmt.euros(float(montant or 0) - prix)} de frais"
        if frais
        else "frais de notaire en plus"
    )
    return fmt.euros(prix), detail


@callback(
    Output("budget-verdict", "children"),
    Output("budget-map", "figure"),
    Output("budget-grid", "rowData"),
    Input("filters-store", "data"),
    Input("budget-montant", "value"),
    Input("budget-frais", "checked"),
    Input("budget-type", "value"),
    Input("budget-surface", "value"),
    Input("budget-pieces", "value"),
    Input("color-scheme-store", "data"),
)
def maj_budget(store, montant, frais, type_, surface, pieces, scheme):
    f = Filtres.from_store(store)
    prix_bien = _params(montant, frais)
    surface = float(surface or 0)
    pieces = int(pieces or 0)
    df = api.budget_communes(f, type_, prix_bien, surface, pieces)

    fig = carte_communes(
        df,
        scheme,
        f.zone,
        valeur="part_sous_budget",
        titre_echelle="Dans le budget",
        format_valeur=lambda v: f"{v * 100:.0f} %",
        lignes_hover=lambda r: [
            f"<b>{fmt.pct(r['part_sous_budget'], signe=False, decimales=0)}</b> des ventes comparables dans le budget",
            f"{fmt.entier(r['n_sous_budget'])} sur {fmt.ventes(r['n'])} · prix médian {fmt.euros(r['prix_med'])}",
        ],
        zrange=(0, 1),
    )

    rows = df.assign(fiabilite=df["fiable"].map({True: "Fiable", False: "Indicatif"}))
    rows = rows[
        [
            "code_commune",
            "nom_commune",
            "part_sous_budget",
            "n_sous_budget",
            "n",
            "prix_med",
            "pm2_med",
            "surf_med",
            "fiabilite",
        ]
    ].to_dict("records")

    bien = f"{'une maison' if type_ == 'Maison' else 'un appartement'} d'au moins {fmt.m2(surface)}"
    if pieces:
        bien += f" et {pieces} pièces"
    fiables = df[df["fiable"]]
    ok = fiables[fiables["dans_budget"]].sort_values("n_sous_budget", ascending=False)

    if df.empty:
        verdict = dmc.Alert(
            f"Aucune vente de {bien} dans la zone avec ces filtres. Essayez une surface plus petite "
            "ou élargissez la zone au Loiret.",
            color="gray",
            icon=icon("tabler:info-circle"),
            title="Aucun bien comparable",
        )
    else:
        n_ok = len(ok)
        couleur = "teal" if n_ok >= 3 else ("yellow" if n_ok else "red")
        ico = (
            "tabler:circle-check"
            if n_ok >= 3
            else ("tabler:alert-triangle" if n_ok else "tabler:circle-x")
        )
        if n_ok:
            titre = f"{n_ok} commune{'s' if n_ok > 1 else ''} où {bien} se vend en médiane dans votre budget"
            corps = [
                "Là où vous aurez le plus de choix : ",
                html.Strong(
                    ", ".join(
                        f"{r.nom_commune} ({r.n_sous_budget} ventes)"
                        for r in ok.head(3).itertuples()
                    )
                ),
                f". Calcul sur les communes ayant au moins {cfg.SEUIL_FIABILITE} ventes comparables "
                f"({len(fiables)} dans {cfg.ZONES[f.zone]['label']}).",
            ]
        else:
            meilleur = fiables.sort_values("part_sous_budget", ascending=False).head(1)
            titre = f"Aucune commune fiable où {bien} se vend en médiane dans votre budget"
            corps = (
                [
                    "Meilleure option : ",
                    html.Strong(meilleur.iloc[0]["nom_commune"]),
                    f", où {fmt.pct(meilleur.iloc[0]['part_sous_budget'], signe=False, decimales=0)} des ventes "
                    "comparables tenaient dans le budget. Réduisez la surface ou élargissez la zone.",
                ]
                if len(meilleur)
                else ["Pas assez de ventes comparables : élargissez la zone au Loiret."]
            )
        verdict = dmc.Alert(
            corps, title=titre, color=couleur, icon=icon(ico, 22), className="verdict"
        )

    return verdict, fig, rows


@callback(
    Output("budget-nav", "href"),
    Input("budget-map", "clickData"),
    Input("budget-grid", "cellClicked"),
    prevent_initial_call=True,
)
def ouvrir_commune(click, cell):
    trig = dash.ctx.triggered_id
    if trig == "budget-map" and click and click.get("points"):
        code = click["points"][0].get("location")
        return f"/commune/{code}" if code else no_update
    if trig == "budget-grid" and cell and cell.get("colId") == "nom_commune":
        return f"/commune/{cell.get('rowId')}"
    return no_update


def _assistant_actif() -> bool:
    try:
        return bool(api.assistant_statut().get("actif"))
    except api.ApiError:
        return False


@callback(
    Output("budget-conseil-texte", "children"),
    Input("filters-store", "data"),
    Input("budget-montant", "value"),
    Input("budget-frais", "checked"),
    Input("budget-type", "value"),
    Input("budget-surface", "value"),
    Input("budget-pieces", "value"),
)
def effacer_conseil(*_):
    """Le conseil correspond à un projet : on l'efface quand le projet change."""
    return None


@callback(
    Output("budget-conseil-texte", "children", allow_duplicate=True),
    Output("llm-quota", "data", allow_duplicate=True),
    Input("budget-conseil", "n_clicks"),
    State("filters-store", "data"),
    State("budget-montant", "value"),
    State("budget-frais", "checked"),
    State("budget-type", "value"),
    State("budget-surface", "value"),
    State("budget-pieces", "value"),
    prevent_initial_call=True,
)
def conseiller(_clic, store, montant, frais, type_, surface, pieces):
    if not _clic or not montant:  # n_clicks vaut 0 au montage du bouton : pas un clic
        return no_update, no_update
    return assistant.appeler(
        api.conseil_budget,
        Filtres.from_store(store),
        float(montant),
        bool(frais),
        type_,
        float(surface or 0),
        int(pieces or 0),
    )
