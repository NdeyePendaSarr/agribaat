# Guide de démo — AgriBaat (PAS Challenge 2026)

## 1. La veille : préparer la machine

1. Choisir **la machine la plus puissante de l'équipe** (idéalement 16 Go de mémoire).
   Sur un PC 8 Go / 2 cœurs, une question *nouvelle* met 30 s à 2 min avec la voix.
2. Installer l'app (voir `agribaat_app/README.md`), puis :
   ```bat
   cd agribaat_app
   python prepare_data.py
   python check_models.py      :: doit afficher « Tout est prêt. »
   ```
3. **Répéter le scénario ci-dessous une fois en entier** : chaque réponse vocale est
   gardée en cache (`agribaat_app/outputs/cache`). Le jour J, ces questions répondent
   en 2 à 3 secondes, voix comprise.
4. Enregistrer une **vidéo de secours** de cette répétition. Le plus simple : app lancée,
   `python demo_auto.py` déroule tout le scénario seul dans une fenêtre Chrome (avec
   les réponses vocales) ; filmer l'écran pendant ce temps avec **Win + Alt + R** (Xbox
   Game Bar, vidéo dans `Vidéos\Captures`) ou l'enregistreur d'écran d'Ubuntu.
   Encore plus simple : `python demo_auto.py --filmer` : Chrome filme lui-même l'onglet,
   voix comprise, dans `outputs/demo_agribaat.webm` (environ 4 min, 20 Mo).
5. Sans rien filmer : `python demo_auto.py --headless` produit
   `outputs/demo_secours.html`, les écrans de la démo avec les vraies réponses vocales,
   qui s'enchaînent tout seuls dans un navigateur, même sans internet.

## 1 ter. Si l'app ne démarre plus (après un `git pull`)

Lancer d'abord le diagnostic, qui dit en clair ce qui ne va pas :
```bash
cd agribaat_app
python diagnostic.py
```

**Remettre la copie à jour.** L'historique GitHub a été réécrit le 18 novembre : une
copie récupérée avant cette date ne peut pas être mise à jour par un simple `git pull`
(conflits). Si vous n'avez pas de modifications à vous à garder :
```bash
git fetch origin
git reset --hard origin/main
```
⚠️ `reset --hard` efface les modifications locales non envoyées : si vous en avez,
mettez-les de côté avant (copie du dossier).

Ensuite : `pip install -r agribaat_app/requirements.txt` (l'app demande Gradio 5), puis
`python prepare_data.py` si le diagnostic signale des données manquantes.

## 1 bis. Tester la voix avec nos propres voix (à faire au plus tôt)

1. Chaque membre enregistre les 14 questions de
   `agribaat_app/test_voix/questions_a_enregistrer.csv` (q01 à q14), par exemple en
   **messages vocaux WhatsApp**, d'une voix normale, sans bruit de fond.
2. Nommer les fichiers `q01`, `q02`… (n'importe quel format : .ogg, .opus, .mp3, .wav ;
   **pas de .m4a** d'iPhone) et les mettre dans un dossier, un dossier par personne.
3. Lancer :
   ```bat
   cd agribaat_app
   ..\.venv_win\Scripts\python.exe tester_voix.py test_voix\bachir --attendu test_voix\questions_a_enregistrer.csv
   ```
4. Ouvrir `resultats_test_voix.csv` dans Excel : pour chaque question, ce que l'app a
   entendu, ce qu'elle a compris et sa réponse. Envoyer ce fichier : les mots mal
   entendus servent à améliorer la compréhension.

Les enregistrements restent sur la machine (ils ne sont pas envoyés sur GitHub).

## 2. Le jour J

1. Fermer tout ce qui consomme de la mémoire : Chrome (onglets lourds), Docker Desktop
   (`wsl --shutdown`), autres serveurs.
2. Lancer l'app **10 minutes avant** :
   ```bat
   cd agribaat_app
   ..\.venv_win\Scripts\python.exe app.py
   ```
3. Ouvrir http://127.0.0.1:7860 dans un navigateur **au premier plan** (un onglet en
   arrière-plan peut ne pas recevoir les réponses).
4. Attendre que le bandeau affiche **« 🎙️ Mode vocal prêt »**.

## 3. Scénario (5 minutes)

| # | Question (cliquer la question type ou la taper) | Ce qu'on montre |
|---|---|---|
| 1 | « Quel est le prix du mil à Kaolack ? » | Réponse chiffrée, **source citée**, réponse **wolof lue à voix haute** |
| 2 | « njëg dugub ci Kaolack » (mode Wolof) | Question **en wolof** comprise directement, même réponse |
| 3 | « Quelle variété de mil à cycle court ? » | Conseil tiré du **Catalogue ouest-africain des variétés** |
| 4 | « Il a plu combien à Mbour ? » | Pluie tirée des **bulletins ANACIM** |
| 5 | « Quand récolter l'arachide ? » | **Recommandation ANACIM** datée |
| 6 | Onglet **📈 Prix des marchés** | Graphique, marché le moins cher / le plus cher |
| 7 | Onglet **🌦️ Conseils** | Catalogue filtrable, pluie par région |
| 8 | Micro : dire « Ñaata la kilo dugub di jar ci Kaolack ? » | Chaîne vocale complète (prévoir 1 à 2 min si la phrase est nouvelle) |
| 9 | Langue **Pulaar**, question type « coggu gawri e Kawlak » (ou au micro) | Même réponse chiffrée **en pulaar, lue à voix haute** |
| 10 | Langue **Sereer · écrit**, taper « ndoɓ no Mbour » | Réponse **écrite en sereer** (pas encore de voix sereer) |

Phrases pulaar et sereer relues et approuvées par Mouhameth et Seydina (18/11). La
reconnaissance vocale pulaar reste expérimentale : pour la démo, préférer la question
type ; le sereer se pose à l'écrit.

## 4. Messages clés pour le jury

- **Aucun chiffre inventé** : chaque réponse vient d'une table officielle (PAM/WFP,
  FAOSTAT, DAPSA, ANACIM, catalogue CEDEAO) et cite sa source.
- **Le wolof d'abord** : réponses construites directement en wolof (pas de traduction
  automatique qui perd des informations) ; nombres dits en lettres.
- **Fonctionne sans GPU ni internet** une fois les modèles téléchargés.
- **Prochaines étapes** : pulaar puis sereer, chiffrées dans `FEUILLE_DE_ROUTE_LANGUES.md`
  (données KALLAAMA déjà collectées, modèles existants testés), fiches d'itinéraire
  technique, LLM pour reformuler les extraits cités.

## 5. Plan B

| Problème | Solution |
|---|---|
| Voix trop lente | Taper la question ; montrer la réponse écrite et l'audio d'une question déjà en cache |
| Micro qui ne marche pas | Bouton « importer » un fichier audio, ou passer en question écrite |
| App plantée | Relancer `app.py` (le cache audio est conservé), ou passer la vidéo de secours |

## 6. Limites connues (à dire si on nous les demande)

- Vocabulaire wolof **en cours de validation** par un locuteur natif (`validation_wolof.csv`).
- Prix jusqu'à octobre 2026, statistiques régionales 2017–2022, pluies juin–octobre.
- Variétés : mil, sorgho, arachide, niébé (pas de maïs ni de riz dans le catalogue disponible).
