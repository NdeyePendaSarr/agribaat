"""Requêtes sur les tables normalisées. Aucune valeur n'est inventée :
chaque fonction renvoie None si la donnée n'existe pas."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .lexicon import normalize


@dataclass
class PriceFact:
    product: str
    market: str | None  # None = moyenne nationale
    date: pd.Timestamp
    price: float  # FCFA/kg (moyenne des variantes si plusieurs)
    n_markets: int
    min_market: str | None = None
    min_price: float | None = None
    max_market: str | None = None
    max_price: float | None = None
    price_year_before: float | None = None
    variants: dict[str, float] | None = None


@dataclass
class StatFact:
    product: str
    indicator: str  # production | superficie | rendement
    year: int
    value: float
    unit: str
    scope: str  # "Sénégal", "région de X", "département de X"
    source: str
    requested_year: int | None = None  # année demandée si différente


class KnowledgeBase:
    """Charge les CSV traités et répond aux requêtes factuelles."""

    def __init__(self, processed_dir: Path) -> None:
        self.prices = pd.read_csv(processed_dir / "prices.csv", parse_dates=["date"])
        self.national = pd.read_csv(processed_dir / "national.csv")
        self.regional = pd.read_csv(processed_dir / "regional.csv")
        # Index normalisés pour retrouver un lieu cité dans une question.
        self.markets = {normalize(m): m for m in self.prices["market"].unique()}
        self.regions = {normalize(r): r for r in self.regional["region"].unique()
                        if r != "Senegal"}
        self.departments = {normalize(d): d for d in self.regional["department"].unique()
                            if d != "Total"}
        self.price_regions = {normalize(r): r for r in self.prices["region"].unique()}

    # ------------------------------------------------------------------ prix
    def price(self, product: str, market: str | None = None,
              region: str | None = None, year: int | None = None) -> PriceFact | None:
        """Dernier prix connu (ou dernier de l'année demandée)."""
        df = self.prices[self.prices["product"] == product]
        if year is not None:
            df = df[df["date"].dt.year == year]
        if market:
            df = df[df["market"] == market]
        elif region:
            df = df[df["region"] == region]
        if df.empty:
            return None
        last = df["date"].max()
        cur = df[df["date"] == last]
        # Une valeur par marché (moyenne des variantes local/importé).
        by_market = cur.groupby("market")["price_xof_kg"].mean()
        variants = cur.groupby("product_variant")["price_xof_kg"].mean().round(0).to_dict()
        prev = df[df["date"] == last - pd.DateOffset(years=1)]
        prev_by_market = prev.groupby("market")["price_xof_kg"].mean()
        fact = PriceFact(
            product=product, market=market, date=last,
            price=float(by_market.mean()), n_markets=len(by_market),
            price_year_before=float(prev_by_market.mean()) if not prev.empty else None,
            variants=variants if len(variants) > 1 else None,
        )
        if not market and len(by_market) > 1:
            fact.min_market, fact.min_price = by_market.idxmin(), float(by_market.min())
            fact.max_market, fact.max_price = by_market.idxmax(), float(by_market.max())
        return fact

    def price_series(self, product: str, market: str | None = None) -> pd.DataFrame:
        """Série mensuelle (date, prix moyen) pour les graphiques."""
        df = self.prices[self.prices["product"] == product]
        if market:
            df = df[df["market"] == market]
        return (df.groupby("date", as_index=False)["price_xof_kg"].mean()
                .rename(columns={"price_xof_kg": "prix_fcfa_kg"}))

    # ------------------------------------------------------- statistiques
    def stat(self, product: str, indicator: str, year: int | None = None,
             region: str | None = None, department: str | None = None) -> StatFact | None:
        """Production / superficie / rendement. National : FAOSTAT ;
        régional ou départemental : DAPSA (2017-2022)."""
        if region or department:
            df = self.regional[(self.regional["product"] == product)
                               & (self.regional["indicator"] == indicator)]
            if department:
                df = df[df["department"] == department]
                scope = f"département de {department}"
            else:
                df = df[(df["region"] == region) & (df["department"] == "Total")]
                scope = f"région de {region}"
            source = "DAPSA (enquête agricole annuelle)"
        else:
            df = self.national[(self.national["product"] == product)
                               & (self.national["indicator"] == indicator)]
            scope, source = "Sénégal", "FAOSTAT"
        if df.empty:
            return None
        chosen = year if year is not None and year in set(df["year"]) else int(df["year"].max())
        row = df[df["year"] == chosen].iloc[0]
        return StatFact(product, indicator, chosen, float(row["value"]), str(row["unit"]),
                        scope, source,
                        requested_year=year if year is not None and year != chosen else None)
