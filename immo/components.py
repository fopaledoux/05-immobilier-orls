"""Briques d'interface réutilisables (Dash Mantine Components)."""

import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import dcc, html
from dash_iconify import DashIconify

from immo.config import SEUIL_FIABILITE, TYPES
from theme import GRAPH_CONFIG


def icon(name: str, size: int = 18, **kwargs):
    return DashIconify(icon=name, width=size, **kwargs)


def page_header(title: str, subtitle, eyebrow: str | None = None, extra=None):
    return html.Div(
        className="page-header",
        children=[
            dmc.Text(eyebrow, className="eyebrow") if eyebrow else None,
            dmc.Title(title, order=1, className="page-title"),
            dmc.Text(subtitle, className="page-subtitle"),
            extra,
        ],
    )


def stat_tile(label: str, value_id: str, detail_id: str, accent: str | None = None):
    """Tuile KPI : libellé, grand chiffre, détail (nombre de ventes...)."""
    return dmc.Paper(
        className=f"stat-tile {f'stat-tile--{accent}' if accent else ''}",
        withBorder=True,
        children=[
            dmc.Text(label, className="stat-label"),
            html.Div(id=value_id, className="stat-value", children="–"),
            dmc.Text(id=detail_id, className="stat-detail", children=""),
        ],
    )


def answer_card(question: str, answer_id: str, href: str, link_label: str, ico: str):
    """Carte « question métier → réponse chiffrée ». La réponse est calculée."""
    return dmc.Paper(
        className="answer-card",
        withBorder=True,
        children=[
            dmc.Group(
                gap="xs",
                children=[
                    html.Span(icon(ico, 18), className="answer-icon"),
                    dmc.Text(question, className="answer-question"),
                ],
            ),
            dcc.Loading(
                html.Div(id=answer_id, className="answer-body"),
                type="dot",
                delay_show=300,
            ),
            dcc.Link(
                [link_label, icon("tabler:arrow-right", 16)],
                href=href,
                className="answer-link",
            ),
        ],
    )


def chart_card(title: str, graph_id: str, subtitle=None, controls=None, height=380, footer=None):
    return dmc.Paper(
        className="chart-card",
        withBorder=True,
        children=[
            dmc.Group(
                justify="space-between",
                align="flex-start",
                wrap="wrap",
                gap="sm",
                className="chart-card-head",
                children=[
                    html.Div(
                        [
                            dmc.Text(title, className="chart-title"),
                            (dmc.Text(subtitle, className="chart-subtitle") if subtitle else None),
                        ]
                    ),
                    controls,
                ],
            ),
            dcc.Loading(
                dcc.Graph(
                    id=graph_id,
                    config=GRAPH_CONFIG,
                    style={"height": f"{height}px"},
                    className="chart-graph",
                ),
                type="circle",
                delay_show=300,
                color="var(--mantine-primary-color-filled)",
            ),
            footer,
        ],
    )


def type_control(id_: str, value: str = "Maison", comparer: bool = False):
    data = [{"value": t, "label": t} for t in TYPES]
    if comparer:
        data.append({"value": "Comparer", "label": "Comparer"})
    return dmc.SegmentedControl(id=id_, value=value, data=data, size="xs", radius="xl")


LOCALE_FR = {
    "page": "Page",
    "of": "sur",
    "to": "à",
    "more": "plus",
    "next": "Suivante",
    "previous": "Précédente",
    "first": "Première",
    "last": "Dernière",
    "pageLastRowUnknown": "?",
    "filterOoo": "Filtrer…",
    "searchOoo": "Rechercher…",
    "equals": "Égal à",
    "notEqual": "Différent de",
    "contains": "Contient",
    "notContains": "Ne contient pas",
    "startsWith": "Commence par",
    "endsWith": "Se termine par",
    "lessThan": "Inférieur à",
    "lessThanOrEqual": "Inférieur ou égal à",
    "greaterThan": "Supérieur à",
    "greaterThanOrEqual": "Supérieur ou égal à",
    "inRange": "Entre",
    "inRangeStart": "De",
    "inRangeEnd": "À",
    "blank": "Vide",
    "notBlank": "Non vide",
    "andCondition": "ET",
    "orCondition": "OU",
    "applyFilter": "Appliquer",
    "resetFilter": "Réinitialiser",
    "clearFilter": "Effacer",
    "noRowsToShow": "Aucune ligne à afficher",
    "loadingOoo": "Chargement…",
    "ariaPageSizeSelectorLabel": "Taille de page",
}


def grid(
    id_: str,
    column_defs: list,
    row_id: str | None = None,
    page_size: int = 10,
    options: dict | None = None,
    **kwargs,
):
    """AgGrid avec la configuration standard du projet (cf. AGENTS.md)."""
    return dag.AgGrid(
        id=id_,
        columnDefs=column_defs,
        rowData=[],
        columnSize="responsiveSizeToFit",
        defaultColDef={
            "filter": True,
            "sortable": True,
            "resizable": True,
            "minWidth": 90,
            "wrapHeaderText": True,
            "autoHeaderHeight": True,
        },
        dashGridOptions={
            "theme": "themeBalham",
            "animateRows": True,
            "pagination": True,
            "paginationPageSize": page_size,
            "paginationPageSizeSelector": False,
            "rowHeight": 36,
            "headerHeight": 38,
            "domLayout": "autoHeight",
            "localeText": LOCALE_FR,
            **(options or {}),
        },
        getRowId=f"params.data.{row_id}" if row_id else None,
        className="immo-grid",
        **kwargs,
    )


def legende_fiabilite():
    return html.Div(
        className="legend-note",
        children=[
            html.Span(className="swatch swatch--indicatif"),
            f"Moins de {SEUIL_FIABILITE} ventes : prix indicatif, non coloré",
        ],
    )


def empty_state(message: str):
    return dmc.Alert(message, color="gray", variant="light", icon=icon("tabler:info-circle"))
