"""Met AgriBaat en ligne sur Hugging Face Spaces (gratuit, 16 Go de mémoire, 2 cœurs).

Prérequis (une seule fois) :
  1. Créer un compte sur https://huggingface.co, puis un jeton d'accès « Write »
     (Settings > Access Tokens).
  2. Dans PowerShell, AVANT de lancer ce script (jamais dans un fichier du dépôt) :
       $env:HF_TOKEN = "hf_..."                       # jeton Write
       $env:ANTHROPIC_API_KEY = "sk-ant-..."          # facultatif : IA générative
       $env:AGRIBAAT_TEAM_PASSWORD = "..."            # mot de passe de l'espace équipe

Usage (dans le dossier agribaat_app) :
  python deploy_space.py mon-compte/agribaat                # crée ou met à jour le Space
  python deploy_space.py mon-compte/agribaat --avec-caches  # + voix et réponses déjà calculées
  python deploy_space.py mon-compte/agribaat --sauvegarde mon-compte/agribaat-journal
      # + dépôt de données PRIVÉ pour garder le journal d'impact (option gratuite)

Ce que fait le script :
  - crée le Space (Gradio, public) s'il n'existe pas ;
  - envoie le dossier agribaat_app (sans outputs/, tests, enregistrements de test) avec
    un README d'en-tête propre au Space ;
  - copie la feuille des tests terrain (../test_terrain/resultats_test_terrain.csv) ;
  - enregistre les secrets du Space à partir des variables ci-dessus (rien n'est écrit
    dans les fichiers envoyés).

Après l'envoi, le Space se construit (5 à 10 min) puis télécharge les modèles de voix au
premier lancement (≈ 6 Go, encore quelques minutes).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parent
IGNORE = ["outputs/**", "tests/**", "test_voix/**", "__pycache__/**", "**/__pycache__/**",
          "*.avant_refonte", "resultats_test_voix.csv", ".pytest_cache/**", "README.md",
          "seed_cache/**", "*.log", "*.wav",
          ".venv/**", "venv/**", ".venv_win/**", ".env", ".git/**"]

SPACE_README = """---
title: AgriBaat
emoji: 🌾
colorFrom: green
colorTo: yellow
sdk: gradio
sdk_version: {gradio}
python_version: "3.12"
app_file: app.py
pinned: false
short_description: Assistant agricole vocal en wolof, pulaar et sereer
---

# AgriBaat — assistant agricole vocal (PAS Challenge 2026, équipe SMART AGRO)

Prix des marchés, météo en direct, calendrier de semis, où vendre, conseils de saison et
diagnostic photo, en wolof, pulaar, sereer et français. Aucun chiffre inventé : chaque
réponse cite sa source officielle (PAM, DAPSA, FAOSTAT, ANACIM, ISRA, Open-Meteo).
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("space", help="identifiant du Space, ex. mon-compte/agribaat")
    ap.add_argument("--avec-caches", action="store_true",
                    help="envoie aussi les voix et réponses de l'IA déjà calculées")
    ap.add_argument("--sauvegarde", metavar="DEPOT",
                    help="dépôt de données privé pour le journal (ex. mon-compte/agribaat-journal)")
    ap.add_argument("--prive", action="store_true", help="Space privé (pour un essai)")
    args = ap.parse_args()

    token = os.getenv("HF_TOKEN")
    if not token:
        print("Définissez d'abord HF_TOKEN (jeton Write de Hugging Face), voir l'aide.")
        return 1
    import gradio
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    api.create_repo(args.space, repo_type="space", space_sdk="gradio", private=args.prive,
                    exist_ok=True)
    print(f"Space : https://huggingface.co/spaces/{args.space}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "README.md").write_text(SPACE_README.format(gradio=gradio.__version__),
                                       encoding="utf-8")
        sheet = APP.parent / "test_terrain" / "resultats_test_terrain.csv"
        if sheet.exists():
            (tmp / "test_terrain").mkdir()
            shutil.copyfile(sheet, tmp / "test_terrain" / sheet.name)
        if args.avec_caches:
            out = APP / "outputs"
            seed = tmp / "seed_cache"
            if (out / "cache").is_dir():
                shutil.copytree(out / "cache", seed / "cache")
            for name in ("llm_cache.json", "saison_2024.json", "saison_2025.json"):
                if (out / name).exists():
                    seed.mkdir(exist_ok=True)
                    shutil.copyfile(out / name, seed / name)
        print("Envoi des fichiers de l'app…")
        api.upload_folder(folder_path=str(APP), repo_id=args.space, repo_type="space",
                          ignore_patterns=IGNORE, commit_message="Mise à jour d'AgriBaat")
        print("Envoi du README du Space, de la feuille terrain et des caches…")
        api.upload_folder(folder_path=str(tmp), repo_id=args.space, repo_type="space",
                          commit_message="README du Space et fichiers annexes")

    secrets = {k: os.getenv(k) for k in ("ANTHROPIC_API_KEY", "AGRIBAAT_TEAM_PASSWORD")}
    if args.sauvegarde:
        api.create_repo(args.sauvegarde, repo_type="dataset", private=True, exist_ok=True)
        secrets["AGRIBAAT_BACKUP_REPO"] = args.sauvegarde
        secrets["HF_TOKEN"] = token
        print(f"Dépôt privé du journal : https://huggingface.co/datasets/{args.sauvegarde}")
    for key, value in secrets.items():
        if value:
            api.add_space_secret(args.space, key, value)
            print(f"Secret enregistré : {key}")
    if not os.getenv("AGRIBAAT_TEAM_PASSWORD"):
        print("ATTENTION : pas de AGRIBAAT_TEAM_PASSWORD -> les contacts des abonnés seraient "
              "visibles par tous. Définissez-le puis relancez le script.")
    print("Terminé. Le Space se construit : suivez l'onglet « Logs » sur sa page.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
