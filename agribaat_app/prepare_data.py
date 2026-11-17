"""Étape 1 : construit data/processed/*.csv à partir des données brutes.

Usage : python prepare_data.py [--raw CHEMIN_VERS_data_agribaat]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import config
from agribaat.prepare import prepare_all


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=config.RAW_DATA_DIR,
                        help="dossier data_agribaat (défaut : %(default)s)")
    args = parser.parse_args()
    if not args.raw.exists():
        raise SystemExit(f"Dossier introuvable : {args.raw}")
    counts = prepare_all(args.raw, config.PROCESSED_DIR)
    for name, n in counts.items():
        print(f"  {name:<9} {n:>7} lignes -> {config.PROCESSED_DIR / (name + '.csv')}")
    print("OK : données prêtes.")


if __name__ == "__main__":
    main()
