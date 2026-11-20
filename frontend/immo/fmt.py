"""Formatage des nombres à la française."""

import math

NBSP = " "  # espace fine insécable


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def entier(x) -> str:
    return f"{x:,.0f}".replace(",", NBSP) if _ok(x) else "–"


def euros(x) -> str:
    return f"{entier(x)}{NBSP}€" if _ok(x) else "–"


def euros_k(x) -> str:
    if not _ok(x):
        return "–"
    if abs(x) >= 1_000_000:
        return f"{x / 1e6:.2f}".replace(".", ",") + f"{NBSP}M€"
    return f"{x / 1000:.0f}{NBSP}k€"


def eur_m2(x) -> str:
    return f"{entier(x)}{NBSP}€/m²" if _ok(x) else "–"


def m2(x) -> str:
    return f"{entier(x)}{NBSP}m²" if _ok(x) else "–"


def pct(x, signe: bool = True, decimales: int = 1) -> str:
    if not _ok(x):
        return "–"
    s = f"{x * 100:+.{decimales}f}" if signe else f"{x * 100:.{decimales}f}"
    return s.replace(".", ",").replace("-", "−") + f"{NBSP}%"


def ventes(n) -> str:
    return f"{entier(n)} vente{'s' if n and n > 1 else ''}"
