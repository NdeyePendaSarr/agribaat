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


def _get(kind: str, model_id: str, lang: str = ""):
    """Charge (ou réutilise) le modèle demandé. Les deux modèles d'une même langue
    (reconnaissance + voix) restent en mémoire ensemble ; ceux d'une autre langue
    sont libérés avant."""
    key = f"{lang}:{kind}:{model_id}"
    with _lock:
        if key not in _loaded:
            for old in [k for k in _loaded if not k.startswith(f"{lang}:")]:
                del _loaded[old]  # libère la mémoire de l'autre langue
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
    asr = _get("asr", language.asr_model, lang)
    return asr({"raw": audio16, "sampling_rate": models.TARGET_SR})["text"].strip()


def _cache_path(model_id: str, text: str):
    import hashlib

    key = hashlib.sha1(f"{model_id}|{text}".encode("utf-8")).hexdigest()[:20]
    return models.CACHE_DIR / f"{key}.wav"


def synthesize(lang: str, text: str) -> tuple[int, np.ndarray]:
    """Texte -> voix de synthèse (MMS / VITS), phrase par phrase. Pulaar seulement pour
    l'instant. Les audios produits sont gardés sur disque, comme pour le wolof."""
    import soundfile as sf

    language = LANGUAGES[lang]
    if not language.tts_model:
        raise models.ModelUnavailable(f"Pas de voix de synthèse pour le {language.label}.")
    if not text.strip():
        raise ValueError("Texte vide.")
    cached = _cache_path(language.tts_model, text)
    if cached.exists():
        audio, sr = sf.read(cached, dtype="float32")
        return sr, audio

    import torch

    tokenizer, model = _get("tts", language.tts_model, lang)
    sr = int(model.config.sampling_rate)
    silence = np.zeros(int(0.2 * sr), dtype=np.float32)
    pieces: list[np.ndarray] = []
    # La voix MMS « ful » ne connaît pas « ñ » (orthographe du Sénégal) : on l'écrit « ny »,
    # comme au Nigeria ; sinon la lettre serait sautée (« ñebbe » lu « ebbe »).
    spoken = text.replace("ñ", "ny").replace("Ñ", "Ny")
    for chunk in models.split_sentences(spoken):
        inputs = tokenizer(chunk, return_tensors="pt")
        if inputs["input_ids"].shape[-1] == 0:  # que des caractères inconnus du modèle
            continue
        with torch.no_grad():
            pieces += [model(**inputs).waveform[0].numpy().astype(np.float32), silence]
    if not pieces:
        raise models.ModelUnavailable("Texte illisible par la voix de synthèse.")
    audio = np.concatenate(pieces)
    try:
        models.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        sf.write(cached, audio, sr)
    except OSError:  # cache facultatif
        pass
    return sr, audio
