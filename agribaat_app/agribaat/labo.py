"""Labo langues (expérimental) : pulaar et sereer.

But : laisser l'équipe essayer, avec de vraies voix, les modèles publics existants pour
ces langues (phase 2 et 3 du projet). Le Labo NE RÉPOND PAS aux questions : il montre
seulement ce que la reconnaissance vocale a compris, et fait lire une phrase par la
voix de synthèse quand il en existe une.

Les modèles sont choisis d'après l'évaluation sur la radio KALLAAMA (voir
FEUILLE_DE_ROUTE_LANGUES.md). Un seul modèle de Labo est gardé en mémoire à la fois.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass

import numpy as np

from . import models


@dataclass(frozen=True)
class LabLanguage:
    key: str
    label: str
    asr_model: str | None
    tts_model: str | None
    example: str  # phrase d'exemple pour la voix de synthèse


LANGUAGES: dict[str, LabLanguage] = {
    "pulaar": LabLanguage(
        "pulaar", "Pulaar",
        asr_model=os.getenv("AGRIBAAT_LABO_ASR_PULAAR", "Leonel-Maia/Wav2vec2-fula"),
        tts_model=os.getenv("AGRIBAAT_LABO_TTS_PULAAR", "facebook/mms-tts-ful"),
        example="Jam waali. Hol no coggu gawri woni hannde e luumo Kawlak?"),
    "sereer": LabLanguage(
        "sereer", "Sereer",
        # Aucun modèle public utilisable (vérifié le 18/11/2026 : les modèles sereer
        # publiés n'ont pas de vocabulaire, et MMS n'a pas d'adaptateur sereer).
        asr_model=os.getenv("AGRIBAAT_LABO_ASR_SEREER") or None,
        tts_model=None,  # pas de voix de synthèse sereer fiable à ce jour
        example=""),
}

_lock = threading.Lock()
_loaded: dict[str, object] = {}  # un seul modèle de Labo à la fois (mémoire)


def _get(kind: str, model_id: str):
    """Charge (ou réutilise) le modèle demandé en libérant le précédent."""
    key = f"{kind}:{model_id}"
    with _lock:
        if key not in _loaded:
            _loaded.clear()  # libère l'ancien modèle avant d'en charger un autre
            try:
                if kind == "asr":
                    from transformers import pipeline

                    _loaded[key] = pipeline("automatic-speech-recognition", model=model_id,
                                            device=-1)
                else:
                    from transformers import AutoTokenizer, VitsModel

                    _loaded[key] = (AutoTokenizer.from_pretrained(model_id),
                                    VitsModel.from_pretrained(model_id).eval())
            except Exception as exc:  # noqa: BLE001
                raise models.ModelUnavailable(f"Modèle indisponible ({model_id}) : {exc}") \
                    from exc
        return _loaded[key]


def transcribe(lang: str, sr: int, audio: np.ndarray) -> str:
    """Parole (pulaar / sereer) -> texte, avec le modèle du Labo pour cette langue."""
    language = LANGUAGES[lang]
    if not language.asr_model:
        raise models.ModelUnavailable(f"Pas de reconnaissance vocale pour le {language.label}.")
    audio16 = models.to_mono_16k(sr, audio)
    asr = _get("asr", language.asr_model)
    return asr({"raw": audio16, "sampling_rate": models.TARGET_SR})["text"].strip()


def synthesize(lang: str, text: str) -> tuple[int, np.ndarray]:
    """Texte -> voix de synthèse (MMS / VITS). Pulaar seulement pour l'instant."""
    import torch

    language = LANGUAGES[lang]
    if not language.tts_model:
        raise models.ModelUnavailable(f"Pas de voix de synthèse pour le {language.label}.")
    if not text.strip():
        raise ValueError("Texte vide.")
    tokenizer, model = _get("tts", language.tts_model)
    with torch.no_grad():
        wave = model(**tokenizer(text, return_tensors="pt")).waveform[0].numpy()
    return int(model.config.sampling_rate), wave.astype(np.float32)
