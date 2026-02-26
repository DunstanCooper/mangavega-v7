# ARCHITECTURE — MangaVega Tracker V7

**Document de référence technique — Architecture complète**
Version : 2026-02-26 | Auteur : référence générée

---

## Table des matières

1. [Vue d'ensemble C4 Level 1 — Contexte système](#1-vue-densemble-c4-level-1--contexte-système)
2. [Vue d'ensemble C4 Level 2 — Containers](#2-vue-densemble-c4-level-2--containers)
3. [Graphe des dépendances modules](#3-graphe-des-dépendances-modules)
4. [Schéma BDD complet — SQLite](#4-schéma-bdd-complet--sqlite)
5. [Diagramme flux de données principal — Séquence d'un scan](#5-diagramme-flux-de-données-principal--séquence-dun-scan)
6. [Diagramme flux suivi éditorial](#6-diagramme-flux-suivi-éditorial)
7. [Diagramme pipeline de scraping — Phases A → B → C](#7-diagramme-pipeline-de-scraping--phases-a--b--c)
8. [Diagramme communication Viewer ↔ Script — Via Gist](#8-diagramme-communication-viewer--script--via-gist)
9. [Diagramme email workflow — SMTP + IMAP / .eml fallback](#9-diagramme-email-workflow--smtp--imap--eml-fallback)
10. [Légende et conventions](#10-légende-et-conventions)

---

## 1. Vue d'ensemble C4 Level 1 — Contexte système

```
╔══════════════════════════════════════════════════════════════════════════════════════╗
║                        C4 LEVEL 1 — CONTEXTE SYSTÈME                               ║
║                        MangaVega Tracker V7                                         ║
╚══════════════════════════════════════════════════════════════════════════════════════╝

  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │                           UTILISATEURS                                          │
  │                                                                                 │
  │  ┌───────────────────┐              ┌──────────────────────┐                   │
  │  │  Chargé(e)        │              │  Administrateur      │                   │
  │  │  de droits        │              │  système             │                   │
  │  │  (éditorial)      │              │  (technique)         │                   │
  │  └────────┬──────────┘              └──────────┬───────────┘                   │
  └───────────┼──────────────────────────────────────┼──────────────────────────────┘
              │  Consulte / valide                   │  Lance scan CLI
              │  le Viewer                           │  Configure .env
              ▼                                      ▼
  ┌───────────────────────────────────────────────────────────────────────────────────┐
  │                                                                                   │
  │                     MANGAVEGA TRACKER V7 SYSTEM                                  │
  │                     (Script Python — machine locale)                             │
  │                                                                                   │
  │   ┌─────────────────────────────────────────────────────────────────────────┐    │
  │   │  app.py · config.py · database.py · pipeline.py · scraper.py · sync.py │    │
  │   │  utils.py · notifications.py · api_server.py                            │    │
  │   └─────────────────────────────────────────────────────────────────────────┘    │
  │                                                                                   │
  └──┬────────────────────┬───────────────────┬────────────────────┬──────────────────┘
     │                    │                   │                    │
     ▼                    ▼                   ▼                    ▼
┌──────────────┐  ┌───────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ Amazon.co.jp │  │  GitHub       │  │  Gmail SMTP      │  │  Microsoft 365   │
│              │  │  ┌──────────┐ │  │  (Rapports +     │  │  Exchange        │
│  Pages manga │  │  │  Gist    │ │  │  alertes mail)   │  │  (Brouillons     │
│  + produit   │  │  │  (JSON)  │ │  │                  │  │  workflow        │
│  (scraping   │  │  └──────────┘ │  │  gmail.com       │  │  éditorial)      │
│  HTML curl)  │  │  ┌──────────┐ │  └──────────────────┘  │                  │
│              │  │  │  Pages   │ │                         │  outlook.com     │
│ amazon.co.jp │  │  │(Viewer   │ │                         └──────────────────┘
└──────────────┘  │  │ HTML)    │ │
                  │  └──────────┘ │
                  │  github.com   │
                  └───────────────┘

  FLUX ENTRANTS                          FLUX SORTANTS
  ─────────────────                      ─────────────────
  ◄ Amazon : HTML pages scraping         ► GitHub Gist : manga_collection.json
  ◄ Gist : corrections utilisateur       ► GitHub Pages : manga_collection.json
  ◄ Gist : completions suivi éditorial   ► Gmail : emails rapports + alertes
                                         ► M365 : brouillons emails éditoriaux
                                         ► SQLite local : manga_alerts.db
```

---

## 2. Vue d'ensemble C4 Level 2 — Containers

```
╔══════════════════════════════════════════════════════════════════════════════════════╗
║                        C4 LEVEL 2 — CONTAINERS                                     ║
╚══════════════════════════════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────────────────────────┐
│  MACHINE LOCALE (Windows)                                                           │
│                                                                                     │
│  ┌────────────────────────────────────────────────────────────────────────────┐    │
│  │  SCRIPT PYTHON — Orchestrateur principal                                   │    │
│  │  app.py (CLI + main loop)                                                  │    │
│  │                                                                            │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐ │    │
│  │  │  pipeline.py │  │  scraper.py  │  │   sync.py    │  │notifications  │ │    │
│  │  │  Phase A+B+C │  │  curl_cffi   │  │  Gist R/W    │  │    .py        │ │    │
│  │  │  Orchestrer  │  │  HTTP/HTML   │  │  Git push    │  │  SMTP + IMAP  │ │    │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └───────┬───────┘ │    │
│  │         │                 │                  │                  │         │    │
│  │         └────────┬────────┘                  │                  │         │    │
│  │                  ▼                           │                  │         │    │
│  │  ┌────────────────────────┐                  │                  │         │    │
│  │  │     database.py        │◄─────────────────┘                  │         │    │
│  │  │  DatabaseManager       │                                      │         │    │
│  │  │  SQLite — 10 tables    │                                      │         │    │
│  │  └────────────────────────┘                                      │         │    │
│  │                  ▲                                               │         │    │
│  │  ┌───────────────┴────────────────────────────────────────────┐  │         │    │
│  │  │  config.py · utils.py                                      │  │         │    │
│  │  │  (Configuration globale, parseurs, constantes)             │  │         │    │
│  │  └────────────────────────────────────────────────────────────┘  │         │    │
│  └────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                     │
│  ┌────────────────────────────────┐  ┌──────────────────────────────────────────┐  │
│  │  FLASK API SERVER              │  │  SQLITE DATABASE                         │  │
│  │  api_server.py                 │  │  manga_alerts.db                         │  │
│  │  localhost:5000                │  │  10 tables                               │  │
│  │                                │  │  volumes, featured_history,              │  │
│  │  GET /api/stats                │  │  featured_progression,                   │  │
│  │  GET /api/volumes              │  │  verifications_cache,                    │  │
│  │  GET /api/series               │  │  statuts_manuels, traductions,           │  │
│  │  GET /api/editorial            │  │  series_editeurs, alertes,               │  │
│  │  POST /api/scan                │  │  volume_serie_override,                  │  │
│  │  GET /api/health               │  │  suivi_editorial                         │  │
│  └────────────────────────────────┘  └──────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────┘
              │                                          │
              │ HTTP REST                                │ SQLite R/W
              ▼                                          │
┌──────────────────────────────────────────────────────────────────────────────────┐
│  VIEWER WEB — GitHub Pages (ou local)                                            │
│  manga_collection_viewer.html (3719 l.)                                          │
│  Vanilla HTML + CSS + JavaScript                                                 │
│                                                                                  │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌────────────────────────┐  │
│  │  Collection manga   │  │  Suivi éditorial     │  │  Filtres, recherche,   │  │
│  │  55 séries          │  │  Workflow 6 étapes   │  │  statistiques          │  │
│  │  Volumes + statuts  │  │  Boutons "✓ Fait"    │  │  Export CSV            │  │
│  └─────────────────────┘  └─────────────────────┘  └────────────────────────┘  │
│                                                                                  │
│  Données lues depuis : manga_collection.json (GitHub Pages / local)              │
│  Écrit vers : GitHub Gist (corrections + completions éditorial)                  │
└──────────────────────────────────────────────────────────────────────────────────┘
              │                          ▲
              │ Write (corrections +     │ Read (scan suivant)
              │ completions éditorial)   │
              ▼                          │
┌──────────────────────────────────────────────────────────────────────────────────┐
│  GITHUB GIST — Bus de communication Viewer ↔ Script                              │
│  manga_collection.json                                                           │
│  gist.github.com (API v3)                                                        │
│                                                                                  │
│  Contenu : volumes validés/rejetés + completions suivi éditorial                 │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Graphe des dépendances modules

```
╔══════════════════════════════════════════════════════════════════════════════════════╗
║                     GRAPHE DES DÉPENDANCES — IMPORTS PYTHON                        ║
╚══════════════════════════════════════════════════════════════════════════════════════╝

  app.py (575 l.)  ←── Point d'entrée CLI / orchestrateur
  ├── config.py
  ├── database.py
  ├── pipeline.py
  ├── sync.py
  ├── notifications.py
  └── api_server.py (démarré en thread optionnel)

  pipeline.py (1425 l.)  ←── Orchestrateur scraping
  ├── config.py
  ├── database.py
  ├── scraper.py
  ├── utils.py
  └── notifications.py

  scraper.py (761 l.)  ←── HTTP + extraction HTML
  ├── config.py
  └── utils.py

  sync.py (672 l.)  ←── Gist R/W + Git push
  ├── config.py
  ├── database.py
  └── utils.py

  notifications.py (525 l.)  ←── SMTP + IMAP + .eml
  ├── config.py
  ├── database.py
  └── utils.py

  database.py (1283 l.)  ←── DatabaseManager SQLite
  ├── config.py
  └── utils.py

  api_server.py (273 l.)  ←── Flask REST API
  ├── config.py
  └── database.py

  config.py (235 l.)  ←── Configuration .env + globals
  └── (aucune dépendance interne)

  utils.py (647 l.)  ←── Fonctions pures + constantes
  └── (aucune dépendance interne)

  ─────────────────────────────────────────────────────────────────────────────────
  ARBRE DE DÉPENDANCES (lecture de gauche → droite = "importe")
  ─────────────────────────────────────────────────────────────────────────────────

  app.py ──────────────────────────────────────────────────► config.py
         ├───────────────────────────────────────────────── ► database.py ──► config.py
         │                                                                └──► utils.py
         ├───► pipeline.py ──────────────────────────────── ► config.py
         │                  ├──────────────────────────────► database.py
         │                  ├──► scraper.py ──────────────► config.py
         │                  │                └─────────────► utils.py
         │                  ├──────────────────────────────► utils.py
         │                  └──────────────────────────────► notifications.py
         │
         ├───► sync.py ──────────────────────────────────── ► config.py
         │               ├──────────────────────────────────► database.py
         │               └──────────────────────────────────► utils.py
         │
         ├───► notifications.py ──────────────────────────── ► config.py
         │                        ├───────────────────────── ► database.py
         │                        └───────────────────────── ► utils.py
         │
         └───► api_server.py ─────────────────────────────── ► config.py
                               └────────────────────────────► database.py

  ─────────────────────────────────────────────────────────────────────────────────
  MODULES FEUILLES (pas de dépendances internes)
  ─────────────────────────────────────────────────────────────────────────────────
  config.py  ──── chargement .env, variables globales mutables, chemins fichiers
  utils.py   ──── parsers tomes/dates, EDITEURS_ROMAJI, fonctions pures

  ─────────────────────────────────────────────────────────────────────────────────
  TAILLES DES MODULES (lignes de code)
  ─────────────────────────────────────────────────────────────────────────────────
  database.py      ████████████████████████████████████████████████  1283 l.
  pipeline.py      ██████████████████████████████████████████████████ 1425 l.
  scraper.py       ████████████████████████████████  761 l.
  utils.py         ████████████████████████████  647 l.
  sync.py          ███████████████████████████  672 l.
  notifications.py ██████████████████████  525 l.
  app.py           ████████████████████  575 l.
  viewer.html      ████████████████████████████████████████████████████████████ 3719 l.
  api_server.py    ██████  273 l.
  config.py        ████  235 l.
```

---

## 4. Schéma BDD complet — SQLite

```
╔══════════════════════════════════════════════════════════════════════════════════════╗
║                     SCHÉMA BASE DE DONNÉES — manga_alerts.db                       ║
║                     10 tables SQLite                                                ║
╚══════════════════════════════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────────────────────────┐
│  TABLE : volumes                                                                    │
│  Description : Volumes papier détectés et validés                                  │
│  Clé unique : asin                                                                  │
├────────────────────┬──────────────┬──────────────────────────────────────────────┤
│  Colonne           │  Type        │  Description                                 │
├────────────────────┼──────────────┼──────────────────────────────────────────────┤
│  id                │  INTEGER PK  │  Auto-increment                              │
│  asin              │  TEXT UNIQUE │  Amazon Standard ID (identifiant produit)    │
│  titre             │  TEXT        │  Titre du volume (JP)                        │
│  serie             │  TEXT        │  Nom de la série                             │
│  tome              │  INTEGER     │  Numéro de tome                              │
│  date_sortie       │  TEXT        │  Date de sortie Amazon (YYYY-MM-DD)          │
│  editeur           │  TEXT        │  Éditeur japonais                            │
│  prix              │  TEXT        │  Prix en JPY                                 │
│  url               │  TEXT        │  URL page produit Amazon                     │
│  date_detection    │  TEXT        │  Date de première détection                  │
│  statut            │  TEXT        │  'nouveau' | 'alerte_envoyee' | 'ignore'     │
│  source_phase      │  TEXT        │  'A' | 'B' | 'C' (phase scraping détection)  │
└────────────────────┴──────────────┴──────────────────────────────────────────────┘
                              │
                              │ asin FK →
                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  TABLE : featured_history                                                           │
│  Description : Tous ASINs croisés + leur classification (~1094 lignes)             │
├────────────────────┬──────────────┬──────────────────────────────────────────────┤
│  Colonne           │  Type        │  Description                                 │
├────────────────────┼──────────────┼──────────────────────────────────────────────┤
│  id                │  INTEGER PK  │  Auto-increment                              │
│  asin              │  TEXT        │  Amazon ASIN                                 │
│  serie             │  TEXT        │  Série associée                              │
│  titre             │  TEXT        │  Titre extrait                               │
│  type_produit      │  TEXT        │  'papier' | 'kindle' | 'coffret' | 'autre'  │
│  date_detection    │  TEXT        │  Timestamp détection                         │
│  page_source       │  INTEGER     │  Numéro de page Featured source              │
│  position_page     │  INTEGER     │  Position dans la page                       │
│  classification    │  TEXT        │  Résultat classification automatique         │
└────────────────────┴──────────────┴──────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│  TABLE : featured_progression                                                       │
│  Description : Progression pages Featured par série (55 lignes — 1 par série)      │
├────────────────────┬──────────────┬──────────────────────────────────────────────┤
│  Colonne           │  Type        │  Description                                 │
├────────────────────┼──────────────┼──────────────────────────────────────────────┤
│  id                │  INTEGER PK  │  Auto-increment                              │
│  serie             │  TEXT UNIQUE │  Nom de la série                             │
│  derniere_page     │  INTEGER     │  Dernière page scrappée avec succès          │
│  date_update       │  TEXT        │  Dernière mise à jour                        │
│  total_asin_trouves│  INTEGER     │  Nombre total d'ASINs trouvés                │
└────────────────────┴──────────────┴──────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│  TABLE : verifications_cache                                                        │
│  Description : Cache pages produit /dp/ASIN — TTL 24h (~341 lignes)               │
├────────────────────┬──────────────┬──────────────────────────────────────────────┤
│  Colonne           │  Type        │  Description                                 │
├────────────────────┼──────────────┼──────────────────────────────────────────────┤
│  id                │  INTEGER PK  │  Auto-increment                              │
│  asin              │  TEXT UNIQUE │  Amazon ASIN                                 │
│  html_contenu      │  TEXT        │  HTML brut de la page produit                │
│  date_cache        │  TEXT        │  Timestamp mise en cache                     │
│  est_valide        │  INTEGER     │  1 = cache valide, 0 = expiré                │
└────────────────────┴──────────────┴──────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│  TABLE : statuts_manuels                                                            │
│  Description : Validations/rejets manuels depuis Gist (~327 lignes)                │
├────────────────────┬──────────────┬──────────────────────────────────────────────┤
│  Colonne           │  Type        │  Description                                 │
├────────────────────┼──────────────┼──────────────────────────────────────────────┤
│  id                │  INTEGER PK  │  Auto-increment                              │
│  asin              │  TEXT UNIQUE │  Amazon ASIN                                 │
│  statut            │  TEXT        │  'valide' | 'rejete' | 'a_verifier'          │
│  date_statut       │  TEXT        │  Date de validation/rejet                    │
│  source            │  TEXT        │  'gist' | 'auto' | 'manuel'                  │
│  commentaire       │  TEXT        │  Note optionnelle                            │
└────────────────────┴──────────────┴──────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│  TABLE : traductions                                                                │
│  Description : Correspondances noms JP → FR par série (55 lignes)                  │
├────────────────────┬──────────────┬──────────────────────────────────────────────┤
│  Colonne           │  Type        │  Description                                 │
├────────────────────┼──────────────┼──────────────────────────────────────────────┤
│  id                │  INTEGER PK  │  Auto-increment                              │
│  nom_jp            │  TEXT UNIQUE │  Nom japonais de la série                    │
│  nom_fr            │  TEXT        │  Nom français de la série                    │
│  date_update       │  TEXT        │  Dernière mise à jour                        │
└────────────────────┴──────────────┴──────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│  TABLE : series_editeurs                                                            │
│  Description : Éditeur principal par série (54 lignes)                             │
├────────────────────┬──────────────┬──────────────────────────────────────────────┤
│  Colonne           │  Type        │  Description                                 │
├────────────────────┼──────────────┼──────────────────────────────────────────────┤
│  id                │  INTEGER PK  │  Auto-increment                              │
│  serie             │  TEXT UNIQUE │  Nom de la série                             │
│  editeur           │  TEXT        │  Éditeur japonais principal                  │
│  editeur_romaji    │  TEXT        │  Éditeur en romaji (depuis utils.EDITEURS)   │
│  date_update       │  TEXT        │  Dernière mise à jour                        │
└────────────────────┴──────────────┴──────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│  TABLE : alertes                                                                    │
│  Description : Historique des alertes email envoyées (16 lignes)                   │
├────────────────────┬──────────────┬──────────────────────────────────────────────┤
│  Colonne           │  Type        │  Description                                 │
├────────────────────┼──────────────┼──────────────────────────────────────────────┤
│  id                │  INTEGER PK  │  Auto-increment                              │
│  asin              │  TEXT        │  ASIN du volume alerté                       │
│  serie             │  TEXT        │  Série concernée                             │
│  tome              │  INTEGER     │  Numéro de tome                              │
│  date_alerte       │  TEXT        │  Timestamp envoi alerte                      │
│  type_alerte       │  TEXT        │  'nouveau_volume' | 'relance' | 'rapport'    │
│  email_destinataire│  TEXT        │  Adresse email destinataire                  │
└────────────────────┴──────────────┴──────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│  TABLE : volume_serie_override                                                      │
│  Description : Réaffectation manuelle volume → série (0 lignes actuellement)       │
├────────────────────┬──────────────┬──────────────────────────────────────────────┤
│  Colonne           │  Type        │  Description                                 │
├────────────────────┼──────────────┼──────────────────────────────────────────────┤
│  id                │  INTEGER PK  │  Auto-increment                              │
│  asin              │  TEXT UNIQUE │  ASIN du volume à réaffecter                 │
│  serie_originale   │  TEXT        │  Série détectée automatiquement              │
│  serie_override    │  TEXT        │  Série corrigée manuellement                 │
│  date_override     │  TEXT        │  Date de la correction                       │
└────────────────────┴──────────────┴──────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│  TABLE : suivi_editorial                                                            │
│  Description : Workflow éditorial par volume — 6 étapes séquentielles             │
├────────────────────┬──────────────┬──────────────────────────────────────────────┤
│  Colonne           │  Type        │  Description                                 │
├────────────────────┼──────────────┼──────────────────────────────────────────────┤
│  id                │  INTEGER PK  │  Auto-increment                              │
│  asin              │  TEXT UNIQUE │  ASIN du volume suivi                        │
│  serie             │  TEXT        │  Série concernée                             │
│  tome              │  INTEGER     │  Numéro de tome                              │
│  editeur           │  TEXT        │  Éditeur japonais                            │
│  date_detection    │  TEXT        │  Date de détection du nouveau volume         │
│  etape_courante    │  TEXT        │  Étape active du workflow                    │
│  mail_nwk_date     │  TEXT        │  Date completion étape 1 (mail réseau)       │
│  draft_ad_date     │  TEXT        │  Date completion étape 2 (brouillon AD)      │
│  reponse_nwk_date  │  TEXT        │  Date completion étape 3 (réponse réseau)    │
│  contrat_ad_date   │  TEXT        │  Date completion étape 4 (contrat AD)        │
│  signature_nwk_date│  TEXT        │  Date completion étape 5 (signature réseau)  │
│  facture_date      │  TEXT        │  Date completion étape 6 (facture)           │
│  statut_global     │  TEXT        │  'en_cours' | 'complete' | 'abandonne'       │
│  date_relance      │  TEXT        │  Prochaine date de relance calculée          │
└────────────────────┴──────────────┴──────────────────────────────────────────────┘

  RELATIONS PRINCIPALES
  ──────────────────────
  volumes.asin          ──(1:1)──► suivi_editorial.asin
  volumes.asin          ──(1:N)──► alertes.asin
  volumes.asin          ──(1:1)──► statuts_manuels.asin
  volumes.asin          ──(1:1)──► verifications_cache.asin
  volumes.serie         ──(N:1)──► traductions.nom_jp
  volumes.serie         ──(N:1)──► series_editeurs.serie
  featured_history.asin ──(N:1)──► volumes.asin  (peut ne pas exister en volumes)
  featured_history.serie──(N:1)──► featured_progression.serie
```

---

## 5. Diagramme flux de données principal — Séquence d'un scan

```
╔══════════════════════════════════════════════════════════════════════════════════════╗
║              FLUX PRINCIPAL — SÉQUENCE COMPLÈTE D'UN SCAN                          ║
╚══════════════════════════════════════════════════════════════════════════════════════╝

  DÉCLENCHEMENT
  ─────────────
  Utilisateur / Tâche planifiée
        │
        ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  app.py — main()                                            │
  │  Parse CLI args : --scan, --force, --serie, --dry-run       │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        ▼                        ▼                        ▼
  ┌───────────┐          ┌───────────────┐        ┌──────────────────┐
  │ sync.py   │          │  config.py    │        │  database.py     │
  │ Lire Gist │          │  Charger .env │        │  Ouvrir SQLite   │
  │ (corr. +  │          │  Valider vars │        │  Créer tables si │
  │  editorial│          │               │        │  inexistantes    │
  │  compl.)  │          └───────────────┘        └──────────────────┘
  └─────┬─────┘
        │
        │ Appliquer corrections
        │ Appliquer completions éditorial
        ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  pipeline.py — run_pipeline()                               │
  │  Itération sur 55 séries configurées                        │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        ▼                        ▼                        ▼
  ┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
  │  PHASE A     │     │  PHASE B         │     │  PHASE C         │
  │  Recherche   │     │  Bulk            │     │  Featured        │
  │  Amazon      │     │  depuis page     │     │  Pages paginées  │
  │  (termes JP) │     │  produit connue  │     │  Amazon          │
  └──────┬───────┘     └────────┬─────────┘     └────────┬─────────┘
         │                      │                        │
         └──────────────────────┼────────────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │  scraper.py           │
                    │  SessionWrapper       │
                    │  curl_cffi            │
                    │  impersonate="chrome" │
                    │  Cookies JPY + JA     │
                    └──────────┬────────────┘
                               │
                               ▼
                    ┌───────────────────────┐
                    │  Amazon.co.jp         │
                    │  GET /s?k=...         │
                    │  GET /dp/ASIN         │
                    │  GET /...featured...  │
                    └──────────┬────────────┘
                               │
                               │ HTML Response
                               ▼
                    ┌───────────────────────┐
                    │  BeautifulSoup        │
                    │  Extraction :         │
                    │  - ASINs              │
                    │  - Titres             │
                    │  - Dates sortie       │
                    │  - Éditeurs           │
                    │  - Prix               │
                    │  - Format (papier?)   │
                    └──────────┬────────────┘
                               │
                               │ Liste de volumes candidats
                               ▼
                    ┌───────────────────────┐
                    │  Vérification finale  │
                    │  /dp/ASIN             │
                    │  - Confirme "papier"  │
                    │  - Extraire tome      │
                    │  - Extraire éditeur   │
                    │  Cache 24h SQLite     │
                    └──────────┬────────────┘
                               │
                               │ Volumes vérifiés
                               ▼
                    ┌───────────────────────┐
                    │  database.py          │
                    │  INSERT/UPDATE        │
                    │  volumes              │
                    │  featured_history     │
                    │  featured_progression │
                    └──────────┬────────────┘
                               │
                               │ Nouveaux volumes détectés ?
                               ▼
              ┌────────────────┴─────────────────┐
              │ OUI : nouveau(x) volume(s)        │ NON : aucun nouveau
              ▼                                   ▼
  ┌───────────────────────┐           ┌───────────────────────┐
  │  notifications.py     │           │  Continuer vers       │
  │  Alerte email         │           │  série suivante       │
  │  Gmail SMTP           │           └───────────────────────┘
  │  + Démarrer suivi     │
  │  éditorial (INSERT    │
  │  suivi_editorial)     │
  └───────────┬───────────┘
              │
              │ Après toutes les séries
              ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  Génération rapport final                                   │
  │  notifications.py — envoyer_rapport()                       │
  │  Gmail SMTP                                                 │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  sync.py — push_to_github()                                 │
  │  Génère manga_collection.json depuis SQLite                 │
  │  git add + commit + push                                    │
  │  GitHub Repo → GitHub Pages (Viewer)                        │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  sync.py — write_gist()                                     │
  │  Met à jour le Gist (corrections + statuts)                 │
  └─────────────────────────────────────────────────────────────┘

  PAUSE 8s entre chaque série (anti-détection)
  warm_up() exécuté au démarrage de la session curl_cffi
```

---

## 6. Diagramme flux suivi éditorial

```
╔══════════════════════════════════════════════════════════════════════════════════════╗
║              FLUX SUIVI ÉDITORIAL — DE LA DÉTECTION AU WORKFLOW COMPLET            ║
╚══════════════════════════════════════════════════════════════════════════════════════╝

  DÉCLENCHEMENT : Nouveau volume papier détecté par pipeline.py
  ──────────────────────────────────────────────────────────────

  ┌───────────────────────────────────────────────────────────────────────────────┐
  │  pipeline.py détecte nouveau ASIN papier confirmé                            │
  └──────────────────────────────────┬────────────────────────────────────────────┘
                                     │
                                     ▼
  ┌───────────────────────────────────────────────────────────────────────────────┐
  │  database.py — INSERT INTO suivi_editorial                                   │
  │  Crée fiche workflow avec :                                                  │
  │  - asin, serie, tome, editeur                                                │
  │  - date_detection = maintenant                                               │
  │  - etape_courante = 'mail_nwk'  (étape 1)                                   │
  │  - statut_global = 'en_cours'                                                │
  │  - date_relance = maintenant + 10 jours                                      │
  └──────────────────────────────────┬────────────────────────────────────────────┘
                                     │
                                     ▼
  ╔═══════════════════════════════════════════════════════════════════════════════╗
  ║                  WORKFLOW 6 ÉTAPES SÉQUENTIELLES                             ║
  ╠═══════════════════════════════════════════════════════════════════════════════╣
  ║                                                                               ║
  ║  ÉTAPE 1 : mail_nwk                                                          ║
  ║  ─────────────────                                                           ║
  ║  Action : Envoyer email au réseau japonais (éditeur JP)                      ║
  ║  Brouillon créé : notifications.py → IMAP M365 ou .eml                       ║
  ║  Délai max : 10 jours                                                        ║
  ║                                                                               ║
  ║       │ mail_nwk_date renseigné (bouton "✓ Fait" dans Viewer)                ║
  ║       ▼                                                                       ║
  ║  ÉTAPE 2 : draft_ad                                                          ║
  ║  ──────────────────                                                          ║
  ║  Action : Préparer brouillon accord de distribution (AD)                     ║
  ║  Brouillon créé : notifications.py → IMAP M365 ou .eml                       ║
  ║  Délai max : 10 jours                                                        ║
  ║                                                                               ║
  ║       │ draft_ad_date renseigné                                               ║
  ║       ▼                                                                       ║
  ║  ÉTAPE 3 : reponse_nwk                                                       ║
  ║  ──────────────────────                                                      ║
  ║  Action : Attente réponse réseau japonais                                    ║
  ║  Délai max : 10 jours → relance automatique                                  ║
  ║                                                                               ║
  ║       │ reponse_nwk_date renseigné                                            ║
  ║       ▼                                                                       ║
  ║  ÉTAPE 4 : contrat_ad                                                        ║
  ║  ──────────────────────                                                      ║
  ║  Action : Envoi contrat accord de distribution finalisé                      ║
  ║  Brouillon créé : notifications.py → IMAP M365 ou .eml                       ║
  ║  Délai max : 10 jours                                                        ║
  ║                                                                               ║
  ║       │ contrat_ad_date renseigné                                             ║
  ║       ▼                                                                       ║
  ║  ÉTAPE 5 : signature_nwk                                                     ║
  ║  ─────────────────────────                                                   ║
  ║  Action : Attente signature réseau japonais                                  ║
  ║  Délai max : 10 jours → relance automatique                                  ║
  ║                                                                               ║
  ║       │ signature_nwk_date renseigné                                          ║
  ║       ▼                                                                       ║
  ║  ÉTAPE 6 : facture                                                           ║
  ║  ─────────────────                                                           ║
  ║  Action : Émission et envoi facture                                          ║
  ║  Brouillon créé : notifications.py → IMAP M365 ou .eml                       ║
  ║  Délai max : 10 jours                                                        ║
  ║                                                                               ║
  ║       │ facture_date renseigné                                                ║
  ║       ▼                                                                       ║
  ║  WORKFLOW COMPLET — statut_global = 'complete'                               ║
  ║                                                                               ║
  ╚═══════════════════════════════════════════════════════════════════════════════╝

  MÉCANISME DE RELANCE (délai dépassé)
  ─────────────────────────────────────
  Lors de chaque scan :
  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │  database.py — get_suivi_editorial_relances()                                  │
  │  Requête : étape_courante non complétée ET date_relance < maintenant           │
  └──────────────────────────────────┬─────────────────────────────────────────────┘
                                     │ Fiches en retard
                                     ▼
  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │  notifications.py — envoyer_relance_editorial()                                │
  │  Email d'alerte interne : "Relance requise — [Série] tome [N] — étape [X]"    │
  │  Gmail SMTP vers équipe éditoriale                                             │
  └─────────────────────────────────────────────────────────────────────────────────┘

  COMPLÉTION VIA VIEWER (sens Viewer → Script)
  ─────────────────────────────────────────────
  ┌──────────────────┐     ┌───────────────┐     ┌────────────────────────────────┐
  │  Utilisateur     │     │  GitHub Gist  │     │  Script Python (scan suivant)  │
  │  Viewer HTML     │     │               │     │                                │
  │                  │     │               │     │                                │
  │  Clic "✓ Fait"   │────►│  PATCH Gist   │────►│  sync.py — read_gist()         │
  │  Étape X         │     │  editorial    │     │  Détecte completion étape X    │
  │  Série / Tome    │     │  completions: │     │  database.py — UPDATE          │
  │                  │     │  [{asin, etape│     │  suivi_editorial               │
  │                  │     │   date}]      │     │  Avance etape_courante         │
  └──────────────────┘     └───────────────┘     └────────────────────────────────┘
```

---

## 7. Diagramme pipeline de scraping — Phases A → B → C

```
╔══════════════════════════════════════════════════════════════════════════════════════╗
║              PIPELINE DE SCRAPING — PHASES A → B → C                               ║
╚══════════════════════════════════════════════════════════════════════════════════════╝

  Pour chaque série (55 séries) :
  ────────────────────────────────

  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │  ENTRÉE : nom_serie (JP), termes_recherche[], url_featured                     │
  └──────────────────────────────────┬──────────────────────────────────────────────┘
                                     │
                                     ▼
  ╔═══════════════════════════════════════════════════════════════════════════════╗
  ║                  PHASE A — RECHERCHE AMAZON                                  ║
  ║                                                                               ║
  ║  GET /s?k={terme_recherche}&i=stripbooks                                     ║
  ║                                                                               ║
  ║  scraper.py — search_amazon()                                                ║
  ║    ├── BeautifulSoup → extraire ASINs depuis résultats                       ║
  ║    ├── Filtrer : titre contient nom série ?                                  ║
  ║    ├── Filtrer : type papier (pas kindle) ?                                  ║
  ║    └── Pour chaque ASIN retenu → liste_candidats_A                           ║
  ║                                                                               ║
  ╚═════════════════════════════════════════════════════════════════════════════╤═╝
                                                                               │
                                                                               ▼
  ╔═══════════════════════════════════════════════════════════════════════════════╗
  ║                  PHASE B — BULK PURCHASES                                    ║
  ║                  (depuis page produit connue)                                 ║
  ║                                                                               ║
  ║  Condition : série a un ASIN de référence connu                              ║
  ║                                                                               ║
  ║  GET /dp/{asin_reference}                                                    ║
  ║    └── Section "Bulk purchases" ou "Series" sur page produit                 ║
  ║                                                                               ║
  ║  scraper.py — get_bulk_asins()                                               ║
  ║    ├── BeautifulSoup → extraire ASINs de la section Bulk                     ║
  ║    ├── Fusionner avec liste_candidats_A                                       ║
  ║    └── Dédupliquer                                                            ║
  ║                                                                               ║
  ╚═════════════════════════════════════════════════════════════════════════════╤═╝
                                                                               │
                                                                               ▼
  ╔═══════════════════════════════════════════════════════════════════════════════╗
  ║                  PHASE C — FEATURED PAGES                                    ║
  ║                  (pages paginées Amazon)                                      ║
  ║                                                                               ║
  ║  GET {url_featured}&page={n}                                                 ║
  ║                                                                               ║
  ║  scraper.py — get_featured_asins()                                           ║
  ║    ├── Page 1, 2, 3 ... jusqu'à épuisement ou max_pages                      ║
  ║    ├── Mémoriser dernière page dans featured_progression                      ║
  ║    ├── Arrêt si page vide ou plus de résultats                                ║
  ║    └── Fusionner ASINs dans liste complète                                    ║
  ║                                                                               ║
  ║  Logique pagination :                                                         ║
  ║  ┌───────────────────────────────────────────────────────────────────────┐   ║
  ║  │  page = 1                                                             │   ║
  ║  │  Tant que True :                                                      │   ║
  ║  │    asins_page = scraper.get_featured_page(url, page)                  │   ║
  ║  │    Si asins_page vide → BREAK (fin de pagination)                    │   ║
  ║  │    Si page > max_check_pagination → BREAK                             │   ║
  ║  │    asins_total += asins_page                                          │   ║
  ║  │    db.update_featured_progression(serie, page)                        │   ║
  ║  │    page += 1                                                          │   ║
  ║  └───────────────────────────────────────────────────────────────────────┘   ║
  ║                                                                               ║
  ╚═════════════════════════════════════════════════════════════════════════════╤═╝
                                                                               │
                                        ┌──────────────────────────────────────┘
                                        │ LISTE COMPLÈTE ASINs (A + B + C, dédupliqués)
                                        ▼
  ╔═══════════════════════════════════════════════════════════════════════════════╗
  ║                  VÉRIFICATION FINALE — /dp/ASIN                              ║
  ║                  (pour chaque ASIN de la liste complète)                     ║
  ║                                                                               ║
  ║  Vérification cache SQLite (verifications_cache — TTL 24h)                   ║
  ║                                                                               ║
  ║  ┌─────────────────────────────────────────────────────────────────────────┐ ║
  ║  │  ASIN en cache valide ?                                                  │ ║
  ║  │       │ OUI                         │ NON                               │ ║
  ║  │       ▼                             ▼                                   │ ║
  ║  │  Utiliser HTML cache        GET /dp/{asin} Amazon                       │ ║
  ║  │                             Stocker en cache                             │ ║
  ║  └─────────────────────────────────────────────────────────────────────────┘ ║
  ║                                                                               ║
  ║  BeautifulSoup — vérifications :                                             ║
  ║  ┌─────────────────────────────────────────────────────────────────────────┐ ║
  ║  │  Format == "単行本" (Tankobon / papier) ?                              │ ║
  ║  │       │ OUI                         │ NON                               │ ║
  ║  │       ▼                             ▼                                   │ ║
  ║  │  Extraire :               Ignorer cet ASIN                              │ ║
  ║  │  - Tome (numéro)          (kindle, coffret, etc.)                       │ ║
  ║  │  - Date sortie                                                           │ ║
  ║  │  - Éditeur (JP + romaji)                                                │ ║
  ║  │  - Prix JPY                                                              │ ║
  ║  │  - Titre complet                                                         │ ║
  ║  └─────────────────────────────────────────────────────────────────────────┘ ║
  ║                                                                               ║
  ╚═════════════════════════════════════════════════════════════════════════════╤═╝
                                                                               │
                                                                               ▼
  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │  ASIN déjà en base ? (volumes.asin)                                            │
  │       │ OUI → vérifier mise à jour dates/statuts                              │
  │       │ NON → INSERT volumes + INSERT featured_history + INSERT suivi_editorial│
  └──────────────────────────────────┬──────────────────────────────────────────────┘
                                     │
                                     ▼
  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │  Pause 8 secondes (anti-détection Amazon)                                      │
  │  Passer à la série suivante                                                    │
  └─────────────────────────────────────────────────────────────────────────────────┘

  ANTI-DÉTECTION (SessionWrapper — scraper.py)
  ─────────────────────────────────────────────
  ┌────────────────────────────────────────────────────────────────────────────────┐
  │  curl_cffi.requests.Session(impersonate="chrome")                             │
  │                                                                                │
  │  Headers injectés :                                                           │
  │  - Cookie: i18n-prefs=JPY                                                     │
  │  - Accept-Language: ja-JP,ja;q=0.9,en;q=0.5                                  │
  │  - User-Agent: Chrome (géré par curl_cffi automatiquement)                    │
  │                                                                                │
  │  warm_up() : requête initiale vers amazon.co.jp pour établir session          │
  │  Délai 8s entre chaque série (éviter rate limiting)                           │
  └────────────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Diagramme communication Viewer ↔ Script — Via Gist

```
╔══════════════════════════════════════════════════════════════════════════════════════╗
║              COMMUNICATION VIEWER ↔ SCRIPT — GitHub Gist BUS                      ║
╚══════════════════════════════════════════════════════════════════════════════════════╝

  ARCHITECTURE GÉNÉRALE : Gist = bus de communication unidirectionnel par cycle
  ─────────────────────────────────────────────────────────────────────────────────

                    SCRIPT PYTHON                    VIEWER HTML/JS
                    (machine locale)                 (GitHub Pages)
                         │                                │
                         │                                │
                    ┌────┴────────────────────────────────┴────┐
                    │                                          │
                    │           GITHUB GIST                    │
                    │     manga_collection.json                │
                    │     gist.github.com/API v3              │
                    │                                          │
                    └────┬────────────────────────────────┬────┘
                         │                                │
                         ▼                                ▼
                    SENS SCRIPT → GIST             SENS GIST → VIEWER
                    (écriture JSON principal)       (lecture manga_collection.json)
                    sync.py — write_gist()          fetch() JavaScript natif


  FLUX DÉTAILLÉ
  ─────────────

  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │  A. SCRIPT → GIST (écriture JSON principal, chaque scan)                       │
  │                                                                                 │
  │  sync.py                                                                        │
  │  ┌──────────────────────────────────────────────────────────────────────────┐   │
  │  │  1. Charger tous les volumes depuis SQLite (database.py)                 │   │
  │  │  2. Charger statuts_manuels, traductions, series_editeurs, suivi_edit.  │   │
  │  │  3. Construire manga_collection.json :                                   │   │
  │  │     {                                                                    │   │
  │  │       "series": [{nom, tomes: [{asin, tome, date, statut, editorial}]}] │   │
  │  │       "meta": {date_scan, nb_series, nb_volumes}                         │   │
  │  │       "corrections": {}   ← réservé corrections utilisateur              │   │
  │  │       "editorial_completions": []  ← réservé completions éditorial       │   │
  │  │     }                                                                    │   │
  │  │  4. PATCH https://api.github.com/gists/{GIST_ID}                        │   │
  │  │     Authorization: token {GITHUB_TOKEN}                                  │   │
  │  └──────────────────────────────────────────────────────────────────────────┘   │
  └─────────────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │  B. GIST → VIEWER (lecture, démarrage Viewer)                                  │
  │                                                                                 │
  │  manga_collection_viewer.html                                                   │
  │  ┌──────────────────────────────────────────────────────────────────────────┐   │
  │  │  fetch("https://gist.githubusercontent.com/.../manga_collection.json")  │   │
  │  │    ├── Charger séries et volumes                                         │   │
  │  │    ├── Charger statuts (validé / rejeté / à vérifier)                   │   │
  │  │    └── Charger suivi_editorial par volume (étapes completées)            │   │
  │  │                                                                          │   │
  │  │  Rendu UI :                                                              │   │
  │  │    - Grille séries avec volumes et statuts colorés                       │   │
  │  │    - Tableau suivi éditorial avec étapes et boutons "✓ Fait"            │   │
  │  │    - Statistiques globales                                               │   │
  │  └──────────────────────────────────────────────────────────────────────────┘   │
  └─────────────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │  C. VIEWER → GIST (écriture corrections + completions)                         │
  │                                                                                 │
  │  manga_collection_viewer.html — JavaScript                                      │
  │  ┌──────────────────────────────────────────────────────────────────────────┐   │
  │  │  Correction statut volume :                                             │   │
  │  │    Bouton "Valider" / "Rejeter" → asin + nouveau_statut                 │   │
  │  │                                                                          │   │
  │  │  Completion étape éditoriale :                                           │   │
  │  │    Bouton "✓ Fait" → asin + etape + date_iso                            │   │
  │  │                                                                          │   │
  │  │  PATCH https://api.github.com/gists/{GIST_ID}                           │   │
  │  │  {                                                                       │   │
  │  │    "corrections": {                                                      │   │
  │  │      "{asin}": "valide" | "rejete"                                       │   │
  │  │    },                                                                    │   │
  │  │    "editorial_completions": [                                            │   │
  │  │      {"asin": "...", "etape": "mail_nwk", "date": "2026-02-26"}         │   │
  │  │    ]                                                                     │   │
  │  │  }                                                                       │   │
  │  └──────────────────────────────────────────────────────────────────────────┘   │
  │                                                                                 │
  │  NOTE SÉCURITÉ : GITHUB_TOKEN exposé dans le HTML du Viewer                    │
  │  Permissions minimales recommandées : gist write only                          │
  └─────────────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │  D. GIST → SCRIPT (lecture corrections + completions, au prochain scan)        │
  │                                                                                 │
  │  sync.py — read_gist()                                                          │
  │  ┌──────────────────────────────────────────────────────────────────────────┐   │
  │  │  GET https://api.github.com/gists/{GIST_ID}                             │   │
  │  │  Extraire corrections{}                                                  │   │
  │  │  Extraire editorial_completions[]                                        │   │
  │  │                                                                          │   │
  │  │  Pour chaque correction :                                               │   │
  │  │    database.py — UPDATE statuts_manuels SET statut=... WHERE asin=...   │   │
  │  │                                                                          │   │
  │  │  Pour chaque completion éditoriale :                                    │   │
  │  │    database.py — UPDATE suivi_editorial                                  │   │
  │  │    SET {etape}_date = date, etape_courante = etape_suivante              │   │
  │  └──────────────────────────────────────────────────────────────────────────┘   │
  └─────────────────────────────────────────────────────────────────────────────────┘

  CYCLE COMPLET (timeline)
  ────────────────────────
  T+0   Script scan complet → write_gist (JSON à jour)
  T+X   Utilisateur ouvre Viewer → read_gist → affiche données
  T+X   Utilisateur clique "✓ Fait" étape N → PATCH Gist (completion)
  T+X   Utilisateur clique "Valider" volume → PATCH Gist (correction)
  T+1j  Script scan suivant → read_gist → applique corrections + completions
        → write_gist (JSON remis à jour)
```

---

## 9. Diagramme email workflow — SMTP + IMAP / .eml fallback

```
╔══════════════════════════════════════════════════════════════════════════════════════╗
║              EMAIL WORKFLOW — SMTP Gmail + IMAP M365 + .eml FALLBACK               ║
╚══════════════════════════════════════════════════════════════════════════════════════╝

  TYPES D'EMAILS ÉMIS PAR LE SYSTÈME
  ─────────────────────────────────────

  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │  TYPE 1 : Rapport de scan (envoi direct SMTP)                                  │
  │  TYPE 2 : Alerte nouveau volume (envoi direct SMTP)                             │
  │  TYPE 3 : Relance workflow éditorial (envoi direct SMTP)                        │
  │  TYPE 4 : Brouillons workflow éditorial (IMAP M365 ou .eml fallback)            │
  └─────────────────────────────────────────────────────────────────────────────────┘


  FLUX TYPE 1, 2, 3 — ENVOI DIRECT GMAIL SMTP
  ─────────────────────────────────────────────

  ┌─────────────────────────┐
  │  notifications.py       │
  │  envoyer_rapport()      │  ─── TYPE 1 : rapport récap scan
  │  envoyer_alerte()       │  ─── TYPE 2 : nouveau volume papier
  │  envoyer_relance()      │  ─── TYPE 3 : relance étape éditoriale
  └────────────┬────────────┘
               │
               │  smtplib.SMTP_SSL
               │  smtp.gmail.com:465
               │  Authentification : EMAIL_USER + EMAIL_APP_PASSWORD
               ▼
  ┌─────────────────────────┐
  │  Gmail SMTP             │
  │  gmail.com              │
  │  (compte MangaVega)     │
  └────────────┬────────────┘
               │
               │  Livraison email
               ▼
  ┌─────────────────────────┐
  │  Destinataire(s)        │
  │  EMAIL_DESTINATAIRE     │
  │  (chargé(e) de droits)  │
  └─────────────────────────┘


  FLUX TYPE 4 — BROUILLONS WORKFLOW ÉDITORIAL (IMAP M365 + FALLBACK .eml)
  ─────────────────────────────────────────────────────────────────────────

  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │  notifications.py — creer_brouillon_editorial(etape, volume_info)              │
  │                                                                                 │
  │  Construit MIMEMultipart :                                                      │
  │  - Sujet : "[MangaVega] {etape} — {serie} tome {n}"                            │
  │  - Corps : template texte selon étape (mail_nwk / draft_ad / contrat_ad /      │
  │            facture)                                                             │
  │  - Destinataire : selon étape (réseau JP ou equipe interne)                    │
  └──────────────────────────────────────────┬──────────────────────────────────────┘
                                             │
                       ┌─────────────────────┤
                       │ Tentative principale │ Fallback si échec IMAP
                       ▼                     ▼
  ┌────────────────────────────┐   ┌──────────────────────────────────────────────┐
  │  IMAP M365 — BROUILLON     │   │  FICHIER .eml — FALLBACK LOCAL               │
  │                            │   │                                              │
  │  imaplib.IMAP4_SSL         │   │  Créer fichier :                             │
  │  outlook.office365.com:993 │   │  ./brouillons/{timestamp}_{etape}.eml        │
  │  Auth : M365_USER +        │   │                                              │
  │         M365_PASSWORD      │   │  Format : RFC 2822 standard                  │
  │                            │   │  (email.mime.multipart)                      │
  │  APPEND "[Drafts]"         │   │                                              │
  │  (\\Draft)                 │   │  Utilisateur ouvre manuellement              │
  │                            │   │  avec Outlook / Thunderbird                  │
  │  Email créé comme          │   │                                              │
  │  brouillon M365            │   │  LOG : "Brouillon sauvé : {chemin}"          │
  └────────────────────────────┘   └──────────────────────────────────────────────┘
               │                                    │
               ▼                                    ▼
  ┌────────────────────────────┐   ┌──────────────────────────────────────────────┐
  │  Dossier Brouillons M365   │   │  Répertoire ./brouillons/ local              │
  │  Utilisateur peut          │   │  Fichiers : YYYY-MM-DD_HH-MM_etape.eml       │
  │  modifier + envoyer        │   │  Utilisateur ouvre + envoie manuellement     │
  │  depuis Outlook            │   │                                              │
  └────────────────────────────┘   └──────────────────────────────────────────────┘

  DÉCISION FALLBACK
  ──────────────────
  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │                                                                                 │
  │  try:                                                                          │
  │      imap = imaplib.IMAP4_SSL("outlook.office365.com", 993)                   │
  │      imap.login(M365_USER, M365_PASSWORD)                                      │
  │      imap.append("[Gmail]/Brouillons", "\\Draft", ...)                        │
  │      LOG : "Brouillon créé dans M365"                                          │
  │  except (imaplib.IMAP4.error, ConnectionError, TimeoutError) as e:            │
  │      LOG : f"IMAP échoué : {e} — Fallback .eml"                              │
  │      sauvegarder_eml_local(message, etape)                                    │
  │                                                                                 │
  └─────────────────────────────────────────────────────────────────────────────────┘

  VARIABLES D'ENVIRONNEMENT (.env)
  ──────────────────────────────────
  ┌───────────────────────┬───────────────────────────────────────────────────────┐
  │  Variable             │  Usage                                               │
  ├───────────────────────┼───────────────────────────────────────────────────────┤
  │  EMAIL_USER           │  Compte Gmail expéditeur (SMTP)                      │
  │  EMAIL_APP_PASSWORD   │  Mot de passe applicatif Gmail (2FA)                │
  │  EMAIL_DESTINATAIRE   │  Adresse(s) réception rapports + alertes             │
  │  M365_USER            │  Compte Microsoft 365 (IMAP brouillons)              │
  │  M365_PASSWORD        │  Mot de passe M365                                   │
  │  GITHUB_TOKEN         │  Token GitHub (Gist R/W + git push)                 │
  │  GIST_ID              │  ID du Gist manga_collection.json                   │
  └───────────────────────┴───────────────────────────────────────────────────────┘
```

---

## 10. Légende et conventions

```
╔══════════════════════════════════════════════════════════════════════════════════════╗
║                     LÉGENDE ET CONVENTIONS                                          ║
╚══════════════════════════════════════════════════════════════════════════════════════╝

  CARACTÈRES BOX-DRAWING UTILISÉS
  ─────────────────────────────────
  ┌ ─ ┐     Coin haut-gauche, ligne horizontale, coin haut-droite
  │         Ligne verticale
  ├         Jonction gauche (T horizontal)
  └ ─ ┘     Coin bas-gauche, ligne horizontale, coin bas-droite
  ╔ ═ ╗     Coin haut-gauche double, ligne double, coin haut-droite double
  ║         Ligne verticale double
  ╠ ╣       Jonctions doubles
  ╚ ═ ╝     Coin bas-gauche double, ligne double, coin bas-droite double
  ►         Flèche droite (flux de données)
  ◄         Flèche gauche (flux retour)
  ▼         Flèche bas (flux descendant)
  ▲         Flèche haut (flux montant)
  ──►       Relation ou dépendance directionnelle
  ──(1:N)──► Relation base de données (cardinalité)

  CONVENTIONS DE NOMMAGE
  ───────────────────────
  module.py         Module Python source
  NomClasse()       Classe Python instanciée
  fonction()        Appel de fonction
  TABLE             Table SQLite (majuscules dans le schéma)
  {VARIABLE}        Variable d'environnement ou paramètre dynamique
  /* commentaire */ Note de diagramme

  NIVEAUX C4 UTILISÉS
  ─────────────────────
  Level 1 (Context)    — Vue macro : acteurs humains + systèmes externes
  Level 2 (Containers) — Vue des processus : script, API, BDD, Viewer, Gist

  PHASES DE SCRAPING
  ───────────────────
  Phase A   Recherche Amazon /s?k=... → liste initiale ASINs
  Phase B   Bulk depuis page /dp/{asin} → ASINs "série complète"
  Phase C   Featured pages paginées → ASINs exhaustifs par série

  ÉTAPES WORKFLOW ÉDITORIAL (dans l'ordre)
  ──────────────────────────────────────────
  1. mail_nwk       Email initial au réseau japonais (éditeur JP)
  2. draft_ad       Brouillon accord de distribution préparé
  3. reponse_nwk    Réponse reçue du réseau japonais
  4. contrat_ad     Contrat accord de distribution envoyé
  5. signature_nwk  Signature obtenue du réseau japonais
  6. facture        Facture émise et envoyée

  STATUTS VOLUMES
  ────────────────
  nouveau           Volume détecté, alerte non encore envoyée
  alerte_envoyee    Alerte email envoyée à l'équipe
  valide            Confirmé manuellement via Viewer/Gist
  rejete            Rejeté manuellement (faux positif, kindle, etc.)
  a_verifier        Statut intermédiaire en attente de review

  FLUX DE DONNÉES — RÉSUMÉ
  ──────────────────────────
  Amazon.co.jp ──────────────────────────────► SQLite (manga_alerts.db)
  SQLite ─────────────────────────────────────► manga_collection.json
  manga_collection.json ──────────────────────► GitHub Pages (Viewer)
  manga_collection.json ──────────────────────► GitHub Gist (bus comm)
  GitHub Gist ────────────────────────────────► Script Python (scan suivant)
  Script Python ──────────────────────────────► Gmail SMTP (rapports + alertes)
  Script Python ──────────────────────────────► IMAP M365 / .eml (brouillons)
  Script Python ──────────────────────────────► GitHub Repo (git push JSON)
```

---

*Fin du document ARCHITECTURE.md — MangaVega Tracker V7*
*Généré le 2026-02-26*
