#!/usr/bin/env python3
"""
AgriBaat – téléchargement des datasets prioritaires (périmètre Seydina Wade).

Datasets couverts
  DS-08  FAOSTAT Sénégal            -> data_agribaat/rag/faostat_senegal_production.csv
  DS-12  Prix alimentaires WFP/HDX  -> data_agribaat/rag/wfp_food_prices_senegal.csv
  DS-02  KALLAAMA (OpenSLR 151)     -> data_agribaat/raw/speech_dataset_<langue>.tar.gz

Aucune dépendance externe (bibliothèque standard Python 3.8+).
Les téléchargements sont reprenables : relance la même commande après une coupure.

Utilisation
  python agribaat_fetch_data.py                      # RAG seulement (FAOSTAT + WFP, léger)
  python agribaat_fetch_data.py kallaama             # sereer (~3,9 Go)
  python agribaat_fetch_data.py kallaama --extract   # + décompression
  python agribaat_fetch_data.py kallaama --lang srr wol fuc
  python agribaat_fetch_data.py all                  # tout (RAG + sereer)
  python agribaat_fetch_data.py rag --out mon_dossier
"""
import argparse
import csv
import hashlib
import io
import json
import sys
import tarfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

HEADERS = {"User-Agent": "Mozilla/5.0 (AgriBaat data fetch)"}

FAO_URL = (
    "https://bulks-faostat.fao.org/production/"
    "Production_Crops_Livestock_E_All_Data_(Normalized).zip"
)
HDX_API = (
    "https://data.humdata.org/api/3/action/package_show"
    "?id=wfp-food-prices-for-senegal"
)
KALLAAMA_LANGS = {"srr": "sereer", "wol": "wolof", "fuc": "pulaar"}
ZENODO_RECORD = "10892569"


# --------------------------------------------------------------------------- #
# Outils
# --------------------------------------------------------------------------- #
def download(url: str, dest: Path) -> Path:
    """Télécharge url vers dest, avec reprise (Range) et barre de progression."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    done = dest.stat().st_size if dest.exists() else 0
    headers = dict(HEADERS)
    if done:
        headers["Range"] = f"bytes={done}-"
    try:
        resp = urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=60
        )
    except urllib.error.HTTPError as e:
        if e.code == 416:  # fichier déjà complet
            print(f"  déjà complet : {dest.name}")
            return dest
        raise

    if resp.status != 206:  # le serveur ignore Range : on repart de zéro
        done = 0
    length = resp.headers.get("Content-Length")
    total = int(length) + done if length else None
    mode = "ab" if resp.status == 206 else "wb"

    with open(dest, mode) as f:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                sys.stdout.write(
                    f"\r  {dest.name}: {done / 1e6:,.0f} / {total / 1e6:,.0f} Mo "
                    f"({done * 100 // total} %)"
                )
            else:
                sys.stdout.write(f"\r  {dest.name}: {done / 1e6:,.0f} Mo")
            sys.stdout.flush()
    print()
    return dest


def md5sum(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# DS-08 FAOSTAT
# --------------------------------------------------------------------------- #
def get_faostat(out: Path) -> None:
    print("[DS-08] FAOSTAT – production agricole (filtre Sénégal)")
    zpath = download(FAO_URL, out / "raw" / "faostat_production.zip")
    target = out / "rag" / "faostat_senegal_production.csv"
    target.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zpath) as z:
        name = next(n for n in z.namelist() if n.endswith("(Normalized).csv"))
        with z.open(name) as raw, open(
            target, "w", newline="", encoding="utf-8"
        ) as fo:
            reader = csv.DictReader(
                io.TextIOWrapper(raw, encoding="latin-1", newline="")
            )
            reader.fieldnames = [
                c.replace("ï»¿", "").replace("\ufeff", "").strip('"')
                for c in reader.fieldnames
            ]
            if "Area" not in reader.fieldnames:
                raise RuntimeError(f"Colonne 'Area' absente : {reader.fieldnames}")
            writer = csv.DictWriter(fo, fieldnames=reader.fieldnames)
            writer.writeheader()
            n = 0
            for row in reader:
                if row["Area"] == "Senegal":
                    writer.writerow(row)
                    n += 1
    print(f"  -> {target} ({n:,} lignes)")


# --------------------------------------------------------------------------- #
# DS-12 Prix WFP via HDX
# --------------------------------------------------------------------------- #
def get_wfp(out: Path) -> None:
    print("[DS-12] Prix alimentaires WFP – Sénégal (HDX)")
    req = urllib.request.Request(HDX_API, headers=HEADERS)
    meta = json.load(urllib.request.urlopen(req, timeout=60))["result"]
    candidates = [
        r
        for r in meta["resources"]
        if r.get("format", "").upper() == "CSV"
        and "quickcharts" not in r.get("name", "").lower()
    ]
    if not candidates:
        raise RuntimeError(
            "Aucune ressource CSV trouvée. Télécharge-la à la main : "
            "https://data.humdata.org/dataset/wfp-food-prices-for-senegal"
        )
    res = candidates[0]
    url = res.get("download_url") or res["url"]
    dest = download(url, out / "rag" / "wfp_food_prices_senegal.csv")
    print(
        f"  -> {dest}\n"
        "  Note : les fichiers WFP/HDX ont souvent une 2e ligne de tags HXL "
        "(#date, #adm1+name…) à ignorer, par ex. pd.read_csv(..., skiprows=[1])."
    )


# --------------------------------------------------------------------------- #
# DS-02 KALLAAMA (OpenSLR 151)
# --------------------------------------------------------------------------- #
def get_kallaama(out: Path, langs, extract: bool) -> None:
    for lang in langs:
        print(f"[DS-02] KALLAAMA – {KALLAAMA_LANGS[lang]} ({lang})")
        fname = f"speech_dataset_{lang}.tar.gz"
        sources = [
            f"https://www.openslr.org/resources/151/{fname}",
            f"https://zenodo.org/records/{ZENODO_RECORD}/files/{fname}?download=1",
        ]
        dest = None
        for url in sources:
            try:
                dest = download(url, out / "raw" / fname)
                break
            except Exception as e:  # noqa: BLE001
                print(f"  échec ({url}) : {e}")
        if dest is None:
            print("  Impossible de télécharger. Essaie un miroir sur https://openslr.org/151")
            continue

        print(f"  md5 : {md5sum(dest)}  (à comparer avec la page Zenodo {ZENODO_RECORD})")
        if extract:
            target = out / "asr" / f"kallaama_{lang}"
            target.mkdir(parents=True, exist_ok=True)
            print(f"  extraction -> {target}")
            with tarfile.open(dest) as tar:
                try:
                    tar.extractall(target, filter="data")
                except TypeError:  # Python < 3.12
                    tar.extractall(target)


# --------------------------------------------------------------------------- #
def main() -> None:
    p = argparse.ArgumentParser(description="Téléchargement des datasets AgriBaat")
    p.add_argument(
        "target",
        nargs="?",
        default="rag",
        choices=["rag", "faostat", "wfp", "kallaama", "all"],
        help="rag = FAOSTAT + WFP (défaut) ; all = rag + KALLAAMA",
    )
    p.add_argument("--out", default="data_agribaat", help="dossier de sortie")
    p.add_argument(
        "--lang",
        nargs="+",
        default=["srr"],
        choices=list(KALLAAMA_LANGS),
        help="langues KALLAAMA : srr=sereer (défaut), wol=wolof, fuc=pulaar",
    )
    p.add_argument("--extract", action="store_true", help="décompresser KALLAAMA")
    args = p.parse_args()
    out = Path(args.out)

    steps = {
        "faostat": lambda: get_faostat(out),
        "wfp": lambda: get_wfp(out),
        "kallaama": lambda: get_kallaama(out, args.lang, args.extract),
    }
    order = {
        "rag": ["faostat", "wfp"],
        "faostat": ["faostat"],
        "wfp": ["wfp"],
        "kallaama": ["kallaama"],
        "all": ["faostat", "wfp", "kallaama"],
    }[args.target]

    for name in order:
        try:
            steps[name]()
        except Exception as e:  # noqa: BLE001
            print(f"\n[ERREUR] {name} : {e}\n")
    print("Terminé.")


if __name__ == "__main__":
    main()
