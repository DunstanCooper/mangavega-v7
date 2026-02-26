# CLAUDE.md — Dossier de passation MangaVega Tracker V7

> Ce fichier est le briefing complet pour Claude Code. Il contient TOUT le contexte
> nécessaire pour reprendre le projet sans poser de questions au développeur.
> Dernière mise à jour : 26 février 2026.

---

## 1. RÉSUMÉ DU PROJET

**MangaVega Tracker** est un tracker automatisé qui surveille les sorties de mangas et light novels sur Amazon Japon (amazon.co.jp), détecte les nouveaux volumes papier, et notifie l'utilisateur par email.

Le projet a été **refactorisé de V6 à V7** en février 2026 : monolithe de 4 837 lignes découpé en 9 modules Python (environ 6 400 lignes total). Le viewer HTML (3 719 lignes) permet de consulter la collection et de piloter le script via une API Flask locale.

En plus du suivi Amazon, le projet intègre désormais un **système de suivi éditorial** : pour chaque nouveau volume détecté, un workflow en 6 étapes est créé (mail d'ouverture → draft → réponse → contrat → signature → facture). Un email professionnel combiné (nouvelles sorties + relances) est déposé comme brouillon M365 via IMAP ou sauvegardé en .eml.

**Propriétaire** : Dunstan Cooper
**Repo** : https://github.com/DunstanCooper/mangavega-v7
**Viewer** : https://dunstancooper.github.io/mangavega-v7/manga_collection_viewer.html
**Gist V7** : https://gist.github.com/DunstanCooper/30cd62947f2ea6c07a044ab3546fb08f

---

## 2. STACK TECHNIQUE

| Composant | Technologie | Notes |
|-----------|-------------|-------|
| Langage | Python 3.10.19 (Anaconda env mangavega sur Windows) | |
| Scraping HTTP | `curl_cffi` avec `impersonate="chrome"` | TLS fingerprint Chrome anti-bot |
| Parsing HTML | `BeautifulSoup` + `lxml` | |
| BDD | SQLite3 (`manga_alerts.db`, fichier unique) | |
| API locale | Flask 3.0 sur localhost:5000 | |
| Viewer | HTML/CSS/JS vanilla, fichier unique | Hébergé sur GitHub Pages |
| Corrections | GitHub Gist (API REST) | Bus de comm viewer - script |
| Notifications | SMTP multi-ports (465/587/25/2525) + IMAP M365 brouillons | |
| Planification | Planificateur de tâches Windows | |
| Versioning | Git + GitHub | |

---

## 3. STRUCTURE DES FICHIERS

```
mangavega-v7/
+-- .env                    # Secrets (GIST_TOKEN, EMAIL_MDP, IMAP_MOT_DE_PASSE) -- JAMAIS commite
+-- .env.example            # Modele
+-- .gitignore
+-- README.md
+-- TODO.md                 # Taches et bugs connus -- LIRE EN PREMIER
+-- requirements.txt        # flask, flask-cors, curl_cffi, beautifulsoup4, lxml, aiohttp
+-- mangas_liste.json       # 55 series a suivre (nom JP, nom_fr, url Amazon)
+-- manga_alerts.db         # BDD SQLite (NE PAS SUPPRIMER)
+-- manga_collection.json   # Export JSON pour le viewer (regenere a chaque scan)
+-- manga_collection_viewer.html  # Viewer web (3719 lignes)
|
+-- app.py (575 l.)         # Orchestrateur principal, CLI, main()
+-- config.py (235 l.)      # Constantes, .env, globals mutables
+-- database.py (1283 l.)   # DatabaseManager, 10 tables, 50+ methodes
+-- pipeline.py (1425 l.)   # Pipeline scraping Phase A-B-C, Featured, Bulk
+-- scraper.py (761 l.)     # SessionWrapper, HTTP, extraction HTML Amazon
+-- sync.py (672 l.)        # Gist R/W, Git push, corrections, traductions
+-- utils.py (647 l.)       # Fonctions pures : parsers tomes (14 patterns), dates, editeurs
+-- notifications.py (525 l.) # Emails workflow editorial (brouillon IMAP M365 ou .eml)
+-- api_server.py (273 l.)  # Flask API locale (5 endpoints : /, /status, /sync, /scan, /backup, /log)
|
+-- mangavega_scan.bat      # Lanceur scan interactif (avec pause)
+-- mangavega_scheduled.bat # Lanceur scan planificateur (sans pause)
+-- mangavega_server.bat    # Lanceur API Flask (double-clic)
+-- test_bulk.py            # Script de debug Bulk (en cours)
+-- backups/                # Copies horodatees de la BDD
+-- brouillons/             # Brouillons .eml workflow editorial (IMAP fallback)
+-- logs/                   # Archives de logs
+-- docs/
    +-- CLAUDE.md            # CE FICHIER (dossier de passation)
    +-- DOC_TECHNIQUE.md     # Architecture technique
    +-- DOC_UTILISATEUR.md   # Guide utilisateur
    +-- ARCHITECTURE.md      # Diagrammes complets (nouveau)
    +-- BONNES_PRATIQUES.md  # Securite OWASP
    +-- GUIDE_INSTALLATION.md
```

---

## 4. MODULES -- CE QUE FAIT CHAQUE FICHIER

### app.py -- Orchestrateur (575 lignes)
- Point d'entree main(), argument parsing (--serie, --list, --no-email, --no-push, --reverifier-traductions)
- Charge config, initialise BDD, charge Gist, lance le pipeline pour chaque serie
- Post-traitement : fusionne resultats, applique statuts manuels, genere JSON, envoie email, git push
- **Nouveau (26/02/2026)** : apres collecte des nouveautes, cree un workflow editorial par nouveau tome :
  1. Appelle `db.creer_workflow_volume()` pour chaque nouveau tome (avec editeur_officiel)
  2. Appelle `db.get_workflows_a_notifier()` pour les volumes necessitant email d'ouverture
  3. Appelle `db.get_actions_en_retard()` pour les relances
  4. Un seul appel `envoyer_email_workflow(config.EMAIL_DESTINATAIRE_WORKFLOW, workflows_jour_j, actions_retard)`
  5. Le workflow est exporte dans manga_collection.json sous la cle `workflow` pour le viewer

### config.py -- Configuration (235 lignes)
- Charge .env (GIST_TOKEN, EMAIL_*, SMTP_*, IMAP_MOT_DE_PASSE, EMAIL_DESTINATAIRE_WORKFLOW)
- Constantes : EDITEURS_CONNUS, MOTS_CLES_DERIVES, TITRES_GENERIQUES
- Globals mutables (modifies au runtime) : GIST_CORRECTIONS, GIST_SERIES_CONFIG, TRADUCTIONS_FR, DATE_SEUIL, MANGAS_A_SUIVRE
- GIST_ID : 30cd62947f2ea6c07a044ab3546fb08f
- **Nouvelles variables (26/02/2026)** :
  - `EMAIL_DESTINATAIRE_WORKFLOW` : adresse pro destinataire du workflow (e.morterol@vega-livres.fr)
  - `IMAP_MOT_DE_PASSE` : mot de passe IMAP M365 (vide = fallback .eml)
  - `IMAP_SERVER = 'outlook.office365.com'`
  - `IMAP_PORT = 993`

### database.py -- DatabaseManager (1283 lignes)
- **ATTENTION** : ce fichier a ete reconstruit depuis `__pycache__/database.cpython-313.pyc` le 26/02/2026 apres crash disque (ENOSPC). Le fichier .pyc a ete decompile et le code restaure manuellement.
- Classe singleton, connexion thread-local, **10 tables** (voir section 5)
- Methodes cles existantes : `sauvegarder_volume()`, `sauvegarder_featured()`, `get_asins_rejetes()`, `get_asins_valides()`, `set_statut_manuel()`
- **Nouvelles methodes suivi_editorial (26/02/2026)** :
  - `ETAPES_WORKFLOW = ['mail_nwk','draft_ad','reponse_nwk','contrat_ad','signature_nwk','facture']` (constante module)
  - `creer_workflow_volume(asin, serie_jp, tome, today, editeur='')` — INSERT OR IGNORE l'etape mail_nwk dans suivi_editorial
  - `get_etape_courante_workflow(asin)` → dict ou None — retourne l'etape courante non terminee
  - `marquer_etape_faite(asin, etape, date_completion)` — passe statut='fait', cree automatiquement l'etape suivante
  - `get_actions_en_retard(delai_jours=10)` → liste de dicts avec nom_fr et editeur (via JOIN sur table volumes)
  - `get_workflows_a_notifier()` → volumes nouvellement en mail_nwk (email_ouverture_envoye=0)
  - `incrementer_relances(asin, etape)` — incremente nb_relances
  - `get_tous_workflows_actifs()` → dict {asin: {etape_courante, date_declenchement, jours_ecoules, etapes_faites, nb_relances, date_sortie_jp, editeur}}
- **Bug corrige (26/02/2026)** : `get_workflows_a_notifier` utilisait `t.nom_fr` inexistant → corrige en `t.titre_francais`, JOIN sur `t.titre_japonais` au lieu de `t.serie_jp`

### pipeline.py -- Pipeline de scraping (1425 lignes)
- `rechercher_manga(serie, db, session)` : fonction principale
- Phase A : Recherche Amazon Search
- Phase B : Bulk -- volumes lies depuis page produit (section Bulk purchases)
- Phase C : Featured -- resultats Amazon pagines
- Classification : papier, ebook, sponsorise, hors_sujet_titre, lot, derive, non_papier
- Verification finale : charge page produit, confirme format papier, extrait date/tome/editeur
- `executer_bulk()` a la ligne 423 : helper interne, lance le Bulk et integre les resultats
- IMPORTANT ligne 516 : `inclure_fb = bool(asin_reference and not volumes_connus)` -- desactive Frequently Bought Together pour les series existantes
- **Fix boucle infinie Featured (26/02/2026)** :
  - Verifie le bouton `s-pagination-next` : absent ou classe `s-pagination-disabled` = derniere vraie page
  - Fallback : si `page_num > 1 and len(items) < 8` → arret
  - Corrige l'accumulation de 3 nouvelles pages par run meme sans vrais resultats

### scraper.py -- HTTP et Extraction HTML (761 lignes)
- `SessionWrapper` : wraps curl_cffi.requests.AsyncSession avec impersonate Chrome
  - Cookies japonais (i18n-prefs=JPY), header Accept-Language: ja-JP
  - `warm_up()` : premiere requete sur amazon.co.jp
- `get_html(session, url)` : requete avec retry 3x, backoff exponentiel, detection captcha
- `extraire_info_produit(html)` : parse page produit → titre, date, editeur, couverture
- `extraire_volumes_depuis_page(session, asin, nom, sources)` : LE PARSING BULK (lignes 312-535)
  - Source "bulk" : cherche div.pbnx-desktop-box ou header "Bulk purchases"/"新品まとめ買い"
  - Source "publisher" : cherche "From the Publisher"/"出版社より"
  - Source "frequently_bought" : cherche "Frequently bought together"/"よく一緒に購入"

### sync.py -- Synchronisation (672 lignes)
- `charger_gist_config()` : lit Gist → config.GIST_CORRECTIONS
- `charger_corrections(db)` : importe Gist → table statuts_manuels en BDD
  - **Nouveau (26/02/2026)** : importe aussi les completions suivi_editorial depuis `gist.suivi_editorial` :
    ```python
    gist_suivi = config.GIST_CORRECTIONS.get('suivi_editorial', {})
    for asin, completions in gist_suivi.items():
        for etape, date_completion in completions.items():
            if date_completion:
                db.marquer_etape_faite(asin, etape, date_completion)
    ```
- `sauvegarder_gist_config()` : ecrit corrections.json dans le Gist (met a jour date_seuil)
- `git_push()` : git add + commit + push du manga_collection.json

### utils.py -- Fonctions pures (647 lignes)
- `extraire_numero_tome(titre)` : 14 patterns regex pour extraire le numero de tome
- `parser_date_japonaise(text)` : parse 2025年3月10日 et variantes EN
- `normaliser_editeur(raw)` : uniformise noms (EDITEURS_ROMAJI, 64 mappings katakana→romaji)
- `est_derive(titre)` : detecte artbooks, anthologies, novelisations

### notifications.py -- Emails workflow editorial (525 lignes)

Ce module a ete entierement reecrit le 26/02/2026. Il ne gere plus les anciens rapports HTML mais uniquement l'email professionnel du workflow editorial.

**Architecture des fonctions** :
- `_editeur_romaji(editeur_jp)` : convertit un editeur JP en romaji via utils.EDITEURS_ROMAJI
- `_type_serie(serie_jp)` : retourne ' (LN)' ou ' (Manga)' selon le nom de serie
- `_grouper_par_editeur(items)` : groupe une liste de volumes par editeur romaji
- `_format_date_fr(date_iso)` : convertit YYYY-MM-DD → DD/MM/YYYY
- `_envoyer_smtp(msg, label)` : envoi SMTP multi-ports (essaie 465 → 587 → 25 → 2525)
- `_deposer_brouillon_workflow(msg)` → bool : depose le message dans les Brouillons M365 via IMAP APPEND (Brouillons ou Drafts selon la locale)
- `_sauvegarder_eml(msg, nom_fichier)` : fallback fichier .eml dans le dossier brouillons/
- `envoyer_email_workflow(destinataire, volumes_nouveaux, actions_retard)` : EMAIL COMBINE
  - Sujet dynamique : "Offres a demander" (seulement nouvelles) / "Relance offres" (seulement relances) / "Offres editoriales" (les deux)
  - Corps plain-text professionnel, commence par "Bonjour Nicolas,"
  - Groupe par editeur romaji
  - Nouvelles sorties : `- Titre (LN/Manga) Tx, sortie le DD/MM — il vient de sortir et s'ajoute a la liste`
  - Relances : `- Titre (Manga) Tx, sortie le DD/MM — je t'avais fait un mail sur ce tome le DATE`
  - Essaie IMAP d'abord → fallback .eml (jamais d'envoi direct SMTP)
  - From = EMAIL_DESTINATAIRE_WORKFLOW (adresse pro)

### api_server.py -- Flask API (273 lignes)
- GET / : sert le viewer, GET /api/status, POST /api/sync, POST /api/scan, POST /api/backup, GET /api/log
- Le subprocess charge le .env manuellement et force PYTHONIOENCODING=utf-8

---

## 5. BASE DE DONNEES (manga_alerts.db)

### Tables et colonnes

**volumes** (353 lignes) -- Volumes papier confirmes
- id INTEGER PK AUTO, serie_jp TEXT, serie_fr TEXT, tome TEXT
- asin TEXT UNIQUE, url TEXT, date_sortie_jp TEXT, titre_volume TEXT
- date_ajout TEXT, date_maj TEXT, editeur TEXT

**featured_history** (1094 lignes) -- Tous les ASINs croises + classification
- serie TEXT, asin TEXT PK, statut TEXT, source TEXT, titre TEXT, asin_papier TEXT, date_vu TEXT
- Statuts : ebook(430), papier(46), sponsorise(49), hors_sujet_titre(534), lot(16), derive(2), non_papier(17)
- Sources : migration(331), featured_p1(317), featured_p2(209), featured_p3(60), featured_p4(80), featured_p5(76), bulk(21)

**featured_progression** (55 lignes) -- Progression par serie
- serie TEXT PK, derniere_page INT, exploration_complete INT, date_maj TEXT

**statuts_manuels** (327 lignes) -- Validations/rejets depuis le Gist
- asin TEXT PK, statut TEXT (valide:318/rejete:9), commentaire TEXT, date_modification TEXT

**verifications_cache** (341 lignes) -- Cache pages produit (24h)
- asin TEXT PK, date_verification TEXT, date_sortie TEXT, tome TEXT, titre TEXT, editeur TEXT

**traductions** (55 lignes), **series_editeurs** (54 lignes), **alertes** (16 lignes), **volume_serie_override** (0 lignes)

**suivi_editorial** (nouvelle table, 26/02/2026) -- Workflow editorial par volume
```sql
CREATE TABLE IF NOT EXISTS suivi_editorial (
    asin TEXT NOT NULL,
    serie_jp TEXT NOT NULL,
    tome INTEGER,
    etape TEXT NOT NULL,  -- 'mail_nwk','draft_ad','reponse_nwk','contrat_ad','signature_nwk','facture'
    statut TEXT DEFAULT 'en_attente',   -- 'en_attente', 'fait'
    date_declenchement TEXT NOT NULL,
    date_completion TEXT,
    nb_relances INTEGER DEFAULT 0,
    pause_jusqu_au TEXT,
    email_ouverture_envoye INTEGER DEFAULT 0,
    date_sortie_jp TEXT,   -- date de parution JP du tome
    editeur TEXT,          -- editeur en romaji
    PRIMARY KEY (asin, etape)
)
```

Les 6 etapes du workflow (dans l'ordre) :
1. `mail_nwk` : Email d'ouverture envoye a NWK (Nakawaki)
2. `draft_ad` : Draft de l'AD (accord de distribution) prepare
3. `reponse_nwk` : Reponse de NWK recue
4. `contrat_ad` : Contrat AD envoye
5. `signature_nwk` : Signature NWK recue
6. `facture` : Facture emise

### ATTENTION : colonne `serie` vs `serie_jp`
La colonne s'appelle `serie` dans featured_history et featured_progression, mais `serie_jp` dans volumes. Meme donnee, noms differents. Ne pas confondre dans les requetes SQL.

---

## 6. BUG EN COURS -- TOMES MANQUANTS SUR CERTAINES SERIES

### Contexte important
Le Bulk FONCTIONNE pour la plupart des series. Les 353 volumes en BDD ont ete trouves lors de scans precedents. Le fait que featured_history ne montre que 21 ASINs source=bulk est normal : les ASINs deja connus sont dans asin_deja_vus et ne sont pas re-enregistres dans featured_history.

### Serie reellement problematique : 氷菓 [MANGA] (Hyouka)
- 6 tomes trouves sur 17 (tomes 1, 3, 7, 15, 16, 17)
- 11 tomes manquants : 2, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14
- La section "Bulk purchases of new products" EXISTE sur Amazon pour cette serie
- Le parser Bulk dans scraper.py (lignes 364-446) ne la capture pas

### Faux problemes (resolus apres investigation)
- **わたしの幸せな結婚 [LN]** : tomes 1-10 TOUS presents. Les 2 N/A sont des derives (artbook + databook). Le viewer signalait "tome 3 manquant" a cause de "Date inconnue" -- pas un vrai manque.
- **死亡遊戯で飯を食う [MANGA]** : tomes 1-9 tous presents mais avec doublons (LN MF文庫J melanges avec manga 角川コミックス・エース). Probleme d'affichage, pas de tomes manquants.

### Diagnostic du parser Bulk (scraper.py lignes 364-446)
Le code cherche :
1. Methode 1 (ligne 372) : div.pbnx-desktop-box contenant le titre de la serie
2. Methode 2 (ligne 408) : header "Bulk purchases" ou "新品まとめ買い"
MAIS la page peut etre en anglais "Bulk purchases of new products" (non matche)

### Script de debug
```bash
python test_bulk.py
```
Charge la page de Hyouka tome 1 (ASIN 4041202701), sauvegarde le HTML dans debug_page_4041202701.html.
ATTENTION : crashe actuellement avec 'NoneType' object has no attribute 'get'. A investiguer.

### Probleme connexe : Frequently Bought Together desactive
pipeline.py ligne 516 : `inclure_fb = bool(asin_reference and not volumes_connus)`
Desactive pour les series existantes. Pourrait servir de fallback quand le Bulk ne trouve rien de nouveau.

### Probleme connexe : URLs sponsorisees
25 volumes ont des URLs sspa/spons. L'ASIN est correct mais jamais re-verifie sur /dp/ASIN direct. Ces volumes ont souvent "Date inconnue".

### Probleme connexe : Series manga/LN melangees
死亡遊戯で飯を食う existe en [MANGA] (角川コミックス・エース) et [LN] (MF文庫J) avec le meme titre. Le pipeline ne les separe pas, ce qui cree des doublons dans la collection.

---

## 7. AUTRES BUGS CONNUS

- 12 volumes avec "Date inconnue", 33 avec tome = N/A (LN sans numero, derives)
- 死亡遊戯で飯を食う : LN (MF文庫J) et manga (角川コミックス・エース) melanges dans la meme serie [MANGA]
- Cache N/A : volumes avec tome N/A re-verifies a chaque scan
- Mail : stats basees sur le scan en cours, pas le total BDD

---

## 8. HISTORIQUE DES BUGS CORRIGES

1. UPDATE verifications SET tome -> table inexistante (verifications_cache)
2. MOTS_CLES_DERIVES en dur -> config.MOTS_CLES_DERIVES
3. TITRES_GENERIQUES redefini localement -> supprime
4. reverifier_toutes_traductions doublon -> supprime
5. Imports typing manquants -> ajoutes
6. Secrets en clair -> migration .env
7. 0% dates extraites -> warm-up JP + parser bilingue
8. Featured angle mort precommandes -> tables featured_history + progression
9. Ebooks Bulk non memorises -> sauvegarder_featured()
10. 2 parsers de tome divergents -> fusion utils.py
11. Tome non detecte entre kanji -> Pattern regex Format 11
12. Ebooks LN re-scannes chaque run -> skip via featured_history
13. exploration_complete pas marquee page 5 -> fix + retroactif
14. Featured total incoherent -> supprime
15. Table ebooks_traites fantome -> supprimee + migration
16. 4 fonctions mortes -> supprimees
17. purger_serie() referencait table supprimee -> corrige
18. 54 traductions dupliquees -> dedoublonnees
19. Subprocess scan sans .env ni UTF-8 -> chargement .env + PYTHONIOENCODING
20. GIST_ID pointait vers V6 -> corrige 30cd629...
21. Mail mentionnait "GitHub Actions artifacts" -> lien viewer
22. SQL crash `no such column: t.nom_fr` dans `get_workflows_a_notifier` → corrige en `t.titre_francais`, JOIN sur `t.titre_japonais` au lieu de `t.serie_jp` (26/02/2026)
23. Boucle infinie pages Featured (accumulation 3 pages/run sans vrais resultats) → check bouton `s-pagination-next` absent ou classe `s-pagination-disabled` + fallback `page_num > 1 and len(items) < 8` (26/02/2026)
24. database.py corrompu a 0 octets apres crash disque (ENOSPC) → reconstruit depuis `__pycache__/database.cpython-313.pyc` via decompilation manuelle (26/02/2026)
25. python introuvable dans bash (stub Windows Store interceptait la commande) → cree `~/.bash_profile` avec chemin Anaconda env mangavega en priorite dans PATH (26/02/2026)

---

## 9. DECISIONS TECHNIQUES (ADR)

- ADR-001 : curl_cffi (pas requests) pour TLS fingerprint Chrome anti-bot Amazon
- ADR-002 : SQLite (pas PostgreSQL) pour mono-utilisateur local
- ADR-003 : GitHub Gist comme bus viewer-script (viewer statique ne peut pas parler au script)
- ADR-004 : Modules Python (pas microservices), couplage via config.py globals
- ADR-005 : Flask localhost:5000 pour pilotage (mixed content HTTPS→HTTP OK car localhost exempte)
- ADR-006 : HTML monofichier viewer (zero dependance, zero build)
- ADR-007 : IMAP APPEND (pas SMTP envoi direct) pour les emails workflow — le brouillon est relu/corrige avant envoi manuel par l'utilisateur
- ADR-008 : Fallback .eml si IMAP_MOT_DE_PASSE vide — permet de tester sans credentials M365

---

## 10. ENVIRONNEMENT UTILISATEUR

- OS : Windows 11 Pro
- Python : Anaconda, **env mangavega** (Python 3.10.19) — PAS le base environment
  - Chemin env : `C:\Users\e.morterol\AppData\Local\anaconda3\envs\mangavega`
  - `~/.bash_profile` cree le 26/02/2026 pour mettre l'env mangavega en priorite dans PATH :
    ```bash
    CONDA_ENV="/c/Users/e.morterol/AppData/Local/anaconda3/envs/mangavega"
    export PATH="$CONDA_ENV:$CONDA_ENV/Scripts:$PATH"
    ```
  - Probleme : le stub Windows Store (`python.exe`) interceptait `python` dans bash → resolu par le .bash_profile
- Chemin projet : `C:\Users\e.morterol\dev\mangavegatrackerV7-claudecode\mangavega-v7`
- Git installe, push via HTTPS
- Planificateur : tache "MangaVega", batch mangavega_scheduled.bat
- Encodage : Windows cp1252 → toujours forcer UTF-8
- Console : Anaconda Prompt ou Git Bash avec .bash_profile charge
- PAS de WSL installe

---

## 11. PIEGES A EVITER

1. Ne JAMAIS commiter .env
2. Toujours forcer UTF-8 (PYTHONIOENCODING=utf-8) dans les subprocess
3. GIST_ID doit etre 30cd62947f2ea6c07a044ab3546fb08f (V7, pas V6)
4. Colonne serie vs serie_jp dans la BDD (voir section 5)
5. Config globals mutables modifies au runtime (couplage implicite)
6. Respecter les pauses Amazon (8s/15 series), warm-up obligatoire
7. Pages Amazon parfois en anglais malgre les cookies JP
8. Pas de pause dans les batch du planificateur
9. La veille Windows suspend le scan (duree gonflee)
10. manga_collection.json NE DOIT PAS etre dans .gitignore
11. database.py a ete reconstruit depuis .pyc — si un comportement semble etrange, verifier la fidelite de la reconstruction
12. IMAP_MOT_DE_PASSE vide = fallback .eml, PAS d'erreur fatale — le workflow continue
13. Dans suivi_editorial : JOIN sur `t.titre_japonais` (colonne de la table volumes), pas sur `t.serie_jp` qui n'existe pas dans volumes

---

## 12. COMMANDES UTILES

```bash
# Scanner toutes les series
python app.py

# Scanner une serie specifique sans email ni push
python app.py --serie "葬送のフリーレン" --no-email --no-push

# Lister les series
python app.py --list

# Lancer l'API Flask
python api_server.py

# Test rapide (3 series, ~60s)
python app.py --serie "勇者" --no-email --no-push

# Debug Bulk (en cours de fix)
python test_bulk.py

# Verifier que le bon Python est utilise (doit afficher l'env mangavega)
which python
python --version
```

---

## 13. GIST -- STRUCTURE

```
corrections.json : {
  valides: [...],
  rejetes: [...],
  tomes: {asin: tome_num},
  date_seuil: "2026-02-08",
  suivi_editorial: {
    "ASIN": {
      "mail_nwk": "2026-02-26",
      "draft_ad": "2026-03-05"
    }
  }
}

series_config.json : { urls_supplementaires: {}, series_ajoutees: [] }
```

Le viewer ecrit (validations/rejets/completions editorial). Le script lit au demarrage et ecrit date_seuil a la fin.

**Flux suivi_editorial via Gist** :
1. L'utilisateur clique "Fait" dans le viewer (onglet Suivi)
2. Le viewer ecrit `corrections.json.suivi_editorial[asin][etape] = date_completion`
3. Au prochain scan, `sync.charger_corrections(db)` importe ces completions via `db.marquer_etape_faite()`
4. `marquer_etape_faite()` passe l'etape en 'fait' et cree automatiquement l'etape suivante

---

## 14. PRIORITES DE TRAVAIL

1. CRITIQUE : Comprendre pourquoi 氷菓 n'a que 6 tomes sur 17 (debug Bulk parser scraper.py + test_bulk.py)
2. IMPORTANT : Re-verifier les 25 volumes avec URLs sponsorisees sur leur vraie page /dp/ASIN (date inconnue)
3. IMPORTANT : Activer Frequently Bought Together comme fallback quand Bulk ne trouve rien de nouveau (pipeline.py ligne 516)
4. MOYEN : Separer manga/LN pour les series mixtes (死亡遊戯 : doublons manga+LN)
5. MOYEN : Tester le brouillon IMAP M365 une fois que IMAP_MOT_DE_PASSE est fourni dans .env
6. FUTUR : Migration Raspberry Pi, demarrage auto Flask

---

## 15. SUIVI EDITORIAL -- WORKFLOW

### Vue d'ensemble

Le systeme de suivi editorial permet de gerer le processus d'acquisition des droits de traduction pour chaque nouveau volume detecte sur Amazon JP. Pour chaque nouveau tome, un workflow en 6 etapes est cree automatiquement.

### Les 6 etapes du workflow

| Code etape | Nom complet | Description |
|------------|-------------|-------------|
| `mail_nwk` | Email d'ouverture | Premier contact envoye a NWK (Nakawaki, l'agent JP) |
| `draft_ad` | Draft accord distribution | Preparation du projet d'accord de distribution |
| `reponse_nwk` | Reponse NWK | Reception de la reponse de NWK |
| `contrat_ad` | Contrat AD | Envoi du contrat d'accord de distribution signe |
| `signature_nwk` | Signature NWK | Reception du contrat signe par NWK |
| `facture` | Facture | Emission de la facture finale |

### Declenchement automatique

A chaque scan, app.py :
1. Detecte les nouveaux volumes papier (nouvelles entrees dans la table volumes)
2. Appelle `db.creer_workflow_volume(asin, serie_jp, tome, today, editeur)` → INSERT OR IGNORE etape `mail_nwk`
3. Appelle `db.get_workflows_a_notifier()` → volumes avec `email_ouverture_envoye=0`
4. Appelle `db.get_actions_en_retard(delai_jours=10)` → etapes dont `date_declenchement` depasse 10 jours sans completion
5. Appelle `notifications.envoyer_email_workflow(...)` avec la liste des nouveautes et des relances

### Email workflow (notifications.py)

L'email est **toujours un brouillon** (jamais envoye directement) :
- **Priorite 1** : IMAP APPEND vers M365 (dossier Brouillons ou Drafts) si `IMAP_MOT_DE_PASSE` defini
- **Fallback** : sauvegarde .eml dans le dossier `brouillons/` si IMAP indisponible ou mot de passe vide

Format de l'email :
```
From: e.morterol@vega-livres.fr
To: destinataire
Subject: Offres a demander / Relance offres / Offres editoriales

Bonjour Nicolas,

[Section nouvelles sorties si volumes_nouveaux non vide]
Voici les nouvelles sorties JP de cette semaine :

[Groupes par editeur romaji]
=== Shueisha ===
- One Piece (Manga) T108, sortie le 04/02 — il vient de sortir et s'ajoute a la liste
- Jujutsu Kaisen (Manga) T27, sortie le 04/02 — il vient de sortir et s'ajoute a la liste

=== Kodansha ===
- Fruits Basket (Manga) T14, sortie le 10/02 — il vient de sortir et s'ajoute a la liste

[Section relances si actions_retard non vide]
Voici les titres pour lesquels je n'ai pas eu de retour :

=== Shueisha ===
- Naruto (Manga) T5, sortie le 15/01 — je t'avais fait un mail sur ce tome le 15/01/2026

Bonne journee,
[signature]
```

### Completion via le viewer

Dans l'onglet "Suivi editorial" du viewer :
- Bouton "Fait" (mode admin) : enregistre `suiviEditorial[asin][etape] = date_aujourd_hui` dans le Gist
- Bouton "Pause" : suspend le calcul du delai jusqu'a une date donnee (champ `pause_jusqu_au`)
- Bouton "Relance" : reinitialise `date_declenchement` a aujourd'hui et incremente `nb_relances`

### Progression via le Gist

Le viewer ecrit les completions dans `corrections.json.suivi_editorial`. Au prochain scan, `sync.charger_corrections(db)` importe ces completions :
```python
gist_suivi = config.GIST_CORRECTIONS.get('suivi_editorial', {})
for asin, completions in gist_suivi.items():
    for etape, date_completion in completions.items():
        if date_completion:
            db.marquer_etape_faite(asin, etape, date_completion)
```

`marquer_etape_faite()` : passe l'etape courante en `statut='fait'` ET cree automatiquement la prochaine etape dans `ETAPES_WORKFLOW` avec `date_declenchement = date_completion`.

### Onglet viewer "Suivi editorial" (manga_collection_viewer.html)

- 6eme onglet ajoute au viewer
- En-tete : compteurs (actifs / en retard / en pause / termines)
- Table avec colonnes : Serie | Tome | Editeur | Date JP | Etape courante | Progression (6 pastilles colorees) | Depuis (jours) | Relances | Action
- Pastilles de progression : grise (en attente), verte (fait), orange (en cours)
- Bouton "Creer workflow" disponible aussi depuis l'onglet Volumes (pour les volumes existants sans workflow)
- Donnees lues depuis `d.workflow` dans manga_collection.json, enrichies des completions locales Gist

### Export dans manga_collection.json

app.py exporte le workflow dans le JSON :
```json
{
  "workflow": {
    "B0CXYZ1234": {
      "etape_courante": "draft_ad",
      "date_declenchement": "2026-02-20",
      "jours_ecoules": 6,
      "etapes_faites": ["mail_nwk"],
      "nb_relances": 0,
      "date_sortie_jp": "2026-02-04",
      "editeur": "Shueisha"
    }
  }
}
```

### Variables .env requises

```
EMAIL_DESTINATAIRE_WORKFLOW=e.morterol@vega-livres.fr
IMAP_MOT_DE_PASSE=   # Vide = fallback .eml. Remplir avec le mdp app M365 pour IMAP APPEND
```

### Constante ETAPES_WORKFLOW

Definie dans database.py au niveau module (accessible partout) :
```python
ETAPES_WORKFLOW = ['mail_nwk', 'draft_ad', 'reponse_nwk', 'contrat_ad', 'signature_nwk', 'facture']
```

### Points d'attention

- Le systeme est concu pour ne JAMAIS envoyer d'email automatiquement — toujours un brouillon a valider
- Si le meme ASIN est redetecte (par ex. precommande qui passe en stock), INSERT OR IGNORE evite la duplication
- Le delai par defaut de relance est 10 jours (`delai_jours=10` dans `get_actions_en_retard`)
- La colonne `email_ouverture_envoye` est mise a 1 apres le premier email, pour eviter les doublons au run suivant
- `editeur` dans suivi_editorial est en romaji (ex: "Shueisha"), pas en japonais — utiliser `_editeur_romaji()` pour la conversion
