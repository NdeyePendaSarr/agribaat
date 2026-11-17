"""Modèles pré-entraînés, chargés à la demande (lazy) et mis en cache.

Aucun entraînement : on utilise des modèles publics de Hugging Face.
- ASR  : wav2vec2 / MMS fine-tuné sur le wolof
- MT   : NLLB-200 (wolof <-> français)
- TTS  : SpeechT5 fine-tuné sur le wolof + vocodeur HiFi-GAN

Les imports lourds (torch, transformers) sont faits dans les fonctions pour que
le moteur de réponses et les tests fonctionnent sans eux.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import numpy as np

import config

TARGET_SR = 16_000  # fréquence attendue par l'ASR et produite par le TTS


class ModelUnavailable(RuntimeError):
    """Levée quand un modèle ne peut pas être chargé (réseau, mémoire, accès)."""


# ---------------------------------------------------------------- audio utils
def to_mono_16k(sr: int, audio: np.ndarray) -> np.ndarray:
    """Convertit un audio Gradio (sr, ndarray int16/float) en float32 mono 16 kHz."""
    import torch
    import torchaudio.functional as AF

    audio = np.asarray(audio)
    if audio.dtype.kind == "i":
        audio = audio.astype(np.float32) / np.iinfo(audio.dtype).max
    audio = audio.astype(np.float32)
    if audio.ndim == 2:  # (n, canaux) -> mono
        audio = audio.mean(axis=1)
    if sr != TARGET_SR:
        audio = AF.resample(torch.from_numpy(audio), sr, TARGET_SR).numpy()
    return audio


# ------------------------------------------------------------------------ ASR
@lru_cache(maxsize=1)
def _asr():
    try:
        # Auto* : accepte wav2vec2, MMS, HuBERT… tout modèle CTC.
        from transformers import AutoModelForCTC, AutoProcessor

        processor = AutoProcessor.from_pretrained(config.ASR_MODEL)
        model = None
        if "mms" in config.ASR_MODEL.lower():
            try:  # modèles MMS multilingues : sélection de l'adaptateur wolof
                processor.tokenizer.set_target_lang("wol")
                model = AutoModelForCTC.from_pretrained(config.ASR_MODEL, target_lang="wol",
                                                        ignore_mismatched_sizes=True)
            except Exception:  # MMS déjà spécialisé wolof : pas d'adaptateur
                model = None
        if model is None:
            model = AutoModelForCTC.from_pretrained(config.ASR_MODEL)
        model.eval()
        return processor, model
    except Exception as exc:  # noqa: BLE001 — on remonte un message clair
        raise ModelUnavailable(f"ASR indisponible ({config.ASR_MODEL}) : {exc}") from exc


def transcribe(audio_16k: np.ndarray) -> str:
    """Parole wolof (float32 16 kHz) -> texte wolof."""
    import torch

    processor, model = _asr()
    inputs = processor(audio_16k, sampling_rate=TARGET_SR, return_tensors="pt")
    with torch.no_grad():
        logits = model(**inputs).logits
    ids = torch.argmax(logits, dim=-1)[0]
    return processor.decode(ids).strip()


# ---------------------------------------------------------------- traduction
@lru_cache(maxsize=1)
def _mt():
    try:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(config.MT_MODEL)
        model = AutoModelForSeq2SeqLM.from_pretrained(config.MT_MODEL)
        model.eval()
        return tokenizer, model
    except Exception as exc:  # noqa: BLE001
        raise ModelUnavailable(f"Traduction indisponible ({config.MT_MODEL}) : {exc}") from exc


def translate(text: str, src: str, tgt: str) -> str:
    """Traduit avec NLLB. src/tgt : codes NLLB (wol_Latn, fra_Latn)."""
    import torch

    if not text.strip():
        return ""
    tokenizer, model = _mt()
    tokenizer.src_lang = src
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=400)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=400, num_beams=4,
                             forced_bos_token_id=tokenizer.convert_tokens_to_ids(tgt))
    return tokenizer.batch_decode(out, skip_special_tokens=True)[0].strip()


# ------------------------------------------------------------------------ TTS
def load_speaker_embedding(path: Path = config.SPEAKER_EMBEDDING) -> np.ndarray:
    """Charge l'empreinte vocale ; la télécharge une fois si absente.

    SpeechT5 a besoin d'un x-vector (512 valeurs). On utilise le jeu public
    Matthijs/cmu-arctic-xvectors (exemple officiel de la documentation SpeechT5),
    puis on le sauvegarde en .npy pour ne plus dépendre du réseau.
    """
    if path.exists():
        return np.load(path)
    try:
        # Lecture directe du zip (sans la bibliothèque `datasets`, dont pyarrow peut être
        # bloqué par Windows). Même ordre que le script officiel : fichiers .npy triés.
        import io
        import zipfile

        from huggingface_hub import hf_hub_download

        archive = hf_hub_download("Matthijs/cmu-arctic-xvectors", "spkrec-xvect.zip",
                                  repo_type="dataset")
        with zipfile.ZipFile(archive) as zf:
            names = sorted(n for n in zf.namelist() if n.endswith(".npy"))
            emb = np.load(io.BytesIO(zf.read(names[7306]))).astype(np.float32).reshape(-1)
    except Exception as exc:  # noqa: BLE001
        raise ModelUnavailable(
            "Empreinte vocale introuvable. Lancez check_models.py avec Internet, "
            f"ou placez un fichier {path.name} (512 valeurs). Détail : {exc}") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, emb)
    return emb


def _protobuf_fields(buf: bytes):
    """Décodeur protobuf minimal (varint, longueur, 32/64 bits) : (numéro, valeur)."""
    def varint(i: int) -> tuple[int, int]:
        result = shift = 0
        while True:
            byte = buf[i]
            i += 1
            result |= (byte & 0x7F) << shift
            shift += 7
            if byte < 0x80:
                return result, i

    i = 0
    while i < len(buf):
        key, i = varint(i)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, i = varint(i)
        elif wire == 2:
            size, i = varint(i)
            value, i = buf[i:i + size], i + size
        elif wire in (1, 5):
            size = 8 if wire == 1 else 4
            value, i = buf[i:i + size], i + size
        else:
            raise ValueError(f"type protobuf non géré : {wire}")
        yield number, value


class CharTokenizer:
    """Équivalent Python pur du tokenizer SpeechT5 (SentencePiece en mode caractère).

    Sert de repli quand Windows (contrôle intelligent des applications) bloque la DLL
    de `sentencepiece`. Même règles : NFKC, espaces compactés, « ▁ » en tête et à la
    place des espaces, un identifiant par caractère (<unk> sinon), puis </s>.
    """

    def __init__(self, model_file: Path) -> None:
        pieces = [dict(_protobuf_fields(v))[1].decode("utf-8")
                  for number, v in _protobuf_fields(Path(model_file).read_bytes())
                  if number == 1]
        self.ids = {piece: i for i, piece in enumerate(pieces)}
        self.unk, self.eos = self.ids["<unk>"], self.ids["</s>"]

    def encode(self, text: str) -> list[int]:
        import unicodedata

        text = " ".join(unicodedata.normalize("NFKC", text).split())
        text = "▁" + text.replace(" ", "▁")
        return [self.ids.get(c, self.unk) for c in text] + [self.eos]


def _tts_encoder():
    """Renvoie une fonction texte -> input_ids (tenseur 1 x n)."""
    import torch

    try:
        from transformers import SpeechT5Tokenizer

        tokenizer = SpeechT5Tokenizer.from_pretrained(config.TTS_MODEL)
        return lambda text: tokenizer(text=text, return_tensors="pt")["input_ids"]
    except Exception:  # noqa: BLE001 — sentencepiece absent ou bloqué
        from huggingface_hub import hf_hub_download

        char_tok = CharTokenizer(hf_hub_download(config.TTS_MODEL, "spm_char.model"))
        return lambda text: torch.tensor([char_tok.encode(text)])


@lru_cache(maxsize=1)
def _tts():
    try:
        import torch
        from transformers import SpeechT5ForTextToSpeech, SpeechT5HifiGan

        encode = _tts_encoder()
        model = SpeechT5ForTextToSpeech.from_pretrained(config.TTS_MODEL).eval()
        vocoder = SpeechT5HifiGan.from_pretrained(config.TTS_VOCODER).eval()
        speaker = torch.tensor(load_speaker_embedding()).unsqueeze(0)
        return encode, model, vocoder, speaker
    except ModelUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ModelUnavailable(f"TTS indisponible ({config.TTS_MODEL}) : {exc}") from exc


def split_sentences(text: str, max_chars: int = 180) -> list[str]:
    """Découpe en phrases courtes : SpeechT5 dégrade sur les textes longs."""
    chunks: list[str] = []
    for sentence in re.split(r"(?<=[.!?;])\s+", text.strip()):
        while len(sentence) > max_chars:
            cut = sentence.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            chunks.append(sentence[:cut])
            sentence = sentence[cut:].strip()
        if sentence:
            chunks.append(sentence)
    return chunks


def synthesize(text: str) -> tuple[int, np.ndarray]:
    """Texte wolof -> (16000, audio float32), phrase par phrase."""
    import torch

    encode, model, vocoder, speaker = _tts()
    pieces: list[np.ndarray] = []
    silence = np.zeros(int(0.25 * TARGET_SR), dtype=np.float32)
    for chunk in split_sentences(text):
        with torch.no_grad():
            speech = model.generate_speech(encode(chunk), speaker, vocoder=vocoder)
        pieces += [speech.numpy().astype(np.float32), silence]
    if not pieces:
        raise ValueError("Texte vide : rien à synthétiser.")
    return TARGET_SR, np.concatenate(pieces)
