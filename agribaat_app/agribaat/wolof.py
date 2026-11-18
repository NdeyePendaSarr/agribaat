"""Réponses en wolof construites directement à partir des données.

Pourquoi : la traduction automatique (NLLB) perd ou déforme des informations
(ex. « 10 % de plus » supprimé, « mil » rendu par « miir »). Ici, chaque phrase
wolof est un gabarit rempli avec les mêmes chiffres que la réponse française :
aucun chiffre ne peut disparaître.

Deux versions de chaque réponse :
- `text`   : affichée à l'écran, chiffres en clair (300 FCFA) ;
- `speech` : lue par la synthèse vocale, nombres écrits en wolof (ñetti téeméer sefa).

⚠️ TOUT LE VOCABULAIRE DE CE FICHIER EST À FAIRE VALIDER PAR UN LOCUTEUR NATIF.
Lancez `python validation_wolof.py` pour générer la fiche de relecture, puis
corrigez directement les dictionnaires et gabarits ci-dessous.
"""

from __future__ import annotations

import contextlib
import contextvars
import re
import sys
from dataclasses import dataclass

# ------------------------------------------------------------ vocabulaire
PRODUCTS_WO = {  # clé produit -> nom wolof
    "mil": "dugub",
    "sorgho": "basi",  # À VALIDER (sorgho)
    "mais": "mbóq",
    "riz": "ceeb",
    "arachide": "gerte",
    "niebe": "ñebbe",
    "oignon": "soble",
    "manioc": "ñambi",
    "fonio": "findi",  # À VALIDER
}

MONTHS_WO = ("Samwiyee", "Fewriyee", "Mars", "Awril", "Mee", "Suwe", "Sulet", "Ut",
             "Sattumbar", "Oktoobar", "Nowàmbar", "Desàmbar")

VARIANTS_WO = {  # variante WFP -> précision wolof
    "Maize (local)": "bu fii", "Maize (imported)": "bu ñu indi",
    "Rice (local)": "bu fii", "Rice (imported)": "bu ñu indi",
    "Groundnuts (shelled)": "bu ñu fóq", "Groundnuts (unshelled)": "ak mbaxam",
    "Onions (dry)": "bu fii", "Onions (imported)": "bu ñu indi",
}

PLACES_WO = {  # portée géographique
    "pays": "ci Senegaal",
    "region": "ci diiwaanu {nom}",
    "departement": "ci depàrtmaŋu {nom}",
    "marche": "ci marse {nom}",
}

# ------------------------------------------------------------ gabarits
# {quantités} : remplacées par « 300 FCFA » à l'écran et « ñetti téeméer sefa » à l'oral.
T = {
    "prix_marche": "Ci {mois}, kilo {produit} dafa jaroon {prix} {lieu}.",
    "prix_moyen": "Ci {mois}, kilo {produit} dafa jaroon lu tollu ci {prix} {lieu}. "
                  "Ñu natt ko ci {n} marse.",
    "extremes": "Fi mu gën a yomb mooy {lieu_min}: {prix_min}. "
                "Fi mu gën a seer mooy {lieu_max}: {prix_max}.",
    "hausse": "Njëg gi yokku na {pct} ci li mu jaroon at mi weesu.",
    "baisse": "Njëg gi wàññiku na {pct} ci li mu jaroon at mi weesu.",
    "ancien": "Xamal ne lii mooy njëg mi mujj mi ñu natt ci marse bii.",
    "annee_sans_prix": "Amuma njëg ci at {annee}. Njëg mi mujj mi ma xam a ngi nii.",
    "pas_de_prix": "Amuma njëgu {produit} {lieu}.",
    "production": "Ci at {annee}, góobu {produit} {lieu} tollu na ci {valeur}.",
    "superficie": "Ci at {annee}, ñu bey {produit} {lieu} ci lu tollu ci {valeur}.",
    "rendement": "Ci at {annee}, benn ektaar {produit} {lieu} jur na lu tollu ci {valeur}.",
    "annee_sans_stat": "Amuma lim ci at {annee}. Li gën a jege mooy at {annee_dispo}.",
    "pas_de_stat": "Amuma xibaar ci {produit}.",
    "produit_inconnu": "Xammeewuma ndab li nga wax.",
    "aide": "Man naa la wax njëgu ndab ci marse, walla góob, tool yi ñu bey ak li benn "
            "ektaar di jur. Misaal: « Ñaata la kilo dugub di jar ci Kaolack? »",
    # --- conseils (catalogue des variétés, ANACIM)
    "varietes": "Ci Katalog bu Afrig sowwu jant, xeeti {produit} yii ñu ngi ci Senegaal"
                "{precision}: {liste}.",
    "pas_de_variete": "Amuma xeetu {produit}{precision} ci Katalog bi.",
    "variete_sans_produit": "Waxal ma ban mbay: dugub, basi, gerte walla ñebbe.",
    "pluie_lieu": "Ci fukki fan yi ({periode}), taw bi ci {lieu} tollu na ci {mm}.",
    "pluie_zone": "Ci fukki fan yi ({periode}), {zone}, taw bi mi gën a tuuti mooy {mm_min} "
                  "ci {lieu_min}, bi gën a bari mooy {mm_max} ci {lieu_max}.",
    "pluie_ancienne": "Lii mooy xibaar yi mujj yi ma am.",
    "pas_de_pluie": "Amuma xibaaru taw ci {lieu}.",
    "conseils": "Ci bulletin ANACIM bi ({periode}), am na {n} digal: ci {themes}. "
                "Bind nañu leen ci farañse.",
    "conseils_plusieurs": "Ci bulletin ANACIM yi mujj, am na {n} digal: ci {themes}. "
                          "Bind nañu leen ci farañse.",
    "conseils_sans_sujet": "Amuma digal bu jëm ci {sujet}. Yii ñoo mujj.",
    "extrait": "Amuma tontu bu leer, waaye gis naa xibaar bii ci {source}. "
               "Ci farañse la bind.",
}

# Petits mots utilisés pour assembler les listes et les fiches variétés.
WORDS = {"and": " ak ", "days": "fan ", "to": " ba ", "up_to": ", ba ",
         "per_ha": " ci ektaar bi)", "advice": "digal yi", "senegal": "Senegaal",
         "this": "lii"}

CYCLE_WO = {"court": " yu gaaw", "long": " yu yàgg"}
DROUGHT_WO = " yu mën a muñ ñàkk taw"
THEMES_WO = {  # thème de recommandation -> wolof
    "semis": "ji gi", "recolte": "góob gi", "ravageurs": "aar tool yi",
    "previsions": "xibaari taw bi", "elevage": "mala yi", "eau": "ndox mi",
    "autre": "yeneen liggéey",
}

UNITS_WO = {  # unité -> (écran, oral)
    "fcfa": ("FCFA", "sefa"),
    "t": ("tonn", "tonn"),
    "ha": ("ektaar", "ektaar"),
    "kg/ha": ("kilo", "kilo"),
    "pct": ("%", "ci téeméer"),
    "mm": ("mm", "milimetar"),
    "kg": ("kg", "kilo"),
    "": ("", ""),
}


# ------------------------------------------------------------ nombres en wolof
UNITS = ("", "benn", "ñaar", "ñett", "ñeent", "juróom", "juróom benn", "juróom ñaar",
         "juróom ñett", "juróom ñeent")


def _connect(words: str) -> str:
    """Forme de liaison devant téeméer / junni / milyoŋ : ñaar -> ñaari."""
    return words + "i"


def _below_100(n: int) -> str:
    tens, units = divmod(n, 10)
    parts = []
    if tens:
        parts.append("fukk" if tens == 1 else f"{UNITS[tens]} fukk")
    if units:
        parts.append(UNITS[units])
    return " ak ".join(parts)


def _below_1000(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    parts = []
    if hundreds:
        parts.append("téeméer" if hundreds == 1 else f"{_connect(UNITS[hundreds])} téeméer")
    if rest:
        parts.append(_below_100(rest))
    return " ak ".join(parts)


def number_words(n: int) -> str:
    """Entier (0 à 999 999 999) -> wolof. 344 -> 'ñetti téeméer ak ñeent fukk ak ñeent'."""
    n = int(n)
    if n == 0:
        return "tus"
    parts = []
    for size, name in ((10**6, "milyoŋ"), (1000, "junni")):
        count, n = divmod(n, size)
        if count:
            if count == 1:
                parts.append("benn milyoŋ" if size == 10**6 else name)
            else:
                parts.append(f"{_connect(_below_1000(count))} {name}")
    if n:
        parts.append(_below_1000(n))
    return " ak ".join(parts)


def spoken_round(value: float) -> int:
    """À l'oral, les grands nombres sont arrondis à 2 chiffres significatifs
    (1 681 953 -> 1 700 000) : plus courts à dire, plus faciles à retenir."""
    value = round(value)
    if abs(value) < 10_000:
        return int(value)
    digits = len(str(abs(int(value)))) - 2
    return int(round(value, -digits))


def _digits(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ")


@dataclass(frozen=True)
class Qty:
    """Quantité affichée en chiffres et dite en toutes lettres."""

    value: float
    unit: str = ""
    exact: bool = False  # années : jamais arrondies

    def show(self) -> str:
        label = L().UNITS_WO[self.unit][0]
        number = str(int(self.value)) if self.exact else _digits(self.value)
        return f"{number} {label}".strip()

    def say(self) -> str:
        number = int(self.value) if self.exact else spoken_round(self.value)
        return f"{L().number_words(number)} {L().UNITS_WO[self.unit][1]}".strip()


def year(value: int) -> Qty:
    return Qty(value, exact=True)


@dataclass
class WolofText:
    text: str  # écran
    speech: str  # synthèse vocale

    def __add__(self, other: "WolofText") -> "WolofText":
        return WolofText(f"{self.text} {other.text}".strip(),
                         f"{self.speech} {other.speech}".strip())


@dataclass(frozen=True)
class Seq:
    """Suite de morceaux (texte ou quantités) : « 333 FCFA (bu ñu indi) ak 396 FCFA… »."""

    parts: tuple

    def show(self) -> str:
        return "".join(p.show() if hasattr(p, "show") else p for p in self.parts)

    def say(self) -> str:
        return "".join(p.say() if hasattr(p, "say") else p for p in self.parts)


def render(key: str, **values) -> WolofText:
    """Remplit le gabarit `key` deux fois : version écran et version orale."""
    show = {k: v.show() if hasattr(v, "show") else v for k, v in values.items()}
    say = {k: v.say() if hasattr(v, "say") else v for k, v in values.items()}
    template = L().T[key]
    spoken = template.format(**say)
    for mark, repl in (("(", ", "), (")", ","), ("«", ""), ("»", "")):  # non lus à voix haute
        spoken = spoken.replace(mark, repl)
    return WolofText(_tidy(template.format(**show)), _tidy(spoken).replace(",.", ".")
                     .replace(",,", ","))


def _tidy(text: str) -> str:
    """Espaces doubles et espace avant ponctuation (champ « lieu » vide, etc.)."""
    text = " ".join(text.split())
    for mark in ".,:;?!":
        text = text.replace(f" {mark}", mark)
    return text


def month(ts) -> Seq:
    """Timestamp -> « Oktoobar 2026 » (écran) / « Oktoobar ñaari junni ak… » (oral)."""
    return Seq((L().MONTHS_WO[ts.month - 1] + " ", year(ts.year)))


def price_variants(variants: dict[str, float]) -> Seq:
    """{'Rice (imported)': 333, 'Rice (local)': 396} -> prix par variante, du moins cher."""
    parts: list = []
    for i, (name, value) in enumerate(sorted(variants.items(), key=lambda kv: kv[1])):
        if i:
            parts.append(word("and"))
        parts += [Qty(value, "fcfa"), f" ({L().VARIANTS_WO.get(name, name)})"]
    return Seq(tuple(parts))


def place(kind: str, name: str | None = None) -> str:
    return L().PLACES_WO[kind].format(nom=name or "")


@dataclass(frozen=True)
class Name:
    """Nom propre (variété, source) : chiffres lus en wolof à l'oral (55-437 -> …)."""

    text: str

    def show(self) -> str:
        return self.text

    def say(self) -> str:
        spoken = re.sub(r"\d+", lambda m: f" {L().number_words(int(m.group()))} ", self.text)
        return " ".join(spoken.replace("-", " ").split())


def period(start, end) -> Seq:
    """Décade : « 21 ba 31 Ut 2026 »."""
    return Seq((Qty(start.day, exact=True), word("to"), Qty(end.day, exact=True), " ",
                L().MONTHS_WO[end.month - 1], " ", year(end.year)))


def join_list(items: list) -> Seq:
    """[a, b, c] -> « a, b ak c »."""
    parts: list = []
    for i, item in enumerate(items):
        if i:
            parts.append(word("and") if i == len(items) - 1 else ", ")
        parts.append(item)
    return Seq(tuple(parts))


# ------------------------------------------------------------ autres langues
# Les mêmes outils servent au pulaar et au sereer : chaque langue est un module
# (pulaar.py, sereer.py) qui définit les mêmes noms que ce fichier (T, PRODUCTS_WO,
# MONTHS_WO, VARIANTS_WO, PLACES_WO, CYCLE_WO, DROUGHT_WO, THEMES_WO, UNITS_WO,
# WORDS, number_words). Les noms en « _WO » sont historiques : ils désignent la
# langue locale active, pas forcément le wolof.
_active: contextvars.ContextVar = contextvars.ContextVar("agribaat_langue", default=None)


def L():  # noqa: N802 — « la langue active », utilisée par toutes les réponses
    """Module de la langue locale active (wolof par défaut)."""
    return _active.get() or sys.modules[__name__]


@contextlib.contextmanager
def using(module):
    """Construit les réponses dans une autre langue le temps d'un bloc `with`."""
    token = _active.set(module)
    try:
        yield module
    finally:
        _active.reset(token)


def word(key: str) -> str:
    return L().WORDS[key]
