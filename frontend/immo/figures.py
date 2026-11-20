"""Construction des figures Plotly (thème clair/sombre passé en argument)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from immo import fmt
from immo import config as cfg
from immo.api import geojson_zone
from theme import COULEURS, couleur_type, echelle_divergente, echelle_sequentielle, template


def _base(scheme: str, **layout) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(template=template(scheme), **layout)
    return fig


def figure_vide(scheme: str, message: str) -> go.Figure:
    c = COULEURS[scheme]
    fig = _base(scheme)
    fig.update_layout(
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        annotations=[
            dict(
                text=message,
                showarrow=False,
                font=dict(color=c["muted"], size=14),
                xref="paper",
                yref="paper",
                x=0.5,
                y=0.5,
            )
        ],
    )
    return fig


# --------------------------------------------------------------------------- #
# Cartes
# --------------------------------------------------------------------------- #
def _map_layout(fig: go.Figure, scheme: str, zone: str, center=None, zoom=None):
    z = cfg.ZONES.get(zone, cfg.ZONES["loiret"])
    fig.update_layout(
        map=dict(
            style=COULEURS[scheme]["map_style"],
            center=center or z["center"],
            zoom=zoom if zoom is not None else z["zoom"],
        ),
        margin=dict(l=0, r=0, t=0, b=0),
        uirevision=f"{zone}-{center}",
        showlegend=False,
    )


def carte_communes(
    stats: pd.DataFrame,
    scheme: str,
    zone: str,
    valeur: str,
    titre_echelle: str,
    format_valeur,
    lignes_hover,
    divergente: bool = False,
    zrange: tuple[float, float] | None = None,
    col_fiable: str = "fiable",
) -> go.Figure:
    """Choroplèthe des communes. Les communes « indicatives » sont en gris.

    `lignes_hover(row)` renvoie la liste des lignes de détail de l'infobulle.
    """
    c = COULEURS[scheme]
    geo = geojson_zone(zone)

    def sous_geo(codes):
        """Chaque couche ne reçoit que ses propres contours (payload divisé)."""
        codes = set(codes)
        return {
            "type": "FeatureCollection",
            "features": [f for f in geo["features"] if f["properties"]["code"] in codes],
        }

    fig = _base(scheme)
    if stats.empty:
        _map_layout(fig, scheme, zone)
        return fig

    def hover_text(row):
        lignes = [f"<b>{row['nom_commune']}</b>", *lignes_hover(row)]
        if not row[col_fiable]:
            lignes.append(f"<i>Moins de {cfg.SEUIL_FIABILITE} ventes : indicatif</i>")
        lignes.append("<span style='font-size:11px'>Cliquer pour la fiche commune</span>")
        return "<br>".join(lignes)

    stats = stats.assign(_hover=stats.apply(hover_text, axis=1))
    fiables = stats[stats[col_fiable]]
    indicatifs = stats[~stats[col_fiable]]

    if zrange is None and not fiables.empty:
        zrange = (fiables[valeur].quantile(0.02), fiables[valeur].quantile(0.98))
    if divergente and zrange is not None:
        m = max(abs(zrange[0]), abs(zrange[1]))
        zrange = (-m, m)

    line = dict(color=c["surface"], width=0.8)
    if not indicatifs.empty:
        fig.add_trace(
            go.Choroplethmap(
                geojson=sous_geo(indicatifs["code_commune"]),
                featureidkey="properties.code",
                locations=indicatifs["code_commune"],
                z=np.zeros(len(indicatifs)),
                colorscale=[[0, c["indicatif"]], [1, c["indicatif"]]],
                showscale=False,
                marker=dict(line=line, opacity=0.75),
                text=indicatifs["_hover"],
                hovertemplate="%{text}<extra></extra>",
            )
        )
    if not fiables.empty:
        ticks = np.linspace(zrange[0], zrange[1], 5)
        fig.add_trace(
            go.Choroplethmap(
                geojson=sous_geo(fiables["code_commune"]),
                featureidkey="properties.code",
                locations=fiables["code_commune"],
                z=fiables[valeur],
                zmin=zrange[0],
                zmax=zrange[1],
                colorscale=(
                    echelle_divergente(scheme) if divergente else echelle_sequentielle(scheme)
                ),
                marker=dict(line=line, opacity=0.85),
                text=fiables["_hover"],
                hovertemplate="%{text}<extra></extra>",
                colorbar=dict(
                    title=dict(text=titre_echelle, font=dict(size=11, color=c["ink_2"])),
                    thickness=10,
                    len=0.6,
                    x=0.99,
                    xanchor="right",
                    y=0.5,
                    bgcolor="rgba(0,0,0,0)",
                    outlinewidth=0,
                    tickfont=dict(size=11, color=c["ink_2"]),
                    tickvals=ticks,
                    ticktext=[format_valeur(t) for t in ticks],
                ),
            )
        )
    _map_layout(fig, scheme, zone)
    return fig


def carte_ventes(
    df: pd.DataFrame, scheme: str, section: str | None, center: dict, zoom: float
) -> go.Figure:
    """Nuage des ventes géolocalisées d'une commune, couleur = €/m²."""
    c = COULEURS[scheme]
    fig = _base(scheme)
    df = df.dropna(subset=["latitude", "longitude"])
    if section:
        autres, df_sel = df[df["section"] != section], df[df["section"] == section]
    else:
        autres, df_sel = df.iloc[0:0], df

    def custom(d):
        return np.stack(
            [
                d["type"].astype(str),
                d["valeur_fonciere"].map(fmt.euros),
                d["surface_reelle_bati"].map(fmt.m2),
                d["prix_m2"].map(fmt.eur_m2),
                d["section"],
                d["date_mutation"].dt.strftime("%d/%m/%Y"),
            ],
            axis=-1,
        )

    hover = (
        "<b>%{customdata[0]}</b> · %{customdata[2]}<br>%{customdata[1]} "
        "(%{customdata[3]})<br>Section %{customdata[4]} · %{customdata[5]}<extra></extra>"
    )
    if not autres.empty:
        fig.add_trace(
            go.Scattermap(
                lat=autres["latitude"],
                lon=autres["longitude"],
                mode="markers",
                marker=dict(size=7, color=c["indicatif"], opacity=0.6),
                customdata=custom(autres),
                hovertemplate=hover,
            )
        )
    if not df_sel.empty:
        lo, hi = df_sel["prix_m2"].quantile([0.05, 0.95])
        ticks = np.linspace(lo, hi, 4)
        fig.add_trace(
            go.Scattermap(
                lat=df_sel["latitude"],
                lon=df_sel["longitude"],
                mode="markers",
                marker=dict(
                    size=9,
                    color=df_sel["prix_m2"],
                    cmin=lo,
                    cmax=hi,
                    colorscale=echelle_sequentielle(scheme),
                    opacity=0.9,
                    colorbar=dict(
                        title=dict(text="€/m²", font=dict(size=11, color=c["ink_2"])),
                        thickness=10,
                        len=0.6,
                        x=0.99,
                        xanchor="right",
                        outlinewidth=0,
                        tickfont=dict(size=11, color=c["ink_2"]),
                        tickvals=ticks,
                        ticktext=[fmt.entier(t) for t in ticks],
                    ),
                ),
                customdata=custom(df_sel),
                hovertemplate=hover,
            )
        )
    _map_layout(fig, scheme, "commune", center=center, zoom=zoom)
    return fig


# --------------------------------------------------------------------------- #
# Graphiques
# --------------------------------------------------------------------------- #
def tendance_trimestrielle(df: pd.DataFrame, scheme: str, mesure: str = "pm2_med") -> go.Figure:
    """Prix médian au m² par trimestre, maison vs appartement."""
    c = COULEURS[scheme]
    fig = _base(scheme, hovermode="x unified")
    if df.empty:
        return figure_vide(scheme, "Aucune vente avec ces filtres")
    derniers = {}
    for t in ("Maison", "Appartement"):
        d = df[df["type"] == t]
        if d.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=d["label"],
                y=d[mesure],
                name=t,
                mode="lines",
                line=dict(color=couleur_type(t, scheme), width=2.5),
                customdata=np.stack([d[mesure].map(fmt.eur_m2), d["n"].map(fmt.ventes)], axis=-1),
                hovertemplate=f"{t} : %{{customdata[0]}} · %{{customdata[1]}} sur 12 mois<extra></extra>",
            )
        )
        derniers[t] = d.iloc[-1]
    # Étiquettes de fin de courbe : la plus haute au-dessus, l'autre en dessous
    ordre = sorted(derniers, key=lambda t: derniers[t][mesure], reverse=True)
    for rang, t in enumerate(ordre):
        dernier = derniers[t]
        fig.add_annotation(
            x=dernier["label"],
            y=dernier[mesure],
            text=f"{t} {fmt.eur_m2(dernier[mesure])}",
            showarrow=False,
            xanchor="right",
            yanchor="bottom" if rang == 0 else "top",
            yshift=8 if rang == 0 else -8,
            font=dict(size=12, color=c["ink_2"]),
            bgcolor=c["surface"],
        )
    labels = df.drop_duplicates("label").sort_values("ordre")["label"].tolist()
    if "T3 2022" in labels:
        fig.add_vline(x="T3 2022", line=dict(color=c["axis"], width=1, dash="dot"))
        fig.add_annotation(
            x="T3 2022",
            y=1,
            yref="paper",
            text="Hausse des taux (été 2022)",
            showarrow=False,
            xanchor="left",
            xshift=4,
            font=dict(size=11, color=c["muted"]),
        )
    fig.update_xaxes(
        categoryorder="array", categoryarray=labels, tickangle=0, nticks=6, showgrid=False
    )
    fig.update_yaxes(ticksuffix=" €", rangemode="normal")
    return fig


def volumes_annuels(df: pd.DataFrame, scheme: str) -> go.Figure:
    c = COULEURS[scheme]
    fig = _base(scheme, barmode="group", bargroupgap=0.08)
    for t in ("Maison", "Appartement"):
        d = df[df["type"] == t]
        fig.add_trace(
            go.Bar(
                x=d["annee"].astype(str),
                y=d["n"],
                name=t,
                marker=dict(color=couleur_type(t, scheme), cornerradius=4, line=dict(width=0)),
                customdata=d["n"].map(fmt.entier),
                hovertemplate=f"{t} · %{{x}} : %{{customdata}} ventes<extra></extra>",
            )
        )
    fig.update_yaxes(title_text="Nombre de ventes")
    fig.update_xaxes(showgrid=False)
    fig.update_layout(hovermode="closest")
    return fig


def maison_vs_appart(df: pd.DataFrame, scheme: str, n_max: int = 15) -> go.Figure:
    """Dot plot : €/m² médian maison et appartement, communes les plus actives."""
    c = COULEURS[scheme]
    d = df[df["fiable_maison"] & df["fiable_appart"]].head(n_max)
    if d.empty:
        return figure_vide(
            scheme, f"Aucune commune avec {cfg.SEUIL_FIABILITE} ventes de chaque type"
        )
    d = d.sort_values("pm2_med_maison")
    fig = _base(scheme, hovermode="closest")
    for _, r in d.iterrows():
        fig.add_trace(
            go.Scatter(
                x=[r["pm2_med_maison"], r["pm2_med_appart"]],
                y=[r["nom_commune"]] * 2,
                mode="lines",
                line=dict(color=c["axis"], width=2),
                hoverinfo="skip",
                showlegend=False,
            )
        )
    for t, col, ncol in (
        ("Maison", "pm2_med_maison", "n_maison"),
        ("Appartement", "pm2_med_appart", "n_appart"),
    ):
        fig.add_trace(
            go.Scatter(
                x=d[col],
                y=d["nom_commune"],
                mode="markers",
                name=t,
                marker=dict(
                    size=11,
                    color=couleur_type(t, scheme),
                    line=dict(color=c["surface"], width=2),
                ),
                customdata=np.stack([d[col].map(fmt.eur_m2), d[ncol].map(fmt.ventes)], axis=-1),
                hovertemplate=f"<b>%{{y}}</b><br>{t} : %{{customdata[0]}} (%{{customdata[1]}})<extra></extra>",
            )
        )
    fig.update_xaxes(ticksuffix=" €", title_text="Prix médian au m²")
    fig.update_yaxes(showgrid=False)
    fig.update_layout(margin=dict(l=8, r=16, t=40, b=8))
    return fig


def barres_sections(
    df: pd.DataFrame, scheme: str, selection: str | None, type_: str | None
) -> go.Figure:
    c = COULEURS[scheme]
    if df.empty:
        return figure_vide(scheme, "Aucune vente avec ces filtres")
    base = couleur_type(type_ or "Maison", scheme)
    couleurs = [
        (
            (base if r.fiable else c["indicatif"])
            if (selection is None or r.section == selection)
            else c["grid"]
        )
        for r in df.itertuples()
    ]
    fig = _base(scheme, hovermode="closest", bargap=0.2)
    fig.add_trace(
        go.Bar(
            y=df["section"],
            x=df["pm2_med"],
            orientation="h",
            marker=dict(color=couleurs, cornerradius=4, line=dict(width=0)),
            customdata=np.stack(
                [
                    df["pm2_med"].map(fmt.eur_m2),
                    df["n"].map(fmt.ventes),
                    df["prix_med"].map(fmt.euros),
                    np.where(
                        df["fiable"],
                        "",
                        f"<br><i>Moins de {cfg.SEUIL_FIABILITE} ventes : indicatif</i>",
                    ),
                ],
                axis=-1,
            ),
            text=df["n"].map(lambda n: f"{n}"),
            textposition="outside",
            textfont=dict(size=11, color=c["muted"]),
            cliponaxis=False,
            hovertemplate=(
                "<b>Section %{y}</b><br>%{customdata[0]} · %{customdata[1]}"
                "<br>Prix médian %{customdata[2]}%{customdata[3]}"
                "<br><span style='font-size:11px'>Cliquer pour filtrer les ventes</span><extra></extra>"
            ),
        )
    )
    fig.update_yaxes(
        type="category", categoryorder="array", categoryarray=df["section"].tolist(), showgrid=False
    )
    fig.update_xaxes(ticksuffix=" €", side="top")
    fig.update_layout(margin=dict(l=8, r=36, t=24, b=8), showlegend=False)
    return fig


def barres_evolution(df: pd.DataFrame, scheme: str, n: int = 8) -> go.Figure:
    """Plus fortes baisses et hausses du €/m² médian (communes fiables)."""
    c = COULEURS[scheme]
    d = df[df["fiable"]].sort_values("var")
    if d.empty:
        return figure_vide(
            scheme, f"Aucune commune avec {cfg.SEUIL_FIABILITE} ventes sur chaque période"
        )
    d = pd.concat([d.head(n), d.tail(n)]).drop_duplicates("code_commune")
    fig = _base(scheme, hovermode="closest", bargap=0.25)
    fig.add_trace(
        go.Bar(
            y=d["nom_commune"],
            x=d["var"] * 100,
            orientation="h",
            marker=dict(
                color=[c["baisse"] if v < 0 else c["hausse"] for v in d["var"]],
                cornerradius=4,
                line=dict(width=0),
            ),
            text=d["var"].map(fmt.pct),
            textposition="outside",
            textfont=dict(size=11, color=c["ink_2"]),
            cliponaxis=False,
            customdata=np.stack(
                [
                    d["pm2_med_avant"].map(fmt.eur_m2),
                    d["pm2_med_apres"].map(fmt.eur_m2),
                    d["n_avant"].map(fmt.entier),
                    d["n_apres"].map(fmt.entier),
                ],
                axis=-1,
            ),
            hovertemplate=(
                f"<b>%{{y}}</b><br>{cfg.PERIODE_AVANT[0]}-{cfg.PERIODE_AVANT[1]} : %{{customdata[0]}} "
                f"(%{{customdata[2]}} ventes)<br>{cfg.PERIODE_APRES[0]}-{cfg.PERIODE_APRES[1]} : %{{customdata[1]}} "
                "(%{customdata[3]} ventes)<extra></extra>"
            ),
        )
    )
    fig.update_yaxes(
        type="category",
        categoryorder="array",
        categoryarray=d["nom_commune"].tolist(),
        showgrid=False,
    )
    fig.update_xaxes(ticksuffix=" %", zeroline=True, zerolinecolor=c["axis"], zerolinewidth=1)
    fig.update_layout(margin=dict(l=8, r=48, t=16, b=8), showlegend=False)
    return fig


def tendance_annuelle_commune(df: pd.DataFrame, scheme: str) -> go.Figure:
    """Évolution annuelle du €/m² médian pour une commune (n affiché au survol)."""
    c = COULEURS[scheme]
    fig = _base(scheme, hovermode="x unified")
    for t in ("Maison", "Appartement"):
        d = df[df["type"] == t]
        if d.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=d["annee"].astype(str),
                y=d["pm2_med"],
                name=t,
                mode="lines+markers",
                line=dict(color=couleur_type(t, scheme), width=2),
                marker=dict(
                    size=9,
                    color=[couleur_type(t, scheme) if f else c["surface"] for f in d["fiable"]],
                    line=dict(color=couleur_type(t, scheme), width=2),
                ),
                customdata=np.stack(
                    [d["pm2_med"].map(fmt.eur_m2), d["n"].map(fmt.ventes)], axis=-1
                ),
                hovertemplate=f"{t} : %{{customdata[0]}} · %{{customdata[1]}}<extra></extra>",
            )
        )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(ticksuffix=" €")
    return fig
