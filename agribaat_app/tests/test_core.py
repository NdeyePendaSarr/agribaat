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

    # Conseils météo et « où vendre » : seul le résumé météo existe en sereer (à écrire).
    advice_only = {k for k in wolof.T if k.startswith(("meteo_", "vente_"))
                   and not k.startswith("meteo_resume")}
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


@needs_data
def test_weekly_bulletin_in_three_languages(kb, monkeypatch):
    """Bulletin : météo + prix du mil et de l'arachide, dans la langue choisie."""
    from agribaat import bulletin, meteo

    monkeypatch.setattr(meteo, "forecast", lambda region, force=False: _fake_forecast(
        [15, 10, 5, 0, 0, 0, 0], 33))
    for lang, opening in (("wo", "Xibaaru AgriBaat"), ("pul", "Kabaruuji AgriBaat"),
                          ("srr", "Xibaar AgriBaat")):
        b = bulletin.build("Kaolack", lang, kb)
        titles = [s.title for s in b.sections]
        assert titles[0].startswith("🌤️") and any("mil" in t for t in titles), lang
        assert b.local.text.startswith(opening) and "FCFA" in b.local.text, lang
    # « Saint-Louis » (météo) / « Saint Louis » (prix PAM) : les prix sont bien trouvés
    assert len(bulletin.build("Saint-Louis", "wo", kb).sections) >= 2


def test_alerts_subscribers_and_outbox(tmp_path, monkeypatch):
    from agribaat import bulletin, meteo

    monkeypatch.setattr(bulletin, "SUBSCRIBERS", tmp_path / "abonnes.csv")
    monkeypatch.setattr(bulletin, "OUTBOX_DIR", tmp_path / "envois")
    hot, calm = _fake_forecast([0] * 7, 38), _fake_forecast([0] * 7, 30)
    hot.region, calm.region = "Kaolack", "Dakar"
    monkeypatch.setattr(meteo, "all_forecasts", lambda force=False: {"Kaolack": hot,
                                                                     "Dakar": calm})
    alerts = bulletin.current_alerts()
    assert [a.region for a in alerts] == ["Kaolack"]
    assert bulletin.alert_text(alerts[0], "wo").text.startswith("Artu AgriBaat ci Kaolack")

    bulletin.subscribe("GIE Ndimbal", "Organisation de producteurs", "Kaolack", "pul",
                       "WhatsApp")
    bulletin.subscribe("Radio Dakar", "Radio communautaire", "Dakar", "wo", "Radio")
    assert len(bulletin.subscribers()) == 2
    path, rows = bulletin.prepare_outbox()
    assert path.exists() and len(rows) == 1  # seul l'abonné de Kaolack est en alerte
    assert rows[0]["destinataire"] == "GIE Ndimbal" and "Reentino" in rows[0]["message"]
    bulletin.unsubscribe(0)
    assert [s["nom"] for s in bulletin.subscribers()] == ["Radio Dakar"]


@pytest.fixture(autouse=True)
def _private_usage_journal(tmp_path, monkeypatch):
    """Les tests n'écrivent jamais dans le vrai journal d'utilisation (chiffres d'impact)."""
    from agribaat import usage

    monkeypatch.setattr(usage, "EVENTS", tmp_path / "journal_usage.csv")
    monkeypatch.setattr(usage, "FEEDBACK", tmp_path / "journal_avis.csv")
    # Ni appel réseau ni écriture dans le vrai cache du LLM pendant les tests.
    from agribaat import llm

    monkeypatch.setenv("AGRIBAAT_LLM", "0")
    monkeypatch.setattr(llm, "CACHE", tmp_path / "llm_cache.json")


def test_usage_journal_is_anonymous_and_counts_field_tests():
    from agribaat import usage

    team = usage.log_question(canal="Texte", langue="Français", sujet="prix", trouve=True,
                              temps_s=0.4)
    p1 = {"code": "P1", "profil": "Productrice", "sexe": "Femme"}
    a = usage.log_question(canal="Voix", langue="Wolof", sujet="meteo", trouve=True,
                           temps_s=12.0, session=p1)
    b = usage.log_question(canal="Voix", langue="Wolof", sujet="", trouve=False, temps_s=8.0,
                           session=p1)
    usage.log_feedback(a, True)
    usage.log_feedback(b, False)
    usage.log_feedback(team, True)
    text = usage.EVENTS.read_text(encoding="utf-8-sig")
    assert "Quel" not in text and "prix du mil" not in text  # aucune question en clair
    field = usage.summary(usage.load(field_only=True))
    assert field["questions"] == 2 and field["participants"] == 1 and field["femmes"] == 1
    assert field["trouve_pct"] == 50 and field["compris_pct"] == 50 and field["voix_pct"] == 100
    assert usage.summary(usage.load())["questions"] == 3
    assert set(usage.load()["sujet"]) == {"Prix des marchés", "Météo en direct",
                                          "Question non comprise"}


def test_field_sheet_before_after(tmp_path):
    from agribaat import usage

    sheet = tmp_path / "resultats.csv"
    sheet.write_text(
        "n_fiche;prix_temps_aujourd_hui_min;t1_temps_s;t1_comprise (oui/2e essai/non);"
        "t1_redit_chiffre (oui/non)\n1;30;20;oui;oui\n2;60;40;2e essai;non\n",
        encoding="utf-8-sig")
    r = usage.field_results(sheet)
    assert r["personnes"] == 2 and r["avant_min"] == 45 and round(r["apres_min"] * 60) == 30
    assert r["premier_coup_pct"] == 50 and r["redit_pct"] == 50


@needs_data
@needs_advice
def test_assistant_answers_are_logged_with_topic(monkeypatch):
    monkeypatch.setenv("AGRIBAAT_WARMUP", "0")
    import importlib

    from agribaat import usage

    app = importlib.import_module("app")
    out = app.on_text("Quel est le prix du mil à Kaolack ?", "Français", [],
                      {"code": "P2", "profil": "Producteur", "sexe": "Homme"})
    assert len(out) == 6 and out[5]  # identifiant de la question pour l'avis
    df = usage.load(field_only=True)
    assert list(df["sujet"]) == ["Prix des marchés"] and list(df["canal"]) == ["Texte"]
    kpis, _, _ = app.impact_view("terrain")
    assert "questions posées" in kpis


def _rain(start, values):
    from datetime import date, timedelta

    d0 = date.fromisoformat(start)
    return [(d0 + timedelta(days=i), float(v)) for i, v in enumerate(values)]


def test_onset_rule_and_false_start():
    """20 mm en 3 jours sans 7 jours secs ensuite ; sinon faux départ."""
    from datetime import date

    from agribaat import calendrier

    # 25 mm le 1er juillet puis 10 jours secs (faux départ), puis 30 mm le 20 et pluies régulières
    values = [25] + [0] * 18 + [30] + [5 if i % 3 == 0 else 0 for i in range(60)]
    onset, false = calendrier.detect(_rain("2025-07-01", values), date(2025, 6, 1),
                                     date(2025, 12, 31))
    assert [f.day.isoformat() for f in false] == ["2025-07-01"]
    assert onset.day.isoformat() == "2025-07-20" and onset.confirmed and onset.observed
    none, _ = calendrier.detect(_rain("2025-07-01", [5] * 60), date(2025, 6, 1),
                                date(2025, 12, 31))
    assert none is None  # jamais 20 mm en 3 jours


@needs_data
def test_sowing_calendar_dry_season_and_late_onset(kb):
    from datetime import date

    from agribaat import calendrier

    dry = {"Kaolack": _rain("2026-10-20", [0] * 47)}
    cal = calendrier.build("Kaolack", "now", kb.varieties, today=date(2026, 11, 20), rain=dry)
    assert cal.status == "Saison sèche" and "fin juin" in cal.message and cal.varieties
    late = {"Kaffrine": _rain("2025-05-01", [0] * 93 + [30] + [6] * 90)}  # démarrage le 2/08
    cal = calendrier.build("Kaffrine", "2025", kb.varieties, rain=late)
    assert cal.onset.day == date(2025, 8, 2) and cal.late and cal.level == "alerte"
    early = {"Sedhiou": _rain("2025-05-01", [0] * 50 + [30] + [6] * 120)}  # 20 juin
    cal = calendrier.build("Sedhiou", "2025", kb.varieties, rain=early)
    assert cal.level == "ok" and cal.varieties.get("mil") and not cal.late


def test_rain_chart_marks_onset_and_forecast():
    from datetime import date

    from agribaat.charts import rain_bars

    days = _rain("2025-07-01", [0, 25, 3, 0, 12])
    svg = rain_bars(days, today=date(2025, 7, 3), onset=date(2025, 7, 2),
                    false_starts=(date(2025, 7, 1),), title="Pluie", source="test")
    assert "semis 02/07" in svg and "faux départ 01/07" in svg and "prévisions" in svg
    assert "(prévision)" in svg and "40 mm" in svg


def _prices(rows):
    import pandas as pd

    return pd.DataFrame(rows, columns=["date", "region", "market", "product", "product_variant",
                                       "price_xof_kg"]).assign(date=lambda d: pd.to_datetime(d["date"]))


def test_where_to_sell_net_price_and_radius():
    """Prix net = prix − transport ; marché trop loin écarté ; marché local repéré."""
    from agribaat import vente

    df = _prices([("2026-10-15", "Kaffrine", "Kaffrine", "mil", "Millet", 300),
                  ("2026-10-15", "Kaolack", "Kaolack", "mil", "Millet", 360),  # ~70 km
                  ("2026-10-15", "Dakar", "Tilene", "mil", "Millet", 500),  # ~270 km
                  ("2020-10-15", "Fatick", "Fatick", "mil", "Millet", 900)])  # trop ancien
    sp = vente.plan(df, "mil", "Kaffrine", transport_rate=1000)
    assert [o.market for o in sp.offers] == ["Kaolack", "Kaffrine"]  # Dakar > 150 km
    assert sp.local.market == "Kaffrine" and 50 < sp.best.km < 90
    assert abs(sp.best.transport - sp.best.km / 10) < 1e-9  # 1000 F / sac de 100 kg / 100 km
    assert round(sp.gain) == round(60 - sp.best.km / 10)
    far = vente.plan(df, "mil", "Kaffrine", transport_rate=1000, max_km=None)
    assert far.best.market == "Tilene"
    assert vente.plan(df, "mil", "Kaffrine", transport_rate=10000).best.market == "Kaffrine"


def test_where_to_sell_seasonality_removes_inflation():
    from agribaat import vente

    rows = []
    for year, base in ((2024, 300), (2025, 400)):  # +33 % d'inflation : ne doit rien changer
        for m in range(1, 13):
            rows.append((f"{year}-{m:02d}-15", "Kaolack", "Kaolack", "mil", "Millet",
                         base * (1.10 if m == 9 else 0.95 if m in (11, 12) else 1.0)))
    season, years = vente.seasonality(_prices(rows))
    assert years == (2024, 2025) and max(season, key=season.get) == 9
    assert abs(season[9] - season[1] - 10.0) < 0.6


@needs_data
def test_where_to_sell_question_in_three_languages(kb):
    from agribaat import pulaar, sereer

    for text, lang in (("Où vendre mon arachide ? Je suis à Kaffrine", None),
                       ("Fan laa wara jaay sama dugub ci Kaolack ?", None),
                       ("Toy mi yeeyata gawri am e Kolda ?", pulaar),
                       ("Où vendre mon mil à Kédougou ?", sereer)):
        q = parse([text], kb)
        assert q.intent == "vendre", text
        a = answer(q, kb, lang)
        assert a.found and "FCFA" in a.text and a.wolof.text and "Prix de détail" in a.text
    q = parse(["Quel est le prix du mil à Kaolack ?"], kb)
    assert q.intent == "prix"  # une simple question de prix ne change pas


def test_month_chart_marks_best_month_and_harvest():
    from agribaat.charts import month_bars

    svg = month_bars({m: (8.0 if m == 9 else -6.0 if m in (11, 12) else 0.5) for m in range(1, 13)},
                     best=9, harvest=(11, 12), title="Quand vendre", source="test")
    assert "vendre ici" in svg and "récolte" in svg and "sept. : +8,0 %" in svg


# ---------------------------------------------------------------- LLM sous contrôle
def _fake_llm(monkeypatch, replies):
    """Remplace l'appel à Claude : `replies` = liste de réponses JSON, dans l'ordre."""
    from agribaat import llm

    calls = []

    def fake(system, user, schema, max_tokens=2000):
        calls.append(user)
        return replies.pop(0) if replies else None
    monkeypatch.setenv("AGRIBAAT_LLM", "1")
    monkeypatch.setattr(llm, "_ask_json", fake)
    return calls


def test_llm_guard_rejects_invented_numbers():
    from agribaat import llm

    passages = ["Semer à 80 cm entre les lignes, 1 200 kg par hectare, cycle de 90 jours."]
    assert llm.check("Semez à 80 cm ; comptez 90 jours.", passages) is None
    assert llm.check("On obtient 1 200 kg par hectare.", passages) is None
    assert "150" in llm.check("Mettez 150 kg d'engrais.", passages)
    assert llm.check("", passages) == "réponse vide"
    assert llm.numbers("2,50 et 3 000") == {"2.5", "3000"}


@needs_data
def test_llm_understanding_feeds_the_normal_engine(kb, monkeypatch):
    """Question que les mots-clés ne comprennent pas : Claude remplit le formulaire, les
    chiffres viennent des tables (même prix que la question classique)."""
    from agribaat.pipeline import Assistant

    calls = _fake_llm(monkeypatch, [{
        "intention": "prix", "culture": "mil", "lieu": "Kaolack", "annee": 2031,
        "sujet": "aucun", "question_fr": "Combien coûte le mil à Kaolack ?"}])
    bot = Assistant(kb, speak=False)
    res = bot.ask_text("Zorglub blabla trucmuche", "fr")
    assert calls and res.llm == "comprehension" and res.intent == "prix"
    ref = bot.ask_text("Quel est le prix du mil à Kaolack ?", "fr")
    assert ref.llm == "" and len(calls) == 1  # question claire : aucun appel au LLM
    assert res.answer_fr == ref.answer_fr and res.highlight.value == ref.highlight.value


@needs_data
def test_llm_synthesis_is_dropped_when_it_invents_a_number(kb, monkeypatch):
    from agribaat.pipeline import Assistant

    q = "Comment lutter contre le striga dans le mil ?"
    bot = Assistant(kb, speak=False)
    base = bot.ask_text(q, "fr")
    if not (base.source or "").endswith("(extrait)"):
        pytest.skip("pas d'extrait de document pour cette question")
    # 1) réponse avec un chiffre inventé : rejetée, on garde l'extrait
    _fake_llm(monkeypatch, [None, {"repond": True, "reponse": "Mettez 987654 kg de fumier.",
                                   "passages_utilises": [1]}])
    res = bot.ask_text(q, "fr")
    assert res.llm == "" and res.answer_fr == base.answer_fr
    # 2) réponse sans chiffre, passage cité : acceptée, source indiquée
    from agribaat import llm

    llm.CACHE.unlink()  # la réponse rejetée est en cache (elle le resterait : même rejet)
    _fake_llm(monkeypatch, [None, {"repond": True, "reponse": "Arrachez le striga avant "
                                   "la floraison et utilisez une variété adaptée.",
                                   "passages_utilises": [1]}])
    res = bot.ask_text(q, "fr")
    assert res.llm == "synthese" and "chiffres vérifiés" in res.source
    assert res.answer_fr.startswith("Arrachez le striga")


def test_llm_disabled_without_key(monkeypatch):
    from agribaat import llm

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("AGRIBAAT_LLM", "auto")
    assert not llm.enabled() and llm.understand("dugub", "Wolof") is None


@needs_data
def test_llm_intent_beats_a_guessed_product_sheet_and_admits_no_answer(kb, monkeypatch):
    """« Mon arachide jaunit » : pas une fiche de prix. Si les documents ne répondent pas
    (avis de Claude), on le dit au lieu d'afficher un extrait hors sujet."""
    from agribaat.pipeline import Assistant

    bot = Assistant(kb, speak=False)
    q = "Mon arachide jaunit, qu'est-ce que je dois faire ?"
    assert bot.ask_text(q, "fr").intent == "fiche"  # mots-clés seuls : fiche devinée
    _fake_llm(monkeypatch, [
        {"intention": "technique", "culture": "arachide", "lieu": "", "annee": 0,
         "sujet": "aucun", "question_fr": "Mon arachide jaunit, que faire ?"},
        {"repond": False, "reponse": "", "passages_utilises": []}])
    res = bot.ask_text(q, "fr")
    assert res.intent == "technique" and res.llm == "comprehension"
    assert "FCFA" not in res.answer_fr and not res.highlight
    assert not res.found and "information fiable" in res.answer_fr  # -> conseiller agricole


@needs_data
def test_llm_off_topic_question_is_declined(kb, monkeypatch):
    """« coupe du monde » : « monde » ressemble à « soñde » (récolte, pulaar) ; sans LLM on
    garde l'ancien comportement, avec le LLM on répond poliment « hors sujet »."""
    from agribaat.pipeline import Assistant

    q = "Qui a gagné la coupe du monde ?"
    assert parse([q], kb).intent_fuzzy
    _fake_llm(monkeypatch, [{"intention": "hors_sujet", "culture": "aucun", "lieu": "",
                             "annee": 0, "sujet": "aucun", "question_fr": q}])
    res = Assistant(kb, speak=False).ask_text(q, "fr")
    assert res.intent == "hors_sujet" and not res.found and "agriculture" in res.answer_fr


# ---------------------------------------------------------------- diagnostic photo
def test_photo_diagnosis_drops_hypotheses_with_numbers():
    from agribaat import diagnostic

    d = diagnostic.parse_reply({
        "photo_exploitable": True, "culture": "mil",
        "observations": ["Taches brunes sur les feuilles", "Environ 30 % des feuilles touchées"],
        "hypotheses": [
            {"probleme": "Mildiou", "type": "maladie", "confiance": "moyenne",
             "indices": "duvet blanchâtre sous les feuilles"},
            {"probleme": "Carence", "type": "carence", "confiance": "faible",
             "indices": "épandre 50 kg d'urée"},  # dose : écartée
            {"probleme": "X", "type": "inconnu", "confiance": "faible", "indices": ""}],
        "question_documents": "mildiou du mil", "conseil_photo": ""})
    assert [h.problem for h in d.hypotheses] == ["Mildiou"] and d.dropped == 1
    assert d.observations == ["Taches brunes sur les feuilles"]  # « 30 % » écarté
    blurry = diagnostic.parse_reply({"photo_exploitable": False, "culture": "inconnue",
                                     "observations": [], "hypotheses": [{"probleme": "a",
                                     "type": "autre", "confiance": "faible", "indices": ""}],
                                     "question_documents": "", "conseil_photo": "Plus près."})
    assert not blurry.usable and not blurry.hypotheses and blurry.photo_tip == "Plus près."
    assert diagnostic.parse_reply({"culture": "mil"}) is None


@needs_data
def test_photo_diagnosis_page(monkeypatch):
    import numpy as np

    import app

    img = (np.random.default_rng(0).random((60, 80, 3)) * 255).astype("uint8")
    assert "Diagnostic photo indisponible" in app.diag_view(img, "")  # sans clé
    assert "Ajoutez une photo" in app.diag_view(None, "")
    _fake_llm(monkeypatch, [
        {"photo_exploitable": True, "culture": "mil", "observations": ["Feuilles jaunies"],
         "hypotheses": [{"probleme": "Mildiou du mil", "type": "maladie",
                         "confiance": "moyenne", "indices": "jaunissement en bandes"}],
         "question_documents": "mildiou du mil", "conseil_photo": ""},
        {"repond": False, "reponse": "", "passages_utilises": []}])
    out = app.diag_view(img, "mil")
    assert "Mildiou du mil" in out and "non vérifiées" in out and "conseiller agricole" in out
    assert "Pas de fiche" in out  # documents muets : on ne conseille pas de traitement
