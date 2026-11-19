# Audit d'AgriBaat par rapport au cahier des charges

Audit du 19 novembre 2026 (démo le 22). Référence : `FICHE_1` (vue d'ensemble),
`FICHE_2` (6 piliers), `FICHE_3` (datasets). Tests : 84 tests automatiques au vert,
29 questions posées dans les 4 langues, interface vérifiée sur ordinateur et téléphone.

## 1. Conformité pilier par pilier

| Pilier (FICHE_2) | Demandé | Livré | État |
|---|---|---|---|
| 1. ASR | Parole wolof / pulaar / sereer → texte | Wolof : Wolof-HuBERT. Pulaar : Wav2vec2-fula (expérimental). Sereer : aucun modèle public utilisable | ✅ wolof · 🟡 pulaar · ❌ sereer (phase 3, prévu) |
| 2. TTS | Réponse orale en wolof | SpeechT5 wolof, nombres dits en lettres, cache audio. En plus : voix pulaar (Meta MMS) | ✅ (au-delà du demandé) |
| 3. NLP/LLM | Comprendre la question, générer la réponse en wolof/français | Compréhension par mots-clés FR/wolof/pulaar/sereer tolérante aux erreurs, traduction NLLB en secours ; réponses générées par phrases modèles relues | 🟡 pas de LLM (choix assumé, voir §3) |
| 4. RAG | Indexer et rechercher l'information agricole | Tables officielles (WFP, FAOSTAT, DAPSA, ANACIM, catalogue CEDEAO) + recherche BM25 dans les documents ISRA/ANACIM, extraits cités | ✅ |
| 5. Backend & API | Orchestrer ASR→LLM→TTS, servir l'API | Pipeline avec mode dégradé et chronométrage ; **API JSON `demander` ajoutée le 19/11** | ✅ |
| 6. Frontend & UX vocale | Interface web/mobile : enregistrer, afficher, lire | Interface Gradio : micro, réponse chiffrée et sourcée, audio, prix, production, conseils ; adaptée au téléphone, installable (PWA) | ✅ |

| Langues (FICHE_1) | Demandé | Livré |
|---|---|---|
| Wolof | prioritaire | ✅ voix + texte (phrases encore à faire valider par un locuteur natif) |
| Pulaar | phase 2 | ✅ voix + texte, phrases relues par Mouhameth (18/11) |
| Sereer | phase 3 | 🟡 texte seulement, phrases relues par Seydina (18/11) |
| Français | interface | ✅ |

| Datasets (FICHE_3) | Utilisation |
|---|---|
| DS-08 FAOSTAT, DS-10 DAPSA, DS-11 ANACIM, DS-12 WFP, DS-13 ISRA | Base de connaissances de l'Assistant ✅ |
| DS-02 KALLAAMA | Évaluation des modèles pulaar/sereer, mesures de tolérance aux erreurs ✅ |
| DS-01 ALFFA, DS-03 GalsenAI TTS, DS-04 FLEURS, DS-06/07 | Collectés ; utilisés via les modèles publics déjà entraînés dessus (pas d'entraînement propre) |
| DS-05 Common Voice | Absent (inscription manuelle) |
| DS-09 AGRIDATA | Collecté, quasi vide |

## 2. Corrections et améliorations du 19 novembre

**Assistant (toutes langues)**
- Salutations comprises (« Bonjour », « Salaam aleekum », « Jam waali », « Na fio ») :
  avant, « bonjour » renvoyait un extrait sans rapport d'une Lettre de l'ISRA.
  L'assistant répond par ce qu'il sait faire, avec les phrases d'aide déjà relues.
- « Prix de l'oignon à Dakar » : le marché « Dakar » n'a pas d'oignon, mais la région en a.
  Avant : « pas de prix ». Maintenant : la moyenne de la région, avec ses deux marchés.
- Pulaar : « Ndakaaru » est reconnu comme Dakar (avant : la réponse donnait la moyenne nationale).
- Wolof : « ban xeetu dugub moo gaaw » donnait la production ; il donne maintenant les
  variétés de mil à cycle court.
- Mots-clés d'intention déformés d'une lettre par la reconnaissance vocale (« cogu » au
  lieu de « coggu ») : désormais compris.
- Audio : avant la reconnaissance vocale, les longs silences sont coupés et un
  enregistrement trop faible est remonté (wolof et pulaar).

**Livrables du cahier des charges**
- Pilier 5 : API JSON `demander(question, langue)` (voir `agribaat_app/README.md`).
- Pilier 6 : sur téléphone, l'en-tête est réduit et le micro remonte, les langues sont
  en grille 2 × 2, les questions types sont deux par ligne. L'app est installable sur
  l'écran d'accueil (PWA).
- README mis à jour (schéma, langues, API, téléphone).

## 3. Écarts restants (à dire honnêtement au jury)

1. **Pas de LLM génératif.** Le cahier des charges prévoit un « LLM connecté à une base de
   connaissances ». Nous avons choisi des réponses construites à partir des tables :
   **aucun chiffre ne peut être inventé**, et cela tourne sur un PC de 8 Go sans GPU. Un
   petit LLM pourrait plus tard reformuler les extraits cités, sans toucher aux chiffres
   (prochaine étape annoncée).
2. **Sereer sans voix** : pas de modèle public de reconnaissance ni de synthèse ; il faut
   entraîner le nôtre sur KALLAAMA (≈ 2 à 3 mois, `FEUILLE_DE_ROUTE_LANGUES.md`).
3. **Pulaar vocal expérimental** : environ 80 % d'erreur par mot sur la radio. Pour la
   démo, préférer la question type.
4. **Wolof pas encore validé** par un locuteur natif (`validation_wolof.csv`).
5. **Micro sur téléphone** : les navigateurs exigent HTTPS. En réseau local, seules les
   questions écrites marchent ; avec Internet, un lien de partage HTTPS
   (`GRADIO_SHARE=True`) permet le micro.
6. **Lenteur sur PC 8 Go** : 30 s à 2 min pour une question vocale nouvelle. Les questions
   répétées la veille répondent en 2 à 3 s (cache).

## 4. À faire avant le 22 novembre

- [ ] Faire relire `validation_wolof.csv` par un locuteur natif.
- [ ] Choisir la machine de démo (16 Go si possible), y répéter le scénario de
      `GUIDE_DEMO.md`, puis refilmer avec `python demo_auto.py --filmer`.
- [ ] Copier `outputs/demo_agribaat.webm` et `outputs/demo_secours.html` sur une clé USB.
