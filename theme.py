"""Thème partagé : couleurs, typographie, templates Plotly clair/sombre.

Palette : rôles validés (contraste, daltonisme) pour le clair ET le sombre.
- Maison = bleu (catégorie 1), Appartement = orange (catégorie 2)
- Magnitudes (prix) = rampe séquentielle bleue, une seule teinte
- Variations (hausse/baisse) = divergente bleu <-> rouge, milieu gris neutre
"""

import plotly.graph_objects as go
import plotly.io as pio

FONT_FAMILY = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'

COULEURS = {
    "light": {
        "surface": "#fcfcfb",
        "page": "#f9f9f7",
        "ink": "#0b0b0b",
        "ink_2": "#52514e",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
        "maison": "#2a78d6",
        "appartement": "#eb6834",
        "indicatif": "#d6d5ce",  # commune / section sous le seuil de fiabilité
        "neutre": "#f0efec",
        "hausse": "#e34948",
        "baisse": "#2a78d6",
        "map_style": "carto-positron",
    },
    "dark": {
        "surface": "#1a1a19",
        "page": "#0d0d0d",
        "ink": "#f0efec",
        "ink_2": "#c3c2b7",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "axis": "#383835",
        "maison": "#3987e5",
        "appartement": "#d95926",
        "indicatif": "#4a4a46",
        "neutre": "#383835",
        "hausse": "#e66767",
        "baisse": "#3987e5",
        "map_style": "carto-darkmatter",
    },
}

# Rampe séquentielle bleue (100 -> 700)
RAMPE_BLEUE = [
    "#cde2fb",
    "#b7d3f6",
    "#9ec5f4",
    "#86b6ef",
    "#6da7ec",
    "#5598e7",
    "#3987e5",
    "#2a78d6",
    "#256abf",
    "#1c5cab",
    "#184f95",
    "#104281",
    "#0d366b",
]


def echelle_sequentielle(scheme: str) -> list:
    """Clair : faible = clair. Sombre : faible = sombre (se fond dans le fond)."""
    rampe = RAMPE_BLEUE if scheme == "light" else RAMPE_BLEUE[::-1]
    n = len(rampe) - 1
    return [[i / n, c] for i, c in enumerate(rampe)]


def echelle_divergente(scheme: str) -> list:
    c = COULEURS[scheme]
    if scheme == "light":
        baisse = ["#104281", "#2a78d6", "#86b6ef"]
        hausse = ["#f2a7a5", "#e34948", "#a12a2a"]
    else:
        baisse = ["#86b6ef", "#3987e5", "#1c5cab"]
        hausse = ["#9e3434", "#e66767", "#f4b0ae"]
    pts = baisse + [c["neutre"]] + hausse
    return [[i / (len(pts) - 1), col] for i, col in enumerate(pts)]


def couleur_type(type_: str, scheme: str) -> str:
    return COULEURS[scheme]["maison" if type_ == "Maison" else "appartement"]


# Couleurs Mantine (10 nuances) pour la couleur primaire de l'interface
MANTINE_BLEU = [
    "#eaf2fd",
    "#cde2fb",
    "#9ec5f4",
    "#6da7ec",
    "#3987e5",
    "#2a78d6",
    "#256abf",
    "#1c5cab",
    "#184f95",
    "#104281",
]

MANTINE_THEME = {
    "fontFamily": FONT_FAMILY,
    "headings": {"fontFamily": FONT_FAMILY, "fontWeight": "700"},
    "primaryColor": "immo",
    "primaryShade": {"light": 5, "dark": 4},
    "colors": {"immo": MANTINE_BLEU},
    "defaultRadius": "md",
    "radius": {"md": "10px", "lg": "14px"},
}

GRAPH_CONFIG = {"displayModeBar": False, "responsive": True}


def _template(scheme: str) -> go.layout.Template:
    c = COULEURS[scheme]
    axis = dict(
        gridcolor=c["grid"],
        linecolor=c["axis"],
        zerolinecolor=c["axis"],
        tickfont=dict(color=c["muted"], size=12),
        title=dict(font=dict(color=c["ink_2"], size=12)),
        showline=False,
        ticks="",
        automargin=True,
    )
    return go.layout.Template(
        layout=dict(
            font=dict(family=FONT_FAMILY, color=c["ink"], size=13),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            colorway=[c["maison"], c["appartement"], "#1baf7a"],
            separators=", ",
            xaxis=axis,
            yaxis=axis,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="left",
                x=0,
                font=dict(color=c["ink_2"], size=12),
                title_text="",
            ),
            hoverlabel=dict(
                bgcolor=c["surface"],
                bordercolor=c["axis"],
                font=dict(family=FONT_FAMILY, color=c["ink"], size=13),
            ),
            margin=dict(l=8, r=8, t=36, b=8),
            bargap=0.25,
        )
    )


pio.templates["immo_light"] = _template("light")
pio.templates["immo_dark"] = _template("dark")


def template(scheme: str) -> str:
    return "immo_dark" if scheme == "dark" else "immo_light"
