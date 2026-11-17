"""Compréhension de la question : intention + produit + lieu + année.

Approche par mots-clés, volontairement simple et prévisible. Elle analyse à la
fois le texte wolof (sortie de l'ASR) et sa traduction française : un mot-clé
trouvé dans l'un ou l'autre suffit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .knowledge import TOPICS, KnowledgeBase
from .lexicon import INTENT_KEYWORDS, PRODUCTS, normalize

# Alias de lieux : orthographes courantes -> nom dans les données.
PLACE_ALIASES: dict[str, str] = {
    "ziguinchor": "Zigiunchor",  # orthographe du fichier WFP
    "thies": "Thies",
    "saint louis": "Saint-Louis",
    "ndar": "Saint-Louis",  # nom wolof de Saint-Louis (À VALIDER)
}


@dataclass
class Query:
    intent: str | None = None  # prix | production | rendement | superficie
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

    @property
    def is_complete(self) -> bool:
        if self.intent in ("pluie", "conseil"):  # pas besoin de produit
            return True
        return self.intent is not None and self.product is not None


def _contains(text: str, keyword: str) -> bool:
    """Recherche d'un mot entier (ou d'une expression) dans un texte normalisé."""
    return re.search(rf"(?<![a-z]){re.escape(normalize(keyword))}(?![a-z])", text) is not None


def _find_place(text: str, index: dict[str, str]) -> str | None:
    """Renvoie le lieu le plus long cité dans le texte (évite 'Touba' vs 'Touba Toul')."""
    hits = [k for k in index if k and _contains(text, k)]
    return index[max(hits, key=len)] if hits else None


def parse(texts: list[str], kb: KnowledgeBase) -> Query:
    """Analyse une ou plusieurs versions d'une même question (wolof, français)."""
    text = " ".join(normalize(t) for t in texts if t)
    q = Query()

    for product in PRODUCTS:
        if any(_contains(text, k) for k in product.fr + product.wo):
            q.product = product.key
            break

    q.text = text
    for intent in ("pluie", "variete", "conseil", "prix", "rendement", "superficie",
                   "production"):
        if any(_contains(text, k) for k in INTENT_KEYWORDS[intent]):
            q.intent = intent
            break

    # Précisions pour les conseils.
    if re.search(r"cycle court|precoce|hatif|rapide|\bgaaw", text):
        q.cycle = "court"
    elif re.search(r"cycle long|tardi", text):
        q.cycle = "long"
    q.drought = bool(re.search(r"secheresse|manque de pluie|peu de pluie|deficit", text))
    for topic, pattern in TOPICS.items():
        if re.search(pattern, text):
            q.topic = topic
            break

    years = re.findall(r"\b(19[6-9]\d|20[0-4]\d)\b", text)
    q.year = int(years[-1]) if years else None

    # Lieux : alias d'abord, puis marchés, départements, régions.
    for alias, place in PLACE_ALIASES.items():
        if _contains(text, alias):
            text += f" {normalize(place)}"
    q.market = _find_place(text, kb.markets)
    q.department = _find_place(text, kb.departments)
    q.region = _find_place(text, kb.regions) or _find_place(text, kb.price_regions)
    q.locality = _find_place(text, kb.localities)

    # Intention par défaut : un marché cité -> prix ; sinon production.
    if q.intent is None and q.product:
        q.intent = "prix" if q.market else "production"
    return q
