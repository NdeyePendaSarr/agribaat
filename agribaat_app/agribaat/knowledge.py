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

        # Conseils (facultatifs : l'app fonctionne sans ces fichiers).
        curated = processed_dir.parent / "curated"
        self.varieties = _read_optional(curated / "varietes.csv")
        self.rain = _read_optional(processed_dir / "pluies.csv", ["decade_debut"])
        self.advice = _read_optional(processed_dir / "recommandations.csv", ["decade_debut"])
        self.localities = ({normalize(x): x for x in self.rain["localite"].unique()}
                           if not self.rain.empty else {})
        # Recherche de passages (secours), construite au premier usage.
        self._passages_file = processed_dir / "passages.csv"
        self._search = None

    # ---------------------------------------------------------- variétés
    def variety_list(self, product: str, cycle: str | None = None,
                     drought: bool = False, limit: int | None = 3) -> pd.DataFrame:
        """Variétés inscrites au Sénégal (catalogue ouest-africain).

        cycle : 'court' (≤ 95 jours) ou 'long' (≥ 110 jours) ; drought : tolérantes
        ou résistantes à la sécheresse (pas « sensibles »).
        """
        df = self.varieties
        if df.empty:
            return df
        df = df[df["culture"] == product]
        if cycle == "court":
            df = df[df["cycle_max"] <= 95].sort_values(["cycle_max", "rendement_max"],
                                                       ascending=[True, False])
        elif cycle == "long":
            df = df[df["cycle_min"] >= 110].sort_values("rendement_max", ascending=False)
        else:
            df = df.sort_values("rendement_max", ascending=False)
        if drought:
            text = df["caracteristiques"].fillna("").str.lower()
            df = df[text.str.contains(r"(?:tolérante|résistante)[^;]*sécheresse|pour la sécheresse",
                                      regex=True)]
        df = df[df["rendement_max"].notna()]
        return df.head(limit) if limit else df

    # ---------------------------------------------------------- pluies
    def rainfall(self, place: str | None = None) -> RainFact | None:
        """Cumul de pluie de la décade la plus récente où le lieu a un relevé.

        `place` : localité citée par l'ANACIM ou région ; None = tout le pays.
        """
        df = self.rain
        if df.empty:
            return None
        kind = "pays"
        if place:
            by_loc = df[df["localite"].map(normalize) == normalize(place)]
            by_reg = df[df["region"].fillna("").map(normalize) == normalize(place)]
            if not by_reg.empty and (by_loc.empty or normalize(place) in
                                     {normalize(r) for r in self.regions.values()}):
                df, kind = by_reg, "region"
            elif not by_loc.empty:
                df, kind = by_loc, "localite"
            else:
                return None
        last = df["decade_debut"].max()
        cur = df[df["decade_debut"] == last].sort_values("pluie_mm")
        values = list(zip(cur["localite"], cur["pluie_mm"]))
        return RainFact(place=place, kind=kind, start=last, end=decade_end(last),
                        values=values, source=str(cur["source"].iloc[0]),
                        latest_bulletin=self.rain["decade_debut"].max())

    # ---------------------------------------------------------- recommandations
    def advice_for(self, product_words: tuple[str, ...] = (), topic: str | None = None,
                   limit: int = 3) -> AdviceFact | None:
        """Recommandations ANACIM : celles qui citent le produit ou le thème (les plus
        récentes), sinon celles du dernier bulletin."""
        df = self.advice
        if df.empty:
            return None
        text = df["recommandation"].map(normalize)
        by_product = pd.Series(False, index=df.index)
        for word in product_words:
            by_product |= text.str.contains(rf"\b{normalize(word)}", regex=True)
        by_topic = (text.str.contains(TOPICS[topic], regex=True) if topic
                    else pd.Series(False, index=df.index))
        # Préférence : produit + thème, puis thème seul (c'est l'objet de la
        # question), puis produit seul.
        mask = pd.Series(False, index=df.index)
        for candidate in (by_product & by_topic, by_topic, by_product):
            if candidate.any():
                mask = candidate
                break
        if mask.any():  # les plus récentes sur le sujet, éventuellement sur plusieurs bulletins
            sel = (df[mask].sort_values("decade_debut", ascending=False)
                   .drop_duplicates("recommandation"))
        else:  # sinon : le dernier bulletin
            sel = df[df["decade_debut"] == df["decade_debut"].max()]
        sel = sel.head(limit)
        last = sel["decade_debut"].iloc[0]
        return AdviceFact(start=last, end=decade_end(last),
                          items=sel["recommandation"].tolist(),
                          dates=sel["decade_debut"].tolist(),
                          source=str(sel["source"].iloc[0]), matched=bool(mask.any()))

    # ---------------------------------------------------------- passages
    def search(self, question: str):
        """Passage le plus pertinent (recherche par mots-clés), ou None."""
        if self._search is None:
            from .search import PassageIndex

            self._search = PassageIndex.load(self._passages_file)
        return self._search.best(question)



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


# Thèmes des recommandations (texte normalisé, sans accents).
TOPICS = {
    "semis": r"\bsemis|\bsemer|resemis",
    "recolte": r"recolte",
    "ravageurs": r"ravageur|oiseaux|criquet|sauteriau|chenille|maladie|phytosanit|traitement|chancre|mildiou",
    "previsions": r"prevision|information|meteo|climat",
    "elevage": r"elevage|betail|cheptel|paturage|forage|animaux|vaccin|fourrag",
    "eau": r"hydrolog|fleuve|lacher|inondation|crue",
}


def _read_optional(path: Path, dates: list[str] | None = None) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=dates) if path.exists() else pd.DataFrame()


def decade_end(start: pd.Timestamp) -> pd.Timestamp:
    """Fin de décade : 1 -> 10, 11 -> 20, 21 -> dernier jour du mois."""
    start = pd.Timestamp(start)
    if start.day >= 21:
        return start + pd.offsets.MonthEnd(0)
    return start + pd.DateOffset(days=9)


@dataclass
class RainFact:
    place: str | None
    kind: str  # localite | region | pays
    start: pd.Timestamp
    end: pd.Timestamp
    values: list[tuple[str, float]]  # (localité, mm), du plus sec au plus arrosé
    source: str
    latest_bulletin: pd.Timestamp


@dataclass
class AdviceFact:
    start: pd.Timestamp
    end: pd.Timestamp
    items: list[str]
    dates: list[pd.Timestamp]  # début de décade de chaque recommandation
    source: str
    matched: bool  # True si filtrées par produit/thème
