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


# ------------------------------------------------------------------ conseils
needs_advice = pytest.mark.skipif(not (config.PROCESSED_DIR / "pluies.csv").exists(),
                                  reason="lancer d'abord python prepare_data.py")


@needs_data
@needs_advice
@pytest.mark.parametrize("question, intent, product", [
    ("Quelle variété de mil à cycle court ?", "variete", "mil"),
    ("xeeti gerte yu gaaw", "variete", "arachide"),
    ("Il a plu combien à Mbour ?", "pluie", None),
    ("taw bi ci Ziguinchor", "pluie", None),
    ("Quand récolter l'arachide ?", "conseil", "arachide"),
    ("conseils pour les semis de mil", "conseil", "mil"),
])
def test_parse_advice_questions(kb, question, intent, product):
    q = parse([question], kb)
    assert (q.intent, q.product) == (intent, product)
    assert q.is_complete


@needs_data
@needs_advice
def test_short_cycle_varieties_respect_the_filter(kb):
    rows = kb.variety_list("arachide", cycle="court", limit=None)
    assert len(rows) >= 3 and (rows["cycle_max"] <= 95).all()
    dry = kb.variety_list("arachide", drought=True, limit=None)
    assert not dry["caracteristiques"].str.contains("sensible à la sécheresse").any()


@needs_data
@needs_advice
@pytest.mark.parametrize("question, source_word", [
    ("Quelle variété de mil à cycle court ?", "Catalogue"),
    ("Il a plu combien à Mbour ?", "ANACIM"),
    ("pluie dans la région de Kaolack", "ANACIM"),
    ("Quand récolter l'arachide ?", "ANACIM"),
    ("nouvelles variétés de blé homologuées", "ISRA"),
])
def test_advice_answers_are_sourced_and_spoken_without_digits(kb, question, source_word):
    ans = answer(parse([question], kb), kb)
    assert ans.found and source_word in ans.source
    assert ans.wolof is not None and ans.wolof.text
    assert not any(ch.isdigit() for ch in ans.wolof.speech)
    fr = sorted(n.replace(" ", "") for n in _digits_in(ans.text))
    if ans.source.startswith(("Catalogue", "ANACIM")) and "Recommandations" not in ans.text:
        wo = sorted(n.replace(" ", "") for n in _digits_in(ans.wolof.text))
        assert set(wo) <= set(fr) | {"1"}, (ans.text, ans.wolof.text)


@needs_data
@needs_advice
def test_rain_values_are_decadal(kb):
    """Aucun cumul saisonnier ne doit se glisser dans les relevés décadaires."""
    assert kb.rain["pluie_mm"].max() <= 450
    assert kb.rain["decade_debut"].dt.month.isin([6, 7, 8, 9, 10]).all()


@needs_data
@needs_advice
def test_search_refuses_unrelated_questions(kb):
    assert kb.search("Quel temps fait-il à Paris ?") is None
    passage = kb.search("oiseaux granivores dans la vallée")
    assert passage is not None and "ANACIM" in passage.source


# ------------------------------------------------------------------ voix
def test_split_sentences_cuts_long_sentences_at_commas():
    text = ("Ci Oktoobar ñaari junni ak ñaar fukk ak juróom benn, kilo dugub dafa jaroon "
            "ñetti téeméer sefa ci marse Kaolack. Lii mooy xibaar yi mujj.")
    chunks = split_sentences(text)
    assert all(len(c) <= 70 for c in chunks)
    assert chunks[0].endswith(",") and len(chunks) == 3


def test_warmup_reports_progress_and_survives_errors(monkeypatch):
    from agribaat import models, warmup

    monkeypatch.setattr(models, "_tts", lambda: None)
    monkeypatch.setattr(models, "_asr", lambda: (_ for _ in ()).throw(
        models.ModelUnavailable("ASR absent")))

    class FakeAssistant:
        def ask_text(self, text, lang):
            class R:
                warnings: list = []
            return R()

    status = warmup.WarmupStatus()
    warmup.run(FakeAssistant(), [("a", "fr"), ("b", "wo")], status)
    assert status.state == "prêt" and (status.done, status.total) == (2, 2)
    assert "ASR absent" in status.errors

    monkeypatch.setattr(models, "_tts", lambda: 1 / 0)
    broken = warmup.WarmupStatus()
    warmup.run(FakeAssistant(), [("a", "fr")], broken)
    assert broken.state == "erreur" and broken.finished


def test_tts_cache_returns_stored_audio(tmp_path, monkeypatch):
    import numpy as np
    import soundfile as sf

    from agribaat import models

    monkeypatch.setattr(models, "CACHE_DIR", tmp_path)
    sf.write(models._cache_path("Mas naa jaay lii."), np.zeros(1600, dtype=np.float32), 16000)
    monkeypatch.setattr(models, "_tts", lambda: (_ for _ in ()).throw(AssertionError))
    sr, audio = models.synthesize("Mas naa jaay lii.")  # ne doit pas charger le modèle
    assert sr == 16000 and len(audio) == 1600


@needs_data
@pytest.mark.parametrize("question, product", [
    ("njëg gertei ci Kaolack", "arachide"),  # transcription vocale déformée
    ("dugud bi ci Kaffrine", "mil"),
    ("ñebe bi", "niebe"),
])
def test_parse_tolerates_one_letter_asr_errors(kb, question, product):
    assert parse([question], kb).product == product


@needs_data
def test_fuzzy_matching_does_not_invent_products(kb):
    assert parse(["prix bas à Kaolack"], kb).product is None  # « bas » ≠ « basi »


@needs_data
def test_parse_asr_style_question(kb):
    """Transcription réelle de « Ñaata la kilo dugub di jar ci Kaolack ? »."""
    q = parse(["ñaata la kilo dugub di jaar ci kalaak"], kb)
    assert (q.intent, q.product, q.market) == ("prix", "mil", "Kaolack")
    assert parse(["njëg dugub ci Kawlax"], kb).market == "Kaolack"
    assert parse(["amul benn risque"], kb).market is None  # pas de faux lieu


@needs_data
def test_recording_list_questions_are_understood(kb):
    """Les 14 questions du kit de test vocal sont comprises à l'écrit."""
    import csv

    path = config.APP_DIR / "test_voix" / "questions_a_enregistrer.csv"
    rows = list(csv.reader(path.open(encoding="utf-8"), delimiter=";"))[1:]
    queries = {name: parse([text], kb) for name, text in rows}
    assert all(q.is_complete for q in queries.values())
    assert queries["q06"].year == 2024  # année dite en toutes lettres
    assert (queries["q10"].intent, queries["q10"].drought) == ("variete", True)
    assert queries["q13"].topic == "semis"
    assert (queries["q14"].intent, queries["q14"].topic) == ("conseil", "recolte")


def test_labo_reports_missing_sereer_models_clearly():
    import numpy as np

    from agribaat import labo, models

    assert labo.LANGUAGES["pulaar"].asr_model and labo.LANGUAGES["pulaar"].tts_model
    with pytest.raises(models.ModelUnavailable, match="Sereer"):
        labo.transcribe("sereer", 16000, np.zeros(16000, dtype=np.float32))
    with pytest.raises(models.ModelUnavailable, match="Sereer"):
        labo.synthesize("sereer", "phrase")


@needs_data
@needs_advice
def test_interface_tabs_render_with_real_data(monkeypatch):
    """Chaque onglet produit son contenu sans erreur (Assistant, Production, Conseils)."""
    monkeypatch.setenv("AGRIBAAT_WARMUP", "0")
    import importlib

    app = importlib.import_module("app")
    card = app.on_text("Quel est le prix du mil à Kaolack ?", "Français", [])[0]
    assert "Chiffre vérifié" in card and "300" in card and "Kaolack" in card
    kpis, series, bars = app.on_stats("arachide", "production")
    assert "Record" in kpis and "ag-chart" in series and series.count("class=\"hit\"") > 10 and 'class="fill"' in bars
    assert "vtable" in app.variety_table("arachide", "court", False)
    assert "hbar" in app.rain_by_region(app.DECADES[0][1])[0]
    for lang, cards in app.EXAMPLES_BY_LANG.items():
        labels = app.EXAMPLE_LABELS[lang]
        assert all("\n" not in x and t in x for x, (_, t) in zip(labels, cards))
        # chaque question type de chaque langue trouve une réponse (sans synthèse vocale)
        for question, _ in cards:
            res = app.api_assistant.ask_text(question, app.LANG_CODES[lang])
            assert res.found, (lang, question)
    for lang in ("Pulaar", "Sereer"):
        card = app.on_text("coggu gawri e Kawlak", lang, [])[0]
        assert f"{lang} :" in card and "brouillon" not in card and "300" in card


# ---------------------------------------------------------------- pulaar et sereer
def test_pulaar_numbers():
    from agribaat.pulaar import number_words

    assert number_words(7) == "jeeɗiɗi"
    assert number_words(344) == "teemedde tati e capanɗe nay e nay"
    assert number_words(2026) == "ujunaaje ɗiɗi e noogaas e jeegom"
    assert number_words(1000) == "ujunere"


def test_language_modules_define_the_same_templates():
    from agribaat import pulaar, sereer, wolof

    # Conseils météo : seul le résumé existe en sereer (phrases de conseil à écrire).
    advice_only = {k for k in wolof.T if k.startswith("meteo_") and not k.startswith("meteo_resume")}
    for module in (pulaar, sereer):
        missing = set(wolof.T) - set(module.T)
        assert missing <= (advice_only if module is sereer else set()), module.LABEL
        assert set(module.T) <= set(wolof.T), module.LABEL
        assert set(module.PRODUCTS_WO) == set(wolof.PRODUCTS_WO)
        assert set(module.THEMES_WO) == set(wolof.THEMES_WO)
        assert set(module.WORDS) == set(wolof.WORDS)
        assert len(module.MONTHS_WO) == 12


@needs_data
@pytest.mark.parametrize("lang", ["pul", "srr"])
@pytest.mark.parametrize("question", [
    "Quel est le prix du mil à Kaolack ?", "Combien coûte le riz ?", "Prix du mil en 2030",
    "production d'arachide en 2024", "rendement du mil à Birkilane",
])
def test_other_languages_keep_every_number(kb, lang, question):
    from agribaat import langues

    module = langues.get(lang).module
    ans = answer(parse([question], kb), kb, module)
    fr = sorted(n.replace(" ", "") for n in _digits_in(ans.text))
    local = sorted(n.replace(" ", "") for n in _digits_in(ans.wolof.text))
    assert fr == local, (ans.text, ans.wolof.text)
    assert "{" not in ans.wolof.text
    if lang == "pul":  # voix pulaar : nombres en lettres
        assert not any(ch.isdigit() for ch in ans.wolof.speech)


def test_language_switch_does_not_leak(kb):
    """Une réponse pulaar ne laisse pas la langue active sur le pulaar."""
    from agribaat import pulaar

    q = parse(["prix du mil à Kaolack"], kb)
    assert "coggu" in answer(q, kb, pulaar).wolof.text
    assert "kilo dugub" in answer(q, kb).wolof.text


@needs_data
@pytest.mark.parametrize("question, intent, product, place", [
    ("Hol no coggu kiloo gawri woni e Kawlak?", "prix", "mil", "Kaolack"),
    ("coggu maaro", "prix", "riz", None),
    ("toɓo e Mbour", "pluie", None, "Mbour"),
    ("noone biriiji yaawɗe", "variete", "arachide", None),
    ("ndey aawde gawri", "conseil", "mil", None),
    ("njeg kilo maac no Kaolack", "prix", "mil", "Kaolack"),
    ("ndoɓ no Mbour", "pluie", None, "Mbour"),
])
def test_parse_pulaar_and_sereer_keywords(kb, question, intent, product, place):
    q = parse([question], kb)
    assert (q.intent, q.product) == (intent, product)
    if place:
        assert place in (q.market, q.region, q.locality)


def test_partial_spoken_year_is_ignored():
    from agribaat.lexicon import normalize
    from agribaat.nlu import _year_in_words

    assert _year_in_words(normalize("ujunaaje ɗiɗi e noogas e jeeko")) is None
    assert _year_in_words(normalize("hitaande ujunaaje ɗiɗi e noogaas e ɗiɗi")) == 2022


def test_sereer_voice_question_is_refused_politely(kb):
    import numpy as np

    from agribaat.pipeline import Assistant

    res = Assistant(kb, speak=False).ask_audio(16000, np.zeros(16000, np.float32), "srr")
    assert "tapez" in res.answer_fr


# ---------------------------------------------------------------- audit du 19/11
@needs_data
@pytest.mark.parametrize("text,lang", [("Bonjour", "fr"), ("Salaam aleekum", "wo"),
                                       ("Jam waali", "pul"), ("Na fio", "srr")])
def test_greeting_answers_with_what_the_assistant_can_do(kb, text, lang):
    """Une salutation ne doit plus renvoyer un extrait de document sans rapport."""
    from agribaat import langues

    q = parse([text], kb)
    assert q.intent == "salutation" and q.is_complete
    ans = answer(q, kb, langues.get(lang).module)
    assert ans.found and ans.source is None and "AgriBaat" in ans.text
    assert ans.wolof is not None and ans.wolof.text


@needs_data
def test_greeting_does_not_hide_a_real_question(kb):
    assert parse(["Bonjour, quel est le prix du mil à Kaolack ?"], kb).intent == "prix"


@needs_data
def test_market_without_this_product_falls_back_to_its_region(kb):
    ans = answer(parse(["prix de l'oignon à Dakar"], kb), kb)
    assert ans.found and "région de Dakar" in ans.text


@needs_data
def test_pulaar_and_wolof_name_of_dakar(kb):
    assert parse(["coggu basal e Ndakaaru"], kb).region == "Dakar"


@needs_data
def test_wolof_variety_question_with_xeetu(kb):
    q = parse(["ban xeetu dugub moo gaaw"], kb)
    assert (q.intent, q.product, q.cycle) == ("variete", "mil", "court")


@needs_data
def test_intent_word_misheard_by_one_letter(kb):
    """Transcription vocale : « cogu » pour « coggu » (prix, pulaar)."""
    q = parse(["cogu gawri e kawlak"], kb)
    assert (q.intent, q.product, q.market) == ("prix", "mil", "Kaolack")


def test_clean_speech_trims_silence_and_raises_volume():
    import numpy as np

    from agribaat.models import clean_speech

    sr = 16_000
    voice = 0.05 * np.sin(np.linspace(0, 2 * np.pi * 220, sr)).astype(np.float32)
    audio = np.concatenate([np.zeros(3 * sr, np.float32), voice, np.zeros(3 * sr, np.float32)])
    out = clean_speech(audio, sr)
    assert len(out) < 2 * sr  # 6 s de silence retirées (0,25 s gardée de chaque côté)
    assert abs(float(np.abs(out).max()) - 0.9) < 0.01
    assert clean_speech(np.zeros(sr, np.float32), sr).max() == 0


@needs_data
@needs_advice
def test_json_api(monkeypatch):
    monkeypatch.setenv("AGRIBAAT_WARMUP", "0")
    import importlib

    app = importlib.import_module("app")
    out = app.api_demander("Quel est le prix du mil à Kaolack ?", "fr")
    assert out["trouve"] and out["chiffre_cle"]["valeur"] == "300"
    assert out["source"].startswith("PAM") and out["reponse_locale"]
    assert app.api_demander("coggu gawri e Kawlak", "pul")["langue"] == "pul"


@needs_data
@needs_advice
def test_share_and_orientation(monkeypatch):
    """Partage WhatsApp d'une réponse trouvée ; orientation vers un conseiller sinon."""
    monkeypatch.setenv("AGRIBAAT_WARMUP", "0")
    import importlib
    import urllib.parse

    app = importlib.import_module("app")
    res = app.api_assistant.ask_text("Quel est le prix du mil à Kaolack ?", "fr")
    card = app.answer_card(res)
    assert "wa.me/?text=" in card and "orient" not in card
    text = urllib.parse.unquote(app.share_link(res).split("text=", 1)[1])
    assert res.answer_fr in text and "Source : PAM" in text

    miss = app.api_assistant.ask_text("Quelle est la production de café ?", "fr")
    assert not miss.found
    card = app.answer_card(miss)
    assert "ANCAR" in card and "wa.me" not in card
    out = app.api_demander("Quelle est la production de café ?", "fr")
    assert out["orientation"] and out["texte_a_partager"] is None

    hello = app.api_assistant.ask_text("Bonjour", "fr")
    assert "wa.me" not in app.answer_card(hello) and "ANCAR" not in app.answer_card(hello)


@needs_data
@needs_advice
@pytest.mark.parametrize("text", [
    "Quel engrais pour l'arachide ?", "Comment conserver les oignons ?",
    "Quelle dose de NPK pour le mil ?", "engrais biriiji", "traitement maac",
])
def test_practical_question_never_gets_a_production_figure(kb, text):
    """Avant : un produit cité sans mot-clé connu donnait le tonnage de production."""
    q = parse([text], kb)
    assert q.intent == "technique"
    ans = answer(q, kb)
    assert "production" not in ans.text.split("«")[0].lower()
    # extrait de document, recommandations ANACIM, ou aveu d'ignorance — jamais une stat
    assert ((ans.source or "").endswith("(extrait)") or (ans.source or "").startswith("ANACIM")
            or not ans.found)


@needs_data
@needs_advice
@pytest.mark.parametrize("text,lang", [
    ("Gawri am ina ñawi, hol ko mbaawmi waɗde?", "pul"),  # mil malade : que faire ?
    ("Ɓoggi ina nyaama gawri am", "pul"),  # mot inconnu : fiche du mil
    ("Dugub bi dafa am feebar, lan laa war a def?", "wo"),
    ("Maac no Fatick", "srr"),
    ("Soble ci Senegaal", "wo"),
])
def test_free_local_questions_get_a_useful_answer(kb, text, lang):
    """Question libre, jamais vue : réponse utile (pas « je n'ai pas compris »)."""
    from agribaat import langues

    q = parse([text], kb)
    ans = answer(q, kb, langues.get(lang).module)
    assert ans.found and q.product is not None


def test_vocabulary_file_feeds_the_keywords():
    from agribaat import lexicon

    assert "feebar" in lexicon.INTENT_KEYWORDS["technique"]
    assert "ndungu" in lexicon.INTENT_KEYWORDS["pluie"]
    assert lexicon.LOCAL_GLOSS.get("suuf") == "sol"


@needs_data
@needs_advice
def test_practical_answer_cites_the_relevant_passage(kb):
    ans = answer(parse(["Quelle dose de NPK pour le mil ?"], kb), kb)
    assert ans.found and "NPK" in ans.text
    ans = answer(parse(["Comment lutter contre le striga ?"], kb), kb)
    assert ans.found and "striga" in ans.text.lower()


@needs_data
@needs_advice
@pytest.mark.parametrize("text,lang,intent,product", [
    ("hol ko heɓaa e biriiji e hitaande 2022", "pul", "production", "arachide"),
    ("gawri aawaama e ektaar no foti e Kaffrine", "pul", "superficie", "mil"),
    ("ektaar gooto makka rokkata no foti", "pul", "rendement", "mais"),
    ("hol luumo ɗo basi ɓuri hoyde", "pul", "prix", "sorgho"),
    ("xoox gerte no ndiig 2022", "srr", "production", "arachide"),
    ("fo basi a yombe ten", "srr", "prix", "sorgho"),
    ("kilo maalo a jeg no marse Tilene", "srr", "prix", "riz"),
])
def test_local_words_from_reviewed_sentences_are_understood(kb, text, lang, intent, product):
    from agribaat import langues

    q = parse([text], kb)
    assert (q.intent, q.product) == (intent, product)
    assert answer(q, kb, langues.get(lang).module).found


def test_search_stems_word_families():
    from agribaat.search import stem

    assert stem("conserver") == stem("conservation")
    assert stem("irriguer") == stem("irrigation")
    assert stem("oignons") == stem("oignon")
    assert stem("conseil") != stem("conserver")


@needs_data
def test_senegal_map_regions_and_best_crops(kb):
    """Carte : 14 régions dessinées, cultures classées par rendement relatif."""
    from agribaat.carte import REGION_ZONE, SenegalMap

    m = SenegalMap(kb.regional, kb.varieties, kb.rain)
    assert set(m.shapes) == set(REGION_ZONE)
    svg = m.svg("best", "Kaolack")
    assert svg.count("<path") == 14 and "Kaolack" in svg
    for mode in ("zones", "mil", "arachide"):
        assert m.svg(mode).count("<path") == 14
    best = m.best_crops("Sedhiou")
    assert best and best[0].ratio > 1 and best == sorted(best, key=lambda s: -s.ratio)
    card = m.region_card("Kaolack")
    assert "Climat : zone" in card and "kg/ha" in card and "DAPSA" in card
    assert "Aucune culture au-dessus" in m.region_card("Dakar")


def test_area_chart_annotates_max_and_last():
    from datetime import date

    from agribaat.charts import area_chart

    svg = area_chart([(date(2020, 1, 1), 100.0), (date(2021, 1, 1), 300.0),
                      (date(2022, 1, 1), 200.0)], title="Test", unit="t", source="S", yearly=True)
    assert "Max 300 · 2021" in svg and "200 t" in svg and svg.count('class="hit"') == 3
    assert "Pas assez" in area_chart([(date(2020, 1, 1), 1.0)], title="T", unit="", source="")


def _fake_forecast(rain, tmax, wind=10.0, month=7):
    from datetime import date, datetime

    from agribaat.meteo import Day, Forecast

    days = [Day(date(2026, month, 1 + i), r, 80 if r else 0, tmax, tmax - 12, wind, 5.0)
            for i, r in enumerate(rain)]
    return Forecast("Kaolack", datetime(2026, month, 1, 9), True, tmax - 5, 60, wind, days)


def test_weather_advice_rules():
    from agribaat import meteo

    keys = lambda fc: [a.key for a in meteo.advice(fc)]  # noqa: E731
    assert keys(_fake_forecast([15, 10, 5, 0, 0, 0, 0], 33))[0] == "pluie_forte"
    assert keys(_fake_forecast([4, 3, 0, 0, 0, 0, 0], 33))[0] == "pluie"
    assert "recolte" in keys(_fake_forecast([4, 3, 0, 0, 0, 0, 0], 33, month=10))
    assert keys(_fake_forecast([0] * 7, 38)) == ["chaleur"]
    assert keys(_fake_forecast([0] * 7, 30)) == ["sec"]
    assert "vent" in keys(_fake_forecast([0] * 7, 30, wind=40))


def test_weather_advice_in_local_languages():
    from agribaat import meteo, pulaar, sereer, wolof

    fc = _fake_forecast([15, 10, 5, 0, 0, 0, 0], 33)
    adv = meteo.advice(fc)
    wo_text = meteo.local_text(fc, adv, wolof)
    assert "Taw bu bari" in wo_text.text and "fukk" in wo_text.speech  # nombres en lettres
    assert "Toɓo mawɗo" in meteo.local_text(fc, adv, pulaar).text
    assert meteo.local_text(fc, adv, sereer).text.startswith("No fan 7")
    dry = _fake_forecast([0] * 7, 38)
    assert "0 mm" not in meteo.local_text(dry, meteo.advice(dry), wolof).text


@needs_data
@needs_advice
def test_weather_question_uses_the_forecast(kb, monkeypatch):
    from agribaat import meteo

    monkeypatch.setattr(meteo, "forecast", lambda region, force=False: _fake_forecast(
        [0] * 7, 38) if region else None)
    q = parse(["Va-t-il pleuvoir à Kaolack ?"], kb)
    assert q.intent == "meteo"
    ans = answer(q, kb)
    assert ans.found and ans.source.startswith("Open-Meteo") and "38 °C" in ans.text
    assert parse(["Il a plu combien à Mbour ?"], kb).intent == "pluie"  # le passé : ANACIM
