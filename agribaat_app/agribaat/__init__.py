"""AgriBaat — assistant vocal agricole en wolof (version locale, hors OctOpus).

Modules :
- lexicon   : produits, lieux et mots-clés (français + wolof)
- prepare   : normalisation des données brutes (WFP, FAOSTAT, DAPSA)
- knowledge : requêtes sur les tables normalisées
- nlu       : compréhension de la question (intention + entités)
- answers   : construction de réponses sourcées en français
- models    : modèles pré-entraînés (ASR, traduction, TTS), chargés à la demande
- pipeline  : enchaînement voix → texte → réponse → voix
"""

__version__ = "0.1.0"
