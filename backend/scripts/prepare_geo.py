"""Télécharge et simplifie les contours des communes du Loiret.

Source : geo.api.gouv.fr (IGN Admin Express, Licence Ouverte 2.0).
Usage : uv run python scripts/prepare_geo.py
"""

import json
import math
import urllib.request
from pathlib import Path

URL = (
    "https://geo.api.gouv.fr/departements/45/communes"
    "?format=geojson&geometry=contour&fields=code,nom,codeEpci"
)
OUT = Path(__file__).resolve().parents[1] / "data" / "communes_loiret.geojson"
TOLERANCE = 0.0004  # degrés (~30-40 m), invisible à l'échelle du département


def _perp_dist(p, a, b):
    if a == b:
        return math.dist(p, a)
    (x, y), (x1, y1), (x2, y2) = p, a, b
    num = abs((y2 - y1) * x - (x2 - x1) * y + x2 * y1 - y2 * x1)
    return num / math.dist(a, b)


def simplify(points, tol):
    """Douglas-Peucker itératif."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        dmax, idx = 0.0, start
        for i in range(start + 1, end):
            d = _perp_dist(points[i], points[start], points[end])
            if d > dmax:
                dmax, idx = d, i
        if dmax > tol:
            keep[idx] = True
            stack += [(start, idx), (idx, end)]
    return [p for p, k in zip(points, keep) if k]


def simplify_ring(ring):
    out = simplify([tuple(p) for p in ring], TOLERANCE)
    if len(out) < 4:  # un anneau valide garde au moins 4 points
        out = [tuple(p) for p in ring]
    return [[round(x, 5), round(y, 5)] for x, y in out]


def main():
    with urllib.request.urlopen(URL, timeout=60) as resp:
        geo = json.load(resp)
    for feat in geo["features"]:
        geom = feat["geometry"]
        if geom["type"] == "Polygon":
            geom["coordinates"] = [simplify_ring(r) for r in geom["coordinates"]]
        else:
            geom["coordinates"] = [[simplify_ring(r) for r in poly] for poly in geom["coordinates"]]
    OUT.write_text(json.dumps(geo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(geo['features'])} communes -> {OUT} ({OUT.stat().st_size / 1e3:.0f} ko)")


if __name__ == "__main__":
    main()
