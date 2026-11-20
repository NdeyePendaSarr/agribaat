"""Carte du Sénégal : climat et cultures à fort rendement, région par région.

- Contours des 14 régions : geoBoundaries (Gouvernement du Sénégal, OCHA ROWCA),
  licence CC BY 3.0 IGO, fichier assets/senegal_regions.geojson (hors ligne).
- Rendements : DAPSA, moyennes 2017–2022 par région et par culture, comparées à la
  moyenne nationale DAPSA des mêmes années.
- Zones climatiques : repère général (nord sahélien, centre soudano-sahélien, sud
  soudanien), avec un ordre de grandeur des pluies annuelles.
- Variétés adaptées : catalogue ouest-africain (CEDEAO), plage de pluviométrie de chaque
  variété comparée à celle de la zone.

La carte est un SVG dessiné côté serveur : aucune bibliothèque ni connexion requise.
"""

from __future__ import annotations

import html
import json
import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .lexicon import PRODUCT_BY_KEY, normalize

GEOJSON = Path(__file__).resolve().parent.parent / "assets" / "senegal_regions.geojson"

ICONS = {"mil": "🌾", "sorgho": "🌾", "mais": "🌽", "riz": "🍚", "arachide": "🥜",
         "niebe": "🫘", "manioc": "🥔", "fonio": "🌾"}
CROP_COLORS = {"mil": "#ca8a04", "sorgho": "#b45309", "mais": "#eab308", "riz": "#0e7490",
               "arachide": "#9a3412", "niebe": "#65a30d", "manioc": "#7c3aed",
               "fonio": "#a16207"}

# Repère général : zones climatiques du Sénégal et ordre de grandeur des pluies annuelles.
ZONES = {
    "sahelienne": ("Sahélienne (nord)", "#f4c66a", (0, 400), "moins de 400 mm de pluie par an"),
    "soudano": ("Soudano-sahélienne (centre)", "#a3c46a", (400, 800),
                "400 à 800 mm de pluie par an"),
    "soudanienne": ("Soudanienne (sud)", "#3f8f4f", (800, 1500),
                    "plus de 800 mm de pluie par an"),
}
REGION_ZONE = {
    "Saint-Louis": "sahelienne", "Louga": "sahelienne", "Matam": "sahelienne",
    "Dakar": "soudano", "Thies": "soudano", "Diourbel": "soudano", "Fatick": "soudano",
    "Kaolack": "soudano", "Kaffrine": "soudano", "Tambacounda": "soudano",
    "Kolda": "soudanienne", "Sedhiou": "soudanienne", "Ziguinchor": "soudanienne",
    "Kedougou": "soudanienne",
}
LABELS = {"Saint-Louis": "Saint-Louis", "Thies": "Thiès", "Sedhiou": "Sédhiou",
          "Kedougou": "Kédougou"}
MIN_AREA_HA = 1000  # culture marginale dans la région : ignorée (rendement peu fiable)


def label(region: str) -> str:
    return LABELS.get(region, region)


@dataclass
class CropScore:
    product: str
    yield_kg_ha: float
    national: float
    area_ha: float

    @property
    def ratio(self) -> float:
        return self.yield_kg_ha / self.national if self.national else 0.0


class SenegalMap:
    def __init__(self, regional: pd.DataFrame, varieties: pd.DataFrame | None = None,
                 rainfall: pd.DataFrame | None = None, geojson: Path = GEOJSON) -> None:
        self.varieties = varieties if varieties is not None else pd.DataFrame()
        self.rainfall = rainfall if rainfall is not None else pd.DataFrame()
        self.scores = self._scores(regional)
        self.shapes = self._load_shapes(geojson) if geojson.exists() else {}

    # ------------------------------------------------------------------ données
    @staticmethod
    def _scores(regional: pd.DataFrame) -> dict[str, list[CropScore]]:
        mean = regional.groupby(["region", "product", "indicator"])["value"].mean()
        out: dict[str, list[CropScore]] = {}
        for region in REGION_ZONE:
            scores = []
            for product in PRODUCT_BY_KEY:
                try:
                    y = mean[(region, product, "rendement")]
                    area = mean[(region, product, "superficie")]
                    nat = mean[("Senegal", product, "rendement")]
                except KeyError:
                    continue
                if pd.notna(y) and y > 0 and area >= MIN_AREA_HA and nat > 0:
                    scores.append(CropScore(product, float(y), float(nat), float(area)))
            out[region] = sorted(scores, key=lambda s: s.ratio, reverse=True)
        return out

    def best_crops(self, region: str, n: int = 3) -> list[CropScore]:
        """Cultures où la région dépasse le plus la moyenne nationale."""
        return [s for s in self.scores.get(region, []) if s.ratio >= 1.0][:n] or \
            self.scores.get(region, [])[:1]

    def yield_of(self, region: str, product: str) -> CropScore | None:
        return next((s for s in self.scores.get(region, []) if s.product == product), None)

    def varieties_for(self, region: str, product: str) -> list[str]:
        """Variétés du catalogue dont la plage de pluie recoupe celle de la zone."""
        if self.varieties.empty:
            return []
        lo, hi = ZONES[REGION_ZONE[region]][2]
        v = self.varieties[(self.varieties["culture"] == product)
                           & self.varieties["pluie_min"].notna()]
        ok = v[(v["pluie_min"] < hi) & (v["pluie_max"] > lo)]
        return ok["variete"].tolist()

    def rain_summary(self, region: str) -> tuple[float, int] | None:
        """Pluie moyenne par relevé décadaire ANACIM dans la région (mm, nombre)."""
        df = self.rainfall
        if df.empty or "region" not in df:
            return None
        sel = df[df["region"] == region]["pluie_mm"].dropna()
        return (float(sel.mean()), int(sel.size)) if sel.size >= 5 else None

    # ------------------------------------------------------------------ géométrie
    @staticmethod
    def _region_name(name: str) -> str:
        key = normalize(name).replace("-", " ")
        for region in REGION_ZONE:
            if normalize(region).replace("-", " ") == key:
                return region
        return name

    def _load_shapes(self, path: Path) -> dict[str, list[list[tuple[float, float]]]]:
        data = json.loads(path.read_text(encoding="utf-8"))
        shapes: dict[str, list[list[tuple[float, float]]]] = {}
        for feat in data["features"]:
            geom = feat["geometry"]
            polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
            rings = [[(x, y) for x, y in poly[0]] for poly in polys]  # anneau extérieur
            shapes[self._region_name(feat["properties"]["shapeName"])] = rings
        return shapes

    # ------------------------------------------------------------------ dessin
    W, H = 760, 520

    def _projector(self):
        pts = [p for rings in self.shapes.values() for ring in rings for p in ring]
        lon0, lon1 = min(p[0] for p in pts), max(p[0] for p in pts)
        lat0, lat1 = min(p[1] for p in pts), max(p[1] for p in pts)
        kx = math.cos(math.radians((lat0 + lat1) / 2))
        scale = min((self.W - 20) / ((lon1 - lon0) * kx), (self.H - 20) / (lat1 - lat0))
        ox = (self.W - (lon1 - lon0) * kx * scale) / 2
        oy = (self.H - (lat1 - lat0) * scale) / 2
        return lambda lon, lat: (ox + (lon - lon0) * kx * scale, oy + (lat1 - lat) * scale)

    def _style(self, region: str, mode: str) -> tuple[str, str]:
        """(couleur, texte de l'infobulle) selon le mode d'affichage."""
        zone = REGION_ZONE[region]
        if mode == "zones":
            name, color, _, rain = ZONES[zone]
            return color, f"{label(region)} : zone {name.lower()}, {rain}"
        if mode == "best":
            best = self.best_crops(region, 1)
            if not best:
                return "#d6d3d1", f"{label(region)} : pas de donnée"
            s = best[0]
            return CROP_COLORS[s.product], (
                f"{label(region)} : meilleur rendement relatif pour le "
                f"{PRODUCT_BY_KEY[s.product].label} ({s.yield_kg_ha:,.0f} kg/ha, "
                f"{(s.ratio - 1) * 100:+.0f} % / moyenne nationale)").replace(",", " ")
        s = self.yield_of(region, mode)  # mode = produit
        if s is None:
            return "#e7e5e4", f"{label(region)} : peu ou pas de {PRODUCT_BY_KEY[mode].label}"
        t = max(0.0, min(1.0, (s.ratio - 0.4) / 1.2))  # 0,4× -> clair ; 1,6× -> foncé
        r, g, b = (int(a + (c - a) * t) for a, c in zip((236, 252, 203), (20, 83, 45)))
        return f"rgb({r},{g},{b})", (
            f"{label(region)} : {PRODUCT_BY_KEY[mode].label} {s.yield_kg_ha:,.0f} kg/ha "
            f"({(s.ratio - 1) * 100:+.0f} % / moyenne nationale)").replace(",", " ")

    def svg(self, mode: str = "best", selected: str | None = None) -> str:
        if not self.shapes:
            return "<p>Contours des régions introuvables (assets/senegal_regions.geojson).</p>"
        proj = self._projector()
        paths, labels = [], []
        for region, rings in self.shapes.items():
            color, tip = self._style(region, mode)
            d = " ".join("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in (proj(*p) for p in ring))
                         + "Z" for ring in rings)
            stroke = ("#111827", 3) if region == selected else ("#ffffff", 1.4)
            paths.append(f'<path d="{d}" fill="{color}" stroke="{stroke[0]}" '
                         f'stroke-width="{stroke[1]}" class="reg"><title>{html.escape(tip)}'
                         f"</title></path>")
            ring = max(rings, key=len)
            xs, ys = zip(*(proj(*p) for p in ring))
            cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            if region == "Dakar":
                cx -= 2
                cy -= 14
            icon = ""
            if mode == "best" and self.best_crops(region, 1):
                icon = ICONS[self.best_crops(region, 1)[0].product] + " "
            labels.append(f'<text x="{cx:.0f}" y="{cy:.0f}" class="lbl">{icon}'
                          f"{html.escape(label(region))}</text>")
        return (f'<svg viewBox="0 0 {self.W} {self.H}" class="sn-map" role="img" '
                f'aria-label="Carte des régions du Sénégal">{"".join(paths)}'
                f'{"".join(labels)}</svg>')

    def legend(self, mode: str) -> str:
        if mode == "zones":
            items = [(c, f"{n} · {r}") for n, c, _, r in ZONES.values()]
        elif mode == "best":
            shown = {self.best_crops(r, 1)[0].product for r in REGION_ZONE
                     if self.best_crops(r, 1)}
            items = [(CROP_COLORS[p], f"{ICONS[p]} {PRODUCT_BY_KEY[p].label}")
                     for p in sorted(shown)]
        else:
            items = [("rgb(236,252,203)", "rendement inférieur à la moyenne nationale"),
                     ("rgb(20,83,45)", "rendement supérieur à la moyenne nationale"),
                     ("#e7e5e4", "culture marginale ou absente")]
        return '<div class="sn-legend">' + "".join(
            f'<span><i style="background:{c}"></i>{html.escape(t)}</span>' for c, t in items) \
            + "</div>"

    def region_card(self, region: str) -> str:
        """Fiche d'une région : climat, cultures à fort rendement, variétés adaptées."""
        esc = html.escape
        zone_name, color, _, rain = ZONES[REGION_ZONE[region]]
        rows = []
        crops = self.best_crops(region, 3)
        above = bool(crops) and crops[0].ratio >= 1.0
        subtitle = ("Cultures à fort rendement dans la région" if above else
                    "Aucune culture au-dessus de la moyenne nationale ; la plus proche")
        for s in crops:
            varieties = self.varieties_for(region, s.product)
            var = (f'<div class="sn-var">Variétés adaptées à cette pluviométrie : '
                   f'{esc(", ".join(varieties[:4]))}</div>') if varieties else ""
            rows.append(
                f'<li><b>{ICONS[s.product]} {esc(PRODUCT_BY_KEY[s.product].label.capitalize())}'
                f'</b> · {s.yield_kg_ha:,.0f} kg/ha '.replace(",", " ")
                + f'<span class="pill {"up" if s.ratio >= 1 else "down"}">'
                  f'{(s.ratio - 1) * 100:+.0f} % / moyenne nationale</span>'
                + f"{var}</li>")
        observed = self.rain_summary(region)
        obs = (f'<div class="sn-obs">🌧️ Pluies relevées par l\'ANACIM (2023–2026) : en moyenne '
               f'{observed[0]:.0f} mm par décade ({observed[1]} relevés).</div>') if observed else ""
        return (f'<div class="sn-card"><h3>📍 {esc(label(region))}</h3>'
                f'<div class="sn-zone" style="border-color:{color}">Climat : zone '
                f'{esc(zone_name.lower())} · {esc(rain)}</div>{obs}'
                f'<div class="sn-sub">{subtitle}</div>'
                f'<ul>{"".join(rows)}</ul>'
                f'<div class="src-note">Rendements : DAPSA, moyennes 2017–2022, comparées à la '
                f'moyenne nationale. Zones climatiques : repère général. Variétés : catalogue '
                f'ouest-africain (CEDEAO). Contours : geoBoundaries (Gouvernement du Sénégal, '
                f'OCHA), CC BY 3.0 IGO.</div></div>')
