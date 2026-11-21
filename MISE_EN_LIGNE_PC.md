# Mettre AgriBaat en ligne depuis un PC Linux (Ubuntu)

L'appli tourne sur le PC, et **ngrok** lui donne une adresse publique HTTPS **fixe**
(elle reste la même après un redémarrage). Le PC doit rester **allumé, branché sur
secteur et connecté à Internet** jusqu'à la fin de l'évaluation.

Pourquoi ngrok plutôt qu'un lien Cloudflare rapide : le lien déposé dans le formulaire
ne peut plus être modifié. Un lien Cloudflare rapide change à chaque redémarrage ;
le domaine gratuit de ngrok, lui, ne change pas.

Ne jamais écrire une clé, un jeton ou un mot de passe dans un fichier du dépôt ni dans
une capture d'écran partagée.

---

## 1. Préparer le code (déjà fait si les tests passent)

```bash
cd ~/agribaat
git pull origin main
source .venv/bin/activate
cd agribaat_app
python -m pytest -q            # attendu : 134 passed
```

Copier le dossier `outputs/` reçu de Ndeye dans `~/agribaat/agribaat_app/outputs/`
(voix déjà calculées et réponses de l'IA en cache : la démo est rapide dès le départ).

## 2. Les secrets, dans un fichier privé hors du dépôt

```bash
mkdir -p ~/.config
nano ~/.config/agribaat.env
```

Écrire ces trois lignes (avec les vraies valeurs), puis Ctrl+O, Entrée, Ctrl+X :

```
ANTHROPIC_API_KEY=sk-ant-...
AGRIBAAT_TEAM_PASSWORD=mot-de-passe-equipe
PYTHONIOENCODING=utf-8
```

Puis le rendre lisible par vous seul :

```bash
chmod 600 ~/.config/agribaat.env
```

## 3. Installer ngrok et réserver l'adresse fixe

1. Créer un compte gratuit sur https://ngrok.com.
2. Dans le tableau de bord ngrok : **Domains** → réserver le domaine gratuit
   (du type `quelque-chose.ngrok-free.app`). C'est l'adresse à donner au jury.
3. Copier son **Authtoken** (tableau de bord → Your Authtoken).

```bash
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
echo "deb https://ngrok-agent.s3.amazonaws.com bookworm main" | sudo tee /etc/apt/sources.list.d/ngrok.list
sudo apt update && sudo apt install -y ngrok
ngrok config add-authtoken VOTRE_AUTHTOKEN
```

## 4. Faire tourner l'appli et ngrok en continu (redémarrage automatique)

Deux services : ils démarrent tout seuls au démarrage du PC et redémarrent en cas d'arrêt.

```bash
mkdir -p ~/.config/systemd/user
nano ~/.config/systemd/user/agribaat.service
```

Contenu :

```
[Unit]
Description=AgriBaat

[Service]
WorkingDirectory=%h/agribaat/agribaat_app
EnvironmentFile=%h/.config/agribaat.env
ExecStart=%h/agribaat/.venv/bin/python app.py
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
```

```bash
nano ~/.config/systemd/user/ngrok.service
```

Contenu (remplacer le domaine par le vôtre) :

```
[Unit]
Description=Adresse publique ngrok pour AgriBaat

[Service]
ExecStart=/usr/bin/ngrok http --url=quelque-chose.ngrok-free.app 7860
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
```

Activer les deux, et les laisser tourner même sans session ouverte :

```bash
systemctl --user daemon-reload
systemctl --user enable --now agribaat ngrok
sudo loginctl enable-linger $USER
```

Suivre le démarrage (le premier lancement télécharge les modèles de voix, ≈ 6 Go,
quelques minutes) ; Ctrl+C pour quitter l'affichage, l'appli continue :

```bash
journalctl --user -u agribaat -f
```

## 5. Empêcher la mise en veille

```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

Garder le PC **branché** et l'écran **ouvert** (rabattre l'écran peut couper le réseau
sur certains portables).

## 6. Vérifier depuis un téléphone (en 4G, pas sur le Wi-Fi du PC)

Ouvrir `https://quelque-chose.ngrok-free.app` :

- ngrok affiche d'abord une page d'avertissement : cliquer **Visit Site** (normal avec
  l'offre gratuite) ;
- poser une question écrite, puis une question vocale (le micro marche car l'adresse est en HTTPS) ;
- « Bulletins & alertes » doit demander le mot de passe équipe ;
- « À propos » doit afficher « État : actif ».

## En cas de problème

| Symptôme | Commande |
|---|---|
| L'appli ne répond pas | `systemctl --user status agribaat` puis `journalctl --user -u agribaat -n 50` |
| L'adresse ngrok ne répond pas | `systemctl --user status ngrok` |
| Après une mise à jour du code | `git pull` puis `systemctl --user restart agribaat` |
| Arrêter après l'évaluation | `systemctl --user disable --now agribaat ngrok` puis `sudo systemctl unmask sleep.target suspend.target hibernate.target hybrid-sleep.target` |

Si une erreur persiste, coller le message à Claude avec `PROMPT_BASCULEMENT.md`.
