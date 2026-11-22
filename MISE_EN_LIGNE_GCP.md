# Mettre AgriBaat en ligne sur Google Cloud (GCP)

Tout se fait **dans le navigateur**, depuis n'importe quel PC : la console Google Cloud
et un terminal ouvert dans la page. AgriBaat tourne sur un serveur Google (16 Go de RAM),
pas sur votre PC : une fois lancé, vous pouvez éteindre votre ordinateur.

Coût : **0 €** grâce aux 300 $ de crédit d'essai (90 jours). Google ne prélève rien tant
que le compte n'est pas passé manuellement en « payant ».

Durée : environ 1 h 30, dont une bonne partie à attendre des téléchargements.

Ne jamais écrire une clé, un jeton ou un mot de passe dans un fichier du dépôt ni dans
une capture d'écran partagée.

---

## 0. Avant de commencer : rendre le dépôt GitHub public

Le formulaire demande des liens publics, et le serveur doit pouvoir télécharger le code.
Sur GitHub : dépôt **agribaat** → **Settings** → tout en bas, *Danger Zone* →
**Change visibility** → **Public**. (Vérifié : aucune clé ni donnée personnelle dans le dépôt.)

## 1. Créer le compte Google Cloud (10 min)

1. Aller sur https://console.cloud.google.com et se connecter avec un compte Google.
2. Accepter l'essai gratuit (**Free trial / Essai gratuit, 300 $**) : pays Sénégal, carte
   bancaire pour vérifier l'identité (rien n'est prélevé).
3. En haut de la page, sélecteur de projet → **Nouveau projet** → nom : `agribaat` → Créer,
   puis le sélectionner.

**Alerte de budget (2 min, à faire tout de suite)** : menu ☰ → **Facturation** →
**Budgets et alertes** → **Créer un budget** → montant `300` $ → alertes à 50 %, 80 % et 100 %
→ Terminer. Vous recevrez un e-mail avant d'arriver au bout du crédit.

## 2. Créer le serveur (10 min)

Menu ☰ → **Compute Engine** → **Instances de VM** (la première fois, cliquer **Activer**
l'API et attendre une minute) → **Créer une instance** :

| Champ | Valeur |
|---|---|
| Nom | `agribaat` |
| Région | `europe-west9 (Paris)` (proche de Dakar), zone au choix |
| Configuration de la machine | Série **E2**, type **e2-standard-4** (4 vCPU, 16 Go) |
| Disque de démarrage → Modifier | **Ubuntu**, version **Ubuntu 24.04 LTS** (x86/64), disque **équilibré**, **50 Go** |
| Pare-feu | Cocher **Autoriser le trafic HTTP** et **Autoriser le trafic HTTPS** |

Cliquer **Créer**. Au bout d'une minute, la VM apparaît avec une **adresse IP externe**.

**Rendre l'adresse IP fixe** (sinon elle change si le serveur redémarre) : menu ☰ →
**Réseau VPC** → **Adresses IP** → sur la ligne de la VM, menu ⋮ → **Promouvoir en adresse
IP statique** → nom `agribaat-ip` → Réserver.

## 3. Ouvrir le terminal du serveur

Dans **Instances de VM**, sur la ligne `agribaat`, cliquer **SSH**. Une fenêtre noire
s'ouvre : c'est le terminal du serveur. Les commandes ci-dessous s'y collent
(clic droit → Coller, ou Ctrl+V), **une par une**.

## 4. Installer AgriBaat (30 à 40 min, surtout du téléchargement)

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip ffmpeg git unzip
```
```bash
git clone https://github.com/NdeyePendaSarr/agribaat.git
```
```bash
cd ~/agribaat && python3 -m venv .venv && source .venv/bin/activate
```
```bash
pip install --upgrade pip
```
```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
```
```bash
pip install -r agribaat_app/requirements.txt
```

**Facultatif mais conseillé : envoyer le dossier `outputs`** (voix déjà calculées, réponses
de l'IA en cache : l'appli est rapide dès le premier jour).
1. Sur votre PC Windows : clic droit sur `agribaat_app\outputs` → **Compresser dans un
   fichier ZIP** → `outputs.zip`.
2. Dans la fenêtre SSH : bouton **⬆ Importer un fichier** (en haut à droite) → choisir `outputs.zip`.
3. Puis :
```bash
unzip -o ~/outputs.zip -d ~/agribaat/agribaat_app/ && rm ~/outputs.zip
```

## 5. Les secrets (clé IA et mot de passe équipe)

```bash
mkdir -p ~/.config && nano ~/.config/agribaat.env
```

Écrire ces trois lignes avec les vraies valeurs, puis **Ctrl+O**, **Entrée**, **Ctrl+X** :

```
ANTHROPIC_API_KEY=sk-ant-...
AGRIBAAT_TEAM_PASSWORD=mot-de-passe-choisi-par-l-equipe
PYTHONIOENCODING=utf-8
```

```bash
chmod 600 ~/.config/agribaat.env
```

## 6. Lancer AgriBaat en service (redémarre tout seul)

Copier ce bloc **en entier** (il crée le service avec votre nom d'utilisateur) :

```bash
sudo tee /etc/systemd/system/agribaat.service >/dev/null <<EOF
[Unit]
Description=AgriBaat
After=network-online.target

[Service]
User=$USER
WorkingDirectory=$HOME/agribaat/agribaat_app
EnvironmentFile=$HOME/.config/agribaat.env
ExecStart=$HOME/agribaat/.venv/bin/python app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
```
```bash
sudo systemctl daemon-reload && sudo systemctl enable --now agribaat
```

Suivre le démarrage (le premier lancement télécharge les modèles de voix, ≈ 6 Go,
quelques minutes ; attendre la ligne `Running on local URL: http://127.0.0.1:7860`),
puis **Ctrl+C** pour quitter l'affichage (l'appli continue) :

```bash
journalctl -u agribaat -f
```

## 7. L'adresse publique HTTPS (Caddy)

Le HTTPS est obligatoire pour que le micro marche sur téléphone. Caddy obtient le
certificat tout seul ; l'adresse utilise le service gratuit sslip.io à partir de l'IP.

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
```
```bash
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
```
```bash
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
```
```bash
sudo apt update && sudo apt install -y caddy
```

Construire l'adresse et configurer Caddy (copier le bloc en entier) :

```bash
IP=$(curl -s https://ifconfig.me); DOMAINE="${IP//./-}.sslip.io"
sudo tee /etc/caddy/Caddyfile >/dev/null <<EOF
$DOMAINE {
    reverse_proxy 127.0.0.1:7860
}
EOF
sudo systemctl reload caddy
echo "Adresse de l'appli : https://$DOMAINE"
```

La dernière ligne affiche l'adresse, du type `https://34-155-12-34.sslip.io`.
**C'est le lien à mettre dans le formulaire.** (Le certificat met parfois une minute à
arriver : si la page affiche une erreur de sécurité, attendre et recharger.)

## 8. Vérifier depuis un téléphone (en 4G)

- l'appli s'ouvre, sans page d'avertissement ;
- une question écrite, puis une question vocale ;
- « Bulletins & alertes » demande le mot de passe équipe ;
- « À propos » affiche « État : actif » pour l'IA.

Vous pouvez maintenant fermer la fenêtre SSH et éteindre votre PC : le serveur continue.

## En cas de problème

| Symptôme | Commande (dans la fenêtre SSH) |
|---|---|
| L'appli ne répond pas | `sudo systemctl status agribaat` puis `journalctl -u agribaat -n 50` |
| Erreur de certificat / HTTPS | `sudo systemctl status caddy` puis `journalctl -u caddy -n 50` |
| Mettre à jour le code | `cd ~/agribaat && git pull && sudo systemctl restart agribaat` |
| Changer la clé ou le mot de passe | `nano ~/.config/agribaat.env` puis `sudo systemctl restart agribaat` |
| Après le challenge | Console → Instances de VM → **Arrêter** (ou **Supprimer**) la VM, et libérer l'IP statique |

Si une erreur persiste, coller le message (sans aucune clé visible) à Claude avec
`PROMPT_BASCULEMENT.md`.
