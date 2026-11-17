"""Lexique d'AgriBaat : produits, sources et mots-clés.

Les termes wolof sont volontairement peu nombreux : chacun doit être validé par
un locuteur natif avant la démo. Ajoutez des variantes orthographiques ici
(l'ASR ne produit pas toujours l'orthographe standard).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


def normalize(text: str) -> str:
    """Minuscules, sans accents, ponctuation remplacée par des espaces."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9ñŋ' -]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class Product:
    """Un produit agricole et ses correspondances dans chaque source."""

    key: str  # identifiant interne
    label: str  # libellé affiché (français)
    fr: tuple[str, ...]  # mots-clés français
    wo: tuple[str, ...]  # mots-clés wolof (À VALIDER)
    wfp: tuple[str, ...] = field(default_factory=tuple)  # libellés WFP
    fao: str | None = None  # libellé FAOSTAT
    dapsa: str | None = None  # libellé DAPSA


PRODUCTS: tuple[Product, ...] = (
    Product("mil", "mil", ("mil",), ("dugub",), ("Millet",), "Millet", "MIL"),
    Product("sorgho", "sorgho", ("sorgho",), ("basi",), ("Sorghum",), "Sorghum", "SORGHO"),
    Product("mais", "maïs", ("mais",), ("mboq", "mbooq"),
            ("Maize (local)", "Maize (imported)"), "Maize (corn)", "MAIS"),
    Product("riz", "riz", ("riz",), ("ceeb",),
            ("Rice (local)", "Rice (imported)"), "Rice", "RIZ"),
    Product("arachide", "arachide", ("arachide", "arachides", "cacahuete"),
            ("gerte",), ("Groundnuts (shelled)", "Groundnuts (unshelled)"),
            "Groundnuts, excluding shelled", "ARACHIDE"),
    Product("niebe", "niébé", ("niebe", "haricot", "haricots"),
            ("nebbe", "ñebbe"), ("Beans (niebe)",), "Cow peas, dry", "NIEBE"),
    Product("oignon", "oignon", ("oignon", "oignons"), ("soble",),
            ("Onions (dry)", "Onions (imported)"),
            "Onions and shallots, dry (excluding dehydrated)", None),
    Product("manioc", "manioc", ("manioc",), ("ñambi", "nambi"), ("Cassava",),
            "Cassava, fresh", "MANIOC"),
    Product("fonio", "fonio", ("fonio",), ("findi",), ("Fonio",), "Fonio", "FONIO"),
)

PRODUCT_BY_KEY: dict[str, Product] = {p.key: p for p in PRODUCTS}

# Mots-clés d'intention (déjà normalisés : sans accents, minuscules).
INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    # Wolof (À VALIDER) : njëg = prix, jar = coûter, jënd = acheter, jaay = vendre,
    # marse = marché ; benn ektaar = un hectare ; bey = cultiver ; góob/jur = récolter/produire.
    # Conseils (wolof À VALIDER) : taw = pluie, xeet = sorte/variété, jiwu = semence,
    # digal = conseiller, ji = semer.
    "pluie": ("pluie", "pluies", "plu", "pleut", "pleuvoir", "pluviometrie",
              "precipitation", "precipitations", "meteo", "taw"),
    "variete": ("variete", "varietes", "semence", "semences", "cycle court", "cycle long",
                "precoce", "precoces", "xeet", "xeeti", "jiwu"),
    "conseil": ("conseil", "conseils", "recommandation", "recommandations", "que faire",
                "quand semer", "semer", "semis", "recolter", "ravageur", "ravageurs",
                "traitement", "chenille", "chenilles", "oiseaux", "criquet", "criquets",
                "maladie", "maladies", "digal", "ndigal"),
    "prix": ("prix", "coute", "couter", "tarif", "cher", "vend", "vendre",
             "acheter", "marche", "njeg", "njegu", "jend", "jaay", "jar", "marse",
             "seer", "yomb"),
    "rendement": ("rendement", "par hectare", "kg ha", "kg/ha", "benn ektaar"),
    "superficie": ("superficie", "surface", "hectares", "cultive", "emblave", "ektaar",
                   "tool", "bey"),
    "production": ("production", "produit", "produire", "recolte", "tonnes",
                   "tonne", "combien de", "goob", "jur", "tonn"),
}

MONTHS_FR = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet",
             "août", "septembre", "octobre", "novembre", "décembre")
