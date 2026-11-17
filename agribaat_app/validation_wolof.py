"""Génère la fiche de relecture du wolof : validation_wolof.csv (ouvrable dans Excel).

Usage : python validation_wolof.py

Le relecteur (locuteur natif) remplit les colonnes « correct » (oui / non) et
« correction ». Les corrections se reportent ensuite dans agribaat/wolof.py
(vocabulaire et gabarits) et agribaat/lexicon.py (mots-clés de compréhension).
"""

from __future__ import annotations

import csv

import config
from agribaat import wolof as wo
from agribaat.answers import answer
from agribaat.knowledge import KnowledgeBase
from agribaat.lexicon import INTENT_KEYWORDS, PRODUCTS
from agribaat.nlu import parse

OUT = config.APP_DIR / "validation_wolof.csv"

TEMPLATE_FR = {
    "prix_marche": "En {mois}, le kilo de {produit} coûtait {prix} {lieu}.",
    "prix_moyen": "En {mois}, le kilo de {produit} coûtait environ {prix} {lieu}. "
                  "Mesuré sur {n} marchés.",
    "extremes": "Le moins cher : {lieu_min} ({prix_min}). Le plus cher : {lieu_max} ({prix_max}).",
    "hausse": "Le prix a augmenté de {pct} par rapport à l'an dernier.",
    "baisse": "Le prix a baissé de {pct} par rapport à l'an dernier.",
    "ancien": "Attention : c'est le dernier prix relevé sur ce marché.",
    "annee_sans_prix": "Je n'ai pas de prix en {annee}. Voici le dernier prix que je connais.",
    "pas_de_prix": "Je n'ai pas le prix du {produit} {lieu}.",
    "production": "En {annee}, la production de {produit} {lieu} était d'environ {valeur}.",
    "superficie": "En {annee}, on a cultivé environ {valeur} de {produit} {lieu}.",
    "rendement": "En {annee}, un hectare de {produit} {lieu} a produit environ {valeur}.",
    "annee_sans_stat": "Je n'ai pas de chiffre pour {annee}. Le plus proche est {annee_dispo}.",
    "pas_de_stat": "Je n'ai pas d'information sur le {produit}.",
    "produit_inconnu": "Je n'ai pas compris le produit dont vous parlez.",
    "aide": "Je peux vous donner le prix d'un produit au marché, la production, les "
            "surfaces cultivées et le rendement. Exemple : « Combien coûte le kilo de "
            "mil à Kaolack ? »",
    "varietes": "D'après le Catalogue ouest-africain, voici des variétés de {produit} "
                "inscrites au Sénégal{precision} : {liste}.",
    "pas_de_variete": "Je n'ai pas de variété de {produit}{precision} dans le catalogue.",
    "variete_sans_produit": "Dites-moi quelle culture : mil, sorgho, arachide ou niébé.",
    "pluie_lieu": "Pendant la décade ({periode}), il est tombé {mm} à {lieu}.",
    "pluie_zone": "Pendant la décade ({periode}), {zone}, la pluie la plus faible est {mm_min} "
                  "à {lieu_min}, la plus forte {mm_max} à {lieu_max}.",
    "pluie_ancienne": "Ce sont les dernières informations dont je dispose.",
    "pas_de_pluie": "Je n'ai pas d'information sur la pluie à {lieu}.",
    "conseils": "Dans le bulletin ANACIM ({periode}), il y a {n} conseils : sur {themes}. "
                "Ils sont écrits en français.",
    "conseils_plusieurs": "Dans les derniers bulletins ANACIM, il y a {n} conseils : sur "
                          "{themes}. Ils sont écrits en français.",
    "conseils_sans_sujet": "Je n'ai pas de conseil sur {sujet}. Voici les derniers.",
    "extrait": "Je n'ai pas de réponse précise, mais j'ai trouvé cette information dans "
               "{source}. Elle est écrite en français.",
}

EXAMPLES = [
    "Quel est le prix du mil à Kaolack ?", "Combien coûte le riz ?",
    "Prix de l'arachide à Touba", "Prix du mil en 2030",
    "Quelle a été la production d'arachide en 2024 ?", "rendement du mil à Birkilane",
    "superficie de riz à Saint Louis", "production de mil à Kaolack en 2025",
    "Quel temps fait-il ?",
    "Quelle variété de mil à cycle court ?", "variété d'arachide résistante à la sécheresse",
    "Il a plu combien à Mbour ?", "pluie dans la région de Kaolack",
    "Quand récolter l'arachide ?", "conseils pour les semis de mil",
    "nouvelles variétés de blé homologuées",
]

NUMBERS = [0, 1, 7, 10, 15, 20, 25, 99, 100, 150, 300, 344, 500, 1000, 1725, 2026, 15000,
           62000, 140000, 1700000]

UNIT_FR = {"fcfa": "FCFA (à l'oral)", "t": "tonnes", "ha": "hectares",
           "kg/ha": "kilos (rendement)", "pct": "pour cent (à l'oral)",
           "mm": "millimètres (pluie)", "kg": "kilos"}


def rows() -> list[list[str]]:
    out: list[list[str]] = []

    def add(cat, key, fr, wolof, comment=""):
        out.append([cat, key, fr, wolof, "", "", comment])

    labels = {p.key: p.label for p in PRODUCTS}
    for key, word in wo.PRODUCTS_WO.items():
        add("1. Produits", key, labels[key], word, "nom utilisé dans les réponses")
    for key, value in wo.VARIANTS_WO.items():
        add("2. Variantes", key, key, value)
    for key, value in wo.PLACES_WO.items():
        add("3. Lieux", key, {"pays": "au Sénégal", "region": "dans la région de {nom}",
                             "departement": "dans le département de {nom}",
                             "marche": "au marché de {nom}"}[key], value)
    months_fr = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
                 "septembre", "octobre", "novembre", "décembre")
    for fr, wolof in zip(months_fr, wo.MONTHS_WO):
        add("4. Mois", fr, fr, wolof)
    for key, value in wo.CYCLE_WO.items():
        add("2b. Conseils", f"cycle {key}", f"(variétés) à cycle {key}", value.strip())
    add("2b. Conseils", "secheresse", "(variétés) tolérantes à la sécheresse",
        wo.DROUGHT_WO.strip())
    for key, value in wo.THEMES_WO.items():
        add("2b. Conseils", f"thème {key}", key, value, "thème d'une recommandation ANACIM")
    for key, (_, spoken) in wo.UNITS_WO.items():
        if key:
            add("5. Unités", key, UNIT_FR[key], spoken)
    for key, template in wo.T.items():
        add("6. Phrases modèles", key, TEMPLATE_FR[key], template,
            "les {…} sont remplacés automatiquement")
    for n in NUMBERS:
        add("7. Nombres (voix)", str(n), f"{n:,}".replace(",", " "), wo.number_words(n))

    kb = KnowledgeBase(config.PROCESSED_DIR)
    for question in EXAMPLES:
        ans = answer(parse([question], kb), kb)
        add("8. Réponses complètes", question, ans.text, ans.wolof.text, "texte affiché")
        add("8. Réponses complètes", question, "(texte lu par la voix)", ans.wolof.speech,
            "texte prononcé")

    for intent, words in INTENT_KEYWORDS.items():
        wolof_words = [w for w in words if w in ("njeg", "njegu", "jend", "jaay", "jar",
                                                 "marse", "seer", "yomb", "benn ektaar", "taw", "xeet",
                                                 "xeeti", "jiwu", "digal", "ndigal",
                                                 "ektaar", "tool", "bey", "goob", "jur",
                                                 "tonn")]
        add("9. Mots-clés compris", intent, intent, ", ".join(wolof_words),
            "mots qui déclenchent cette intention (sans accents) ; en ajouter ?")
    for p in PRODUCTS:
        add("9. Mots-clés compris", p.key, p.label, ", ".join(p.wo) or "(aucun)",
            "orthographes reconnues pour ce produit ; en ajouter ?")
    return out


def main() -> None:
    data = rows()
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:  # BOM : accents OK dans Excel
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["catégorie", "clé", "français", "wolof proposé", "correct ? (oui/non)",
                         "correction", "commentaire"])
        writer.writerows(data)
    print(f"{len(data)} lignes -> {OUT}")


if __name__ == "__main__":
    main()
