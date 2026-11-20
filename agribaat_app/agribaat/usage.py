"""Mesure d'impact : journal anonyme d'utilisation, avis des utilisateurs, tests terrain.

Rien de personnel n'est enregistré : ni le texte de la question, ni la voix, ni le nom.
Chaque question laisse une ligne (canal, langue, sujet, réponse trouvée ou non, temps de
réponse). Pendant un test terrain, l'enquêteur donne un code de participant (P1, P2…) et
un profil : les questions de ce participant sont ainsi séparées de celles de l'équipe.
Les fichiers restent sur l'ordinateur (outputs/), au format CSV lisible dans Excel.
"""

from __future__ import annotations

import csv
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd

import config

OUT = config.APP_DIR / "outputs"
EVENTS = OUT / "journal_usage.csv"
FEEDBACK = OUT / "journal_avis.csv"
FIELD_SHEET = config.APP_DIR.parent / "test_terrain" / "resultats_test_terrain.csv"

EVENT_FIELDS = ("id", "horodatage", "canal", "langue", "sujet", "trouve", "temps_s",
                "session", "profil", "sexe")
FEEDBACK_FIELDS = ("id", "horodatage", "compris")

TOPICS = {"prix": "Prix des marchés", "production": "Production", "superficie": "Production",
          "rendement": "Production", "pluie": "Pluies (ANACIM)", "meteo": "Météo en direct",
          "variete": "Variétés", "conseil": "Conseils de saison",
          "technique": "Pratiques agricoles", "fiche": "Fiche d'une culture",
          "salutation": "Salutation / aide", "vendre": "Où vendre",
          "hors_sujet": "Hors sujet", "diagnostic": "Diagnostic photo",
          "": "Question non comprise"}


def _append(path: Path, fields: tuple[str, ...], row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter=";")
        if new:
            w.writeheader()
        w.writerow(row)


def log_question(*, canal: str, langue: str, sujet: str, trouve: bool, temps_s: float,
                 session: dict | None = None) -> str:
    """Enregistre une question (anonyme) ; renvoie son identifiant (pour l'avis)."""
    event_id = uuid.uuid4().hex[:12]
    session = session or {}
    _append(EVENTS, EVENT_FIELDS, {
        "id": event_id, "horodatage": f"{datetime.now():%Y-%m-%d %H:%M:%S}", "canal": canal,
        "langue": langue, "sujet": TOPICS.get(sujet or "", sujet or ""),
        "trouve": "oui" if trouve else "non", "temps_s": f"{temps_s:.2f}",
        "session": session.get("code", ""), "profil": session.get("profil", ""),
        "sexe": session.get("sexe", "")})
    return event_id


def log_feedback(event_id: str, understood: bool) -> None:
    _append(FEEDBACK, FEEDBACK_FIELDS, {"id": event_id,
                                        "horodatage": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
                                        "compris": "oui" if understood else "non"})


def load(field_only: bool = False) -> pd.DataFrame:
    """Questions + dernier avis donné sur chacune."""
    if not EVENTS.exists():
        return pd.DataFrame(columns=[*EVENT_FIELDS, "compris"])
    df = pd.read_csv(EVENTS, sep=";", dtype=str, encoding="utf-8-sig").fillna("")
    if FEEDBACK.exists():
        fb = (pd.read_csv(FEEDBACK, sep=";", dtype=str, encoding="utf-8-sig").fillna("")
              .drop_duplicates("id", keep="last")[["id", "compris"]])
        df = df.merge(fb, on="id", how="left").fillna({"compris": ""})
    else:
        df["compris"] = ""
    df["temps_s"] = pd.to_numeric(df["temps_s"], errors="coerce")
    if field_only:
        df = df[df["session"] != ""]
    return df


def summary(df: pd.DataFrame) -> dict:
    """Chiffres clés pour le jury."""
    n = len(df)
    rated = df[df["compris"] != ""]
    local = df["langue"].isin(["Wolof", "Pulaar", "Sereer"])
    return {
        "questions": n,
        "participants": df.loc[df["session"] != "", "session"].nunique(),
        "trouve_pct": 100 * (df["trouve"] == "oui").mean() if n else None,
        "compris_pct": 100 * (rated["compris"] == "oui").mean() if len(rated) else None,
        "avis": len(rated),
        "temps_median": float(df["temps_s"].median()) if n else None,
        "local_pct": 100 * local.mean() if n else None,
        "voix_pct": 100 * (df["canal"] == "Voix").mean() if n else None,
        "femmes": df.loc[(df["session"] != "") & (df["sexe"] == "Femme"), "session"].nunique(),
    }


# ------------------------------------------------------------------ fiche terrain
def field_results(path: Path = FIELD_SHEET) -> dict | None:
    """Avant / avec AgriBaat, d'après la feuille de résultats des tests terrain."""
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, sep=";", dtype=str, encoding="utf-8-sig").fillna("")
    except (ValueError, pd.errors.EmptyDataError):
        return None
    df = df[df.get("n_fiche", pd.Series(dtype=str)).astype(str).str.strip() != ""]
    if df.empty:
        return None

    def num(col: str) -> pd.Series:
        return pd.to_numeric(df.get(col, pd.Series(dtype=str)).str.replace(",", "."),
                             errors="coerce")

    before = num("prix_temps_aujourd_hui_min").dropna()
    after = pd.concat([num(f"t{i}_temps_s") for i in (1, 2, 3)]).dropna() / 60
    understood = pd.concat([df.get(f"t{i}_comprise (oui/2e essai/non)", pd.Series(dtype=str))
                            for i in (1, 2, 3)]).str.strip().str.lower()
    understood = understood[understood != ""]
    repeated = pd.concat([df.get(f"t{i}_redit_chiffre (oui/non)", pd.Series(dtype=str))
                          for i in (1, 2, 3)]).str.strip().str.lower()
    repeated = repeated[repeated != ""]
    return {
        "personnes": len(df),
        "avant_min": float(before.median()) if len(before) else None,
        "apres_min": float(after.median()) if len(after) else None,
        "premier_coup_pct": 100 * (understood == "oui").mean() if len(understood) else None,
        "redit_pct": 100 * (repeated == "oui").mean() if len(repeated) else None,
        "femmes": int((df.get("sexe", pd.Series(dtype=str)) == "Femme").sum()),
    }
