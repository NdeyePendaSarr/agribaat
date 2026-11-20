"""Bulletin vocal hebdomadaire et alertes climat, par région et par langue.

Bulletin : météo des 7 jours et conseil du moment (Open-Meteo), prix du mil et de
l'arachide dans la région (PAM / WFP), sources. Construit avec les phrases de réponse de
l'Assistant (mêmes chiffres, mêmes gabarits), lu par la voix de synthèse et enregistré en
fichier audio : une radio communautaire le diffuse, une OP le partage sur WhatsApp.

Alertes : régions où les prévisions déclenchent un conseil de niveau « alerte » (forte
pluie, chaleur sèche, vent fort, récoltes à protéger). Les abonnés (OP, radio, producteur)
sont gardés localement ; les messages sont préparés dans une boîte d'envoi, prêts à être
transmis par un opérateur SMS / WhatsApp (à brancher).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import config

from . import langues, meteo
from . import wolof as wo
from .answers import answer
from .carte import label
from .nlu import Query

OUT = config.OUTPUTS_DIR
BULLETIN_DIR = OUT / "bulletins"
SUBSCRIBERS = OUT / "abonnes.csv"
OUTBOX_DIR = OUT / "envois"
BULLETIN_PRODUCTS = ("mil", "arachide")
SUB_FIELDS = ("nom", "type", "region", "langue", "canal", "contact", "inscrit_le")


@dataclass
class Section:
    title: str
    fr: str
    local: wo.WolofText | None = None


@dataclass
class Bulletin:
    region: str
    lang: str
    made: date
    sections: list[Section] = field(default_factory=list)
    local: wo.WolofText = field(default_factory=lambda: wo.WolofText("", ""))

    @property
    def french(self) -> str:
        return " ".join(s.fr for s in self.sections)


def _price_region(region: str) -> str:
    return region.replace("-", " ")  # « Saint-Louis » (météo) / « Saint Louis » (PAM)


def build(region: str, lang: str, kb) -> Bulletin:
    """Script du bulletin (français + langue locale) pour une région."""
    langue = langues.get(lang)
    b = Bulletin(region, langue.code, date.today())
    with wo.using(langue.module):
        parts = [wo.render("bulletin_intro", lieu=label(region))]
        fc = meteo.forecast(region)
        if fc is not None:
            advices = meteo.advice(fc)
            local = meteo.local_text(fc, advices, langue.module)
            b.sections.append(Section("🌤️ Météo des 7 prochains jours", meteo.summary_fr(fc),
                                      local))
            parts.append(local)
        for product in BULLETIN_PRODUCTS:
            ans = answer(Query(intent="prix", product=product, region=_price_region(region)),
                         kb, langue.module)
            if ans.found and ans.wolof is not None:
                name = {"mil": "du mil", "arachide": "de l’arachide"}.get(product, product)
                b.sections.append(Section(f"💰 Prix {name}", ans.text, ans.wolof))
                parts.append(ans.wolof)
        parts.append(wo.render("bulletin_fin"))
    out = parts[0]
    for p in parts[1:]:
        out = out + wo.WolofText(" ", " ") + p
    b.local = out
    return b


def audio_path(b: Bulletin) -> Path:
    return BULLETIN_DIR / f"agribaat_{b.made:%Y-%m-%d}_{b.region}_{b.lang}.wav"


def record(b: Bulletin) -> Path | None:
    """Lit le bulletin à voix haute et l'enregistre (wav). None si pas de voix (sereer)."""
    import soundfile as sf

    from . import labo, models

    langue = langues.get(b.lang)
    if langue.voice_out == "wolof":
        sr, audio = models.synthesize(b.local.speech)
    elif langue.voice_out == "labo":
        sr, audio = labo.synthesize(langue.labo_key, b.local.speech)
    else:
        return None
    path = audio_path(b)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, audio, sr)
    return path


# ------------------------------------------------------------------ alertes
@dataclass
class Alert:
    region: str
    advices: list[meteo.Advice]
    forecast: meteo.Forecast


def current_alerts() -> list[Alert]:
    """Régions dont les prévisions déclenchent au moins un conseil de niveau « alerte »."""
    out = []
    for region, fc in meteo.all_forecasts().items():
        hits = [a for a in meteo.advice(fc) if a.level == "alerte"]
        if hits:
            out.append(Alert(region, hits, fc))
    return sorted(out, key=lambda a: label(a.region))


def alert_text(alert: Alert, lang: str) -> wo.WolofText:
    """« Artu AgriBaat ci Kaolack ! » + les conseils d'alerte dans la langue."""
    module = langues.get(lang).module
    with wo.using(module):
        out = wo.render("alerte_intro", lieu=label(alert.region))
        for a in alert.advices:
            key = f"meteo_{a.key}"
            if key in module.T:
                out = out + wo.WolofText(" ", " ") + wo.render(
                    key, mm=wo.Qty(alert.forecast.rain3, "mm"),
                    tmax=wo.Qty(alert.forecast.tmax7, "c"))
    return out


# ------------------------------------------------------------------ abonnés
def subscribers() -> list[dict]:
    if not SUBSCRIBERS.exists():
        return []
    with SUBSCRIBERS.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def _save(rows: list[dict]) -> None:
    SUBSCRIBERS.parent.mkdir(parents=True, exist_ok=True)
    with SUBSCRIBERS.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SUB_FIELDS, delimiter=";")
        w.writeheader()
        w.writerows(rows)


def subscribe(nom: str, kind: str, region: str, lang: str, canal: str, contact: str = "") -> None:
    rows = subscribers()
    rows.append({"nom": nom.strip(), "type": kind, "region": region, "langue": lang,
                 "canal": canal, "contact": contact.strip(),
                 "inscrit_le": f"{datetime.now():%Y-%m-%d %H:%M}"})
    _save(rows)


def unsubscribe(index: int) -> None:
    rows = subscribers()
    if 0 <= index < len(rows):
        del rows[index]
        _save(rows)


def prepare_outbox(alerts: list[Alert] | None = None) -> tuple[Path | None, list[dict]]:
    """Un message par abonné dont la région est en alerte (texte local + français)."""
    alerts = current_alerts() if alerts is None else alerts
    by_region = {a.region: a for a in alerts}
    rows = []
    for s in subscribers():
        alert = by_region.get(s["region"])
        if alert is None:
            continue
        local = alert_text(alert, s["langue"])
        rows.append({"destinataire": s["nom"], "canal": s["canal"], "contact": s["contact"],
                     "region": label(s["region"]), "langue": langues.get(s["langue"]).label,
                     "message": local.text,
                     "message_fr": " ".join(a.text for a in alert.advices)})
    if not rows:
        return None, []
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTBOX_DIR / f"alertes_{datetime.now():%Y-%m-%d_%H%M}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=";")
        w.writeheader()
        w.writerows(rows)
    return path, rows
