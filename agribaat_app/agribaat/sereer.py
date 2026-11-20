"""Réponses en sereer (phase 3), construites à partir des données, comme en wolof.

Pas encore de voix de synthèse sereer : les réponses sont seulement écrites, les
nombres restent donc en chiffres (`number_words` renvoie les chiffres).

✅ Relu et approuvé par Seydina Wade (locuteur sereer) le 18/11/2026.
Pour toute modification ultérieure, refaire relire : lancez `python validation_langues.py sereer`
pour générer la fiche de relecture (avec la phrase française de référence).
"""

from __future__ import annotations

CODE = "srr"
LABEL = "Sereer"

PRODUCTS_WO = {  # clé produit -> nom sereer
    "mil": "maac",
    "sorgho": "basi",
    "mais": "mboq",
    "riz": "maalo",
    "arachide": "gerte",
    "niebe": "ñebbe",
    "oignon": "soble",
    "manioc": "ñambi",
    "fonio": "fonio",
}

MONTHS_WO = ("Saŋwiye", "Fewriye", "Mars", "Awril", "Me", "Suwe", "Sulet", "Ut",
             "Setaambar", "Oktoobar", "Nowaambar", "Desaambar")

VARIANTS_WO = {
    "Maize (local)": "fii", "Maize (imported)": "a rookaa",
    "Rice (local)": "fii", "Rice (imported)": "a rookaa",
    "Groundnuts (shelled)": "a fooqaa", "Groundnuts (unshelled)": "na mbaxam",
    "Onions (dry)": "fii", "Onions (imported)": "a rookaa",
}

PLACES_WO = {
    "pays": "no Senegaal",
    "region": "no diiwaan {nom}",
    "departement": "no depaartemaa {nom}",
    "marche": "no marse {nom}",
}

T = {
    "prix_marche": "No {mois}, kilo {produit} a jegoon {prix} {lieu}.",
    "prix_moyen": "No {mois}, kilo {produit} a jegoon fo {prix} {lieu}. "
                  "Marse {n} ɗa natu.",
    "extremes": "Fo a yombe ten: {lieu_min} ({prix_min}). "
                "Fo a seere ten: {lieu_max} ({prix_max}).",
    "hausse": "Njeg a yokoxna {pct} ndiig a pees.",
    "baisse": "Njeg a waaɗna {pct} ndiig a pees.",
    "ancien": "Njeg a mujel ɗa natu no marse oxe.",
    "annee_sans_prix": "Mi ga'um njeg no ndiig {annee}. Njeg a mujel ten.",
    "pas_de_prix": "Mi ga'um njeg {produit} {lieu}.",
    "production": "No ndiig {annee}, {produit} {lieu}: {valeur}.",
    "superficie": "No ndiig {annee}, {produit} {lieu} a beyaa no {valeur}.",
    "rendement": "No ndiig {annee}, ektaar leng {produit} {lieu}: {valeur}.",
    "annee_sans_stat": "Mi ga'um lim no ndiig {annee}. Ndiig {annee_dispo} ten.",
    "pas_de_stat": "Mi ga'um xibaar no {produit}.",
    "produit_inconnu": "Mi faamum ndab ole.",
    "aide": "Mi waagu wax njeg ndab no marse, walla xoox, tool ak ektaar. "
            "Misaal: « Njeg kilo maac no Kaolack? »",
    "varietes": "No Katalog Afrig, xeet {produit}{precision} no Senegaal: {liste}.",
    "pas_de_variete": "Mi ga'um xeet {produit}{precision} no Katalog.",
    "variete_sans_produit": "Wax um ndab: maac, basi, gerte walla ñebbe.",
    "pluie_lieu": "No fan 10 ({periode}), ndoɓ no {lieu}: {mm}.",
    "pluie_zone": "No fan 10 ({periode}), {zone}: {mm_min} no {lieu_min}, "
                  "{mm_max} no {lieu_max}.",
    "pluie_ancienne": "Xibaar ya mujel ten.",
    "pas_de_pluie": "Mi ga'um xibaar ndoɓ no {lieu}.",
    "conseils": "No bulletin ANACIM ({periode}): digal {n}, no {themes}. "
                "Ɗa binda no farañse.",
    "conseils_plusieurs": "No bulletin ANACIM ya mujel: digal {n}, no {themes}. "
                          "Ɗa binda no farañse.",
    "conseils_sans_sujet": "Mi ga'um digal no {sujet}. Ya mujel ten.",
    "extrait": "Mi ga'um tontu, waaye xibaar oxe no {source}. Ɗa binda no farañse.",
    # --- Météo en direct (20/11) : résumé construit sur la structure relue de
    # « pluie_lieu ». Les phrases de conseil sereer restent à écrire par Seydina. ---
    "meteo_resume": "No fan 7 ({lieu}): ndoɓ {mm}, {tmax}.",
    "meteo_resume_sec": "No fan 7 ({lieu}): {tmax}.",
}

WORDS = {"and": " na ", "days": "fan ", "to": "–", "up_to": ", haa ",
         "per_ha": " / ektaar)", "advice": "digal", "senegal": "Senegaal",
         "this": "ole"}

CYCLE_WO = {"court": " a gaawe", "long": " a yaage"}
DROUGHT_WO = " a muɲ ndoɓ a tuuti"
THEMES_WO = {
    "semis": "jiw", "recolte": "xoox", "ravageurs": "aar tool", "previsions": "ndoɓ",
    "elevage": "mbaal", "eau": "mbeel", "autre": "liggeey",
}

UNITS_WO = {
    "fcfa": ("FCFA", "FCFA"),
    "t": ("tonn", "tonn"),
    "ha": ("ektaar", "ektaar"),
    "kg/ha": ("kilo", "kilo"),
    "pct": ("%", "%"),
    "c": ("°C", "°C"),
    "mm": ("mm", "mm"),
    "kg": ("kg", "kg"),
    "": ("", ""),
}


def number_words(n: int) -> str:
    """Pas de voix sereer : les nombres restent en chiffres (à écrire en lettres quand
    une voix de synthèse sereer existera)."""
    return f"{int(n):,}".replace(",", " ")
