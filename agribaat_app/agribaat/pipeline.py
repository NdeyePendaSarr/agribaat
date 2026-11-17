"""Enchaînement complet : voix/texte -> compréhension -> réponse -> voix.

Chaque étape est protégée : si un modèle manque, on continue en mode dégradé
(par exemple réponse en français sans audio) et on l'indique dans `warnings`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

import config
from . import models
from .answers import answer
from .knowledge import KnowledgeBase
from .nlu import parse


@dataclass
class Result:
    question_wo: str = ""  # transcription ou saisie wolof
    question_fr: str = ""  # traduction (ou saisie) française
    answer_fr: str = ""
    answer_wo: str = ""  # affichée (chiffres)
    speech_wo: str = ""  # lue par la synthèse vocale (nombres en lettres)
    audio: tuple[int, np.ndarray] | None = None
    source: str | None = None
    found: bool = False
    timings: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class Assistant:
    def __init__(self, kb: KnowledgeBase, speak: bool = True) -> None:
        self.kb = kb
        self.speak = speak

    def _timed(self, res: Result, step: str, fn, *args):
        """Exécute une étape, mesure sa durée, capture l'indisponibilité d'un modèle."""
        start = time.perf_counter()
        try:
            return fn(*args)
        except models.ModelUnavailable as exc:
            res.warnings.append(str(exc))
            return None
        except ImportError as exc:  # torch/transformers non installés : mode texte seul
            res.warnings.append(f"Étape « {step} » ignorée : {exc}. "
                                "Installez les dépendances (pip install -r requirements.txt).")
            return None
        finally:
            res.timings[step] = round(time.perf_counter() - start, 2)

    def ask_audio(self, sr: int, audio: np.ndarray) -> Result:
        res = Result()
        audio16 = self._timed(res, "audio", models.to_mono_16k, sr, audio)
        if audio16 is not None:
            res.question_wo = self._timed(res, "asr", models.transcribe, audio16) or ""
        if not res.question_wo:
            res.answer_fr = "Je n'ai pas réussi à transcrire l'audio. Réessayez ou tapez la question."
            return res
        return self._answer(res, from_wolof=True)

    def ask_text(self, text: str, lang: str = "wo") -> Result:
        res = Result()
        if lang == "wo":
            res.question_wo = text.strip()
        else:
            res.question_fr = text.strip()
        return self._answer(res, from_wolof=lang == "wo")

    def _answer(self, res: Result, from_wolof: bool) -> Result:
        query = None
        if from_wolof:
            # Les mots-clés wolof suffisent souvent : on évite alors la traduction (lente
            # et parfois fausse). Sinon, la traduction française aide à comprendre.
            query = parse([res.question_wo], self.kb)
            if not query.is_complete:
                res.question_fr = self._timed(res, "traduction_wo_fr", models.translate,
                                              res.question_wo, config.LANG_WO,
                                              config.LANG_FR) or ""
                query = None
        start = time.perf_counter()
        query = query or parse([res.question_wo, res.question_fr], self.kb)
        ans = answer(query, self.kb)
        res.timings["reponse"] = round(time.perf_counter() - start, 3)
        res.answer_fr, res.source, res.found = ans.text, ans.source, ans.found

        if ans.wolof is not None:  # réponse wolof construite à partir des données
            res.answer_wo, res.speech_wo = ans.wolof.text, ans.wolof.speech
        else:  # secours : traduction automatique (à relire)
            res.answer_wo = self._timed(res, "traduction_fr_wo", models.translate,
                                        res.answer_fr, config.LANG_FR, config.LANG_WO) or ""
            res.speech_wo = res.answer_wo
            if res.answer_wo:
                res.warnings.append("Réponse wolof traduite automatiquement : à vérifier.")
        if self.speak and res.speech_wo:
            res.audio = self._timed(res, "tts", models.synthesize, res.speech_wo)
        res.timings["total"] = round(sum(v for k, v in res.timings.items() if k != "total"), 2)
        return res
