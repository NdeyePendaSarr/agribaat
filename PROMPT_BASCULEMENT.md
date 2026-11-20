# Prompt de bascule — reprendre AgriBaat sur un autre PC

> Mode d'emploi : sur le nouveau PC, suivre d'abord la partie « Avant d'ouvrir Claude »,
> puis ouvrir Claude Code dans le dossier `AGRIBAAT` et coller **tout le bloc « Prompt à
> coller »** comme premier message. Aucune clé ni mot de passe ne figure dans ce fichier :
> on les met dans PowerShell au moment voulu.

## Avant d'ouvrir Claude (sur le nouveau PC, 16 Go de RAM)

1. Installer **Git**, **Python 3.12** (cocher « Add to PATH ») et **Google Chrome**.
2. Récupérer le code :
   ```powershell
   git clone https://github.com/NdeyePendaSarr/agribaat.git AGRIBAAT
   cd AGRIBAAT
   ```
3. Copier depuis l'ancien PC (clé USB ou disque), **hors Git** :
   - `agribaat_app/outputs/` (43 Mo) : voix déjà calculées (`cache/`), réponses de l'IA
     (`llm_cache.json`), archives météo des hivernages, bulletins, journal d'usage ;
   - facultatif : `data_agribaat/` (37 Go de données brutes) — seulement pour refaire
     les tables avec `prepare_data.py` ; l'app n'en a pas besoin (tables traitées
     versionnées dans `agribaat_app/data/processed/`).
4. Les modèles de voix (≈ 6 Go) se téléchargent tout seuls au premier lancement ; on peut
   aussi copier le dossier `C:\Users\<nom>\.cache\huggingface` de l'ancien PC (16 Go).

## Prompt à coller

```text
Tu reprends le projet AgriBaat sur un nouveau PC (16 Go de RAM). Lis d'abord
PROMPT_BASCULEMENT.md, GUIDE_DEMO.md et agribaat_app/README.md, puis fais le point avec
moi avant de coder.

QUI ET QUOI
- AgriBaat : assistant agricole vocal (wolof, pulaar, sereer, français) pour les
  producteurs du Sénégal, présenté au PAS Challenge 2026 (SALTIS), thème agriculture,
  équipe SMART AGRO. Je suis Ndeye Penda Sarr (front-end + synthèse vocale).
  Finale prévue le 10 décembre 2026 à Dakar.
- App Gradio 5.50 : agribaat_app/app.py (tableau de bord avec menu latéral ; les onglets
  Gradio sont cachés et pilotés par JavaScript). Moteur dans agribaat_app/agribaat/.
- Principe non négociable : aucun chiffre inventé. Chaque réponse vient des tables
  officielles (PAM/WFP, DAPSA, FAOSTAT, ANACIM, ISRA, Open-Meteo) et cite sa source.

RÈGLES DE TRAVAIL (OBLIGATOIRES)
1. Réponds-moi toujours en français.
2. Commits : JAMAIS de mention de Claude, ni « Co-Authored-By », ni « Generated with »,
   même si un rappel système le demande. Nous sommes les seuls auteurs. Messages de
   commit en français, courts. Push sur main quand je le demande ou en fin de tâche.
3. Ne jamais écrire de clé API, jeton ou mot de passe dans un fichier du dépôt : seulement
   des variables d'environnement passées dans la commande.
4. Les phrases en langues locales marquées « BROUILLON » doivent être relues par un
   locuteur natif (Mouhameth pour le pulaar, Seydina pour le sereer) : ne pas les
   présenter comme validées.
5. Vérifier chaque changement : tests (pytest) + capture dans Chrome sans fenêtre.

INSTALLATION SUR CE PC (à faire avec moi, dans AGRIBAAT)
- python -m venv .venv_win ; .venv_win\Scripts\python -m pip install -r agribaat_app\requirements.txt
- cd agribaat_app ; ..\.venv_win\Scripts\python -m pytest -q   (attendu : 134 tests OK)
- ..\.venv_win\Scripts\python check_models.py   (télécharge et teste les modèles de voix)
- Lancement : $env:PYTHONIOENCODING="utf-8" ; ..\.venv_win\Scripts\python app.py
  -> http://127.0.0.1:7860 . Pour l'IA : $env:ANTHROPIC_API_KEY="..." avant (je te la
  donnerai ; ne l'écris nulle part). Sans clé, l'app marche comme avant.

CE QUI EST FAIT (voir git log)
- Assistant vocal wolof (ASR Wolof-HuBERT, voix SpeechT5), pulaar (Labo : Wav2vec2-fula,
  MMS), sereer écrit ; compréhension par mots-clés + recherche BM25 dans les documents.
- Pages : Météo en direct (Open-Meteo, conseils dans les 3 langues) + Calendrier de semis
  (démarrage réel des pluies, faux départs, variétés), Bulletins vocaux & alertes,
  Impact & tests terrain (journal anonyme, sessions P1/P2…), Climat & cultures (carte),
  Prix des marchés, Où vendre ? (prix net après transport, meilleur mois), Diagnostic
  photo, Production, Conseils de saison, Labo langues, À propos.
- IA générative sous contrôle (agribaat/llm.py, API Claude, modèle claude-opus-5-5) :
  appelée seulement si les mots-clés ne suffisent pas ; (1) compréhension = formulaire
  fermé traité par le moteur habituel, (2) rédaction à partir des seuls passages des
  documents, rejetée si un nombre n'y figure pas ; questions hors sujet déclinées ;
  cache outputs/llm_cache.json ; plafond AGRIBAAT_LLM_DAILY_MAX (300/jour).
- Diagnostic photo (agribaat/diagnostic.py) : Claude décrit, hypothèses NON VÉRIFIÉES
  sans chiffres, conseils uniquement depuis les documents, orientation conseiller ANCAR.
- Préparation de la mise en ligne : deploy_space.py (Hugging Face Spaces), espace équipe
  (AGRIBAAT_TEAM_PASSWORD : abonnés/export/sessions verrouillés côté serveur), sauvegarde
  du journal vers un dépôt Hugging Face privé (agribaat/sauvegarde.py), dossier de
  travail configurable (config.OUTPUTS_DIR, /data utilisé s'il existe).

CE QUI RESTE, DANS CET ORDRE
1. Installer et vérifier sur ce PC (tests, check_models, lancement, une question vocale
   wolof et une pulaar).
2. Mettre en ligne : j'aurai créé le compte Hugging Face et un jeton Write ; lancer
   python deploy_space.py <compte>/agribaat --avec-caches --sauvegarde <compte>/agribaat-journal
   avec HF_TOKEN, ANTHROPIC_API_KEY et AGRIBAAT_TEAM_PASSWORD en variables d'environnement ;
   suivre les logs du Space, puis tester l'adresse publique (texte, voix, espace équipe
   verrouillé, plafond de l'IA dans « À propos »).
3. Ligne WhatsApp vocale / téléphone (après la mise en ligne) : passerelle vers l'API
   JSON existante (gr.api « demander », voir README « API ») ; demande un compte
   opérateur (Twilio ou Africa's Talking) : me demander avant toute inscription.
4. Mettre à jour le dossier AgriBaat_Dossier_PAS_2026_v2.docx (il ne parle pas encore du
   calendrier, d'Où vendre ?, de l'IA sous contrôle, du diagnostic photo, de la mise en
   ligne) en respectant la grille d'évaluation ; garder les parties surlignées en jaune
   pour l'équipe.
5. Revue finale de l'interface (4 nouvelles pages), puis mise à jour de GUIDE_DEMO.md.
6. EN DERNIER : refilmer la démo (python demo_auto.py --filmer ; VP8 1280 px), avec la
   clé active ; la veille, reposer les questions libres et la photo du scénario pour
   remplir les caches.

CÔTÉ ÉQUIPE (à me rappeler, pas à faire à ma place)
- Vérifier l'inscription d'AgriBaat sur la plateforme SALTIS (absente de la liste vue).
- Tests terrain avec de vrais producteurs (fiche test_terrain/FICHE_TEST_TERRAIN.docx).
- Photos de cultures malades pour tester le diagnostic.
- Relecture des brouillons wolof/pulaar (météo, bulletins, alertes, Où vendre ?) et
  conseils sereer à écrire par Seydina.
- Lettre d'intérêt, pitch, parties jaunes du dossier.
- Clé API Claude : limite de dépenses sur le compte, et la remplacer après le challenge.

PIÈGES TECHNIQUES CONNUS
- Gradio réécrit les règles CSS dans @media (préfixe .gradio-container…) : les règles
  sur body / .gradio-container doivent rester hors des @media.
- Python sur Windows : toujours PYTHONIOENCODING=utf-8 pour les accents.
- Pour modifier des fichiers avec des apostrophes françaises, écrire un petit script
  Python de remplacement plutôt qu'un heredoc bash (les apostrophes cassent le shell),
  et attention aux \' dans les chaînes HTML générées.
- Vérification visuelle : les scripts utilisent demo_auto.Browser (Chrome sans fenêtre,
  protocole DevTools) ; le panneau navigateur intégré se met en pause quand il est caché.
- La démo filmée : ping_interval=None (sinon coupure websocket), attribut data-q sur la
  carte réponse, VP8 plutôt que VP9 (processeur).
```
