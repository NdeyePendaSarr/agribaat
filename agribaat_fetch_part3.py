#!/usr/bin/env python3
"""
AgriBaat – partie 3 : ce qui manque + récapitulatif DS-01 .. DS-13.

  alffa     DS-01 ALFFA Wolof (git, dépôt getalp/ALFFA_PUBLIC, dossier ASR/WOLOF)
  wolofdata DS-07 WolofProcessing/online_wolof_data (git) : liste de sources de texte wolof
  anacim    DS-11 bulletins agrométéo décadaires (version renforcée, diagnostic des erreurs)
  kallaama  DS-02 wolof + pulaar (+ corpus texte DS-07) via agribaat_fetch_data.py
  tts       DS-03 GalsenAI Wolof TTS via agribaat_fetch_part2.py
  status    récapitulatif : présent / absent pour chaque DS (affiché + RECAP_DATASETS.csv)
  all       alffa, wolofdata, anacim, puis status (PAS les gros téléchargements)

Les gros téléchargements (kallaama, tts) sont à lancer explicitement.
DS-05 (Common Voice) est manuel : voir le message affiché par `status`.

Exemples
  python agribaat_fetch_part3.py status
  python agribaat_fetch_part3.py alffa wolofdata anacim
  python agribaat_fetch_part3.py anacim --years 2023 2024 2025 2026
  python agribaat_fetch_part3.py kallaama tts
  python agribaat_fetch_part3.py all
"""
import argparse
import csv
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/pdf,text/html,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
}


# --------------------------------------------------------------------------- #
# Git : DS-01 ALFFA, DS-07 WolofProcessing
# --------------------------------------------------------------------------- #
def run(cmd, cwd=None) -> bool:
    print("  $ " + " ".join(cmd))
    try:
        return subprocess.run(cmd, cwd=cwd, check=False).returncode == 0
    except FileNotFoundError:
        print(f"  commande introuvable : {cmd[0]} (installe-la, ex. sudo apt install git)")
        return False


def get_alffa(out: Path) -> None:
    print("[DS-01] ALFFA Wolof (getalp/ALFFA_PUBLIC, dossier ASR/WOLOF)")
    target = out / "asr" / "alffa_public"
    if (target / "ASR" / "WOLOF").exists():
        print(f"  déjà présent : {target}/ASR/WOLOF")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    url = "https://github.com/getalp/ALFFA_PUBLIC.git"
    # clone partiel : uniquement le dossier wolof (évite swahili, hausa, amharique)
    ok = run(["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", url, str(target)])
    if ok:
        ok = run(["git", "sparse-checkout", "set", "ASR/WOLOF"], cwd=target)
    if not ok:
        print("  clone partiel impossible -> clone complet (plus lourd)")
        shutil.rmtree(target, ignore_errors=True)
        ok = run(["git", "clone", "--depth", "1", url, str(target)])
    if ok:
        n = sum(1 for p in (target / "ASR" / "WOLOF").rglob("*") if p.is_file())
        print(f"  ok : {n} fichiers dans ASR/WOLOF. Lis le README de ce dossier "
              "(licence académique : à citer, vérifier l'usage).")
    else:
        print("  échec. À faire à la main :  git clone " + url)


def get_wolofdata(out: Path) -> None:
    print("[DS-07] WolofProcessing/online_wolof_data (sources de texte wolof)")
    target = out / "nlp" / "online_wolof_data"
    if target.exists() and any(target.iterdir()):
        print(f"  déjà présent : {target}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    ok = run(["git", "clone", "--depth", "1",
              "https://github.com/WolofProcessing/online_wolof_data.git", str(target)])
    if ok:
        print("  ok. Ce dépôt recense des sources en ligne : ouvre son README pour la liste.")
        print("  Le gros du corpus texte (1,14M mots) est dans l'archive KALLAAMA wolof : "
              "python agribaat_fetch_part3.py kallaama")
    else:
        print("  échec. À faire à la main :  git clone "
              "https://github.com/WolofProcessing/online_wolof_data.git")


# --------------------------------------------------------------------------- #
# DS-11 ANACIM (renforcé)
# --------------------------------------------------------------------------- #
MONTHS = ["mai", "juin", "juillet", "aout", "septembre", "octobre", "novembre"]
ANACIM_HOSTS = ["https://anacim.sn"]  # sans www : confirmé par l'utilisateur (www ne répond pas)


def anacim_names(years):
    for y in years:
        for m in MONTHS:
            for d in (1, 2, 3):
                yield f"bulletin_dec{d}_{m}_{y}.pdf"


def fetch_pdf(name: str, folder: Path):
    """Essaie chaque hôte. Renvoie (statut, détail) : ok / 404 / erreur."""
    last = ("404", "")
    for host in ANACIM_HOSTS:
        url = f"{host}/IMG/pdf/{name}"
        req = urllib.request.Request(url, headers=BROWSER_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            if not data.startswith(b"%PDF"):  # page d'erreur HTML déguisée
                last = ("pas_pdf", url)
                continue
            folder.mkdir(parents=True, exist_ok=True)
            (folder / name).write_bytes(data)
            return ("ok", url)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                last = (f"http_{e.code}", url)
        except Exception as e:  # noqa: BLE001
            last = ("reseau", f"{url} ({e})")
    return last


def get_anacim(out: Path, years) -> None:
    print("[DS-11] ANACIM – bulletins agrométéorologiques décadaires")
    folder = out / "docs" / "anacim"
    stats, examples = Counter(), {}
    for name in anacim_names(years):
        if (folder / name).exists():
            stats["deja"] += 1
            continue
        status, detail = fetch_pdf(name, folder)
        stats[status] += 1
        if status not in ("ok", "404"):
            examples.setdefault(status, detail)
        time.sleep(0.3)
    print("  résultat : " + ", ".join(f"{k}={v}" for k, v in sorted(stats.items())))
    got = stats["ok"] + stats["deja"]
    if got:
        print(f"  {got} bulletins dans {folder}")
        print("  (les 404 sont normaux : tous les mois n'ont pas de bulletin)")
    for status, detail in examples.items():
        print(f"  problème {status} : {detail}")
    if not got:
        print("  Aucun bulletin récupéré. Causes probables :")
        print("   - http_403 / reseau : le site bloque ou ton réseau coupe -> teste dans "
              "le navigateur :")
        print("     https://anacim.sn/IMG/pdf/bulletin_dec1_aout_2025.pdf")
        print("   - uniquement des 404 : le nom a changé -> ouvre anacim.sn, onglet "
              "bulletins agrométéorologiques, et copie un vrai lien PDF pour que je "
              "corrige le modèle de nom.")


# --------------------------------------------------------------------------- #
# Gros téléchargements : délégation aux scripts 1 et 2
# --------------------------------------------------------------------------- #
def delegate(script: str, args) -> None:
    path = HERE / script
    if not path.exists():
        print(f"  {script} introuvable à côté de ce script ({HERE}).")
        return
    run([sys.executable, str(path)] + list(args))


def get_kallaama(out: Path) -> None:
    print("[DS-02 / DS-07] KALLAAMA wolof + pulaar (~8,5 Go) – reprenable si coupure")
    delegate("agribaat_fetch_data.py", ["kallaama", "--lang", "wol", "fuc", "--extract"])


def get_tts(out: Path) -> None:
    print("[DS-03] GalsenAI Wolof TTS (plusieurs Go) – vérifie la licence sur la page HF")
    delegate("agribaat_fetch_part2.py", ["hf", "--hf", "tts", "--out", str(out)])


# --------------------------------------------------------------------------- #
# Récapitulatif DS-01 .. DS-13
# --------------------------------------------------------------------------- #
def stats_of(paths):
    n, size = 0, 0
    for p in paths:
        if p.is_file():
            n += 1
            size += p.stat().st_size
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.is_file():
                    n += 1
                    size += f.stat().st_size
    return n, size / 1e6


def status(out: Path) -> None:
    A = lambda *p: out.joinpath(*p)  # noqa: E731
    checks = [
        ("DS-01", "ALFFA Wolof", [A("asr", "alffa_public", "ASR", "WOLOF")]),
        ("DS-02 srr", "KALLAAMA sereer", [A("asr", "kallaama_srr")]),
        ("DS-02 wol", "KALLAAMA wolof", [A("asr", "kallaama_wol")]),
        ("DS-02 fuc", "KALLAAMA pulaar", [A("asr", "kallaama_fuc")]),
        ("DS-03", "GalsenAI Wolof TTS", [A("tts", "galsenai_wolof_tts")]),
        ("DS-04", "Google FLEURS wo_sn", [A("asr", "fleurs_wo_sn")]),
        ("DS-05", "Common Voice (manuel)", [A("asr", "common_voice_wo")]),
        ("DS-06", "Traduction FR<->wolof", [A("nlp", "french_wolof_translation")]),
        ("DS-07", "Corpus texte wolof", [A("nlp", "online_wolof_data")]),
        ("DS-08", "FAOSTAT Sénégal", [A("rag", "faostat_senegal_production.csv")]),
        ("DS-09", "AGRIDATA / ANSD", [A("inventaire", "agridata_inventaire.csv"),
                                       A("rag", "agridata")]),
        ("DS-10", "DAPSA", [A("docs", "dapsa")]),
        ("DS-11", "ANACIM bulletins", [A("docs", "anacim")]),
        ("DS-12", "Prix WFP", [A("rag", "wfp_food_prices_senegal.csv")]),
        ("DS-13", "ISRA", [A("docs", "isra")]),
    ]
    rows = []
    for ds, name, paths in checks:
        n, mo = stats_of(paths)
        rows.append({"ds": ds, "dataset": name, "etat": "présent" if n else "ABSENT",
                     "fichiers": n, "taille_mo": round(mo, 1)})
    print(f"\n[RECAP] dossier : {out}")
    print(f"{'DS':<10}{'Dataset':<26}{'État':<10}{'Fichiers':>9}{'Mo':>10}")
    for r in rows:
        print(f"{r['ds']:<10}{r['dataset']:<26}{r['etat']:<10}"
              f"{r['fichiers']:>9}{r['taille_mo']:>10}")
    out.mkdir(parents=True, exist_ok=True)
    rec = out / "RECAP_DATASETS.csv"
    with open(rec, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\n  -> {rec}")
    missing = [r["ds"] for r in rows if r["etat"] == "ABSENT"]
    if missing:
        print("  Absents : " + ", ".join(missing))
    if any(r["ds"] == "DS-05" and r["etat"] == "ABSENT" for r in rows):
        print("  DS-05 Common Voice : télécharge-le à la main (compte requis) sur "
              "commonvoice.mozilla.org, puis place les fichiers dans "
              f"{A('asr', 'common_voice_wo')}")
    print("  Note : un dossier peut être « présent » mais incomplet (téléchargement "
          "interrompu) : compare le nombre de fichiers et la taille aux valeurs attendues.")
    print("  À vérifier hors script : licences DS-03, DS-06, DS-01 (académique) ; "
          "volume réel DS-05 et DS-06.")


# --------------------------------------------------------------------------- #
def main() -> None:
    p = argparse.ArgumentParser(description="AgriBaat – datasets partie 3")
    p.add_argument("targets", nargs="+",
                   choices=["alffa", "wolofdata", "anacim", "kallaama", "tts", "status", "all"])
    p.add_argument("--out", default="data_agribaat")
    p.add_argument("--years", nargs="+", type=int, default=[2023, 2024, 2025, 2026])
    a = p.parse_args()
    out = Path(a.out)

    todo = a.targets
    if "all" in todo:
        todo = ["alffa", "wolofdata", "anacim", "status"]
    if "status" in todo:  # toujours en dernier
        todo = [t for t in todo if t != "status"] + ["status"]

    for t in todo:
        try:
            if t == "alffa":
                get_alffa(out)
            elif t == "wolofdata":
                get_wolofdata(out)
            elif t == "anacim":
                get_anacim(out, a.years)
            elif t == "kallaama":
                get_kallaama(out)
            elif t == "tts":
                get_tts(out)
            elif t == "status":
                status(out)
        except Exception as e:  # noqa: BLE001
            print(f"\n[ERREUR] {t} : {e}\n")
    print("Terminé.")


if __name__ == "__main__":
    main()
