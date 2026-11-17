#!/usr/bin/env python3
"""
AgriBaat – partie 2 : datasets Hugging Face + sources à explorer.

  hf        DS-03 GalsenAI Wolof TTS, DS-04 Google FLEURS (wo_sn), DS-06 traduction FR<->wolof
  agridata  DS-09 AGRIDATA / ANSD : inventaire du portail (API CKAN) + CSV d'inventaire
  dapsa     DS-10 DAPSA / EAA : rapports (site DAPSA + catalogue FAO microdata)
  anacim    DS-11 ANACIM : bulletins agrométéorologiques décadaires (PDF)
  isra      DS-13 ISRA : PDF du site isra.sn + catalogue variétés FAO/CORAF
  extract   PDF / DOCX téléchargés -> .txt (prêt pour le chunking / l'embedding RAG)
  all       tout sauf KALLAAMA et TTS (voir plus bas), puis extract

Installation :   pip install huggingface_hub pypdf
(pypdf n'est utile que pour la commande extract ; les PDF scannés demandent un OCR.)

Exemples
  python agribaat_fetch_part2.py hf                       # FLEURS wo_sn + traduction (léger)
  python agribaat_fetch_part2.py hf --hf tts              # TTS Baamtu (volumineux, plusieurs Go)
  python agribaat_fetch_part2.py agridata
  python agribaat_fetch_part2.py anacim --years 2024 2025 2026
  python agribaat_fetch_part2.py dapsa isra extract
  python agribaat_fetch_part2.py all --out data_agribaat

Les URLs ANACIM, FAO microdata, FAOSTAT, HF ont été vérifiées par recherche web ; le crawl
des sites DAPSA / ISRA / AGRIDATA est « au mieux » (les sites changent) : en cas d'échec le
script l'indique et propose l'URL à ouvrir à la main.
"""
import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

HEADERS = {"User-Agent": "Mozilla/5.0 (AgriBaat data fetch)"}

# --------------------------------------------------------------------------- #
# Outils réseau
# --------------------------------------------------------------------------- #
def http_get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def download(url: str, dest: Path) -> Path:
    """Télécharge url vers dest (fichier). Saute si déjà présent."""
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  déjà présent : {dest.name}")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    tmp.rename(dest)
    print(f"  ok : {dest.name} ({dest.stat().st_size / 1e6:.1f} Mo)")
    return dest


def download_named(url: str, folder: Path) -> Path:
    """Télécharge url dans folder en utilisant le nom fourni par Content-Disposition."""
    folder.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=120) as r:
        cd = r.headers.get("Content-Disposition", "")
        m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd)
        name = urllib.parse.unquote(m.group(1)) if m else url.rstrip("/").split("/")[-1]
        name = re.sub(r"[^\w.\-() ]", "_", name)
        dest = folder / name
        if dest.exists() and dest.stat().st_size > 0:
            print(f"  déjà présent : {name}")
            return dest
        with open(dest, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
    print(f"  ok : {dest.name} ({dest.stat().st_size / 1e6:.1f} Mo)")
    return dest


DOC_RE = re.compile(r"""href=["']([^"'#]+?\.(?:pdf|docx?|xlsx?|csv))(?:\?[^"']*)?["']""", re.I)
LINK_RE = re.compile(r"""href=["']([^"'#]+)["']""", re.I)
KEYWORDS = ("publication", "rapport", "enquete", "enquête", "document", "fiche",
            "telechar", "télécharg", "ressource", "bulletin", "statisti", "download")


def crawl_documents(starts, max_pages: int = 40):
    """Parcours léger (même domaine) : renvoie l'ensemble des liens vers pdf/docx/xlsx/csv."""
    seen, docs, queue = set(), set(), list(starts)
    while queue and len(seen) < max_pages:
        page = queue.pop(0)
        if page in seen:
            continue
        seen.add(page)
        try:
            html = http_get(page, timeout=30).decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001
            print(f"  page inaccessible : {page} ({e})")
            continue
        for href in DOC_RE.findall(html):
            docs.add(urllib.parse.urljoin(page, href))
        host = urllib.parse.urlparse(page).netloc
        for href in LINK_RE.findall(html):
            full = urllib.parse.urljoin(page, href)
            if (urllib.parse.urlparse(full).netloc == host and full not in seen
                    and not DOC_RE.search(full + '"')
                    and any(k in full.lower() for k in KEYWORDS)):
                queue.append(full)
        time.sleep(0.3)
    return sorted(docs)


# --------------------------------------------------------------------------- #
# Hugging Face : DS-03, DS-04, DS-06
# --------------------------------------------------------------------------- #
HF_JOBS = {
    # clé: (repo, motifs de fichiers, sous-dossier)
    "tts": ("galsenai/wolof_tts", None, "tts/galsenai_wolof_tts"),
    "fleurs": ("google/fleurs", ["README.md", "data/wo_sn/*"], "asr/fleurs_wo_sn"),
    "translation": ("galsenai/french-wolof-translation", None, "nlp/french_wolof_translation"),
}


def get_hf(out: Path, which) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("[HF] installe d'abord :  pip install huggingface_hub")
        return
    for key in which:
        repo, patterns, sub = HF_JOBS[key]
        target = out / sub
        print(f"[HF] {repo} -> {target}")
        try:
            snapshot_download(repo_id=repo, repo_type="dataset",
                              local_dir=str(target), allow_patterns=patterns)
        except Exception as e:  # noqa: BLE001
            print(f"  échec : {e}")
            continue
        n = sum(1 for p in target.rglob("*") if p.is_file())
        print(f"  {n} fichiers")
        if key == "fleurs" and not list((target / "data" / "wo_sn").glob("*")):
            print("  Aucun fichier wo_sn trouvé. Alternative :\n"
                  "    pip install 'datasets<4'  puis  "
                  "load_dataset('google/fleurs', 'wo_sn', trust_remote_code=True)")


# --------------------------------------------------------------------------- #
# DS-09 AGRIDATA / ANSD : inventaire CKAN
# --------------------------------------------------------------------------- #
CKAN_SITES = [
    ("agridata.ansd.sn", "https://agridata.ansd.sn", ""),
    ("bulk.openafrica.net (ANSD)", "https://bulk.openafrica.net", "agriculture S\u00e9n\u00e9gal"),
]


def get_agridata(out: Path, fetch_files: bool = False) -> None:
    print("[DS-09] AGRIDATA / ANSD – inventaire CKAN")
    rows = []
    for label, base, query in CKAN_SITES:
        api = (f"{base}/api/3/action/package_search?rows=500&q="
               + urllib.parse.quote(query))
        try:
            res = json.loads(http_get(api, timeout=45))["result"]
        except Exception as e:  # noqa: BLE001
            print(f"  {label} : API CKAN indisponible ({e}) -> à explorer à la main : {base}")
            continue
        print(f"  {label} : {res.get('count', '?')} jeux de données")
        for ds in res.get("results", []):
            for r in ds.get("resources", []) or [{}]:
                rows.append({
                    "site": label,
                    "dataset": ds.get("title") or ds.get("name"),
                    "organisation": (ds.get("organization") or {}).get("title", ""),
                    "ressource": r.get("name", ""),
                    "format": (r.get("format") or "").upper(),
                    "url": r.get("url", ""),
                })
    if not rows:
        print("  Aucun inventaire obtenu.")
        return
    inv = out / "inventaire" / "agridata_inventaire.csv"
    inv.parent.mkdir(parents=True, exist_ok=True)
    with open(inv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"  -> {inv} ({len(rows)} ressources). Filtre-le, puis relance avec --fetch-files.")
    if fetch_files:
        for r in rows:
            if r["format"] in {"CSV", "XLS", "XLSX"} and r["url"]:
                try:
                    download_named(r["url"], out / "rag" / "agridata")
                except Exception as e:  # noqa: BLE001
                    print(f"  échec {r['url']} : {e}")


# --------------------------------------------------------------------------- #
# DS-10 DAPSA / EAA
# --------------------------------------------------------------------------- #
FAO_MICRODATA = {  # catalogues FAO microdata de l'Enquête Agricole Annuelle (DAPSA)
    "eaa_2021_2022": "https://microdata.fao.org/index.php/catalog/2418/related-materials",
    "eaa_2022_2023": "https://microdata.fao.org/index.php/catalog/2522/related-materials",
    "eaa_2024_2025": "https://microdata.fao.org/index.php/catalog/3089/related-materials",
}
DAPSA_SITES = ["http://www.dapsa.gouv.sn/", "https://dapsa.sec.gouv.sn/"]


def get_dapsa(out: Path, max_pages: int) -> None:
    print("[DS-10] DAPSA – enquêtes agricoles annuelles (EAA)")
    folder = out / "docs" / "dapsa"
    # 1) Catalogue FAO microdata : liens /download/<id> des documents liés
    for name, url in FAO_MICRODATA.items():
        try:
            html = http_get(url, timeout=45).decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001
            print(f"  {name} : inaccessible ({e}) -> ouvre {url}")
            continue
        links = sorted(set(re.findall(r'href=["\']([^"\']*/download/\d+)["\']', html)))
        print(f"  {name} : {len(links)} documents")
        for href in links:
            try:
                download_named(urllib.parse.urljoin(url, href), folder / name)
            except Exception as e:  # noqa: BLE001
                print(f"    échec {href} : {e}")
            time.sleep(0.3)
    # 2) Site DAPSA (crawl léger)
    docs = crawl_documents(DAPSA_SITES, max_pages)
    print(f"  site DAPSA : {len(docs)} documents trouvés")
    for url in docs:
        try:
            download(url, folder / "site" / Path(urllib.parse.urlparse(url).path).name)
        except Exception as e:  # noqa: BLE001
            print(f"    échec {url} : {e}")


# --------------------------------------------------------------------------- #
# DS-11 ANACIM : bulletins agrométéorologiques décadaires
# --------------------------------------------------------------------------- #
MONTHS = ["mai", "juin", "juillet", "aout", "septembre", "octobre", "novembre"]


def anacim_urls(years):
    for y in years:
        for m in MONTHS:
            for d in (1, 2, 3):
                yield (f"bulletin_dec{d}_{m}_{y}.pdf",
                       f"https://www.anacim.sn/IMG/pdf/bulletin_dec{d}_{m}_{y}.pdf")


def get_anacim(out: Path, years) -> None:
    print("[DS-11] ANACIM – bulletins agrométéorologiques décadaires")
    folder = out / "docs" / "anacim"
    ok = 0
    for name, url in anacim_urls(years):
        if (folder / name).exists():
            ok += 1
            continue
        try:
            download(url, folder / name)
            ok += 1
        except urllib.error.HTTPError as e:
            if e.code != 404:
                print(f"  {name} : HTTP {e.code}")
        except Exception as e:  # noqa: BLE001
            print(f"  {name} : {e}")
        time.sleep(0.3)
    print(f"  {ok} bulletins disponibles dans {folder}")


# --------------------------------------------------------------------------- #
# DS-13 ISRA
# --------------------------------------------------------------------------- #
ISRA_KNOWN = [  # PDF vérifiés par recherche web
    "https://isra.sn/wp-content/uploads/2022/08/93928-ISRA-brochures-210x297mm-BAT.pdf",
    "https://www.fao.org/docrep/pdf/010/i0062f/i0062f01.pdf",  # catalogue ouest-africain : mil
    "https://www.fao.org/docrep/pdf/010/i0062f/i0062f03.pdf",  # catalogue ouest-africain : arachide
]


def get_isra(out: Path, max_pages: int) -> None:
    print("[DS-13] ISRA – publications et fiches techniques")
    folder = out / "docs" / "isra"
    urls = list(ISRA_KNOWN)
    # PDF de la médiathèque WordPress d'isra.sn (si l'API REST est ouverte)
    try:
        api = "https://isra.sn/wp-json/wp/v2/media?per_page=100&mime_type=application/pdf"
        media = json.loads(http_get(api, timeout=45))
        urls += [m["source_url"] for m in media if m.get("source_url")]
        print(f"  médiathèque isra.sn : {len(media)} PDF")
    except Exception as e:  # noqa: BLE001
        print(f"  API médiathèque indisponible ({e}) -> crawl du site")
        urls += crawl_documents(["https://isra.sn/"], max_pages)
    for url in dict.fromkeys(urls):
        try:
            download(url, folder / Path(urllib.parse.urlparse(url).path).name)
        except Exception as e:  # noqa: BLE001
            print(f"  échec {url} : {e}")


# --------------------------------------------------------------------------- #
# Extraction texte (RAG)
# --------------------------------------------------------------------------- #
def docx_to_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<[^>]+>", "", xml)
    return re.sub(r"&amp;", "&", re.sub(r"&lt;", "<", re.sub(r"&gt;", ">", xml)))


def pdf_to_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError("pip install pypdf")
    return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)


def extract_all(out: Path) -> None:
    print("[RAG] Extraction texte PDF/DOCX -> data_agribaat/text/")
    src, dst = out / "docs", out / "text"
    n = empty = 0
    for p in sorted(src.rglob("*")):
        suffix = p.suffix.lower()
        if suffix not in {".pdf", ".docx"}:
            continue
        target = dst / p.relative_to(src).with_suffix(".txt")
        if target.exists():
            continue
        try:
            text = docx_to_text(p) if suffix == ".docx" else pdf_to_text(p)
        except Exception as e:  # noqa: BLE001
            print(f"  échec {p.name} : {e}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        n += 1
        if len(text.strip()) < 200:
            empty += 1
            print(f"  peu de texte (PDF scanné ? OCR nécessaire) : {p.name}")
    print(f"  {n} fichiers convertis, dont {empty} quasi vides")


# --------------------------------------------------------------------------- #
def main() -> None:
    p = argparse.ArgumentParser(description="AgriBaat – datasets partie 2")
    p.add_argument("targets", nargs="+",
                   choices=["hf", "agridata", "dapsa", "anacim", "isra", "extract", "all"])
    p.add_argument("--out", default="data_agribaat")
    p.add_argument("--hf", nargs="+", default=["fleurs", "translation"],
                   choices=list(HF_JOBS), help="datasets HF (tts = volumineux)")
    p.add_argument("--years", nargs="+", type=int, default=[2023, 2024, 2025, 2026])
    p.add_argument("--max-pages", type=int, default=40, help="limite du crawl par site")
    p.add_argument("--fetch-files", action="store_true",
                   help="agridata : télécharge aussi les CSV/XLS de l'inventaire")
    a = p.parse_args()
    out = Path(a.out)

    todo = a.targets
    if "all" in todo:
        todo = ["hf", "agridata", "dapsa", "anacim", "isra", "extract"]

    for t in todo:
        try:
            if t == "hf":
                get_hf(out, a.hf)
            elif t == "agridata":
                get_agridata(out, a.fetch_files)
            elif t == "dapsa":
                get_dapsa(out, a.max_pages)
            elif t == "anacim":
                get_anacim(out, a.years)
            elif t == "isra":
                get_isra(out, a.max_pages)
            elif t == "extract":
                extract_all(out)
        except Exception as e:  # noqa: BLE001
            print(f"\n[ERREUR] {t} : {e}\n")
    print("Terminé.")


if __name__ == "__main__":
    main()
