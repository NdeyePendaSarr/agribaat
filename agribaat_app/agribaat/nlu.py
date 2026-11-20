"""Compréhension de la question : intention + produit + lieu + année.

Approche par mots-clés, volontairement simple et prévisible. Elle analyse à la
fois le texte wolof (sortie de l'ASR) et sa traduction française : un mot-clé
trouvé dans l'un ou l'autre suffit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .knowledge import TOPICS, KnowledgeBase
from .lexicon import (GREETING_KEYWORDS, INTENT_KEYWORDS, LOCAL_GLOSS,
                      OTHER_PRODUCT_KEYWORDS, PRODUCTS, PRODUCT_BY_KEY, normalize)

# Alias de lieux : orthographes courantes -> nom dans les données.
PLACE_ALIASES: dict[str, str] = {
    "ziguinchor": "Zigiunchor",  # orthographe du fichier WFP
    "thies": "Thies",
    "saint louis": "Saint-Louis",
    "ndar": "Saint-Louis",  # nom wolof de Saint-Louis (À VALIDER)
    "kawlax": "Kaolack", "kawlaax": "Kaolack",  # nom wolof de Kaolack (À VALIDER)
    "kawlak": "Kaolack",  # nom pulaar de Kaolack
    "ndakaaru": "Dakar", "ndakaru": "Dakar",  # nom pulaar et wolof de Dakar
}


@dataclass
class Query:
    intent: str | None = None  # prix | vendre | production | ... | salutation
    product: str | None = None
    market: str | None = None  # marché WFP
    region: str | None = None  # région (DAPSA ou WFP)
    department: str | None = None  # département DAPSA
    year: int | None = None
    locality: str | None = None  # localité citée par l'ANACIM (pluies)
    cycle: str | None = None  # court | long (variétés)
    drought: bool = False  # variété tolérante à la sécheresse
    topic: str | None = None  # semis | recolte | ravageurs | ... (conseils)
    text: str = ""  # question normalisée (recherche de passages)
    intent_guessed: bool = False  # intention déduite par défaut (aucun mot-clé)
    intent_fuzzy: bool = False  # mot-clé reconnu à une lettre près seulement
    focus: str = ""  # sens reconnu seulement (produit + notions), en français

    @property
    def is_complete(self) -> bool:
        if self.intent in ("pluie", "conseil", "salutation", "technique", "meteo"):  # sans produit
            return True
        return self.intent is not None and self.product is not None


# Ordre de priorité des intentions. « variete » avant « pluie » : « variété résistante
# au manque de pluie » parle de variétés ; « technique » avant « conseil » : « que faire
# contre le striga » demande une pratique (documents ISRA), pas le calendrier ANACIM.
ORDER = ("variete", "meteo", "pluie", "technique", "conseil", "prix", "rendement", "superficie",
         "production")


def _contains(text: str, keyword: str) -> bool:
    """Recherche d'un mot entier (ou d'une expression) dans un texte normalisé."""
    return re.search(rf"(?<![a-z]){re.escape(normalize(keyword))}(?![a-z])", text) is not None


def _year_in_words(text: str) -> int | None:
    """Année dite en wolof (« ñaari junni ak ñaar fukk ak ñeent » -> 2024) ou en
    pulaar, telle que la transcription vocale l'écrit. Années 1990 à 2030."""
    from . import pulaar, wolof

    found, found_len = None, 0
    for number_words in (wolof.number_words, pulaar.number_words):
        for year in range(1990, 2031):
            words = normalize(number_words(year))
            # la plus longue l'emporte (2024 contient « … ak ñaar fukk » de 2020)
            # « … (ak|e) mot » juste après : nombre plus long mal transcrit
            # (« ujunaaje ɗiɗi e noogas » n'est pas 2000) -> ignoré.
            if len(words) > found_len and re.search(
                    rf"(?<![a-z]){re.escape(words)}(?![a-z])(?! (?:ak|e) [a-z])", text):
                found, found_len = year, len(words)
    return found


def _edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _close(keyword: str, words: list[str]) -> bool:
    """Mot wolof reconnu à une lettre près (« gertei » -> « gerte »).

    Réservé aux mots d'au moins 5 lettres : « basi » ou « ceeb » seraient confondus
    avec des mots courts (« bas »…). Mesuré sur la radio KALLAAMA : 25/30 mots-clés
    transcrits à l'identique, 26/30 à une lettre près.
    """
    if len(keyword) < 5 or " " in keyword:
        return False
    return any(abs(len(w) - len(keyword)) <= 1 and _edit_distance(keyword, w) <= 1
               for w in words)


def _find_place(text: str, index: dict[str, str]) -> str | None:
    """Renvoie le lieu le plus long cité dans le texte (évite 'Touba' vs 'Touba Toul')."""
    hits = [k for k in index if k and _contains(text, k)]
    return index[max(hits, key=len)] if hits else None


def parse(texts: list[str], kb: KnowledgeBase) -> Query:
    """Analyse une ou plusieurs versions d'une même question (wolof, français)."""
    text = " ".join(normalize(t) for t in texts if t)
    q = Query()

    for product in PRODUCTS:
        local = product.wo + OTHER_PRODUCT_KEYWORDS.get(product.key, ())
        if any(_contains(text, k) for k in product.fr + local):
            q.product = product.key
            break
    if q.product is None:  # la transcription vocale déforme parfois un mot wolof
        words = text.split()
        for product in PRODUCTS:
            local = product.wo + OTHER_PRODUCT_KEYWORDS.get(product.key, ())
            if any(_close(normalize(k), words) for k in local):
                q.product = product.key
                break

    # Texte pour la recherche dans les documents (en français) : on ajoute le nom
    # français du produit et les équivalents des mots locaux connus.
    extra = [PRODUCT_BY_KEY[q.product].label] if q.product else []
    extra += [fr for local, fr in LOCAL_GLOSS.items() if _contains(text, local)]
    q.text = " ".join([text] + [normalize(x) for x in extra])
    # Recherche de secours sur ce seul sens : des mots locaux (« def », « war ») existent
    # parfois dans les documents français et faussent la recherche sur la phrase entière.
    q.focus = " ".join(normalize(x) for x in extra)
    # Priorités : voir ORDER (« xeeti gerte yu mën a muñ ñàkk taw » = variétés).
    for intent in ORDER:
        if any(_contains(text, k) for k in INTENT_KEYWORDS[intent]):
            q.intent = intent
            break
    if q.intent is None:  # mot-clé déformé par la transcription (« cogu » -> « coggu »)
        words = text.split()
        for intent in ORDER:
            if any(_close(k, words) for k in INTENT_KEYWORDS[intent]):
                q.intent = intent
                q.intent_fuzzy = True  # « monde » ~ « soñde » : à confirmer (llm.py)
                break

    # « Où vendre ? » (fr), « fan laa wara jaay » (wo), « toy mi yeeyata » (pulaar,
    # À VALIDER), « meilleur marché », « quand vendre » : marché le plus rentable.
    if re.search(r"\b(ou|fan|toy|quel marche|quand|kan|ndey)\b.{0,40}"
                 r"\b(vendre|vend|jaay|yeey\w*)\b|meilleur marche|meilleur prix"
                 r"|\b(jaay|yeey\w*)\b.{0,30}\b(fan|toy)\b", text):
        q.intent = "vendre"

    # Précisions pour les conseils.
    if re.search(r"cycle court|precoce|hatif|rapide|\bgaaw|\byaaw", text):  # yaaw : pulaar
        q.cycle = "court"
    elif re.search(r"cycle long|tardi|\bneeb|\byaage", text):  # neeɓ pulaar, yaage sereer
        q.cycle = "long"
    q.drought = bool(re.search(
        r"secheresse|manque de pluie|peu de pluie|deficit|nakk taw|nakkum taw|nakku tobo"
        r"|ndob a tuuti", text))
    for topic, pattern in TOPICS.items():
        if re.search(pattern, q.text):  # avec les équivalents français des mots locaux
            q.topic = topic
            break
    # « kañ » (quand ?) + góob / ji : question de calendrier -> conseil
    # (« Kañ lañuy góob gerte ? » = « Quand récolte-t-on l'arachide ? »).
    if re.search(r"\bkan\b", text) and re.search(r"\bgoob|\bji\b|jiyee", text):
        q.intent = "conseil"
        q.topic = "recolte" if re.search(r"\bgoob", text) else "semis"
    # Pulaar (À VALIDER) : « ndey » (quand ?) + aawde (semer) / soñde, taƴde (récolter).
    if re.search(r"\bndey\b", text) and re.search(r"\baaw|\bsonde|\btayde", text):
        q.intent = "conseil"
        q.topic = "semis" if re.search(r"\baaw", text) else "recolte"

    years = re.findall(r"\b(19[6-9]\d|20[0-4]\d)\b", text)
    q.year = int(years[-1]) if years else _year_in_words(text)

    # Lieux : alias d'abord, puis marchés, départements, régions.
    for alias, place in PLACE_ALIASES.items():
        if _contains(text, alias):
            text += f" {normalize(place)}"
    indexes = (kb.markets, kb.departments, kb.regions, kb.price_regions, kb.localities)
    if not any(_find_place(text, idx) for idx in indexes):
        guess = _closest_place(text, indexes)  # « kalaak » (transcription) -> Kaolack
        if guess:
            text += f" {guess}"
    q.market = _find_place(text, kb.markets)
    q.department = _find_place(text, kb.departments)
    q.region = _find_place(text, kb.regions) or _find_place(text, kb.price_regions)
    q.locality = _find_place(text, kb.localities)

    # Salutation ou demande d'aide sans autre précision : « Jam waali », « bonjour ».
    if q.intent is None and q.product is None and any(
            _contains(text, k) for k in GREETING_KEYWORDS):
        q.intent = "salutation"

    # Intention par défaut : marché cité, ou « kilo » sans hectare -> prix ; sinon fiche.
    if q.intent is None and q.product:
        per_kilo = _contains(text, "kilo") and not re.search(r"ektaar|hectare", text)
        # Sans marché ni « kilo » : fiche de la culture (prix + production) plutôt
        # qu'une intention devinée au hasard.
        q.intent = "prix" if q.market or per_kilo else "fiche"
        q.intent_guessed = True
    return q


def _closest_place(text: str, indexes) -> str | None:
    """Lieu le plus proche d'un mot de la question (tolérance : 1 lettre jusqu'à 6
    lettres, 2 au-delà). Renvoie None en cas d'égalité ou si rien n'est assez proche."""
    names = {name for idx in indexes for name in idx if len(name) >= 5 and " " not in name}
    best, best_d, tie = None, 99, False
    for word in {w for w in text.split() if len(w) >= 5}:
        for name in names:
            # même initiale, longueur proche : évite « risque » -> Rufisque, « niakhar » -> Diakhao
            if name[0] != word[0] or abs(len(name) - len(word)) > 1:
                continue
            limit = 1 if len(name) <= 6 else 2
            d = _edit_distance(word, name)
            if d <= limit and d < best_d:
                best, best_d, tie = name, d, False
            elif d <= limit and d == best_d and name != best:
                tie = True
    return None if tie else best
