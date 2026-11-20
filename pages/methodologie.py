"""Méthodologie : sources, filtres, choix de calcul et limites."""

import dash
import dash_mantine_components as dmc
from dash import dcc, html

from immo import fmt
from immo.components import icon, page_header
from immo.config import BORNES, PERIODE_APRES, PERIODE_AVANT, SEUIL_FIABILITE, TAUX_FRAIS_NOTAIRE

dash.register_page(__name__, path="/methodologie", name="Méthodologie", order=4)


def _bloc(titre, ico, contenu):
    return dmc.Paper(
        withBorder=True,
        className="method-card",
        children=[
            dmc.Group(
                gap="xs",
                mb="xs",
                children=[
                    html.Span(icon(ico, 18), className="answer-icon"),
                    dmc.Text(titre, fw=700),
                ],
            ),
            dcc.Markdown(contenu, className="method-text"),
        ],
    )


def layout(**_):
    p0, p1 = BORNES["prix"]
    s0, s1 = BORNES["surface"]
    m0, m1 = BORNES["prix_m2"]
    frais = f"{TAUX_FRAIS_NOTAIRE:.1%}".replace(".", ",")
    return html.Div(
        [
            page_header(
                "Méthodologie et limites",
                "D'où viennent les chiffres, comment ils sont calculés, et ce qu'ils ne disent pas.",
                eyebrow="Méthodologie",
            ),
            dmc.SimpleGrid(
                cols={"base": 1, "md": 2},
                spacing="md",
                className="section",
                children=[
                    _bloc(
                        "Source des données",
                        "tabler:database",
                        "**Demandes de valeurs foncières (DVF)** : toutes les ventes immobilières enregistrées "
                        "par l'administration fiscale, republiées et géolocalisées par Etalab.\n\n"
                        "Ici : les ventes d'**un seul logement** (maison ou appartement) dans le Loiret, "
                        "du 02/01/2021 au 31/12/2025, soit 46 022 ventes dans 325 communes.\n\n"
                        "Source : *DGFiP, DVF*, Licence Ouverte 2.0. Contours des communes : "
                        "IGN Admin Express via geo.api.gouv.fr.",
                    ),
                    _bloc(
                        "Filtres appliqués",
                        "tabler:filter",
                        f"Filtres de la source, qui sont aussi les valeurs par défaut des filtres de l'appli :\n\n"
                        f"- prix de vente entre {fmt.euros(p0)} et {fmt.euros(p1)}\n"
                        f"- surface habitable entre {s0} et {s1} m²\n"
                        f"- prix au m² entre {fmt.entier(m0)} et {fmt.eur_m2(m1)}\n\n"
                        "Le bouton **Filtres** (en haut à droite) permet de resserrer ces bornes, par exemple "
                        "pour écarter des ventes atypiques. Un point bleu sur le bouton signale des filtres "
                        "modifiés.",
                    ),
                    _bloc(
                        "Médianes et fiabilité",
                        "tabler:chart-dots",
                        "Tous les prix sont des **médianes** : la moitié des ventes est au-dessus, l'autre "
                        "au-dessous. Contrairement à la moyenne, la médiane ne monte pas à cause de quelques "
                        "ventes très chères.\n\n"
                        f"Une médiane calculée sur peu de ventes n'est pas fiable : en dessous de "
                        f"**{SEUIL_FIABILITE} ventes**, une commune ou une section reste en gris et son prix est "
                        "dit *indicatif*. Le nombre de ventes est toujours affiché à côté du prix.",
                    ),
                    _bloc(
                        "Mon budget",
                        "tabler:wallet",
                        f"Si la case *frais de notaire inclus* est cochée, on retire environ **{frais}** "
                        "(frais d'acquisition dans l'ancien) pour obtenir le prix maximum du bien.\n\n"
                        "Pour chaque commune, on garde les ventes **comparables** (même type, surface et "
                        "nombre de pièces au moins égaux à ceux demandés), puis on calcule la part vendue "
                        "dans le budget. Une commune est *dans le budget* quand le prix médian des "
                        "comparables y tient.",
                    ),
                    _bloc(
                        "Tendances",
                        "tabler:chart-line",
                        f"On compare deux périodes de deux ans : **{PERIODE_AVANT[0]}-{PERIODE_AVANT[1]}** "
                        f"(avant et pendant la remontée des taux, entamée à l'été 2022) et "
                        f"**{PERIODE_APRES[0]}-{PERIODE_APRES[1]}**. Des périodes de deux ans donnent assez de "
                        "ventes par commune pour une médiane stable.\n\n"
                        "La variation des volumes compare le nombre moyen de ventes **par an**.",
                    ),
                    _bloc(
                        "Ce que les données ne disent pas",
                        "tabler:alert-triangle",
                        "- **ni l'état, ni l'étage, ni le DPE** : deux biens au même prix au m² ne se valent "
                        "pas forcément\n"
                        "- **pas d'adresse** : la section cadastrale (quelques rues) est le niveau le plus fin\n"
                        "- le prix d'une maison **inclut le terrain**\n"
                        "- ce sont des prix **de vente**, pas des prix affichés en agence\n"
                        "- 1 011 ventes n'ont pas de coordonnées : elles comptent dans les statistiques mais "
                        "n'apparaissent pas sur la carte des ventes",
                    ),
                ],
            ),
        ]
    )
