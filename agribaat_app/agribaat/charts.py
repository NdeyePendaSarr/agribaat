"""Graphiques AgriBaat en SVG (dessinés côté serveur, aux couleurs de l'application).

Courbe avec aire dégradée, grille légère, axes lisibles, annotation du maximum et de la
dernière valeur, valeur exacte au survol de chaque point. Aucune bibliothèque ni
connexion requise.
"""

from __future__ import annotations

import html
import math
from datetime import date


def _nice_step(span: float, target: int = 5) -> float:
    raw = span / max(target, 1)
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def _fmt(v: float) -> str:
    """1 234 567 -> « 1,2 M » ; 12 345 -> « 12 345 »."""
    if abs(v) >= 1_000_000:
        return f"{v / 1_000_000:.1f} M".replace(".", ",").replace(",0 M", " M")
    return f"{v:,.0f}".replace(",", " ")


MONTHS = ("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.",
          "nov.", "déc.")


def _label(x: date, yearly: bool) -> str:
    return str(x.year) if yearly else f"{MONTHS[x.month - 1]} {x.year}"


def area_chart(points: list[tuple[date, float]], *, title: str, unit: str, source: str,
               yearly: bool = False) -> str:
    """Carte HTML contenant la courbe des valeurs (dates croissantes)."""
    esc = html.escape
    if len(points) < 2:
        return (f'<div class="chart-card"><div class="cc-head"><div><h4>{esc(title)}</h4>'
                f'<span>{esc(source)}</span></div></div><div class="cc-empty">Pas assez de '
                "données pour tracer une courbe.</div></div>")
    W, H, L, R, T, B = 760, 320, 66, 24, 30, 38
    xs = [p[0].toordinal() for p in points]
    ys = [p[1] for p in points]
    x0, x1 = min(xs), max(xs)
    lo, hi = min(ys), max(ys)
    step = _nice_step(hi - lo if hi > lo else hi or 1)
    y0 = math.floor(lo / step) * step
    y1 = math.ceil(hi / step) * step
    if y1 == y0:
        y1 = y0 + step
    px = lambda x: L + (x - x0) / (x1 - x0) * (W - L - R)  # noqa: E731
    py = lambda y: T + (y1 - y) / (y1 - y0) * (H - T - B)  # noqa: E731

    grid, ylab = [], []
    v = y0
    while v <= y1 + 1e-9:
        y = py(v)
        grid.append(f'<line x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}" class="g"/>')
        ylab.append(f'<text x="{L - 8}" y="{y + 4:.1f}" class="ya">{_fmt(v)}</text>')
        v += step
    years = sorted({p[0].year for p in points})
    every = max(1, math.ceil(len(years) / 9))
    xlab = []
    for yr in years[::every]:
        xo = date(yr, 1, 1).toordinal()
        if x0 <= xo <= x1:
            xlab.append(f'<text x="{px(xo):.1f}" y="{H - 10}" class="xa">{yr}</text>')

    line = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in zip(xs, ys))
    area = (f"M{px(xs[0]):.1f},{py(y0):.1f} L" + " L".join(
        f"{px(x):.1f},{py(y):.1f}" for x, y in zip(xs, ys)) + f" L{px(xs[-1]):.1f},{py(y0):.1f} Z")
    imax = ys.index(hi)
    mx, my = px(xs[imax]), py(hi)
    lx, ly = px(xs[-1]), py(ys[-1])
    anchor = "end" if mx > W - 160 else "start"
    dx = -10 if anchor == "end" else 10
    hits = "".join(
        f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="6" class="hit"><title>'
        f"{esc(_label(p[0], yearly))} : {_fmt(y)} {esc(unit)}</title></circle>"
        for p, x, y in zip(points, xs, ys))
    last_lbl = f"{_fmt(ys[-1])} {unit}"
    svg = (f'<svg viewBox="0 0 {W} {H}" class="ag-chart" role="img" aria-label="{esc(title)}">'
           '<defs><linearGradient id="agArea" x1="0" y1="0" x2="0" y2="1">'
           '<stop offset="0" stop-color="#1e7b4f" stop-opacity=".32"/>'
           '<stop offset="1" stop-color="#1e7b4f" stop-opacity="0"/></linearGradient></defs>'
           f'{"".join(grid)}{"".join(ylab)}{"".join(xlab)}'
           f'<path d="{area}" fill="url(#agArea)"/>'
           f'<polyline points="{line}" class="ln"/>'
           f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="5.5" class="mx"/>'
           f'<text x="{mx + dx:.1f}" y="{max(my - 10, 14):.1f}" class="ann" text-anchor="{anchor}">'
           f"Max {_fmt(hi)} · {esc(_label(points[imax][0], yearly))}</text>"
           f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="5.5" class="last"/>'
           f"{hits}</svg>")
    return (f'<div class="chart-card"><div class="cc-head"><div><h4>{esc(title)}</h4>'
            f'<span>{esc(source)}</span></div><div class="cc-last"><b>{esc(last_lbl)}</b>'
            f'<small>{esc(_label(points[-1][0], yearly))}</small></div></div>{svg}</div>')
