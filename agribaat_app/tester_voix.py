"""Kit de test vocal : passe un dossier d'enregistrements dans l'assistant.

Usage :
    python tester_voix.py DOSSIER_AUDIO [--attendu attendu.csv] [--voix]

- DOSSIER_AUDIO : fichiers .wav, .mp3, .ogg, .opus (messages vocaux WhatsApp), .flac.
  (Les .m4a d'iPhone ne sont pas lus : envoyez-les plutôt par WhatsApp.)
- --attendu : CSV facultatif « fichier;question » avec ce qui a été réellement dit,
  pour mesurer les erreurs de transcription (WER). Le nom peut être donné sans
  extension (« q01 ») : voir test_voix/questions_a_enregistrer.csv.
- --voix : produit aussi la réponse vocale (beaucoup plus lent ; inutile pour le test).

Résultat : resultats_test_voix.csv (à ouvrir dans Excel), une ligne par fichier :
ce que l'app a entendu, ce qu'elle a compris (intention, produit, lieu), sa réponse.
"""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import soundfile as sf

import config
from agribaat.knowledge import KnowledgeBase
from agribaat.nlu import _edit_distance, parse
from agribaat.pipeline import Assistant

FORMATS = {".wav", ".mp3", ".ogg", ".opus", ".flac"}
OUT = config.APP_DIR / "resultats_test_voix.csv"


def read_audio(path: Path):
    """Lit un fichier audio (le format est reconnu d'après son contenu : les .opus
    de WhatsApp sont des fichiers OGG/Opus)."""
    audio, sr = sf.read(path, dtype="float32")
    return sr, audio


def wer(reference: str, hypothesis: str) -> float:
    ref, hyp = reference.lower().split(), hypothesis.lower().split()
    return _edit_distance(ref, hyp) / max(len(ref), 1)


def load_expected(path: Path | None) -> dict[str, str]:
    if not path:
        return {}
    with path.open(encoding="utf-8-sig") as f:
        return {row[0].strip(): row[1].strip() for row in csv.reader(f, delimiter=";")
                if len(row) >= 2 and row[0].strip() and row[0].strip() != "fichier"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dossier", type=Path)
    parser.add_argument("--attendu", type=Path, default=None)
    parser.add_argument("--voix", action="store_true")
    args = parser.parse_args()

    files = sorted(p for p in args.dossier.iterdir() if p.suffix.lower() in FORMATS)
    skipped = sorted(p.name for p in args.dossier.iterdir() if p.suffix.lower() == ".m4a")
    if not files:
        raise SystemExit(f"Aucun fichier audio lisible dans {args.dossier}")
    expected = load_expected(args.attendu)

    kb = KnowledgeBase(config.PROCESSED_DIR)
    assistant = Assistant(kb, speak=args.voix)
    rows, wers, understood = [], [], 0
    for i, path in enumerate(files, 1):
        start = time.perf_counter()
        try:
            sr, audio = read_audio(path)
            res = assistant.ask_audio(sr, audio)
            q = parse([res.question_wo, res.question_fr], kb)
            error = "; ".join(res.warnings)
        except Exception as exc:  # noqa: BLE001 — un fichier abîmé ne bloque pas le test
            res, q, error = None, None, str(exc)
        said = expected.get(path.name) or expected.get(path.stem, "")  # « q01 » ou « q01.ogg »
        heard = res.question_wo if res else ""
        score = wer(said, heard) if said and heard else None
        if score is not None:
            wers.append(score)
        if q is not None and q.is_complete:
            understood += 1
        rows.append({
            "fichier": path.name,
            "phrase_dite": said,
            "entendu_par_l_app": heard,
            "erreur_transcription": f"{score:.0%}" if score is not None else "",
            "comprise": "oui" if q is not None and q.is_complete else "non",
            "intention": q.intent if q else "",
            "produit": q.product if q else "",
            "lieu": (q.market or q.locality or q.region or q.department or "") if q else "",
            "reponse_fr": res.answer_fr if res else "",
            "reponse_wolof": res.answer_wo if res else "",
            "secondes": round(time.perf_counter() - start, 1),
            "probleme": error,
        })
        print(f"[{i}/{len(files)}] {path.name} -> « {heard} »")

    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)} fichiers testés -> {OUT}")
    if wers:
        print(f"Erreur de transcription moyenne : {sum(wers) / len(wers):.0%}")
    print(f"Questions comprises : {understood}/{len(rows)}")
    if skipped:
        print(f"Ignorés (.m4a non lus) : {', '.join(skipped)}")


if __name__ == "__main__":
    main()
