"""Diagnostic : pourquoi l'app ne démarre pas ?

Usage (dans le dossier agribaat_app) :
    python diagnostic.py

Vérifie, dans l'ordre : la version de Python, les bibliothèques, l'état Git (fichiers
en conflit après un « git pull »), les données, puis le chargement de l'app.
Copiez tout ce qui s'affiche et envoyez-le si un point est en ERREUR.
"""

from __future__ import annotations

import importlib
import platform
import re
import subprocess
import sys
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent
ROOT = APP.parent
problems: list[str] = []


def ok(label: str, detail: str = "") -> None:
    print(f"[ OK  ] {label} {detail}")


def bad(label: str, detail: str, fix: str) -> None:
    print(f"[ERREUR] {label} {detail}\n         -> {fix}")
    problems.append(label)


def version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", text)[:3])


# 1. Python
print(f"Système : {platform.system()} {platform.release()}")
if sys.version_info >= (3, 10):
    ok("Python", platform.python_version())
else:
    bad("Python", platform.python_version(), "installer Python 3.10 ou plus récent")

# 2. Bibliothèques
REQUIRED = {"pandas": "2.0", "gradio": "5.30", "numpy": "1.24", "soundfile": "0.12"}
OPTIONAL = {"torch": "2.1", "transformers": "4.44", "huggingface_hub": "0.23"}
for name, minimum in {**REQUIRED, **OPTIONAL}.items():
    try:
        module = importlib.import_module(name)
        version = getattr(module, "__version__", "?")
        if version != "?" and version_tuple(version) < version_tuple(minimum):
            bad(name, f"{version} (il faut ≥ {minimum})",
                f'pip install -U "{name}>={minimum}"' + (' "gradio<6"' if name == "gradio" else ""))
        else:
            ok(name, version)
    except Exception as exc:  # noqa: BLE001
        if name in REQUIRED:
            bad(name, f"absent ou cassé ({exc})", "pip install -r requirements.txt")
        else:
            print(f"[ info] {name} absent : l'app marchera sans la voix ({exc})")

# 3. Git : conflits après un « git pull »
try:
    status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=30).stdout
    conflicts = [line[3:] for line in status.splitlines() if line[:2] in ("UU", "AA", "DU", "UD")]
    marked = [str(p.relative_to(ROOT)) for p in list(APP.rglob("*.py")) + [ROOT / "GUIDE_DEMO.md"]
              if p.exists() and re.search(r"^<{7} ", p.read_text(encoding="utf-8", errors="ignore"),
                                          re.M)]
    if conflicts or marked:
        bad("Git", f"fichiers en conflit : {', '.join(sorted(set(conflicts + marked)))}",
            "l'historique GitHub a été réécrit : voir « Remettre la copie à jour » dans "
            "GUIDE_DEMO.md (git fetch origin puis git reset --hard origin/main)")
    else:
        head = subprocess.run(["git", "log", "-1", "--format=%h %s"], cwd=ROOT,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=30).stdout.strip()
        ok("Git", f"pas de conflit (version : {head})")
except Exception as exc:  # noqa: BLE001
    print(f"[ info] Git non vérifié ({exc})")

# 4. Données
needed = ["prices.csv", "national.csv", "regional.csv"]
missing = [n for n in needed if not (APP / "data" / "processed" / n).exists()]
if missing:
    bad("Données", f"manquantes : {', '.join(missing)}", "python prepare_data.py")
else:
    ok("Données", "tables de base présentes")
for extra in ("pluies.csv", "recommandations.csv", "passages.csv"):
    if not (APP / "data" / "processed" / extra).exists():
        print(f"[ info] {extra} absent : onglet Conseils limité (git pull ou prepare_data.py)")

# 5. Chargement de l'app (sans la lancer)
if not problems:
    try:
        import os

        os.environ["AGRIBAAT_WARMUP"] = "0"  # pas de chargement des modèles ici
        sys.path.insert(0, str(APP))
        importlib.import_module("app")
        ok("App", "se charge correctement : lancez python app.py")
    except Exception:  # noqa: BLE001
        bad("App", "ne se charge pas :", "envoyer le message ci-dessous")
        traceback.print_exc()

print("\nRésultat :", "tout est bon." if not problems else f"{len(problems)} problème(s) : "
      + ", ".join(problems))
