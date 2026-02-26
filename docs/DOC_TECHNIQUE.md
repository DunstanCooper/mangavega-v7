# MangaVega Tracker V7 — Documentation Technique

> **Audience** : Développeurs, ingénieurs logiciel, mainteneurs
> **Dernière révision** : 26 février 2026
> **Version** : 7.1.0
> **Auteur** : Dunstan Cooper
> **Repo** : https://github.com/DunstanCooper/mangavega-v7

---

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Architecture système (C4 — Niveau 1 Context)](#2-architecture-système)
3. [Containers (C4 — Niveau 2)](#3-containers)
4. [Modules applicatifs (C4 — Niveau 3 Components)](#4-modules-applicatifs)
5. [Modèle de données](#5-modèle-de-données)
6. [Flux de données](#6-flux-de-données)
7. [Pipeline de scraping](#7-pipeline-de-scraping)
8. [Sécurité](#8-sécurité)
9. [API locale](#9-api-locale)
10. [Conventions de code](#10-conventions-de-code)
11. [Architecture Decision Records (ADR)](#11-architecture-decision-records)
12. [Dépendances](#12-dépendances)
13. [Environnement de développement](#13-environnement-de-développement)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Vue d'ensemble

### Qu'est-ce que MangaVega Tracker ?

Un tracker automatisé qui surveille les sorties de mangas et light novels (LN) sur Amazon Japon, détecte les nouveaux volumes, et notifie l'utilisateur par email. L'interface web (viewer) permet de valider/rejeter les détections et de piloter le script à distance.

### Problème résolu

Amazon Japon n'a pas de système d'alerte pour les nouvelles sorties par série. Le suivi manuel de 55+ séries est impraticable. Ce tracker automatise la veille, le filtrage (dérivés, ebooks, hors-sujet) et la notification.

### Stack technique

| Composant | Technologie |
|-----------|-------------|
| Langage principal | Python 3.11+ (Anaconda) |
| Scraping | `curl_cffi` (impersonate Chrome TLS), `BeautifulSoup` + `lxml` |
| Base de données | SQLite3 (fichier local `manga_alerts.db`) |
| API locale | Flask 3.0 |
| Frontend viewer | HTML/CSS/JS vanilla (fichier unique, 3 719 lignes) |
| Hébergement viewer | GitHub Pages (statique) |
| Stockage corrections | GitHub Gist (API REST) |
| Notifications | SMTP (Gmail App Password) |
| Versioning | Git + GitHub |
| Planification | Planificateur de tâches Windows |

### Chiffres clés

| Métrique | Valeur |
|----------|--------|
| Séries suivies | 55 (config), 54 (en BDD) |
| Volumes en BDD | ~353 |
| ASINs classifiés (Featured) | ~1 094 |
| Statuts manuels | ~327 (318 validés, 9 rejetés) |
| Lignes de code Python | 6 196 |
| Lignes viewer HTML | 3 719 |
| Modules Python | 9 |
| Tables SQLite | 10 actives |
| Temps de scan complet | ~45 minutes |
| Requêtes HTTP/scan | ~300 |

---

## 2. Architecture système

### Diagramme C4 — Niveau 1 (Context)

```
┌─────────────────────────────────────────────────────────────┐
│                     UTILISATEUR                             │
│                  (navigateur web)                            │
└──────────┬──────────────────┬───────────────────────────────┘
           │                  │
           │ HTTPS            │ HTTPS
           │ (lecture)        │ (corrections)
           ▼                  ▼
┌──────────────────┐  ┌──────────────────┐
│  GitHub Pages    │  │  GitHub Gist     │
│  (viewer HTML)   │  │  (corrections +  │
│                  │  │   series_config) │
└──────────────────┘  └────────┬─────────┘
                               │
                               │ HTTPS (API GitHub)
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                  PC LOCAL (Windows)                           │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │ Flask API    │  │ Script Python│  │ SQLite BDD         │ │
│  │ (port 5000)  │←→│ (app.py)     │←→│ (manga_alerts.db)  │ │
│  └──────┬───────┘  └──────┬───────┘  └────────────────────┘ │
│         │                 │                                  │
│         │ localhost        │ HTTPS (curl_cffi)               │
│         ▼                 ▼                                  │
│  ┌──────────────┐  ┌──────────────┐                         │
│  │ Viewer local │  │ Amazon.co.jp │                         │
│  │ (navigateur) │  │ (scraping)   │                         │
│  └──────────────┘  └──────────────┘                         │
│         │                 │                                  │
│         │                 │ SMTP (port 465)                  │
│         │                 ▼                                  │
│         │          ┌──────────────┐                          │
│         │          │ Gmail SMTP   │                          │
│         │          │ (rapport)    │                          │
│         │          └──────────────┘                          │
│         │                                                    │
│         │ git push (HTTPS)                                   │
│         ▼                                                    │
│  ┌──────────────────┐                                        │
│  │ GitHub Repo      │                                        │
│  │ (mangavega-v7)   │                                        │
│  └──────────────────┘                                        │
└──────────────────────────────────────────────────────────────┘
```

### Flux de communication

| Source → Destination | Protocole | Données | Fréquence |
|---------------------|-----------|---------|-----------|
| Script → Amazon.co.jp | HTTPS (TLS Chrome) | Pages HTML produits | ~300 req/scan |
| Script → GitHub Gist | HTTPS (API REST) | Lecture/écriture corrections.json | 2x/scan |
| Script → GitHub Repo | HTTPS (git push) | manga_collection.json | 1x/scan |
| Script → Gmail | SMTP/SSL (465) | Rapport HTML + alertes | 1x/scan |
| Viewer → GitHub Raw | HTTPS | manga_collection.json | 1x/chargement |
| Viewer → GitHub Gist | HTTPS (API REST) | corrections.json | 1x/synchro |
| Viewer → Flask API | HTTP (localhost:5000) | Commandes (scan, sync, backup) | À la demande |

---

## 3. Containers

### 3.1 Script Python (app.py + modules)

**Responsabilité** : Orchestration du scan, scraping Amazon, classification des produits, génération du JSON, envoi email, synchronisation Gist.

**Exécution** : Console Anaconda ou planificateur Windows. Processus unique, mono-thread (sauf API Flask qui lance le scan en subprocess).

**Entrées** : `mangas_liste.json` (séries à suivre), `.env` (secrets), Gist (corrections), BDD SQLite (cache).

**Sorties** : `manga_collection.json` (collection), BDD mise à jour, Gist mis à jour, email, git push.

### 3.2 API Flask (api_server.py)

**Responsabilité** : Interface HTTP entre le viewer et le script local. Expose 6 endpoints REST.

**Exécution** : Processus long, lancé via `mangavega_server.bat` ou planificateur Windows.

**Contrainte** : Doit tourner sur le même PC que le script. Le viewer accède à `localhost:5000`.

### 3.3 Viewer HTML (manga_collection_viewer.html)

**Responsabilité** : Interface de consultation, validation/rejet des volumes, pilotage du script.

**Exécution** : Statique, servi par GitHub Pages ou Flask. Aucun backend requis pour la lecture.

**Données** : Charge le JSON depuis `raw.githubusercontent.com`, les corrections depuis le Gist, l'état du serveur depuis `localhost:5000`.

### 3.4 Base de données SQLite (manga_alerts.db)

**Responsabilité** : Persistance locale. Cache de scraping, statuts manuels, progression Featured, historique alertes.

**Emplacement** : Racine du projet. Fichier unique, portable.

---

## 4. Modules applicatifs

### Vue d'ensemble des modules

```
app.py (575 lignes)           ← Orchestrateur, CLI, main()
  ├── config.py (235 l.)      ← Constantes, .env, globals mutables
  ├── database.py (1 283 l.)  ← DatabaseManager, 10 tables, 50+ méthodes
  ├── pipeline.py (1 425 l.)  ← Phase A→B→C, Featured, Bulk, vérifications
  ├── scraper.py (761 l.)     ← SessionWrapper, HTTP, extraction HTML
  ├── sync.py (672 l.)        ← Gist (R/W), Git push, corrections
  ├── utils.py (647 l.)       ← Fonctions pures, parsers (tomes, dates)
  ├── notifications.py (525 l.) ← Emails SMTP + brouillons workflow éditorial
  └── api_server.py (273 l.)  ← Flask, 6 endpoints REST
```

### 4.1 `config.py` — Configuration

| Élément | Description |
|---------|-------------|
| `GIST_ID` | ID du Gist GitHub pour les corrections |
| `GIST_TOKEN` | Token GitHub (depuis `.env`) |
| `EMAIL_*` | Configuration SMTP |
| `EMAIL_DESTINATAIRE_WORKFLOW` | Adresse email pro pour les brouillons workflow (depuis `.env`) |
| `IMAP_MOT_DE_PASSE` | Mot de passe IMAP M365 (vide = fallback .eml) |
| `IMAP_SERVER` | `'outlook.office365.com'` |
| `IMAP_PORT` | `993` |
| `MANGAS_A_SUIVRE` | Liste des séries (chargée depuis `mangas_liste.json`) |
| `TRADUCTIONS_MANUELLES` | Fallback hardcodé : 52 traductions JP → FR |
| `MOTS_CLES_DERIVES` | Mots-clés pour filtrer artbooks, anthologies, etc. |
| `EDITEURS_CONNUS` | Liste blanche d'éditeurs manga/LN japonais |
| `DATE_SEUIL` | Mutable. Date en deçà de laquelle un volume n'est pas "nouveauté" |
| `GIST_CORRECTIONS` | Mutable. Corrections chargées depuis le Gist |
| `TRADUCTIONS_FR` | Mutable. Dictionnaire JP→FR (BDD + fallback) |

**Pattern globals mutables** : Plusieurs variables dans config.py sont modifiées au runtime par d'autres modules (`sync.py`, `app.py`). C'est un choix pragmatique pour éviter de passer des contextes partout, mais c'est un couplage implicite documenté ici.

### 4.2 `database.py` — DatabaseManager

Classe singleton encapsulant toutes les opérations SQLite. Connexion thread-local.

**⚠️ database.py a été reconstruit le 26/02/2026 depuis le bytecode `.pyc` (Python 3.13) suite à une corruption ENOSPC (disk full). La syntaxe a été vérifiée via `ast.parse()`.**

**Tables** (détail en §5) :

| Table | Rôle | Lignes typiques |
|-------|------|-----------------|
| `volumes` | Volumes papier détectés | ~353 |
| `featured_history` | Tous les ASINs croisés + classification | ~1 094 |
| `featured_progression` | Progression par série (pages Featured explorées) | ~55 |
| `verifications_cache` | Cache des pages produit (24h) | ~341 |
| `traductions` | Traductions JP → FR | ~55 |
| `series_editeurs` | Éditeur principal par série | ~54 |
| `alertes` | Historique des alertes envoyées | ~16 |
| `statuts_manuels` | Validations/rejets manuels (depuis Gist) | ~327 |
| `volume_serie_override` | Réaffectation de volume à une autre série | 0 |
| `suivi_editorial` | Workflow éditorial par volume (étapes de suivi) | variable |

**Nouvelles méthodes (v7.1.0) :**

| Méthode | Description |
|---------|-------------|
| `creer_workflow_volume(asin, serie_jp, tome, today, editeur)` | INSERT OR IGNORE étape `mail_nwk` |
| `marquer_etape_faite(asin, etape, date_completion)` | Complète une étape et crée l'étape suivante |
| `get_actions_en_retard(delai_jours=10)` | Retourne la liste des étapes en retard (JOIN traductions + series_editeurs) |
| `get_workflows_a_notifier()` | Volumes à notifier (`email_ouverture_envoye=0`) |
| `get_tous_workflows_actifs()` | Dictionnaire `{asin: {etape_courante, jours_ecoules, date_sortie_jp, editeur, ...}}` |
| `incrementer_relances(asin, etape)` | Incrémente le compteur de relances pour une étape |

**Constante workflow :**

```python
ETAPES_WORKFLOW = ['mail_nwk', 'draft_ad', 'reponse_nwk', 'contrat_ad', 'signature_nwk', 'facture']
```

**Méthodes existantes** (50+ au total) :

| Méthode | Rôle |
|---------|------|
| `ajouter_volume()` | Insert ou met à jour un volume papier |
| `get_volumes()` | Retourne les volumes avec filtres |
| `upsert_featured()` | Insert ou ignore dans featured_history |
| `get_statut_manuel()` | Récupère validation/rejet pour un ASIN |
| *...et 45+ autres* | |

### 4.3 `pipeline.py` — Pipeline de scraping

Module le plus complexe (1 425 lignes). Implémente la recherche en 3 phases :

- **Phase A** : Recherche via Amazon Search (`?k=série+nom`)
- **Phase B** : Bulk — volumes liés depuis une page produit connue
- **Phase C** : Featured — résultats sponsorisés/recommandés (pagination max 5 pages)

**Fix pagination infinie (26/02/2026)** : Vérification du bouton `s-pagination-next` (absent ou classe `s-pagination-disabled` = dernière vraie page). Fallback : `page_num > 1 and len(items) < 8`. Évite la boucle infinie due à l'accumulation de 3 nouvelles pages par run même sans résultats réels.

Détail complet en §7.

### 4.4 `scraper.py` — HTTP & Extraction

| Classe/Fonction | Rôle |
|----------------|------|
| `SessionWrapper` | Session `curl_cffi` avec impersonate Chrome, cookies japonais, retry 3x |
| `extraire_info_produit()` | Parse une page produit Amazon → titre, date, éditeur, couverture |
| `extraire_volumes_recherche()` | Parse une page de recherche Amazon → liste d'ASINs |
| `warm_up()` | Première requête sur amazon.co.jp pour établir les cookies |

**Anti-détection** : `curl_cffi` avec `impersonate="chrome"` reproduit le TLS fingerprint de Chrome. Cookie `i18n-prefs=JPY` + header `Accept-Language: ja-JP` pour forcer les pages en japonais.

### 4.5 `sync.py` — Synchronisation

| Fonction | Rôle |
|----------|------|
| `charger_gist_config()` | Lit corrections.json et series_config.json depuis le Gist |
| `charger_corrections(db)` | Importe Gist → `statuts_manuels` en BDD + completions workflow |
| `charger_series_config(db)` | Fusionne séries ajoutées/supprimées depuis le viewer |
| `sauvegarder_gist_config()` | Écrit corrections.json + date_seuil dans le Gist |
| `git_push()` | `git add` + `git commit` + `git push` du JSON |
| `rechercher_traduction_web(serie_jp)` | Scrape la traduction FR via recherche web |

**Import des completions workflow depuis le Gist** dans `charger_corrections(db)` :

```python
gist_suivi = config.GIST_CORRECTIONS.get('suivi_editorial', {})
for asin, completions in gist_suivi.items():
    for etape, date_completion in completions.items():
        if date_completion:
            db.marquer_etape_faite(asin, etape, date_completion)
```

### 4.6 `utils.py` — Fonctions pures

| Fonction | Rôle |
|----------|------|
| `extraire_numero_tome(titre)` | 14 patterns regex pour extraire le numéro de tome |
| `parser_date_japonaise(text)` | Parse `2025年3月10日` et variantes |
| `normaliser_editeur(editeur_raw)` | Uniformise les noms d'éditeurs (romaji, aliases) |
| `est_derive(titre)` | Détecte artbooks, anthologies, novelisations |
| `strip_type_suffix(nom)` | Retire `[MANGA]` ou `[LN]` du nom de série |
| `EDITEURS_ROMAJI` | 64 mappings katakana → romaji pour les éditeurs |

### 4.7 `notifications.py` — Emails

**Architecture notifications.py (525 lignes) :**

*Emails SMTP (rapport et alertes) :*
- `envoyer_email_rapport()` : rapport HTML envoyé à `EMAIL_DESTINATAIRE` à chaque scan
- `envoyer_email()` : alertes avec couvertures si nouveautés

*Système de brouillons workflow éditorial :*
- `envoyer_email_workflow(destinataire, volumes_nouveaux, actions_retard)` : EMAIL COMBINÉ
  - Corps plain-text professionnel, "Bonjour Nicolas,", groupé par éditeur romaji
  - Nouvelles sorties : `- Titre (LN) Tx, sortie le DD/MM — il vient de sortir`
  - Relances : `- Titre (Manga) Tx, sortie le DD/MM — je t'avais fait un mail le DATE`
  - Sujet : "Offres à demander" / "Relance offres" / "Offres éditoriales"
  - Essaie IMAP APPEND vers M365 (dossier Brouillons/Drafts) → fallback .eml
  - From = EMAIL_DESTINATAIRE_WORKFLOW (adresse pro)

*Helpers internes :*
- `_editeur_romaji(editeur_jp)` : JP → romaji via `utils.EDITEURS_ROMAJI`
- `_type_serie(serie_jp)` : `' (LN)'` ou `' (Manga)'` depuis le suffixe
- `_grouper_par_editeur(items)` : groupe par éditeur, ordre alphabétique
- `_format_date_fr(date_iso)` : YYYY-MM-DD → DD/MM/YYYY
- `_envoyer_smtp(msg, label)` : fallback multi-ports (465/587/25/2525)
- `_deposer_brouillon_workflow(msg) → bool` : IMAP APPEND vers M365
- `_sauvegarder_eml(msg, nom_fichier)` : sauvegarde dans `brouillons/` (fallback)

### 4.8 `api_server.py` — Serveur Flask

| Endpoint | Méthode | Rôle |
|----------|---------|------|
| `/` | GET | Sert le viewer HTML |
| `/api/status` | GET | État serveur + stats BDD |
| `/api/sync` | POST | Applique corrections Gist → BDD |
| `/api/scan` | POST | Lance scan en subprocess (body: `{serie, no_email, no_push}`) |
| `/api/backup` | POST | Copie horodatée de la BDD |
| `/api/log` | GET | Dernières N lignes du log |

Le scan est lancé en `subprocess.run()` dans un thread daemon. Variables d'environnement du `.env` injectées manuellement. `PYTHONIOENCODING=utf-8` forcé pour Windows.

---

## 5. Modèle de données

### Schéma relationnel

```
┌─────────────────────┐     ┌──────────────────────┐
│ volumes             │     │ featured_history      │
├─────────────────────┤     ├──────────────────────┤
│ id (PK, auto)       │     │ asin (PK)            │
│ serie_jp            │     │ serie                │
│ serie_fr            │     │ titre                │
│ tome (INTEGER)      │     │ statut               │
│ asin (UNIQUE)       │     │   (ebook, papier,    │
│ url                 │     │    sponsorise,        │
│ date_sortie_jp      │     │    hors_sujet_titre,  │
│ titre_volume        │     │    lot, derive,       │
│ date_ajout          │     │    non_papier)        │
│ date_maj            │     │ source               │
│ editeur             │     │ asin_papier          │
└──────────┬──────────┘     │ date_vu              │
           │                └──────────────────────┘
           │ serie_jp
           ▼
┌─────────────────────┐     ┌──────────────────────┐
│ series_editeurs     │     │ featured_progression  │
├─────────────────────┤     ├──────────────────────┤
│ serie_id (PK)       │     │ serie (PK)           │
│ editeur_officiel    │     │ derniere_page        │
│ date_detection      │     │ exploration_complete  │
│ nb_volumes_detectes │     │ date_maj             │
│ derniere_recherche  │     └──────────────────────┘
└─────────────────────┘

┌─────────────────────┐     ┌──────────────────────┐
│ traductions         │     │ statuts_manuels       │
├─────────────────────┤     ├──────────────────────┤
│ titre_japonais (PK) │     │ asin (PK)            │
│ titre_francais      │     │ statut               │
│ date_ajout          │     │   (valide, rejete)   │
│ source              │     │ commentaire          │
│ est_officielle      │     │ date_modification    │
│ derniere_verificat° │     └──────────────────────┘
└─────────────────────┘

┌─────────────────────┐     ┌──────────────────────┐
│ verifications_cache │     │ alertes               │
├─────────────────────┤     ├──────────────────────┤
│ asin (PK)           │     │ nom                  │
│ date_verification   │     │ url                  │
│ date_sortie         │     │ date                 │
│ tome                │     └──────────────────────┘
│ titre               │
│ editeur             │     ┌──────────────────────┐
└─────────────────────┘     │ volume_serie_override │
                            ├──────────────────────┤
                            │ asin (PK)            │
                            │ serie_alternative    │
                            │ date_modification    │
                            └──────────────────────┘

┌──────────────────────────────────────────────┐
│ suivi_editorial                              │
├──────────────────────────────────────────────┤
│ asin TEXT (PK avec etape)                    │
│ serie_jp TEXT                                │
│ tome INTEGER                                 │
│ etape TEXT (PK avec asin)                    │
│   'mail_nwk'|'draft_ad'|'reponse_nwk'|      │
│   'contrat_ad'|'signature_nwk'|'facture'     │
│ statut TEXT  'en_attente'|'fait'             │
│ date_declenchement TEXT                      │
│ date_completion TEXT  (NULL si en attente)   │
│ nb_relances INTEGER                          │
│ pause_jusqu_au TEXT                          │
│ email_ouverture_envoye INTEGER               │
│ date_sortie_jp TEXT                          │
│ editeur TEXT                                 │
└──────────────────────────────────────────────┘
```

**⚠️ Noms de colonnes incohérents** : la colonne série s'appelle `serie_jp` dans `volumes`, `serie` dans `featured_history` et `featured_progression`, `serie_id` dans `series_editeurs`, et `titre_japonais` dans `traductions`. Même donnée, noms différents.

### Tables actives (10)

| Table | Rôle |
|-------|------|
| `volumes` | Volumes papier détectés |
| `featured_history` | Tous les ASINs croisés + classification |
| `featured_progression` | Progression par série (pages Featured explorées) |
| `verifications_cache` | Cache des pages produit (24h) |
| `traductions` | Traductions JP → FR |
| `series_editeurs` | Éditeur principal par série |
| `alertes` | Historique des alertes envoyées |
| `statuts_manuels` | Validations/rejets manuels (depuis Gist) |
| `volume_serie_override` | Réaffectation de volume à une autre série |
| `suivi_editorial` | Workflow éditorial par volume |

### Classification des ASINs (`featured_history.statut`)

| Statut | Description | Action |
|--------|-------------|--------|
| `papier` | Volume physique confirmé | Ajouté à `volumes` |
| `ebook` | Version numérique | Ignoré (on ne suit que le papier) |
| `sponsorise` | Résultat sponsorisé Amazon | Ignoré |
| `hors_sujet_titre` | Titre ne correspond pas à la série | Ignoré |
| `lot` | Pack/coffret de plusieurs volumes | Ignoré |
| `derive` | Artbook, anthologie, novelisation | Ignoré |
| `non_papier` | Format non-papier (calendrier, etc.) | Ignoré |

---

## 6. Flux de données

### 6.1 Cycle de vie d'un scan

```
1. INITIALISATION
   app.py main()
     ├── Charge mangas_liste.json → config.MANGAS_A_SUIVRE
     ├── Initialise DatabaseManager
     ├── Charge .env → variables d'environnement
     ├── charger_gist_config() → config.GIST_CORRECTIONS
     ├── charger_corrections(db) → statuts_manuels en BDD
     └── charger_series_config(db) → fusion séries

2. SCAN (pour chaque série)
   pipeline.rechercher_manga(serie, db, session)
     ├── Phase A : Recherche Amazon → candidats bruts
     ├── Phase B : Bulk (volumes liés) → candidats supplémentaires
     ├── Phase C : Featured (pages 1→5) → classification ASINs
     ├── Filtrage : éditeur, titre, format, dérivés
     ├── Vérification page produit : date, tome, format papier
     └── Résultat : liste de volumes papier confirmés

3. POST-TRAITEMENT
   app.py
     ├── Fusionne tous les résultats
     ├── Applique statuts manuels (valide/rejeté)
     ├── Génère manga_collection.json
     ├── Sauvegarde Gist (date_seuil mise à jour)
     ├── Envoie email rapport + alertes
     └── Git push (JSON → GitHub)
```

### 6.2 Flux corrections (viewer ↔ script)

```
UTILISATEUR (viewer)
    │
    │ 1. Valide/rejette des volumes
    │
    ▼
GitHub Gist (corrections.json)
    │  { "valides": [...], "rejetes": [...], "tomes": {...} }
    │
    │ 2. Au prochain scan, le script lit le Gist
    │
    ▼
sync.charger_gist_config()
    │
    │ 3. Importe dans la BDD
    │
    ▼
sync.charger_corrections(db)  → INSERT INTO statuts_manuels
    │
    │ 4. Le JSON exporté inclut les statuts
    │
    ▼
manga_collection.json (avec statut par volume)
    │
    │ 5. Git push → le viewer affiche les bons statuts
    │
    ▼
Viewer actualise les compteurs (Validés / Rejetés / À traiter)
```

---

## 7. Pipeline de scraping

### Phase A — Recherche Amazon

```
Entrée: nom de série (ex: "葬送のフリーレン [MANGA]")
  │
  ├── Recherche: amazon.co.jp/s?k=葬送のフリーレン+コミック
  ├── Parse les résultats (ASINs, titres)
  ├── Filtre par titre (doit contenir le nom de série)
  ├── Filtre par éditeur (doit être un éditeur manga connu)
  └── Résultat: liste de candidats ASIN
```

### Phase B — Bulk (volumes liés)

```
Entrée: ASIN de référence (volume connu de la série)
  │
  ├── Charge la page produit de cet ASIN
  ├── Parse la section "volumes liés" d'Amazon
  ├── Extrait les ASINs associés
  ├── Classifie chaque ASIN dans featured_history
  └── Résultat: candidats supplémentaires
```

### Phase C — Featured (recommandations Amazon)

```
Entrée: recherche Featured pour la série
  │
  ├── Reprend là où on s'est arrêté (featured_progression)
  ├── Pages 1 → 5 max, 3 nouvelles pages max par run
  ├── Pour chaque résultat:
  │     ├── Déjà vu (featured_history) → skip
  │     ├── Titre hors-sujet → classifie "hors_sujet_titre"
  │     ├── URL sponsorisée (sspa) → classifie "sponsorise"
  │     └── Pertinent → classifie et ajoute aux candidats
  └── Résultat: candidats + featured_history enrichi
```

### Vérification finale

```
Pour chaque candidat papier:
  │
  ├── Cache verifications_cache valide (< 24h) → skip
  ├── Charge la page produit Amazon
  ├── Vérifie: format papier (not Kindle), éditeur correct
  ├── Extrait: date de sortie, tome, couverture
  ├── Sauvegarde dans verifications_cache
  └── Si papier confirmé → ajoute à volumes
```

### Patterns d'extraction de tome (`utils.extraire_numero_tome`)

14 patterns regex ordonnés par priorité :

| # | Pattern | Exemple | Résultat |
|---|---------|---------|----------|
| 1 | `第N巻` | 第3巻 | 3 |
| 2 | `(N)` parenthèses | (5) | 5 |
| 3 | `Vol. N` | Vol. 12 | 12 |
| 4 | `N巻` | 3巻 | 3 |
| 5 | `Volume N` | Volume 7 | 7 |
| 6 | ` N ` (entre espaces) | série 3 suite | 3 |
| 7 | `N 巻` (espace avant 巻) | 3 巻 | 3 |
| 8 | Romain `I`, `II`, `III`... | Tome III | 3 |
| 9 | `第N集` | 第2集 | 2 |
| 10 | Fin de titre ` N` | タイトル 5 | 5 |
| 11 | Entre kanji `X N Y` | す 1 懲 | 1 |
| 12 | `#N` | #15 | 15 |
| 13 | `N巻` depuis Bulk | 1巻セット | 1 |
| 14 | `Vol.N` (sans espace) | Vol.3 | 3 |

---

## 8. Sécurité

### Secrets

| Secret | Stockage | Utilisation |
|--------|----------|-------------|
| `GIST_TOKEN` | `.env` | Lecture/écriture Gist (scope `gist`) |
| `EMAIL_MDP` | `.env` | Gmail App Password |
| `IMAP_MOT_DE_PASSE` | `.env` | IMAP M365 pour brouillons workflow |
| Token viewer | `localStorage` chiffré AES (PBKDF2) | Écriture Gist depuis le viewer |

**Règles** :
- `.env` dans `.gitignore` — jamais commité
- `.env.example` commité comme modèle (sans valeurs)
- Aucun secret en dur dans le code
- Token viewer chiffré côté client avec mot de passe utilisateur

### Réseau

- Tout le trafic sortant est HTTPS (Amazon, GitHub, Gmail)
- L'API Flask écoute uniquement sur `127.0.0.1` (pas d'accès externe)
- CORS activé pour permettre GitHub Pages → localhost

### Anti-détection Amazon

- `curl_cffi` avec TLS fingerprint Chrome
- Cookies japonais (`i18n-prefs=JPY`)
- Pauses entre séries (8s toutes les 15 séries)
- Retry avec backoff exponentiel (3 tentatives)
- Warm-up initial sur amazon.co.jp

---

## 9. API locale

### Configuration

- **URL** : `http://localhost:5000`
- **CORS** : Activé (cross-origin depuis GitHub Pages)
- **Authentification** : Aucune (localhost uniquement)

### Endpoints

#### `GET /api/status`

```json
{
  "server": "online",
  "scan_running": false,
  "total_volumes": 353,
  "total_series": 55,
  "total_featured": 1094,
  "last_scan": "2026-02-22",
  "last_result": "success",
  "last_finished": "2026-02-22 10:56:00"
}
```

#### `POST /api/sync`

Applique les corrections du Gist à la BDD sans relancer le scan.

```json
// Réponse
{ "success": true, "message": "Corrections appliquées depuis le Gist" }
```

#### `POST /api/scan`

```json
// Requête
{ "serie": "葬送のフリーレン", "no_email": true, "no_push": false }

// Réponse
{ "success": true, "message": "Scan lancé (série: 葬送のフリーレン)" }
```

#### `POST /api/backup`

```json
// Réponse
{ "success": true, "message": "Backup créé : manga_alerts_2026-02-22_10h56.db", "size_mb": 0.51 }
```

#### `GET /api/log?lines=80`

```json
{ "log": "...", "total_lines": 450, "showing": 80 }
```

---

## 10. Conventions de code

### Nommage

| Élément | Convention | Exemple |
|---------|-----------|---------|
| Modules | `snake_case.py` | `pipeline.py` |
| Classes | `PascalCase` | `DatabaseManager`, `SessionWrapper` |
| Fonctions | `snake_case` | `extraire_numero_tome()` |
| Constantes | `UPPER_SNAKE` | `EDITEURS_CONNUS` |
| Variables globales mutables | `UPPER_SNAKE` | `GIST_CORRECTIONS` |
| Tables BDD | `snake_case` | `featured_history` |

### Logging

Toutes les sorties passent par `config.logger` (module `logging`). Format avec emojis pour lisibilité dans les logs :

| Emoji | Signification |
|-------|---------------|
| 📚 | Série en cours de scan |
| ✅ | Succès |
| ❌ | Erreur / rejet |
| ⚠️ | Warning |
| 💾 | Sauvegarde / cache |
| 🔄 | Exploration en cours |
| 📦 | Résultat phase |
| ☁️ | Opération Gist |
| 📧 | Email |

### Gestion d'erreurs

- Les erreurs HTTP sont retryées 3 fois avec backoff exponentiel
- Les erreurs fatales par série sont catchées — le scan continue avec les autres séries
- Les séries en 503 sont retryées une dernière fois en fin de scan
- Les erreurs de parsing sont loguées mais ne bloquent pas

---

## 11. Architecture Decision Records

### ADR-001 : curl_cffi au lieu de requests

- **Date** : Février 2026
- **Contexte** : Amazon bloque les requêtes avec un fingerprint TLS non-navigateur. `requests` et `aiohttp` sont détectés et reçoivent des pages vides ou des captchas.
- **Décision** : Utiliser `curl_cffi` avec `impersonate="chrome"` pour reproduire le TLS fingerprint de Chrome.
- **Conséquences** : Dépendance native (compilation C), mais 100% de succès sur Amazon.co.jp. Installation plus complexe que `requests`.

### ADR-002 : SQLite plutôt que PostgreSQL/MongoDB

- **Date** : Février 2026
- **Contexte** : Le projet est mono-utilisateur, tourne sur un PC local. Pas besoin de serveur de base de données.
- **Décision** : SQLite3 (fichier unique, zero config, intégré à Python).
- **Conséquences** : Pas de concurrence d'écriture (un seul processus écrit à la fois). Backup = copier un fichier. Migration = script Python.

### ADR-003 : GitHub Gist comme bus de communication viewer ↔ script

- **Date** : Février 2026
- **Contexte** : Le viewer (HTML statique sur GitHub Pages) ne peut pas communiquer directement avec le script local. Il faut un intermédiaire cloud.
- **Décision** : GitHub Gist pour stocker les corrections (validations/rejets) et la configuration des séries. Lecture publique, écriture authentifiée via token.
- **Conséquences** : Gratuit, simple, API REST standard. Limité à ~100 requêtes/heure. Pas de temps réel (polling).

### ADR-004 : Monolithe refactorisé en modules plutôt que microservices

- **Date** : Février 2026
- **Contexte** : Le script V6 faisait 4 837 lignes dans un seul fichier. Illisible et inmaintenable.
- **Décision** : Découper en 8 modules Python avec responsabilités claires, dans le même processus.
- **Conséquences** : Code organisé et lisible. Pas de complexité réseau inter-services. Couplage via `config.py` (globals mutables).

### ADR-005 : Flask API locale pour le pilotage

- **Date** : Février 2026
- **Contexte** : Le viewer sur GitHub Pages ne peut pas exécuter de commandes sur le PC local (restriction navigateur). GitHub Actions n'est plus utilisé (migration vers exécution locale).
- **Décision** : Petit serveur Flask sur localhost:5000 exposant 6 endpoints. Le viewer appelle ces endpoints via `fetch()`.
- **Conséquences** : Nécessite que Flask tourne sur le PC. Mixed content HTTPS→HTTP fonctionne car les navigateurs exemptent localhost. Pas d'authentification (localhost uniquement).

### ADR-006 : HTML monofichier pour le viewer

- **Date** : Février 2026
- **Contexte** : Le viewer doit être hébergé gratuitement et simplement.
- **Décision** : Un seul fichier HTML (CSS + JS inline, 3 719 lignes) servi par GitHub Pages.
- **Conséquences** : Zéro dépendance, zéro build. Fichier volumineux mais fonctionnel. Pas de framework (vanilla JS).

### ADR-007 : Brouillons IMAP plutôt qu'envoi direct

- **Date** : Février 2026
- **Contexte** : Les emails de prospection éditoriale (vers NWK) doivent être validés par un humain avant envoi. Un envoi automatique sans relecture serait risqué.
- **Décision** : Déposer les emails en brouillons via IMAP APPEND vers M365 (dossier Brouillons/Drafts), l'utilisateur les relit et les envoie manuellement.
- **Conséquences** : Permet la validation humaine avant envoi vers NWK. Nécessite un compte IMAP M365 configuré.

### ADR-008 : Fallback .eml si IMAP indisponible

- **Date** : Février 2026
- **Contexte** : Si le serveur IMAP est indisponible (réseau, mot de passe incorrect, M365 down), les brouillons ne doivent pas être perdus silencieusement.
- **Décision** : En cas d'échec IMAP, sauvegarder le message au format `.eml` dans le dossier `brouillons/` local, ouvrable depuis Outlook ou tout client mail.
- **Conséquences** : Pas de perte d'information. L'utilisateur peut ouvrir le .eml depuis Outlook ou un client web.

---

## 12. Dépendances

### Python

| Package | Version min | Rôle | Note |
|---------|-------------|------|------|
| `curl_cffi` | ≥ 0.7 | HTTP avec TLS Chrome | Compile une lib native |
| `beautifulsoup4` | ≥ 4.12 | Parsing HTML | Avec `lxml` |
| `lxml` | ≥ 5.0 | Parser HTML rapide | |
| `aiohttp` | ≥ 3.9 | Requêtes async (traductions) | |
| `flask` | ≥ 3.0 | API locale | |
| `flask-cors` | ≥ 4.0 | CORS pour Flask | |

### Système

| Outil | Rôle |
|-------|------|
| Python 3.11+ | Anaconda recommandé |
| Git | Push automatique du JSON |
| Planificateur de tâches Windows | Exécution automatique |

### Services externes

| Service | Utilisation | Coût |
|---------|-------------|------|
| GitHub (repo public) | Hébergement code + JSON + viewer | Gratuit |
| GitHub Gist | Stockage corrections | Gratuit |
| GitHub Pages | Hébergement viewer | Gratuit |
| Gmail SMTP | Envoi emails | Gratuit (App Password) |
| Microsoft 365 IMAP | Brouillons workflow éditorial | Abonnement existant |
| Amazon.co.jp | Source de données (scraping) | Gratuit (ToS à surveiller) |

---

## 13. Environnement de développement

### Prérequis

| Logiciel | Version | Installation |
|----------|---------|--------------|
| Anaconda | Dernière | https://www.anaconda.com/download |
| Git | Dernière | https://git-scm.com/download/win |
| VS Code (optionnel) | Dernière | https://code.visualstudio.com |

### Setup initial

```bash
# 1. Cloner le repo
git clone https://github.com/DunstanCooper/mangavega-v7.git
cd mangavega-v7

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Configurer les secrets
copy .env.example .env
# Éditer .env avec vos valeurs

# 4. Premier scan (test)
python app.py --serie "葬送のフリーレン" --no-email --no-push

# 5. Lancer l'API
python api_server.py
```

### Structure du projet

```
mangavega-v7/
├── .env                    # Secrets (JAMAIS commité)
├── .env.example            # Modèle sans secrets
├── .gitignore
├── README.md
├── TODO.md
├── BONNES_PRATIQUES.md
├── GUIDE_INSTALLATION.md
├── DOC_TECHNIQUE.md        # Ce document
├── DOC_UTILISATEUR.md      # Guide utilisateur
├── requirements.txt
├── mangas_liste.json       # Liste des 55 séries à suivre
├── manga_alerts.db         # Base de données SQLite
├── manga_collection.json   # Export JSON (pour le viewer)
├── manga_collection_viewer.html  # Viewer web
├── app.py                  # Orchestrateur principal
├── config.py               # Configuration
├── database.py             # Accès BDD
├── pipeline.py             # Pipeline de scraping
├── scraper.py              # HTTP & extraction HTML
├── sync.py                 # Gist & Git
├── utils.py                # Fonctions utilitaires
├── notifications.py        # Emails
├── api_server.py           # Serveur Flask
├── mangavega_scan.bat      # Lanceur scan (interactif)
├── mangavega_scheduled.bat # Lanceur scan (planificateur)
├── mangavega_server.bat    # Lanceur API Flask
├── backups/                # Sauvegardes BDD horodatées
├── brouillons/             # Emails .eml (fallback IMAP)
└── logs/                   # Archives de logs
```

### Variables d'environnement (.env)

```ini
# GitHub
GIST_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx

# Email (Gmail)
EMAIL_EXPEDITEUR=votre@gmail.com
EMAIL_DESTINATAIRE=destinataire@gmail.com
EMAIL_MDP=xxxx xxxx xxxx xxxx

# Email workflow éditorial (Microsoft 365)
EMAIL_DESTINATAIRE_WORKFLOW=votre@domaine.com
IMAP_MOT_DE_PASSE=

# Optionnel
SMTP_SERVER=smtp.gmail.com
```

---

## 14. Troubleshooting

### Erreurs fréquentes

| Symptôme | Cause probable | Solution |
|----------|---------------|----------|
| `corrections.json: 0 validé(s), 0 rejeté(s)` | `GIST_ID` pointe vers mauvais Gist | Vérifier `GIST_ID` dans `config.py` |
| `UnicodeEncodeError: charmap` | Windows utilise cp1252 | Ajouter `PYTHONIOENCODING=utf-8` à l'env |
| Scan 9h au lieu de 45min | PC en veille | Cocher "Réveiller l'ordinateur" dans le planificateur |
| `Task Start Failed` (code 203) | Batch introuvable ou `pause` bloquant | Utiliser `mangavega_scheduled.bat` (sans pause) |
| `curl: (28) Send failure` | Timeout Amazon | Retry automatique (3 tentatives, backoff) |
| `332 À traiter` dans le mail | Statuts non importés depuis Gist | Vérifier `GIST_ID`, lancer un sync |
| Serveur hors ligne (viewer) | Flask pas lancé | Lancer `mangavega_server.bat` |
| Mixed content bloqué | Navigateur bloque HTTP depuis HTTPS | Utiliser `http://localhost:5000` pour le pilotage |

### Commandes de diagnostic

```bash
# Vérifier la BDD
python -c "import sqlite3; c=sqlite3.connect('manga_alerts.db'); print(c.execute('SELECT COUNT(*) FROM volumes').fetchone())"

# Vérifier le Gist
python -c "import urllib.request,json; r=urllib.request.urlopen(urllib.request.Request('https://api.github.com/gists/30cd62947f2ea6c07a044ab3546fb08f',headers={'User-Agent':'X'})); d=json.loads(r.read()); c=json.loads(d['files']['corrections.json']['content']); print(f'rejetes: {len(c.get(\"rejetes\",[]))}')"

# Tester un scan ciblé
python app.py --serie "勇者" --no-email --no-push

# Lister les séries
python app.py --list
```

### `no such column: t.nom_fr` dans les workflows

La table `traductions` utilise `titre_francais` (pas `nom_fr`) et le JOIN doit se faire sur `titre_japonais` (pas `serie_jp`). Bug corrigé le 26/02/2026.

### database.py vide / corrompu

Si database.py est corrompu (ex: ENOSPC), le reconstruire depuis le bytecode :

```bash
python -c "
import marshal, dis, types
with open('__pycache__/database.cpython-313.pyc','rb') as f:
    f.read(16)  # skip magic + timestamp + size
    code = marshal.loads(f.read())
# extraire toutes les constantes string récursivement
"
```

Puis reconstruire manuellement ou via IA en fournissant les strings extraites.

### `python` introuvable (code 49, Microsoft Store stub)

Créer `~/.bash_profile` :

```bash
CONDA_ENV="/c/Users/e.morterol/AppData/Local/anaconda3/envs/mangavega"
export PATH="$CONDA_ENV:$CONDA_ENV/Scripts:$PATH"
```

---

> **Changelog documentation**
> - 2026-02-22 : Création initiale (architecture C4, modules, BDD, ADR, flux)
> - 2026-02-26 : v7.1.0 — Ajout table suivi_editorial, workflow éditorial (notifications.py réécrit), fix pagination infinie pipeline.py, reconstruction database.py depuis bytecode, ADR-007/008, nouvelles variables config IMAP, troubleshooting étendu
