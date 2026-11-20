"""Prépare les ventes du Loiret du 1er semestre 2026 à partir des DVF brutes (DGFiP).

Les données 2021-2025 du projet viennent des DVF géolocalisées d'Etalab. Pour
2026, seule la version brute de la DGFiP est publiée (pas de coordonnées) : ce
script en tire un fichier au même format que `immobilier.parquet`, avec les
mêmes règles de sélection.

Source : https://www.data.gouv.fr/datasets/demandes-de-valeurs-foncieres/
Fichier : valeursfoncieres-2026-s1.txt.zip (Licence Ouverte 2.0, « DGFiP, DVF »)

Usage :
    uv run python scripts/prepare_dvf_2026s1.py <chemin vers ValeursFoncieres-2026-S1.txt ou .zip>

Règles (identiques au fichier d'origine) :
- mutations de nature « Vente » du Loiret (département 45) ;
- une mutation = une ligne, comportant exactement un logement (maison ou
  appartement), les dépendances étant admises ;
- prix 10 k€ - 2 M€, surface 9 - 400 m², prix au m² 300 - 8 000 € ;
- surface du terrain = somme des parcelles distinctes de la mutation.

Faute d'identifiant de mutation dans la version brute, une mutation est
reconnue par : date, nature, valeur foncière, département et commune.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pandas as pd

ICI = Path(__file__).resolve().parents[1]
SORTIE = ICI / "data" / "immobilier_2026s1.parquet"
REFERENCE = ICI / "data" / "immobilier.parquet"

COLONNES = {
    "Date mutation": "date",
    "Nature mutation": "nature",
    "Valeur fonciere": "valeur",
    "Code postal": "code_postal",
    "Commune": "commune_brute",
    "Code departement": "dep",
    "Code commune": "com",
    "Prefixe de section": "prefixe",
    "Section": "section",
    "No plan": "plan",
    "1er lot": "lot",
    "Type local": "type",
    "Surface reelle bati": "surface",
    "Nombre pieces principales": "pieces",
    "Nature culture": "culture",
    "Surface terrain": "terrain",
}
CLE_MUTATION = ["date", "nature", "valeur", "dep", "com"]


def lire(chemin: Path) -> pd.DataFrame:
    options = dict(sep="|", dtype=str, usecols=list(COLONNES), encoding="utf-8")
    if chemin.suffix == ".zip":
        with zipfile.ZipFile(chemin) as z:
            nom = next(n for n in z.namelist() if n.lower().endswith(".txt"))
            with z.open(nom) as f:
                df = pd.read_csv(f, **options)
    else:
        df = pd.read_csv(chemin, **options)
    return df.rename(columns=COLONNES)


def nombre(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.str.replace(",", ".", regex=False), errors="coerce")


def preparer(brut: pd.DataFrame) -> pd.DataFrame:
    df = brut[(brut["dep"] == "45") & (brut["nature"] == "Vente")].copy()
    df = df.dropna(subset=["valeur"])
    df["mutation"] = df.groupby(CLE_MUTATION, sort=False).ngroup()

    # Logements distincts de chaque mutation (une ligne brute par lot × parcelle)
    logements = df[df["type"].isin(["Maison", "Appartement"])].drop_duplicates(
        ["mutation", "type", "surface", "pieces", "prefixe", "section", "plan", "lot"]
    )
    n_log = logements.groupby("mutation").size()
    uniques = n_log[n_log == 1].index
    out = logements[logements["mutation"].isin(uniques)].copy()

    # Terrain : parcelles distinctes de la mutation
    parcelles = df.dropna(subset=["terrain"]).drop_duplicates(
        ["mutation", "prefixe", "section", "plan", "culture"]
    )
    terrain = parcelles.assign(t=nombre(parcelles["terrain"])).groupby("mutation")["t"].sum()

    out["date_mutation"] = pd.to_datetime(out["date"], format="%d/%m/%Y")
    out["valeur_fonciere"] = nombre(out["valeur"])
    out["surface_reelle_bati"] = nombre(out["surface"])
    out["nombre_pieces_principales"] = nombre(out["pieces"])
    out["surface_terrain"] = out["mutation"].map(terrain).fillna(0.0)
    out["prix_m2"] = out["valeur_fonciere"] / out["surface_reelle_bati"]
    out["code_commune"] = out["dep"] + out["com"].str.zfill(3)
    out["code_postal"] = out["code_postal"].str.zfill(5)
    out["section"] = out["section"].fillna("").str.zfill(2)
    out["annee"] = out["date_mutation"].dt.year.astype("int32")

    out = out[
        out["valeur_fonciere"].between(10_000, 2_000_000)
        & out["surface_reelle_bati"].between(9, 400)
        & out["prix_m2"].between(300, 8_000)
    ]

    # Noms de communes identiques au fichier d'origine (casse, accents)
    ref = pd.read_parquet(REFERENCE, columns=["code_commune", "nom_commune"])
    noms = ref.drop_duplicates("code_commune").set_index("code_commune")["nom_commune"]
    out["nom_commune"] = out["code_commune"].map(noms).fillna(out["commune_brute"].str.title())

    out = out.sort_values(["date_mutation", "code_commune", "valeur_fonciere"])
    out["id_mutation"] = [f"2026S1-{i:06d}" for i in range(1, len(out) + 1)]
    out["longitude"] = float("nan")
    out["latitude"] = float("nan")
    return out


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    out = preparer(lire(Path(sys.argv[1])))
    types = pd.read_parquet(REFERENCE).dtypes
    out = out[list(types.index)].astype(types.to_dict())
    out.to_parquet(SORTIE, index=False)
    print(f"{len(out)} ventes du Loiret, 1er semestre 2026 -> {SORTIE}")
    print(out.groupby("type")["prix_m2"].median().round(0).to_dict())


if __name__ == "__main__":
    main()
