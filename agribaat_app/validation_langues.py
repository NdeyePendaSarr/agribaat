"""Fiche de relecture du pulaar ou du sereer (même principe que validation_wolof.py).

Usage :
    python validation_langues.py pulaar   -> validation_pulaar.csv (pour Mouhameth)
    python validation_langues.py sereer   -> validation_sereer.csv (pour Seydina)

Le relecteur remplit « correct ? » (oui / non) et « correction » ; la colonne
« français » donne le sens attendu. Les corrections se reportent ensuite dans
agribaat/pulaar.py ou agribaat/sereer.py (et agribaat/lexicon.py pour les mots-clés).
"""

from __future__ import annotations

import csv
import sys

import config
from agribaat import pulaar, sereer
from agribaat.answers import answer
from agribaat.knowledge import KnowledgeBase
from agribaat.lexicon import OTHER_PRODUCT_KEYWORDS, PRODUCTS
from agribaat.nlu import parse
from validation_wolof import NUMBERS, TEMPLATE_FR, UNIT_FR

MODULES = {"pulaar": pulaar, "sereer": sereer}

# Questions d'essai : en français (sens connu) et dans la langue (mots-clés à vérifier).
EXAMPLES_FR = [
    "Quel est le prix du mil à Kaolack ?", "Combien coûte le riz ?",
    "Prix du mil en 2030", "Quelle a été la production d'arachide en 2024 ?",
    "rendement du mil à Birkilane", "Quelle variété de mil à cycle court ?",
    "Il a plu combien à Mbour ?", "Quand récolter l'arachide ?",
]
EXAMPLES_LOCAL = {
    "pulaar": ["Hol no coggu kiloo gawri woni e Kawlak?", "coggu maaro",
               "toɓo e Mbour", "noone biriiji yaawɗe", "ndey aawde gawri"],
    "sereer": ["njeg kilo maac no Kaolack", "ndoɓ no Mbour", "xeet gerte"],
}


def rows(name: str) -> list[list[str]]:
    module = MODULES[name]
    out: list[list[str]] = []

    def add(cat, key, fr, local, comment=""):
        out.append([cat, key, fr, local, "", "", comment])

    labels = {p.key: p.label for p in PRODUCTS}
    for key, word in module.PRODUCTS_WO.items():
        add("1. Produits", key, labels[key], word, "nom utilisé dans les réponses")
    for key, value in module.VARIANTS_WO.items():
        add("2. Variantes", key, key, value)
    for key, value in module.PLACES_WO.items():
        add("3. Lieux", key, {"pays": "au Sénégal", "region": "dans la région de {nom}",
                             "departement": "dans le département de {nom}",
                             "marche": "au marché de {nom}"}[key], value)
    months_fr = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
                 "septembre", "octobre", "novembre", "décembre")
    for fr, local in zip(months_fr, module.MONTHS_WO):
        add("4. Mois", fr, fr, local)
    for key, value in module.CYCLE_WO.items():
        add("2b. Conseils", f"cycle {key}", f"(variétés) à cycle {key}", value.strip())
    add("2b. Conseils", "secheresse", "(variétés) tolérantes à la sécheresse",
        module.DROUGHT_WO.strip())
    for key, value in module.THEMES_WO.items():
        add("2b. Conseils", f"thème {key}", key, value, "thème d'une recommandation ANACIM")
    words_fr = {"and": "et", "days": "(…) jours", "to": "de … à …", "up_to": "jusqu'à",
                "per_ha": "par hectare", "advice": "les conseils", "senegal": "Sénégal",
                "this": "cela"}
    for key, value in module.WORDS.items():
        add("2c. Petits mots", key, words_fr[key], value.strip())
    for key, (_, spoken) in module.UNITS_WO.items():
        if key:
            add("5. Unités", key, UNIT_FR[key], spoken)
    for key, template in module.T.items():
        add("6. Phrases modèles", key, TEMPLATE_FR[key], template,
            "les {…} sont remplacés automatiquement")
    if module is pulaar:  # le sereer n'a pas encore de voix : nombres en chiffres
        for n in NUMBERS:
            add("7. Nombres (voix)", str(n), f"{n:,}".replace(",", " "), module.number_words(n))

    kb = KnowledgeBase(config.PROCESSED_DIR)
    for question in EXAMPLES_FR:
        ans = answer(parse([question], kb), kb, module)
        add("8. Réponses complètes", question, ans.text, ans.wolof.text, "texte affiché")
        if module is pulaar:
            add("8. Réponses complètes", question, "(texte lu par la voix)", ans.wolof.speech,
                "texte prononcé")
    for question in EXAMPLES_LOCAL[name]:
        q = parse([question], kb)
        ans = answer(q, kb, module)
        add("8b. Questions dans la langue", question,
            f"compris : {q.intent or '?'} / {q.product or '-'} / "
            f"{q.market or q.region or q.locality or '-'}", ans.wolof.text,
            "la question est-elle bien écrite ? l'app a-t-elle compris ?")
    for p in PRODUCTS:
        if p.key in OTHER_PRODUCT_KEYWORDS:
            add("9. Mots-clés compris", p.key, p.label, ", ".join(OTHER_PRODUCT_KEYWORDS[p.key]),
                "pulaar et sereer mélangés ; ajouter les orthographes courantes")
    add("9. Mots-clés compris", "intentions", "prix, pluie, variété, conseil…",
        "voir agribaat/lexicon.py (mots marqués « pulaar »)", "à compléter")
    return out


def main() -> None:
    name = (sys.argv[1] if len(sys.argv) > 1 else "pulaar").lower()
    if name not in MODULES:
        sys.exit(f"Langue inconnue : {name} (pulaar ou sereer)")
    data = rows(name)
    path = config.APP_DIR / f"validation_{name}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as f:  # BOM : accents OK dans Excel
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["catégorie", "clé", "français", f"{name} proposé",
                         "correct ? (oui/non)", "correction", "commentaire"])
        writer.writerows(data)
    print(f"{len(data)} lignes -> {path}")


if __name__ == "__main__":
    main()
