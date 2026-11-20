"""Construction des réponses en français, courtes, chiffrées et sourcées.

Règle : chaque chiffre vient d'une table. Si la donnée manque, on le dit.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass

from . import wolof as wo
from .knowledge import KnowledgeBase, PriceFact, StatFact, decade_end
from .lexicon import MONTHS_FR, PRODUCT_BY_KEY
from .nlu import Query

INDICATOR_LABELS = {"production": "la production", "superficie": "la superficie cultivée",
                    "rendement": "le rendement"}

HELP_TEXT = ("Je peux vous donner le prix d'un produit sur un marché, ou la production, "
             "la superficie et le rendement d'une culture. Par exemple : "
             "« Quel est le prix du mil à Kaolack ? »")
WELCOME_TEXT = ("Bonjour ! Je suis AgriBaat. " + HELP_TEXT.removesuffix(
    "Par exemple : « Quel est le prix du mil à Kaolack ? »")
    + "Je connais aussi les pluies (ANACIM), les variétés recommandées et les conseils "
    "de saison. Par exemple : « Quel est le prix du mil à Kaolack ? »")


@dataclass
class Answer:
    text: str  # réponse en français
    source: str | None  # source des chiffres
    found: bool  # False si aucune donnée
    wolof: wo.WolofText | None = None  # même réponse en langue locale (écran + oral)
    highlight: Highlight | None = None  # chiffre clé, pour la carte « chiffre vérifié »


@dataclass
class Highlight:
    """Chiffre clé d'une réponse (mêmes données que la phrase, rien d'autre)."""

    label: str  # « Prix du mil · marché de Kaolack »
    value: str  # « 300 »
    unit: str  # « FCFA/kg »
    sub: str = ""  # « Relevé d'octobre 2026 · 30 marchés »
    delta: float | None = None  # variation sur un an, en %
    icon: str = "🌾"


ICONS = {"mil": "🌾", "sorgho": "🌾", "mais": "🌽", "riz": "🍚", "arachide": "🥜",
         "niebe": "🫘", "oignon": "🧅", "manioc": "🍠", "fonio": "🌾"}


def _price_highlight(fact: PriceFact, q: Query) -> Highlight:
    label = PRODUCT_BY_KEY[fact.product].label
    if fact.market:
        where = f"marché de {place(fact.market)}"
    else:
        where = f"moyenne, région de {place(q.region)}" if q.region else "moyenne nationale"
    if fact.variants:  # plusieurs variantes : on n'en fait pas la moyenne
        values = sorted(fact.variants.values())
        value = f"{fmt_number(values[0])}–{fmt_number(values[-1])}"
        sub = " · ".join(f"{VARIANT_FR.get(n, n)} {fmt_number(v)}"
                         for n, v in sorted(fact.variants.items(), key=lambda kv: kv[1]))
    else:
        value, sub = fmt_number(fact.price), ""
    if not fact.market:
        sub = (sub + " · " if sub else "") + f"{fact.n_markets} marchés suivis"
    delta = None
    if fact.price_year_before and not fact.variants:
        delta = (fact.price - fact.price_year_before) / fact.price_year_before * 100
    return Highlight(f"Prix du {label} · {where}", value, "FCFA/kg",
                     f"Relevé {de(fmt_month(fact.date))}" + (f" · {sub}" if sub else ""),
                     delta, ICONS.get(fact.product, "🌾"))


def _stat_highlight(fact: StatFact, kb: KnowledgeBase) -> Highlight:
    label = PRODUCT_BY_KEY[fact.product].label
    unit = {"t": "tonnes", "ha": "hectares", "kg/ha": "kg/ha"}[fact.unit]
    title = {"production": "Production", "superficie": "Superficie",
             "rendement": "Rendement"}[fact.indicator]
    delta = None
    if fact.scope == "Sénégal":
        prev = kb.stat(fact.product, fact.indicator, year=fact.year - 1)
        if prev is not None and not prev.requested_year and prev.value:
            delta = (fact.value - prev.value) / prev.value * 100
    return Highlight(f"{title} {de(label)} · {fact.scope}", fmt_number(fact.value), unit,
                     f"Campagne {fact.year}", delta, ICONS.get(fact.product, "🌾"))


def fmt_number(value: float, decimals: int = 0) -> str:
    """12345.6 -> '12 346' (séparateur de milliers à la française)."""
    return f"{value:,.{decimals}f}".replace(",", " ")


def fmt_month(ts) -> str:
    return f"{MONTHS_FR[ts.month - 1]} {ts.year}"


DISPLAY_NAMES = {"Zigiunchor": "Ziguinchor", "Thies": "Thiès", "Kedougou": "Kédougou",
                 "Sedhiou": "Sédhiou", "Saint Louis": "Saint-Louis"}  # corrige les fautes du fichier source


def place(name: str | None) -> str:
    return DISPLAY_NAMES.get(name or "", name or "")


def de(label: str) -> str:
    """'mil' -> 'de mil' ; 'arachide' -> "d'arachide" (élision)."""
    return f"d'{label}" if label[:1] in "aeiouyéèh" else f"de {label}"


VARIANT_FR = {
    "Maize (local)": "local", "Maize (imported)": "importé",
    "Rice (local)": "local", "Rice (imported)": "importé",
    "Groundnuts (shelled)": "décortiquée", "Groundnuts (unshelled)": "en coque",
    "Onions (dry)": "local", "Onions (imported)": "importé",
}


def _price_value(fact: PriceFact) -> str:
    """'300 FCFA' ou, s'il y a plusieurs variantes, '333 FCFA (importé) et 396 FCFA (local)'.
    On ne fait pas la moyenne de variantes différentes (ex. arachide décortiquée / en coque)."""
    if not fact.variants:
        return f"{fmt_number(fact.price)} FCFA"
    parts = [f"{fmt_number(v)} FCFA ({VARIANT_FR.get(name, name)})"
             for name, v in sorted(fact.variants.items(), key=lambda kv: kv[1])]
    return ", ".join(parts[:-1]) + " et " + parts[-1]


def _price_answer(fact: PriceFact, q: Query, latest=None) -> str:
    label = PRODUCT_BY_KEY[fact.product].label
    when = fmt_month(fact.date)
    if fact.market:
        text = (f"Au marché de {place(fact.market)}, le kilo {de(label)} coûtait "
                f"{_price_value(fact)} en {when}.")
    else:
        where = f"dans la région de {place(q.region)}" if q.region else "au Sénégal"
        text = (f"En {when}, le kilo {de(label)} coûtait en moyenne "
                f"{_price_value(fact)} {where} ({fact.n_markets} marchés suivis).")
        if fact.min_market and fact.max_market and not fact.variants:
            text += (f" Le moins cher : {place(fact.min_market)} ({fmt_number(fact.min_price)} FCFA) ;"
                     f" le plus cher : {place(fact.max_market)} ({fmt_number(fact.max_price)} FCFA).")
    if fact.price_year_before and not fact.variants:
        change = (fact.price - fact.price_year_before) / fact.price_year_before * 100
        if abs(change) >= 1:
            sens = "plus" if change > 0 else "moins"
            text += f" C'est {fmt_number(abs(change))} % de {sens} qu'un an plus tôt."
    if latest is not None and (latest - fact.date).days > 365:
        text += " Attention : c'est le dernier relevé disponible pour ce marché."
    return text


def _stat_answer(fact: StatFact) -> str:
    label = PRODUCT_BY_KEY[fact.product].label
    unit = {"t": "tonnes", "ha": "hectares", "kg/ha": "kg par hectare"}[fact.unit]
    text = ""
    if fact.requested_year:
        text = (f"Je n'ai pas de chiffre pour {fact.requested_year}. "
                f"La donnée la plus proche disponible est celle de {fact.year}. ")
    scope = "au Sénégal" if fact.scope == "Sénégal" else f"dans le {fact.scope}" \
        if fact.scope.startswith("département") else f"dans la {fact.scope}"
    text += (f"En {fact.year}, {INDICATOR_LABELS[fact.indicator]} {de(label)} {scope} "
             f"était d'environ {fmt_number(fact.value)} {unit}.")
    return text


# ---------------------------------------------------------------- wolof
# Mêmes faits, mêmes chiffres, phrase construite directement en wolof (voir wolof.py).
def _price_wolof(fact: PriceFact, q: Query, latest=None) -> wo.WolofText:
    product = wo.L().PRODUCTS_WO[fact.product]
    price = wo.price_variants(fact.variants) if fact.variants else wo.Qty(fact.price, "fcfa")
    if fact.market:
        out = wo.render("prix_marche", mois=wo.month(fact.date), produit=product, prix=price,
                        lieu=wo.place("marche", place(fact.market)))
    else:
        where = wo.place("region", place(q.region)) if q.region else wo.place("pays")
        out = wo.render("prix_moyen", mois=wo.month(fact.date), produit=product, prix=price,
                        lieu=where, n=wo.Qty(fact.n_markets))
        if fact.min_market and fact.max_market and not fact.variants:
            out += wo.render("extremes", lieu_min=place(fact.min_market),
                             prix_min=wo.Qty(fact.min_price, "fcfa"),
                             lieu_max=place(fact.max_market),
                             prix_max=wo.Qty(fact.max_price, "fcfa"))
    if fact.price_year_before and not fact.variants:
        change = (fact.price - fact.price_year_before) / fact.price_year_before * 100
        if abs(change) >= 1:
            out += wo.render("hausse" if change > 0 else "baisse", pct=wo.Qty(abs(change), "pct"))
    if latest is not None and (latest - fact.date).days > 365:
        out += wo.render("ancien")
    return out


def _stat_wolof(fact: StatFact) -> wo.WolofText:
    if fact.scope == "Sénégal":
        where = wo.place("pays")
    elif fact.scope.startswith("département de "):
        where = wo.place("departement", place(fact.scope.removeprefix("département de ")))
    else:
        where = wo.place("region", place(fact.scope.removeprefix("région de ")))
    out = wo.WolofText("", "")
    if fact.requested_year:
        out += wo.render("annee_sans_stat", annee=wo.year(fact.requested_year),
                         annee_dispo=wo.year(fact.year))
    return out + wo.render(fact.indicator, annee=wo.year(fact.year),
                           produit=wo.L().PRODUCTS_WO[fact.product], lieu=where,
                           valeur=wo.Qty(fact.value, fact.unit))


# ---------------------------------------------------------------- conseils
CATALOGUE = "Catalogue ouest-africain des espèces et variétés végétales"
CROPS_WITH_VARIETIES = "mil, sorgho, arachide et niébé"
TOPIC_FR = {"semis": "les semis", "recolte": "la récolte", "ravageurs": "les ravageurs",
            "previsions": "la météo", "elevage": "l'élevage", "eau": "l'eau"}


def fmt_period(start, end) -> str:
    """« du 21 au 31 août 2026 »."""
    first = "1er" if start.day == 1 else str(start.day)
    return f"du {first} au {end.day} {MONTHS_FR[end.month - 1]} {end.year}"


def _range(lo: float, hi: float) -> str:
    return f"{lo:g}" if lo == hi else f"{lo:g} à {hi:g}"


def _variety_answer(q: Query, kb: KnowledgeBase) -> Answer:
    if q.product is None:
        found = _search_answer(q, kb)  # ex. « nouvelles variétés de blé » : extrait cité
        if found is not None:
            return found
        return Answer(f"Précisez la culture : je connais les variétés de "
                      f"{CROPS_WITH_VARIETIES}.", None, False,
                      wo.render("variete_sans_produit"))
    label = PRODUCT_BY_KEY[q.product].label
    precision = {"court": " à cycle court", "long": " à cycle long"}.get(q.cycle, "")
    precision += " tolérantes à la sécheresse" if q.drought else ""
    precision_wo = wo.L().CYCLE_WO.get(q.cycle, "") + (wo.L().DROUGHT_WO if q.drought else "")
    product_wo = wo.L().PRODUCTS_WO[q.product]
    rows = kb.variety_list(q.product, cycle=q.cycle, drought=q.drought)
    if rows.empty:
        return Answer(f"Je n'ai pas de variété {de(label)}{precision} dans le catalogue "
                      f"(cultures couvertes : {CROPS_WITH_VARIETIES}).", None, False,
                      wo.render("pas_de_variete", produit=product_wo, precision=precision_wo))
    items_fr, items_wo = [], []
    for r in rows.itertuples():
        kg = r.rendement_max * 1000
        items_fr.append(f"{r.variete} ({_range(r.cycle_min, r.cycle_max)} jours, "
                        f"jusqu'à {fmt_number(kg)} kg/ha)")
        cycle = (wo.Seq((wo.word("days"), wo.Qty(r.cycle_min, exact=True)))
                 if r.cycle_min == r.cycle_max else
                 wo.Seq((wo.word("days"), wo.Qty(r.cycle_min, exact=True), wo.word("to"),
                         wo.Qty(r.cycle_max, exact=True))))
        items_wo.append(wo.Seq((wo.Name(r.variete), " (", cycle, wo.word("up_to"),
                                wo.Qty(kg, "kg"), wo.word("per_ha"))))
    text = (f"D'après le {CATALOGUE}, voici des variétés {de(label)} inscrites au Sénégal"
            f"{precision} : " + ", ".join(items_fr) + ".")
    best = rows.iloc[0]
    hl = Highlight(f"Variété {de(label)}{precision}", str(best["variete"]),
                   f"· {_range(best['cycle_min'], best['cycle_max'])} jours",
                   f"Jusqu'à {fmt_number(best['rendement_max'] * 1000)} kg/ha"
                   + (f" · {len(rows) - 1} autre(s) ci-dessous" if len(rows) > 1 else ""),
                   None, "🌱")
    return Answer(text, f"{CATALOGUE} (CEDEAO)", True,
                  wo.render("varietes", produit=product_wo, precision=precision_wo,
                            liste=wo.join_list(items_wo)), hl)


def _rain_answer(q: Query, kb: KnowledgeBase) -> Answer:
    target = q.locality or q.region or q.market
    fact = kb.rainfall(target)
    if fact is None:
        where = place(target) if target else "le Sénégal"
        return Answer(f"Je n'ai pas de relevé de pluie pour {where}.", None, False,
                      wo.render("pas_de_pluie", lieu=place(target) if target else wo.word("senegal")))
    when = fmt_period(fact.start, fact.end)
    period_wo = wo.period(fact.start, fact.end)
    if len(fact.values) == 1:
        loc, mm = fact.values[0]
        text = f"Selon l'ANACIM, il est tombé {fmt_number(mm)} mm à {place(loc)} {when.replace('du', 'pendant la décade du', 1)}."
        out = wo.render("pluie_lieu", periode=period_wo, lieu=place(loc), mm=wo.Qty(mm, "mm"))
    else:
        (lo_loc, lo), (hi_loc, hi) = fact.values[0], fact.values[-1]
        zone = f"dans la région de {place(fact.place)}" if fact.kind == "region" else "au Sénégal"
        zone_wo = (wo.place("region", place(fact.place)) if fact.kind == "region"
                   else wo.place("pays"))
        text = (f"Selon l'ANACIM, pendant la décade {when}, {zone}, les relevés vont de "
                f"{fmt_number(lo)} mm ({place(lo_loc)}) à {fmt_number(hi)} mm ({place(hi_loc)}).")
        out = wo.render("pluie_zone", periode=period_wo, zone=zone_wo,
                        mm_min=wo.Qty(lo, "mm"), lieu_min=place(lo_loc),
                        mm_max=wo.Qty(hi, "mm"), lieu_max=place(hi_loc))
    text += (" Ce sont les derniers chiffres disponibles : les bulletins couvrent la saison "
             "des pluies (juin à octobre).")
    out += wo.render("pluie_ancienne")
    if len(fact.values) == 1:
        hl = Highlight(f"Pluie · {place(fact.values[0][0])}", fmt_number(fact.values[0][1]),
                       "mm", f"Décade {when}", None, "🌧️")
    else:
        hl = Highlight(f"Pluie · {zone.replace('dans la ', '').replace('au ', '')}",
                       f"{fmt_number(lo)}–{fmt_number(hi)}", "mm",
                       f"Décade {when} · {len(fact.values)} relevés", None, "🌧️")
    return Answer(text, f"ANACIM, bulletin agrométéorologique décadaire ({when})", True,
                  out, hl)


def _topic_of(text: str) -> str:
    from .knowledge import TOPICS
    from .lexicon import normalize

    norm = normalize(text)
    return next((t for t, pattern in TOPICS.items() if re.search(pattern, norm)), "autre")


def _advice_answer(q: Query, kb: KnowledgeBase) -> Answer:
    words = PRODUCT_BY_KEY[q.product].fr if q.product else ()
    fact = kb.advice_for(words, q.topic)
    if fact is None:
        return Answer("Je n'ai pas de recommandation disponible.", None, False,
                      wo.render("pas_de_stat", produit=wo.word("advice")))
    when = fmt_period(fact.start, fact.end)
    asked = " et ".join(x for x in (
        f"{TOPIC_FR[q.topic]}" if q.topic else "",
        f"le {PRODUCT_BY_KEY[q.product].label}" if q.product else "") if x)
    prefix, prefix_wo = "", wo.WolofText("", "")
    if asked and not fact.matched:
        prefix = f"Je n'ai pas de recommandation sur {asked}. Voici les plus proches. "
        sujet = THEMES_OR_PRODUCT_WO(q)
        prefix_wo = wo.render("conseils_sans_sujet", sujet=sujet)
    if len(set(fact.dates)) > 1:  # plusieurs bulletins : chaque conseil garde sa date
        items = " ; ".join(f"{i}) {item} ({fmt_period(d, decade_end(d))})"
                           for i, (item, d) in enumerate(zip(fact.items, fact.dates), 1))
        text = prefix + f"Recommandations de l'ANACIM : {items}."
    else:
        items = " ; ".join(f"{i}) {item}" for i, item in enumerate(fact.items, 1))
        text = prefix + f"Recommandations de l'ANACIM (décade {when}) : {items}."
    themes = []
    for item in fact.items:
        theme = wo.L().THEMES_WO[_topic_of(item)]
        if theme not in themes:
            themes.append(theme)
    if len(set(fact.dates)) > 1:
        out = prefix_wo + wo.render("conseils_plusieurs", n=wo.Qty(len(fact.items)),
                                    themes=wo.join_list(themes))
    else:
        out = prefix_wo + wo.render("conseils", periode=wo.period(fact.start, fact.end),
                                    n=wo.Qty(len(fact.items)), themes=wo.join_list(themes))
    return Answer(text, f"ANACIM, bulletin agrométéorologique décadaire ({when})", True, out)


def THEMES_OR_PRODUCT_WO(q: Query) -> str:  # noqa: N802 — petite aide de formulation
    parts = []
    if q.topic:
        parts.append(wo.L().THEMES_WO[q.topic])
    if q.product:
        parts.append(wo.L().PRODUCTS_WO[q.product])
    return wo.word("and").join(parts) or wo.word("this")


def _excerpt(passage_text: str, question: str, idf: dict[str, float] | None = None,
             size: int = 70) -> str:
    """Les `size` mots du passage les plus proches de la question (plutôt que son
    début, souvent sans rapport). Les mots rares (« striga ») comptent plus que les
    mots courants (« lutter »)."""
    from .search import tokens

    words = passage_text.split()
    if len(words) <= size:
        return passage_text
    wanted = set(tokens(question))
    idf = idf or {}
    hits = [sum(idf.get(t, 1.0) for t in set(tokens(w)) & wanted) for w in words]
    best = max(range(0, len(words) - size + 1, 5), key=lambda i: sum(hits[i:i + size]))
    out = " ".join(words[best:best + size])
    return ("… " if best else "") + out + (" …" if best + size < len(words) else "")


def _search_answer(q: Query, kb: KnowledgeBase) -> Answer | None:
    passage = kb.search(q.text) if q.text else None
    asked = q.text
    if passage is None and q.focus and len(q.focus.split()) >= 2:
        passage, asked = kb.search(q.focus), q.focus  # sens reconnu seulement
    if passage is None:
        return None
    excerpt = _excerpt(passage.text, asked, getattr(kb._search, "idf", None))
    text = (f"Je n'ai pas de réponse chiffrée, mais voici un extrait de « {passage.source} » : "
            f"« {excerpt} »")
    return Answer(text, f"{passage.source} (extrait)", True,
                  wo.render("extrait", source=wo.Name(passage.source)))


def _meteo_region(q: Query, kb: KnowledgeBase) -> str | None:
    """Région de la question (région, marché ou localité citée), pour les prévisions."""
    from . import meteo

    if q.region in meteo.CITIES:
        return q.region
    if q.market:
        rows = kb.prices[kb.prices["market"] == q.market]["region"]
        if len(rows) and rows.iloc[0] in meteo.CITIES:
            return rows.iloc[0]
    if q.locality and not kb.rain.empty:
        rows = kb.rain[kb.rain["localite"] == q.locality]["region"].dropna()
        if len(rows) and rows.iloc[0] in meteo.CITIES:
            return rows.iloc[0]
    return None


def _meteo_answer(q: Query, kb: KnowledgeBase) -> Answer:
    """Prévisions en temps réel (Open-Meteo) et conseils, dans la langue choisie."""
    from . import meteo
    from .carte import label

    region = _meteo_region(q, kb)
    if region is None:  # pas de lieu : la région où il pleuvra le plus (sinon la plus chaude)
        every = meteo.all_forecasts()
        if every:
            region = max(every, key=lambda r: (every[r].rain7, every[r].tmax7))
    fc = meteo.forecast(region) if region else None
    if fc is None:
        return Answer("Je n'ai pas pu récupérer les prévisions météo (pas de connexion à "
                      "Open-Meteo).", None, False,
                      wo.render("pas_de_pluie", lieu=place(region) if region else
                                wo.word("senegal")))
    advices = meteo.advice(fc)
    text = meteo.summary_fr(fc)
    if not fc.live:
        text += f" (Hors ligne : prévisions du {fc.fetched:%d/%m à %H:%M}.)"
    sky = "🌧️" if fc.rain7 >= 1 else "☀️"
    hl = Highlight(f"Météo · {label(fc.region)} · 7 jours", f"{fc.tmax7:.0f}", "°C max",
                   f"{fc.rain7:.0f} mm de pluie prévus · {fc.days[0].day:%d/%m}–"
                   f"{fc.days[-1].day:%d/%m}", None, sky)
    return Answer(text, f"Open-Meteo (prévisions du {fc.fetched:%d/%m à %H:%M})", True,
                  meteo.local_text(fc, advices, wo.L()), hl)


def _product_sheet(q: Query, kb: KnowledgeBase) -> Answer | None:
    """Culture reconnue, mais pas le reste de la question (formulation inconnue) :
    plutôt que deviner, on donne l'essentiel sur cette culture — dernier prix moyen et
    production nationale —, avec les phrases déjà relues dans chaque langue."""
    price = kb.price(q.product, region=q.region)
    stat = kb.stat(q.product, "production", region=q.region)
    if price is None and stat is None:
        return None
    texts, local, sources = [], wo.WolofText("", ""), []
    if price is not None:
        latest = kb.prices["date"].max()
        texts.append(_price_answer(price, q, latest=latest))
        local = local + _price_wolof(price, q, latest=latest)
        sources.append("PAM / WFP (prix de détail)")
    if stat is not None:
        texts.append(_stat_answer(stat))
        local = local + wo.WolofText(" ", " ") + _stat_wolof(stat) if price is not None \
            else _stat_wolof(stat)
        sources.append(stat.source)
    label = PRODUCT_BY_KEY[q.product].label
    text = f"Voici l'essentiel sur le {label}. " + " ".join(texts)
    hl = _price_highlight(price, q) if price is not None else _stat_highlight(stat, kb)
    return Answer(text, " ; ".join(sources), True, local, hl)


def _technique_answer(q: Query, kb: KnowledgeBase) -> Answer:
    """Pratique agricole (engrais, conservation, lutte…) : extrait des documents ISRA,
    sinon recommandations ANACIM sur les ravageurs, sinon aveu d'ignorance."""
    found = _search_answer(q, kb)
    if found is not None:
        return found
    if q.topic or q.product:
        # Pas de document précis : recommandations datées de l'ANACIM sur ce sujet ou
        # cette culture (la réponse dit si elles ne portent pas exactement sur la question).
        return _advice_answer(q, kb)
    return Answer("Je n'ai pas encore d'information fiable sur ce sujet dans mes documents "
                  "(ISRA, ANACIM).", None, False,
                  wo.render("pas_de_stat", produit=wo.word("this")))


def answer(q: Query, kb: KnowledgeBase, lang=None) -> Answer:
    """Répond à une requête analysée (français + langue locale, mêmes chiffres).

    `lang` : module de langue (wolof par défaut, ou pulaar / sereer, voir langues.py).
    """
    if lang is not None:
        with wo.using(lang):
            return _answer(q, kb)
    return _answer(q, kb)


def _answer(q: Query, kb: KnowledgeBase) -> Answer:
    if q.intent == "salutation":  # pas de chiffre : on dit ce que l'on sait faire
        return Answer(WELCOME_TEXT, None, True, wo.render("aide"))
    if q.intent == "variete":
        return _variety_answer(q, kb)
    if q.intent == "pluie":
        return _rain_answer(q, kb)
    if q.intent == "conseil":
        ans = _advice_answer(q, kb)
        if q.topic == "semis":  # « quand semer … à Kaffrine ? » : calendrier de la région
            region = _meteo_region(q, kb)
            if region:
                from . import calendrier

                cal = calendrier.build(region, "now", kb.varieties)
                if cal is not None:
                    ans = dataclasses.replace(ans, text=ans.text + f" Calendrier de semis à "
                                              f"{place(region)} : {cal.status}. {cal.message}")
        return ans
    if q.intent == "technique":
        return _technique_answer(q, kb)
    if q.intent == "meteo":
        return _meteo_answer(q, kb)
    if q.intent == "fiche" and q.product:
        return _product_sheet(q, kb) or Answer(
            f"Je n'ai pas d'information sur le {PRODUCT_BY_KEY[q.product].label}.", None,
            False, wo.render("pas_de_stat", produit=wo.L().PRODUCTS_WO[q.product]))
    if q.product is None:
        found = _search_answer(q, kb)  # question ouverte : extrait cité, si pertinent
        if found is not None:
            return found
        return Answer("Je n'ai pas reconnu le produit. " + HELP_TEXT, None, False,
                      wo.render("produit_inconnu") + wo.render("aide"))
    label = PRODUCT_BY_KEY[q.product].label
    product_wo = wo.L().PRODUCTS_WO[q.product]

    if q.intent == "prix":
        region = None if q.market else q.region
        fact = kb.price(q.product, market=q.market, region=region, year=q.year)
        prefix, prefix_wo = "", wo.WolofText("", "")
        if fact is None and q.year is not None:
            # Pas de relevé l'année demandée : on donne le dernier connu, en le disant.
            fact = kb.price(q.product, market=q.market, region=region)
            if fact is not None:
                prefix = f"Je n'ai pas de relevé en {q.year}. Voici le dernier prix connu. "
                prefix_wo = wo.render("annee_sans_prix", annee=wo.year(q.year))
        if fact is None and q.market and q.region:
            # Marché sans relevé pour ce produit (« oignon à Dakar ») : moyenne de la région.
            q = dataclasses.replace(q, market=None)
            region = q.region
            fact = kb.price(q.product, region=region, year=q.year) or kb.price(
                q.product, region=region)
        if fact is None:
            where = f" à {place(q.market or q.region)}" if (q.market or q.region) else ""
            where_wo = (wo.place("marche", place(q.market)) if q.market else
                        wo.place("region", place(q.region)) if q.region else "")
            return Answer(f"Je n'ai pas de prix {de(label)}{where}.", None, False,
                          wo.render("pas_de_prix", produit=product_wo, lieu=where_wo))
        latest = kb.prices["date"].max()
        return Answer(prefix + _price_answer(fact, q, latest=latest),
                      "PAM / WFP (prix de détail)", True,
                      prefix_wo + _price_wolof(fact, q, latest=latest),
                      _price_highlight(fact, q))

    # Statistiques : si un nom est à la fois région et département, on prend la région.
    department = q.department if q.department and q.department != q.region else None
    fact = kb.stat(q.product, q.intent or "production", year=q.year,
                   region=None if department else q.region, department=department)
    if fact is None:
        return Answer(f"Je n'ai pas cette information pour le {label}.", None, False,
                      wo.render("pas_de_stat", produit=product_wo))
    return Answer(_stat_answer(fact), fact.source, True, _stat_wolof(fact),
                  _stat_highlight(fact, kb))
