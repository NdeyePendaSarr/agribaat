"""Configuration d'AgriBaat. Chaque valeur peut être remplacée par une variable
d'environnement du même nom (ex. AGRIBAAT_ASR_MODEL=...)."""

from __future__ import annotations

import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent

# Données brutes : par défaut le dossier data_agribaat voisin (E:\AGRIBAAT\data_agribaat).
RAW_DATA_DIR = Path(os.getenv("AGRIBAAT_RAW_DATA", APP_DIR.parent / "data_agribaat"))
PROCESSED_DIR = Path(os.getenv("AGRIBAAT_PROCESSED", APP_DIR / "data" / "processed"))

# Modèles pré-entraînés (aucun entraînement). Téléchargés au premier lancement.
# ASR par défaut : Wolof-HuBERT (94 M de paramètres, ~0,4 Go, quelques secondes sur CPU).
# Sur une machine de 16 Go, alternatives plus précises mais bien plus lourdes :
#   asr-africa/wav2vec2-xls-r-wolof-kallaama-fleurs-51-hours  (315 M, radio agricole)
#   bilalfaye/wav2vec2-large-mms-1b-wolof                    (964 M, ~4 Go)
ASR_MODEL = os.getenv("AGRIBAAT_ASR_MODEL", "soynade-research/Wolof-HuBERT-CTC")
MT_MODEL = os.getenv("AGRIBAAT_MT_MODEL", "facebook/nllb-200-distilled-600M")
TTS_MODEL = os.getenv("AGRIBAAT_TTS_MODEL", "bilalfaye/speecht5_tts-wolof-v0.2")
TTS_VOCODER = os.getenv("AGRIBAAT_TTS_VOCODER", "microsoft/speecht5_hifigan")

# Empreinte vocale (x-vector) utilisée par SpeechT5. Créée par check_models.py.
SPEAKER_EMBEDDING = Path(os.getenv("AGRIBAAT_SPEAKER_EMBEDDING",
                                   APP_DIR / "data" / "speaker_embedding.npy"))

# Codes de langue NLLB.
LANG_WO = "wol_Latn"
LANG_FR = "fra_Latn"
