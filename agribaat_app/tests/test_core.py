"""Tests du moteur de réponses (sans modèles). Lancement : pytest"""

from __future__ import annotations

import pytest

import config
from agribaat.answers import answer, de, fmt_number
from agribaat.knowledge import KnowledgeBase
from agribaat.lexicon import normalize
from agribaat.models import split_sentences
from agribaat.nlu import parse

needs_data = pytest.mark.skipif(not (config.PROCESSED_DIR / "prices.csv").exists(),
                                reason="lancer d'abord python prepare_data.py")


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return KnowledgeBase(config.PROCESSED_DIR)


def test_normalize_removes_accents_and_case():
    assert normalize("Quel est le PRIX du Maïs à Thiès ?") == "quel est le prix du mais a thies"


def test_fmt_number_and_elision():
    assert fmt_number(1681953.4) == "1 681 953"
    assert de("arachide") == "d'arachide" and de("mil") == "de mil"


def test_split_sentences_respects_max_length():
    chunks = split_sentences("Phrase un. " + "mot " * 80, max_chars=50)
    assert all(len(c) <= 50 for c in chunks) and chunks[0] == "Phrase un."


@needs_data
@pytest.mark.parametrize("question, intent, product, place", [
    ("Quel est le prix du mil à Kaolack ?", "prix", "mil", "Kaolack"),
    ("njëg dugub ci Kaolack", "prix", "mil", "Kaolack"),
    ("Combien coûte le riz ?", "prix", "riz", None),
    ("production d'arachide en 2024", "production", "arachide", None),
    ("rendement du mil à Birkilane", "rendement", "mil", None),
    ("superficie de riz à Saint Louis", "superficie", "riz", None),
])
def test_parse(kb, question, intent, product, place):
    q = parse([question], kb)
    assert (q.intent, q.product) == (intent, product)
    if place:
        assert q.market == place


@needs_data
def test_answers_are_sourced_and_numeric(kb):
    for question in ["prix du mil à Kaolack", "production d'arachide en 2024",
                     "production de mil dans la région de Kaffrine"]:
        ans = answer(parse([question], kb), kb)
        assert ans.found and ans.source and any(ch.isdigit() for ch in ans.text)


@needs_data
def test_unknown_question_gives_help(kb):
    ans = answer(parse(["Quel temps fait-il ?"], kb), kb)
    assert not ans.found and "prix" in ans.text


@needs_data
def test_missing_year_is_announced(kb):
    ans = answer(parse(["production de mil à Kaolack en 2025"], kb), kb)
    assert "2025" in ans.text and "2022" in ans.text


@needs_data
def test_national_production_matches_faostat(kb):
    fact = kb.stat("arachide", "production", year=2024)
    assert fact is not None and round(fact.value) == 1681953


def _spm_file(tmp_path, pieces):
    """Fichier SentencePiece minimal : un message `pieces` (champ 1) par symbole."""
    out = b""
    for piece in pieces:
        raw = piece.encode("utf-8")
        msg = b"\x0a" + bytes([len(raw)]) + raw
        out += b"\x0a" + bytes([len(msg)]) + msg
    path = tmp_path / "spm_char.model"
    path.write_bytes(out)
    return path


def test_char_tokenizer_matches_sentencepiece_rules(tmp_path):
    from agribaat.models import CharTokenizer

    tok = CharTokenizer(_spm_file(tmp_path, ["<unk>", "<s>", "</s>", "▁", "a", "n", "ë"]))
    # « ▁ » en tête, espaces multiples compactés, caractère inconnu -> <unk>, puis </s>
    assert tok.encode("  në  an z") == [3, 5, 6, 3, 4, 5, 3, 0, 2]


# ------------------------------------------------------------------ wolof
def test_wolof_numbers():
    from agribaat.wolof import number_words, spoken_round

    assert number_words(300) == "ñetti téeméer"
    assert number_words(344) == "ñetti téeméer ak ñeent fukk ak ñeent"
    assert number_words(15) == "fukk ak juróom"
    assert number_words(2026) == "ñaari junni ak ñaar fukk ak juróom benn"
    assert spoken_round(1681953) == 1700000 and spoken_round(344.4) == 344


def _digits_in(text: str) -> list[str]:
    import re
    return re.findall(r"\d[\d ]*\d|\d", text)


@needs_data
@pytest.mark.parametrize("question", [
    "Quel est le prix du mil à Kaolack ?", "Combien coûte le riz ?", "Prix du mil en 2030",
    "production d'arachide en 2024", "rendement du mil à Birkilane",
    "production de mil à Kaolack en 2025", "superficie de riz à Saint Louis",
])
def test_wolof_answer_keeps_every_number(kb, question):
    """Aucun chiffre de la réponse française ne doit manquer dans la réponse wolof."""
    ans = answer(parse([question], kb), kb)
    assert ans.wolof is not None
    fr = sorted(n.replace(" ", "") for n in _digits_in(ans.text))
    wo = sorted(n.replace(" ", "") for n in _digits_in(ans.wolof.text))
    assert fr == wo, (ans.text, ans.wolof.text)
    assert not any(ch.isdigit() for ch in ans.wolof.speech)  # la voix ne lit que des mots
    assert "(" not in ans.wolof.speech


@needs_data
@pytest.mark.parametrize("question, intent, product", [
    ("ñaata la benn ektaar dugub di jur ci Kaffrine", "rendement", "mil"),
    ("ñaata la kilo ceeb di jar ci Dakar", "prix", "riz"),
    ("góobu gerte ci 2024", "production", "arachide"),
])
def test_parse_wolof_keywords(kb, question, intent, product):
    q = parse([question], kb)
    assert (q.intent, q.product) == (intent, product)


@needs_data
def test_unknown_product_has_wolof_help(kb):
    ans = answer(parse(["Quel temps fait-il ?"], kb), kb)
    assert ans.wolof is not None and "dugub" in ans.wolof.text
