"""Construction des réponses en français, courtes, chiffrées et sourcées.

Règle : chaque chiffre vient d'une table. Si la donnée manque, on le dit.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import wolof as wo
from .knowledge import KnowledgeBase, PriceFact, StatFact
from .lexicon import MONTHS_FR, PRODUCT_BY_KEY
from .nlu import Query

INDICATOR_LABELS = {"production": "la production", "superficie": "la superficie cultivée",
                    "rendement": "le rendement"}

HELP_TEXT = ("Je peux vous donner le prix d'un produit sur un marché, ou la production, "
             "la superficie et le rendement d'une culture. Par exemple : "
             "« Quel est le prix du mil à Kaolack ? »")


@dataclass
class Answer:
    text: str  # réponse en français
    source: str | None  # source des chiffres
    found: bool  # False si aucune donnée
    wolof: wo.WolofText | None = None  # même réponse en wolof (écran + oral)


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
    product = wo.PRODUCTS_WO[fact.product]
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
                           produit=wo.PRODUCTS_WO[fact.product], lieu=where,
                           valeur=wo.Qty(fact.value, fact.unit))


def answer(q: Query, kb: KnowledgeBase) -> Answer:
    """Répond à une requête analysée (français + wolof, mêmes chiffres)."""
    if q.product is None:
        return Answer("Je n'ai pas reconnu le produit. " + HELP_TEXT, None, False,
                      wo.render("produit_inconnu") + wo.render("aide"))
    label = PRODUCT_BY_KEY[q.product].label
    product_wo = wo.PRODUCTS_WO[q.product]

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
        if fact is None:
            where = f" à {place(q.market or q.region)}" if (q.market or q.region) else ""
            where_wo = (wo.place("marche", place(q.market)) if q.market else
                        wo.place("region", place(q.region)) if q.region else "")
            return Answer(f"Je n'ai pas de prix {de(label)}{where}.", None, False,
                          wo.render("pas_de_prix", produit=product_wo, lieu=where_wo))
        latest = kb.prices["date"].max()
        return Answer(prefix + _price_answer(fact, q, latest=latest),
                      "PAM / WFP (prix de détail)", True,
                      prefix_wo + _price_wolof(fact, q, latest=latest))

    # Statistiques : si un nom est à la fois région et département, on prend la région.
    department = q.department if q.department and q.department != q.region else None
    fact = kb.stat(q.product, q.intent or "production", year=q.year,
                   region=None if department else q.region, department=department)
    if fact is None:
        return Answer(f"Je n'ai pas cette information pour le {label}.", None, False,
                      wo.render("pas_de_stat", produit=product_wo))
    return Answer(_stat_answer(fact), fact.source, True, _stat_wolof(fact))
