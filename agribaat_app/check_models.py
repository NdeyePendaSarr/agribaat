"""Étape 2 : télécharge et teste chaque modèle, un par un.

Usage : python check_models.py
Le premier lancement télécharge environ 6 Go (une seule fois, mis en cache).
Résultat : un tableau OK / ERREUR et un fichier de test outputs/test_tts.wav.
"""

from __future__ import annotations

import time
import traceback


import config
from agribaat import models

OUT = config.APP_DIR / "outputs"


def step(name: str, fn):
    start = time.perf_counter()
    try:
        detail = fn()
        print(f"[ OK  ] {name:<22} {time.perf_counter() - start:6.1f}s  {detail}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[ERREUR] {name:<22} {exc}")
        traceback.print_exc(limit=1)
        return False


def check_mt() -> str:
    fr = "Quel est le prix du mil à Kaolack ?"
    wo = models.translate(fr, config.LANG_FR, config.LANG_WO)
    back = models.translate(wo, config.LANG_WO, config.LANG_FR)
    return f"FR→WO : « {wo} » | retour : « {back} »"


def check_tts() -> str:
    import soundfile as sf

    sr, audio = models.synthesize("Mas naa jaay lii.")
    OUT.mkdir(exist_ok=True)
    sf.write(OUT / "test_tts.wav", audio, sr)
    return f"{len(audio) / sr:.1f}s d'audio -> {OUT / 'test_tts.wav'}"


def check_asr() -> str:
    wav = OUT / "test_tts.wav"
    if not wav.exists():
        return "ignoré (pas de fichier test_tts.wav)"
    import soundfile as sf

    audio, sr = sf.read(wav, dtype="float32")
    text = models.transcribe(models.to_mono_16k(sr, audio))
    return f"transcription de test_tts.wav : « {text} »"


if __name__ == "__main__":
    print(f"ASR : {config.ASR_MODEL}\nMT  : {config.MT_MODEL}\nTTS : {config.TTS_MODEL}\n")
    results = [
        step("Empreinte vocale", lambda: f"{models.load_speaker_embedding().shape}"),
        step("Traduction NLLB", check_mt),
        step("Synthèse vocale", check_tts),
        step("Reconnaissance ASR", check_asr),
    ]
    print("\nTout est prêt." if all(results) else "\nCertains modèles ont échoué : "
          "envoie ce rapport pour diagnostic.")
