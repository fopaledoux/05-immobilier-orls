"""Rattache chaque vente à son quartier nommé (IRIS de l'INSEE).

Les sections cadastrales (« AB », « DX »…) ne parlent pas aux acheteurs. On les
remplace par les quartiers IRIS, découpage officiel de l'INSEE (environ
2 000 habitants par quartier) qui porte des noms connus : « Carmes-République »,
« Saint-Marceau »… Les communes trop petites forment un seul IRIS.

Source : contours IRIS 2024 (IGN / INSEE, Licence Ouverte 2.0), jeu
« georef-france-iris » d'OpenDataSoft, filtré sur le Loiret :
https://public.opendatasoft.com/explore/dataset/georef-france-iris/

Usage :
    uv run python scripts/prepare_quartiers.py <iris_loiret.geojson>

Produit, dans backend/data :
- quartiers_loiret.geojson : contours simplifiés (code_iris, nom_quartier,
  code_commune, irisee) ;
- ventes_quartiers.parquet : id_mutation -> code_iris.

Rattachement : les ventes géolocalisées par leur position (point dans le
polygone) ; les autres (dont tout 2026) par leur section cadastrale, via le
quartier où tombent la plupart des ventes géolocalisées de cette section.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_geo import simplify_ring  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"
VENTES = [DATA / "immobilier.parquet", DATA / "immobilier_2026s1.parquet"]
SORTIE_GEO = DATA / "quartiers_loiret.geojson"
SORTIE_VENTES = DATA / "ventes_quartiers.parquet"


def _premier(v):
    return v[0] if isinstance(v, list) else v


def polygones(geom) -> list[list[list[tuple]]]:
    """Liste de polygones, chacun = [anneau extérieur, trous...]."""
    coords = geom["coordinates"]
    polys = coords if geom["type"] == "MultiPolygon" else [coords]
    return [[[tuple(p) for p in ring] for ring in poly] for poly in polys]


def _dans_anneau(x, y, ring) -> bool:
    dedans = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            dedans = not dedans
        j = i
    return dedans


def contient(polys, bbox, x, y) -> bool:
    if not (bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]):
        return False
    for poly in polys:
        if _dans_anneau(x, y, poly[0]) and not any(_dans_anneau(x, y, h) for h in poly[1:]):
            return True
    return False


def charger_iris(chemin: Path) -> list[dict]:
    geo = json.loads(chemin.read_text(encoding="utf-8"))
    iris = []
    for f in geo["features"]:
        p = f["properties"]
        irisee = p["iris_type"] != "commune"
        polys = polygones(f["geometry"])
        xs = [x for poly in polys for x, _ in poly[0]]
        ys = [y for poly in polys for _, y in poly[0]]
        iris.append(
            {
                "code_iris": _premier(p["iris_code"]),
                "nom_quartier": _premier(p["iris_name"]) if irisee else _premier(p["com_name"]),
                "code_commune": _premier(p["com_code"]),
                "irisee": irisee,
                "polys": polys,
                "bbox": (min(xs), min(ys), max(xs), max(ys)),
                "geometry": f["geometry"],
            }
        )
    return iris


def rattacher(ventes: pd.DataFrame, iris: list[dict]) -> pd.Series:
    par_commune = defaultdict(list)
    for z in iris:
        par_commune[z["code_commune"]].append(z)

    code = {}
    for v in ventes.itertuples():
        zones = par_commune.get(v.code_commune, [])
        if len(zones) == 1:
            code[v.id_mutation] = zones[0]["code_iris"]
        elif zones and pd.notna(v.longitude):
            for z in zones:
                if contient(z["polys"], z["bbox"], v.longitude, v.latitude):
                    code[v.id_mutation] = z["code_iris"]
                    break

    # Ventes sans position : quartier majoritaire de leur section cadastrale
    votes = defaultdict(Counter)
    for v in ventes.itertuples():
        if v.id_mutation in code:
            votes[(v.code_commune, v.section)][code[v.id_mutation]] += 1
    for v in ventes.itertuples():
        if v.id_mutation not in code and votes[(v.code_commune, v.section)]:
            code[v.id_mutation] = votes[(v.code_commune, v.section)].most_common(1)[0][0]
    return ventes["id_mutation"].map(code)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    iris = charger_iris(Path(sys.argv[1]))
    colonnes = ["id_mutation", "code_commune", "section", "longitude", "latitude"]
    ventes = pd.concat([pd.read_parquet(f, columns=colonnes) for f in VENTES], ignore_index=True)
    assert ventes["id_mutation"].is_unique, "identifiants de vente en double"

    ventes["code_iris"] = rattacher(ventes, iris)
    ventes[["id_mutation", "code_iris"]].to_parquet(SORTIE_VENTES, index=False)

    features = []
    for z in iris:
        g = z["geometry"]
        if g["type"] == "Polygon":
            coords = [simplify_ring(r) for r in g["coordinates"]]
        else:
            coords = [[simplify_ring(r) for r in poly] for poly in g["coordinates"]]
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "code_iris": z["code_iris"],
                    "nom_quartier": z["nom_quartier"],
                    "code_commune": z["code_commune"],
                    "irisee": z["irisee"],
                },
                "geometry": {"type": g["type"], "coordinates": coords},
            }
        )
    SORTIE_GEO.write_text(
        json.dumps(
            {"type": "FeatureCollection", "features": features},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )

    total = len(ventes)
    sans = ventes["code_iris"].isna().sum()
    print(
        f"{len(features)} quartiers -> {SORTIE_GEO.name} ({SORTIE_GEO.stat().st_size / 1e3:.0f} ko)"
    )
    print(f"{total - sans} / {total} ventes rattachées à un quartier ({sans} sans quartier)")


if __name__ == "__main__":
    main()
