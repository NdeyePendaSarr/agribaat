"""Normalisation des données brutes en 3 tables propres (CSV).

Entrées (dans data_agribaat/) :
- rag/wfp_food_prices_senegal.csv                    -> prix de détail (PAM/WFP)
- rag/faostat_senegal_production.csv                 -> production nationale (FAOSTAT)
- docs/dapsa/eaa_2022_2023/EAA_2017_2022_T3_*.xlsx   -> production régionale (DAPSA)

Sorties (dans data/processed/) :
- prices.csv          date, region, market, product, product_variant, price_xof_kg
- national.csv        year, product, indicator, value, unit, source
- regional.csv        year, region, department, product, indicator, value, unit
Les données brutes ne sont jamais modifiées.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .lexicon import PRODUCTS, normalize

WFP_FILE = Path("rag/wfp_food_prices_senegal.csv")
FAO_FILE = Path("rag/faostat_senegal_production.csv")
DAPSA_FILE = Path("docs/dapsa/eaa_2022_2023/"
                  "EAA_2017_2022_T3_Superficie_ Rendement et Production agricoles.xlsx")

INDICATORS_FAO = {"Production": ("production", "t"),
                  "Area harvested": ("superficie", "ha"),
                  "Yield": ("rendement", "kg/ha")}
INDICATORS_DAPSA = {"Production en tonne": ("production", "t"),
                    "Superficie en ha": ("superficie", "ha"),
                    "Rendement kg/ha": ("rendement", "kg/ha")}


def prepare_prices(raw_dir: Path) -> pd.DataFrame:
    """Prix WFP au kilo, en FCFA, restreints aux produits du lexique."""
    df = pd.read_csv(raw_dir / WFP_FILE)
    variant_to_key = {v: p.key for p in PRODUCTS for v in p.wfp}
    df = df[df["commodity"].isin(variant_to_key) & (df["unit"] == "KG")
            & (df["currency"] == "XOF")]
    out = pd.DataFrame({
        "date": pd.to_datetime(df["date"]),
        "region": df["admin1"].str.strip(),
        "market": df["market"].str.strip(),
        "product": df["commodity"].map(variant_to_key),
        "product_variant": df["commodity"],
        "price_xof_kg": df["price"].astype(float),
    })
    return out.dropna(subset=["price_xof_kg"]).sort_values("date").reset_index(drop=True)


def prepare_national(raw_dir: Path) -> pd.DataFrame:
    """Production, superficie et rendement nationaux (FAOSTAT)."""
    df = pd.read_csv(raw_dir / FAO_FILE)
    item_to_key = {p.fao: p.key for p in PRODUCTS if p.fao}
    df = df[df["Item"].isin(item_to_key) & df["Element"].isin(INDICATORS_FAO)]
    df = df[df["Unit"].isin(["t", "ha", "kg/ha"])]
    out = pd.DataFrame({
        "year": df["Year"].astype(int),
        "product": df["Item"].map(item_to_key),
        "indicator": df["Element"].map(lambda e: INDICATORS_FAO[e][0]),
        "value": df["Value"].astype(float),
        "unit": df["Element"].map(lambda e: INDICATORS_FAO[e][1]),
        "source": "FAOSTAT",
    })
    return out.dropna(subset=["value"]).reset_index(drop=True)


def prepare_regional(raw_dir: Path) -> pd.DataFrame:
    """Production par région et département (DAPSA, enquête agricole annuelle).

    La ligne Département == 'TOTAL' correspond au total de la région ;
    REGION == 'SENEGAL' au total national.
    """
    df = pd.read_excel(raw_dir / DAPSA_FILE)
    df.columns = ["year", "region", "department", "culture", "indicator", "value"]
    culture_to_key = {p.dapsa: p.key for p in PRODUCTS if p.dapsa}
    df = df[df["culture"].isin(culture_to_key) & df["indicator"].isin(INDICATORS_DAPSA)]
    out = pd.DataFrame({
        "year": df["year"].astype(int),
        "region": df["region"].str.strip().str.title(),
        "department": df["department"].str.strip().str.title(),
        "product": df["culture"].map(culture_to_key),
        "indicator": df["indicator"].map(lambda i: INDICATORS_DAPSA[i][0]),
        "value": pd.to_numeric(df["value"], errors="coerce"),
        "unit": df["indicator"].map(lambda i: INDICATORS_DAPSA[i][1]),
    })
    return out.dropna(subset=["value"]).reset_index(drop=True)


# ------------------------------------------------------------------ ANACIM
ANACIM_DIR = Path("text/anacim")
MONTHS = {"juin": 6, "juillet": 7, "aout": 8, "août": 8, "septembre": 9, "octobre": 10}
DECADE_START = {"dec1": 1, "dec2": 11, "dec3": 21}

_NAME = r"([A-ZÉÈ][\wéèêëàâîïôûçÉ'’\-]+(?:[ \-](?:[A-ZÉ][\wéèêëàâîïôûç'’\-]+|de|du|Essy))*)"
_RAIN_AFTER = re.compile(r"(\d+(?:[.,]\d+)?)\s?mm\s+(?:à|a|au|de)\s+" + _NAME)
_RAIN_BEFORE = re.compile(_NAME + r"\s*(?:\(|:)?\s*(\d+(?:[.,]\d+)?)\s?mm")
_HEADER = re.compile(r"[Dd][ée]cade du (\d+)(?:er)? au \d+ (\w+) (\d{4})")
_NOT_PLACES = {"Au", "Le", "La", "Les", "Dans", "Durant", "Cette", "En", "Par", "Pour", "Avec",
               "Sur", "Nord", "Sud", "Est", "Ouest", "Centre", "Cap", "Entre"}

# Localités citées par l'ANACIM qui ne sont pas des départements DAPSA -> région.
EXTRA_LOCALITIES = {
    "Cap Skirring": "Ziguinchor", "Cabrousse": "Ziguinchor", "Diouloulou": "Ziguinchor",
    "Tendouck": "Ziguinchor", "Diogué": "Ziguinchor", "Mpack": "Ziguinchor",
    "Thiadiaye": "Thies", "Mérina Dakhar": "Thies", "Méouane": "Thies",
    "Mbao": "Dakar", "Richard Toll": "Saint-Louis", "Saint Louis": "Saint-Louis",
    "Saraya": "Kedougou", "Salémata": "Kedougou", "Salemata": "Kedougou",
    "Fongolimbi": "Kedougou", "Khossanto": "Kedougou", "Sabodola": "Kedougou",
    "Kidira": "Tambacounda", "Tamba": "Tambacounda", "Déaly": "Louga", "Barkédji": "Louga",
    "Thilogne": "Matam", "Semmé": "Matam", "Ogo": "Matam", "Taif": "Diourbel",
    "Fimela": "Fatick", "Diattacounda": "Sedhiou", "Paoskoto": "Kaolack",
    "Wack Ngouna": "Kaolack", "Wakh Ngouna": "Kaolack", "Nioro": "Kaolack",
    "Malem Hoddar": "Kaffrine", "Ranérou": "Matam", "Guédiawaye": "Dakar",
    "Dakar Yoff": "Dakar", "Diass": "Thies", "Niakhar": "Fatick", "Tanaf": "Sedhiou",
    "Dioulacolon": "Kolda", "Darou Mousty": "Louga", "Daroul Mouhty": "Louga",
}

# Phrases qui parlent du cumul de la saison (et non de la décade) : ignorées.
_SEASONAL = re.compile(r"saison|depuis le d[ée]but|cumuls? (?:saisonnier|annuel)|normale",
                       re.I)
MAX_DECADE_MM = 450  # au-delà, c'est forcément un cumul saisonnier mal repéré


def _anacim_period(name: str, text: str) -> pd.Timestamp | None:
    """Début de la décade : en-tête du bulletin si présent, sinon nom du fichier."""
    header = _HEADER.search(text)
    if header:
        day, month, year = header.groups()
        month_num = MONTHS.get(normalize_month(month))
        if month_num:
            return pd.Timestamp(int(year), month_num, int(day))
    parts = name.removesuffix(".txt").split("_")  # bulletin_dec1_aout_2026
    if len(parts) == 4 and parts[1] in DECADE_START and parts[2] in MONTHS:
        return pd.Timestamp(int(parts[3]), MONTHS[parts[2]], DECADE_START[parts[1]])
    return None


def normalize_month(month: str) -> str:
    return month.lower().replace("û", "u") if month.lower() != "août" else "aout"


def _locality_regions(raw_dir: Path) -> dict[str, str]:
    """Département DAPSA -> région, complété par EXTRA_LOCALITIES."""
    mapping: dict[str, str] = {}
    try:
        regional = prepare_regional(raw_dir)
        for dep, reg in regional[["department", "region"]].drop_duplicates().values:
            if dep != "Total":
                mapping[dep] = reg
        for reg in regional["region"].unique():
            mapping.setdefault(reg, reg)
    except Exception:  # noqa: BLE001 — DAPSA absent : on garde la liste manuelle
        pass
    mapping.update(EXTRA_LOCALITIES)
    return {normalize(k): v for k, v in mapping.items()}


def prepare_rainfall(raw_dir: Path) -> pd.DataFrame:
    """Cumuls de pluie par localité et par décade, tirés des bulletins ANACIM."""
    regions = _locality_regions(raw_dir)
    rows = []
    for path in sorted((raw_dir / ANACIM_DIR).glob("*.txt")):
        text = path.read_text(encoding="utf-8").replace(" ", " ")
        text = re.sub(r"-\s*\n\s*", "", text)  # mots coupés en fin de ligne
        start = _anacim_period(path.name, text)
        if start is None:
            continue
        body = re.split(r"Perspectives", text)[0].replace("\n", " ")
        hits = []
        for sentence in re.split(r"(?<=[.;])\s+", body):
            if _SEASONAL.search(sentence):  # cumul de la saison, pas de la décade
                continue
            hits += [(m.group(2), m.group(1)) for m in _RAIN_AFTER.finditer(sentence)]
            hits += [(m.group(1), m.group(2)) for m in _RAIN_BEFORE.finditer(sentence)]
        for place, mm in hits:
            place = place.strip(" -")
            value = float(mm.replace(",", "."))
            if place in _NOT_PLACES or len(place) < 3 or value > MAX_DECADE_MM:
                continue
            rows.append({"decade_debut": start, "localite": place,
                         "region": regions.get(normalize(place), ""),
                         "pluie_mm": float(mm.replace(",", ".")),
                         "source": f"ANACIM, bulletin agrométéorologique ({path.name})"})
    out = pd.DataFrame(rows, columns=["decade_debut", "localite", "region", "pluie_mm", "source"])
    return (out.drop_duplicates(["decade_debut", "localite"])
            .sort_values(["decade_debut", "localite"]).reset_index(drop=True))


def prepare_advice(raw_dir: Path) -> pd.DataFrame:
    """Recommandations (puces « • ») de chaque bulletin ANACIM."""
    rows = []
    for path in sorted((raw_dir / ANACIM_DIR).glob("*.txt")):
        text = path.read_text(encoding="utf-8").replace(" ", " ")
        start = _anacim_period(path.name, text)
        section = re.search(r"Recommandations[^\n]*\n(.*?)(?:Groupe de Travail|$)", text, re.S)
        if start is None or not section:
            continue
        for item in re.split(r"\s*[•]\s*", section.group(1)):  # deux styles de puces
            # coupe la mise en page qui suit parfois la dernière puce
            item = re.split(r"\.?\s*Suivi de la végétation|Page \d|Décade du", item)[0]
            item = " ".join(item.replace("-\n", "").split()).strip(" ;.-")
            if not 25 <= len(item) <= 400:
                continue
            if re.search(r"\[a\]|GTP|AGRHYMET|Agence Nationale|Téléphone", item):
                continue
            org = re.search(r"\(([^()]{2,60})\)\s*$", item)
            rows.append({"decade_debut": start,
                         "recommandation": re.sub(r"\s*\([^()]{2,60}\)\s*$", "", item),
                         "organisme": org.group(1) if org else "",
                         "source": f"ANACIM, bulletin agrométéorologique ({path.name})"})
    return pd.DataFrame(rows, columns=["decade_debut", "recommandation", "organisme", "source"])


def prepare_all(raw_dir: Path, out_dir: Path) -> dict[str, int]:
    """Construit les tables et renvoie le nombre de lignes de chacune."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = {
        "prices": prepare_prices(raw_dir),
        "national": prepare_national(raw_dir),
        "regional": prepare_regional(raw_dir),
    }
    if (raw_dir / ANACIM_DIR).exists():
        from .search import prepare_passages

        tables["pluies"] = prepare_rainfall(raw_dir)
        tables["recommandations"] = prepare_advice(raw_dir)
        tables["passages"] = prepare_passages(raw_dir / "text")
    for name, table in tables.items():
        table.to_csv(out_dir / f"{name}.csv", index=False)
    return {name: len(table) for name, table in tables.items()}
