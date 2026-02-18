# MangaVega Tracker V7 — Guide de mise en place pas à pas

> **Objectif :** Créer un repo GitHub V7 et un Gist propres, sans toucher à la V6 existante.
> La V6 (monolithe + ancien Gist) reste intacte sur son repo/Gist actuel.

---

## Prérequis

Vérifiez que tout est installé avant de commencer :

**Python 3.10+ :**
```bash
python --version
```
→ Doit afficher `Python 3.10.x` ou supérieur. Si ce n'est pas le cas, téléchargez Python depuis https://www.python.org/downloads/

**Git :**
```bash
git --version
```
→ Doit afficher `git version 2.x.x`. Si ce n'est pas le cas, téléchargez Git depuis https://git-scm.com/downloads

**Git configuré :**
```bash
git config --global user.name
git config --global user.email
```
→ Doit afficher votre nom et email. Si c'est vide :
```bash
git config --global user.name "Votre Nom"
git config --global user.email "votre@email.com"
```

---

## Étape 1 : Créer le Gist V7

Le Gist sert de canal de communication entre le script local et le viewer web.
On crée un **nouveau** Gist pour ne pas perturber la V6.

1. Ouvrez votre navigateur et allez sur **https://gist.github.com**
2. Connectez-vous à GitHub si ce n'est pas déjà fait
3. Dans le champ **"Gist description"** en haut, tapez : `MangaVega Tracker V7`
4. Dans le champ **"Filename including extension"**, tapez : `corrections.json`
5. Dans la grande zone de texte, collez exactement ceci :

```json
{
  "date_seuil": "2025-06-01",
  "valides": [],
  "rejetes": [],
  "tomes": {},
  "editeurs_officiels": {},
  "commentaires": {}
}
```

6. Cliquez sur le bouton **"Add file"** (en bas à gauche de la zone de texte)
7. Un deuxième fichier apparaît. Dans le champ nom, tapez : `series_config.json`
8. Dans sa zone de texte, collez exactement ceci :

```json
{
  "urls_supplementaires": {},
  "series_ajoutees": [],
  "series_supprimees": [],
  "traductions": {}
}
```

9. En bas à droite, cliquez sur la flèche à côté de **"Create secret gist"** et choisissez **"Create secret gist"**
10. Le Gist est créé. **Copiez l'ID** depuis la barre d'adresse du navigateur :
    ```
    https://gist.github.com/votre_user/a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4
                                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                        ← C'est ça l'ID (32 caractères)
    ```
11. **Notez cet ID** quelque part, on en aura besoin à l'étape 4

> **Vérification :** Votre Gist doit avoir 2 fichiers : `corrections.json` et `series_config.json`

---

## Étape 2 : Créer un token GitHub

Le token permet au script de lire et écrire sur le Gist.
Si vous avez déjà un token avec le scope `gist`, vous pouvez le réutiliser et passer à l'étape 3.

1. Allez sur **https://github.com/settings/tokens**
2. Cliquez sur **"Tokens (classic)"** dans le menu de gauche
3. Cliquez sur **"Generate new token"** → **"Generate new token (classic)"**
4. GitHub vous demande votre mot de passe → confirmez
5. Remplissez :
   - **Note :** `MangaVega V7`
   - **Expiration :** choisissez `No expiration` (ou 1 an si vous préférez)
   - **Scopes :** cochez ces trois cases :
     - `gist` — permet au script de lire et écrire sur le Gist (synchronisation avec le viewer)
     - `repo` — permet de pousser les fichiers vers le repo GitHub (BDD, mangas_liste.json)
     - `workflow` — permet de déclencher des GitHub Actions (utile si vous ajoutez des automatisations plus tard)
   - Un seul token pour tous les usages est plus simple à gérer (un seul endroit à mettre à jour s'il expire)
6. Cliquez **"Generate token"** tout en bas
7. **IMPORTANT :** Le token s'affiche une seule fois ! Il ressemble à `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
8. **Copiez-le immédiatement** et sauvegardez-le quelque part de sûr

> **Vérification :** Vous avez un token qui commence par `ghp_` et fait ~40 caractères

---

## Étape 3 : Préparer le dossier du projet

Choisissez où vous voulez installer le projet sur votre ordinateur.

**Windows — Ouvrez PowerShell :**
```powershell
cd C:\Users\VotreNom\Documents
mkdir mangavega-v7
cd mangavega-v7
git init
```

**Linux/Mac — Ouvrez un terminal :**
```bash
cd ~/Documents
mkdir mangavega-v7
cd mangavega-v7
git init
```

→ Vous devez voir : `Initialized empty Git repository in .../mangavega-v7/.git/`

Maintenant, copiez **tous les fichiers** du dossier `mangavega/` que je vous ai fourni dans ce dossier `mangavega-v7/`. Vous pouvez le faire par glisser-déposer dans l'explorateur de fichiers, ou en ligne de commande.

**Vérifiez que tout est là :**
```bash
ls
```
→ Vous devez voir au minimum ces fichiers :
```
app.py              notifications.py    requirements.txt
config.py           pipeline.py         mangavega_scan.bat
database.py         scraper.py          .gitignore
mangas_liste.json   sync.py             README.md
utils.py
```

> Si `.gitignore` n'apparaît pas avec `ls`, c'est normal (fichier caché). Essayez `ls -a` pour le voir.

---

## Étape 4 : Configurer le GIST_ID dans le code

C'est **la seule modification** à faire dans le code source.

1. Ouvrez `config.py` avec un éditeur de texte (Bloc-notes, VS Code, Notepad++...)
2. Cherchez cette ligne (vers la ligne 50) :
   ```python
   GIST_ID = "8deb1120eaa6acc53c1f627fcd0839bc"
   ```
3. Remplacez l'ID entre guillemets par **l'ID de votre nouveau Gist** (noté à l'étape 1) :
   ```python
   GIST_ID = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
   ```
4. Sauvegardez le fichier

> **Vérification :** La ligne contient votre nouvel ID, entre guillemets, sans espaces

---

## Étape 5 : Installer les dépendances Python

Depuis le dossier `mangavega-v7/`, lancez :

```bash
pip install -r requirements.txt
```

**Ce qui s'installe :**
- `aiohttp` — requêtes HTTP asynchrones
- `beautifulsoup4` + `lxml` — extraction de données depuis le HTML Amazon
- `curl-cffi` — imite le navigateur Chrome pour éviter les blocages Amazon

**Si `curl-cffi` échoue à l'installation :**
```
ERROR: Failed building wheel for curl-cffi
```
→ Ce n'est pas bloquant. Le script fonctionnera avec `aiohttp` en fallback. Vous verrez un warning au lancement, c'est normal. Mais les risques de blocage par Amazon seront un peu plus élevés.

**Vérifiez que ça a marché :**
```bash
python -c "import aiohttp, bs4, lxml; print('OK')"
```
→ Doit afficher `OK` sans erreur

---

## Étape 6 : Configurer le token GitHub

Le script a besoin du token (étape 2) pour communiquer avec le Gist.
On utilise un fichier `.env` pour ne jamais mettre le token en dur dans le code.

### 6a. Créer le fichier `.env`

Dans le dossier `mangavega-v7/`, créez une copie du modèle :

**Windows (Anaconda Prompt ou Invite de commandes) :**
```
copy .env.example .env
```

**Linux/Mac :**
```bash
cp .env.example .env
```

### 6b. Mettre votre token dans le fichier `.env`

1. Ouvrez le fichier `.env` avec un éditeur de texte (Bloc-notes, VS Code, Notepad++...)
2. Vous voyez :
   ```
   GIST_TOKEN=
   ```
3. Ajoutez votre token **juste après le `=`**, sans espaces, sans guillemets :
   ```
   GIST_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
4. Sauvegardez

> **IMPORTANT :** Ce fichier `.env` ne sera **jamais** poussé vers GitHub (il est dans le `.gitignore`). C'est la bonne pratique recommandée par OWASP et la communauté GitHub. Ne partagez jamais votre token en clair (ni par chat, ni par email, ni dans un document).

---

## Étape 7 : Décider quoi faire de l'ancienne base de données

Le fichier `manga_alerts.db` contient le cache de tous les volumes déjà scannés, les traductions, les statuts validé/rejeté, etc.

### Option A — Repartir de zéro (recommandé)

Ne rien copier. Le script créera une BDD vierge au premier lancement.

- **Avantage :** départ 100% propre
- **Inconvénient :** le premier scan est un peu plus long (~25 min) car aucun cache. Les statuts validé/rejeté que vous aviez mis via le viewer seront perdus (il faudra revalider au fur et à mesure)

### Option B — Récupérer le cache existant

Copiez le fichier `manga_alerts.db` depuis votre dossier V6 dans `mangavega-v7/`.

- **Avantage :** le cache est conservé, scan plus rapide, validations/rejets préservés
- **Inconvénient :** les données anciennes peuvent contenir des résidus de bugs V6

---

## Étape 8 : Premier lancement (test)

C'est le moment de vérité. Assurez-vous d'être dans le bon dossier :

```bash
cd C:\Users\VotreNom\Documents\mangavega-v7   # Windows
cd ~/Documents/mangavega-v7                     # Linux/Mac
```

**Si vous utilisez le batch (Windows) :**
Double-cliquez sur `mangavega_scan.bat`

**Sinon, en ligne de commande :**
```bash
python app.py
```

### Ce que vous devez voir dans la console

Voici les messages importants dans l'ordre. Vérifiez-les un par un :

**1. Token détecté :**
```
🔑 GIST_TOKEN détecté (40 caractères)
```
→ Si vous voyez `⚠️ GIST_TOKEN non défini` → retournez à l'étape 6

**2. Séries chargées :**
```
📋 55 série(s) chargée(s) depuis mangas_liste.json
```
→ Si vous voyez `❌ mangas_liste.json non trouvé` → le fichier n'est pas dans le bon dossier

**3. Migration des traductions (premier lancement uniquement) :**
```
📦 Migration V7: injection des traductions manuelles en BDD...
   ✅ 54 traductions migrées en BDD
```
→ Au 2e lancement vous verrez `✅ Traductions manuelles déjà en BDD (54 entrées)` — c'est normal

**4. Gist lu :**
```
☁️  Chargement de la configuration depuis le Gist...
   ✅ corrections.json: 0 validé(s), 0 rejeté(s)
   ✅ series_config.json: 0 URL(s) supp., 0 série(s) ajoutée(s)
```
→ Si vous voyez `⚠️ Impossible de charger le Gist` → vérifiez le GIST_ID (étape 4) et le token (étape 6)

**5. Début du scan :**
```
🚀 MANGA TRACKER v7.0.0 (2026-02-17)
📚 55 mangas à surveiller
🌐 Session HTTP: curl_cffi (impersonate=chrome, TLS+HTTP/2 fingerprint)
🔥 Warm-up: visite amazon.co.jp pour recevoir les cookies...
```

Le scan dure ensuite **15 à 25 minutes** (pauses anti-blocage incluses). C'est normal.

**6. Résumé final :**
```
📊 RÉSUMÉ FINAL
⏱️  Temps: XXXs
📚 Scannés: 55
📦 Papiers trouvés: XXX
✨ Nouveautés: X
```

**7. Fichier généré :**
```
📋 JSON collection: manga_collection.json
```
→ Vérifiez que le fichier `manga_collection.json` a bien été créé dans le dossier.

---

## Étape 9 : Créer le repo sur GitHub et pousser le code

### 9a. Créer le repo sur GitHub

1. Allez sur **https://github.com/new**
2. Remplissez :
   - **Repository name :** `mangavega-v7`
   - **Description :** `Surveillance manga Amazon Japon`
   - **Visibility :** Private (recommandé, le code contient votre email)
   - **NE cochez PAS** "Add a README" ni "Add .gitignore" (on les a déjà)
3. Cliquez **"Create repository"**
4. GitHub affiche des commandes. Ignorez-les, suivez plutôt l'étape 9b ci-dessous.

### 9b. Pousser le code depuis votre machine

Revenez dans votre terminal, toujours dans le dossier `mangavega-v7/` :

```bash
# Ajouter tous les fichiers au suivi Git
git add .

# Premier commit
git commit -m "MangaVega Tracker V7 - Initial commit"

# Connecter au repo GitHub (remplacez VOTRE_USER par votre nom GitHub)
git remote add origin https://github.com/VOTRE_USER/mangavega-v7.git

# Pousser vers GitHub
git branch -M main
git push -u origin main
```

Si Git vous demande vos identifiants :
- **Username :** votre nom d'utilisateur GitHub
- **Password :** votre **token** (pas votre mot de passe GitHub !)

### 9c. Après le premier scan réussi, commiter aussi la BDD

```bash
git add manga_alerts.db
git commit -m "BDD après premier scan"
git push
```

> **Vérification :** Allez sur `https://github.com/VOTRE_USER/mangavega-v7` dans votre navigateur — vous devez voir tous vos fichiers.

---

## Étape 10 : Configurer le viewer HTML

Si vous utilisez le viewer HTML (`manga_collection_viewer.html`) :

1. Ouvrez le fichier HTML du viewer avec un éditeur de texte
2. Cherchez (Ctrl+F) l'ancien GIST_ID : `8deb1120eaa6acc53c1f627fcd0839bc`
3. Remplacez-le par **l'ID de votre nouveau Gist V7** (le même qu'à l'étape 4)
4. Sauvegardez

Le viewer a besoin de deux choses pour fonctionner :
- **Le Gist** (pour les corrections/validations en temps réel) → configuré ci-dessus
- **Le fichier `manga_collection.json`** (résultats du scan) → généré à chaque scan dans le dossier local

---

## Étape 11 : Lancement automatique

Trois options selon votre usage.

---

### Option A — Lancement manuel (double-clic)

La méthode la plus simple : double-cliquez sur `mangavega_scan.bat` quand vous voulez lancer un scan.

Le batch ouvre une fenêtre noire, lance le scan (~20 min), puis affiche `Appuyez sur une touche pour continuer...` à la fin.

Rien à configurer de plus — le token est déjà dans le batch (étape 6).

---

### Option B — Planificateur de tâches Windows (scan quotidien automatique)

Pour que le scan se lance tout seul chaque jour, même si vous n'y pensez pas.

**Étape par étape :**

1. Appuyez sur la touche **Windows** de votre clavier
2. Tapez `Planificateur de tâches` et ouvrez l'application qui apparaît
3. Dans le panneau de droite (ou dans le menu Action), cliquez sur **"Créer une tâche de base..."**

4. **Page "Créer une tâche de base" :**
   - Nom : `MangaVega Scan V7`
   - Description : `Scan quotidien des nouveautés manga Amazon JP`
   - Cliquez **Suivant**

5. **Page "Déclencheur" :**
   - Sélectionnez **"Tous les jours"**
   - Cliquez **Suivant**

6. **Page "Tous les jours" :**
   - Début : choisissez **la date d'aujourd'hui**
   - Heure : choisissez une heure où votre PC est **allumé et connecté à Internet** (par exemple `08:00:00` ou `20:00:00`)
   - Périodicité : laissez **1 jour**
   - Cliquez **Suivant**

7. **Page "Action" :**
   - Sélectionnez **"Démarrer un programme"**
   - Cliquez **Suivant**

8. **Page "Démarrer un programme" :**
   - Cliquez le bouton **"Parcourir..."**
   - Naviguez jusqu'à votre dossier `mangavega-v7`
   - Sélectionnez le fichier **`mangavega_scan.bat`**
   - Le champ "Programme/script" doit maintenant afficher quelque chose comme :
     ```
     C:\Users\VotreNom\Documents\mangavega-v7\mangavega_scan.bat
     ```
   - Dans le champ **"Commencer dans (facultatif)"**, tapez le chemin du dossier (sans le nom du fichier) :
     ```
     C:\Users\VotreNom\Documents\mangavega-v7
     ```
   - Cliquez **Suivant**

9. **Page "Résumé" :**
   - Relisez les informations
   - Cochez la case **"Ouvrir les propriétés de cette tâche après avoir cliqué sur Terminer"**
   - Cliquez **Terminer**

10. **Fenêtre de propriétés** (s'ouvre automatiquement si vous avez coché la case) :
    - Onglet **"Général"** : vérifiez que "Exécuter avec les autorisations les plus élevées" n'est **PAS** coché (inutile ici)
    - Onglet **"Conditions"** :
      - Décochez **"Ne démarrer la tâche que si l'ordinateur est sur secteur"** (sinon ça ne marchera pas sur batterie)
      - Cochez **"Réactiver l'ordinateur pour exécuter cette tâche"** si vous voulez que le scan se lance même en veille
    - Onglet **"Paramètres"** :
      - Cochez **"Autoriser l'exécution de la tâche à la demande"** (permet de la lancer manuellement depuis le Planificateur)
      - Cochez **"Si la tâche échoue, redémarrer toutes les : 30 minutes"** avec **"Tentatives max : 2"** (comme ça si le réseau était coupé, ça réessaie)
    - Cliquez **OK**

**Pour vérifier que tout fonctionne :**
1. Dans le Planificateur de tâches, trouvez votre tâche **"MangaVega Scan V7"** dans la liste
2. Clic droit dessus → **"Exécuter"**
3. Une fenêtre noire de commande doit s'ouvrir et le scan doit démarrer
4. Attendez quelques secondes et vérifiez que vous voyez les messages habituels (`🚀 MANGA TRACKER v7.0.0`, etc.)

> **Si la fenêtre s'ouvre et se ferme immédiatement :** le chemin dans "Commencer dans" est probablement incorrect. Vérifiez qu'il pointe vers le dossier contenant `app.py`.

---

### Option C — Linux/Mac avec Crontab

**1. Ouvrir l'éditeur crontab :**
```bash
crontab -e
```
→ Si c'est la première fois, le système vous demande quel éditeur utiliser. Choisissez `nano` (le plus simple).

**2. Ajouter la ligne suivante** (tout en bas du fichier) :
```bash
0 8 * * * cd /home/votre_user/Documents/mangavega-v7 && GIST_TOKEN="ghp_votre_token" python3 app.py >> manga_tracker.log 2>&1
```

Décryptage de cette ligne :
- `0 8 * * *` = tous les jours à 8h00
- `cd .../mangavega-v7` = se placer dans le bon dossier
- `GIST_TOKEN="..."` = passer le token au script
- `python3 app.py` = lancer le scan
- `>> manga_tracker.log 2>&1` = écrire la sortie dans un fichier log (ajout, pas écrasement)

**3. Sauvegarder et quitter :**
- Si vous êtes dans `nano` : appuyez sur `Ctrl+O` (sauver), `Entrée` (confirmer), `Ctrl+X` (quitter)
- Si vous êtes dans `vim` : tapez `:wq` puis `Entrée`

**4. Vérifier que la tâche est enregistrée :**
```bash
crontab -l
```
→ Doit afficher votre ligne `0 8 * * *...`

**5. Vérifier que le cron fonctionne** (le lendemain) :
```bash
cat /home/votre_user/Documents/mangavega-v7/manga_tracker.log
```
→ Doit contenir le log du scan avec `🚀 MANGA TRACKER v7.0.0`

> **Si le log est vide ou n'existe pas :** vérifiez que le chemin dans la ligne crontab est correct, et que `python3` est bien dans le PATH du cron. Vous pouvez tester avec le chemin complet : `/usr/bin/python3 app.py`

---

## Flux de données (résumé visuel)

```
┌─────────────────────────────────────────────────────┐
│                    VIEWER HTML                       │
│  (manga_collection_viewer.html)                     │
│                                                     │
│  Lit: manga_collection.json (résultats du scan)     │
│  Écrit: Gist (corrections + series_config)          │
└─────────────┬──────────────────────┬────────────────┘
              │                      │
              ▼ lit                   ▼ écrit
┌─────────────────────────────────────────────────────┐
│                   GIST GITHUB                        │
│  corrections.json : valides, rejetés, éditeurs      │
│  series_config.json : ajouts, suppressions, URLs    │
└─────────────┬──────────────────────┬────────────────┘
              │                      │
              ▼ lit                   ▼ écrit
┌─────────────────────────────────────────────────────┐
│                SCRIPT (app.py)                       │
│  1. Charge mangas_liste.json                         │
│  2. Lit le Gist (corrections + series config)        │
│  3. Scanne Amazon pour chaque série                  │
│  4. Génère manga_collection.json                     │
│  5. Met à jour le Gist (nettoyage URLs traitées)     │
│  6. Sauvegarde manga_alerts.db                       │
└─────────────────────────────────────────────────────┘
```

---

## Ce qui a changé par rapport à la V6

| Aspect | V6 (monolithe) | V7 (modulaire) |
|--------|----------------|----------------|
| Fichier source | 1 fichier (4837 lignes) | 8 modules (~5000 lignes total) |
| Point d'entrée | `python mangavega_monitor.py` | `python app.py` |
| mangas_liste.json | Données transitoires incluses | Clés structurelles uniquement |
| TRADUCTIONS_MANUELLES | Hardcodées, jamais en BDD | Migrées en BDD au 1er lancement |
| Bug `verifications` | Table introuvable (typo) | Corrigé → `verifications_cache` |
| Séries Kamuya/Peleliu | Traduction sans série | Retirées (traductions orphelines) |
| git_push() | Absent | Ajouté dans sync.py |
| BDD | Compatible | Même schéma, même fichier |
| Viewer | Compatible | Aucun changement de format |
| Gist | Compatible | Même format (nouveau Gist propre) |

---

## Dépannage

### Au lancement

| Message | Cause | Solution |
|---------|-------|----------|
| `⚠️ GIST_TOKEN non défini` | Token pas configuré | Étape 6 : vérifiez que le fichier `.env` existe et contient votre token |
| `❌ mangas_liste.json non trouvé` | Fichier manquant | Vérifiez que `mangas_liste.json` est dans le dossier `mangavega-v7/` |
| `⚠️ Impossible de charger le Gist` | GIST_ID incorrect ou token invalide | Vérifiez l'ID dans `config.py` (étape 4) et le token (étape 6) |
| `ModuleNotFoundError: No module named 'aiohttp'` | Dépendances manquantes | `pip install -r requirements.txt` (étape 5) |
| `ModuleNotFoundError: No module named 'config'` | Mauvais dossier courant | Vérifiez que vous êtes dans `mangavega-v7/` avec `cd` avant de lancer |

### Pendant le scan

| Message | Cause | Solution |
|---------|-------|----------|
| `⚠️ Rate limit (503)` répété | Amazon bloque temporairement | Normal. Le script attend et réessaie automatiquement. Si ça persiste, relancez plus tard |
| `⚠️ Captcha/bot détecté` | Amazon soupçonne un robot | Normal en petites quantités. Le circuit breaker fait une pause de 30s puis reprend |
| `❌ Timeout définitif` | Connexion instable | Vérifiez votre connexion. Le volume en erreur sera re-tenté au prochain scan |
| `curl_cffi non disponible` | Paquet non installé | Le script fonctionne en fallback aiohttp, mais plus de blocages possibles. Essayez `pip install curl-cffi` |

### Après le scan

| Problème | Solution |
|----------|----------|
| `manga_collection.json` n'existe pas | Le scan a planté avant la fin. Consultez `manga_tracker.log` |
| Le viewer ne montre rien | Vérifiez le GIST_ID dans le viewer = même ID qu'à l'étape 4 |
| Les validations/rejets V6 sont perdus | Normal si BDD vierge (option A étape 7). Revalidez progressivement |

### Planificateur de tâches Windows

| Problème | Solution |
|----------|----------|
| La fenêtre s'ouvre et se ferme immédiatement | Le champ "Commencer dans" est probablement vide ou incorrect. Mettez le chemin complet du dossier |
| La tâche "s'exécute" mais rien ne se passe | Vérifiez dans l'historique de la tâche (onglet "Historique" dans le Planificateur). Code retour 0 = OK, autre = erreur |
| "Accès refusé" dans l'historique | Décochez "Exécuter avec les autorisations les plus élevées" dans les propriétés |
