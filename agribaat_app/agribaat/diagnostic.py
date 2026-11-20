"""Diagnostic photo « sous contrôle » : Claude regarde, les documents conseillent.

1. Claude (vision) décrit la photo : la photo est-elle exploitable, quelle culture,
   ce qu'il observe, et au plus 3 hypothèses (maladie, ravageur, carence…) avec un
   niveau de confiance. Ces hypothèses sont affichées comme NON VÉRIFIÉES et ne
   contiennent aucun chiffre (dose, pourcentage…) : une hypothèse avec un chiffre est
   écartée.
2. Les conseils viennent seulement des documents (ISRA, ANACIM) : recherche des passages
   sur le problème observé, puis rédaction contrôlée (llm.synthesize : chaque nombre
   doit figurer dans les passages cités). Sinon, on dit qu'on n'a pas de fiche.
3. L'app oriente toujours vers le conseiller agricole : une photo ne remplace pas une
   visite de la parcelle.

La photo est réduite (1 280 px au plus) avant l'envoi ; elle n'est pas gardée. Le
résultat est mis en cache par empreinte de l'image (outputs/llm_cache.json).
"""

from __future__ import annotations

import base64
import hashlib
import io
import re
from dataclasses import dataclass, field

from . import llm

MAX_SIDE = 1280
CROPS = ["mil", "sorgho", "mais", "riz", "arachide", "niebe", "oignon", "manioc", "fonio",
         "tomate", "autre", "inconnue"]
KINDS = ["maladie", "ravageur", "carence", "manque_eau", "exces_eau", "adventice", "autre"]
LEVELS = ["faible", "moyenne", "elevee"]

SYSTEM = """Tu es le module « diagnostic photo » d'AgriBaat, assistant agricole pour les \
producteurs du Sénégal. On te montre la photo d'une culture. Tu décris ce que tu vois et \
tu proposes des hypothèses prudentes ; un conseiller agricole confirmera. Règles :
- photo_exploitable = false si la photo est floue, trop loin, sans plante, ou sans rapport \
avec l'agriculture ; explique alors dans conseil_photo comment la reprendre ;
- observations : 1 à 4 constats visibles, courts et concrets (couleur, taches, trous, \
insectes, flétrissement, partie de la plante touchée) ;
- hypotheses : au plus 3, de la plus probable à la moins probable ; aucun chiffre, aucune \
dose, aucun produit commercial ; si la plante paraît saine, aucune hypothèse ;
- question_documents : une requête courte en français pour chercher la conduite à tenir \
dans des documents agronomiques (ex. « lutte contre la chenille mineuse de l'épi du mil »).
Écris en français simple."""

SCHEMA = {
    "type": "object",
    "properties": {
        "photo_exploitable": {"type": "boolean"},
        "culture": {"type": "string", "enum": CROPS},
        "observations": {"type": "array", "items": {"type": "string"}},
        "hypotheses": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "probleme": {"type": "string"},
                "type": {"type": "string", "enum": KINDS},
                "confiance": {"type": "string", "enum": LEVELS},
                "indices": {"type": "string"},
            },
            "required": ["probleme", "type", "confiance", "indices"],
            "additionalProperties": False}},
        "question_documents": {"type": "string"},
        "conseil_photo": {"type": "string"},
    },
    "required": ["photo_exploitable", "culture", "observations", "hypotheses",
                 "question_documents", "conseil_photo"],
    "additionalProperties": False,
}


@dataclass
class Hypothesis:
    problem: str
    kind: str
    confidence: str
    clues: str


@dataclass
class Diagnosis:
    usable: bool
    crop: str
    observations: list[str] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    photo_tip: str = ""
    query: str = ""
    advice: str = ""  # conseil rédigé à partir des documents (chiffres vérifiés)
    sources: list[str] = field(default_factory=list)
    dropped: int = 0  # hypothèses écartées par le garde-fou (chiffre)


def prepare(image) -> tuple[str, str]:
    """Image PIL ou numpy -> (JPEG base64 réduit, empreinte)."""
    from PIL import Image

    img = image if isinstance(image, Image.Image) else Image.fromarray(image)
    img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    data = buf.getvalue()
    return base64.standard_b64encode(data).decode("ascii"), hashlib.sha256(data).hexdigest()


def _clean(text, limit: int = 240) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def parse_reply(data: dict) -> Diagnosis | None:
    """Vérifie la réponse de Claude ; écarte toute hypothèse qui contient un chiffre."""
    if not isinstance(data, dict) or not isinstance(data.get("photo_exploitable"), bool):
        return None
    crop = data.get("culture") if data.get("culture") in CROPS else "inconnue"
    obs = [_clean(o) for o in data.get("observations") or [] if _clean(o)][:4]
    hyps, dropped = [], 0
    for h in (data.get("hypotheses") or [])[:3]:
        if not isinstance(h, dict) or h.get("type") not in KINDS or h.get("confiance") not in LEVELS:
            continue
        problem, clues = _clean(h.get("probleme"), 120), _clean(h.get("indices"))
        if not problem or re.search(r"\d", problem + clues):
            dropped += 1  # garde-fou : pas de chiffre (dose, %) dans une hypothèse
            continue
        hyps.append(Hypothesis(problem, h["type"], h["confiance"], clues))
    obs = [o for o in obs if not re.search(r"\d", o)]
    return Diagnosis(data["photo_exploitable"], crop, obs, hyps if data["photo_exploitable"] else [],
                     _clean(data.get("conseil_photo"), 300), _clean(data.get("question_documents"),
                                                                     200), dropped=dropped)


def diagnose(image, kb, crop_hint: str | None = None) -> Diagnosis | None:
    """Diagnostic complet (photo -> hypothèses -> conseils des documents), ou None."""
    b64, digest = prepare(image)
    hint = f"Le producteur indique : {crop_hint}." if crop_hint else "Culture non précisée."
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
        {"type": "text", "text": f"{hint} Que vois-tu sur cette photo ?"},
    ]
    data = llm._cached(llm._key("photo", llm.MODEL, digest, crop_hint or ""),
                       lambda: llm._ask_json(SYSTEM, content, SCHEMA, max_tokens=3000))
    diag = parse_reply(data) if data is not None else None
    if diag is None or not diag.usable or not diag.hypotheses:
        return diag
    # Conseils : seulement à partir des documents, rédaction vérifiée.
    words = " ".join([diag.query] + [h.problem for h in diag.hypotheses[:2]]
                     + ([diag.crop] if diag.crop not in ("autre", "inconnue") else []))
    passages = kb.search_many(words, 3) or kb.search_many(diag.query, 3)
    syn = llm.synthesize(diag.query or words, passages) if passages else None
    if syn is not None and syn.answered:
        diag.advice, diag.sources = syn.text, syn.sources
    return diag
