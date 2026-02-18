# MangaVega Tracker V7

Surveillance automatique des nouveautés manga/LN sur Amazon Japon, avec synchronisation viewer HTML via GitHub Gist.

## Structure

```
├── app.py               ← Point d'entrée (python app.py)
├── config.py            ← Configuration, constantes, globals
├── utils.py             ← Fonctions utilitaires pures
├── database.py          ← Gestionnaire SQLite
├── scraper.py           ← HTTP Amazon + extraction HTML
├── sync.py              ← Synchronisation Gist ↔ fichiers locaux
├── notifications.py     ← Envoi d'emails
├── pipeline.py          ← Logique de recherche (le cœur)
├── mangas_liste.json    ← Liste des 55 séries à surveiller
├── .env.example         ← Modèle des variables d'environnement
├── docs/                ← Documentation
│   ├── GUIDE_INSTALLATION.md
│   └── BONNES_PRATIQUES.md
├── manga_alerts.db      ← Base de données SQLite (générée)
├── manga_collection.json← Résultats du scan (généré, lu par le viewer)
└── manga_tracker.log    ← Log du dernier scan (généré)
```

## Prérequis

- Python 3.10+
- `pip install -r requirements.txt`

## Configuration

1. Copiez le modèle : `copy .env.example .env`
2. Remplissez vos identifiants dans le fichier `.env`
3. Voir `docs/GUIDE_INSTALLATION.md` pour le pas à pas complet

## Lancement

```bash
python app.py
```

Ou double-cliquez sur `mangavega_scan.bat` (Windows).

## Documentation

- **[Guide d'installation](docs/GUIDE_INSTALLATION.md)** — mise en place pas à pas
- **[Bonnes pratiques](docs/BONNES_PRATIQUES.md)** — règles de sécurité et conventions
