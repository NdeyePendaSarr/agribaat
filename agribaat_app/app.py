"""Interface AgriBaat (Gradio). Lancement : python app.py  ->  http://127.0.0.1:7860"""

from __future__ import annotations

import base64
import html
import importlib.util
import logging
import urllib.parse
from pathlib import Path

import gradio as gr
import pandas as pd

import config
from agribaat.answers import CATALOGUE, fmt_month, fmt_number, fmt_period, place
from agribaat.knowledge import KnowledgeBase
from agribaat.knowledge import decade_end
from agribaat.lexicon import PRODUCT_BY_KEY, PRODUCTS
from agribaat import carte, labo, langues, warmup
from agribaat.carte import SenegalMap
from agribaat.pipeline import Assistant, Result

# Windows : quand le navigateur recharge la page, asyncio journalise une « erreur »
# WinError 10054 (connexion fermée par le navigateur) sans conséquence. On la masque.
logging.getLogger("asyncio").addFilter(
    lambda record: not (record.exc_info and "10054" in str(record.exc_info[1])))

kb = KnowledgeBase(config.PROCESSED_DIR)
assistant = Assistant(kb)

# Les modèles vocaux demandent torch + transformers. Sans eux : mode texte seul.
VOICE_READY = all(importlib.util.find_spec(m) for m in ("torch", "transformers"))

ALL = "__all__"
PRICE_PRODUCTS = [(p.label.capitalize(), p.key) for p in PRODUCTS
                  if p.key in set(kb.prices["product"])]
STAT_PRODUCTS = [(p.label.capitalize(), p.key) for p in PRODUCTS
                 if p.key in set(kb.national["product"])]
PRICE_REGIONS = [("Toutes les régions", ALL)] + [
    (place(r), r) for r in sorted(kb.prices["region"].unique())]
INDICATORS = [("Production (tonnes)", "production"), ("Superficie (hectares)", "superficie"),
              ("Rendement (kg/ha)", "rendement")]
UNITS = {"production": "t", "superficie": "ha", "rendement": "kg/ha"}

LAST_DATE = kb.prices["date"].max()
N_MARKETS = kb.prices["market"].nunique()
YEARS_FAO = (int(kb.national["year"].min()), int(kb.national["year"].max()))

# Langues du sélecteur -> code interne (voir agribaat/langues.py).
LANG_CODES = {"Wolof": "wo", "Pulaar": "pul", "Sereer": "srr", "Français": "fr"}
LANG_CHOICES = [("Wolof · prioritaire", "Wolof"), ("Pulaar", "Pulaar"),
                ("Sereer · écrit", "Sereer"), ("Français", "Français")]

# Questions types, différentes pour chaque langue choisie : (question, titre court).
# Phrases locales construites avec le vocabulaire des réponses relues par les locuteurs
# (wolof.py, pulaar.py, sereer.py) ; chacune est vérifiée par tests/test_core.py.
EXAMPLES_BY_LANG: dict[str, list[tuple[str, str]]] = {
    "Français": [
        ("Quel est le prix du mil à Kaolack ?", "Prix du mil à Kaolack"),
        ("Quelle a été la production d'arachide en 2024 ?", "Production d'arachide 2024"),
        ("Quelle variété de mil à cycle court ?", "Variété de mil à cycle court"),
        ("Il a plu combien à Mbour ?", "Pluie à Mbour"),
        ("Quand récolter l'arachide ?", "Quand récolter l'arachide ?"),
        ("Quelle dose de NPK pour le mil ?", "Dose d'engrais NPK pour le mil"),
        ("Comment stocker le niébé ?", "Stocker le niébé"),
        ("Comment lutter contre le striga ?", "Lutter contre le striga"),
    ],
    "Wolof": [
        ("njëg dugub ci Kaolack", "« njëg dugub ci Kaolack »"),
        ("soble bi ñaata lay jar ci Dakar", "« soble bi ñaata lay jar ci Dakar »"),
        ("ñaata gerte lañu góob ci 2022", "« ñaata gerte lañu góob ci 2022 »"),
        ("ñaata ektaar dugub lañu bey ci Kaffrine", "« ektaar dugub ci Kaffrine »"),
        ("taw bi ñaata la ci Kolda", "« taw bi ñaata la ci Kolda »"),
        ("xeeti ñebbe yu gaaw", "« xeeti ñebbe yu gaaw »"),
        ("kañ lañuy góob gerte", "« kañ lañuy góob gerte »"),
        ("engrais NPK ci dugub", "« engrais NPK ci dugub »"),
    ],
    "Pulaar": [
        ("Hol no coggu kiloo gawri woni e Kawlak?", "« coggu gawri e Kawlak »"),
        ("coggu maaro e luumo Tilene", "« coggu maaro e luumo Tilene »"),
        ("hol ko heɓaa e biriiji e hitaande 2022", "« ko heɓaa e biriiji 2022 »"),
        ("gawri aawaama e ektaar no foti e Kaffrine", "« gawri aawaama e Kaffrine »"),
        ("toɓo e Kolda no foti", "« toɓo e Kolda no foti »"),
        ("noone ñebbe yaawɗe", "« noone ñebbe yaawɗe »"),
        ("ektaar gooto makka rokkata no foti", "« ektaar gooto makka »"),
        ("engrais NPK e gawri", "« engrais NPK e gawri »"),
    ],
    "Sereer": [
        ("njeg kilo maac no Kaolack", "« njeg kilo maac no Kaolack »"),
        ("kilo maalo a jeg no marse Tilene", "« kilo maalo no marse Tilene »"),
        ("xoox gerte no ndiig 2022", "« xoox gerte no ndiig 2022 »"),
        ("tool maac a beyaa no Kaffrine", "« tool maac no Kaffrine »"),
        ("ndoɓ no Mbour", "« ndoɓ no Mbour »"),
        ("xeet ñebbe a gaawe", "« xeet ñebbe a gaawe »"),
        ("ektaar leng mboq", "« ektaar leng mboq »"),
        ("engrais NPK no maac", "« engrais NPK no maac »"),
    ],
}
N_EXAMPLES = 8
assert all(len(v) == N_EXAMPLES for v in EXAMPLES_BY_LANG.values())

# Réponses vocales préparées au démarrage : celles du scénario de démo seulement (sur un
# PC de 8 Go, chaque phrase nouvelle prend 30 s à 2 min).
WARM_QUESTIONS = [
    ("Quel est le prix du mil à Kaolack ?", "Français"),
    ("Quelle a été la production d'arachide en 2024 ?", "Français"),
    ("Quelle variété de mil à cycle court ?", "Français"),
    ("Il a plu combien à Mbour ?", "Français"),
    ("Quand récolter l'arachide ?", "Français"),
    ("njëg dugub ci Kaolack", "Wolof"),
    ("Hol no coggu kiloo gawri woni e Kawlak?", "Pulaar"),
    ("njeg kilo maac no Kaolack", "Sereer"),
]


def _example_label(question: str, lang: str, title: str) -> str:
    """« 🌾 Prix du mil à Kaolack » : une seule ligne, l'icône tirée de la vraie réponse."""
    from agribaat.answers import answer
    from agribaat.nlu import parse

    ans = answer(parse([question], kb), kb)
    hl = ans.highlight
    icon = hl.icon if hl is not None else ("📚" if (ans.source or "").endswith("(extrait)")
                                           else "🌦️")
    return f"{icon}  {title}"


EXAMPLE_LABELS = {lang: [_example_label(q, lang, t) for q, t in cards]
                  for lang, cards in EXAMPLES_BY_LANG.items()}

# Préparation en arrière-plan : modèles vocaux + réponses vocales des questions types.
WARMUP = (warmup.start(assistant, [(t, LANG_CODES[l]) for t, l in WARM_QUESTIONS])
          if VOICE_READY else warmup.WarmupStatus(state="désactivé"))

CSS = """
/* Le conteneur suit la largeur de l'écran : sans cela, sur un écran étroit (< 700 px),
   la barre d'onglets l'élargissait et le contenu était coupé à droite. */
.gradio-container {max-width: 1180px !important; margin: auto; width: 100% !important;
                   min-width: 0 !important;}
.gradio-container .row > *, .gradio-container .column, .gradio-container .block,
.gradio-container .form {min-width: 0;}
[role=tablist] {overflow-x: auto; flex-wrap: nowrap; scrollbar-width: thin;}
[role=tablist] button {flex: 0 0 auto; white-space: nowrap;}
footer {display: none !important;}
html, body {overflow-x: hidden;}

#hero {background: linear-gradient(135deg, #14532d 0%, #3f6212 55%, #a16207 100%);
       color: #fff; border-radius: 20px; padding: 26px 30px; margin-bottom: 4px;}
#hero h1 {color: #fff; font-size: 2.2rem; margin: 0; letter-spacing: -0.5px;}
#hero .tag {color: #ecfccb; margin: 4px 0 16px 0; font-size: 1.05rem;}
#hero .chips {display: flex; flex-wrap: wrap; gap: 8px;}
#hero .chip {background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.25);
             border-radius: 999px; padding: 4px 12px; font-size: .88rem; color: #fff;}

.mode {border-radius: 12px; padding: 10px 14px; font-size: .92rem; margin: 2px 0;}
.mode.ok {background: #dcfce7; color: #14532d;}
.mode.text {background: #fef3c7; color: #78350f;}

.card {border: 1px solid var(--border-color-primary); border-radius: 16px;
       padding: 18px 20px; background: var(--block-background-fill);}
.card .lbl {font-size: .78rem; text-transform: uppercase; letter-spacing: .06em;
            color: var(--body-text-color-subdued); margin-bottom: 6px;}
.card .wo {font-size: 1.35rem; line-height: 1.45; font-weight: 600; margin-bottom: 12px;}
.card .fr {font-size: 1.08rem; line-height: 1.55;}
.card .empty {color: var(--body-text-color-subdued); font-style: italic;}
.badges {display: flex; flex-wrap: wrap; gap: 6px; margin-top: 14px;}
.badge {font-size: .8rem; border-radius: 999px; padding: 3px 10px;
        background: var(--background-fill-secondary); color: var(--body-text-color);}
.badge.src {background: #dcfce7; color: #14532d;}
.badge.miss {background: #fee2e2; color: #7f1d1d;}
.heard {font-size: .92rem; margin-bottom: 12px; padding: 8px 10px; border-radius: 8px;
         background: var(--background-fill-secondary); color: var(--body-text-color);}
.hint {font-size: .85rem; color: var(--body-text-color-subdued);}
.warn {margin-top: 12px; font-size: .85rem; color: #92400e; background: #fffbeb;
       border-left: 3px solid #f59e0b; padding: 8px 10px; border-radius: 6px;}

.kpis {display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px;}
.kpi {border: 1px solid var(--border-color-primary); border-radius: 14px; padding: 14px 16px;
      background: var(--block-background-fill);}
.kpi .k {font-size: .78rem; color: var(--body-text-color-subdued); text-transform: uppercase;
         letter-spacing: .05em;}
.kpi .v {font-size: 1.55rem; font-weight: 700; margin-top: 4px;}
.kpi .s {font-size: .85rem; color: var(--body-text-color-subdued); margin-top: 2px;}
.bad {color: #b91c1c;} .good {color: #15803d;}

#ask-voice button {font-size: 1.05rem;}
.hist {font-size: .9rem;}

/* Téléphone : en-tête compact, cartes de chiffres sur deux colonnes, textes lisibles. */
@media (max-width: 640px) {
  #hero {padding: 18px 16px; border-radius: 14px;}
  #hero h1 {font-size: 1.6rem;}
  #hero .tag {font-size: .95rem; margin-bottom: 10px;}
  #hero .chip {font-size: .78rem; padding: 3px 9px;}
  .kpis {grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px;}
  .kpi {padding: 10px 12px;}
  .kpi .v {font-size: 1.2rem;}
  .card {padding: 14px;}
  .card .wo {font-size: 1.15rem;}
  #ask-voice button {min-height: 52px;}  /* gros bouton micro, facile à toucher */
}

/* ===================== Refonte visuelle (maquette PAS Challenge) ===================== */
:root {--ab-green: #15803d; --ab-green-d: #14532d; --ab-mint: #ecfdf5; --ab-line: #d1fae5;
       --ab-amber: #b45309; --ab-red: #dc2626;}
#hero {position: relative;}
#hero .event {position: absolute; top: 20px; right: 22px; background: rgba(0,0,0,.22);
              border: 1px solid rgba(255,255,255,.3); color: #fef3c7; font-size: .8rem;
              font-weight: 600; padding: 4px 12px; border-radius: 999px;}
#hero .event::before {content: "●"; color: #4ade80; margin-right: 6px;}
@media (max-width: 640px) {#hero .event {position: static; display: inline-block;
                                          margin-bottom: 8px;}}

/* Bandeau d'état + choix de langue */
#status-row {align-items: stretch; gap: 10px;}
#status-row .mode {height: 100%; display: flex; align-items: center; margin: 0;}
#lang-toggle {padding: 0 !important; background: transparent !important; border: none !important;}
#lang-toggle .wrap {gap: 6px; flex-wrap: wrap; justify-content: flex-end;}
#lang-toggle label {border-radius: 10px !important; font-weight: 600; padding: 8px 12px !important;
                    border: 1px solid var(--border-color-primary) !important;}
#lang-toggle label.selected {background: var(--ab-green) !important; color: #fff !important;
                             border-color: var(--ab-green) !important;}
#lang-toggle input {display: none;}

/* Carte micro : grand cercle rouge */
#mic-card {border: 1px solid var(--ab-line); border-radius: 18px; background:
           linear-gradient(180deg, #f0fdf4 0%, var(--block-background-fill) 60%);
           padding: 18px 16px 8px; text-align: center;}
#mic-card .mic-title {font-size: 1.25rem; font-weight: 700; margin: 4px 0 2px;}
#mic-card .mic-sub {font-size: .9rem; color: var(--body-text-color-subdued);}
#mic {border: none !important; background: transparent !important; box-shadow: none !important;}
#mic .controls {flex-direction: column; align-items: center; gap: 10px;}
#mic .record-button, #mic .stop-button, #mic .stop-button-paused {
    width: 124px !important; height: 124px !important; border-radius: 50% !important;
    margin: 14px auto 6px !important; padding: 0 !important; font-size: 0 !important;
    align-items: center; justify-content: center;  /* affichage géré par Gradio */
    background: radial-gradient(circle at 35% 30%, #f87171, #b91c1c 70%) !important;
    border: 4px solid #fde68a !important; color: #fff !important;
    box-shadow: 0 0 0 12px rgba(220,38,38,.12), 0 0 0 24px rgba(220,38,38,.06);
    transition: transform .15s ease;}
#mic .record-button:hover {transform: scale(1.04);}
#mic .record-button::before {content: "🎙️"; font-size: 44px; line-height: 1;
    background: none !important; width: auto !important; height: auto !important;
    margin: 0 !important; border-radius: 0 !important;}  /* remplace le point vert Gradio */
#mic .stop-button::before, #mic .stop-button-paused::before {
    content: "■"; font-size: 40px; color: #fff; line-height: 1; animation: none !important;
    background: none !important; width: auto !important; height: auto !important;
    margin: 0 !important; border-radius: 0 !important;}
#mic .stop-button {animation: ab-pulse 1.4s ease-in-out infinite;}
#mic .record-icon, #mic .pinger, #mic .dot, #mic .hidden,
#mic .pause-button, #mic .resume-button {display: none !important;}
@keyframes ab-pulse {0%, 100% {box-shadow: 0 0 0 10px rgba(220,38,38,.18), 0 0 0 22px rgba(220,38,38,.08);}
                     50% {box-shadow: 0 0 0 18px rgba(220,38,38,.25), 0 0 0 34px rgba(220,38,38,.10);}}
#mic-card .hint {display: block; margin: 4px 0 6px;}

/* Carte réponse « chiffre vérifié » */
.answer {border: 1px solid var(--ab-line); border-radius: 18px; padding: 16px 18px;
         background: var(--block-background-fill);}
.ans-head {display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px;
           margin-bottom: 12px;}
.achip {font-size: .74rem; font-weight: 700; letter-spacing: .03em; border-radius: 6px;
        padding: 4px 9px; text-transform: uppercase;}
.achip.ok {background: var(--ab-green-d); color: #fff;}
.achip.miss {background: #fee2e2; color: #991b1b;}
.achip.src {background: #fef3c7; color: #92400e; text-transform: none; font-weight: 600;
           border: 1px solid #fde68a;}
.kpi-box {display: flex; align-items: center; justify-content: space-between; gap: 12px;
          border: 1px solid var(--border-color-primary); border-radius: 14px; padding: 12px 14px;
          margin-bottom: 12px;}
.kpi-box .k {font-size: .74rem; text-transform: uppercase; letter-spacing: .05em;
             color: var(--body-text-color-subdued); font-weight: 600;}
.kpi-box .big {font-size: 2rem; font-weight: 800; color: var(--ab-green-d); line-height: 1.15;
               margin: 2px 0;}
.kpi-box .big small {font-size: 1.05rem; font-weight: 700;}
.kpi-box .s {font-size: .82rem; color: var(--body-text-color-subdued);}
.kpi-box .ico {font-size: 1.9rem; background: var(--ab-mint); border: 1px solid var(--ab-line);
               border-radius: 12px; width: 56px; height: 56px; display: flex;
               align-items: center; justify-content: center; flex: 0 0 auto;}
.pill {font-size: .78rem; font-weight: 700; border-radius: 999px; padding: 2px 8px;
       vertical-align: middle; margin-left: 6px;}
.pill.up {background: #dcfce7; color: #166534;} .pill.down {background: #fee2e2; color: #991b1b;}
.wo-quote {font-size: 1rem; font-weight: 600; line-height: 1.45; margin-bottom: 6px;}
.draft {font-size: .85rem; color: #8a5a00; background: #fff6e0; border-radius: 8px; padding: 4px 10px; margin-bottom: 8px; display: inline-block;}
.fr-line {font-size: .92rem; color: var(--body-text-color-subdued); line-height: 1.5;}
/* Orientation vers un conseiller (quand l'assistant n'a pas la réponse) */
.orient {margin-top: 12px; font-size: .9rem; line-height: 1.45; border-radius: 10px;
         padding: 10px 12px; background: var(--ab-mint); border: 1px solid var(--ab-line);}
/* Partage WhatsApp (relais des organisations de producteurs) */
.share {display: inline-flex; align-items: center; gap: 6px; margin-top: 12px;
        font-size: .85rem; font-weight: 700; text-decoration: none !important;
        color: #fff !important; background: #1f9d55; border-radius: 999px; padding: 7px 14px;}
.share:hover {background: #15803d;}

/* Questions types illustrées */
.ex-title {font-size: .8rem; font-weight: 800; letter-spacing: .05em; text-transform: uppercase;
           margin: 14px 0 6px;}
.ex-card {white-space: pre-line !important; text-align: left !important; display: block !important;
          line-height: 1.3 !important; min-height: 0; border-radius: 12px !important;
          border: 1px solid var(--border-color-primary) !important;
          color: var(--body-text-color) !important; background: var(--block-background-fill) !important;
          padding: 10px 12px !important; font-weight: 600 !important; font-size: .9rem !important;}
.ex-card:hover {border-color: var(--ab-green) !important; background: var(--ab-mint) !important;}

/* Barres horizontales (production par région, pluie par région) */
.hbars {border: 1px solid var(--ab-line); border-radius: 16px; padding: 14px 16px;
        background: var(--block-background-fill);}
.hbars h4 {margin: 0 0 10px; font-size: .95rem;}
.hbar {display: grid; grid-template-columns: 110px 1fr 86px; align-items: center; gap: 10px;
       margin: 6px 0; font-size: .86rem;}
.hbar .n {font-weight: 600; text-align: right; overflow: hidden; text-overflow: ellipsis;
          white-space: nowrap;}
.hbar .track {display: block; background: var(--background-fill-secondary); border-radius: 999px;
              height: 12px; overflow: hidden;}
.hbar .fill {display: block; height: 100%; border-radius: 999px;
             background: linear-gradient(90deg, #15803d, #34d399);}
.hbar .v {font-weight: 700; font-variant-numeric: tabular-nums;}
.hbars .note {font-size: .78rem; color: var(--body-text-color-subdued); margin-top: 8px;}

/* Tableau des variétés */
.vtable {width: 100%; border-collapse: separate; border-spacing: 0; font-size: .86rem;
         border: 1px solid var(--border-color-primary); border-radius: 14px; overflow: hidden;}
.vtable th {background: var(--background-fill-secondary); text-align: left; font-size: .72rem;
            text-transform: uppercase; letter-spacing: .05em; padding: 10px 12px;}
.vtable td {padding: 12px; border-top: 1px solid var(--border-color-primary); vertical-align: top;}
.vtable th, .vtable td {border-left: none !important; border-right: none !important;
                        border-bottom: none !important;}
.vtable thead th {border-top: none !important;}
.vtable td.name {font-weight: 800; color: var(--ab-green-d); white-space: nowrap;}
.vtable td.num {white-space: nowrap; font-variant-numeric: tabular-nums;}
.tag {display: inline-block; font-size: .72rem; font-weight: 700; border-radius: 999px;
      padding: 2px 9px; margin: 1px 2px 1px 0;}
.tag.huilerie {background: #fef3c7; color: #92400e;}
.tag.confiserie {background: #dbeafe; color: #1e40af;}
.vscroll {overflow-x: auto;}
.src-note {font-size: .8rem; color: var(--body-text-color-subdued); margin-top: 6px;}

/* À propos */
.about h3 {margin: 6px 0 10px;}
.about .pipe {border: 1px solid var(--ab-line); background: var(--ab-mint); border-radius: 14px;
              padding: 14px 16px; margin: 16px 0;}
.about .pipe b {color: var(--ab-green-d);}
.about ul {margin: 6px 0 0 18px;}
.about li {margin: 3px 0;}
@media (max-width: 640px) {
  .kpi-box .big {font-size: 1.6rem;}
  .hbar {grid-template-columns: 84px 1fr 70px;}
  #mic .record-button, #mic .stop-button {width: 104px !important; height: 104px !important;}
  /* Le micro doit être visible sans défiler : en-tête réduit à l'essentiel. */
  #hero {padding: 14px 16px;}
  #hero .event {display: none;}
  #hero h1 {font-size: 1.45rem;}
  #hero .tag {font-size: .84rem; margin: 2px 0 8px;}
  #hero .chip:nth-child(n+3) {display: none;}
  /* Langues : grille 2 x 2 bien alignée au lieu d'une ligne qui déborde. */
  #lang-toggle .wrap {display: grid !important; grid-template-columns: 1fr 1fr; gap: 6px;}
  #lang-toggle label {justify-content: center; padding: 10px 8px !important;}
  /* Questions types : deux par ligne, plus compactes. */
  .ex-row {flex-wrap: wrap !important; gap: 8px !important;}
  .ex-row > * {flex: 1 1 calc(50% - 8px) !important; min-width: 0 !important;}
  .ex-card {font-size: .8rem !important; padding: 8px 10px !important;}
}

/* ===================== Ambiance agricole : terre, champs, mil ===================== */
body, .gradio-container, gradio-app {background: #f7f1e3 !important;}
.gradio-container {background:
    radial-gradient(circle at 12% -10%, rgba(253,230,138,.55), transparent 42%),
    radial-gradient(circle at 95% 0%, rgba(187,247,208,.5), transparent 38%),
    #f7f1e3 !important;}

/* En-tête : paysage dessiné + voile vert pour la lisibilité du texte */
#hero {position: relative; overflow: hidden; padding: 0; min-height: 214px; border-radius: 22px;
       background: #14532d; box-shadow: 0 10px 30px rgba(20,83,45,.18);}
#hero .hero-art {position: absolute; inset: 0; width: 100%; height: 100%;}
#hero .hero-veil {position: absolute; inset: 0;
    background: linear-gradient(90deg, rgba(20,83,45,.96) 0%, rgba(20,83,45,.86) 34%,
                rgba(20,83,45,.25) 62%, rgba(20,83,45,0) 80%);}
#hero .hero-text {position: relative; padding: 24px 30px 18px; max-width: 640px;}
#hero .event {position: static; display: inline-block; margin-bottom: 8px;
              background: rgba(253,230,138,.18); border-color: rgba(253,230,138,.5);}
#hero h1 {font-size: 2.4rem; text-shadow: 0 2px 10px rgba(0,0,0,.25);}
#hero .tag {color: #fef3c7; font-weight: 600; margin: 2px 0 14px;}
#hero .figs {display: flex; flex-wrap: wrap; gap: 10px;}
#hero .fig {display: flex; flex-direction: column; background: rgba(255,255,255,.14);
            border: 1px solid rgba(255,255,255,.28); border-radius: 14px; padding: 7px 13px;
            min-width: 108px;}
#hero .fig b {color: #fff; font-size: 1.05rem; white-space: nowrap;}
#hero .fig small {color: #d9f99d; font-size: .74rem; letter-spacing: .02em;}
#hero .src {color: rgba(255,255,255,.72); font-size: .74rem; margin: 12px 0 0;}

/* Cartes : blanches, ombre douce, liseré vert */
#mic-card, .answer {background: #fffdf8 !important; border: 1px solid #eadfc6 !important;
                    box-shadow: 0 6px 18px rgba(120,90,30,.08);}
.answer {border-left: 5px solid var(--ab-green) !important;}
.kpi-box {background: linear-gradient(135deg, #f0fdf4, #fefce8); border-color: #d9f99d !important;}
.kpi-box .ico {background: #fef3c7; border-color: #fde68a;}
.ex-title {color: #713f12; display: flex; align-items: center; gap: 6px;}
.ex-title::before {content: "🌾";}
.ex-card {background: #fffdf8 !important; border-color: #eadfc6 !important;}
.ex-card:hover {background: #f0fdf4 !important; border-color: var(--ab-green) !important;
                transform: translateY(-1px); box-shadow: 0 4px 12px rgba(21,128,61,.12);}
[role=tablist] button[aria-selected=true] {color: var(--ab-green-d) !important;
    border-bottom: 3px solid #ca8a04 !important; font-weight: 700;}
.mode.ok {background: #ecfccb; color: #365314;}

@media (max-width: 640px) {
  #hero {min-height: 0; border-radius: 16px;}
  #hero .hero-veil {background: linear-gradient(90deg, rgba(20,83,45,.95) 0%,
                    rgba(20,83,45,.8) 60%, rgba(20,83,45,.45) 100%);}
  #hero .hero-text {padding: 14px 16px 12px;}
  #hero h1 {font-size: 1.5rem;}
  #hero .tag {margin-bottom: 8px;}
  #hero .fig {min-width: 0; padding: 5px 9px;}
  #hero .fig b {font-size: .9rem;}
  #hero .fig:nth-child(n+3), #hero .src {display: none;}
}
"""

# Photo de fond (assets/fond_agricole.webp) : plein écran, fixe, intégrée à la page
# (aucun fichier à servir, marche hors ligne). Les blocs deviennent des panneaux
# translucides pour que la photo occupe le plus d'espace possible.
BACKGROUND = Path(__file__).with_name("assets") / "fond_agricole.webp"
if BACKGROUND.exists():
    _bg = "data:image/webp;base64," + base64.b64encode(BACKGROUND.read_bytes()).decode()
    CSS += """
body::before {content: ""; position: fixed; inset: 0; z-index: -1;
    background: linear-gradient(180deg, rgba(10,40,20,.18), rgba(10,40,20,.32)),
                url(__BG__) center 30% / cover no-repeat;}
body, gradio-app, .gradio-container, .gradio-container > .main, .app, .contain,
.gradio-container .wrap.default {background: transparent !important;}
/* En-tête : une bannière où la photo se voit (texte lisible à gauche, visages à droite) */
#hero {background: linear-gradient(90deg, rgba(8,40,18,.78) 0%, rgba(8,40,18,.5) 38%,
                                   rgba(8,40,18,0) 68%) !important;
       box-shadow: none; min-height: 300px; display: flex; align-items: flex-end;}
#hero .hero-art, #hero .hero-veil {display: none;}
#hero .hero-text {max-width: 620px;}
#hero h1, #hero .tag {text-shadow: 0 2px 12px rgba(0,0,0,.55);}
.block:has(> #hero), .block:has(#hero), .prose:has(#hero) {background: transparent !important;
    border: none !important; box-shadow: none !important;}
@media (max-width: 640px) {
  #hero {min-height: 210px; background: linear-gradient(180deg, rgba(8,40,18,.15) 0%,
                                                         rgba(8,40,18,.82) 70%) !important;}
}
/* Panneaux translucides */
.gradio-container .block, #mic-card, .answer, .ex-card, .gradio-container .tabitem {
    background: rgba(255,253,248,.9) !important;}
.gradio-container .tabitem {border-radius: 18px; padding: 10px !important;
    background: rgba(255,253,248,.38) !important;}
[role=tablist] {background: rgba(255,253,248,.9); border-radius: 14px; padding: 2px 6px;}
.ex-title {background: rgba(255,253,248,.9); border-radius: 999px; padding: 4px 12px;
           width: fit-content;}
.mode.ok {background: rgba(236,252,203,.92);}
.mode.text {background: rgba(254,243,199,.92);}
""".replace("__BG__", _bg)

CSS += """
/* Carte du Sénégal : climat et cultures */
.sn-intro {background: rgba(255,253,248,.92); border-radius: 14px; padding: 10px 14px;
           font-size: .95rem; border-left: 5px solid #ca8a04;}
.sn-wrap {background: rgba(255,253,248,.95); border-radius: 18px; padding: 10px;
          border: 1px solid #eadfc6;}
.sn-map {width: 100%; height: auto; display: block;}
.sn-map .reg {transition: opacity .15s; cursor: pointer;}
.sn-map .reg:hover {opacity: .78;}
.sn-map .lbl {font-size: 13px; font-weight: 700; fill: #1f2937; text-anchor: middle;
              paint-order: stroke; stroke: rgba(255,255,255,.85); stroke-width: 3px;
              pointer-events: none;}
.sn-legend {display: flex; flex-wrap: wrap; gap: 6px 14px; margin: 8px 4px 2px;
            font-size: .82rem;}
.sn-legend i {display: inline-block; width: 14px; height: 14px; border-radius: 4px;
              margin-right: 5px; vertical-align: -2px; border: 1px solid rgba(0,0,0,.15);}
.sn-card {background: #fffdf8; border-radius: 18px; padding: 14px 16px;
          border: 1px solid #eadfc6; border-left: 5px solid var(--ab-green);}
.sn-card h3 {margin: 0 0 8px;}
.sn-zone {border-left: 6px solid; padding: 6px 10px; background: #fefce8; border-radius: 8px;
          font-weight: 600; font-size: .92rem;}
.sn-obs {font-size: .85rem; margin-top: 6px; color: var(--body-text-color-subdued);}
.sn-sub {font-size: .78rem; font-weight: 800; text-transform: uppercase; letter-spacing: .05em;
         margin: 12px 0 4px; color: #713f12;}
.sn-card ul {margin: 0; padding-left: 4px; list-style: none;}
.sn-card li {margin: 8px 0; font-size: .95rem;}
.sn-var {font-size: .82rem; color: var(--body-text-color-subdued); margin-top: 2px;}
"""


# ---------------------------------------------------------------- en-tête
# Paysage agricole dessiné en SVG (aucune image à télécharger : marche hors ligne) :
# ciel d'aube, soleil, collines, champ en rangs, mil mûr au premier plan, baobab.
_MILLET = "".join(
    f'<g transform="translate({x},{y}) scale({s})"><path d="M0 0 Q2 -40 0 -78" '
    f'stroke="#6b4f12" stroke-width="2.4" fill="none"/>'
    f'<ellipse cx="1" cy="-92" rx="5.5" ry="17" fill="#a16207"/>'
    f'<path d="M0 -30 Q-14 -40 -22 -36 M0 -46 Q14 -56 22 -52" stroke="#4d7c0f" '
    f'stroke-width="2.2" fill="none"/></g>'
    for x, y, s in ((700, 236, 1.0), (735, 240, 1.15), (770, 234, .9), (805, 242, 1.2),
                    (845, 238, 1.0), (1135, 240, 1.1), (1170, 236, .95)))
HERO_SVG = f"""<svg class="hero-art" viewBox="0 0 1200 240" preserveAspectRatio="xMidYMid slice"
 aria-hidden="true" xmlns="http://www.w3.org/2000/svg">
<defs>
 <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#fde68a"/><stop offset=".6" stop-color="#fcd34d"/>
  <stop offset="1" stop-color="#f59e0b"/></linearGradient>
 <radialGradient id="sun"><stop offset="0" stop-color="#fffbeb"/>
  <stop offset=".45" stop-color="#fef3c7" stop-opacity=".9"/>
  <stop offset="1" stop-color="#fde68a" stop-opacity="0"/></radialGradient>
 <pattern id="rows" width="26" height="12" patternUnits="userSpaceOnUse"
  patternTransform="skewX(-35)"><rect width="26" height="12" fill="#65a30d"/>
  <rect width="26" height="4" fill="#4d7c0f"/></pattern>
</defs>
<rect width="1200" height="240" fill="url(#sky)"/>
<circle cx="980" cy="88" r="95" fill="url(#sun)"/><circle cx="980" cy="88" r="34" fill="#fffbeb"/>
<path d="M0 150 Q160 110 330 140 T700 128 T1000 136 T1200 122 V240 H0Z" fill="#a3b763"/>
<path d="M0 178 Q220 140 480 168 T900 160 T1200 166 V240 H0Z" fill="url(#rows)"/>
<path d="M0 210 Q260 188 560 206 T1200 198 V240 H0Z" fill="#ca8a04"/>
<g fill="#3f3a1d"><path d="M1052 205 C1050 170 1046 150 1040 132 L1062 132 C1060 150 1058 172 1062 205Z"/>
 <ellipse cx="1024" cy="122" rx="30" ry="14"/><ellipse cx="1060" cy="112" rx="36" ry="17"/>
 <ellipse cx="1094" cy="124" rx="26" ry="12"/></g>
{_MILLET}
</svg>"""


def _hero_figures() -> list[str]:
    """Chiffres du jour, tirés des vraies données (mêmes calculs que l'Assistant)."""
    from agribaat.answers import answer
    from agribaat.nlu import parse

    out = []
    for question, label in (("Quel est le prix du mil à Kaolack ?", "Mil · Kaolack"),
                            ("Il a plu combien à Mbour ?", "Pluie · Mbour")):
        hl = answer(parse([question], kb), kb).highlight
        if hl is not None:
            out.append(f'<span class="fig"><b>{hl.icon} {html.escape(hl.value)} '
                       f'{html.escape(hl.unit)}</b><small>{label}</small></span>')
    out.append(f'<span class="fig"><b>📍 {N_MARKETS}</b><small>marchés suivis</small></span>')
    out.append('<span class="fig"><b>🗣️ 3</b><small>langues locales</small></span>')
    return out


def hero_html() -> str:
    figures = "".join(_hero_figures())
    return ('<div id="hero">' + HERO_SVG + '<div class="hero-veil"></div>'
            '<div class="hero-text"><span class="event">PAS Challenge 2026</span>'
            '<h1>🌾 AgriBaat</h1>'
            '<p class="tag">Assistant agricole vocal · wolof, pulaar, sereer</p>'
            f'<div class="figs">{figures}</div>'
            f'<p class="src">Données officielles : PAM · ANACIM · FAOSTAT · DAPSA · '
            f'relevé de {fmt_month(LAST_DATE)}</p></div></div>')


def mode_html() -> str:
    if VOICE_READY:
        s = WARMUP
        if s.state in ("en attente", "chargement"):
            return ('<div class="mode text">⏳ Chargement de la voix (1 à 3 min) · '
                    "l'écrit marche déjà</div>")
        if s.state == "préparation":
            return (f'<div class="mode text">⏳ Préparation de la voix : '
                    f"{s.done}/{s.total}</div>")
        return '<div class="mode ok">🎙️ Mode vocal prêt</div>'
    return ('<div class="mode text">⌨️ Mode texte : les modèles vocaux ne sont pas installés '
            "(torch, transformers). Les questions écrites en français fonctionnent ; "
            "voir le README pour activer la voix.</div>")


# ---------------------------------------------------------------- assistant
EMPTY_CARD = ('<div class="answer"><div class="ans-head"><span class="achip ok">📊 Réponse '
              'sourcée</span></div><div class="fr-line">Posez une question à voix haute '
              "(cercle rouge) ou cliquez une question type : la réponse, son chiffre clé et "
              "sa source s'afficheront ici.</div></div>")


def _num(value: float) -> str:
    return f"{value:+.1f}".replace(".", ",")


# Quand l'assistant n'a pas la réponse, il oriente vers une personne compétente
# (besoin A1 de la cartographie des segments) au lieu de s'arrêter à « je ne sais pas ».
ORIENTATION = ("Pour un problème sur votre parcelle, demandez au conseiller agricole "
               "de votre zone (ANCAR) ou à votre organisation de producteurs.")


def _is_welcome(res: Result) -> bool:
    return res.found and not res.source and not res.highlight


def share_text(res: Result) -> str:
    """Texte partagé sur WhatsApp : réponse locale, français et source."""
    lines = []
    if res.answer_wo:
        lines.append(res.answer_wo)
    lines.append(res.answer_fr)
    if res.source:
        lines.append(f"Source : {res.source}")
    lines.append("— AgriBaat, assistant agricole vocal")
    return "\n\n".join(lines)


def share_link(res: Result) -> str:
    return "https://wa.me/?text=" + urllib.parse.quote(share_text(res))


def answer_card(res: Result, spoken: bool = False) -> str:
    """Carte réponse : chiffre clé vérifié + source + wolof + français."""
    esc = html.escape
    # data-q : la carte change même quand deux questions donnent la même réponse
    # (la démo automatique s'en sert pour savoir que la réponse est arrivée).
    asked = esc(res.question_wo or res.question_fr or "")
    parts = [f'<div class="answer" data-q="{asked}"><div class="ans-head">']
    if _is_welcome(res):  # salutation, aide
        parts.append('<span class="achip ok">💬 Ce que je sais faire</span>')
    elif res.found:
        parts.append('<span class="achip ok">📊 Chiffre vérifié</span>' if res.highlight
                     else '<span class="achip ok">📚 Réponse sourcée</span>')
    else:
        parts.append('<span class="achip miss">Aucune donnée trouvée</span>')
    if res.source:
        parts.append(f'<span class="achip src">Source : {esc(res.source)}</span>')
    parts.append("</div>")
    if spoken:  # question vocale : on montre ce que l'app a entendu
        heard = esc(res.question_wo) if res.question_wo else "<i>(rien de compréhensible)</i>"
        parts.append(f'<div class="heard">🎙️ Entendu : « {heard} »</div>')
    hl = res.highlight
    if hl is not None:
        pill = ""
        if hl.delta is not None and abs(hl.delta) >= 0.1:
            cls = "up" if hl.delta > 0 else "down"
            pill = (f'<span class="pill {cls}">{"▲" if hl.delta > 0 else "▼"} '
                    f'{_num(hl.delta)} % sur un an</span>')
        parts.append(
            f'<div class="kpi-box"><div><div class="k">{esc(hl.label)}</div>'
            f'<div class="big">{esc(hl.value)} <small>{esc(hl.unit)}</small>{pill}</div>'
            f'<div class="s">{esc(hl.sub)}</div></div>'
            f'<div class="ico">{hl.icon}</div></div>')
    langue = langues.get(res.lang)
    if res.answer_wo:
        parts.append(f'<div class="wo-quote">🗣️ {langue.label} : « {esc(res.answer_wo)} »</div>')
        if langue.draft:
            parts.append(f'<div class="draft">✍️ Phrase {langue.label.lower()} en brouillon, '
                         "en cours de relecture par un locuteur natif.</div>")
    parts.append(f'<div class="fr-line"><b>Français :</b> {esc(res.answer_fr)}</div>')
    partial = res.answer_fr.startswith("Je n'ai pas de recommandation sur")
    if not res.found or partial:  # pas de réponse, ou réponse approchante seulement
        parts.append(f'<div class="orient">🧑‍🌾 {esc(ORIENTATION)}</div>')
    if res.found and not _is_welcome(res):
        parts.append(f'<a class="share" href="{esc(share_link(res))}" target="_blank" '
                     'rel="noopener">📤 Partager sur WhatsApp</a>')
    warnings = [w for w in res.warnings if "brouillon" not in w]  # déjà affiché au-dessus
    if warnings and VOICE_READY:  # en mode texte, le bandeau suffit
        parts.append('<div class="warn">' + "<br>".join(esc(w) for w in warnings) + "</div>")
    parts.append("</div>")
    return "".join(parts)


def _details(res: Result) -> str:
    lines = [f"**Question ({langues.get(res.lang).label.lower()}) :** {res.question_wo or '—'}",
             f"**Question (français) :** {res.question_fr or '—'}"]
    if res.speech_wo and res.speech_wo != res.answer_wo:
        lines.append(f"**Texte lu par la voix :** {res.speech_wo}")
    if res.timings:
        lines.append("**Temps par étape :** "
                     + " · ".join(f"{k} {v} s" for k, v in res.timings.items()))
    return "\n\n".join(lines)


def _history_md(history: list[tuple[str, str]]) -> str:
    if not history:
        return "_Aucune question pour l'instant._"
    return "\n".join(f"- **{html.escape(q)}** — {html.escape(a)}" for q, a in history[:6])


def _render(res: Result, history: list, spoken: bool = False):
    question = res.question_fr or res.question_wo
    if question:
        history = [(question, res.answer_fr)] + history[:9]
    return answer_card(res, spoken), res.audio, _details(res), history, _history_md(history)


# Laisse la réponse précédente affichée (gr.skip n'existe pas dans les vieux Gradio).
NOTHING = ((gr.skip() if hasattr(gr, "skip") else gr.update()),) * 5


def on_voice(audio, lang, history):
    # Message doux (pas d'état « Erreur » sur les cases de réponse).
    code = LANG_CODES.get(lang, "wo")
    if code == "srr":
        gr.Warning("Pas encore de reconnaissance vocale en sereer : tapez la question.")
        return NOTHING
    if audio is None:
        gr.Warning("Cliquez d'abord sur « Arrêter » pour terminer l'enregistrement, "
                   "ou importez un fichier audio.")
        return NOTHING
    sr, data = audio
    if len(data) < 0.5 * sr:
        gr.Warning("Enregistrement trop court : parlez au moins une seconde.")
        return NOTHING
    # Français choisi : la question parlée reste en wolof (pas de reconnaissance du français).
    return _render(assistant.ask_audio(sr, data, "pul" if code == "pul" else "wo"), history,
                   spoken=True)


def on_text(text: str, lang: str, history):
    if not text or not text.strip():
        gr.Warning("Tapez d'abord une question.")
        return NOTHING
    return _render(assistant.ask_text(text, LANG_CODES.get(lang, "wo")), history)


MIC_HEAD = {
    "Wolof": ("Maa ngi lay déglu…", "Appuyez sur le cercle rouge et parlez"),
    "Pulaar": ("Question en pulaar", "Appuyez sur le cercle rouge et parlez"),
    "Sereer": ("Sereer · à l'écrit", "Tapez la question ci-dessous"),
    "Français": ("Maa ngi lay déglu…", "Parlez en wolof, ou tapez en français ci-dessous"),
}


def mic_head(lang: str) -> str:
    title, sub = MIC_HEAD.get(lang, MIC_HEAD["Wolof"])
    return f'<div class="mic-title">{title}</div><div class="mic-sub">{sub}</div>'


def on_lang(lang: str):
    """Change le titre du micro et les questions types ; en sereer, ouvre directement
    la saisie au clavier."""
    sereer = lang == "Sereer"
    labels = EXAMPLE_LABELS.get(lang, EXAMPLE_LABELS["Wolof"])
    return (mic_head(lang), gr.Audio(interactive=VOICE_READY and not sereer),
            gr.Accordion(open=True) if sereer else gr.Accordion(),
            *[gr.Button(value=label) for label in labels])


def on_example(i: int, lang: str, history: list):
    """Clic sur la i-ème question type de la langue choisie."""
    question, _ = EXAMPLES_BY_LANG.get(lang, EXAMPLES_BY_LANG["Wolof"])[i]
    return on_text(question, lang, history)


# ---------------------------------------------------------------- prix
def _filtered_prices(product: str, region: str) -> pd.DataFrame:
    df = kb.prices[kb.prices["product"] == product]
    return df if region == ALL else df[df["region"] == region]


def latest_by_market(product: str, region: str) -> pd.DataFrame:
    """Dernier relevé de chaque marché (moyenne des variantes), du moins cher au plus cher.

    Seuls les marchés relevés dans les 12 derniers mois sont gardés : comparer un prix
    de 2010 à un prix de 2026 n'aurait pas de sens. S'il n'y en a aucun, on garde tout.
    """
    df = _filtered_prices(product, region)
    if df.empty:
        return pd.DataFrame(columns=["Marché", "Région", "Prix (FCFA/kg)", "Relevé"])
    last = df.groupby("market")["date"].transform("max")
    cur = (df[df["date"] == last].groupby(["market", "region", "date"], as_index=False)
           ["price_xof_kg"].mean().sort_values("price_xof_kg"))
    recent = cur[cur["date"] > cur["date"].max() - pd.DateOffset(months=12)]
    cur = recent if not recent.empty else cur
    return pd.DataFrame({
        "Marché": cur["market"].map(place),
        "Région": cur["region"].map(place),
        "Prix (FCFA/kg)": cur["price_xof_kg"].round(0).astype(int),
        "Relevé": cur["date"].map(fmt_month),
    })


def price_kpis(product: str, region: str, market: str) -> str:
    fact = kb.price(product, market=None if market == ALL else market,
                    region=None if region == ALL or market != ALL else region)
    if fact is None:
        return '<div class="kpis"><div class="kpi"><div class="k">Prix</div>' \
               '<div class="v">—</div><div class="s">Aucun relevé</div></div></div>'
    where = place(market) if market != ALL else (place(region) if region != ALL else "Sénégal")
    cards = [("Prix moyen" if market == ALL else "Prix", f"{fmt_number(fact.price)} FCFA/kg",
              f"{where} · {fmt_month(fact.date)}")]
    if fact.price_year_before:
        change = (fact.price - fact.price_year_before) / fact.price_year_before * 100
        cls, arrow = ("bad", "▲") if change > 0 else ("good", "▼")
        cards.append(("Sur un an", f'<span class="{cls}">{arrow} {abs(change):.1f} %</span>'.replace('.', ','),
                      f"contre {fmt_number(fact.price_year_before)} FCFA/kg"))
    if fact.min_market:
        cards.append(("Le moins cher", f"{fmt_number(fact.min_price)} FCFA",
                      place(fact.min_market)))
        cards.append(("Le plus cher", f"{fmt_number(fact.max_price)} FCFA",
                      place(fact.max_market)))
    if fact.variants:
        label = PRODUCT_BY_KEY[product].label
        cards.append(("Variantes", str(len(fact.variants)),
                      f"{label} local / importé : prix moyennés"))
    return '<div class="kpis">' + "".join(
        f'<div class="kpi"><div class="k">{k}</div><div class="v">{v}</div>'
        f'<div class="s">{s}</div></div>' for k, v, s in cards) + "</div>"


def price_chart(product: str, region: str, market: str) -> pd.DataFrame:
    df = _filtered_prices(product, region)
    if market != ALL:
        df = df[df["market"] == market]
    return (df.groupby("date", as_index=False)["price_xof_kg"].mean()
            .rename(columns={"price_xof_kg": "prix_fcfa_kg"}))


def on_price_filters(product: str, region: str):
    markets = sorted(_filtered_prices(product, region)["market"].unique())
    dd = gr.Dropdown(choices=[("Tous les marchés", ALL)] + [(place(m), m) for m in markets],
                     value=ALL)
    return (dd, price_kpis(product, region, ALL), price_chart(product, region, ALL),
            latest_by_market(product, region))


def on_price_market(product: str, region: str, market: str):
    return price_kpis(product, region, market), price_chart(product, region, market)


# ---------------------------------------------------------------- production
def national_series(product: str, indicator: str) -> pd.DataFrame:
    df = kb.national[(kb.national["product"] == product)
                     & (kb.national["indicator"] == indicator)]
    out = df[["year", "value"]].sort_values("year")
    # années en dates : l'axe affiche « 1960 » et non « 1,960 »
    return out.assign(year=pd.to_datetime(out["year"].astype(str), format="%Y"))


def hbars_html(title: str, rows: list[tuple[str, float]], unit: str, note: str = "") -> str:
    """Barres horizontales (nom, valeur) : longueur proportionnelle, valeur en clair."""
    if not rows:
        return f'<div class="hbars"><h4>{html.escape(title)}</h4><div class="note">Pas de ' \
               "données.</div></div>"
    top = max(v for _, v in rows) or 1
    lines = "".join(
        f'<div class="hbar"><span class="n" title="{html.escape(n)}">{html.escape(n)}</span>'
        f'<span class="track"><span class="fill" style="width:{max(v / top * 100, 2):.1f}%">'
        f'</span></span><span class="v">{fmt_number(v)} {unit}</span></div>'
        for n, v in rows)
    note_html = f'<div class="note">{html.escape(note)}</div>' if note else ""
    return f'<div class="hbars"><h4>{html.escape(title)}</h4>{lines}{note_html}</div>'


def regional_bars(product: str, indicator: str) -> str:
    df = kb.regional[(kb.regional["product"] == product)
                     & (kb.regional["indicator"] == indicator)
                     & (kb.regional["department"] == "Total")
                     & (kb.regional["region"] != "Senegal")]
    if df.empty:
        return hbars_html("Par région (DAPSA)", [], UNITS[indicator])
    year = int(df["year"].max())
    cur = df[df["year"] == year].sort_values("value", ascending=False)
    rows = [(place(r), float(v)) for r, v in zip(cur["region"], cur["value"])]
    return hbars_html(f"Par région, campagne {year} (DAPSA)", rows, UNITS[indicator],
                      "Source : DAPSA, enquête agricole annuelle.")


def stat_kpis(product: str, indicator: str) -> str:
    fact = kb.stat(product, indicator)
    if fact is None:
        return ""
    unit = UNITS[indicator]
    cards = [(f"Sénégal · {fact.year}", f"{fmt_number(fact.value)} {unit}", "FAOSTAT")]
    prev = kb.stat(product, indicator, year=fact.year - 1)
    if prev is not None and not prev.requested_year and prev.value:
        change = (fact.value - prev.value) / prev.value * 100
        cls, arrow = ("good", "▲") if change > 0 else ("bad", "▼")
        cards.append(("Sur un an", f'<span class="{cls}">{arrow} {abs(change):.1f} %</span>'.replace('.', ','),
                      f"{fact.year - 1} : {fmt_number(prev.value)} {unit}"))
    series = national_series(product, indicator)
    if len(series):
        best = series.loc[series["value"].idxmax()]
        cards.append(("Record", f"{fmt_number(best['value'])} {unit}", f"en {pd.Timestamp(best['year']).year}"))
    return '<div class="kpis">' + "".join(
        f'<div class="kpi"><div class="k">{k}</div><div class="v">{v}</div>'
        f'<div class="s">{s}</div></div>' for k, v, s in cards) + "</div>"


def on_stats(product: str, indicator: str):
    return (stat_kpis(product, indicator), national_series(product, indicator),
            regional_bars(product, indicator))


# ---------------------------------------------------------------- conseils
VARIETY_CROPS = [(PRODUCT_BY_KEY[c].label.capitalize(), c)
                 for c in (kb.varieties["culture"].unique() if not kb.varieties.empty else [])]
CYCLES = [("Tous les cycles", "tous"), ("Cycle court (≤ 95 jours)", "court"),
          ("Cycle long (≥ 110 jours)", "long")]
DECADES = ([(fmt_period(d, decade_end(d)).removeprefix("du ").capitalize(), d.isoformat())
            for d in sorted(kb.rain["decade_debut"].unique(), reverse=True)]
           if not kb.rain.empty else [])
ADVICE_READY = not kb.varieties.empty or not kb.rain.empty


def _span(lo, hi, unit: str = "") -> str:
    if pd.isna(lo):
        return "—"
    return (f"{lo:g}" if lo == hi else f"{lo:g}–{hi:g}") + unit


# ---------------------------------------------------------------- carte climat
SN_MAP = SenegalMap(kb.regional, kb.varieties, kb.rain)
MAP_MODES = [("🌾 Cultures à fort rendement", "best"), ("🌦️ Zones climatiques", "zones"),
             ("Rendement du mil", "mil"), ("Rendement de l'arachide", "arachide"),
             ("Rendement du maïs", "mais"), ("Rendement du riz", "riz"),
             ("Rendement du sorgho", "sorgho"), ("Rendement du niébé", "niebe")]
MAP_REGIONS = [(carte.label(r), r) for r in sorted(carte.REGION_ZONE, key=carte.label)]


def map_view(mode: str, region: str | None) -> str:
    return f'<div class="sn-wrap">{SN_MAP.svg(mode, region)}{SN_MAP.legend(mode)}</div>'


def on_map(mode: str, region: str):
    region = region or "Kaolack"
    return map_view(mode or "best", region), SN_MAP.region_card(region)


def variety_table(crop: str, cycle: str, drought: bool) -> str:
    """Catalogue des variétés en tableau HTML (nom en gras, usages en badges)."""
    df = kb.variety_list(crop, cycle=None if cycle == "tous" else cycle, drought=drought,
                         limit=None)
    if df.empty:
        return '<div class="src-note">Aucune variété ne correspond à ces critères.</div>'
    esc = html.escape
    rows = []
    for r in df.itertuples():
        tags = "".join(f'<span class="tag {esc(t.strip())}">{esc(t.strip().capitalize())}</span>'
                       for t in str(r.vocation or "").split(",") if t.strip() and t != "nan")
        traits = str(r.caracteristiques) if isinstance(r.caracteristiques, str) else "—"
        rows.append(
            f'<tr><td class="name">{esc(r.variete)}</td>'
            f'<td class="num">{_span(r.cycle_min, r.cycle_max)} j</td>'
            f'<td class="num">{_span(r.rendement_min * 1000, r.rendement_max * 1000)}</td>'
            f'<td class="num">{_span(r.pluie_min, r.pluie_max)}</td>'
            f"<td>{esc(traits)}</td><td>{tags or '—'}</td></tr>")
    return ('<div class="vscroll"><table class="vtable"><thead><tr><th>Variété</th>'
            "<th>Cycle</th><th>Rdt (kg/ha)</th><th>Pluie (mm/an)</th>"
            "<th>Points forts et faiblesses</th><th>Usage</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table></div>")


def rain_by_region(decade: str) -> tuple[str, pd.DataFrame, str]:
    day = pd.Timestamp(decade)
    cur = kb.rain[kb.rain["decade_debut"] == day]
    by_region = (cur.dropna(subset=["region"]).groupby("region", as_index=False)["pluie_mm"]
                 .max().sort_values("pluie_mm", ascending=False))
    bars = hbars_html(f"Pluie par région — décade {fmt_period(day, decade_end(day))}",
                      [(place(r), float(v)) for r, v in zip(by_region["region"],
                                                            by_region["pluie_mm"])],
                      "mm", "Relevé le plus élevé de chaque région (bulletin ANACIM).")
    table = pd.DataFrame({"Localité": cur["localite"].map(place),
                          "Région": cur["region"].fillna("").map(place),
                          "Pluie (mm)": cur["pluie_mm"].round(1)}
                         ).sort_values("Pluie (mm)", ascending=False)
    advice = kb.advice[kb.advice["decade_debut"] == day]["recommandation"].tolist()
    md = (f"**Recommandations ANACIM ({fmt_period(day, decade_end(day))})**\n\n"
          + "\n".join(f"- {html.escape(a)}" for a in advice)
          if advice else "_Pas de recommandation dans ce bulletin._")
    return bars, table, md


def on_rain(decade: str):
    return rain_by_region(decade)


# ---------------------------------------------------------------- labo langues
LAB_STATUS = {
    "pulaar": (
        "**Pulaar — expérimental.** Le pulaar est aussi disponible dans l'**Assistant** "
        "(langue « Pulaar »). Reconnaissance vocale : `Wav2vec2-fula` "
        "(erreur ≈ 80 % sur la radio KALLAAMA, souvent des différences d'orthographe ; "
        "≈ 5 s par phrase). Voix de synthèse : Meta MMS (peul).\n\n"
        "Ici, le Labo montre seulement ce que le modèle entend et fait lire une phrase "
        "libre. À juger par un locuteur pulaar."),
    "sereer": (
        "**Sereer — en préparation.** Aucun modèle public de reconnaissance vocale ni de "
        "voix de synthèse sereer n'est utilisable aujourd'hui. Il faudra entraîner le "
        "nôtre sur les 38 h d'enregistrements KALLAAMA déjà collectées "
        "(voir FEUILLE_DE_ROUTE_LANGUES.md). En attendant, l'**Assistant** répond en sereer "
        "**à l'écrit** (langue « Sereer · écrit »)."),
}


def on_lab_lang(lang: str):
    language = labo.LANGUAGES[lang]
    return (LAB_STATUS[lang], gr.Audio(interactive=bool(language.asr_model)),
            gr.Textbox(value=language.example, interactive=bool(language.tts_model)),
            gr.Button(interactive=bool(language.tts_model)))


def on_lab_listen(lang: str, audio):
    if audio is None:
        gr.Warning("Cliquez d'abord sur « Arrêter », ou importez un fichier.")
        return gr.skip() if hasattr(gr, "skip") else gr.update()
    sr, data = audio
    try:
        text = labo.transcribe(lang, sr, data)
    except Exception as exc:  # noqa: BLE001 — modèle absent : message clair
        gr.Warning(str(exc))
        return ""
    return text or "(rien de compréhensible)"


def on_lab_speak(lang: str, text: str):
    try:
        return labo.synthesize(lang, text)
    except Exception as exc:  # noqa: BLE001
        gr.Warning(str(exc))
        return None


# ---------------------------------------------------------------- à propos
_SOURCES = [
    ("Prix de détail par marché", "PAM / WFP (HDX)",
     f"{kb.prices['date'].min().year} – {kb.prices['date'].max().year}"),
    ("Production, superficie, rendement nationaux", "FAOSTAT",
     f"{YEARS_FAO[0]} – {YEARS_FAO[1]}"),
    ("Production par région et département", "DAPSA, enquête agricole annuelle",
     f"{int(kb.regional['year'].min())} – {int(kb.regional['year'].max())}"),
    ("Variétés inscrites au Sénégal", "Catalogue ouest-africain des variétés (CEDEAO)", "—"),
    ("Pluies et recommandations décadaires", "ANACIM, bulletins agrométéorologiques",
     (f"{kb.rain['decade_debut'].min().year} – {kb.rain['decade_debut'].max().year}"
      if not kb.rain.empty else "—")),
]
ABOUT_HTML = (
    '<div class="about"><h3>Sources des données officielles</h3>'
    '<div class="vscroll"><table class="vtable"><thead><tr><th>Donnée</th><th>Source</th>'
    "<th>Période</th></tr></thead><tbody>"
    + "".join(f"<tr><td>{d}</td><td><b>{s}</b></td><td class='num'>{p}</td></tr>"
              for d, s, p in _SOURCES)
    + "</tbody></table></div>"
    '<div class="pipe"><h3>Comment ça marche : aucun chiffre inventé</h3>'
    "Voix wolof → <b>reconnaissance vocale</b> (Wolof-HuBERT) → <b>compréhension</b> "
    "(mots-clés français et wolof, tolérante aux erreurs de transcription) → "
    "<b>réponse tirée des tables officielles</b> (prix, statistiques, variétés, pluies, "
    "recommandations) → <b>phrase wolof construite directement</b> à partir des mêmes "
    "chiffres (pas de traduction automatique) → <b>synthèse vocale</b> (SpeechT5 wolof), "
    "nombres dits en lettres.<br><br><b>Pulaar</b> : même chaîne avec Wav2vec2-fula et la "
    "voix Meta MMS ; <b>sereer</b> : réponses écrites. Phrases pulaar et sereer relues "
    "par des locuteurs natifs.</div>"
    "<h3>Axes d'amélioration</h3><ul>"
    "<li>Validation du wolof par des locuteurs natifs (fiche <code>validation_wolof.csv</code>)."
    "</li><li>Pulaar et sereer : entraînement de la reconnaissance vocale sur "
    "KALLAAMA, voix sereer (<code>FEUILLE_DE_ROUTE_LANGUES.md</code>).</li>"
    "<li>Fiches d'itinéraire technique (semis, engrais) pour des conseils plus concrets.</li>"
    "</ul><p><i>Équipe SMART AGRO — PAS Challenge 2026.</i></p></div>")


# ---------------------------------------------------------------- API (pilier 5)
api_assistant = Assistant(kb, speak=False)  # l'API renvoie du texte : pas de synthèse


def api_demander(question: str, langue: str = "fr") -> dict:
    """Pose une question écrite à AgriBaat et renvoie la réponse en JSON.

    Args:
        question: la question, par ex. « Quel est le prix du mil à Kaolack ? »
        langue: langue de la question et de la réponse locale : fr (réponse wolof),
            wo (wolof), pul (pulaar) ou srr (sereer).
    """
    langue = langue if langue in ("fr", "wo", "pul", "srr") else "fr"
    res = api_assistant.ask_text(question or "", langue)
    hl = res.highlight
    return {
        "question": question, "langue": res.lang, "trouve": res.found,
        "reponse_fr": res.answer_fr, "reponse_locale": res.answer_wo,
        "texte_lu": res.speech_wo, "source": res.source,
        "chiffre_cle": ({"libelle": hl.label, "valeur": hl.value, "unite": hl.unit,
                         "detail": hl.sub, "variation_pct": hl.delta} if hl else None),
        "orientation": ORIENTATION if (not res.found or res.answer_fr.startswith(
            "Je n'ai pas de recommandation sur")) else None,
        "texte_a_partager": share_text(res) if res.found and not _is_welcome(res) else None,
    }


# ---------------------------------------------------------------- interface
THEME = gr.themes.Soft(primary_hue="green", secondary_hue="amber",
                       font=[gr.themes.GoogleFont("Inter"), "sans-serif"])

# Thème clair imposé, comme la maquette : sans cela, un système en mode sombre
# (Ubuntu, Windows) affichait l'app en sombre et les cartes claires devenaient illisibles.
FORCE_LIGHT = """
() => {
  const url = new URL(window.location);
  if (url.searchParams.get("__theme") !== "light") {
    url.searchParams.set("__theme", "light");
    window.location.replace(url.href);
  }
}
"""

with gr.Blocks(title="AgriBaat", css=CSS, theme=THEME, js=FORCE_LIGHT) as demo:
    gr.HTML(hero_html())
    history = gr.State([])

    with gr.Tab("🎙️ Assistant"):
        with gr.Row(elem_id="status-row", equal_height=True):
            with gr.Column(scale=4, min_width=240):
                mode_banner = gr.HTML(mode_html())
            lang = gr.Radio(LANG_CHOICES,
                            value="Wolof", show_label=False, scale=3, min_width=300,
                            elem_id="lang-toggle", container=False)
        demo.load(mode_html, None, mode_banner)  # état réel à chaque ouverture de la page
        if VOICE_READY and not WARMUP.finished:
            # Rafraîchit le bandeau pendant la préparation, puis s'arrête.
            timer = gr.Timer(5)
            timer.tick(lambda: (mode_html(), gr.Timer(active=not WARMUP.finished)),
                       None, [mode_banner, timer])
        with gr.Row(equal_height=False):
            with gr.Column(scale=5, elem_id="mic-card"):
                mic_title = gr.HTML(mic_head("Wolof"))
                mic = gr.Audio(sources=["microphone", "upload"], type="numpy",
                               show_label=False, elem_id="mic", interactive=VOICE_READY)
                btn_voice = gr.Button("↻ Renvoyer la dernière question vocale", size="sm",
                                      variant="secondary", elem_id="ask-voice",
                                      interactive=VOICE_READY)
            with gr.Column(scale=6):
                out_card = gr.HTML(EMPTY_CARD)
                out_audio = gr.Audio(label="🔊 Réponse vocale", autoplay=True,
                                     visible=VOICE_READY, elem_id="answer-audio")
                with gr.Accordion("🔍 Ce que l'assistant a compris", open=False):
                    out_details = gr.Markdown()
                with gr.Accordion("🕘 Questions récentes", open=False):
                    out_hist = gr.Markdown(_history_md([]), elem_classes="hist")
        outputs = [out_card, out_audio, out_details, history, out_hist]

        gr.HTML('<div class="ex-title">Questions types</div>')
        example_buttons = []  # libellés : ceux de la langue choisie (voir on_lang)
        for row_start in range(0, N_EXAMPLES, 4):
            with gr.Row(equal_height=True, elem_classes="ex-row"):
                for i in range(row_start, row_start + 4):
                    example_buttons.append(gr.Button(EXAMPLE_LABELS["Wolof"][i],
                                                     elem_classes="ex-card", min_width=150))
        with gr.Accordion("⌨️ Ou tapez votre question (mode clavier)", open=False) as kb_box:
            with gr.Row(equal_height=True):
                txt = gr.Textbox(placeholder="Ex. : Quel est le prix du mil à Kaolack ?",
                                 show_label=False, lines=1, scale=5)
                btn_text = gr.Button("Envoyer", variant="primary", scale=1, min_width=90)

        lang.change(on_lang, lang, [mic_title, mic, kb_box, *example_buttons])
        btn_voice.click(on_voice, [mic, lang, history], outputs)
        if VOICE_READY:
            # La question part dès qu'on arrête l'enregistrement ou qu'on importe un
            # fichier : plus besoin de penser à cliquer sur « Envoyer ».
            mic.stop_recording(on_voice, [mic, lang, history], outputs)
            mic.upload(on_voice, [mic, lang, history], outputs)
        btn_text.click(on_text, [txt, lang, history], outputs)
        txt.submit(on_text, [txt, lang, history], outputs)
        for i, button in enumerate(example_buttons):  # un clic pose la question
            button.click(lambda lg, h, i=i: on_example(i, lg, h), [lang, history], outputs)

    with gr.Tab("🗺️ Climat & cultures"):
        gr.HTML('<div class="sn-intro"><b>Quoi cultiver, et où ?</b> Pour chaque région : sa '
                "zone climatique et les cultures où son rendement dépasse la moyenne "
                "nationale. Survolez une région pour le détail.</div>")
        with gr.Row(equal_height=False):
            with gr.Column(scale=3, min_width=300):
                map_html = gr.HTML(map_view("best", "Kaolack"))
            with gr.Column(scale=2, min_width=260):
                map_mode = gr.Radio(MAP_MODES, value="best", label="Afficher",
                                    elem_id="map-mode")
                map_region = gr.Dropdown(MAP_REGIONS, value="Kaolack", label="Région")
                map_card = gr.HTML(SN_MAP.region_card("Kaolack"))
        map_mode.change(on_map, [map_mode, map_region], [map_html, map_card])
        map_region.change(on_map, [map_mode, map_region], [map_html, map_card])

    with gr.Tab("📈 Prix des marchés"):
        with gr.Row():
            dd_product = gr.Dropdown(PRICE_PRODUCTS, value="mil", label="Produit")
            dd_region = gr.Dropdown(PRICE_REGIONS, value=ALL, label="Région")
            dd_market = gr.Dropdown([("Tous les marchés", ALL)], value=ALL, label="Marché")
        kpis = gr.HTML()
        chart = gr.LinePlot(x="date", y="prix_fcfa_kg", height=360, x_title=" ",
                            y_title="FCFA / kg", title="Prix de détail mensuel — PAM/WFP")
        with gr.Accordion("Dernier prix par marché, 12 derniers mois (du moins cher au plus cher)", open=True):
            table = gr.Dataframe(interactive=False, max_height=360)
        price_filters = [dd_product, dd_region]
        for comp in price_filters:
            comp.change(on_price_filters, price_filters, [dd_market, kpis, chart, table])
        dd_market.input(on_price_market, [dd_product, dd_region, dd_market], [kpis, chart])
        demo.load(on_price_filters, price_filters, [dd_market, kpis, chart, table])

    with gr.Tab("🌱 Production"):
        with gr.Row():
            dd_sp = gr.Dropdown(STAT_PRODUCTS, value="arachide", label="Culture")
            dd_ind = gr.Dropdown(INDICATORS, value="production", label="Indicateur")
        stat_cards = gr.HTML()
        with gr.Row(equal_height=False):
            nat_chart = gr.LinePlot(x="year", y="value", height=340, x_title=" ",
                                    y_title=" ", title=f"Sénégal — évolution FAOSTAT "
                                    f"({YEARS_FAO[0]}–{YEARS_FAO[1]})", scale=3)
            with gr.Column(scale=2, min_width=260):
                reg_chart = gr.HTML()
        stat_inputs = [dd_sp, dd_ind]
        for comp in stat_inputs:
            comp.change(on_stats, stat_inputs, [stat_cards, nat_chart, reg_chart])
        demo.load(on_stats, stat_inputs, [stat_cards, nat_chart, reg_chart])

    if ADVICE_READY:
        with gr.Tab("🌦️ Conseils"):
            with gr.Accordion("Variétés recommandées (inscrites au Sénégal)", open=True):
                with gr.Row():
                    dd_vcrop = gr.Dropdown(VARIETY_CROPS, value="arachide", label="Culture")
                    dd_cycle = gr.Dropdown(CYCLES, value="tous", label="Cycle")
                    cb_drought = gr.Checkbox(label="Tolérante à la sécheresse")
                v_table = gr.HTML()
                gr.HTML(f"<div class='src-note'>Source : {CATALOGUE} (CEDEAO / CORAF). "
                        "Rendement potentiel : en conditions favorables. Pluie : zone "
                        "pluviométrique adaptée (isohyètes).</div>")
                v_inputs = [dd_vcrop, dd_cycle, cb_drought]
                for comp in v_inputs:
                    comp.change(variety_table, v_inputs, v_table)
                demo.load(variety_table, v_inputs, v_table)
            with gr.Accordion("Pluies et recommandations ANACIM", open=True):
                dd_decade = gr.Dropdown(DECADES, value=DECADES[0][1] if DECADES else None,
                                        label="Décade (bulletin agrométéorologique)")
                with gr.Row(equal_height=False):
                    with gr.Column(scale=3, min_width=260):
                        rain_chart = gr.HTML()
                    advice_md = gr.Markdown()
                with gr.Accordion("Détail par localité", open=False):
                    rain_table = gr.Dataframe(interactive=False, max_height=320)
                dd_decade.change(on_rain, dd_decade, [rain_chart, rain_table, advice_md])
                demo.load(on_rain, dd_decade, [rain_chart, rain_table, advice_md])

    if VOICE_READY:
        with gr.Tab("🧪 Labo langues"):
            gr.Markdown("Essayez les modèles publics existants pour les **autres langues "
                        "du projet**. Phase expérimentale : à faire juger par des "
                        "locuteurs natifs.")
            lab_lang = gr.Radio([(l.label, k) for k, l in labo.LANGUAGES.items()],
                                value="pulaar", label="Langue")
            lab_status = gr.Markdown(LAB_STATUS["pulaar"])
            with gr.Row(equal_height=False):
                with gr.Column():
                    lab_mic = gr.Audio(sources=["microphone", "upload"], type="numpy",
                                       label="Dites une phrase (elle part à l'arrêt)")
                    lab_heard = gr.Textbox(label="Ce que le modèle a entendu", lines=3,
                                           interactive=False)
                with gr.Column():
                    lab_text = gr.Textbox(label="Phrase à faire lire",
                                          value=labo.LANGUAGES["pulaar"].example, lines=3)
                    lab_btn = gr.Button("🔊 Faire lire par la voix de synthèse")
                    lab_audio = gr.Audio(label="Voix de synthèse", autoplay=True)
            lab_lang.change(on_lab_lang, lab_lang, [lab_status, lab_mic, lab_text, lab_btn])
            lab_mic.stop_recording(on_lab_listen, [lab_lang, lab_mic], lab_heard)
            lab_mic.upload(on_lab_listen, [lab_lang, lab_mic], lab_heard)
            lab_btn.click(on_lab_speak, [lab_lang, lab_text], lab_audio)

    with gr.Tab("ℹ️ À propos"):
        gr.HTML(ABOUT_HTML)

    # API JSON : POST /gradio_api/call/demander, ou gradio_client (voir README).
    gr.api(api_demander, api_name="demander")

if __name__ == "__main__":
    # pwa : sur téléphone, « Ajouter à l'écran d'accueil » installe AgriBaat comme une appli.
    demo.launch(pwa=True)
