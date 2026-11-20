"""Calendrier de semis : démarrage réel de la saison des pluies, faux départs, variétés.

Règle agronomique classique au Sahel (démarrage « agronomique » de la saison) : le premier
jour, après une date de début plausible, où il tombe au moins 20 mm en 3 jours, SANS
période sèche de 7 jours ou plus (moins de 1 mm par jour) dans les 30 jours qui suivent.
Une pluie suivie d'une telle période sèche est un « faux départ » : semer à ce moment-là
expose à perdre les levées.

Données : Open-Meteo. « Maintenant » : 31 derniers jours + 16 jours de prévisions.
« Hivernage AAAA » : pluies relevées de mai à octobre (archive Open-Meteo), pour revoir une
saison passée région par région. Les variétés proposées sont celles du catalogue CEDEAO
dont le cycle tient avant la fin habituelle des pluies dans la zone et dont la plage de
pluviométrie correspond à la zone (repères généraux, affichés comme tels).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import date, timedelta

import config

from .carte import REGION_ZONE, label
from .meteo import CITIES

OUT = config.APP_DIR / "outputs"
FORECAST_API = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_API = "https://archive-api.open-meteo.com/v1/archive"
ONSET_MM, ONSET_DAYS, DRY_SPELL, CHECK_DAYS = 20.0, 3, 7, 30

# Repères généraux par zone : début de recherche, fin habituelle des pluies, fenêtre
# habituelle de démarrage (texte).
ZONE_SEASON = {
    "sahelienne": ((6, 15), (9, 20), "début à mi-juillet"),
    "soudano": ((6, 1), (10, 10), "fin juin à mi-juillet"),
    "soudanienne": ((5, 15), (10, 31), "fin mai à mi-juin"),
}
CROPS = ("mil", "sorgho", "arachide", "niebe")


@dataclass
class Onset:
    day: date
    rain3: float
    observed: bool  # True : relevé ; False : prévu (prévisions)
    confirmed: bool  # False : les 30 jours suivants ne sont pas encore connus


@dataclass
class Calendar:
    region: str
    mode: str  # « now » ou une année (« 2025 »)
    days: list[tuple[date, float]]
    onset: Onset | None = None
    false_starts: list[Onset] = field(default_factory=list)
    season_end: date | None = None
    status: str = ""
    message: str = ""
    level: str = "info"  # ok | info | alerte
    varieties: dict[str, list[str]] = field(default_factory=dict)
    late: str = ""  # semis tardif : aucune variété du catalogue n'a un cycle assez court

    @property
    def total(self) -> float:
        return sum(mm for _, mm in self.days)


# ------------------------------------------------------------------ données
def _get_json(url: str, params: dict, timeout: float = 20):
    import httpx

    return httpx.get(url, params=params, timeout=timeout).raise_for_status().json()


def _coords() -> dict:
    names = list(CITIES)
    return names, {"latitude": ",".join(str(CITIES[n][0]) for n in names),
                   "longitude": ",".join(str(CITIES[n][1]) for n in names),
                   "daily": "precipitation_sum", "timezone": "Africa/Dakar"}


def _series(raw: dict) -> list[tuple[date, float]]:
    d = raw["daily"]
    return [(date.fromisoformat(t), float(v or 0.0)) for t, v in zip(d["time"],
                                                                        d["precipitation_sum"])]


def _cached(path, fetch, max_age: float | None):
    """Lit le cache s'il est assez récent ; sinon interroge l'API (et garde la réponse)."""
    cached = None
    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            cached = None
    if cached and (max_age is None or time.time() - cached["fetched"] < max_age):
        return cached
    try:
        fresh = {"fetched": time.time(), "regions": fetch()}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(fresh), encoding="utf-8")
        return fresh
    except Exception:  # noqa: BLE001 — hors ligne : dernière réponse connue
        return cached


def recent_rain() -> dict[str, list[tuple[date, float]]]:
    """31 derniers jours + 16 jours de prévisions, par région."""
    def fetch():
        names, params = _coords()
        data = _get_json(FORECAST_API, {**params, "past_days": 31, "forecast_days": 16})
        data = data if isinstance(data, list) else [data]
        return dict(zip(names, data))
    got = _cached(OUT / "pluie_recente.json", fetch, 3600)
    return {r: _series(raw) for r, raw in (got or {}).get("regions", {}).items()}


def season_rain(year: int) -> dict[str, list[tuple[date, float]]]:
    """Pluies relevées de mai à octobre d'une année passée (archive, gardée sur disque)."""
    def fetch():
        names, params = _coords()
        data = _get_json(ARCHIVE_API, {**params, "start_date": f"{year}-05-01",
                                       "end_date": f"{year}-10-31"}, timeout=40)
        data = data if isinstance(data, list) else [data]
        return dict(zip(names, data))
    got = _cached(OUT / f"saison_{year}.json", fetch, None)
    return {r: _series(raw) for r, raw in (got or {}).get("regions", {}).items()}


# ------------------------------------------------------------------ règle de démarrage
def detect(days: list[tuple[date, float]], start: date, today: date
           ) -> tuple[Onset | None, list[Onset]]:
    """(démarrage, faux départs) selon la règle 20 mm en 3 jours sans 7 jours secs ensuite."""
    false_starts: list[Onset] = []
    mm = [v for _, v in days]
    i = 0
    while i + ONSET_DAYS <= len(days):
        d0 = days[i][0]
        rain3 = sum(mm[i:i + ONSET_DAYS])
        if d0 < start or rain3 < ONSET_MM or mm[i] < 1.0:  # le 1er jour est un jour de pluie
            i += 1
            continue
        after = mm[i + ONSET_DAYS:i + ONSET_DAYS + CHECK_DAYS]
        run = longest = 0
        for v in after:
            run = run + 1 if v < 1.0 else 0
            longest = max(longest, run)
        onset = Onset(d0, rain3, observed=d0 <= today, confirmed=len(after) >= CHECK_DAYS)
        if longest >= DRY_SPELL:
            false_starts.append(onset)
            i += ONSET_DAYS  # on cherche plus loin
            continue
        return onset, false_starts
    return None, false_starts


def varieties_for(region: str, sow: date, end: date, catalogue) -> dict[str, list[str]]:
    """Variétés dont le cycle tient avant la fin habituelle des pluies (et la zone)."""
    from .carte import ZONES

    if catalogue is None or catalogue.empty:
        return {}
    left = (end - sow).days - 5  # marge
    lo, hi = ZONES[REGION_ZONE[region]][2]
    out = {}
    for crop in CROPS:
        v = catalogue[(catalogue["culture"] == crop) & (catalogue["cycle_max"] <= left)]
        rain_ok = v["pluie_min"].isna() | ((v["pluie_min"] < hi) & (v["pluie_max"] > lo))
        names = v[rain_ok].sort_values("cycle_max", ascending=False)["variete"].tolist()
        if names:
            out[crop] = names[:4]
    return out


# ------------------------------------------------------------------ calendrier
def build(region: str, mode: str, catalogue=None, today: date | None = None,
          rain: dict | None = None) -> Calendar | None:
    """Calendrier de semis d'une région : « now » (prévisions) ou une année passée."""
    today = today or date.today()
    zone = REGION_ZONE[region]
    (sm, sd), (em, ed), usual = ZONE_SEASON[zone]
    if mode == "now":
        series = (rain if rain is not None else recent_rain()).get(region)
        year = today.year
    else:
        year = int(mode)
        series = (rain if rain is not None else season_rain(year)).get(region)
        today = date(year, 12, 31)  # saison passée : tout est relevé
    if not series:
        return None
    start, end = date(year, sm, sd), date(year, em, ed)
    cal = Calendar(region, mode, series, season_end=end)
    cal.onset, cal.false_starts = detect(series, start, today)
    place = label(region)
    if mode == "now" and not (start <= today <= end + timedelta(days=10)):
        nxt = year + 1 if today > end else year
        cal.status = "Saison sèche"
        cal.message = (f"Pas de semis pluvial à {place} en ce moment : le démarrage habituel "
                       f"des pluies y est {usual}. Semez quand il est tombé au moins 20 mm en "
                       "3 jours et qu'aucune période sèche de 7 jours n'est annoncée. En "
                       "attendant : cultures irriguées et maraîchage de contre-saison.")
        cal.level = "info"
        cal.varieties = varieties_for(region, date(nxt, sm, sd) + timedelta(days=20),
                                      date(nxt, em, ed), catalogue)
        return cal
    if cal.onset:
        o = cal.onset
        when = f"{o.day:%d/%m}"
        if o.observed and o.confirmed:
            cal.status = f"Saison démarrée le {when}"
            cal.message = (f"{o.rain3:.0f} mm en 3 jours à partir du {when}, sans période "
                           "sèche de 7 jours ensuite : bonne date de semis.")
            cal.level = "ok"
        elif o.observed:
            cal.status = f"Démarrage probable le {when}"
            cal.message = (f"{o.rain3:.0f} mm en 3 jours à partir du {when}. Les prévisions "
                           "n'annoncent pas de longue période sèche : semez si le sol est "
                           "humide sur au moins 15 cm.")
            cal.level = "ok"
        else:
            cal.status = f"Fenêtre de semis annoncée vers le {when}"
            cal.message = (f"Les prévisions annoncent environ {o.rain3:.0f} mm en 3 jours à "
                           f"partir du {when} : préparez les semences, semez après la pluie.")
            cal.level = "info"
        cal.varieties = varieties_for(region, o.day, end, catalogue)
        left = (end - o.day).days
        if not cal.varieties and catalogue is not None and not catalogue.empty:
            early = (catalogue[catalogue["culture"].isin(CROPS)].sort_values("cycle_min")
                     .drop_duplicates("culture").head(3))
            names = ", ".join(f"{r.variete} ({r.culture}, {r.cycle_min:.0f} j)"
                              for r in early.itertuples())
            cal.late = (f"Semis tardif : il reste environ {left} jours de pluie jusqu'à la fin "
                        "habituelle de la saison, moins que le cycle des variétés du catalogue. "
                        f"Les plus hâtives ({names}) risquent de manquer d'eau en fin de cycle.")
            cal.level = "alerte"
    else:
        cal.status = "Démarrage pas encore atteint"
        cal.message = ("Il n'est pas encore tombé 20 mm en 3 jours suivis d'une période "
                       "favorable : attendez avant de semer.")
        cal.level = "alerte" if cal.false_starts else "info"
    if cal.false_starts:
        fs = cal.false_starts[0]
        cal.message += (f" Attention : faux départ le {fs.day:%d/%m} ({fs.rain3:.0f} mm puis "
                        "au moins 7 jours sans pluie) ; les semis faits ce jour-là étaient "
                        "exposés à la sécheresse.")
    return cal
