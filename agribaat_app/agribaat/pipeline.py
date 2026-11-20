"""Enchaînement complet : voix/texte -> compréhension -> réponse -> voix.

Chaque étape est protégée : si un modèle manque, on continue en mode dégradé
(par exemple réponse en français sans audio) et on l'indique dans `warnings`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

import config
from . import labo, langues, models
from .answers import answer
from .knowledge import KnowledgeBase
from .nlu import parse


@dataclass
class Result:
    lang: str = "wo"  # langue locale de la réponse : wo | pul | srr
    question_wo: str = ""  # transcription ou saisie en langue locale (wolof, pulaar…)
    question_fr: str = ""  # traduction (ou saisie) française
    answer_fr: str = ""
    answer_wo: str = ""  # affichée (chiffres)
    speech_wo: str = ""  # lue par la synthèse vocale (nombres en lettres)
    audio: tuple[int, np.ndarray] | None = None
    source: str | None = None
    found: bool = False
    highlight: object | None = None  # chiffre clé (answers.Highlight)
    timings: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    intent: str = ""  # sujet compris (prix, pluie, météo…) : mesure d'impact


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

    def ask_audio(self, sr: int, audio: np.ndarray, lang: str = "wo") -> Result:
        """Question parlée. `lang` : wo (wolof) ou pul (pulaar, modèle du Labo)."""
        langue = langues.get(lang)
        res = Result(lang=langue.code)
        if langue.voice_in == "wolof":
            audio16 = self._timed(res, "audio", models.to_mono_16k, sr, audio)
            if audio16 is not None:
                res.question_wo = self._timed(res, "asr", models.transcribe, audio16) or ""
        elif langue.voice_in == "labo":
            res.question_wo = self._timed(res, "asr", labo.transcribe, langue.labo_key,
                                          sr, audio) or ""
        else:
            res.answer_fr = (f"Pas encore de reconnaissance vocale en {langue.label} : "
                             "tapez la question.")
            return res
        if not res.question_wo:
            res.answer_fr = "Je n'ai pas réussi à transcrire l'audio. Réessayez ou tapez la question."
            return res
        return self._answer(res, from_local=True)

    def ask_text(self, text: str, lang: str = "wo") -> Result:
        """Question écrite. `lang` : wo, pul, srr (langue locale) ou fr (réponse en wolof)."""
        res = Result(lang=lang if lang in langues.LANGUES else "wo")
        if lang == "fr":
            res.question_fr = text.strip()
        else:
            res.question_wo = text.strip()
        return self._answer(res, from_local=lang != "fr")

    def _answer(self, res: Result, from_local: bool) -> Result:
        langue = langues.get(res.lang)
        query = None
        if from_local and langue.code != "wo":
            # Pas de traduction automatique fiable pour le pulaar et le sereer :
            # la compréhension se fait sur les seuls mots-clés.
            query = parse([res.question_wo], self.kb)
        elif from_local:
            # Les mots-clés wolof suffisent souvent : on évite alors la traduction (lente
            # et parfois fausse). Sinon, la traduction française aide à comprendre.
            query = parse([res.question_wo], self.kb)
            # Intention seulement devinée (« dugub » sans mot-clé de prix, de pluie…) :
            # la traduction française peut révéler une question de pratique agricole.
            if not query.is_complete or query.intent_guessed:
                res.question_fr = self._timed(res, "traduction_wo_fr", models.translate,
                                              res.question_wo, config.LANG_WO,
                                              config.LANG_FR) or ""
                query = None
        start = time.perf_counter()
        query = query or parse([res.question_wo, res.question_fr], self.kb)
        ans = answer(query, self.kb, langue.module)
        res.intent = query.intent or ""
        res.timings["reponse"] = round(time.perf_counter() - start, 3)
        res.answer_fr, res.source, res.found = ans.text, ans.source, ans.found
        res.highlight = ans.highlight

        if ans.wolof is not None:  # réponse wolof construite à partir des données
            res.answer_wo, res.speech_wo = ans.wolof.text, ans.wolof.speech
        elif langue.code == "wo":  # secours : traduction automatique (à relire)
            res.answer_wo = self._timed(res, "traduction_fr_wo", models.translate,
                                        res.answer_fr, config.LANG_FR, config.LANG_WO) or ""
            res.speech_wo = res.answer_wo
            if res.answer_wo:
                res.warnings.append("Réponse wolof traduite automatiquement : à vérifier.")
        if langue.draft and res.answer_wo:
            res.warnings.append(f"Réponse {langue.label.lower()} : brouillon en cours de "
                                "relecture par un locuteur natif.")
        if self.speak and res.speech_wo and langue.voice_out == "wolof":
            res.audio = self._timed(res, "tts", models.synthesize, res.speech_wo)
        elif self.speak and res.speech_wo and langue.voice_out == "labo":
            res.audio = self._timed(res, "tts", labo.synthesize, langue.labo_key,
                                    res.speech_wo)
        res.timings["total"] = round(sum(v for k, v in res.timings.items() if k != "total"), 2)
        return res
