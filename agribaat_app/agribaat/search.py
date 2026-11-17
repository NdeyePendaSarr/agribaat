"""Recherche de passages (secours pour les questions ouvertes).

Index BM25 en Python pur (aucune bibliothèque compilée, aucun modèle) sur les
documents utiles de l'ISRA et de l'ANACIM. La réponse est un EXTRAIT cité, jamais
un texte généré : rien n'est inventé.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .lexicon import normalize

STOPWORDS = set("""
au aux avec ce ces dans de des du elle en et eux il ils je la le les leur lui ma mais me
meme mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta te
tes toi ton tu un une vos votre vous est sont ete etre avoir a ont fait faire comme plus
moins tres tout tous toute toutes cette cet aussi bien entre sans sous chez donc alors
quel quelle quels quelles comment combien quand pourquoi dois doit faut peut peux
""".split())


def tokens(text: str) -> list[str]:
    return [w for w in normalize(text).split() if len(w) > 2 and w not in STOPWORDS]


@dataclass
class Passage:
    text: str
    source: str
    score: float


class PassageIndex:
    """BM25 (k1 = 1,5 ; b = 0,75) sur des passages d'environ 120 mots."""

    def __init__(self, passages: pd.DataFrame) -> None:
        self.passages = passages.reset_index(drop=True)
        self.docs = [Counter(tokens(t)) for t in self.passages.get("texte", [])]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg = (sum(self.lengths) / len(self.lengths)) if self.docs else 0
        df = Counter(w for d in self.docs for w in d)
        n = len(self.docs)
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}

    @classmethod
    def load(cls, path: Path) -> "PassageIndex":
        return cls(pd.read_csv(path) if path.exists() else pd.DataFrame(columns=["texte", "source"]))

    def best(self, question: str, min_score: float = 6.0) -> Passage | None:
        """Meilleur passage, ou None si rien n'est assez proche de la question."""
        query = {w for w in tokens(question) if w in self.idf}
        if not query or not self.docs:
            return None
        # Garde-fous : le mot le plus rare de la question (le plus distinctif) doit
        # figurer dans le passage, ainsi que la moitié au moins des mots.
        key_word = max(query, key=lambda w: self.idf[w])
        k1, b = 1.5, 0.75
        best_i, best = -1, 0.0
        for i, doc in enumerate(self.docs):
            matched = sum(w in doc for w in query)
            if key_word not in doc or matched * 2 < len(query) or matched < min(2, len(query)):
                continue
            score = 0.0
            norm = k1 * (1 - b + b * self.lengths[i] / self.avg)
            for w in query:
                f = doc.get(w)
                if f:
                    score += self.idf[w] * f * (k1 + 1) / (f + norm)
            if score > best:
                best_i, best = i, score
        if best_i < 0 or best < min_score:
            return None
        row = self.passages.iloc[best_i]
        return Passage(str(row["texte"]), str(row["source"]), round(best, 1))


# ------------------------------------------------------------ préparation
# Documents utiles seulement (le reste du corpus ISRA est administratif).
ISRA_DOCS = {
    "i0062f01.txt": "Catalogue ouest-africain des variétés (mil, sorgho)",
    "i0062f03.txt": "Catalogue ouest-africain des variétés (arachide, niébé)",
    "93928-ISRA-brochures-210x297mm-BAT.txt": "ISRA, brochure",
    "Rapport-annuel-des-activites-de-lISRA-2025.txt": "ISRA, rapport annuel 2025",
    "Rencontres-francophones-legumineuses-4.txt": "Rencontres francophones sur les légumineuses",
}
ISRA_PATTERNS = (r"lettre[-_]de[-_]l", )


def _label(path: Path) -> str | None:
    name = path.name
    if path.parent.name == "anacim":
        parts = name.removesuffix(".txt").split("_")  # bulletin_dec1_aout_2026
        if len(parts) == 4:
            return f"ANACIM, bulletin agrométéorologique ({parts[1]} {parts[2]} {parts[3]})"
        return "ANACIM, bulletin agrométéorologique"
    if name in ISRA_DOCS:
        return ISRA_DOCS[name]
    if any(re.search(p, name, re.I) for p in ISRA_PATTERNS):
        num = re.search(r"(\d+)", name)
        return f"Lettre de l'ISRA n° {num.group(1)}" if num else "Lettre de l'ISRA"
    return None


def prepare_passages(text_dir: Path, size: int = 120, overlap: int = 30) -> pd.DataFrame:
    """Découpe les documents utiles en passages qui se chevauchent."""
    rows = []
    for folder in ("isra", "anacim"):
        for path in sorted((text_dir / folder).glob("*.txt")):
            label = _label(path)
            if label is None:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            text = re.sub(r"-\s*\n\s*", "", text)
            words = text.split()
            for start in range(0, max(len(words) - overlap, 1), size - overlap):
                chunk = " ".join(words[start:start + size])
                if len(chunk) > 200:
                    rows.append({"texte": chunk, "source": label})
    return pd.DataFrame(rows, columns=["texte", "source"])
