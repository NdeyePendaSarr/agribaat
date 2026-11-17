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

from pathlib import Path

import pandas as pd

from .lexicon import PRODUCTS

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


def prepare_all(raw_dir: Path, out_dir: Path) -> dict[str, int]:
    """Construit les 3 tables et renvoie le nombre de lignes de chacune."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = {
        "prices": prepare_prices(raw_dir),
        "national": prepare_national(raw_dir),
        "regional": prepare_regional(raw_dir),
    }
    for name, table in tables.items():
        table.to_csv(out_dir / f"{name}.csv", index=False)
    return {name: len(table) for name, table in tables.items()}
