"""LLM « sous contrôle » (API Claude) : il comprend et reformule, il n'invente aucun chiffre.

Deux usages, tous deux facultatifs (sans clé API ou sans connexion, l'app répond
exactement comme avant) :

1. Compréhension : quand les mots-clés ne suffisent pas (question libre, tournure
   inconnue, wolof / pulaar / sereer approximatif), Claude remplit un formulaire fermé
   — intention, culture, lieu, année, sujet, question en français — à partir d'une
   liste de valeurs autorisées. Ce formulaire est ensuite traité par le moteur
   habituel : les chiffres viennent toujours des tables officielles.
2. Synthèse : pour une question de pratique agricole, au lieu d'un extrait brut,
   Claude rédige une réponse courte à partir des seuls passages trouvés dans les
   documents (ISRA, ANACIM). Garde-fou : chaque nombre de sa réponse doit figurer
   dans ces passages, et il doit citer les passages utilisés ; sinon on garde l'extrait.

Ce qui part chez Anthropic : le texte de la question et, pour la synthèse, les passages
des documents. Ni voix, ni nom, ni numéro. Les résultats sont gardés dans
outputs/llm_cache.json : une question déjà posée fonctionne ensuite hors ligne.

Réglages (variables d'environnement) : ANTHROPIC_API_KEY (ou `ant auth login`),
AGRIBAAT_LLM=0 pour désactiver, AGRIBAAT_LLM_MODEL pour changer de modèle.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

import config

MODEL = os.environ.get("AGRIBAAT_LLM_MODEL", "claude-opus-5-5")
CACHE = config.APP_DIR / "outputs" / "llm_cache.json"
TIMEOUT = 25.0  # secondes : au-delà, on répond sans le LLM
INTENTS = ("prix", "vendre", "production", "superficie", "rendement", "variete", "pluie",
           "meteo", "conseil", "technique", "salutation", "hors_sujet")
TOPICS = ("semis", "recolte", "ravageurs", "previsions", "elevage", "eau", "aucun")

_lock = threading.Lock()
_client = None
_status = {"last_error": ""}


# ------------------------------------------------------------------ disponibilité
def enabled() -> bool:
    """Clé API (ou profil `ant`) présente, SDK installé, et pas désactivé."""
    if os.environ.get("AGRIBAAT_LLM", "1") == "0":
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or os.environ.get("AGRIBAAT_LLM") == "1")


def status() -> str:
    if not enabled():
        return "désactivé (pas de clé API)"
    return f"actif ({MODEL})" + (f" · dernière erreur : {_status['last_error']}"
                                 if _status["last_error"] else "")


def _get_client():
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic(timeout=TIMEOUT, max_retries=1)
    return _client


# ------------------------------------------------------------------ cache disque
def _load_cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _key(kind: str, *parts: str) -> str:
    return kind + ":" + hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]


def _cached(key: str, compute):
    """Résultat mémorisé (même hors ligne), sinon appel au LLM puis mise en cache."""
    if os.environ.get("AGRIBAAT_LLM", "1") == "0":
        return None
    with _lock:
        cache = _load_cache()
        if key in cache:
            return cache[key]
    if not enabled():
        return None
    value = compute()
    if value is not None:
        with _lock:
            cache = _load_cache()
            cache[key] = value
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return value


def _ask_json(system: str, user, schema: dict, max_tokens: int = 2000) -> dict | None:
    """Un appel, réponse JSON imposée par un schéma. None en cas d'échec ou de refus.

    `user` : texte, ou liste de blocs (image + texte) pour le diagnostic photo."""
    import anthropic

    try:
        resp = _get_client().beta.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            # Refus de sécurité : la requête est rejouée sur un autre modèle (côté serveur).
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.AuthenticationError:
        _status["last_error"] = "clé API refusée"
        return None
    except anthropic.RateLimitError:
        _status["last_error"] = "trop de requêtes"
        return None
    except anthropic.APIStatusError as exc:
        _status["last_error"] = f"erreur {exc.status_code}"
        return None
    except anthropic.APIConnectionError:  # hors ligne, délai dépassé
        _status["last_error"] = "pas de connexion"
        return None
    if resp.stop_reason in ("refusal", "max_tokens"):
        _status["last_error"] = f"réponse interrompue ({resp.stop_reason})"
        return None
    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except ValueError:
        _status["last_error"] = "réponse illisible"
        return None
    _status["last_error"] = ""
    return data


# ------------------------------------------------------------------ 1. compréhension
UNDERSTAND_SYSTEM = """Tu es le module de compréhension d'AgriBaat, assistant agricole vocal \
pour les producteurs du Sénégal. On te donne une question d'agriculteur, en wolof, pulaar, \
sereer ou français (souvent transcrite de la voix, donc avec des fautes). Tu remplis un \
formulaire ; tu ne réponds jamais à la question et tu n'écris aucun chiffre de prix, de \
production ou de pluie.

Intentions :
- prix : prix d'un produit sur un marché ; vendre : où ou quand vendre sa récolte ;
- production, superficie, rendement : statistiques agricoles ;
- variete : quelle variété semer ; pluie : pluies relevées (ANACIM) ;
- meteo : prévisions des prochains jours ; conseil : calendrier (semis, récolte, ravageurs) ;
- technique : pratique agricole (engrais, maladie, striga, irrigation, stockage…) ;
- salutation : bonjour ou demande d'aide ; hors_sujet : sans rapport avec l'agriculture.

Cultures (clé) : mil, sorgho, mais, riz, arachide, niebe, oignon, manioc, fonio ; \
« aucun » si aucune. Lieu : nom de la ville, du marché ou de la région du Sénégal cité, \
écrit en français (ex. « Kaolack »), sinon chaîne vide. Année : celle citée, sinon 0. \
question_fr : traduction fidèle et simple de la question en français."""

UNDERSTAND_SCHEMA = {
    "type": "object",
    "properties": {
        "intention": {"type": "string", "enum": list(INTENTS)},
        "culture": {"type": "string", "enum": ["mil", "sorgho", "mais", "riz", "arachide",
                                               "niebe", "oignon", "manioc", "fonio", "aucun"]},
        "lieu": {"type": "string"},
        "annee": {"type": "integer"},
        "sujet": {"type": "string", "enum": list(TOPICS)},
        "question_fr": {"type": "string"},
    },
    "required": ["intention", "culture", "lieu", "annee", "sujet", "question_fr"],
    "additionalProperties": False,
}


@dataclass
class Understanding:
    intent: str
    product: str | None
    place: str
    year: int | None
    topic: str | None
    question_fr: str


def understand(question: str, lang_label: str) -> Understanding | None:
    """Formulaire rempli par Claude (valeurs vérifiées ici une seconde fois)."""
    question = question.strip()
    if not question:
        return None
    data = _cached(_key("comprendre", MODEL, lang_label, question), lambda: _ask_json(
        UNDERSTAND_SYSTEM, f"Langue choisie dans l'app : {lang_label}.\nQuestion : {question}",
        UNDERSTAND_SCHEMA, max_tokens=1500))
    if not isinstance(data, dict) or data.get("intention") not in INTENTS:
        return None
    year = data.get("annee") or None
    # Une année n'est gardée que si elle est écrite dans la question (pas devinée).
    if year is not None and str(year) not in question:
        year = None
    product = data.get("culture")
    topic = data.get("sujet")
    return Understanding(data["intention"], None if product in (None, "aucun") else product,
                         str(data.get("lieu") or "")[:60], year,
                         None if topic in (None, "aucun") else topic,
                         str(data.get("question_fr") or "")[:400])


# ------------------------------------------------------------------ 2. synthèse
SYNTH_SYSTEM = """Tu es AgriBaat, assistant agricole pour les producteurs du Sénégal. Tu \
réponds à la question en t'appuyant UNIQUEMENT sur les passages fournis (documents de \
l'ISRA, de l'ANACIM, catalogues de variétés). Règles :
- 2 à 4 phrases simples, en français, sans jargon, utiles pour un producteur ;
- aucun chiffre, dose, date ou nom de variété qui ne soit pas écrit dans les passages ;
- si les passages ne répondent pas vraiment à la question, mets repond à false ;
- indique les numéros des passages utilisés."""

SYNTH_SCHEMA = {
    "type": "object",
    "properties": {
        "repond": {"type": "boolean"},
        "reponse": {"type": "string"},
        "passages_utilises": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["repond", "reponse", "passages_utilises"],
    "additionalProperties": False,
}

_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def numbers(text: str) -> set[str]:
    """Nombres d'un texte, normalisés (« 1 200 » -> 1200, « 2,5 » -> 2.5)."""
    text = re.sub(r"(?<=\d)[\s  ](?=\d{3}\b)", "", text)
    return {n.replace(",", ".").rstrip("0").rstrip(".") if "." in n.replace(",", ".") else n
            for n in _NUM.findall(text)}


@dataclass
class Synthesis:
    text: str
    sources: list[str] = field(default_factory=list)
    answered: bool = True  # False : les passages ne répondent pas à la question


def check(answer: str, passages: list[str]) -> str | None:
    """Garde-fou : renvoie la raison du rejet, ou None si la réponse est acceptable."""
    if not answer.strip():
        return "réponse vide"
    if len(answer) > 900:
        return "réponse trop longue"
    invented = numbers(answer) - numbers(" ".join(passages))
    if invented:
        return "chiffre absent des documents : " + ", ".join(sorted(invented))
    return None


def synthesize(question_fr: str, passages) -> Synthesis | None:
    """Réponse rédigée à partir des passages, ou None (garde-fou, refus, hors ligne)."""
    if not question_fr.strip() or not passages:
        return None
    blocks = "\n\n".join(f"[{i}] ({p.source})\n{p.text}" for i, p in enumerate(passages, 1))
    data = _cached(_key("synthese", MODEL, question_fr, blocks), lambda: _ask_json(
        SYNTH_SYSTEM, f"Passages :\n{blocks}\n\nQuestion : {question_fr}", SYNTH_SCHEMA))
    if not isinstance(data, dict):
        return None
    if data.get("repond") is False:  # Claude juge que les documents ne répondent pas
        return Synthesis("", [], answered=False)
    used = [i for i in data.get("passages_utilises", []) if isinstance(i, int)
            and 1 <= i <= len(passages)]
    if not used:
        return None
    text = str(data.get("reponse", "")).strip()
    reason = check(text, [passages[i - 1].text for i in used])
    if reason:
        _status["last_error"] = f"synthèse rejetée ({reason})"
        return None
    return Synthesis(text, list(dict.fromkeys(passages[i - 1].source for i in used)))
