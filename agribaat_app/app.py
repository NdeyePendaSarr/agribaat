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
from agribaat import bulletin, carte, labo, langues, meteo, models, usage, warmup
from agribaat.carte import SenegalMap
from agribaat.charts import area_chart
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

# Système de design : une seule feuille de style (assets/agribaat.css), plus la photo
# de fond intégrée à la page (aucun fichier à servir, marche hors ligne).
ASSETS = Path(__file__).with_name("assets")
CSS = (ASSETS / "agribaat.css").read_text(encoding="utf-8")
# Police Plus Jakarta Sans (variable, licence SIL OFL) intégrée : aucune requête réseau.
_FONT_RANGES = {"latin": "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, "
                         "U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, "
                         "U+2193, U+2212, U+2215, U+FEFF, U+FFFD",
                "latin-ext": "U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, "
                             "U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, "
                             "U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF"}
for _subset, _range in _FONT_RANGES.items():
    _file = ASSETS / "fonts" / f"plus-jakarta-sans-{_subset}.woff2"
    if _file.exists():
        CSS = ("@font-face {font-family: 'Plus Jakarta Sans'; font-style: normal; "
               "font-display: swap; font-weight: 200 800; src: url(data:font/woff2;base64,"
               + base64.b64encode(_file.read_bytes()).decode() + ") format('woff2'); "
               f"unicode-range: {_range};}}\n") + CSS
BACKGROUND = ASSETS / "fond_agricole.webp"
if BACKGROUND.exists():
    _bg = "data:image/webp;base64," + base64.b64encode(BACKGROUND.read_bytes()).decode()
    # La photo habille la carte de bienvenue du tableau de bord.
    CSS += (".dash-head .welcome {background-image: linear-gradient(100deg, rgba(14,59,44,.92)"
            " 0%, rgba(14,59,44,.62) 45%, rgba(14,59,44,.08) 80%), url(" + _bg + ");}")


# ---------------------------------------------------------------- en-tête
def page_head(icon: str, title: str, subtitle: str) -> str:
    """En-tête commun à chaque onglet : icône, titre, une phrase d'explication."""
    return (f'<div class="page-head"><div class="ph-ico">{icon}</div><div>'
            f"<h2>{html.escape(title)}</h2><p>{html.escape(subtitle)}</p></div></div>")


def _hero_figures() -> list[str]:
    """Tuiles « chiffres du jour », tirées des vraies données (mêmes calculs que l'Assistant)."""
    from agribaat.answers import answer
    from agribaat.nlu import parse

    def tile(icon: str, value: str, label: str, tone: str) -> str:
        return (f'<div class="tile {tone}"><div class="t-ico">{icon}</div><div>'
                f"<b>{html.escape(value)}</b><small>{html.escape(label)}</small></div></div>")

    out = []
    for question, label, tone in (("Quel est le prix du mil à Kaolack ?", "Prix du mil · Kaolack",
                                   "gold"),
                                  ("Il a plu combien à Mbour ?", "Dernière pluie · Mbour", "rain")):
        hl = answer(parse([question], kb), kb).highlight
        if hl is not None:
            out.append(tile(hl.icon, f"{hl.value} {hl.unit}", label, tone))
    out.append(tile("📍", str(N_MARKETS), "marchés suivis", "leaf"))
    out.append(tile("🗣️", "3", "langues locales", "forest"))
    return out


def hero_html() -> str:
    """Accueil du tableau de bord : carte de bienvenue (photo) + tuiles de chiffres."""
    return ('<div id="hero" class="dash-head"><div class="welcome">'
            '<span class="event">PAS Challenge 2026</span>'
            '<h1>🌾 AgriBaat</h1>'
            '<p class="tag">Assistant agricole vocal · wolof, pulaar, sereer</p>'
            f'<p class="src">Données officielles : PAM · ANACIM · FAOSTAT · DAPSA · '
            f'relevé de {fmt_month(LAST_DATE)}</p></div>'
            f'<div class="tiles">{"".join(_hero_figures())}</div></div>')


# Navigation : menu latéral (le contenu reste dans des onglets Gradio, cachés, que le
# menu pilote par JavaScript : les tests et la démo automatique fonctionnent toujours).
def nav_items() -> list[tuple[str, str, str]]:
    """(texte de l'onglet, icône, libellé du menu), dans l'ordre des onglets."""
    items = [("Assistant", "🎙️", "Assistant vocal"), ("Météo en direct", "🌤️", "Météo en direct"),
             ("Bulletins & alertes", "📻", "Bulletins & alertes"),
             ("Impact", "📊", "Impact & tests terrain"),
             ("Climat & cultures", "🗺️", "Climat & cultures"),
             ("Prix des marchés", "📈", "Prix des marchés"), ("Production", "🌱", "Production")]
    items += [("Conseils", "🌦️", "Conseils de saison")] if ADVICE_READY else []
    items += [("Labo langues", "🧪", "Labo langues")] if VOICE_READY else []
    return items + [("À propos", "ℹ️", "À propos")]


def sidebar_html() -> str:
    links = "".join(
        f'<a href="#" class="side-link{" active" if i == 0 else ""}" data-tab="{tab}">'
        f'<span class="sl-ico">{icon}</span><span>{html.escape(label)}</span></a>'
        for i, (tab, icon, label) in enumerate(nav_items()))
    return ('<aside class="sidenav"><div class="brand"><div class="logo">🌾</div><div>'
            '<b>AgriBaat</b><small>Assistant agricole vocal</small></div>'
            '<button class="side-close" aria-label="Fermer le menu" title="Fermer le menu">✕'
            '</button></div>'
            f'<div class="side-sec">Navigation</div><nav>{links}</nav>'
            '<div class="side-sec">Langues</div><div class="side-langs">'
            '<span>Wolof</span><span>Pulaar</span><span>Sereer</span><span>Français</span></div>'
            '<div class="side-foot"><b>PAS Challenge 2026</b><span>Équipe SMART AGRO</span>'
            '<small>Aucun chiffre inventé : chaque réponse cite sa source officielle.</small>'
            '</div></aside><div class="nav-scrim"></div>')


def topbar_html() -> str:
    return ('<header class="topbar"><button class="nav-toggle" aria-label="Menu">☰</button>'
            '<div class="crumb">AgriBaat <span>/</span> <b class="tb-page">Assistant vocal</b></div>'
            f'<div class="tb-right"><span class="tb-pill">📅 Données : {fmt_month(LAST_DATE)}</span>'
            '<span class="tb-pill on">● Hors ligne prêt</span></div></header>')


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


def _render(res: Result, history: list, spoken: bool = False, canal: str = "Texte",
            lang: str = "", session: dict | None = None):
    question = res.question_fr or res.question_wo
    if question:
        history = [(question, res.answer_fr)] + history[:9]
    event = usage.log_question(canal=canal, langue=lang or langues.get(res.lang).label,
                               sujet=res.intent, trouve=res.found,
                               temps_s=res.timings.get("total", 0.0), session=session)
    return (answer_card(res, spoken), res.audio, _details(res), history, _history_md(history),
            event)


# Laisse la réponse précédente affichée (gr.skip n'existe pas dans les vieux Gradio).
NOTHING = ((gr.skip() if hasattr(gr, "skip") else gr.update()),) * 6


def on_voice(audio, lang, history, session=None):
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
                   spoken=True, canal="Voix", lang=lang, session=session)


def on_text(text: str, lang: str, history, session=None, canal: str = "Texte"):
    if not text or not text.strip():
        gr.Warning("Tapez d'abord une question.")
        return NOTHING
    return _render(assistant.ask_text(text, LANG_CODES.get(lang, "wo")), history,
                   canal=canal, lang=lang, session=session)


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


def on_example(i: int, lang: str, history: list, session=None):
    """Clic sur la i-ème question type de la langue choisie."""
    question, _ = EXAMPLES_BY_LANG.get(lang, EXAMPLES_BY_LANG["Wolof"])[i]
    return on_text(question, lang, history, session, canal="Question type")


def on_feedback(event: str | None, understood: bool):
    """Avis de l'utilisateur sur la dernière réponse (mesure « réponses comprises »)."""
    if not event:
        gr.Warning("Posez d'abord une question.")
        return
    usage.log_feedback(event, understood)
    gr.Info("Merci ! Votre avis est enregistré." if understood else
            "Merci : nous allons améliorer cette réponse.")


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


def price_chart(product: str, region: str, market: str) -> str:
    """Courbe du prix mensuel (moyenne des marchés retenus)."""
    df = _filtered_prices(product, region)
    if market != ALL:
        df = df[df["market"] == market]
    series = df.groupby("date")["price_xof_kg"].mean()
    where = place(market) if market != ALL else (place(region) if region != ALL else "Sénégal")
    label = PRODUCT_BY_KEY[product].label
    return area_chart([(d.date(), float(v)) for d, v in series.items()],
                      title=f"Prix du {label} · {where}", unit="FCFA/kg",
                      source="Prix de détail mensuel · PAM / WFP")


def market_rank(product: str, region: str) -> str:
    """Classement visuel : marchés les moins chers et les plus chers (12 derniers mois)."""
    df = latest_by_market(product, region)
    if df.empty:
        return hbars_html("Marchés", [], "FCFA")
    rows = list(zip(df["Marché"], df["Prix (FCFA/kg)"].astype(float)))
    n = min(5, len(rows))
    cheap = hbars_html("🟢 Les moins chers", rows[:n], "FCFA")
    dear = hbars_html("🔴 Les plus chers", rows[::-1][:n], "FCFA")
    return (f'<div class="rank">{cheap}{dear}<div class="src-note">Dernier relevé de '
            f"chaque marché, 12 derniers mois · {len(rows)} marchés.</div></div>")


def on_price_filters(product: str, region: str):
    markets = sorted(_filtered_prices(product, region)["market"].unique())
    dd = gr.Dropdown(choices=[("Tous les marchés", ALL)] + [(place(m), m) for m in markets],
                     value=ALL)
    return (dd, price_kpis(product, region, ALL), price_chart(product, region, ALL),
            market_rank(product, region), latest_by_market(product, region))


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


def national_chart(product: str, indicator: str) -> str:
    series = national_series(product, indicator)
    label = PRODUCT_BY_KEY[product].label
    name = dict((v, k) for k, v in INDICATORS).get(indicator, indicator).split(" (")[0]
    return area_chart([(pd.Timestamp(y).date(), float(v)) for y, v in
                       zip(series["year"], series["value"])],
                      title=f"{name} · {label} au Sénégal", unit=UNITS[indicator],
                      source=f"FAOSTAT · {YEARS_FAO[0]}–{YEARS_FAO[1]}", yearly=True)


def on_stats(product: str, indicator: str):
    return (stat_kpis(product, indicator), national_chart(product, indicator),
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


# ---------------------------------------------------------------- météo en direct
METEO_LANGS = [("Wolof", "wo"), ("Pulaar", "pul"), ("Sereer · écrit", "srr")]
DAY_NAMES = ("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim.")


def _sky(day) -> str:
    if day.rain >= 10:
        return "⛈️"
    if day.rain >= 1 or day.prob >= 50:
        return "🌧️"
    if day.prob >= 20:
        return "⛅"
    return "☀️"


def meteo_view(region: str, lang: str, force: bool = False):
    """(conditions + 7 jours, conseils, texte local, vue nationale) pour une région."""
    region = region or "Kaolack"
    fc = meteo.forecast(region, force=force)
    if fc is None:
        empty = ('<div class="mt-card"><b>Prévisions indisponibles</b><p>Pas de connexion à '
                 "Open-Meteo et aucune prévision gardée en mémoire. Connectez-vous à internet "
                 "puis cliquez sur « Actualiser ».</p></div>")
        return empty, "", "", ""
    when = fc.fetched.strftime("%d/%m à %H:%M")
    status = (f'<span class="mt-live">● En direct · mis à jour le {when}</span>' if fc.live else
              f'<span class="mt-off">● Hors ligne · prévisions du {when}</span>')
    days = "".join(
        f'<div class="mt-day"><small>{"Auj." if i == 0 else DAY_NAMES[d.day.weekday()]}</small>'
        f'<span class="mt-sky">{_sky(d)}</span><b>{d.tmax:.0f}°</b><i>{d.tmin:.0f}°</i>'
        f'<em class="{"wet" if d.rain >= 1 else ""}">{d.rain:.0f} mm</em>'
        f'<small>{d.prob:.0f} %</small></div>' for i, d in enumerate(fc.days))
    now = (f'<div class="mt-card mt-now"><div class="mt-top"><div><h4>📍 {carte.label(region)}'
           f"</h4>{status}</div><div class=\"mt-temp\">{fc.temp:.0f}<small>°C</small></div></div>"
           f'<div class="mt-meta"><span>💧 Humidité {fc.humidity:.0f} %</span><span>💨 Vent '
           f"{fc.wind:.0f} km/h</span><span>🌧️ {fc.rain7:.0f} mm sur 7 j</span><span>🌱 "
           f"{fc.et0:.0f} mm/j évaporés</span></div>"
           + f'<div class="mt-days">{days}</div><div class="src-note">Source : Open-Meteo, '
           "prévisions à 7 jours (pluie, probabilité, températures, vent, évapotranspiration)."
           "</div></div>")
    advices = meteo.advice(fc)
    adv = '<div class="mt-advice">' + "".join(
        f'<div class="mt-adv {a.level}"><span class="mt-ico">{a.icon}</span><div><b>'
        f"{html.escape(a.title)}</b><p>{html.escape(a.text)}</p></div></div>" for a in advices)         + '<div class="src-note">Conseils calculés automatiquement à partir des prévisions '        "(règles générales de bonnes pratiques).</div></div>"
    langue = langues.get(lang)
    local = meteo.local_text(fc, advices, langue.module)
    note = ("" if meteo.has_local_advice(langue.module) else
            '<div class="draft">Conseils sereer à écrire par un locuteur : seul le résumé est '
            "traduit pour l'instant.</div>")
    local_html = (f'<div class="mt-card mt-local"><div class="mt-lh">🗣️ Conseil en '
                  f"{langue.label.lower()}</div><p>« {html.escape(local.text)} »</p>{note}"
                  '<div class="draft">Phrases météo en brouillon : à faire relire par un '
                  "locuteur natif.</div></div>")
    return now, adv, local_html, meteo_national()


def meteo_national() -> str:
    rows = []
    for region, fc in sorted(meteo.all_forecasts().items(), key=lambda kv: -kv[1].rain7):
        top = meteo.advice(fc)[0]
        rows.append(f'<div class="mt-reg"><b>{carte.label(region)}</b><span>{top.icon}</span>'
                    f"<em>{fc.rain7:.0f} mm</em><i>{fc.tmax7:.0f}°</i></div>")
    return ('<div class="mt-card"><h4>🇸🇳 Toutes les régions · 7 jours</h4><div class="mt-grid">'
            + "".join(rows) + "</div></div>") if rows else ""


def meteo_listen(region: str, lang: str):
    """Conseil lu à voix haute (wolof : SpeechT5 ; pulaar : Meta MMS ; sereer : pas de voix)."""
    fc = meteo.forecast(region or "Kaolack")
    langue = langues.get(lang)
    if fc is None or not VOICE_READY or langue.voice_out is None:
        return None
    text = meteo.local_text(fc, meteo.advice(fc), langue.module).speech
    if langue.voice_out == "wolof":
        return models.synthesize(text)
    return labo.synthesize(langue.labo_key, text)


# ---------------------------------------------------------------- bulletins & alertes
SUB_TYPES = ["Organisation de producteurs", "Radio communautaire", "Producteur", "Conseiller"]
SUB_CHANNELS = ["WhatsApp", "SMS", "Appel vocal", "Radio"]
OUTBOX_COLS = ["Destinataire", "Canal", "Contact", "Région", "Langue", "Message (langue locale)",
               "Message (français)"]


def on_bulletin(region: str, lang: str):
    """Script du bulletin + fichier audio (wolof, pulaar). Sereer : texte seulement."""
    b = bulletin.build(region or "Kaolack", lang, kb)
    langue = langues.get(lang)
    blocks = "".join(
        f'<div class="bl-sec"><h5>{html.escape(s.title)}</h5>'
        f'<p class="bl-local">« {html.escape(s.local.text if s.local else "")} »</p>'
        f'<p class="bl-fr">{html.escape(s.fr)}</p></div>' for s in b.sections)
    script = (f'<div class="mt-card bl-card"><div class="bl-head"><span>📻</span><div><h4>'
              f"Bulletin AgriBaat · {carte.label(b.region)}</h4><small>{b.made:%d/%m/%Y} · "
              f"{langue.label}</small></div></div>{blocks}"
              '<div class="draft">Phrases d’ouverture, de clôture et de météo en brouillon : '
              "à faire relire par un locuteur natif. Les phrases de prix sont déjà relues."
              "</div></div>")
    audio = None
    if VOICE_READY and langue.voice_out:
        path = bulletin.record(b)
        audio = str(path) if path else None
    return script, audio


def alerts_html() -> str:
    alerts = bulletin.current_alerts()
    if not alerts:
        return ('<div class="mt-card"><h4>✅ Aucune alerte en cours</h4><p>Les prévisions des '
                "7 prochains jours ne déclenchent aucune alerte.</p></div>")
    cards = "".join(
        f'<div class="al-reg"><b>{carte.label(a.region)}</b>'
        + "".join(f'<span title="{html.escape(x.text)}">{x.icon} {html.escape(x.title)}</span>'
                  for x in a.advices) + "</div>" for a in alerts)
    return (f'<div class="mt-card"><h4>🚨 {len(alerts)} région(s) en alerte</h4>'
            f'<div class="al-grid">{cards}</div><div class="src-note">Prévisions Open-Meteo, '
            "règles de conseil de la page Météo en direct.</div></div>")


def subscribers_table():
    rows = bulletin.subscribers()
    return pd.DataFrame([{"Nom": r["nom"], "Type": r["type"], "Région": carte.label(r["region"]),
                          "Langue": langues.get(r["langue"]).label, "Canal": r["canal"],
                          "Inscrit le": r["inscrit_le"]} for r in rows],
                        columns=["Nom", "Type", "Région", "Langue", "Canal", "Inscrit le"])


def sub_choices():
    return gr.Dropdown(choices=[(f"{r['nom']} · {carte.label(r['region'])}", i)
                                for i, r in enumerate(bulletin.subscribers())], value=None)


def on_subscribe(nom, kind, region, lang, canal, contact, consent):
    if not (nom or "").strip():
        gr.Warning("Indiquez un nom (personne, OP ou radio).")
    elif not consent:
        gr.Warning("L’accord de la personne est nécessaire pour l’inscrire.")
    else:
        bulletin.subscribe(nom, kind, region, lang, canal, contact or "")
        gr.Info(f"{nom.strip()} est inscrit(e) aux alertes.")
    return subscribers_table(), sub_choices()


def on_unsubscribe(index):
    if index is not None:
        bulletin.unsubscribe(int(index))
    return subscribers_table(), sub_choices()


def on_outbox():
    path, rows = bulletin.prepare_outbox()
    if not rows:
        return ('<div class="mt-card"><b>Aucun message à envoyer</b><p>Aucun abonné ne se trouve '
                "dans une région en alerte.</p></div>"), pd.DataFrame(columns=OUTBOX_COLS)
    note = (f'<div class="mt-card"><b>📤 {len(rows)} message(s) prêt(s)</b><p>Fichier : '
            f"<code>outputs/envois/{path.name}</code>. Envoi réel : à brancher sur un "
            "opérateur SMS / WhatsApp (Africa’s Talking, Twilio…) avec vos propres clés."
            "</p></div>")
    return note, pd.DataFrame(rows).rename(columns={
        "destinataire": "Destinataire", "canal": "Canal", "contact": "Contact",
        "region": "Région", "langue": "Langue", "message": "Message (langue locale)",
        "message_fr": "Message (français)"})


# ---------------------------------------------------------------- impact
PROFILES = ["Producteur", "Productrice", "Responsable d'OP", "Conseiller agricole", "Autre"]


def _pct(v) -> str:
    return "—" if v is None else f"{v:.0f} %"


def impact_view(scope: str):
    """(chiffres clés, graphiques, avant/après) pour « terrain » ou « tout »."""
    df = usage.load(field_only=scope == "terrain")
    s = usage.summary(df)
    who = "pendant les tests terrain" if scope == "terrain" else "depuis le début"
    if s["questions"] == 0:
        empty = (f'<div class="mt-card"><h4>Aucune question enregistrée {who}</h4><p>'
                 "Démarrez une session de test ci-dessous, puis faites poser des questions "
                 "dans l'Assistant vocal.</p></div>")
        return empty, "", impact_field()
    tiles = [
        ("❓", f"{s['questions']}", "questions posées"),
        ("👥", f"{s['participants']}", f"participants ({s['femmes']} femme(s))"),
        ("✅", _pct(s["trouve_pct"]), "réponses trouvées"),
        ("👍", _pct(s["compris_pct"]), f"réponses comprises ({s['avis']} avis)"),
        ("⏱️", "—" if s["temps_median"] is None
         else f"{s['temps_median']:.1f} s".replace(".", ","),
         "temps de réponse médian"),
        ("🗣️", _pct(s["local_pct"]), "en wolof, pulaar ou sereer"),
    ]
    kpis = '<div class="kpis">' + "".join(
        f'<div class="kpi"><div class="k">{k}</div><div class="v">{v}</div><div class="s">'
        f"{html.escape(sub)}</div></div>" for k, v, sub in tiles) + "</div>"
    by_lang = df["langue"].value_counts()
    by_topic = df["sujet"].value_counts()
    by_canal = df["canal"].value_counts()
    bars = ('<div class="imp-grid">'
            + hbars_html("Par langue", [(k, float(v)) for k, v in by_lang.items()], "")
            + hbars_html("Par sujet", [(k, float(v)) for k, v in by_topic.items()], "")
            + hbars_html("Par canal", [(k, float(v)) for k, v in by_canal.items()], "")
            + "</div>")
    days = df.assign(jour=df["horodatage"].str[:10]).groupby("jour").size()
    if len(days) >= 2:
        bars += area_chart([(pd.Timestamp(d).date(), float(n)) for d, n in days.items()],
                           title="Questions par jour", unit="questions",
                           source="Journal d'utilisation AgriBaat (anonyme)", yearly=False)
    return kpis, bars, impact_field()


def impact_field() -> str:
    """Avant / avec AgriBaat, d'après la feuille test_terrain/resultats_test_terrain.csv."""
    r = usage.field_results()
    if r is None:
        return ('<div class="mt-card imp-field"><h4>📋 Avant / avec AgriBaat</h4><p>Remplissez '
                "<code>test_terrain/resultats_test_terrain.csv</code> après chaque entretien "
                "(fiche d'entretien imprimable dans le même dossier) : la comparaison "
                "s'affichera ici.</p></div>")
    before = "—" if r["avant_min"] is None else f"{r['avant_min']:.0f} min"
    after = "—" if r["apres_min"] is None else f"{r['apres_min'] * 60:.0f} s"
    return (f'<div class="mt-card imp-field"><h4>📋 Avant / avec AgriBaat · {r["personnes"]} '
            "personne(s) interrogée(s)</h4><div class=\"imp-ba\"><div><small>Pour connaître un "
            f"prix aujourd'hui</small><b>{before}</b></div><div class=\"arrow\">→</div><div>"
            f"<small>Avec AgriBaat</small><b>{after}</b></div></div><div class=\"imp-row\">"
            f"<span>Question comprise du premier coup : <b>{_pct(r['premier_coup_pct'])}</b>"
            f"</span><span>Chiffre redit correctement : <b>{_pct(r['redit_pct'])}</b></span>"
            "</div><div class=\"src-note\">Valeurs médianes, d'après la feuille de résultats "
            "des tests terrain.</div></div>")


def on_session_start(code, profil, sexe, commune):
    code = (code or "").strip().upper()
    if not code:
        gr.Warning("Donnez un code de participant (P1, P2…), jamais son nom.")
        return None, session_banner(None)
    session = {"code": code, "profil": profil or "", "sexe": sexe or "", "commune": commune or ""}
    gr.Info(f"Session {code} démarrée : faites poser des questions dans l'Assistant vocal.")
    return session, session_banner(session)


def session_banner(session) -> str:
    if not session:
        return ('<div class="mode text">Aucune session de test en cours : les questions sont '
                "comptées comme utilisation de l'équipe.</div>")
    return (f'<div class="mode ok">Test terrain en cours · participant {html.escape(session["code"])}'
            f' · {html.escape(session["profil"])} — passez à l\'Assistant vocal.</div>')


def impact_export(scope: str):
    df = usage.load(field_only=scope == "terrain")
    path = usage.OUT / f"impact_{scope}_{pd.Timestamp.now():%Y-%m-%d_%H%M}.csv"
    df.to_csv(path, sep=";", index=False, encoding="utf-8-sig")
    return gr.File(value=str(path), visible=True)


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
    usage.log_question(canal="API", langue=langues.get(res.lang).label if langue != "fr"
                       else "Français", sujet=res.intent, trouve=res.found,
                       temps_s=res.timings.get("total", 0.0))
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
# Thème Gradio aligné sur le système de design (assets/agribaat.css).
THEME = gr.themes.Soft(
    primary_hue="green", secondary_hue="amber", neutral_hue="stone",
    radius_size=gr.themes.sizes.radius_lg,
    # Police intégrée à la page (assets/fonts) : identique même sans internet.
    font=[gr.themes.Font("Plus Jakarta Sans"), gr.themes.Font("system-ui"),
          gr.themes.Font("Segoe UI"), gr.themes.Font("sans-serif")],
).set(
    body_background_fill="#f7f2e8", body_text_color="#17231d",
    block_background_fill="#ffffff", block_border_color="#e7dfcf", block_radius="16px",
    block_label_text_color="#0e3b2c", block_title_text_color="#0e3b2c",
    input_background_fill="#ffffff", input_border_color="#e7dfcf",
    input_border_color_focus="#1e7b4f",
    button_primary_background_fill="#1e7b4f", button_primary_background_fill_hover="#0e3b2c",
    button_primary_text_color="#ffffff",
    checkbox_background_color_selected="#1e7b4f", checkbox_border_color_selected="#1e7b4f",
    color_accent="#1e7b4f", color_accent_soft="#eaf5ee",
    loader_color="#1e7b4f", slider_color="#1e7b4f",
)

# Thème clair imposé, comme la maquette : sans cela, un système en mode sombre
# (Ubuntu, Windows) affichait l'app en sombre et les cartes claires devenaient illisibles.
APP_JS = """
() => {
  const url = new URL(window.location);
  if (url.searchParams.get("__theme") !== "light") {
    url.searchParams.set("__theme", "light");
    window.location.replace(url.href);
    return;
  }
  // Menu latéral : chaque lien sélectionne l'onglet correspondant (caché).
  const sync = () => {
    const sel = document.querySelector('[role=tablist] button[aria-selected=true]');
    const name = sel ? sel.innerText : "";
    let label = "";
    document.querySelectorAll(".side-link").forEach(a => {
      const on = name.includes(a.dataset.tab);
      a.classList.toggle("active", on);
      if (on) label = a.innerText.trim();
    });
    const page = document.querySelector(".tb-page");
    if (page && label) page.textContent = label;
  };
  document.addEventListener("click", e => {
    // ☰ : ouvre le tiroir (téléphone) ou rouvre le menu replié (ordinateur).
    // ✕ : ferme le tiroir (téléphone) ou replie le menu (ordinateur).
    const wide = window.innerWidth > 900;
    if (e.target.closest(".nav-toggle")) {
      document.body.classList.toggle(wide ? "side-collapsed" : "nav-open");
      return;
    }
    if (e.target.closest(".side-close")) {
      document.body.classList.remove("nav-open");
      if (wide) document.body.classList.add("side-collapsed");
      return;
    }
    if (e.target.closest(".nav-scrim")) { document.body.classList.remove("nav-open"); return; }
    const a = e.target.closest(".side-link");
    if (!a) return;
    e.preventDefault();
    const btn = [...document.querySelectorAll("[role=tablist] button, .overflow-dropdown button")]
      .find(b => b.innerText.includes(a.dataset.tab));
    if (btn) btn.click();
    document.body.classList.remove("nav-open");
    window.scrollTo({top: 0, behavior: "smooth"});
    setTimeout(sync, 60);
  });
  setInterval(sync, 400);
}
"""

with gr.Blocks(title="AgriBaat", css=CSS, theme=THEME, js=APP_JS) as demo:
    gr.HTML(sidebar_html(), elem_id="sidenav-host")
    gr.HTML(topbar_html(), elem_id="topbar-host")
    history = gr.State([])
    test_session = gr.State(None)  # test terrain en cours : {"code", "profil", "sexe"}
    last_event = gr.State(None)  # identifiant de la dernière question (pour l'avis)

    with gr.Tab("🎙️ Assistant"):
        gr.HTML(hero_html())
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
                with gr.Row(elem_id="feedback-row"):
                    fb_yes = gr.Button("👍 J'ai compris", size="sm", variant="secondary")
                    fb_no = gr.Button("👎 Pas clair", size="sm", variant="secondary")
                with gr.Accordion("🔍 Ce que l'assistant a compris", open=False):
                    out_details = gr.Markdown()
                with gr.Accordion("🕘 Questions récentes", open=False):
                    out_hist = gr.Markdown(_history_md([]), elem_classes="hist")
        outputs = [out_card, out_audio, out_details, history, out_hist, last_event]
        fb_yes.click(lambda e: on_feedback(e, True), last_event, None)
        fb_no.click(lambda e: on_feedback(e, False), last_event, None)

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
        btn_voice.click(on_voice, [mic, lang, history, test_session], outputs)
        if VOICE_READY:
            # La question part dès qu'on arrête l'enregistrement ou qu'on importe un
            # fichier : plus besoin de penser à cliquer sur « Envoyer ».
            mic.stop_recording(on_voice, [mic, lang, history, test_session], outputs)
            mic.upload(on_voice, [mic, lang, history, test_session], outputs)
        btn_text.click(on_text, [txt, lang, history, test_session], outputs)
        txt.submit(on_text, [txt, lang, history, test_session], outputs)
        for i, button in enumerate(example_buttons):  # un clic pose la question
            button.click(lambda lg, h, s, i=i: on_example(i, lg, h, s),
                         [lang, history, test_session], outputs)

    with gr.Tab("🌤️ Météo en direct"):
        gr.HTML(page_head("🌤️", "Météo en direct",
                          "Prévisions à 7 jours pour chaque région et conseils pour les "
                          "cultures, lus en wolof et en pulaar."))
        with gr.Row(elem_classes="toolbar"):
            mt_region = gr.Dropdown(MAP_REGIONS, value="Kaolack", label="Région")
            mt_lang = gr.Radio(METEO_LANGS, value="wo", label="Langue du conseil",
                               elem_id="mt-lang")
            mt_refresh = gr.Button("🔄 Actualiser", variant="secondary", scale=0,
                                   min_width=130)
        with gr.Row(equal_height=False):
            with gr.Column(scale=3, min_width=320):
                mt_now = gr.HTML()
            with gr.Column(scale=2, min_width=280):
                mt_adv = gr.HTML()
                mt_local = gr.HTML()
                mt_listen = gr.Button("🔊 Écouter le conseil", variant="primary",
                                      visible=VOICE_READY)
                mt_audio = gr.Audio(label="Conseil lu", autoplay=True, visible=VOICE_READY)
        mt_nat = gr.HTML()
        mt_out = [mt_now, mt_adv, mt_local, mt_nat]
        mt_region.change(meteo_view, [mt_region, mt_lang], mt_out)
        mt_lang.change(meteo_view, [mt_region, mt_lang], mt_out)
        mt_refresh.click(lambda r, l: meteo_view(r, l, force=True), [mt_region, mt_lang], mt_out)
        mt_listen.click(meteo_listen, [mt_region, mt_lang], mt_audio)
        demo.load(meteo_view, [mt_region, mt_lang], mt_out)

    with gr.Tab("📻 Bulletins & alertes"):
        gr.HTML(page_head("📻", "Bulletins vocaux & alertes climat",
                          "Un bulletin audio par région et par langue, prêt à diffuser à la "
                          "radio ou sur WhatsApp, et des alertes préparées pour les abonnés."))
        with gr.Accordion("📻 Bulletin vocal de la semaine", open=True):
            with gr.Row(elem_classes="toolbar"):
                bl_region = gr.Dropdown(MAP_REGIONS, value="Kaolack", label="Région")
                bl_lang = gr.Radio(METEO_LANGS, value="wo", label="Langue")
                bl_go = gr.Button("🎙️ Générer le bulletin", variant="primary", scale=0,
                                  min_width=190)
            with gr.Row(equal_height=False):
                with gr.Column(scale=3, min_width=320):
                    bl_script = gr.HTML('<div class="mt-card"><p>Choisissez une région et une '
                                        "langue, puis « Générer le bulletin ». La lecture à "
                                        "voix haute peut prendre une à deux minutes.</p></div>")
                with gr.Column(scale=2, min_width=260):
                    bl_audio = gr.Audio(label="Bulletin audio (à télécharger et diffuser)",
                                        type="filepath", visible=VOICE_READY)
            bl_go.click(on_bulletin, [bl_region, bl_lang], [bl_script, bl_audio])
        with gr.Accordion("🚨 Alertes climat", open=True):
            al_now = gr.HTML()
            with gr.Row(equal_height=False):
                with gr.Column(scale=2, min_width=280):
                    gr.HTML('<div class="sn-sub">Inscrire un abonné</div>')
                    sub_name = gr.Textbox(label="Nom (personne, OP ou radio)")
                    sub_kind = gr.Dropdown(SUB_TYPES, value=SUB_TYPES[0], label="Type")
                    sub_region = gr.Dropdown(MAP_REGIONS, value="Kaolack", label="Région")
                    sub_lang = gr.Radio(METEO_LANGS, value="wo", label="Langue")
                    sub_canal = gr.Radio(SUB_CHANNELS, value="WhatsApp", label="Canal")
                    sub_contact = gr.Textbox(label="Contact (facultatif)",
                                             placeholder="numéro ou nom du groupe")
                    sub_ok = gr.Checkbox(label="La personne a donné son accord pour recevoir "
                                               "les alertes")
                    sub_btn = gr.Button("➕ Inscrire", variant="primary")
                with gr.Column(scale=3, min_width=320):
                    gr.HTML('<div class="sn-sub">Abonnés</div>')
                    sub_table = gr.Dataframe(interactive=False, max_height=280)
                    with gr.Row():
                        sub_pick = gr.Dropdown(label="Retirer un abonné", choices=[], scale=3)
                        sub_del = gr.Button("Retirer", variant="secondary", scale=1)
                    al_send = gr.Button("📤 Préparer les messages d’alerte", variant="primary")
                    al_note = gr.HTML()
                    al_outbox = gr.Dataframe(interactive=False, max_height=280, wrap=True)
            gr.HTML('<div class="src-note">Les abonnés sont enregistrés uniquement sur cet '
                    "ordinateur (outputs/abonnes.csv), avec leur accord. Rien n’est envoyé "
                    "automatiquement.</div>")
            sub_btn.click(on_subscribe, [sub_name, sub_kind, sub_region, sub_lang, sub_canal,
                                         sub_contact, sub_ok], [sub_table, sub_pick])
            sub_del.click(on_unsubscribe, sub_pick, [sub_table, sub_pick])
            al_send.click(on_outbox, None, [al_note, al_outbox])
        demo.load(lambda: (alerts_html(), subscribers_table(), sub_choices()), None,
                  [al_now, sub_table, sub_pick])

    with gr.Tab("📊 Impact"):
        gr.HTML(page_head("📊", "Impact & tests terrain",
                          "Ce que les utilisateurs demandent, ce qu'ils comprennent, et le "
                          "temps gagné. Journal anonyme : ni texte, ni voix, ni nom."))
        with gr.Accordion("🧪 Session de test terrain", open=True):
            with gr.Row(elem_classes="toolbar"):
                ts_code = gr.Textbox(label="Code du participant", placeholder="P1, P2…")
                ts_profil = gr.Dropdown(PROFILES, value=PROFILES[0], label="Profil")
                ts_sexe = gr.Radio(["Femme", "Homme"], label="Sexe (facultatif)")
                ts_commune = gr.Textbox(label="Commune (facultatif)")
            with gr.Row():
                ts_start = gr.Button("▶️ Démarrer la session", variant="primary")
                ts_stop = gr.Button("⏹️ Terminer la session", variant="secondary")
            ts_banner = gr.HTML(session_banner(None))
            ts_start.click(on_session_start, [ts_code, ts_profil, ts_sexe, ts_commune],
                           [test_session, ts_banner])
            ts_stop.click(lambda: (None, session_banner(None)), None, [test_session, ts_banner])
        with gr.Row(elem_classes="toolbar"):
            imp_scope = gr.Radio([("Tests terrain", "terrain"), ("Toute l'utilisation", "tout")],
                                 value="terrain", label="Afficher", elem_id="imp-scope")
            imp_refresh = gr.Button("🔄 Actualiser", variant="secondary", scale=0, min_width=130)
            imp_export = gr.Button("⬇️ Exporter (CSV)", variant="secondary", scale=0,
                                   min_width=150)
        imp_kpis = gr.HTML()
        imp_field = gr.HTML()
        imp_bars = gr.HTML()
        imp_file = gr.File(label="Export pour le dossier", visible=False)
        imp_out = [imp_kpis, imp_bars, imp_field]
        imp_scope.change(impact_view, imp_scope, imp_out)
        imp_refresh.click(impact_view, imp_scope, imp_out)
        imp_export.click(impact_export, imp_scope, imp_file)
        demo.load(impact_view, imp_scope, imp_out)

    with gr.Tab("🗺️ Climat & cultures"):
        gr.HTML(page_head("🗺️", "Quoi cultiver, et où ?",
                          "Zone climatique de chaque région et cultures où son rendement "
                          "dépasse la moyenne nationale. Survolez une région pour le détail."))
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
        gr.HTML(page_head("📈", "Prix des marchés",
                          f"Prix de détail relevés par le PAM sur {N_MARKETS} marchés : "
                          "tendance, marché le moins cher et le plus cher."))
        with gr.Row(elem_classes="toolbar"):
            dd_product = gr.Dropdown(PRICE_PRODUCTS, value="mil", label="Produit")
            dd_region = gr.Dropdown(PRICE_REGIONS, value=ALL, label="Région")
            dd_market = gr.Dropdown([("Tous les marchés", ALL)], value=ALL, label="Marché")
        kpis = gr.HTML()
        with gr.Row(equal_height=False):
            with gr.Column(scale=3, min_width=320):
                chart = gr.HTML()
            with gr.Column(scale=2, min_width=260):
                rank = gr.HTML()
        with gr.Accordion("Tableau complet : dernier prix de chaque marché", open=False):
            table = gr.Dataframe(interactive=False, max_height=360)
        price_filters = [dd_product, dd_region]
        price_out = [dd_market, kpis, chart, rank, table]
        for comp in price_filters:
            comp.change(on_price_filters, price_filters, price_out)
        dd_market.input(on_price_market, [dd_product, dd_region, dd_market], [kpis, chart])
        demo.load(on_price_filters, price_filters, price_out)

    with gr.Tab("🌱 Production"):
        gr.HTML(page_head("🌱", "Production agricole",
                          "Production, superficie et rendement : évolution nationale "
                          "(FAOSTAT) et comparaison des régions (DAPSA)."))
        with gr.Row(elem_classes="toolbar"):
            dd_sp = gr.Dropdown(STAT_PRODUCTS, value="arachide", label="Culture")
            dd_ind = gr.Dropdown(INDICATORS, value="production", label="Indicateur")
        stat_cards = gr.HTML()
        with gr.Row(equal_height=False):
            with gr.Column(scale=3, min_width=320):
                nat_chart = gr.HTML()
            with gr.Column(scale=2, min_width=260):
                reg_chart = gr.HTML()
        stat_inputs = [dd_sp, dd_ind]
        for comp in stat_inputs:
            comp.change(on_stats, stat_inputs, [stat_cards, nat_chart, reg_chart])
        demo.load(on_stats, stat_inputs, [stat_cards, nat_chart, reg_chart])

    if ADVICE_READY:
        with gr.Tab("🌦️ Conseils"):
            gr.HTML(page_head("🌦️", "Conseils de saison",
                              "Variétés du catalogue ouest-africain, pluies et "
                              "recommandations des bulletins de l'ANACIM."))
            with gr.Accordion("Variétés recommandées (inscrites au Sénégal)", open=True):
                with gr.Row(elem_classes="toolbar"):
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
            gr.HTML(page_head("🧪", "Labo langues",
                              "Modèles publics de reconnaissance et de synthèse vocale pour "
                              "les autres langues du projet. Phase expérimentale."))
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
        gr.HTML(page_head("ℹ️", "À propos d'AgriBaat",
                          "Sources officielles, fonctionnement et limites connues."))
        gr.HTML(ABOUT_HTML)

    # API JSON : POST /gradio_api/call/demander, ou gradio_client (voir README).
    gr.api(api_demander, api_name="demander")

if __name__ == "__main__":
    # pwa : sur téléphone, « Ajouter à l'écran d'accueil » installe AgriBaat comme une appli.
    demo.launch(pwa=True)
