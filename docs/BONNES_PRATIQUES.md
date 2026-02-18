# Bonnes Pratiques — MangaVega Tracker

Ce document rassemble les règles de sécurité et de développement à respecter sur ce projet.
Il est basé sur le [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html) et les recommandations de la communauté GitHub.

**Règle d'or : ce fichier est vivant.** On l'enrichit à chaque leçon apprise.

---

## 1. Gestion des secrets (tokens, mots de passe, clés API)

### 1.1 Ne jamais partager un secret en clair

- **Jamais** dans un chat, un email, un document, une capture d'écran
- **Jamais** dans un commit Git (même supprimé après, il reste dans l'historique)
- **Jamais** en dur dans le code source (fichiers `.py`, `.bat`, `.html`, etc.)
- Si un secret est exposé par accident → **le révoquer immédiatement** et en créer un nouveau

> **Source :** OWASP — *"Secrets should not be hardcoded. The secrets should not be unencrypted. The secrets should not be stored in source code."*

### 1.2 Utiliser un fichier `.env` pour les secrets locaux

Les secrets sont stockés dans un fichier `.env` à la racine du projet :

```
# .env — NE JAMAIS COMMITER CE FICHIER
GIST_TOKEN=ghp_votre_vrai_token_ici
EMAIL_DESTINATAIRE=votre@email.com
EMAIL_EXPEDITEUR=votre@gmail.com
MOT_DE_PASSE_APP=votre_mot_de_passe_app
```

Ce fichier :
- Est **ignoré par Git** (listé dans `.gitignore`)
- N'est **jamais** poussé vers GitHub
- Est **lu automatiquement** par `config.py` au démarrage (avant toute utilisation des variables)
- Est aussi lu par `mangavega_scan.bat` (qui n'a donc aucun secret en dur)

Un fichier `.env.example` est commité avec des valeurs vides pour servir de modèle :

```
# .env.example — Modèle (sans secrets)
GIST_TOKEN=
EMAIL_DESTINATAIRE=
EMAIL_EXPEDITEUR=
MOT_DE_PASSE_APP=
```

> **Source :** GitHub Community — *"Always add `.env` to your `.gitignore` file before your first commit. Create a `.env.example` that contains the names of the variables but not the values."*

### 1.3 Ne jamais mettre de secret dans un fichier batch ou script

Les fichiers `.bat`, `.sh`, `.ps1` sont commités dans Git. Si un secret y est écrit, il se retrouve dans l'historique.
Le batch `mangavega_scan.bat` charge les variables depuis `.env` — il ne contient aucun secret.

### 1.4 Ne jamais mettre de secret en exemple dans la documentation

Les fichiers `README.md`, guides, et tutoriels ne doivent **jamais** contenir de vrais tokens ni d'exemples ressemblant à un vrai token (comme `ghp_abc123...`). Utiliser des formulations neutres comme "remplissez votre token dans le fichier `.env`" et renvoyer vers le `.env.example`.

### 1.5 Vérifier le `.gitignore` avant chaque premier commit

Avant tout `git add .` sur un nouveau projet, vérifiez que `.gitignore` contient :

```
.env
.env.*
```

Une fois un secret commité, même si vous le supprimez dans un commit suivant, il reste dans l'historique Git. La seule solution est de révoquer le secret et d'en créer un nouveau.

### 1.6 Rotation des tokens

- Choisir une durée d'expiration raisonnable (1 an max recommandé)
- Marquer dans son calendrier la date de renouvellement
- Si un token n'est plus utilisé → le supprimer immédiatement sur GitHub

---

## 2. Organisation du code

### 2.1 Séparation configuration / code

- Les constantes et la configuration sont dans `config.py`
- Les secrets sont dans `.env` (jamais dans `config.py`)
- Le code métier ne contient aucune valeur en dur (URLs, seuils, listes de mots-clés → tout dans `config.py`)

### 2.2 Pas de données transitoires dans les fichiers de référence

Le fichier `mangas_liste.json` ne contient que les clés structurelles (nom, url_suffix, type, filtre).
Les données transitoires (urls_supplementaires, asin_reference) vivent uniquement en mémoire pendant l'exécution.

### 2.3 Nommage et structure

- Un module = une responsabilité (config, utils, database, scraper, sync, notifications, pipeline, app)
- Les fonctions sont importées explicitement (`from utils import extraire_asin`, pas `from utils import *`)
- Les globals mutables sont accédés via `config.VARIABLE`, jamais redéfinis par accident

---

## 3. Git et GitHub

### 3.1 Ce qu'on commite

- ✅ Le code source (`.py`)
- ✅ Les fichiers de configuration non-secrets (`mangas_liste.json`, `requirements.txt`, `.gitignore`)
- ✅ La base de données (`manga_alerts.db`) — contient le cache, pas de secrets
- ✅ La documentation (`README.md`, `GUIDE_INSTALLATION.md`, `BONNES_PRATIQUES.md`)

### 3.2 Ce qu'on ne commite JAMAIS

- ❌ `.env` (contient le token)
- ❌ `manga_tracker.log` (peut contenir des URLs sensibles)
- ❌ `manga_collection.json` (fichier généré, volumineux)
- ❌ `debug_page_*.html` (pages Amazon sauvegardées pour debug)
- ❌ Tout fichier contenant un token, mot de passe ou clé API

### 3.3 Messages de commit

Écrire des messages clairs et utiles :
- ✅ `Ajout série Dandadan [MANGA]`
- ✅ `Fix extraction tome pour titres avec tirets`
- ✅ `BDD après scan du 2026-02-18`
- ❌ `update`
- ❌ `fix`
- ❌ `wip`

---

## 4. Sécurité du compte GitHub

### 4.1 Activer l'authentification à deux facteurs (2FA)

Allez sur https://github.com/settings/security et activez le 2FA.
C'est la protection la plus efficace contre le vol de compte.

### 4.2 Scope minimal pour les tokens

Ne cocher que les permissions nécessaires lors de la création d'un token :
- `gist` — lecture/écriture Gist
- `repo` — push vers le repo
- `workflow` — GitHub Actions (si utilisé)

Ne jamais cocher `admin:org`, `delete_repo`, ou `user` sauf besoin explicite.

### 4.3 Repo privé par défaut

Le repo `mangavega-v7` doit être **privé** car :
- `config.py` contient le GIST_ID (permet de retrouver le Gist)
- Les emails dans les paramètres SMTP sont visibles
- L'historique Git pourrait contenir des informations personnelles

---

## 5. Checklist avant chaque action

### Avant un commit / push

- [ ] Le fichier `.env` n'est PAS dans les fichiers stagés (`git status`)
- [ ] Aucun token ou mot de passe dans le diff (`git diff --staged`)
- [ ] Le message de commit est descriptif

### Avant de partager du code ou une capture d'écran

- [ ] Aucun token visible
- [ ] Aucun mot de passe visible
- [ ] Aucun email personnel visible (sauf si volontaire)

### Avant de créer un nouveau token

- [ ] L'ancien token est-il encore nécessaire ? Si non, le supprimer
- [ ] Le scope est minimal (seules les permissions nécessaires sont cochées)
- [ ] La date d'expiration est définie

---

## Historique des leçons apprises

| Date | Leçon |
|------|-------|
| 2026-02-18 | Ne jamais partager un token en clair dans un chat, même privé |
| 2026-02-18 | Utiliser un fichier `.env` + `.env.example` plutôt qu'un token en dur dans un `.bat` |
| 2026-02-18 | Toujours vérifier le `.gitignore` avant le premier commit d'un nouveau projet |
| 2026-02-18 | Les emails et mots de passe d'application sont des secrets au même titre que les tokens |
| 2026-02-18 | Le `.env` doit être chargé AVANT les lignes qui lisent `os.environ.get()` dans le code |
| 2026-02-18 | Ne jamais mettre de vrais tokens ni de faux tokens réalistes dans le README ou les docs |
| 2026-02-18 | Un fichier batch commité ne doit contenir aucun secret — il charge le `.env` à la place |
| 2026-02-18 | Vérifier le mot de passe d'app Gmail : s'il a été commité en V6, le révoquer et en créer un nouveau |
