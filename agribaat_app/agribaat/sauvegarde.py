"""Sauvegarde du journal d'impact vers un dépôt Hugging Face PRIVÉ (option gratuite).

En ligne, sans stockage persistant, le disque du Space est effacé à chaque redémarrage :
le journal d'usage, les avis et les abonnés seraient perdus. Ce module :
- au démarrage, récupère ces fichiers depuis le dépôt de données privé (s'ils manquent) ;
- toutes les 10 minutes, renvoie ceux qui ont changé.

Activé seulement si deux secrets sont définis : HF_TOKEN (jeton « write » du compte
Hugging Face) et AGRIBAAT_BACKUP_REPO (ex. « mon-compte/agribaat-journal », dépôt de
type dataset, créé PRIVÉ — il contient les contacts des abonnés). Sinon, rien ne se passe.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import threading

import config

FILES = ("journal_usage.csv", "journal_avis.csv", "abonnes.csv")
EVERY_S = 600
log = logging.getLogger("agribaat.sauvegarde")
_sent: dict[str, str] = {}


def settings() -> tuple[str, str] | None:
    repo, token = os.getenv("AGRIBAAT_BACKUP_REPO", ""), os.getenv("HF_TOKEN", "")
    return (repo, token) if repo and token else None


def _digest(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def restore() -> list[str]:
    """Récupère les fichiers absents en local. Renvoie la liste des fichiers récupérés."""
    conf = settings()
    if conf is None:
        return []
    repo, token = conf
    from huggingface_hub import hf_hub_download

    out, done = config.OUTPUTS_DIR, []
    out.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        if (out / name).exists():
            continue
        try:
            got = hf_hub_download(repo, name, repo_type="dataset", token=token)
        except Exception as exc:  # fichier pas encore sauvegardé, réseau…
            log.info("sauvegarde : %s non récupéré (%s)", name, type(exc).__name__)
            continue
        shutil.copyfile(got, out / name)
        _sent[name] = _digest(out / name)
        done.append(name)
    return done


def backup(api=None) -> list[str]:
    """Envoie les fichiers qui ont changé depuis le dernier envoi."""
    conf = settings()
    if conf is None:
        return []
    repo, token = conf
    if api is None:
        from huggingface_hub import HfApi

        api = HfApi()
    sent = []
    for name in FILES:
        path = config.OUTPUTS_DIR / name
        if not path.exists():
            continue
        digest = _digest(path)
        if _sent.get(name) == digest:
            continue
        try:
            api.upload_file(path_or_fileobj=str(path), path_in_repo=name, repo_id=repo,
                            repo_type="dataset", token=token,
                            commit_message=f"Sauvegarde {name}")
        except Exception as exc:
            log.warning("sauvegarde : envoi de %s impossible (%s)", name, exc)
            continue
        _sent[name] = digest
        sent.append(name)
    return sent


def seed_caches() -> int:
    """Copie les caches livrés avec l'app (seed_cache/ : voix déjà calculées, réponses de
    l'IA) dans le dossier de travail, sans écraser l'existant. Renvoie le nombre de fichiers."""
    seed = config.APP_DIR / "seed_cache"
    if not seed.is_dir():
        return 0
    n = 0
    for src in seed.rglob("*"):
        dst = config.OUTPUTS_DIR / src.relative_to(seed)
        if src.is_file() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            n += 1
    return n


def start() -> bool:
    """Récupère puis lance la sauvegarde périodique (thread en arrière-plan)."""
    if settings() is None:
        return False
    restore()

    def loop():
        stop = threading.Event()
        while not stop.wait(EVERY_S):
            backup()
    threading.Thread(target=loop, name="agribaat-sauvegarde", daemon=True).start()
    return True
