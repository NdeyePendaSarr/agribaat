"""Interface AgriBaat (Gradio). Lancement : python app.py  ->  http://127.0.0.1:7860"""

from __future__ import annotations

import html
import importlib.util

import gradio as gr
import pandas as pd

import config
from agribaat.answers import fmt_month, fmt_number, place
from agribaat.knowledge import KnowledgeBase
from agribaat.lexicon import PRODUCT_BY_KEY, PRODUCTS
from agribaat.pipeline import Assistant, Result

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

EXAMPLES = [
    ("Quel est le prix du mil à Kaolack ?", "Français"),
    ("Combien coûte le riz ?", "Français"),
    ("Quelle a été la production d'arachide en 2024 ?", "Français"),
    ("Rendement du mil dans la région de Kaffrine", "Français"),
    ("njëg dugub ci Kaolack", "Wolof"),
]

CSS = """
.gradio-container {max-width: 1180px !important; margin: auto;}
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
"""


# ---------------------------------------------------------------- en-tête
def hero_html() -> str:
    chips = [f"{N_MARKETS} marchés suivis", f"Dernier relevé : {fmt_month(LAST_DATE)}",
             f"Statistiques {YEARS_FAO[0]}–{YEARS_FAO[1]}", "Sources : PAM · FAOSTAT · DAPSA"]
    return ('<div id="hero"><h1>🌾 AgriBaat</h1>'
            '<p class="tag">Assistant agricole vocal en wolof — prix des marchés, '
            'production et rendements, chiffres sourcés</p><div class="chips">'
            + "".join(f'<span class="chip">{c}</span>' for c in chips) + "</div></div>")


def mode_html() -> str:
    if VOICE_READY:
        return ('<div class="mode ok">🎙️ Mode vocal disponible : parlez en wolof, '
                "la réponse est lue à voix haute.</div>")
    return ('<div class="mode text">⌨️ Mode texte : les modèles vocaux ne sont pas installés '
            "(torch, transformers). Les questions écrites en français fonctionnent ; "
            "voir le README pour activer la voix.</div>")


# ---------------------------------------------------------------- assistant
EMPTY_CARD = ('<div class="card"><div class="lbl">Réponse</div>'
              '<div class="empty">Posez une question à voix haute ou par écrit : '
              "la réponse s'affichera ici.</div></div>")


def answer_card(res: Result) -> str:
    esc = html.escape
    parts = ['<div class="card">']
    if res.answer_wo:
        parts.append(f'<div class="lbl">Wolof</div><div class="wo">{esc(res.answer_wo)}</div>')
    parts.append(f'<div class="lbl">Français</div><div class="fr">{esc(res.answer_fr)}</div>')
    badges = []
    if res.source:
        badges.append(f'<span class="badge src">📊 {esc(res.source)}</span>')
    elif not res.found:
        badges.append('<span class="badge miss">Aucune donnée trouvée</span>')
    if "total" in res.timings:
        badges.append(f'<span class="badge">⏱ {res.timings["total"]} s</span>')
    parts.append(f'<div class="badges">{"".join(badges)}</div>')
    if res.warnings and VOICE_READY:  # en mode texte, le bandeau suffit
        parts.append('<div class="warn">' + "<br>".join(esc(w) for w in res.warnings) + "</div>")
    parts.append("</div>")
    return "".join(parts)


def _details(res: Result) -> str:
    lines = [f"**Question (wolof) :** {res.question_wo or '—'}",
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


def _render(res: Result, history: list):
    question = res.question_fr or res.question_wo
    if question:
        history = [(question, res.answer_fr)] + history[:9]
    return answer_card(res), res.audio, _details(res), history, _history_md(history)


def on_voice(audio, history):
    if audio is None:
        raise gr.Error("Enregistrez ou importez d'abord une question.")
    sr, data = audio
    return _render(assistant.ask_audio(sr, data), history)


def on_text(text: str, lang: str, history):
    if not text or not text.strip():
        raise gr.Error("Tapez une question.")
    return _render(assistant.ask_text(text, "wo" if lang == "Wolof" else "fr"), history)


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
    return df[["year", "value"]].sort_values("year")


def regional_bars(product: str, indicator: str) -> tuple[pd.DataFrame, str]:
    df = kb.regional[(kb.regional["product"] == product)
                     & (kb.regional["indicator"] == indicator)
                     & (kb.regional["department"] == "Total")
                     & (kb.regional["region"] != "Senegal")]
    if df.empty:
        return pd.DataFrame(columns=["region", "value"]), "Pas de données régionales DAPSA."
    year = int(df["year"].max())
    cur = df[df["year"] == year].sort_values("value", ascending=False)
    out = pd.DataFrame({"region": cur["region"].map(place), "value": cur["value"].round(0)})
    return out, f"Par région, campagne {year} (DAPSA)"


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
        cards.append(("Record", f"{fmt_number(best['value'])} {unit}", f"en {int(best['year'])}"))
    return '<div class="kpis">' + "".join(
        f'<div class="kpi"><div class="k">{k}</div><div class="v">{v}</div>'
        f'<div class="s">{s}</div></div>' for k, v, s in cards) + "</div>"


def on_stats(product: str, indicator: str):
    bars, title = regional_bars(product, indicator)
    return (stat_kpis(product, indicator), national_series(product, indicator),
            gr.BarPlot(value=bars, title=title))


# ---------------------------------------------------------------- interface
THEME = gr.themes.Soft(primary_hue="green", secondary_hue="amber",
                       font=[gr.themes.GoogleFont("Inter"), "sans-serif"])

with gr.Blocks(title="AgriBaat", css=CSS, theme=THEME) as demo:
    gr.HTML(hero_html())
    history = gr.State([])

    with gr.Tab("🎙️ Assistant"):
        gr.HTML(mode_html())
        with gr.Row(equal_height=False):
            with gr.Column(scale=5):
                with gr.Group():
                    mic = gr.Audio(sources=["microphone", "upload"], type="numpy",
                                   label="Posez votre question en wolof")
                    btn_voice = gr.Button("🎙️ Envoyer la question vocale", variant="primary",
                                          elem_id="ask-voice", interactive=VOICE_READY)
                with gr.Group():
                    txt = gr.Textbox(placeholder="Ex. : Quel est le prix du mil à Kaolack ?",
                                     label="Ou tapez votre question", lines=2)
                    with gr.Row():
                        lang = gr.Radio(["Français", "Wolof"], value="Français",
                                        show_label=False, scale=3)
                        btn_text = gr.Button("Envoyer", variant="secondary", scale=1)
                examples = gr.Examples([list(e) for e in EXAMPLES], inputs=[txt, lang],
                                       label="Questions types (cliquez pour poser)")
            with gr.Column(scale=6):
                out_card = gr.HTML(EMPTY_CARD)
                out_audio = gr.Audio(label="Réponse vocale (wolof)", autoplay=True,
                                     visible=VOICE_READY)
                with gr.Accordion("Ce que l'assistant a compris", open=False):
                    out_details = gr.Markdown()
                with gr.Accordion("Questions récentes", open=False):
                    out_hist = gr.Markdown(_history_md([]), elem_classes="hist")
        outputs = [out_card, out_audio, out_details, history, out_hist]
        btn_voice.click(on_voice, [mic, history], outputs)
        btn_text.click(on_text, [txt, lang, history], outputs)
        txt.submit(on_text, [txt, lang, history], outputs)
        # Un clic sur une question type la pose directement.
        examples.load_input_event.then(on_text, [txt, lang, history], outputs)

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
                                    y_title=" ", title="Sénégal — FAOSTAT", scale=3)
            reg_chart = gr.BarPlot(x="region", y="value", height=340, x_title=" ", y_title=" ",
                                   sort="-y", scale=2)
        stat_inputs = [dd_sp, dd_ind]
        for comp in stat_inputs:
            comp.change(on_stats, stat_inputs, [stat_cards, nat_chart, reg_chart])
        demo.load(on_stats, stat_inputs, [stat_cards, nat_chart, reg_chart])

    with gr.Tab("ℹ️ À propos"):
        gr.Markdown("""
### Sources des données
| Donnée | Source | Période |
|---|---|---|
| Prix de détail par marché | PAM / WFP (HDX) | 2000 – 2026 |
| Production, superficie, rendement nationaux | FAOSTAT | 1961 – 2024 |
| Production par région et département | DAPSA, enquête agricole annuelle | 2017 – 2022 |

### Comment ça marche
Voix wolof → **ASR** (wav2vec2 MMS wolof) → **traduction** (NLLB-200) →
**réponse construite à partir des données** (aucun chiffre inventé) →
**traduction** en wolof → **synthèse vocale** (SpeechT5 wolof).

### Limites connues
- Les réponses en wolof sont des traductions automatiques : à faire relire.
- Les chiffres lus par la synthèse vocale peuvent être mal prononcés.
- Questions couvertes : prix, production, superficie, rendement.

*Équipe SMART AGRO — PAS Challenge 2026.*
""")

if __name__ == "__main__":
    demo.launch()
