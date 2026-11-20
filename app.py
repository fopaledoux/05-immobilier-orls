"""Immo Loiret · où acheter dans le Loiret, et à quel prix ?

Point d'entrée Dash (multipage). Lancer en local : `uv run python app.py`
"""

import os

import dash
import dash_mantine_components as dmc
from dash import (
    ALL,
    Dash,
    Input,
    Output,
    State,
    callback,
    clientside_callback,
    ctx,
    dcc,
    html,
    no_update,
)

from immo.cache import CACHE_CONFIG, cache
from immo.components import icon
from immo.config import BORNES, FILTRES_DEFAUT
from theme import MANTINE_THEME

app = Dash(
    __name__,
    use_pages=True,
    suppress_callback_exceptions=True,
    title="Immo Loiret · prix de l'immobilier autour d'Orléans",
    update_title=None,
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"},
        {
            "name": "description",
            "content": "Prix médians au m² des maisons et appartements du Loiret "
            "(DVF 2021-2025) : où chercher avec son budget.",
        },
    ],
)
server = app.server
cache.init_app(server, config=CACHE_CONFIG)

NAV = [
    ("Vue d'ensemble", "/", "tabler:layout-dashboard"),
    ("Mon budget", "/budget", "tabler:wallet"),
    ("Communes", "/communes", "tabler:map-2"),
    ("Tendances", "/tendances", "tabler:chart-line"),
    ("Méthodologie", "/methodologie", "tabler:info-circle"),
]


def nav_links():
    return html.Nav(
        className="main-nav",
        children=[
            dcc.Link(
                [icon(ico, 16), html.Span(label)],
                href=href,
                id={"type": "nav-link", "href": href},
                className="nav-link",
            )
            for label, href, ico in NAV
        ],
    )


def mobile_menu():
    menu = dmc.Menu(
        position="bottom-end",
        shadow="md",
        width=220,
        children=[
            dmc.MenuTarget(
                dmc.ActionIcon(
                    icon("tabler:menu-2", 20),
                    variant="subtle",
                    color="gray",
                    size="lg",
                    **{"aria-label": "Menu"},
                )
            ),
            dmc.MenuDropdown(
                [
                    dmc.MenuItem(label, href=href, leftSection=icon(ico, 16))
                    for label, href, ico in NAV
                ]
            ),
        ],
    )
    return dmc.Box(menu, hiddenFrom="lg")


def header():
    return dmc.AppShellHeader(
        className="app-header",
        children=dmc.Container(
            size="xl",
            className="header-inner",
            children=[
                dcc.Link(
                    href="/",
                    className="brand",
                    children=[
                        html.Span(icon("tabler:home-search", 22), className="brand-mark"),
                        html.Div(
                            [
                                html.Span("Immo Loiret", className="brand-name"),
                                html.Span("Ventes DVF 2021-2025", className="brand-tag"),
                            ]
                        ),
                    ],
                ),
                dmc.Box(nav_links(), visibleFrom="lg"),
                dmc.Group(
                    gap="xs",
                    wrap="nowrap",
                    children=[
                        dmc.SegmentedControl(
                            id="zone-control",
                            data=[
                                {"value": "metropole", "label": "Métropole"},
                                {"value": "loiret", "label": "Loiret"},
                            ],
                            value=FILTRES_DEFAUT["zone"],
                            size="xs",
                            radius="xl",
                            className="zone-control",
                            persistence=True,
                            persistence_type="session",
                        ),
                        dmc.Tooltip(
                            dmc.Indicator(
                                dmc.ActionIcon(
                                    icon("tabler:adjustments-horizontal", 20),
                                    id="filters-open",
                                    variant="default",
                                    size="lg",
                                    **{"aria-label": "Filtres de données"},
                                ),
                                id="filters-indicator",
                                disabled=True,
                                size=9,
                                offset=3,
                            ),
                            label="Filtres de données",
                        ),
                        dmc.Tooltip(
                            dmc.ActionIcon(
                                icon("tabler:moon", 20, id="theme-icon"),
                                id="theme-toggle",
                                variant="default",
                                size="lg",
                                **{"aria-label": "Basculer le thème clair/sombre"},
                            ),
                            label="Thème clair / sombre",
                        ),
                        mobile_menu(),
                    ],
                ),
            ],
        ),
    )


def _range(id_, label, bornes, step, marks):
    return html.Div(
        className="filter-block",
        children=[
            dmc.Group(
                justify="space-between",
                children=[
                    dmc.Text(label, fw=600, size="sm"),
                    dmc.Text(id=f"{id_}-label", size="sm", c="dimmed"),
                ],
            ),
            dmc.RangeSlider(
                id=id_,
                min=bornes[0],
                max=bornes[1],
                step=step,
                value=list(bornes),
                marks=marks,
                minRange=step,
                label=None,
                mb="lg",
                size="sm",
            ),
        ],
    )


def filters_drawer():
    a0, a1 = BORNES["annees"]
    return dmc.Drawer(
        id="filters-drawer",
        title=dmc.Text("Filtres de données", fw=700, size="lg"),
        position="right",
        size="md",
        padding="lg",
        children=dmc.Stack(
            gap="md",
            children=[
                dmc.Text(
                    "Ces filtres s'appliquent à toutes les pages. Par défaut, ce sont "
                    "les bornes déjà appliquées par la source : on peut les resserrer "
                    "pour écarter des ventes atypiques.",
                    size="sm",
                    c="dimmed",
                ),
                _range(
                    "filter-annees",
                    "Années de vente",
                    BORNES["annees"],
                    1,
                    [{"value": y, "label": str(y)} for y in range(a0, a1 + 1)],
                ),
                _range(
                    "filter-prix",
                    "Prix de vente",
                    BORNES["prix"],
                    10_000,
                    [
                        {"value": v, "label": l}
                        for v, l in ((10_000, "10 k"), (1_000_000, "1 M"), (2_000_000, "2 M€"))
                    ],
                ),
                _range(
                    "filter-surface",
                    "Surface habitable",
                    BORNES["surface"],
                    1,
                    [{"value": v, "label": f"{v}"} for v in (9, 100, 200, 300, 400)],
                ),
                _range(
                    "filter-prix-m2",
                    "Prix au m²",
                    BORNES["prix_m2"],
                    50,
                    [
                        {"value": v, "label": f"{v // 1000} k" if v >= 1000 else str(v)}
                        for v in (300, 2000, 4000, 6000, 8000)
                    ],
                ),
                dmc.Group(
                    justify="space-between",
                    children=[
                        dmc.Button(
                            "Réinitialiser",
                            id="filters-reset",
                            variant="default",
                            leftSection=icon("tabler:restore", 16),
                        ),
                        dmc.Button(
                            "Appliquer", id="filters-apply", leftSection=icon("tabler:check", 16)
                        ),
                    ],
                ),
                dmc.Text(id="filters-summary", size="xs", c="dimmed"),
            ],
        ),
    )


def footer():
    return html.Footer(
        className="app-footer",
        children=dmc.Container(
            size="xl",
            children=[
                html.Span(
                    "Source : DGFiP, DVF (Etalab, données géolocalisées) · Licence Ouverte 2.0 · "
                ),
                html.Span("Contours : IGN Admin Express via geo.api.gouv.fr · "),
                dcc.Link("Méthodologie et limites", href="/methodologie"),
            ],
        ),
    )


app.layout = dmc.MantineProvider(
    id="mantine-provider",
    theme=MANTINE_THEME,
    forceColorScheme="light",
    children=[
        dcc.Store(id="color-scheme-store", storage_type="local", data="light"),
        dcc.Store(id="filters-store", storage_type="session", data=FILTRES_DEFAUT),
        dmc.AppShell(
            header={"height": 68},
            padding=0,
            children=[
                header(),
                filters_drawer(),
                dmc.AppShellMain(
                    [
                        dmc.Container(dash.page_container, size="xl", className="page-container"),
                        footer(),
                    ]
                ),
            ],
        ),
    ],
)


# --------------------------------------------------------------------------- #
# Thème clair / sombre (côté client, mémorisé dans le navigateur)
# --------------------------------------------------------------------------- #
clientside_callback(
    """(n, scheme) => (scheme === 'dark' ? 'light' : 'dark')""",
    Output("color-scheme-store", "data"),
    Input("theme-toggle", "n_clicks"),
    State("color-scheme-store", "data"),
    prevent_initial_call=True,
)

clientside_callback(
    """(scheme) => {
        document.body.dataset.agThemeMode = scheme;
        return scheme;
    }""",
    Output("mantine-provider", "forceColorScheme"),
    Input("color-scheme-store", "data"),
)

clientside_callback(
    """(scheme) => scheme === 'dark' ? 'tabler:sun' : 'tabler:moon'""",
    Output("theme-icon", "icon"),
    Input("color-scheme-store", "data"),
)


# --------------------------------------------------------------------------- #
# Navigation : lien actif
# --------------------------------------------------------------------------- #
clientside_callback(
    """(path, ids) => ids.map(id => {
        const href = id.href;
        const actif = href === '/' ? path === '/' : (path || '').startsWith(href)
            || (href === '/communes' && (path || '').startsWith('/commune/'));
        return actif ? 'nav-link nav-link--active' : 'nav-link';
    })""",
    Output({"type": "nav-link", "href": ALL}, "className"),
    Input("_pages_location", "pathname"),
    State({"type": "nav-link", "href": ALL}, "id"),
)


# --------------------------------------------------------------------------- #
# Filtres globaux
# --------------------------------------------------------------------------- #
@callback(
    Output("filters-drawer", "opened"),
    Input("filters-open", "n_clicks"),
    prevent_initial_call=True,
)
def ouvrir_filtres(_):
    return True


@callback(
    Output("filters-store", "data"),
    Output("filters-drawer", "opened", allow_duplicate=True),
    Input("zone-control", "value"),
    Input("filters-apply", "n_clicks"),
    Input("filters-reset", "n_clicks"),
    State("filter-annees", "value"),
    State("filter-prix", "value"),
    State("filter-surface", "value"),
    State("filter-prix-m2", "value"),
    State("filters-store", "data"),
    prevent_initial_call=True,
)
def maj_filtres(zone, _apply, _reset, annees, prix, surface, prix_m2, store):
    store = {**FILTRES_DEFAUT, **(store or {})}
    if ctx.triggered_id == "zone-control":
        if zone == store["zone"]:
            return no_update, no_update
        return {**store, "zone": zone}, no_update
    if ctx.triggered_id == "filters-reset":
        return {**FILTRES_DEFAUT, "zone": store["zone"]}, False
    return {
        "zone": store["zone"],
        "annees": annees,
        "prix": prix,
        "surface": surface,
        "prix_m2": prix_m2,
    }, False


@callback(
    Output("filter-annees", "value"),
    Output("filter-prix", "value"),
    Output("filter-surface", "value"),
    Output("filter-prix-m2", "value"),
    Output("filters-indicator", "disabled"),
    Input("filters-store", "data"),
)
def synchro_controles(store):
    s = {**FILTRES_DEFAUT, **(store or {})}
    personnalise = any(s[k] != FILTRES_DEFAUT[k] for k in ("annees", "prix", "surface", "prix_m2"))
    return s["annees"], s["prix"], s["surface"], s["prix_m2"], not personnalise


clientside_callback(
    """(annees, prix, surface, pm2) => {
        const nf = new Intl.NumberFormat('fr-FR', {maximumFractionDigits: 0});
        return [
            `${annees[0]} – ${annees[1]}`,
            `${nf.format(prix[0])} – ${nf.format(prix[1])} €`,
            `${surface[0]} – ${surface[1]} m²`,
            `${nf.format(pm2[0])} – ${nf.format(pm2[1])} €/m²`,
        ];
    }""",
    Output("filter-annees-label", "children"),
    Output("filter-prix-label", "children"),
    Output("filter-surface-label", "children"),
    Output("filter-prix-m2-label", "children"),
    Input("filter-annees", "value"),
    Input("filter-prix", "value"),
    Input("filter-surface", "value"),
    Input("filter-prix-m2", "value"),
)


if __name__ == "__main__":
    app.run(debug=os.environ.get("DASH_DEBUG", "1") == "1", port=int(os.environ.get("PORT", 8050)))
