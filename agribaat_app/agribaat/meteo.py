"""Météo en temps réel (Open-Meteo) et conseils agricoles dans les trois langues.

- Source : API Open-Meteo (gratuite, sans clé), prévisions à 7 jours pour les 14 chefs-lieux
  de région, en un seul appel. Seules des coordonnées de villes sont envoyées.
- Hors ligne : la dernière réponse est gardée sur disque (outputs/meteo_cache.json) et
  réutilisée, avec sa date, si l'API ne répond pas.
- Conseils : règles simples et transparentes appliquées aux prévisions (pluie forte,
  pluie, chaleur sèche, temps sec, vent fort, récoltes à protéger). Aucun texte généré.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import config

API = "https://api.open-meteo.com/v1/forecast"
CACHE = config.OUTPUTS_DIR / "meteo_cache.json"
MAX_AGE_S = 3600  # prévisions rafraîchies au plus une fois par heure

# Chefs-lieux de région : (latitude, longitude).
CITIES: dict[str, tuple[float, float]] = {
    "Dakar": (14.69, -17.44), "Thies": (14.79, -16.93), "Diourbel": (14.65, -16.23),
    "Fatick": (14.34, -16.41), "Kaolack": (14.15, -16.07), "Kaffrine": (14.11, -15.55),
    "Louga": (15.62, -16.22), "Saint-Louis": (16.03, -16.49), "Matam": (15.66, -13.26),
    "Tambacounda": (13.77, -13.67), "Kedougou": (12.56, -12.18), "Kolda": (12.89, -14.94),
    "Sedhiou": (12.71, -15.56), "Ziguinchor": (12.58, -16.27),
}
DAILY = ("precipitation_sum", "precipitation_probability_max", "temperature_2m_max",
         "temperature_2m_min", "wind_speed_10m_max", "et0_fao_evapotranspiration")
CURRENT = ("temperature_2m", "relative_humidity_2m", "wind_speed_10m", "precipitation")


@dataclass
class Day:
    day: date
    rain: float
    prob: float
    tmax: float
    tmin: float
    wind: float
    et0: float


@dataclass
class Forecast:
    region: str
    fetched: datetime
    live: bool  # False : dernières prévisions gardées en cache (API injoignable)
    temp: float
    humidity: float
    wind: float
    days: list[Day] = field(default_factory=list)

    @property
    def rain3(self) -> float:
        return sum(d.rain for d in self.days[:3])

    @property
    def rain7(self) -> float:
        return sum(d.rain for d in self.days)

    @property
    def tmax7(self) -> float:
        return max(d.tmax for d in self.days)

    @property
    def wind3(self) -> float:
        return max(d.wind for d in self.days[:3])

    @property
    def et0(self) -> float:
        return sum(d.et0 for d in self.days) / len(self.days)


# ------------------------------------------------------------------ récupération
def _fetch_all(timeout: float = 15) -> dict:
    import httpx

    names = list(CITIES)
    params = {
        "latitude": ",".join(str(CITIES[n][0]) for n in names),
        "longitude": ",".join(str(CITIES[n][1]) for n in names),
        "daily": ",".join(DAILY), "current": ",".join(CURRENT),
        "timezone": "Africa/Dakar", "forecast_days": 7,
    }
    data = httpx.get(API, params=params, timeout=timeout).raise_for_status().json()
    data = data if isinstance(data, list) else [data]
    return {"fetched": time.time(), "regions": dict(zip(names, data))}


def _load(force: bool = False) -> tuple[dict | None, bool]:
    """(données, en_direct). Rafraîchit si le cache a plus d'une heure."""
    cached = None
    if CACHE.exists():
        try:
            cached = json.loads(CACHE.read_text(encoding="utf-8"))
        except ValueError:
            cached = None
    if cached and not force and time.time() - cached["fetched"] < MAX_AGE_S:
        return cached, True
    try:
        fresh = _fetch_all()
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(fresh), encoding="utf-8")
        return fresh, True
    except Exception:  # noqa: BLE001 — pas de réseau : dernières prévisions connues
        return cached, False


def _parse(region: str, raw: dict, fetched: float, live: bool) -> Forecast:
    cur, d = raw.get("current", {}), raw["daily"]
    days = [Day(date.fromisoformat(t), d["precipitation_sum"][i] or 0.0,
                d["precipitation_probability_max"][i] or 0.0, d["temperature_2m_max"][i],
                d["temperature_2m_min"][i], d["wind_speed_10m_max"][i] or 0.0,
                d["et0_fao_evapotranspiration"][i] or 0.0)
            for i, t in enumerate(d["time"])]
    # Cache ancien : on ne garde que les jours à venir.
    today = date.today()
    days = [x for x in days if x.day >= today] or days
    return Forecast(region, datetime.fromtimestamp(fetched), live,
                    cur.get("temperature_2m", days[0].tmax), cur.get("relative_humidity_2m", 0),
                    cur.get("wind_speed_10m", 0), days)


def forecast(region: str, force: bool = False) -> Forecast | None:
    data, live = _load(force)
    if not data or region not in data["regions"]:
        return None
    return _parse(region, data["regions"][region], data["fetched"], live)


def all_forecasts(force: bool = False) -> dict[str, Forecast]:
    data, live = _load(force)
    if not data:
        return {}
    return {r: _parse(r, raw, data["fetched"], live) for r, raw in data["regions"].items()}


# ------------------------------------------------------------------ conseils
@dataclass
class Advice:
    key: str  # gabarit dans les modules de langue (meteo_<key>)
    icon: str
    title: str
    text: str  # français
    level: str  # alerte | info | ok


def advice(fc: Forecast) -> list[Advice]:
    """Règles appliquées aux prévisions ; au plus trois conseils, du plus urgent au moins."""
    out: list[Advice] = []
    r3, r7, tmax, wind, et0 = fc.rain3, fc.rain7, fc.tmax7, fc.wind3, fc.et0
    if r3 >= 20:
        out.append(Advice("pluie_forte", "⛈️", "Forte pluie attendue",
                          f"Environ {r3:.0f} mm en 3 jours : reportez les traitements et "
                          "l'épandage d'engrais, dégagez les rigoles d'écoulement.", "alerte"))
    elif r3 >= 5:
        out.append(Advice("pluie", "🌧️", "Pluie attendue",
                          f"Environ {r3:.0f} mm en 3 jours : ne traitez pas juste avant la "
                          "pluie ; pour semer, attendez un sol bien humide.", "info"))
    if r3 >= 5 and fc.days[0].day.month in (9, 10, 11):
        out.append(Advice("recolte", "🌾", "Récoltes à protéger",
                          "En période de récolte : couvrez les épis et les gousses qui "
                          "sèchent, et mettez les sacs à l'abri.", "alerte"))
    if r7 < 1 and tmax >= 35:
        out.append(Advice("chaleur", "🔥", "Temps sec et très chaud",
                          f"Jusqu'à {tmax:.0f} °C, sans pluie : arrosez tôt le matin ou le "
                          f"soir et paillez le sol ; les cultures perdent environ {et0:.0f} mm "
                          "d'eau par jour.", "alerte"))
    elif r7 < 1:
        out.append(Advice("sec", "☀️", "Pas de pluie cette semaine",
                          f"Arrosez régulièrement les cultures irriguées : environ {et0:.0f} mm "
                          "d'eau perdus par jour.", "info"))
    if wind >= 30:
        out.append(Advice("vent", "💨", "Vent fort",
                          f"Jusqu'à {wind:.0f} km/h : ne pulvérisez pas de produits.", "alerte"))
    if not out:
        out.append(Advice("normal", "✅", "Conditions favorables",
                          "Pas de risque météo particulier dans les prochains jours.", "ok"))
    return out[:3]


# ------------------------------------------------------------------ langues locales
def local_text(fc: Forecast, advices: list[Advice], module):
    """Résumé + conseils dans la langue du module (wolof.py, pulaar.py, sereer.py).

    Renvoie un WolofText (texte écran, texte lu) ; les nombres sont dits en toutes
    lettres comme dans le reste de l'application. Un conseil sans phrase dans la langue
    (sereer, pour l'instant) n'est pas lu.
    """
    from . import wolof as wo
    from .carte import label

    with wo.using(module):
        key = "meteo_resume" if fc.rain7 >= 1 else "meteo_resume_sec"  # pas de « 0 mm »
        out = wo.render(key, lieu=label(fc.region), mm=wo.Qty(fc.rain7, "mm"),
                        tmax=wo.Qty(fc.tmax7, "c"))
        for a in advices:
            key = f"meteo_{a.key}"
            if key in module.T:
                out = out + wo.WolofText(" ", " ") + wo.render(
                    key, mm=wo.Qty(fc.rain3, "mm"), tmax=wo.Qty(fc.tmax7, "c"))
    return out


def has_local_advice(module) -> bool:
    return "meteo_pluie" in module.T


def summary_fr(fc: Forecast) -> str:
    """Résumé français pour l'Assistant (prévisions des 7 prochains jours)."""
    from .carte import label

    rain = (f"environ {fc.rain7:.0f} mm de pluie sur 7 jours" if fc.rain7 >= 1
            else "pas de pluie prévue sur 7 jours")
    return (f"Prévisions pour {label(fc.region)} : {rain}, jusqu'à {fc.tmax7:.0f} °C. "
            + " ".join(a.text for a in advice(fc)))
