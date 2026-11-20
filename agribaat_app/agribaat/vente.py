"""« Où vendre ? » : marché le plus rentable après transport, et meilleur mois pour vendre.

Tout vient des prix de détail mensuels du PAM / WFP (aucun chiffre inventé) :
- prix net d'un marché = dernier prix relevé − coût du transport depuis la région du
  producteur. Le coût du transport est saisi par l'utilisateur (FCFA par sac de 100 kg
  et par 100 km) : c'est le seul paramètre qui ne vient pas des données ;
- distance = distance à vol d'oiseau entre chefs-lieux de région × 1,25 (routes). Un
  marché de la même région est compté à 0 km ;
- saisonnalité = pour chaque marché et chaque année, prix du mois / prix moyen de
  l'année (ce qui retire l'inflation et l'effet « quels marchés sont relevés »), puis
  moyenne sur les 5 dernières années complètes, pour tout le Sénégal ;
- seuls les marchés à moins de 150 km (réglable) sont proposés : au-delà, un petit
  producteur vend rarement lui-même.

Limite à dire : ce sont des prix de détail. Le prix payé au producteur est plus bas,
mais les écarts entre marchés et entre mois restent de bons repères.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from .lexicon import normalize
from .meteo import CITIES

# Variante vendue par le producteur quand le PAM en suit plusieurs.
PRODUCER_VARIANT = {"arachide": "Groundnuts (unshelled)", "mais": "Maize (local)",
                    "riz": "Rice (local)", "oignon": "Onions (dry)"}
VARIANT_LABEL = {"arachide": "arachide en coque", "mais": "maïs local", "riz": "riz local",
                 "oignon": "oignon local"}
ROAD_FACTOR = 1.25
FRESH_MONTHS = 3  # marchés relevés dans les 3 derniers mois
DEFAULT_TRANSPORT = 1000  # FCFA par sac de 100 kg et par 100 km : à ajuster
SEASON_YEARS = 5
MONTHS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
          "septembre", "octobre", "novembre", "décembre")
HARVEST_MONTHS = (11, 12)  # novembre-décembre : la plupart des récoltes sont vendues alors
MAX_KM = 150  # au-delà, le producteur vend rarement lui-même

_CAPITALS = {normalize(k): v for k, v in CITIES.items()}


def region_coords(region: str) -> tuple[float, float] | None:
    return _CAPITALS.get(normalize(region).replace(" ", "-")) or _CAPITALS.get(normalize(region))


def distance_km(a: str, b: str) -> float | None:
    """Distance routière approximative entre les chefs-lieux de deux régions."""
    if normalize(a) == normalize(b):
        return 0.0
    pa, pb = region_coords(a), region_coords(b)
    if pa is None or pb is None:
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, (*pa, *pb))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371 * math.asin(math.sqrt(h)) * ROAD_FACTOR


@dataclass
class MarketOffer:
    market: str
    region: str
    price: float  # FCFA/kg
    date: pd.Timestamp
    km: float
    transport: float  # FCFA/kg

    @property
    def net(self) -> float:
        return self.price - self.transport


@dataclass
class SellPlan:
    product: str
    region: str
    variant: str | None
    offers: list[MarketOffer]  # du plus rentable au moins rentable
    local: MarketOffer | None  # meilleur marché de la région du producteur
    season: dict[int, float] = field(default_factory=dict)  # mois -> écart en % à la moyenne
    season_years: tuple[int, int] | None = None
    transport_rate: float = DEFAULT_TRANSPORT
    max_km: float | None = MAX_KM

    @property
    def best(self) -> MarketOffer | None:
        return self.offers[0] if self.offers else None

    @property
    def gain(self) -> float:
        """Gain net par kg en allant au meilleur marché plutôt qu'au marché local."""
        if not self.best or not self.local:
            return 0.0
        return max(0.0, self.best.net - self.local.net)

    @property
    def best_month(self) -> int | None:
        return max(self.season, key=self.season.get) if self.season else None

    @property
    def season_gain(self) -> float | None:
        """Écart en % entre le meilleur mois et la récolte (novembre-décembre)."""
        if not self.season or any(m not in self.season for m in HARVEST_MONTHS):
            return None
        harvest = sum(self.season[m] for m in HARVEST_MONTHS) / len(HARVEST_MONTHS)
        return (100 + self.season[self.best_month]) / (100 + harvest) * 100 - 100


def _product_prices(prices: pd.DataFrame, product: str) -> tuple[pd.DataFrame, str | None]:
    df = prices[prices["product"] == product]
    variant = PRODUCER_VARIANT.get(product)
    if variant and (df["product_variant"] == variant).any():
        return df[df["product_variant"] == variant], variant
    return df, None


def seasonality(df: pd.DataFrame, years: int = SEASON_YEARS):
    """Écart moyen (en %) de chaque mois au prix moyen de l'année, marché par marché."""
    if df.empty:
        return {}, None
    full = df.groupby(df["date"].dt.year)["date"].apply(lambda s: s.dt.month.nunique())
    complete = sorted(y for y, n in full.items() if n == 12)[-years:]
    if len(complete) < 2:
        return {}, None
    x = df[df["date"].dt.year.isin(complete)].copy()
    x["year"], x["month"] = x["date"].dt.year, x["date"].dt.month
    x = x.groupby(["market", "year", "month"], as_index=False)["price_xof_kg"].mean()
    counts = x.groupby(["market", "year"])["month"].transform("count")
    x = x[counts >= 10]  # année presque complète pour ce marché
    if x.empty:
        return {}, None
    x["idx"] = x["price_xof_kg"] / x.groupby(["market", "year"])["price_xof_kg"].transform("mean")
    by_month = x.groupby("month")["idx"].mean()
    return {int(m): round(float(v) * 100 - 100, 1) for m, v in by_month.items()}, \
        (complete[0], complete[-1])


def plan(prices: pd.DataFrame, product: str, region: str,
         transport_rate: float = DEFAULT_TRANSPORT, max_km: float | None = MAX_KM
         ) -> SellPlan | None:
    """Classement des marchés par prix net pour un producteur de `region`."""
    df, variant = _product_prices(prices, product)
    if df.empty:
        return None
    last = df.groupby("market")["date"].transform("max")
    cur = (df[df["date"] == last].groupby(["market", "region", "date"], as_index=False)
           ["price_xof_kg"].mean())
    cur = cur[cur["date"] > cur["date"].max() - pd.DateOffset(months=FRESH_MONTHS)]
    per_kg_km = transport_rate / 100 / 100  # FCFA par sac de 100 kg et par 100 km -> par kg et km
    offers = []
    for row in cur.itertuples():
        km = distance_km(region, row.region)
        if km is None or (max_km is not None and km > max_km):
            continue
        offers.append(MarketOffer(row.market, row.region, float(row.price_xof_kg), row.date,
                                  km, km * per_kg_km))
    if not offers:
        return None
    offers.sort(key=lambda o: (-o.net, o.km))
    local = max((o for o in offers if o.km == 0), key=lambda o: o.net, default=None)
    if local is None:  # pas de marché suivi dans la région : le plus proche
        local = min(offers, key=lambda o: (o.km, -o.net))
    # Saisonnalité nationale : une région seule a trop peu de relevés (résultats instables).
    season, years = seasonality(df)
    return SellPlan(product, region, variant, offers, local, season, years, transport_rate,
                    max_km)
