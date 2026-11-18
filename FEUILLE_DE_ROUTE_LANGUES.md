# Feuille de route : pulaar et sereer (phases 2 et 3)

État au 18 novembre 2026, établi en testant les modèles publics existants sur les
enregistrements de radio agricole **KALLAAMA** (OpenSLR 151) déjà collectés.

## 1. Où en est chaque langue

| | Wolof | Pulaar | Sereer |
|---|---|---|---|
| Données KALLAAMA collectées | ≈ 55 h | ≈ 32 h | ≈ 38 h |
| Reconnaissance vocale | ✅ en production | 🟡 modèles publics, à améliorer | ❌ aucun modèle utilisable |
| Phrases de réponse | ✅ (à faire valider) | 🟡 brouillon (`agribaat/pulaar.py`) à relire | 🟠 brouillon très incertain (`agribaat/sereer.py`) à réécrire |
| Voix de synthèse | ✅ | 🟡 Meta MMS « peul » à faire juger | ❌ aucune (réponses écrites) |
| Dans l'app | Assistant complet | Assistant (voix + texte) | Assistant (texte seulement) |

**Mise à jour du 18 novembre :** pulaar et sereer sont branchés dans l'Assistant. Fiches
de relecture : `python validation_langues.py pulaar` et `python validation_langues.py
sereer` (fichiers `validation_pulaar.csv`, `validation_sereer.csv`). Les étapes 2 à 5
de la phase 2 et 3 de la phase 3 se résument désormais à corriger ces fiches.

## 2. Résultats des tests (15 extraits de radio par modèle)

### Reconnaissance vocale pulaar

| Modèle | Erreur par mot | Temps / extrait (PC 2 cœurs) | Remarque |
|---|---|---|---|
| `Leonel-Maia/Wav2vec2-fula` | 82 % | **4,6 s** | Erreurs surtout d'orthographe ; **retenu pour le Labo** (rapide) |
| `ngia/whisper-small-pulaar` | 68 % | 47 s | Trop lent sur ce PC |
| `abdouaziz/pulaar-V2` | 61 % | 43 s | Probablement entraîné sur KALLAAMA : score flatté |

Test aller-retour : une phrase pulaar lue par la voix MMS puis réécoutée par
`Wav2vec2-fula` est reconnue presque mot pour mot.

### Reconnaissance vocale sereer
- `taiyintaiyang/sereer-omp` et `taiyintaiyang/sereer-kallaama-15-mins` : **inutilisables**,
  leurs auteurs n'ont pas publié le vocabulaire (`vocab.json`).
- Meta MMS (1 162 langues) : **pas d'adaptateur sereer** (`srr`).

### Voix de synthèse
- Pulaar : `facebook/mms-tts-ful` (peul générique) fonctionne, ≈ 10 s par phrase.
  Prononciation à juger par un locuteur sénégalais.
- Sereer : aucun modèle sérieux (un seul essai amateur).

### Traduction français → langue (aide à la rédaction des phrases de réponse)
- Sereer : plusieurs modèles `Fallovski/french-serer-*` (dont un léger, 82 M de paramètres).
- Pulaar : `morlayecis0003/nllb-200-pulaar-mairie` (1,4 Go).
- À utiliser seulement pour **proposer** un premier jet, toujours relu par un locuteur
  (la traduction automatique perd des informations, comme constaté en wolof).

## 3. Plan proposé

L'architecture est prête : il suffit d'ajouter, pour chaque langue, un module de phrases
modèles sur le modèle de `agribaat/wolof.py`, ses mots-clés, et ses modèles vocaux.

### Phase 2 — Pulaar (≈ 3 à 4 semaines) — responsable : Mouhameth Diop

| Étape | Durée | Détail |
|---|---|---|
| 1. Entraîner la reconnaissance vocale | 1 à 2 sem. | Affiner `Wav2vec2-fula` sur KALLAAMA pulaar (+ FLEURS `ff_sn`) ; GPU gratuit (Colab / Kaggle) ; objectif : erreur < 40 % |
| 2. Écrire les phrases de réponse | 2 à 3 jours | 25 phrases modèles + vocabulaire + nombres, par un locuteur ; fiche de relecture comme `validation_wolof.csv` |
| 3. Mots-clés de compréhension | 1 à 2 jours | Produits, prix, pluie, conseils ; à tirer des transcriptions KALLAAMA |
| 4. Valider la voix MMS | 1 jour | Si la prononciation ne convient pas : affinage sur ≈ 5 h d'une seule voix |
| 5. Intégration et tests | 2 à 3 jours | Langue « Pulaar » dans l'Assistant |

### Phase 3 — Sereer (≈ 2 à 3 mois) — responsable : Seydina Wade

| Étape | Durée | Détail |
|---|---|---|
| 1. Préparer les données | 1 sem. | 38 h KALLAAMA, dont ≈ 16 h sans français : nettoyage du code-switching |
| 2. Entraîner la reconnaissance vocale | 2 à 3 sem. | Affiner `wav2vec2-xls-r-300m` (ou HuBERT, comme le wolof) |
| 3. Phrases de réponse et mots-clés | 1 sem. | Premier jet avec `french-serer-opusmt`, relu par un locuteur |
| 4. Voix de synthèse | 1 à 2 mois | Enregistrer 5 à 10 h d'une seule voix (studio), puis affiner un modèle VITS/MMS. En attendant : réponses sereer **à l'écrit** |
| 5. Intégration et tests | 1 sem. | |

## 4. Moyens nécessaires

- **Calcul** : un GPU pour l'entraînement (Google Colab ou Kaggle, gratuits, suffisent
  pour des modèles de 300 M de paramètres).
- **Locuteurs** : un locuteur pulaar et un locuteur sereer pour la relecture
  (≈ 2 jours chacun) ; une voix sereer pour 5 à 10 h d'enregistrement.
- **Machine de démonstration** : 16 Go de mémoire pour faire tourner plusieurs langues.

## 5. Limites de ces tests

- 15 extraits par modèle : ordre de grandeur, pas une mesure définitive.
- Extraits de radio (parole spontanée, bruit) : des questions posées calmement au micro
  donneront probablement de meilleurs résultats.
- Les orthographes du pulaar et du sereer varient : une partie des « erreurs » n'en
  sont pas pour un lecteur.
