"""Outils que l'assistant (Gemini) peut appeler pendant une discussion.

Chaque outil est une fonction Python typée et documentée : le SDK Gemini en
déduit la description donnée au modèle. Les outils renvoient des chiffres
calculés par l'API, arrondis et compacts ; le modèle ne fait que les expliquer.
Les filtres de l'utilisateur (années, prix, surface...) sont appliqués.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from dataclasses import replace

from immo_api import data
from immo_api.config import TAUX_FRAIS_NOTAIRE, ZONES
from immo_api.data import Filtres

TYPES = ("Maison", "Appartement")


def _sans_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s.lower().replace("-", " ").replace("'", " ").strip()


def _type(type_bien: str) -> str | None:
    t = (type_bien or "").strip().lower()
    if t.startswith("maison"):
        return "Maison"
    if t.startswith("app"):
        return "Appartement"
    return None


def _arrondi(v, pas=1):
    return None if v is None else int(round(v / pas) * pas)


def _bloc_type(d: dict) -> dict:
    return {
        "nombre_ventes": d["n"],
        "prix_m2_median": _arrondi(d["pm2_med"]),
        "prix_median": _arrondi(d["prix_med"], 100),
        "surface_mediane": _arrondi(d["surf_med"]),
        "fiable": d["fiable"],
    }


def outils(f: Filtres) -> list[Callable]:
    """Outils liés aux filtres en cours de l'utilisateur."""
    fl = replace(f, zone="loiret")  # une commune nommée est cherchée dans tout le Loiret

    def chercher_commune(nom: str) -> dict:
        """Trouve le code INSEE d'une commune du Loiret à partir de son nom.

        Args:
            nom: nom de la commune, même approximatif (ex. « st jean de braye »).
        """
        cible = _sans_accents(nom).replace("saint ", "st ")
        idx = data.communes_index()
        noms = idx["nom_commune"].map(lambda n: _sans_accents(n).replace("saint ", "st "))
        exact = idx[noms == cible]
        trouve = exact if len(exact) else idx[noms.str.contains(cible, regex=False)]
        return {
            "communes": [
                {
                    "code_commune": r.code_commune,
                    "nom": r.nom_commune,
                    "metropole": bool(r.metropole),
                }
                for r in trouve.head(5).itertuples()
            ]
        }

    def prix_commune(code_commune: str) -> dict:
        """Prix médians d'une commune (maisons et appartements) et nombre de quartiers.

        Args:
            code_commune: code INSEE à 5 chiffres (utiliser chercher_commune avant).
        """
        r = data.resume_commune(fl, code_commune)
        return {
            "code_commune": code_commune,
            "periode": f"{f.annee_min}-{f.annee_max}",
            "nombre_ventes": r["n"],
            "nombre_quartiers": r["n_quartiers"],
            "maison": _bloc_type(r["Maison"]),
            "appartement": _bloc_type(r["Appartement"]),
        }

    def prix_par_quartier(code_commune: str, type_bien: str = "") -> dict:
        """Prix médian au m² de chaque quartier d'une commune, du moins cher au plus cher.

        Args:
            code_commune: code INSEE à 5 chiffres.
            type_bien: « Maison », « Appartement », ou vide pour les deux.
        """
        df = data.stats_quartiers(fl, code_commune, _type(type_bien))
        return {
            "quartiers": [
                {
                    "quartier": r.nom_quartier,
                    "prix_m2_median": _arrondi(r.pm2_med),
                    "nombre_ventes": int(r.n),
                    "fiable": bool(r.fiable),
                }
                for r in df.itertuples()
            ]
        }

    def communes_pour_budget(
        budget_total: float,
        type_bien: str,
        surface_min: float,
        pieces_min: int = 0,
        frais_notaire_inclus: bool = True,
        zone: str = "metropole",
    ) -> dict:
        """Communes où un bien correspondant se vend en médiane dans le budget.

        Args:
            budget_total: budget en euros.
            type_bien: « Maison » ou « Appartement ».
            surface_min: surface habitable minimale en m².
            pieces_min: nombre de pièces minimum (0 = peu importe).
            frais_notaire_inclus: vrai si le budget comprend les frais de notaire (~7,5 %).
            zone: « metropole » (Orléans Métropole) ou « loiret » (tout le département).
        """
        t = _type(type_bien) or "Maison"
        prix_bien = (
            budget_total / (1 + TAUX_FRAIS_NOTAIRE) if frais_notaire_inclus else budget_total
        )
        z = zone if zone in ZONES else "metropole"
        df = data.budget_communes(replace(f, zone=z), t, prix_bien, surface_min, pieces_min)
        fiables = df[df["fiable"]]
        ok = fiables[fiables["dans_budget"]].sort_values("n_sous_budget", ascending=False)
        moins_cheres = fiables.sort_values("prix_med").head(3)
        return {
            "budget_total_eur": _arrondi(budget_total, 100),
            "frais_de_notaire_inclus_dans_le_budget": frais_notaire_inclus,
            "prix_maximum_du_bien_hors_frais_eur": _arrondi(prix_bien, 100),
            "zone": ZONES[z],
            "communes_fiables_examinees": len(fiables),
            "communes_dans_le_budget": [
                {
                    "commune": r.nom_commune,
                    "code_commune": r.code_commune,
                    "prix_median_comparables_eur": _arrondi(r.prix_med, 100),
                    "part_ventes_dans_budget_pct": _arrondi(r.part_sous_budget * 100),
                    "ventes_comparables_sous_le_budget": int(r.n_sous_budget),
                    "ventes_comparables_total_fondant_la_mediane": int(r.n),
                }
                for r in ok.head(10).itertuples()
            ],
            "communes_les_moins_cheres_pour_ce_bien": [
                {"commune": r.nom_commune, "prix_median_comparables_eur": _arrondi(r.prix_med, 100)}
                for r in moins_cheres.itertuples()
            ],
        }

    def classement_communes(
        type_bien: str = "Maison", zone: str = "metropole", ordre: str = "moins_cher"
    ) -> dict:
        """Communes classées par prix médian au m² (seulement celles d'au moins 30 ventes).

        Args:
            type_bien: « Maison » ou « Appartement ».
            zone: « metropole » ou « loiret ».
            ordre: « moins_cher » ou « plus_cher ».
        """
        z = zone if zone in ZONES else "metropole"
        df = data.stats_communes(replace(f, zone=z), _type(type_bien) or "Maison")
        df = df[df["fiable"]].sort_values("pm2_med", ascending=(ordre != "plus_cher"))
        return {
            "zone": ZONES[z],
            "communes": [
                {
                    "commune": r.nom_commune,
                    "code_commune": r.code_commune,
                    "prix_m2_median": _arrondi(r.pm2_med),
                    "nombre_ventes": int(r.n),
                }
                for r in df.head(10).itertuples()
            ],
        }

    def evolution_des_prix(zone: str = "metropole", type_bien: str = "Maison") -> dict:
        """Évolution du prix médian au m² et des volumes, 2021-2022 contre 2024-2025.

        Args:
            zone: « metropole » ou « loiret ».
            type_bien: « Maison » ou « Appartement » (pour les communes en plus forte variation).
        """
        z = zone if zone in ZONES else "metropole"
        fz = replace(f, zone=z)
        evo = data.evolution_globale(fz)
        ec = data.evolution_communes(fz, _type(type_bien) or "Maison")
        ec = ec[ec["fiable"]]

        def fmt(e):
            if not e:
                return None
            return {
                "prix_m2_avant": _arrondi(e["pm2_avant"]),
                "prix_m2_apres": _arrondi(e["pm2_apres"]),
                "variation_prix_pct": round(e["pm2_var"] * 100, 1),
                "variation_ventes_par_an_pct": round(e["ventes_var"] * 100),
            }

        def communes(d):
            return [
                {"commune": r.nom_commune, "variation_pct": round(r.var * 100, 1)}
                for r in d.itertuples()
            ]

        return {
            "zone": ZONES[z],
            "periodes": "2021-2022 contre 2024-2025",
            "maison": fmt(evo.get("Maison")),
            "appartement": fmt(evo.get("Appartement")),
            "plus_fortes_baisses": communes(ec.head(3)),
            "plus_fortes_hausses": communes(ec.tail(3).iloc[::-1]),
        }

    def evolution_commune(code_commune: str) -> dict:
        """Évolution du prix médian au m² d'une commune, 2021-2022 contre 2024-2025.

        Args:
            code_commune: code INSEE à 5 chiffres (utiliser chercher_commune avant).
        """
        res = {"code_commune": code_commune, "periodes": "2021-2022 contre 2024-2025"}
        for t in TYPES:
            ec = data.evolution_communes(fl, t)
            ligne = ec[ec["code_commune"] == code_commune]
            if ligne.empty:
                res[t.lower()] = "pas de vente sur l'une des deux périodes"
                continue
            r = ligne.iloc[0]
            res[t.lower()] = {
                "prix_m2_avant": _arrondi(r["pm2_med_avant"]),
                "prix_m2_apres": _arrondi(r["pm2_med_apres"]),
                "variation_pct": round(float(r["var"]) * 100, 1),
                "ventes_avant": int(r["n_avant"]),
                "ventes_apres": int(r["n_apres"]),
                "fiable": bool(r["fiable"]),
            }
        return res

    def evaluer_un_prix(code_commune: str, type_bien: str, surface: float, prix: float) -> dict:
        """Situe un prix (annonce) par rapport aux ventes comparables de la commune.

        Args:
            code_commune: code INSEE à 5 chiffres.
            type_bien: « Maison » ou « Appartement ».
            surface: surface habitable en m².
            prix: prix demandé en euros.
        """
        return resume_evaluation(
            data.evaluer_prix(fl, code_commune, _type(type_bien) or "Maison", surface, prix)
        )

    return [
        chercher_commune,
        prix_commune,
        prix_par_quartier,
        communes_pour_budget,
        classement_communes,
        evolution_des_prix,
        evolution_commune,
        evaluer_un_prix,
    ]


def resume_evaluation(e: dict) -> dict:
    """Version compacte d'une évaluation de prix (sans la liste des valeurs)."""
    out = {
        "type": e["type"],
        "surface_m2": _arrondi(e["surface"]),
        "prix": _arrondi(e["prix"], 100),
        "prix_m2": _arrondi(e["pm2"]),
        "nombre_ventes_comparables": e["n"],
        "comparables": f"{e['type'].lower()}s de la commune entre {_arrondi(e['surf_min'])} et "
        f"{_arrondi(e['surf_max'])} m²",
        "fiable": e["fiable"],
    }
    if not e["evaluable"]:
        out["evaluable"] = False
        return out
    out.update(
        prix_m2_median_comparables=_arrondi(e["pm2_med"]),
        moitie_des_comparables_entre=[_arrondi(e["pm2_q1"]), _arrondi(e["pm2_q3"])],
        prix_equivalent_a_la_mediane=_arrondi(e["prix_equivalent"], 100),
        ecart_a_la_mediane_pct=round(e["ecart"] * 100, 1),
        part_comparables_moins_chers_pct=_arrondi(e["rang"] * 100),
        position=e["position"],
    )
    return out
