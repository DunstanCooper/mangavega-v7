#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MangaVega Tracker - Gestionnaire de base de données SQLite
"""

import os
import sqlite3
from datetime import datetime, date
from typing import Optional, List, Dict, Set

import config
from utils import normaliser_editeur

logger = config.logger

_DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'manga_alerts.db')


class Database:
    def __init__(self, db_path: str = _DEFAULT_DB_PATH):
        self.db_path = db_path
        self.init_db()
        self.init_table_volumes()
        self.init_table_editeurs()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=30)

    # ------------------------------------------------------------------
    # init_db
    # ------------------------------------------------------------------

    def init_db(self):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS alertes (
                    nom TEXT,
                    url TEXT,
                    date TEXT,
                    PRIMARY KEY (nom, url)
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS traductions (
                    titre_japonais TEXT PRIMARY KEY,
                    titre_francais TEXT,
                    date_ajout TEXT,
                    source TEXT DEFAULT 'unknown',
                    est_officielle INTEGER DEFAULT 0,
                    derniere_verification TEXT
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS verifications_cache (
                    asin TEXT PRIMARY KEY,
                    date_verification TEXT,
                    date_sortie TEXT,
                    tome TEXT,
                    titre TEXT,
                    editeur TEXT
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS statuts_manuels (
                    asin TEXT PRIMARY KEY,
                    statut TEXT DEFAULT 'non_traite',
                    commentaire TEXT,
                    date_modification TEXT
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS volume_serie_override (
                    asin TEXT PRIMARY KEY,
                    serie_alternative TEXT,
                    date_modification TEXT
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS featured_history (
                    serie TEXT NOT NULL,
                    asin TEXT NOT NULL,
                    statut TEXT NOT NULL,
                    source TEXT,
                    titre TEXT,
                    asin_papier TEXT,
                    date_vu TEXT,
                    PRIMARY KEY (serie, asin)
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS featured_progression (
                    serie TEXT PRIMARY KEY,
                    derniere_page INTEGER DEFAULT 1,
                    exploration_complete INTEGER DEFAULT 0,
                    date_maj TEXT
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS suivi_editorial (
                    asin TEXT NOT NULL,
                    serie_jp TEXT NOT NULL,
                    tome INTEGER,
                    etape TEXT NOT NULL,
                    statut TEXT DEFAULT 'en_attente',
                    date_declenchement TEXT NOT NULL,
                    date_completion TEXT,
                    nb_relances INTEGER DEFAULT 0,
                    pause_jusqu_au TEXT,
                    email_ouverture_envoye INTEGER DEFAULT 0,
                    date_sortie_jp TEXT,
                    editeur TEXT,
                    PRIMARY KEY (asin, etape)
                )
            """)

            conn.commit()

            # Migrations for suivi_editorial (existing DBs)
            for migration in [
                'ALTER TABLE suivi_editorial ADD COLUMN pause_jusqu_au TEXT',
                'ALTER TABLE suivi_editorial ADD COLUMN email_ouverture_envoye INTEGER DEFAULT 0',
                'ALTER TABLE suivi_editorial ADD COLUMN date_sortie_jp TEXT',
                'ALTER TABLE suivi_editorial ADD COLUMN editeur TEXT',
            ]:
                try:
                    c.execute(migration)
                    conn.commit()
                except sqlite3.OperationalError:
                    pass  # Column already exists

        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Volume serie override
    # ------------------------------------------------------------------

    def set_volume_serie_override(self, asin: str, serie_alternative: str):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                'INSERT OR REPLACE INTO volume_serie_override (asin, serie_alternative, date_modification) VALUES (?, ?, ?)',
                (asin, serie_alternative, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            )
            conn.commit()
        finally:
            conn.close()

    def get_all_volume_serie_overrides(self) -> Dict[str, str]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute('SELECT asin, serie_alternative FROM volume_serie_override')
            return {row[0]: row[1] for row in c.fetchall()}
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Alertes
    # ------------------------------------------------------------------

    def get_alertes_existantes(self, nom: str) -> Set[str]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute('SELECT url FROM alertes WHERE nom = ?', (nom,))
            return {row[0] for row in c.fetchall()}
        finally:
            conn.close()

    def marquer_comme_alerte(self, nom: str, url: str, date_str: str):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                'INSERT OR IGNORE INTO alertes (nom, url, date) VALUES (?, ?, ?)',
                (nom, url, date_str)
            )
            conn.commit()
        finally:
            conn.close()

    def get_alerte_date(self, nom: str, url: str) -> Optional[str]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute('SELECT date FROM alertes WHERE nom = ? AND url = ?', (nom, url))
            row = c.fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def update_alerte_date(self, nom: str, url: str, new_date: str):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                'UPDATE alertes SET date = ? WHERE nom = ? AND url = ?',
                (new_date, nom, url)
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Traductions
    # ------------------------------------------------------------------

    def get_traduction_info(self, titre_japonais: str) -> Optional[Dict]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                'SELECT titre_francais, source, est_officielle, derniere_verification FROM traductions WHERE titre_japonais = ?',
                (titre_japonais,)
            )
            row = c.fetchone()
            if row:
                return {
                    'titre_francais': row[0],
                    'source': row[1],
                    'est_officielle': row[2],
                    'derniere_verification': row[3],
                }
            return {
                'titre_francais': None,
                'source': 'unknown',
                'est_officielle': 0,
                'derniere_verification': None,
            }
        finally:
            conn.close()

    def sauvegarder_traduction(self, titre_japonais: str, titre_francais: str, source: str, est_officielle: int):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute(
                """INSERT OR REPLACE INTO traductions
                (titre_japonais, titre_francais, date_ajout, source, est_officielle, derniere_verification)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (titre_japonais, titre_francais, now, source, est_officielle, now)
            )
            conn.commit()
            type_str = '🇫🇷 officielle' if est_officielle else '🌍 fallback'
            logger.info('    💾 Traduction sauvegardée (' + type_str + ', source: ' + source + ')')
        finally:
            conn.close()

    def marquer_verification_traduction(self, titre_japonais: str):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute(
                'UPDATE traductions SET derniere_verification = ? WHERE titre_japonais = ?',
                (now, titre_japonais)
            )
            conn.commit()
        finally:
            conn.close()

    def get_traductions_non_officielles(self) -> List[Dict]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                'SELECT titre_japonais, titre_francais, source, derniere_verification FROM traductions WHERE est_officielle = 0'
            )
            return [
                {
                    'titre_japonais': row[0],
                    'titre_francais': row[1],
                    'source': row[2],
                    'derniere_verification': row[3],
                }
                for row in c.fetchall()
            ]
        finally:
            conn.close()

    def get_traduction_complete(self, titre_japonais: str) -> Optional[Dict]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                'SELECT titre_francais, source, est_officielle, derniere_verification FROM traductions WHERE titre_japonais = ?',
                (titre_japonais,)
            )
            row = c.fetchone()
            if row:
                return {
                    'titre_francais': row[0],
                    'source': row[1],
                    'est_officielle': row[2],
                    'derniere_verification': row[3],
                }
            return None
        finally:
            conn.close()

    def sauvegarder_traduction_complete(self, titre_japonais: str, titre_francais: str, source: str, est_officielle: int):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                'SELECT titre_francais FROM traductions WHERE titre_japonais = ?',
                (titre_japonais,)
            )
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute(
                """INSERT OR REPLACE INTO traductions
                (titre_japonais, titre_francais, date_ajout, source, est_officielle, derniere_verification)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (titre_japonais, titre_francais, now, source, est_officielle, now)
            )
            conn.commit()
        finally:
            conn.close()

    def get_series_sans_traduction(self) -> List[str]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("""
                SELECT DISTINCT v.serie_jp
                FROM volumes v
                WHERE (v.serie_fr IS NULL OR v.serie_fr = '')
                AND NOT EXISTS (
                    SELECT 1 FROM traductions t
                    WHERE (t.titre_japonais = v.serie_jp
                        OR t.titre_japonais = REPLACE(REPLACE(v.serie_jp, ' [LN]', ''), ' [MANGA]', ''))
                )
            """)
            return [row[0] for row in c.fetchall()]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Verifications cache
    # ------------------------------------------------------------------

    def est_verifie_aujourdhui(self, asin: str) -> Optional[Dict]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                'SELECT date_sortie, tome, titre, editeur FROM verifications_cache WHERE asin = ?',
                (asin,)
            )
            row = c.fetchone()
            if not row:
                return None
            if row[1] == 'N/A':
                return None
            return {
                'date': row[0],
                'tome': row[1],
                'titre': row[2],
                'editeur': row[3],
            }
        finally:
            conn.close()

    def get_verification_cache(self, asin: str) -> Optional[Dict]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                'SELECT date_sortie, tome, titre, editeur FROM verifications_cache WHERE asin = ?',
                (asin,)
            )
            row = c.fetchone()
            if not row:
                return None
            return {
                'date': row[0],
                'tome': row[1],
                'titre': row[2],
                'editeur': row[3],
            }
        finally:
            conn.close()

    def sauvegarder_verification(self, asin: str, date_sortie: str, tome, titre: str, editeur: str = None):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute(
                """INSERT OR REPLACE INTO verifications_cache
                (asin, date_verification, date_sortie, tome, titre, editeur)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (asin, now, date_sortie, tome, titre, editeur)
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Volumes table
    # ------------------------------------------------------------------

    def init_table_volumes(self):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS volumes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    serie_jp TEXT NOT NULL,
                    tome INTEGER,
                    asin TEXT UNIQUE NOT NULL,
                    url TEXT,
                    date_ajout TEXT,
                    date_maj TEXT,
                    editeur TEXT
                )
            """)
            conn.commit()

            # Migrations for volumes columns
            for migration in [
                'ALTER TABLE volumes ADD COLUMN serie_fr TEXT',
                'ALTER TABLE volumes ADD COLUMN date_sortie_jp TEXT',
                'ALTER TABLE volumes ADD COLUMN titre_volume TEXT',
            ]:
                try:
                    c.execute(migration)
                    conn.commit()
                except sqlite3.OperationalError:
                    pass  # Column already exists

            # Indexes (created after migrations so serie_fr column exists)
            for idx_sql in [
                'CREATE INDEX IF NOT EXISTS idx_volumes_serie_jp ON volumes (serie_jp)',
                'CREATE INDEX IF NOT EXISTS idx_volumes_serie_fr ON volumes (serie_fr)',
                'CREATE INDEX IF NOT EXISTS idx_volumes_asin ON volumes (asin)',
            ]:
                try:
                    c.execute(idx_sql)
                    conn.commit()
                except sqlite3.OperationalError:
                    pass

        finally:
            conn.close()

    def get_volumes_connus(self, serie_jp: str) -> Dict[str, str]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                'SELECT asin, url FROM volumes WHERE serie_jp = ? ORDER BY tome IS NULL, CAST(tome AS REAL) ASC',
                (serie_jp,)
            )
            return {row[0]: row[1] for row in c.fetchall()}
        finally:
            conn.close()

    def sauvegarder_volume(self, serie_jp: str, serie_fr: str, tome, asin: str, url: str,
                           date_sortie_jp: str, titre_volume: str, editeur: str):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute('SELECT id, serie_fr, editeur FROM volumes WHERE asin = ?', (asin,))
            row = c.fetchone()
            if row:
                c.execute("""
                    UPDATE volumes SET serie_jp = ?, serie_fr = ?, tome = ?, url = ?,
                    date_sortie_jp = ?, titre_volume = ?, date_maj = ?, editeur = ?
                    WHERE asin = ?
                """, (serie_jp, serie_fr, tome, url, date_sortie_jp, titre_volume, now, editeur, asin))
            else:
                c.execute(
                    """INSERT INTO volumes
                    (serie_jp, serie_fr, tome, asin, url, date_sortie_jp, titre_volume, date_ajout, date_maj, editeur)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (serie_jp, serie_fr, tome, asin, url, date_sortie_jp, titre_volume, now, now, editeur)
                )
            conn.commit()
        finally:
            conn.close()

    def update_tome_volume(self, asin: str, tome):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute('UPDATE volumes SET tome = ?, date_maj = ? WHERE asin = ?', (tome, now, asin))
            c.execute('UPDATE verifications_cache SET tome = ? WHERE asin = ?', (tome, asin))
            conn.commit()
            logger.info('   📝 Tome mis à jour: ' + asin + ' → T' + str(tome))
        finally:
            conn.close()

    def get_volumes_valides_sans_tome(self) -> List[Dict]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("""
                SELECT v.asin, v.serie_jp, v.url, v.titre_volume
                FROM volumes v
                JOIN statuts_manuels s ON v.asin = s.asin
                WHERE s.statut = 'valide'
                AND (v.tome IS NULL OR v.tome = 0 OR v.tome = -1)
            """)
            return [
                {'asin': row[0], 'serie_jp': row[1], 'url': row[2], 'titre_volume': row[3]}
                for row in c.fetchall()
            ]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Featured history
    # ------------------------------------------------------------------

    def get_featured_history_asins(self, serie: str, filtre: str = '') -> Set[str]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            if filtre == 'ln_only':
                c.execute(
                    "SELECT asin FROM featured_history WHERE serie = ? AND NOT (statut = 'ebook' AND asin_papier IS NULL)",
                    (serie,)
                )
            else:
                c.execute('SELECT asin FROM featured_history WHERE serie = ?', (serie,))
            return {row[0] for row in c.fetchall()}
        finally:
            conn.close()

    def sauvegarder_featured(self, serie: str, asin: str, statut: str, source: str,
                              titre: str = None, asin_papier: str = None):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute(
                """INSERT OR REPLACE INTO featured_history
                (serie, asin, statut, source, titre, asin_papier, date_vu)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (serie, asin, statut, source, titre, asin_papier, now)
            )
            conn.commit()
        finally:
            conn.close()

    def get_featured_stats(self, serie: str) -> Dict[str, int]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                'SELECT statut, COUNT(*) FROM featured_history WHERE serie = ? GROUP BY statut',
                (serie,)
            )
            return {row[0]: row[1] for row in c.fetchall()}
        finally:
            conn.close()

    def get_featured_progression(self, serie: str):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                'SELECT derniere_page, exploration_complete FROM featured_progression WHERE serie = ?',
                (serie,)
            )
            row = c.fetchone()
            if row:
                return (row[0], bool(row[1]))
            return (0, False)
        finally:
            conn.close()

    def set_featured_progression(self, serie: str, page: int, complete: bool = False):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            complete_int = 1 if complete else 0
            c.execute("""
                INSERT INTO featured_progression (serie, derniere_page, exploration_complete, date_maj)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(serie) DO UPDATE SET
                    derniere_page = ?, exploration_complete = ?, date_maj = ?
            """, (serie, page, complete_int, now, page, complete_int, now))
            conn.commit()
        finally:
            conn.close()

    def migrer_ebooks_vers_featured_history(self):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ebooks_traites'")
            if not c.fetchone():
                return

            c.execute('SELECT COUNT(*) FROM featured_history')
            c.fetchone()

            c.execute('SELECT COUNT(*) FROM ebooks_traites')
            count_ebooks = c.fetchone()[0]

            if count_ebooks > 0:
                c.execute("""
                    INSERT OR IGNORE INTO featured_history
                    (serie, asin, statut, source, titre, asin_papier, date_vu)
                    SELECT manga_nom, asin_ebook, 'ebook', 'migration', NULL, asin_papier, date_traitement
                    FROM ebooks_traites
                """)
                conn.commit()

            c.execute('DROP TABLE ebooks_traites')
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Editeurs
    # ------------------------------------------------------------------

    def init_table_editeurs(self):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS series_editeurs (
                    serie_id TEXT PRIMARY KEY,
                    editeur_officiel TEXT,
                    date_detection TEXT,
                    nb_volumes_detectes INTEGER DEFAULT 0,
                    derniere_recherche TEXT
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def get_editeur_officiel(self, serie_id: str) -> Optional[str]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute('SELECT editeur_officiel FROM series_editeurs WHERE serie_id = ?', (serie_id,))
            row = c.fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def set_editeur_officiel(self, serie_id: str, editeur: str, nb_volumes: int = 0):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute(
                """INSERT OR REPLACE INTO series_editeurs
                (serie_id, editeur_officiel, date_detection, nb_volumes_detectes)
                VALUES (?, ?, ?, ?)""",
                (serie_id, editeur, now, nb_volumes)
            )
            conn.commit()
            logger.info('    📚 Éditeur officiel défini: ' + editeur + ' pour ' + serie_id)
        finally:
            conn.close()

    def get_editeur_majoritaire(self, serie_id: str, valides_seulement: bool = False) -> Optional[str]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            if valides_seulement:
                c.execute("""
                    SELECT v.editeur, COUNT(*) as nb
                    FROM volumes v
                    INNER JOIN statuts_manuels s ON v.asin = s.asin AND s.statut = 'valide'
                    WHERE v.serie_jp = ? AND v.editeur IS NOT NULL AND v.editeur != ''
                    GROUP BY v.editeur
                    ORDER BY nb DESC LIMIT 1
                """, (serie_id,))
            else:
                c.execute("""
                    SELECT editeur, COUNT(*) as nb
                    FROM volumes
                    WHERE serie_jp = ? AND editeur IS NOT NULL AND editeur != ''
                    GROUP BY editeur
                    ORDER BY nb DESC
                    LIMIT 1
                """, (serie_id,))
            row = c.fetchone()
            if row:
                return normaliser_editeur(row[0])
            return None
        finally:
            conn.close()

    def detecter_et_sauvegarder_editeur_officiel(self, serie_id: str, nb_volumes: int = 0) -> Optional[str]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                "SELECT COUNT(*) FROM volumes v INNER JOIN statuts_manuels s ON v.asin = s.asin AND s.statut = 'valide' WHERE v.serie_jp = ?",
                (serie_id,)
            )
            nb_valides = c.fetchone()[0]
        finally:
            conn.close()

        if nb_valides > 0:
            editeur = self.get_editeur_majoritaire(serie_id, valides_seulement=True)
            if editeur:
                editeur_existant = self.get_editeur_officiel(serie_id)
                if editeur != editeur_existant:
                    self.set_editeur_officiel(serie_id, editeur, nb_volumes)
                    logger.info('    📚 Éditeur mis à jour par validation: ' + editeur)
                return editeur

        editeur_existant = self.get_editeur_officiel(serie_id)
        if editeur_existant:
            return editeur_existant

        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                'SELECT COUNT(*) FROM volumes WHERE serie_jp = ? AND editeur IS NOT NULL',
                (serie_id,)
            )
            nb_avec_editeur = c.fetchone()[0]
        finally:
            conn.close()

        if nb_avec_editeur > 0:
            editeur = self.get_editeur_majoritaire(serie_id, valides_seulement=False)
            if editeur:
                self.set_editeur_officiel(serie_id, editeur, nb_volumes)
                return editeur

        return None

    # ------------------------------------------------------------------
    # Statuts manuels
    # ------------------------------------------------------------------

    def set_statut_manuel(self, asin: str, statut: str, commentaire: str = None):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute(
                'INSERT OR REPLACE INTO statuts_manuels (asin, statut, commentaire, date_modification) VALUES (?, ?, ?, ?)',
                (asin, statut, commentaire, now)
            )
            conn.commit()
        finally:
            conn.close()

    def get_asins_rejetes(self) -> Set[str]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT asin FROM statuts_manuels WHERE statut = 'rejete'")
            return {row[0] for row in c.fetchall()}
        finally:
            conn.close()

    def get_asins_valides(self) -> Set[str]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT asin FROM statuts_manuels WHERE statut = 'valide'")
            return {row[0] for row in c.fetchall()}
        finally:
            conn.close()

    def get_asin_reference(self, serie_jp: str) -> Optional[str]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("""
                SELECT v.asin
                FROM volumes v
                JOIN statuts_manuels s ON v.asin = s.asin
                WHERE v.serie_jp = ? AND s.statut = 'valide'
                ORDER BY v.tome DESC
                LIMIT 1
            """, (serie_jp,))
            row = c.fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def importer_statuts_json(self, filepath: str) -> Dict:
        import json
        counts = {'rejetes': 0, 'valides': 0, 'overrides': 0, 'scissions': 0}
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if 'hors_sujet' in data:
            for asin in data['hors_sujet']:
                self.set_statut_manuel(asin, 'rejete')
                counts['rejetes'] += 1

        if 'commentaires' in data:
            for asin, comment in data['commentaires'].items():
                self.set_statut_manuel(asin, 'rejete', comment)
                counts['rejetes'] += 1

        if 'rejetes' in data:
            for asin in data['rejetes']:
                self.set_statut_manuel(asin, 'rejete')
                counts['rejetes'] += 1

        if 'valides' in data:
            for asin in data['valides']:
                self.set_statut_manuel(asin, 'valide')
                counts['valides'] += 1

        overrides_key = 'volume_serie_override' if 'volume_serie_override' in data else 'overrides'
        if overrides_key in data:
            for asin, serie in data[overrides_key].items():
                self.set_volume_serie_override(asin, serie)
                counts['overrides'] += 1

        scissions_key = 'series_scindees' if 'series_scindees' in data else 'scissions'
        if scissions_key in data:
            for entry in data[scissions_key]:
                manga_nom = entry.get('manga_nom')
                nouveau_nom = entry.get('nouveau_nom')
                if manga_nom and nouveau_nom:
                    asins = self.get_asins_serie(manga_nom)
                    for asin in asins:
                        self.set_volume_serie_override(asin, nouveau_nom)
                        counts['scissions'] += 1

        return counts

    # ------------------------------------------------------------------
    # Suivi editorial - workflow
    # ------------------------------------------------------------------

    ETAPES_WORKFLOW = ['mail_nwk', 'draft_ad', 'reponse_nwk', 'contrat_ad', 'signature_nwk', 'facture']

    LABELS_ETAPES = {
        'mail_nwk': 'Mail NWK \u2192 offre \u00e9diteur JP',
        'draft_ad': 'R\u00e9ception draft Ayants Droits',
        'reponse_nwk': 'R\u00e9ponse NWK au draft',
        'contrat_ad': 'R\u00e9ception contrat \u00e0 signer',
        'signature_nwk': 'NWK signe + archive',
        'facture': 'R\u00e9ception + paiement facture',
    }

    def creer_workflow_volume(self, asin: str, serie_jp: str, tome, today: str, editeur: str = '', date_sortie_jp: str = ''):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                """INSERT OR IGNORE INTO suivi_editorial
                (asin, serie_jp, tome, etape, statut, date_declenchement, nb_relances, date_sortie_jp, editeur)
                VALUES (?, ?, ?, 'mail_nwk', 'en_attente', ?, 0, ?, ?)""",
                (asin, serie_jp, tome, today, date_sortie_jp or today, editeur)
            )
            conn.commit()
            logger.info('   \U0001f4d1 Workflow cr\u00e9\u00e9: ' + serie_jp[:30] + ' T' + str(tome) + ' [' + asin + ']')
        finally:
            conn.close()

    def creer_workflow_depuis_asin(self, asin: str, today: str):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute('SELECT serie_jp, tome, date_sortie_jp, editeur FROM volumes WHERE asin = ?', (asin,))
            row = c.fetchone()
        finally:
            conn.close()

        if not row:
            logger.warning('   \u26a0\ufe0f  Workflow init ignor\u00e9: ASIN ' + asin + ' introuvable en BDD')
            return
        serie_jp, tome = row[0], row[1]
        date_sortie_jp = row[2] or ''
        editeur = row[3] or ''
        self.creer_workflow_volume(asin, serie_jp, tome, today, editeur, date_sortie_jp)

    def get_etape_courante_workflow(self, asin: str) -> Optional[Dict]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("""
                SELECT etape, statut, date_declenchement, date_completion, nb_relances, serie_jp, tome
                FROM suivi_editorial
                WHERE asin = ? AND statut = 'en_attente'
                ORDER BY CASE etape
                    WHEN 'mail_nwk'      THEN 1
                    WHEN 'draft_ad'      THEN 2
                    WHEN 'reponse_nwk'   THEN 3
                    WHEN 'contrat_ad'    THEN 4
                    WHEN 'signature_nwk' THEN 5
                    WHEN 'facture'       THEN 6
                    ELSE 99
                END
                LIMIT 1
            """, (asin,))
            row = c.fetchone()
            if not row:
                return None
            etape = row[0]
            date_declenchement = row[2]
            jours_ecoules = 0
            if date_declenchement:
                try:
                    d = datetime.strptime(date_declenchement[:10], '%Y-%m-%d').date()
                    jours_ecoules = (date.today() - d).days
                except (ValueError, TypeError):
                    pass
            return {
                'etape': etape,
                'statut': row[1],
                'date_declenchement': date_declenchement,
                'date_completion': row[3],
                'nb_relances': row[4],
                'serie_jp': row[5],
                'tome': row[6],
                'jours_ecoules': jours_ecoules,
            }
        finally:
            conn.close()

    def _get_etapes_faites(self, asin: str) -> List[str]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                "SELECT etape FROM suivi_editorial WHERE asin = ? AND statut = 'fait'",
                (asin,)
            )
            return [row[0] for row in c.fetchall()]
        finally:
            conn.close()

    def marquer_etape_faite(self, asin: str, etape: str, date_completion: str):
        conn = self._get_conn()
        try:
            c = conn.cursor()

            # Idempotency check
            c.execute(
                'SELECT statut, date_completion FROM suivi_editorial WHERE asin = ? AND etape = ?',
                (asin, etape)
            )
            row = c.fetchone()
            if row and row[0] == 'fait' and row[1] == date_completion:
                return

            # Mark current step as fait
            c.execute(
                "UPDATE suivi_editorial SET statut = 'fait', date_completion = ? WHERE asin = ? AND etape = ?",
                (date_completion, asin, etape)
            )

            # Get base info for serie_jp and tome
            c.execute('SELECT serie_jp, tome FROM suivi_editorial WHERE asin = ? LIMIT 1', (asin,))
            base = c.fetchone()
            if not base:
                conn.commit()
                return
            serie_jp, tome = base[0], base[1]

            # Ensure the step row is correct (handles wrong-statut edge cases)
            c.execute(
                'SELECT date_declenchement FROM suivi_editorial WHERE asin = ? AND etape = ?',
                (asin, etape)
            )
            existing = c.fetchone()
            date_declenchement = existing[0] if existing else date_completion
            c.execute(
                """INSERT OR REPLACE INTO suivi_editorial
                (asin, serie_jp, tome, etape, statut, date_declenchement, date_completion, nb_relances)
                VALUES (?, ?, ?, ?, 'fait', ?, ?, 0)""",
                (asin, serie_jp, tome, etape, date_declenchement, date_completion)
            )

            # Create next step if applicable
            if etape in self.ETAPES_WORKFLOW:
                idx = self.ETAPES_WORKFLOW.index(etape)
                if idx + 1 < len(self.ETAPES_WORKFLOW):
                    etape_suivante = self.ETAPES_WORKFLOW[idx + 1]
                    c.execute(
                        'SELECT 1 FROM suivi_editorial WHERE asin = ? AND etape = ?',
                        (asin, etape_suivante)
                    )
                    if not c.fetchone():
                        c.execute(
                            """INSERT INTO suivi_editorial
                            (asin, serie_jp, tome, etape, statut, date_declenchement, nb_relances)
                            VALUES (?, ?, ?, ?, 'en_attente', ?, 0)""",
                            (asin, serie_jp, tome, etape_suivante, date_completion)
                        )
                        logger.info('   \U0001f4d1 \u00c9tape suivante cr\u00e9\u00e9e: ' + etape_suivante + ' pour [' + asin + ']')

            conn.commit()
        finally:
            conn.close()

    def get_actions_en_retard(self, delai_jours: int = 10) -> List[Dict]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("""
                SELECT s.asin, s.serie_jp, s.tome, s.etape, s.date_declenchement, s.nb_relances,
                       COALESCE(t.titre_francais, s.serie_jp) as nom_fr,
                       COALESCE(s.editeur, se.editeur_officiel, '') as editeur
                FROM suivi_editorial s
                LEFT JOIN traductions t ON (
                    t.titre_japonais = s.serie_jp
                    OR t.titre_japonais = REPLACE(REPLACE(s.serie_jp, ' [LN]', ''), ' [MANGA]', '')
                )
                LEFT JOIN series_editeurs se ON se.serie_id = s.serie_jp
                WHERE s.statut = 'en_attente'
                AND date(s.date_declenchement, '+' || ? || ' days') < date('now')
                AND (s.pause_jusqu_au IS NULL OR date(s.pause_jusqu_au) < date('now'))
                ORDER BY COALESCE(s.editeur, se.editeur_officiel) ASC, s.date_declenchement ASC
            """, (delai_jours,))
            results = []
            for row in c.fetchall():
                asin = row[0]
                serie_jp = row[1]
                tome = row[2]
                etape = row[3]
                date_declenchement = row[4]
                nb_relances = row[5]
                nom_fr = row[6]
                editeur = row[7]
                jours_ecoules = 0
                if date_declenchement:
                    try:
                        d = datetime.strptime(date_declenchement[:10], '%Y-%m-%d').date()
                        jours_ecoules = (date.today() - d).days
                    except (ValueError, TypeError):
                        pass
                results.append({
                    'asin': asin,
                    'serie_jp': serie_jp,
                    'nom_fr': nom_fr,
                    'editeur': editeur,
                    'tome': tome,
                    'etape': etape,
                    'label': self.LABELS_ETAPES.get(etape, etape),
                    'date_declenchement': date_declenchement,
                    'jours_ecoules': jours_ecoules,
                    'nb_relances': nb_relances,
                })
            return results
        finally:
            conn.close()

    def incrementer_relances(self, asin: str, etape: str):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                'UPDATE suivi_editorial SET nb_relances = nb_relances + 1 WHERE asin = ? AND etape = ?',
                (asin, etape)
            )
            conn.commit()
        finally:
            conn.close()

    def get_tous_workflows_actifs(self) -> Dict[str, Dict]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("""
                SELECT s.asin, s.etape, s.date_declenchement, s.nb_relances, s.pause_jusqu_au,
                       COALESCE(NULLIF(v.date_sortie_jp, ''), NULLIF(m.date_sortie_jp, ''), '') as date_sortie_jp,
                       COALESCE(NULLIF(v.editeur, ''), NULLIF(m.editeur, ''), NULLIF(s.editeur, ''), '') as editeur
                FROM suivi_editorial s
                LEFT JOIN suivi_editorial m ON m.asin = s.asin AND m.etape = 'mail_nwk'
                LEFT JOIN volumes v ON v.asin = s.asin
                WHERE s.statut = 'en_attente'
            """)
            rows = c.fetchall()
        finally:
            conn.close()

        # Keep only the earliest (by ETAPES_WORKFLOW order) en_attente step per asin
        order_map = {e: i for i, e in enumerate(self.ETAPES_WORKFLOW)}
        asin_best: Dict[str, tuple] = {}
        for row in rows:
            asin = row[0]
            etape = row[1]
            etape_order = order_map.get(etape, 99)
            if asin not in asin_best or etape_order < asin_best[asin][0]:
                asin_best[asin] = (etape_order, row)

        result: Dict[str, Dict] = {}
        for asin, (_, row) in asin_best.items():
            etape = row[1]
            date_declenchement = row[2]
            nb_relances = row[3]
            pause_jusqu_au = row[4]
            date_sortie_jp = row[5]
            editeur = row[6]
            jours_ecoules = 0
            if date_declenchement:
                try:
                    d = datetime.strptime(date_declenchement[:10], '%Y-%m-%d').date()
                    jours_ecoules = (date.today() - d).days
                except (ValueError, TypeError):
                    pass
            etapes_faites = self._get_etapes_faites(asin)
            result[asin] = {
                'etape_courante': etape,
                'label': self.LABELS_ETAPES.get(etape, etape),
                'date_declenchement': date_declenchement,
                'jours_ecoules': jours_ecoules,
                'nb_relances': nb_relances,
                'etapes_faites': etapes_faites,
                'pause_jusqu_au': pause_jusqu_au,
                'date_sortie_jp': date_sortie_jp,
                'editeur': editeur,
            }
        return result

    def marquer_relance_faite(self, asin: str, etape: str, date_relance: str):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                "SELECT date_declenchement FROM suivi_editorial WHERE asin=? AND etape=? AND statut='en_attente'",
                (asin, etape)
            )
            row = c.fetchone()
            if row and row[0] != date_relance:
                c.execute(
                    "UPDATE suivi_editorial SET date_declenchement = ?, nb_relances = nb_relances + 1 WHERE asin = ? AND etape = ? AND statut = 'en_attente'",
                    (date_relance, asin, etape)
                )
                conn.commit()
            logger.info('   \U0001f4e8 Relance not\u00e9e [' + asin + '] \u00e9tape ' + etape + ' le ' + date_relance + ' \u2192 compteur 10j remis \u00e0 z\u00e9ro')
        finally:
            conn.close()

    def get_workflows_a_notifier(self, today: str) -> List[Dict]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("""
                SELECT s.asin, s.serie_jp, s.tome, s.date_declenchement,
                       COALESCE(t.titre_francais, s.serie_jp) as nom_fr,
                       COALESCE(s.editeur, se.editeur_officiel, '') as editeur
                FROM suivi_editorial s
                LEFT JOIN traductions t ON (
                    t.titre_japonais = s.serie_jp
                    OR t.titre_japonais = REPLACE(REPLACE(s.serie_jp, ' [LN]', ''), ' [MANGA]', '')
                )
                LEFT JOIN series_editeurs se ON se.serie_id = s.serie_jp
                WHERE s.etape = 'mail_nwk'
                AND s.statut = 'en_attente'
                AND date(s.date_declenchement) <= date(?)
                AND s.email_ouverture_envoye = 0
                ORDER BY COALESCE(s.editeur, se.editeur_officiel) ASC, s.date_declenchement ASC
            """, (today,))
            results = []
            for row in c.fetchall():
                results.append({
                    'asin': row[0],
                    'serie_jp': row[1],
                    'tome': row[2],
                    'date_sortie_jp': row[3],
                    'nom_fr': row[4],
                    'editeur': row[5],
                })
            return results
        finally:
            conn.close()

    def marquer_email_ouverture_envoye(self, asin: str):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                "UPDATE suivi_editorial SET email_ouverture_envoye = 1 WHERE asin = ? AND etape = 'mail_nwk'",
                (asin,)
            )
            conn.commit()
        finally:
            conn.close()

    def definir_pause_workflow(self, asin: str, etape: str, date_pause: str):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                "UPDATE suivi_editorial SET pause_jusqu_au = ? WHERE asin = ? AND etape = ? AND statut = 'en_attente'",
                (date_pause, asin, etape)
            )
            conn.commit()
            logger.info('   \u23f8 Pause workflow [' + asin + '] \u00e9tape ' + etape + " jusqu'au " + date_pause)
        finally:
            conn.close()

    def effacer_pause_workflow(self, asin: str, etape: str):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                'UPDATE suivi_editorial SET pause_jusqu_au = NULL WHERE asin = ? AND etape = ?',
                (asin, etape)
            )
            conn.commit()
        finally:
            conn.close()

    def get_pauses_expirees(self) -> List[Dict]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("""
                SELECT asin, serie_jp, tome, etape, date_declenchement, nb_relances, pause_jusqu_au
                FROM suivi_editorial
                WHERE statut = 'en_attente'
                AND pause_jusqu_au IS NOT NULL
                AND date(pause_jusqu_au) <= date('now')
                ORDER BY pause_jusqu_au ASC
            """)
            results = []
            for row in c.fetchall():
                etape = row[3]
                results.append({
                    'asin': row[0],
                    'serie_jp': row[1],
                    'tome': row[2],
                    'etape': etape,
                    'label': self.LABELS_ETAPES.get(etape, etape),
                    'date_declenchement': row[4],
                    'nb_relances': row[5],
                    'pause_jusqu_au': row[6],
                })
            return results
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Utilities - series
    # ------------------------------------------------------------------

    def get_asins_serie(self, serie_jp: str) -> Set[str]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute('SELECT asin FROM volumes WHERE serie_jp = ?', (serie_jp,))
            asins = {row[0] for row in c.fetchall()}
            c.execute('SELECT asin FROM featured_history WHERE serie = ?', (serie_jp,))
            asins.update(row[0] for row in c.fetchall())
            return asins
        finally:
            conn.close()

    def purger_serie(self, serie_jp: str):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            tables = [
                ('featured_history', 'serie'),
                ('featured_progression', 'serie'),
                ('volumes', 'serie_jp'),
                ('series_editeurs', 'serie_id'),
                ('alertes', 'nom'),
                ('traductions', 'titre_japonais'),
            ]
            for table, col in tables:
                c.execute(f'DELETE FROM {table} WHERE {col} = ?', (serie_jp,))
            conn.commit()
            logger.info('   \U0001f5d1\ufe0f  Cache purg\u00e9 pour ' + serie_jp)
        finally:
            conn.close()


# Alias de compatibilité — app.py, pipeline.py et api_server.py importent DatabaseManager
DatabaseManager = Database
