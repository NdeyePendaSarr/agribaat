# 🌾 AgriBaat — version locale

Assistant agricole vocal en wolof, sans entraînement : des modèles pré-entraînés
branchés sur vos données (PAM/WFP, FAOSTAT, DAPSA). Aucun chiffre n'est inventé :
chaque réponse vient d'une table et cite sa source.

```
Voix wolof ─► ASR (MMS wolof) ─► Traduction wo→fr (NLLB) ─► Compréhension (mots-clés FR + wolof)
         ─► Requête sur les données ─► Réponse FR ─► Traduction fr→wo ─► Synthèse vocale wolof
```

## Installation (Windows, une seule fois)

Ouvre un terminal dans le dossier AGRIBAAT :

```bat
py -3.12 -m venv .venv_win
.venv_win\Scripts\activate
cd agribaat_app
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

## Lancement

```bat
python prepare_data.py     :: 1. construit data\processed\*.csv (prix, stats, pluies, conseils, passages)
python check_models.py     :: 2. télécharge et teste les modèles (~4 Go, 1re fois seulement)
python app.py              :: 3. ouvre http://127.0.0.1:7860
pytest                     :: tests du moteur de réponses
```

L'étape 2 affiche un tableau OK / ERREUR. Si une ligne est en ERREUR, l'app
démarre quand même en mode dégradé (réponse en français, sans audio).

## Démo

Voir **`../GUIDE_DEMO.md`** (préparation de la machine, scénario, plan B).

- Au démarrage, l'app charge les modèles vocaux et prépare en arrière-plan les réponses
  vocales des questions types ; le bandeau de l'Assistant indique l'avancement.
  Désactivation : `set AGRIBAAT_WARMUP=0`.
- Chaque réponse vocale est gardée dans `outputs/cache` : une question déjà posée
  répond en 2 à 3 secondes, voix comprise.

## Matériel

| Ressource | Besoin |
|---|---|
| RAM | 8 Go suffisent avec l'ASR par défaut (Wolof-HuBERT ~0,4 Go + NLLB ~2,5 Go + TTS ~0,6 Go) |
| Disque | environ 4 Go pour les modèles (cache Hugging Face) |
| GPU | non nécessaire |

Pour changer d'ASR sans toucher au code : `set AGRIBAAT_ASR_MODEL=<id_du_modèle>` avant `python app.py`.

| ASR | Taille | Temps pour 2 s d'audio (PC 8 Go) | Transcription de « Mas naa jaay lii » |
|---|---|---|---|
| `soynade-research/Wolof-HuBERT-CTC` (défaut) | 94 M | 3,5 s | mës naa jaay ji |
| `asr-africa/wav2vec2-xls-r-wolof-kallaama-fleurs-51-hours` | 315 M | 70 s | mas naa jaay jéen |
| `bilalfaye/wav2vec2-large-mms-1b-wolof` | 964 M | ne charge pas en 8 Go | — |

Les machines de 16 Go ou plus peuvent essayer les deux modèles plus gros, plus précis.

## Structure

| Fichier | Rôle |
|---|---|
| `agribaat/lexicon.py` | Produits, mots-clés français et **wolof (à faire valider)** |
| `agribaat/prepare.py` | Normalisation WFP, FAOSTAT, DAPSA → `data/processed/` |
| `agribaat/knowledge.py` | Requêtes : prix, production, superficie, rendement |
| `agribaat/nlu.py` | Détection intention, produit, lieu, année |
| `agribaat/answers.py` | Réponses en français et en wolof, chiffrées et sourcées |
| `agribaat/wolof.py` | Vocabulaire, phrases modèles et nombres wolof (**à faire valider**) |
| `validation_wolof.py` | Génère `validation_wolof.csv`, la fiche de relecture pour un locuteur natif |
| `agribaat/search.py` | Recherche de passages (secours, extraits cités ISRA / ANACIM) |
| `data/curated/varietes.csv` | Variétés inscrites au Sénégal, saisies depuis le Catalogue ouest-africain |
| `agribaat/models.py` | ASR, traduction, TTS (chargés à la demande, cache audio) |
| `agribaat/warmup.py` | Préchargement des modèles et des réponses types au démarrage |
| `agribaat/pipeline.py` | Enchaînement complet, mode dégradé, chronométrage |
| `app.py` | Interface Gradio (assistant + graphique des prix) |

## Questions couvertes

- **Prix** (2000–2026, 67 marchés) : « Quel est le prix du mil à Kaolack ? »
- **Production / superficie / rendement nationaux** (FAOSTAT, 1961–2024)
- **Par région ou département** (DAPSA, 2017–2022) : « Rendement du mil à Birkilane »
- **Variétés** (Catalogue ouest-africain, 31 variétés de mil, sorgho, arachide, niébé) :
  « Quelle variété de mil à cycle court ? », « variété d'arachide résistante à la sécheresse »
- **Pluies** (bulletins ANACIM 2023–2026, 152 localités) : « Il a plu combien à Mbour ? »
- **Conseils** (recommandations ANACIM) : « Quand récolter l'arachide ? »
- **Questions ouvertes** : extrait cité des documents ISRA / ANACIM, s'il est pertinent

Produits : mil, sorgho, maïs, riz, arachide, niébé, oignon, manioc, fonio.

## À faire avant la démo

1. **Faire remplir `validation_wolof.csv`** par un locuteur natif (`python validation_wolof.py`
   la régénère) : produits, mois, phrases modèles, nombres, réponses complètes, mots-clés.
   Reporter les corrections dans `agribaat/wolof.py` et `agribaat/lexicon.py`.
2. Les réponses wolof sont **construites à partir des données** (plus de traduction
   automatique, sauf en secours) : aucun chiffre ne peut se perdre.
3. **Écouter la prononciation des nombres** (`outputs/*.wav`) : ils sont écrits en
   lettres wolof avant la synthèse vocale.
4. Enregistrer une **vidéo de la démo** dès que tout fonctionne.
