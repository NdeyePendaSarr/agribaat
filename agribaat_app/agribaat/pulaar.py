"""Réponses en pulaar (phase 2), construites à partir des données, comme en wolof.

Même principe que `wolof.py` : chaque phrase est un gabarit rempli avec les mêmes
chiffres que la réponse française ; `number_words` écrit les nombres en pulaar pour
la voix de synthèse (Meta MMS « ful »).

✅ Relu et approuvé par Mouhameth Diop (locuteur pulaar) le 18/11/2026.
Pour toute modification ultérieure, refaire relire.
Lancez `python validation_langues.py pulaar` pour générer la fiche de relecture,
puis corrigez directement les dictionnaires et gabarits ci-dessous.
Orthographe : alphabet officiel du pulaar au Sénégal (ɓ, ɗ, ŋ, ñ, ƴ).
"""

from __future__ import annotations

CODE = "pul"
LABEL = "Pulaar"

PRODUCTS_WO = {  # clé produit -> nom pulaar
    "mil": "gawri",
    "sorgho": "basi",
    "mais": "makka",
    "riz": "maaro",
    "arachide": "biriiji",
    "niebe": "ñebbe",
    "oignon": "basal",
    "manioc": "ñambi",
    "fonio": "foonye",
}

MONTHS_WO = ("Saanwiye", "Feebiriye", "Mars", "Abriil", "Mee", "Suwee", "Sulyee", "Ut",
             "Septaambar", "Oktoobar", "Nowaambar", "Desaambar")

VARIANTS_WO = {
    "Maize (local)": "ɗoo", "Maize (imported)": "naatnaaɗo",
    "Rice (local)": "ɗoo", "Rice (imported)": "naatnaaɗo",
    "Groundnuts (shelled)": "ɓortaaɗo", "Groundnuts (unshelled)": "e ɓuuɓe mum",
    "Onions (dry)": "ɗoo", "Onions (imported)": "naatnaaɗo",
}

PLACES_WO = {
    "pays": "e Senegaal",
    "region": "e diiwaan {nom}",
    "departement": "e depaartemaa {nom}",
    "marche": "e luumo {nom}",
}

T = {
    "prix_marche": "E lewru {mois}, coggu kiloo {produit} ko {prix} {lieu}.",
    "prix_moyen": "E lewru {mois}, coggu kiloo {produit} {lieu} ko hedde {prix}. "
                  "Ɗum hiisaa ko e luumooji {n}.",
    "extremes": "Nokku ɗo ɓuri hoyde ko {lieu_min}: {prix_min}. "
                "Nokku ɗo ɓuri sattude ko {lieu_max}: {prix_max}.",
    "hausse": "Coggu ngu ɓeydiima {pct} e dow ko woni hitaande ɓennunde.",
    "baisse": "Coggu ngu ustiima {pct} e dow ko woni hitaande ɓennunde.",
    "ancien": "Anndu wonde ɗum ko coggu sakkitiingu njiyaa e luumo oo.",
    "annee_sans_prix": "Mi alaa coggu hitaande {annee}. Ngol ko coggu sakkitiingu ngu mi anndi.",
    "pas_de_prix": "Mi alaa coggu {produit} {lieu}.",
    "production": "E hitaande {annee}, ko heɓaa e {produit} {lieu} ko hedde {valeur}.",
    "superficie": "E hitaande {annee}, {produit} aawaama {lieu} e hedde {valeur}.",
    "rendement": "E hitaande {annee}, ektaar gooto {produit} {lieu} rokkii hedde {valeur}.",
    "annee_sans_stat": "Mi alaa limoore hitaande {annee}. Ko ɓadii ko hitaande {annee_dispo}.",
    "pas_de_stat": "Mi alaa humpito e {produit}.",
    "produit_inconnu": "Mi faamaani ndema nde mbiyɗaa ndee.",
    "aide": "Mbaawmi haalande ma coggu ndema e luumooji, walla ko heɓaa, ngesa aawaaɗe e "
            "ko ektaar gooto rokkata. Misal: « Hol no coggu kiloo gawri woni e Kawlak? »",
    "varietes": "E Katalog Afrik Hirnaange, noone {produit} ɗee ina njiyaa e Senegaal"
                "{precision}: {liste}.",
    "pas_de_variete": "Mi alaa noone {produit}{precision} e Katalog oo.",
    "variete_sans_produit": "Wiy am ndema nde: gawri, basi, biriiji walla ñebbe.",
    "pluie_lieu": "E balɗe sappo ɗe ({periode}), toɓo e {lieu} ko hedde {mm}.",
    "pluie_zone": "E balɗe sappo ɗe ({periode}), {zone}, toɓo ɓurngo famɗude ko {mm_min} "
                  "e {lieu_min}, ɓurngo heewde ko {mm_max} e {lieu_max}.",
    "pluie_ancienne": "Ɗum ko kabaruuji sakkitiiɗi ɗi njogiimi.",
    "pas_de_pluie": "Mi alaa kabaru toɓo e {lieu}.",
    "conseils": "E bulletin ANACIM ({periode}), ena woodi wasiyaaji {n}: e {themes}. "
                "Ɗi mbinndaa ko e farayseere.",
    "conseils_plusieurs": "E bulletin ANACIM sakkitiiɗi ɗi, ena woodi wasiyaaji {n}: e "
                          "{themes}. Ɗi mbinndaa ko e farayseere.",
    "conseils_sans_sujet": "Mi alaa wasiyaaji e {sujet}. Ɗii ɗoo ko sakkitiiɗi.",
    "extrait": "Mi alaa jaabawol laaɓngol, kono mi yiyii ngol humpito e {source}. "
               "Ngol winndaa ko e farayseere.",
    # --- Météo en direct (20/11) : BROUILLON, à faire relire par Mouhameth ---
    "meteo_resume": "E {lieu}, e balɗe jeeɗiɗi garooje ɗee: toɓo ina yettoo {mm}, ngulɓiri "
                    "ina yettoo {tmax}.",
    "meteo_resume_sec": "E {lieu}, e balɗe jeeɗiɗi garooje ɗee: ngulɓiri ina yettoo {tmax}.",
    "meteo_pluie_forte": "Toɓo mawɗo ina wara ({mm} e balɗe tati): wata a waɗ lekki, wata a "
                         "werlo engrais.",
    "meteo_pluie": "Toɓo ina wara ({mm} e balɗe tati): wata a waɗ lekki hade toɓo; ngam "
                   "aawde, fadu leydi ndi heewa ndiyam.",
    "meteo_recolte": "Ko jamanu soñde: suddu ko yoorata, ndesku saakuuji maa ɗo toɓo "
                     "heɓataa ɗi.",
    "meteo_chaleur": "Toɓo alaa, ngulɓiri ina tiiɗi ({tmax}): yarnu ngesa maa subaka walla "
                     "kikiiɗe.",
    "meteo_sec": "Toɓo alaa e ndee yontere: yarnu ngesa maa sahaa kala.",
    "meteo_vent": "Henndu ina tiiɗi: wata a waɗ lekki.",
    "meteo_normal": "Alaa caɗeele asamaan e balɗe garooje ɗee.",
    # --- Bulletin vocal et alertes (20/11) : BROUILLON, à faire relire par Mouhameth ---
    "bulletin_intro": "Kabaruuji AgriBaat e {lieu}.",
    "bulletin_fin": "AgriBaat: kabaruuji ɗii iwi ko e ANACIM, PAM e Open-Meteo.",
    "alerte_intro": "Reentino, AgriBaat e {lieu}!",
    # --- Où vendre ? (20/11) : BROUILLON, à faire relire par Mouhameth ---
    "vente_marche": "Ngam yeeyde {produit} maa, luumo ɓurngo nafde e takko maa ko {marche}: "
                    "kiloo ko {prix}, laawol ngol ko {km}. So a ittii coggu laawol, a heɓay "
                    "{gain} e kiloo kala, so fotondiraa e {local}.",
    "vente_sur_place": "Ngam yeeyde {produit} maa, {marche} ɓuri moƴƴude e takko maa: kiloo "
                       "ko {prix}.",
    "vente_mois": "So a waawii ndesaade {produit} maa no moƴƴi, e lewru {mois} coggu ngu "
                  "ɓurata toowde: {pct} ko ɓuri jamanu soñde.",
}

WORDS = {"and": " e ", "days": "balɗe ", "to": " haa ", "up_to": ", haa ",
         "per_ha": " e ektaar)", "advice": "wasiyaaji", "senegal": "Senegaal",
         "this": "ɗum"}

CYCLE_WO = {"court": " yaawɗe", "long": " neeɓɗe"}
DROUGHT_WO = " muñooje ñakku toɓo"
THEMES_WO = {
    "semis": "aawdi", "recolte": "soñde", "ravageurs": "reende ngesa",
    "previsions": "kabaruuji toɓo", "elevage": "jawdi", "eau": "ndiyam",
    "autre": "golle goɗɗe",
}

UNITS_WO = {  # unité -> (écran, oral)
    "fcfa": ("FCFA", "sefa"),
    "t": ("tonn", "tonn"),
    "ha": ("ektaar", "ektaar"),
    "kg/ha": ("kiloo", "kiloo"),
    "pct": ("%", "e teemedere"),
    "c": ("°C", "degre"),
    "mm": ("mm", "milimeeter"),
    "kg": ("kg", "kiloo"),
    "km": ("km", "kilomeeter"),
    "": ("", ""),
}

# ------------------------------------------------------------ nombres en pulaar
UNITS = ("", "go'o", "ɗiɗi", "tati", "nay", "joy", "jeegom", "jeeɗiɗi", "jeetati", "jeenay")


def _below_100(n: int) -> str:
    tens, units = divmod(n, 10)
    parts = []
    if tens == 1:
        parts.append("sappo")
    elif tens == 2:
        parts.append("noogaas")
    elif tens:
        parts.append(f"capanɗe {UNITS[tens]}")
    if units:
        parts.append(UNITS[units])
    return " e ".join(parts)


def _below_1000(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    parts = []
    if hundreds:
        parts.append("teemedere" if hundreds == 1 else f"teemedde {UNITS[hundreds]}")
    if rest:
        parts.append(_below_100(rest))
    return " e ".join(parts)


def number_words(n: int) -> str:
    """Entier -> pulaar. 344 -> 'teemedde tati e capanɗe nay e nay'."""
    n = int(n)
    if n == 0:
        return "sifir"
    parts = []
    millions, n = divmod(n, 10**6)
    if millions:
        parts.append(f"miliyon {_below_1000(millions)}")
    thousands, n = divmod(n, 1000)
    if thousands:
        parts.append("ujunere" if thousands == 1 else f"ujunaaje {_below_1000(thousands)}")
    if n:
        parts.append(_below_1000(n))
    return " e ".join(parts)
