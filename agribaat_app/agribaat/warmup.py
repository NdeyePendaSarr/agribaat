"""Préparation en arrière-plan au démarrage de l'app.

1. charge les modèles vocaux (synthèse, reconnaissance) ;
2. prépare les réponses vocales des questions types et les met en cache disque.

Sur un petit processeur (2 cœurs), une réponse vocale prend 30 s à 2 min ; une fois
en cache, elle est relue instantanément. Le cache survit aux redémarrages.
Désactivation : AGRIBAAT_WARMUP=0.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field

from . import models


@dataclass
class WarmupStatus:
    state: str = "en attente"  # en attente | chargement | préparation | prêt | erreur | désactivé
    done: int = 0
    total: int = 0
    seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    @property
    def finished(self) -> bool:
        return self.state in ("prêt", "erreur", "désactivé")


def run(assistant, questions: list[tuple[str, str]], status: WarmupStatus) -> None:
    """Exécute la préparation (bloquant). `questions` : [(texte, 'fr' | 'wo'), …]."""
    start = time.perf_counter()
    try:
        status.state = "chargement"
        models._tts()
        try:
            models._asr()
        except models.ModelUnavailable as exc:  # la voix reste utile sans ASR
            status.errors.append(str(exc))
        status.state, status.total = "préparation", len(questions)
        for text, lang in questions:
            res = assistant.ask_text(text, lang)  # synthèse -> cache disque
            status.errors += [w for w in res.warnings if w not in status.errors]
            status.done += 1
        status.state = "prêt"
    except Exception as exc:  # noqa: BLE001 — l'app doit continuer à fonctionner
        status.state = "erreur"
        status.errors.append(str(exc))
    finally:
        status.seconds = round(time.perf_counter() - start, 1)


def start(assistant, questions: list[tuple[str, str]]) -> WarmupStatus:
    """Lance la préparation dans un fil d'exécution séparé et renvoie son état."""
    status = WarmupStatus()
    if os.getenv("AGRIBAAT_WARMUP", "1") == "0":
        status.state = "désactivé"
        return status
    threading.Thread(target=run, args=(assistant, questions, status),
                     name="agribaat-warmup", daemon=True).start()
    return status
