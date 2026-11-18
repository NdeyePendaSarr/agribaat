"""Langues de l'Assistant : wolof, pulaar et sereer.

Phrases pulaar et sereer relues et approuvées par Mouhameth Diop (pulaar) et
Seydina Wade (sereer) le 18/11/2026.

Chaque langue a un module de phrases (wolof.py, pulaar.py, sereer.py) et, quand ils
existent, des modèles de reconnaissance vocale et de voix de synthèse.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType

from . import pulaar, sereer, wolof


@dataclass(frozen=True)
class Langue:
    code: str  # wo | pul | srr
    label: str
    module: ModuleType  # gabarits de réponse
    voice_in: str | None  # "wolof" (models.py), "labo" (labo.py) ou None
    voice_out: str | None
    draft: bool  # phrases pas encore relues par un locuteur
    labo_key: str | None = None  # clé dans labo.LANGUAGES


LANGUES: dict[str, Langue] = {
    "wo": Langue("wo", "Wolof", wolof, "wolof", "wolof", draft=False),
    "pul": Langue("pul", "Pulaar", pulaar, "labo", "labo", draft=False, labo_key="pulaar"),
    "srr": Langue("srr", "Sereer", sereer, None, None, draft=False, labo_key="sereer"),
}


def get(code: str) -> Langue:
    return LANGUES.get(code, LANGUES["wo"])
