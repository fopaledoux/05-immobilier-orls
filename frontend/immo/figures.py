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


def vue_geo(features: list[dict]) -> tuple[dict, float]:
    """Centre et zoom qui cadrent des contours GeoJSON."""
    xs, ys = [], []
    for f in features:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            for x, y in poly[0]:
                xs.append(x)
                ys.append(y)
    if not xs:
        return {"lat": 47.9, "lon": 1.9}, 11
    span = max((max(ys) - min(ys)) * 1.45, max(xs) - min(xs), 0.004)
    zoom = min(max(np.log2(360 / span) - 0.35, 9), 15.5)
    return {"lat": (min(ys) + max(ys)) / 2, "lon": (min(xs) + max(xs)) / 2}, float(zoom)


def _custom_ventes(d: pd.DataFrame):
    return np.stack(
        [
            d["type"].astype(str),
            d["valeur_fonciere"].map(fmt.euros),
            d["surface_reelle_bati"].map(fmt.m2),
            d["prix_m2"].map(fmt.eur_m2),
            d["nom_quartier"],
            d["date_mutation"].dt.strftime("%d/%m/%Y"),
            d["code_iris"],
        ],
        axis=-1,
    )


HOVER_VENTE = (
    "<b>%{customdata[0]}</b> · %{customdata[2]}<br>%{customdata[1]} "
    "(%{customdata[3]})<br>%{customdata[4]} · %{customdata[5]}<extra></extra>"
)


def _colorbar(scheme: str, ticks) -> dict:
    c = COULEURS[scheme]
    return dict(
        title=dict(text="€/m²", font=dict(size=11, color=c["ink_2"])),
        thickness=10,
        len=0.6,
        x=0.99,
        xanchor="right",
        bgcolor="rgba(0,0,0,0)",
        outlinewidth=0,
        tickfont=dict(size=11, color=c["ink_2"]),
        tickvals=ticks,
        ticktext=[fmt.entier(t) for t in ticks],
    )


def carte_ventes(df: pd.DataFrame, scheme: str, center: dict, zoom: float) -> go.Figure:
    """Nuage des ventes géolocalisées, couleur = €/m² (communes sans quartiers)."""
    fig = _base(scheme)
    df = df.dropna(subset=["latitude", "longitude"])
    if not df.empty:
        lo, hi = df["prix_m2"].quantile([0.05, 0.95])
        fig.add_trace(
            go.Scattermap(
                lat=df["latitude"],
                lon=df["longitude"],
                mode="markers",
                marker=dict(
                    size=9,
                    color=df["prix_m2"],
                    cmin=lo,
                    cmax=hi,
                    colorscale=echelle_sequentielle(scheme),
                    opacity=0.9,
                    colorbar=_colorbar(scheme, np.linspace(lo, hi, 4)),
                ),
                customdata=_custom_ventes(df),
                hovertemplate=HOVER_VENTE,
            )
        )
    _map_layout(fig, scheme, "commune", center=center, zoom=zoom)
    return fig


def _hover_quartier(r) -> str:
    lignes = [
        f"<b>{r['nom_quartier']}</b>",
        f"<b>{fmt.eur_m2(r['pm2_med'])}</b> · {fmt.ventes(r['n'])}",
        f"Prix médian {fmt.euros(r['prix_med'])}",
    ]
    if not r["fiable"]:
        lignes.append(f"<i>Moins de {cfg.SEUIL_FIABILITE} ventes : indicatif</i>")
    lignes.append("<span style='font-size:11px'>Cliquer pour voir ses ventes</span>")
    return "<br>".join(lignes)


def carte_quartiers(
    stats: pd.DataFrame,
    geo: dict,
    scheme: str,
    selection: str | None,
    ventes_selection: pd.DataFrame,
) -> go.Figure:
    """Quartiers d'une commune colorés par prix médian au m², cliquables.

    Le quartier sélectionné est cerné, et ses ventes géolocalisées affichées.
    """
    c = COULEURS[scheme]
    fig = _base(scheme)
    features = geo["features"]
    par_code = {f["properties"]["code_iris"]: f for f in features}
    transparent = [[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]]

    def sous_geo(codes):
        feats = [par_code[k] for k in codes if k in par_code]
        return {"type": "FeatureCollection", "features": feats}

    stats = stats[stats["code_iris"].isin(par_code)]
    textes = [_hover_quartier(r) for _, r in stats.iterrows()]
    stats = stats.assign(_hover=textes)
    fiables, indicatifs = stats[stats["fiable"]], stats[~stats["fiable"]]
    line = dict(color=c["surface"], width=1.2)
    opacite = 0.45 if selection else 0.8

    vides = [k for k in par_code if k not in set(stats["code_iris"])]
    if vides:
        fig.add_trace(
            go.Choroplethmap(
                geojson=sous_geo(vides),
                featureidkey="properties.code_iris",
                locations=vides,
                z=np.zeros(len(vides)),
                colorscale=transparent,
                showscale=False,
                marker=dict(line=dict(color=c["axis"], width=1)),
                text=[
                    f"<b>{par_code[k]['properties']['nom_quartier']}</b><br>Aucune vente"
                    for k in vides
                ],
                hovertemplate="%{text}<extra></extra>",
            )
        )
    if not indicatifs.empty:
        fig.add_trace(
            go.Choroplethmap(
                geojson=sous_geo(indicatifs["code_iris"]),
                featureidkey="properties.code_iris",
                locations=indicatifs["code_iris"],
                z=np.zeros(len(indicatifs)),
                colorscale=[[0, c["indicatif"]], [1, c["indicatif"]]],
                showscale=False,
                marker=dict(line=line, opacity=opacite),
                text=indicatifs["_hover"],
                hovertemplate="%{text}<extra></extra>",
            )
        )
    if not fiables.empty:
        lo, hi = fiables["pm2_med"].min(), fiables["pm2_med"].max()
        if hi - lo < 1:
            lo, hi = lo - 100, hi + 100
        fig.add_trace(
            go.Choroplethmap(
                geojson=sous_geo(fiables["code_iris"]),
                featureidkey="properties.code_iris",
                locations=fiables["code_iris"],
                z=fiables["pm2_med"],
                zmin=lo,
                zmax=hi,
                colorscale=echelle_sequentielle(scheme),
                marker=dict(line=line, opacity=opacite),
                text=fiables["_hover"],
                hovertemplate="%{text}<extra></extra>",
                colorbar=_colorbar(scheme, np.linspace(lo, hi, 4)),
            )
        )
    if selection in par_code:
        fig.add_trace(
            go.Choroplethmap(
                geojson=sous_geo([selection]),
                featureidkey="properties.code_iris",
                locations=[selection],
                z=[0],
                colorscale=transparent,
                showscale=False,
                marker=dict(line=dict(color=c["ink"], width=3)),
                hoverinfo="skip",
            )
        )
        v = ventes_selection.dropna(subset=["latitude", "longitude"])
        if not v.empty:
            fig.add_trace(
                go.Scattermap(
                    lat=v["latitude"],
                    lon=v["longitude"],
                    mode="markers",
                    marker=dict(size=8, color=c["ink"], opacity=0.75),
                    customdata=_custom_ventes(v),
                    hovertemplate=HOVER_VENTE,
                )
            )
    center, zoom = vue_geo([par_code[selection]] if selection in par_code else features)
    _map_layout(fig, scheme, f"quartiers-{selection}", center=center, zoom=zoom)
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


def libelle_annee(annee) -> str:
    """« 2026 (janv.-juin) » pour l'année incomplète, sinon l'année seule."""
    partielle = cfg.ANNEE_PARTIELLE
    return partielle["label"] if int(annee) == partielle["annee"] else str(int(annee))


def volumes_annuels(df: pd.DataFrame, scheme: str) -> go.Figure:
    c = COULEURS[scheme]
    fig = _base(scheme, barmode="group", bargroupgap=0.08)
    partielle = cfg.ANNEE_PARTIELLE["annee"]
    for t in ("Maison", "Appartement"):
        d = df[df["type"] == t]
        fig.add_trace(
            go.Bar(
                x=d["annee"].map(libelle_annee),
                y=d["n"],
                name=t,
                marker=dict(
                    color=couleur_type(t, scheme),
                    # année incomplète : barre atténuée, pour ne pas lire une chute des ventes
                    opacity=[0.45 if a == partielle else 1 for a in d["annee"]],
                    cornerradius=4,
                    line=dict(width=0),
                ),
                customdata=d["n"].map(fmt.entier),
                hovertemplate=f"{t} · %{{x}} : %{{customdata}} ventes<extra></extra>",
            )
        )
    fig.update_yaxes(title_text="Nombre de ventes")
    fig.update_xaxes(showgrid=False, type="category")
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


def barres_quartiers(
    df: pd.DataFrame, scheme: str, selection: str | None, type_: str | None
) -> go.Figure:
    """Prix médian au m² par quartier nommé, du plus cher (haut) au moins cher."""
    c = COULEURS[scheme]
    if df.empty:
        return figure_vide(scheme, "Aucune vente avec ces filtres")
    base = couleur_type(type_ or "Maison", scheme)
    couleurs = [
        (
            (base if r.fiable else c["indicatif"])
            if (selection is None or r.code_iris == selection)
            else c["grid"]
        )
        for r in df.itertuples()
    ]
    fig = _base(scheme, hovermode="closest", bargap=0.2)
    fig.add_trace(
        go.Bar(
            y=df["nom_quartier"],
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
                    df["code_iris"],
                ],
                axis=-1,
            ),
            text=df["n"].map(lambda n: f"{n}"),
            textposition="outside",
            textfont=dict(size=11, color=c["muted"]),
            cliponaxis=False,
            hovertemplate=(
                "<b>%{y}</b><br>%{customdata[0]} · %{customdata[1]}"
                "<br>Prix médian %{customdata[2]}%{customdata[3]}"
                "<br><span style='font-size:11px'>Cliquer pour voir ses ventes</span>"
                "<extra></extra>"
            ),
        )
    )
    fig.update_yaxes(
        type="category",
        categoryorder="array",
        categoryarray=df["nom_quartier"].tolist(),
        showgrid=False,
        tickfont=dict(size=12),
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
                x=d["annee"].map(libelle_annee),
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
    fig.update_xaxes(showgrid=False, type="category")
    fig.update_yaxes(ticksuffix=" €")
    return fig


def _cercle(lat: float, lon: float, rayon_m: float, n: int = 72) -> tuple[list, list]:
    """Contour d'un cercle de `rayon_m` mètres (approximation locale)."""
    angles = np.linspace(0, 2 * np.pi, n)
    dlat = rayon_m / 111_320
    dlon = rayon_m / (111_320 * np.cos(np.radians(lat)))
    return list(lat + dlat * np.sin(angles)), list(lon + dlon * np.cos(angles))


def carte_autour(df: pd.DataFrame, scheme: str, point: dict, rayon: float, label: str) -> go.Figure:
    """Ventes à moins de `rayon` mètres d'une adresse, couleur = €/m²."""
    c = COULEURS[scheme]
    fig = _base(scheme)
    lats, lons = _cercle(point["lat"], point["lon"], rayon)
    fig.add_trace(
        go.Scattermap(
            lat=lats,
            lon=lons,
            mode="lines",
            fill="toself",
            fillcolor="rgba(42,120,214,0.08)",
            line=dict(color=c["maison"], width=2),
            hoverinfo="skip",
        )
    )
    v = df.dropna(subset=["latitude", "longitude"])
    if not v.empty:
        lo, hi = v["prix_m2"].quantile([0.05, 0.95])
        if hi - lo < 1:
            lo, hi = lo - 100, hi + 100
        fig.add_trace(
            go.Scattermap(
                lat=v["latitude"],
                lon=v["longitude"],
                mode="markers",
                marker=dict(
                    size=10,
                    color=v["prix_m2"],
                    cmin=lo,
                    cmax=hi,
                    colorscale=echelle_sequentielle(scheme),
                    opacity=0.9,
                    colorbar=_colorbar(scheme, np.linspace(lo, hi, 4)),
                ),
                customdata=_custom_ventes(v),
                hovertemplate=HOVER_VENTE,
            )
        )
    fig.add_trace(
        go.Scattermap(
            lat=[point["lat"]],
            lon=[point["lon"]],
            mode="markers",
            marker=dict(size=16, color=c["ink"]),
            text=[label],
            hovertemplate="<b>%{text}</b><br>Adresse recherchée<extra></extra>",
        )
    )
    zoom = float(np.clip(15.0 - np.log2(rayon / 300), 12, 16))
    _map_layout(
        fig,
        scheme,
        f"autour-{label}-{rayon}",
        center={"lat": point["lat"], "lon": point["lon"]},
        zoom=zoom,
    )
    return fig


def distribution_prix(
    valeurs: list[int], pm2_demande: float, pm2_med: float, scheme: str
) -> go.Figure:
    """Histogramme du €/m² des ventes comparables, avec le prix demandé et la médiane."""
    c = COULEURS[scheme]
    fig = _base(scheme, hovermode="closest", bargap=0.06)
    fig.add_trace(
        go.Histogram(
            x=valeurs,
            nbinsx=min(40, max(10, len(valeurs) // 8)),
            marker=dict(color=c["maison"], line=dict(width=0)),
            opacity=0.75,
            hovertemplate="%{x} €/m² : %{y} ventes<extra></extra>",
        )
    )
    for x, texte, couleur, tirets in (
        (pm2_med, f"Médiane {fmt.eur_m2(pm2_med)}", c["ink_2"], "dash"),
        (pm2_demande, f"Ce bien {fmt.eur_m2(pm2_demande)}", c["appartement"], "solid"),
    ):
        fig.add_vline(x=x, line=dict(color=couleur, width=2.5, dash=tirets))
        fig.add_annotation(
            x=x,
            y=1,
            yref="paper",
            text=texte,
            showarrow=False,
            xanchor="left",
            xshift=4,
            yshift=-2 if couleur == c["ink_2"] else -20,
            font=dict(size=12, color=c["ink"]),
            bgcolor=c["surface"],
        )
    fig.update_xaxes(
        title_text="Prix au m² des ventes comparables", ticksuffix=" €", showgrid=False
    )
    fig.update_yaxes(title_text="Nombre de ventes")
    fig.update_layout(showlegend=False, margin=dict(l=8, r=8, t=16, b=8))
    return fig
