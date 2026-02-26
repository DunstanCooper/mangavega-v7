#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MangaVega Tracker - Gestionnaire de base de données SQLite
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Set

import config
from utils import normaliser_editeur

logger = config.logger


class DatabaseManager:
    def __init__(self, db_path: str = "manga_alerts.db"):
        self.db_path = db_path
        self._conn = None
        self.init_db()
    
    def _get_conn(self):
        """Retourne une connexion partagée (réutilisée entre appels)"""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, timeout=15)
        return self._conn
    
    def close(self):
        """Ferme la connexion partagée"""
        if self._conn:
            self._conn.close()
            self._conn = None
    
    def init_db(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alertes (
                nom TEXT,
                url TEXT,
                date TEXT,
                PRIMARY KEY (nom, url)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS traductions (
                titre_japonais TEXT PRIMARY KEY,
                titre_francais TEXT,
                date_ajout TEXT,
                source TEXT DEFAULT 'unknown',
                est_officielle INTEGER DEFAULT 0,
                derniere_verification TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS verifications_cache (
                asin TEXT PRIMARY KEY,
                date_verification TEXT,
                date_sortie TEXT,
                tome TEXT,
                titre TEXT,
                editeur TEXT
            )
        ''')
        # NOTE: Table 'ebooks_traites' supprimée (migrée vers featured_history)
        # La migration se fait dans app.py au démarrage, puis la table est droppée
        
        # Statuts manuels des volumes (validé, rejeté, non traité)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS statuts_manuels (
                asin TEXT PRIMARY KEY,
                statut TEXT DEFAULT 'non_traite',
                commentaire TEXT,
                date_modification TEXT
            )
        ''')
        # Overrides de série (pour les volumes assignés à une série alternative)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS volume_serie_override (
                asin TEXT PRIMARY KEY,
                serie_alternative TEXT,
                date_modification TEXT
            )
        ''')
        # Historique Featured : tous les ASINs croisés dans Featured/Bulk, classifiés
        # Clé (serie, asin) pour permettre qu'un même ASIN soit classé différemment
        # selon la série (ex: un LN est "papier" pour [LN] et "hors_sujet" pour [MANGA])
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS featured_history (
                serie       TEXT NOT NULL,
                asin        TEXT NOT NULL,
                statut      TEXT NOT NULL,
                source      TEXT,
                titre       TEXT,
                asin_papier TEXT,
                date_vu     TEXT,
                PRIMARY KEY (serie, asin)
            )
        ''')
        # Progression Featured : dernière page explorée par série
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS featured_progression (
                serie                TEXT PRIMARY KEY,
                derniere_page        INTEGER DEFAULT 1,
                exploration_complete INTEGER DEFAULT 0,
                date_maj             TEXT
            )
        ''')
        # Suivi éditorial : workflow par tome (6 étapes séquentielles)
        cursor.execute('''
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
                PRIMARY KEY (asin, etape)
            )
        ''')
        conn.commit()
        # Migration : ajouter la colonne pause_jusqu_au si absente (BDD existante)
        try:
            cursor.execute("ALTER TABLE suivi_editorial ADD COLUMN pause_jusqu_au TEXT")
            conn.commit()
            logger.info("Migration BDD : colonne pause_jusqu_au ajoutée à suivi_editorial")
        except Exception:
            pass  # Colonne déjà présente
    
    def set_volume_serie_override(self, asin: str, serie_alternative: str):
        """Définit une série alternative pour un volume spécifique"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO volume_serie_override (asin, serie_alternative, date_modification)
            VALUES (?, ?, ?)
        ''', (asin, serie_alternative, datetime.now().isoformat()))
        conn.commit()
    
    
    def get_all_volume_serie_overrides(self) -> Dict[str, str]:
        """Récupère tous les overrides de série"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT asin, serie_alternative FROM volume_serie_override')
        result = {row[0]: row[1] for row in cursor.fetchall()}
        return result
    
    def get_alertes_existantes(self, nom: str) -> set:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT url FROM alertes WHERE nom = ?', (nom,))
        urls = {row[0] for row in cursor.fetchall()}
        return urls
    
    def marquer_comme_alerte(self, nom: str, url: str, date: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO alertes (nom, url, date) VALUES (?, ?, ?)', (nom, url, date))
        conn.commit()
    
    def get_alerte_date(self, nom: str, url: str) -> Optional[str]:
        """Récupère la date enregistrée d'une alerte"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT date FROM alertes WHERE nom = ? AND url = ?', (nom, url))
        result = cursor.fetchone()
        return result[0] if result else None
    
    def update_alerte_date(self, nom: str, url: str, new_date: str):
        """Met à jour la date d'une alerte existante"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('UPDATE alertes SET date = ? WHERE nom = ? AND url = ?', (new_date, nom, url))
        conn.commit()
    
    def get_traduction_info(self, titre_japonais: str) -> Optional[Dict]:
        """Récupère les infos complètes de traduction depuis la BDD"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT titre_francais, source, est_officielle, derniere_verification 
            FROM traductions WHERE titre_japonais = ?
        ''', (titre_japonais,))
        result = cursor.fetchone()
        if result:
            return {
                'titre_francais': result[0],
                'source': result[1] or 'unknown',
                'est_officielle': bool(result[2]),
                'derniere_verification': result[3]
            }
        return None
    
    def sauvegarder_traduction(self, titre_japonais: str, titre_francais: str, 
                               source: str = 'unknown', est_officielle: bool = False):
        """Sauvegarde une traduction dans la BDD avec métadonnées"""
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
            INSERT OR REPLACE INTO traductions 
            (titre_japonais, titre_francais, date_ajout, source, est_officielle, derniere_verification)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (titre_japonais, titre_francais, now, source, 1 if est_officielle else 0, now))
        conn.commit()
        
        status = "🇫🇷 officielle" if est_officielle else "🌍 fallback"
        logger.info(f"    💾 Traduction sauvegardée ({status}, source: {source}): {titre_francais}")
    
    def marquer_verification_traduction(self, titre_japonais: str):
        """Met à jour la date de dernière vérification sans changer la traduction"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE traductions SET derniere_verification = ? WHERE titre_japonais = ?
        ''', (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), titre_japonais))
        conn.commit()
    
    def get_traductions_non_officielles(self) -> List[Dict]:
        """Récupère toutes les traductions non-officielles pour re-vérification"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT titre_japonais, titre_francais, source, derniere_verification 
            FROM traductions 
            WHERE est_officielle = 0
        ''')
        results = []
        for row in cursor.fetchall():
            results.append({
                'titre_japonais': row[0],
                'titre_francais': row[1],
                'source': row[2],
                'derniere_verification': row[3]
            })
        return results
    
    def get_volumes_connus(self, serie_jp: str) -> dict:
        """Récupère les volumes connus d'une série depuis la table volumes.
        Volumes connus de cette série en BDD.
        
        Returns:
            dict: {asin: url} pour tous les volumes connus de cette série
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT asin, url FROM volumes WHERE serie_jp = ? ORDER BY tome IS NULL, CAST(tome AS INTEGER) ASC', (serie_jp,))
        return {row[0]: row[1] for row in cursor.fetchall()}
    
    # =========================================================================
    # FEATURED HISTORY — historique de tous les ASINs croisés dans Featured/Bulk
    # =========================================================================
    
    def get_featured_history_asins(self, serie: str, filtre: str = None) -> set:
        """Récupère les ASINs déjà vus dans Featured pour cette série.
        
        Pour les séries ln_only : exclut les ebooks qui n'ont PAS encore de résultat
        de recherche papier LN (asin_papier NULL et pas marqué 'ebook_no_ln').
        Les ebooks déjà traités (avec ou sans papier LN trouvé) sont skippés.
        
        Returns:
            set d'ASINs à skipper dans Featured
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        if filtre == "ln_only":
            # Pour LN : skipper tout SAUF les ebooks jamais traités pour cette série LN
            # Un ebook est "traité" s'il a un asin_papier OU s'il a déjà été scanné (date_vu existe)
            # En pratique : on skippe tout, car si l'ebook est dans featured_history
            # c'est qu'il a déjà été scanné pour cette série LN spécifiquement
            cursor.execute('SELECT asin FROM featured_history WHERE serie = ?', (serie,))
        else:
            cursor.execute('SELECT asin FROM featured_history WHERE serie = ?', (serie,))
        return {row[0] for row in cursor.fetchall()}
    
    def sauvegarder_featured(self, serie: str, asin: str, statut: str, 
                             source: str = None, titre: str = None, asin_papier: str = None):
        """Sauvegarde un ASIN rencontré dans Featured/Bulk avec son statut.
        
        Statuts possibles : 'ebook', 'hors_sujet_titre', 'derive', 'lot', 
                           'sponsorise', 'non_papier', 'papier'
        Sources possibles : 'featured_p1', 'featured_p2', ..., 'bulk'
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO featured_history 
            (serie, asin, statut, source, titre, asin_papier, date_vu)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (serie, asin, statut, source, titre, asin_papier,
              datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    
    def get_featured_stats(self, serie: str) -> dict:
        """Récupère les statistiques de featured_history pour une série.
        
        Returns:
            dict: {statut: count} ex: {'ebook': 5, 'hors_sujet_titre': 3, 'papier': 2, ...}
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT statut, COUNT(*) FROM featured_history 
            WHERE serie = ? GROUP BY statut
        ''', (serie,))
        return {row[0]: row[1] for row in cursor.fetchall()}
    
    def get_featured_progression(self, serie: str) -> tuple:
        """Récupère la progression Featured pour une série.
        
        Returns:
            (derniere_page, exploration_complete) ou (0, False) si pas d'entrée
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT derniere_page, exploration_complete FROM featured_progression
            WHERE serie = ?
        ''', (serie,))
        row = cursor.fetchone()
        if row:
            return (row[0], bool(row[1]))
        return (0, False)
    
    def set_featured_progression(self, serie: str, page: int, complete: bool = False):
        """Met à jour la progression Featured pour une série."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO featured_progression (serie, derniere_page, exploration_complete, date_maj)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(serie) DO UPDATE SET 
                derniere_page = ?, exploration_complete = ?, date_maj = ?
        ''', (serie, page, int(complete), datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
              page, int(complete), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    
    def migrer_ebooks_vers_featured_history(self):
        """Migration unique : copie ebooks_traites vers featured_history puis supprime la table.
        Appelée au démarrage. Si la table n'existe plus, retourne 0 silencieusement."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # Vérifier si la table legacy existe encore
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ebooks_traites'")
        if not cursor.fetchone():
            return 0  # Table déjà supprimée
        
        cursor.execute('SELECT COUNT(*) FROM featured_history')
        if cursor.fetchone()[0] > 0:
            return 0  # Déjà migré
        
        cursor.execute('SELECT COUNT(*) FROM ebooks_traites')
        nb_ebooks = cursor.fetchone()[0]
        if nb_ebooks == 0:
            return 0  # Rien à migrer
        
        cursor.execute('''
            INSERT OR IGNORE INTO featured_history (serie, asin, statut, source, titre, asin_papier, date_vu)
            SELECT manga_nom, asin_ebook, 'ebook', 'migration', NULL, asin_papier, date_traitement
            FROM ebooks_traites
        ''')
        conn.commit()
        return cursor.rowcount
    
    def est_verifie_aujourdhui(self, asin: str) -> Optional[Dict]:
        """
        Vérifie si l'ASIN est dans le cache.
        Le cache est permanent car les infos (tome, date sortie) ne changent pas.
        Retourne None seulement si:
        - L'ASIN n'est pas en cache
        - Le tome est N/A (on peut réessayer de le détecter)
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT date_sortie, tome, titre, editeur FROM verifications_cache 
            WHERE asin = ?
        ''', (asin,))
        
        result = cursor.fetchone()
        
        if result:
            tome = result[1]
            if tome == 'N/A':
                return None  # Forcer re-vérification
            
            return {
                'date': result[0],
                'tome': tome,
                'titre': result[2],
                'editeur': result[3]
            }
        return None
    
    def get_verification_cache(self, asin: str) -> Optional[Dict]:
        """
        Récupère le cache pour un ASIN, même si le tome est N/A.
        Utilisé comme fallback quand la page actuelle retourne un captcha.
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT date_sortie, tome, titre, editeur FROM verifications_cache 
            WHERE asin = ?
        ''', (asin,))
        
        result = cursor.fetchone()
        
        if result:
            return {
                'date': result[0],
                'tome': result[1],
                'titre': result[2],
                'editeur': result[3]
            }
        return None
    
    def sauvegarder_verification(self, asin: str, date_sortie: str, tome: str, titre: str, editeur: str = None):
        """Sauvegarde une vérification dans le cache"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO verifications_cache 
            (asin, date_verification, date_sortie, tome, titre, editeur)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (asin, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), date_sortie, tome, titre, editeur))
        conn.commit()
    
    # ========================================================================
    # MÉTHODES POUR LA TABLE VOLUMES (consolidée)
    # ========================================================================
    
    def init_table_volumes(self):
        """Initialise la table volumes si elle n'existe pas"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS volumes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                serie_jp TEXT NOT NULL,
                serie_fr TEXT,
                tome INTEGER,
                asin TEXT UNIQUE NOT NULL,
                url TEXT,
                date_sortie_jp TEXT,
                titre_volume TEXT,
                date_ajout TEXT,
                date_maj TEXT,
                editeur TEXT
            )
        ''')
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_volumes_serie_jp ON volumes(serie_jp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_volumes_serie_fr ON volumes(serie_fr)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_volumes_asin ON volumes(asin)")
        
        conn.commit()
    
    def sauvegarder_volume(self, serie_jp: str, serie_fr: str, 
                          tome: int, asin: str, url: str, date_sortie_jp: str, titre_volume: str,
                          editeur: str = None):
        """Sauvegarde ou met à jour un volume dans la table consolidée"""
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Vérifier si le volume existe déjà
        cursor.execute('SELECT id, serie_fr, editeur FROM volumes WHERE asin = ?', (asin,))
        existing = cursor.fetchone()
        
        if existing:
            existing_fr = existing[1]
            existing_editeur = existing[2]
            
            final_fr = serie_fr if serie_fr else existing_fr
            final_editeur = editeur if editeur else existing_editeur
            
            cursor.execute('''
                UPDATE volumes SET
                    serie_jp = ?,
                    serie_fr = ?,
                    tome = ?,
                    url = ?,
                    date_sortie_jp = ?,
                    titre_volume = ?,
                    date_maj = ?,
                    editeur = ?
                WHERE asin = ?
            ''', (serie_jp, final_fr, tome, url, date_sortie_jp, titre_volume, now, final_editeur, asin))
        else:
            cursor.execute('''
                INSERT INTO volumes 
                (serie_jp, serie_fr, tome, asin, url, date_sortie_jp, titre_volume, date_ajout, date_maj, editeur)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (serie_jp, serie_fr, tome, asin, url, date_sortie_jp, titre_volume, now, now, editeur))
        
        conn.commit()
    
    def get_series_sans_traduction(self) -> List[Dict]:
        """Récupère les séries qui n'ont pas de titre FR.
        Croise volumes ET traductions pour éviter les faux positifs.
        Note : serie_jp contient le suffixe [LN]/[MANGA] mais titre_japonais non,
        donc on compare sans le suffixe.
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DISTINCT v.serie_jp
            FROM volumes v
            WHERE (v.serie_fr IS NULL OR v.serie_fr = '')
            AND NOT EXISTS (
                SELECT 1 FROM traductions t 
                WHERE (t.titre_japonais = v.serie_jp
                    OR t.titre_japonais = REPLACE(REPLACE(v.serie_jp, ' [LN]', ''), ' [MANGA]', ''))
                AND t.titre_francais IS NOT NULL 
                AND t.titre_francais != ''
            )
        ''')
        results = []
        for row in cursor.fetchall():
            results.append({
                'serie_jp': row[0],
                'serie_fr': None
            })
        return results
    
    def sauvegarder_traduction_complete(self, titre_japonais: str, titre_francais: str = None, 
                                        titre_anglais: str = None, source: str = 'unknown', 
                                        est_officielle: bool = False):
        """Sauvegarde une traduction FR"""
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Récupérer la valeur existante
        cursor.execute('SELECT titre_francais FROM traductions WHERE titre_japonais = ?', (titre_japonais,))
        existing = cursor.fetchone()
        
        final_fr = titre_francais if titre_francais else (existing[0] if existing else None)
        
        cursor.execute('''
            INSERT OR REPLACE INTO traductions 
            (titre_japonais, titre_francais, date_ajout, source, est_officielle, derniere_verification)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (titre_japonais, final_fr, now, source, 1 if est_officielle else 0, now))
        
        conn.commit()
        return final_fr
    
    def get_traduction_complete(self, titre_japonais: str) -> Optional[Dict]:
        """Récupère la traduction complète pour un titre"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT titre_francais, source, est_officielle, derniere_verification 
            FROM traductions WHERE titre_japonais = ?
        ''', (titre_japonais,))
        result = cursor.fetchone()
        
        if result:
            return {
                'titre_francais': result[0],
                'source': result[1],
                'est_officielle': result[2] == 1,
                'derniere_verification': result[3]
            }
        return None
    
    # ========================================================================
    # MÉTHODES POUR LA GESTION DES ÉDITEURS
    # ========================================================================
    
    def init_table_editeurs(self):
        """Crée la table des éditeurs officiels par série"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS series_editeurs (
                serie_id TEXT PRIMARY KEY,
                editeur_officiel TEXT,
                date_detection TEXT,
                nb_volumes_detectes INTEGER DEFAULT 0,
                derniere_recherche TEXT
            )
        ''')
        conn.commit()
    
    # NOTE: get_derniere_recherche / set_derniere_recherche supprimées
    # Remplacées par featured_progression (get/set_featured_progression)
    
    def get_editeur_officiel(self, serie_id: str) -> Optional[str]:
        """Récupère l'éditeur officiel d'une série"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT editeur_officiel FROM series_editeurs WHERE serie_id = ?', (serie_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    
    def set_editeur_officiel(self, serie_id: str, editeur: str, nb_volumes: int = 1):
        """Définit l'éditeur officiel d'une série"""
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Normaliser l'éditeur
        editeur_normalise = normaliser_editeur(editeur)
        
        cursor.execute('''
            INSERT OR REPLACE INTO series_editeurs 
            (serie_id, editeur_officiel, date_detection, nb_volumes_detectes)
            VALUES (?, ?, ?, ?)
        ''', (serie_id, editeur_normalise, now, nb_volumes))
        conn.commit()
        logger.info(f"    📚 Éditeur officiel défini: {editeur_normalise}")
    
    
    def get_editeur_majoritaire(self, serie_id: str, valides_seulement: bool = False) -> Optional[str]:
        """
        Récupère l'éditeur majoritaire d'une série depuis les volumes existants.
        
        Args:
            serie_id: Nom de la série (avec suffixe)
            valides_seulement: Si True, ne considère que les volumes validés manuellement
        
        Returns:
            Le nom de l'éditeur le plus fréquent (normalisé), ou None si aucun volume
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        
        if valides_seulement:
            cursor.execute('''
                SELECT v.editeur, COUNT(*) as nb
                FROM volumes v
                INNER JOIN statuts_manuels s ON v.asin = s.asin AND s.statut = 'valide'
                WHERE v.serie_jp = ? AND v.editeur IS NOT NULL AND v.editeur != ''
                GROUP BY v.editeur
                ORDER BY nb DESC
                LIMIT 1
            ''', (serie_id,))
        else:
            cursor.execute('''
                SELECT editeur, COUNT(*) as nb
                FROM volumes
                WHERE serie_jp = ? AND editeur IS NOT NULL AND editeur != ''
                GROUP BY editeur
                ORDER BY nb DESC
                LIMIT 1
            ''', (serie_id,))
        
        result = cursor.fetchone()
        
        if result:
            return normaliser_editeur(result[0])
        return None
    
    def detecter_et_sauvegarder_editeur_officiel(self, serie_id: str) -> Optional[str]:
        """
        Détecte l'éditeur officiel d'une série et le sauvegarde.
        
        Priorité :
        1. Éditeur majoritaire des volumes VALIDÉS manuellement (confirmation utilisateur)
        2. Éditeur déjà enregistré (détection précédente)
        3. Éditeur majoritaire de tous les volumes (auto-détection)
        
        Si des validations existent et donnent un éditeur différent de l'existant,
        l'éditeur est mis à jour (la validation prime).
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # 1. Vérifier si des volumes validés existent pour cette série
        editeur_valide = self.get_editeur_majoritaire(serie_id, valides_seulement=True)
        
        if editeur_valide:
            # La validation utilisateur fait autorité
            editeur_existant = self.get_editeur_officiel(serie_id)
            if editeur_existant != editeur_valide:
                cursor.execute('SELECT COUNT(*) FROM volumes v INNER JOIN statuts_manuels s ON v.asin = s.asin AND s.statut = \'valide\' WHERE v.serie_jp = ?', (serie_id,))
                nb = cursor.fetchone()[0]
                self.set_editeur_officiel(serie_id, editeur_valide, nb)
                if editeur_existant:
                    logger.info(f"    📚 Éditeur mis à jour par validation: {editeur_existant} → {editeur_valide}")
            return editeur_valide
        
        # 2. Éditeur déjà enregistré (pas de validation, on garde l'existant)
        editeur_existant = self.get_editeur_officiel(serie_id)
        if editeur_existant:
            return editeur_existant
        
        # 3. Auto-détection sur tous les volumes (premier run)
        editeur_majoritaire = self.get_editeur_majoritaire(serie_id)
        if editeur_majoritaire:
            cursor.execute('''
                SELECT COUNT(*) FROM volumes 
                WHERE serie_jp = ? AND editeur IS NOT NULL
            ''', (serie_id,))
            nb_volumes = cursor.fetchone()[0]
            self.set_editeur_officiel(serie_id, editeur_majoritaire, nb_volumes)
            return editeur_majoritaire
        
        return None
    
    # ========================================================================
    # MÉTHODES POUR LE SUIVI ÉDITORIAL (workflow par tome)
    # ========================================================================

    ETAPES_WORKFLOW = [
        'mail_nwk',
        'draft_ad',
        'reponse_nwk',
        'contrat_ad',
        'signature_nwk',
        'facture',
    ]

    LABELS_ETAPES = {
        'mail_nwk':      'Mail NWK → offre éditeur JP',
        'draft_ad':      'Réception draft Ayants Droits',
        'reponse_nwk':   'Réponse NWK au draft',
        'contrat_ad':    'Réception contrat à signer',
        'signature_nwk': 'NWK signe + archive',
        'facture':       'Réception + paiement facture',
    }

    def creer_workflow_volume(self, asin: str, serie_jp: str, tome, today: str):
        """Crée la première étape (mail_nwk) pour un nouveau tome, si elle n'existe pas déjà."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO suivi_editorial
            (asin, serie_jp, tome, etape, statut, date_declenchement, nb_relances)
            VALUES (?, ?, ?, 'mail_nwk', 'en_attente', ?, 0)
        ''', (asin, serie_jp, tome, today))
        if cursor.rowcount > 0:
            logger.info(f"   📑 Workflow créé: {serie_jp[:30]} T{tome} [{asin}]")
        conn.commit()

    def get_etape_courante_workflow(self, asin: str) -> Optional[Dict]:
        """Retourne l'étape courante (en_attente) du workflow pour un ASIN, ou None."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
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
        ''', (asin,))
        row = cursor.fetchone()
        if not row:
            return None
        etape = row[0]
        date_decl = row[2]
        try:
            from datetime import date
            jours = (date.today() - datetime.strptime(date_decl, '%Y-%m-%d').date()).days
        except Exception:
            jours = 0
        etapes_faites = self._get_etapes_faites(asin)
        return {
            'etape': etape,
            'label': self.LABELS_ETAPES.get(etape, etape),
            'statut': row[1],
            'date_declenchement': date_decl,
            'date_completion': row[3],
            'nb_relances': row[4],
            'serie_jp': row[5],
            'tome': row[6],
            'jours_ecoules': jours,
            'etapes_faites': etapes_faites,
        }

    def creer_workflow_depuis_asin(self, asin: str, today: str):
        """
        Crée la première étape workflow pour un ASIN en cherchant série/tome dans volumes.
        Utilisé quand le viewer initie un workflow manuellement sur un volume existant.
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT serie_jp, tome FROM volumes WHERE asin = ?', (asin,))
        row = cursor.fetchone()
        if row:
            self.creer_workflow_volume(asin, row[0], row[1], today)
        else:
            logger.warning(f"   ⚠️  Workflow init ignoré: ASIN {asin} introuvable en BDD")

    def _get_etapes_faites(self, asin: str) -> List[str]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT etape FROM suivi_editorial WHERE asin = ? AND statut = 'fait'",
            (asin,)
        )
        return [row[0] for row in cursor.fetchall()]

    def marquer_etape_faite(self, asin: str, etape: str, date_completion: str):
        """
        Marque une étape comme faite et crée automatiquement l'étape suivante.
        Idempotent : si déjà fait avec la même date, ne fait rien.
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        # Vérifier que l'étape existe et est en_attente (ou pas encore créée depuis Gist)
        cursor.execute(
            "SELECT statut, date_completion FROM suivi_editorial WHERE asin = ? AND etape = ?",
            (asin, etape)
        )
        row = cursor.fetchone()
        if row and row[0] == 'fait' and row[1] == date_completion:
            return  # Déjà fait, idempotent
        if row:
            cursor.execute('''
                UPDATE suivi_editorial
                SET statut = 'fait', date_completion = ?
                WHERE asin = ? AND etape = ?
            ''', (date_completion, asin, etape))
        else:
            # L'étape n'existe pas en BDD (import depuis Gist pour une étape future)
            # Récupérer info de base depuis une autre étape du même ASIN
            cursor.execute(
                "SELECT serie_jp, tome FROM suivi_editorial WHERE asin = ? LIMIT 1",
                (asin,)
            )
            base = cursor.fetchone()
            if base:
                serie_jp, tome = base
                cursor.execute('''
                    INSERT OR REPLACE INTO suivi_editorial
                    (asin, serie_jp, tome, etape, statut, date_declenchement, date_completion, nb_relances)
                    VALUES (?, ?, ?, ?, 'fait', ?, ?, 0)
                ''', (asin, serie_jp, tome, etape, date_completion, date_completion))
        # Créer l'étape suivante si elle n'existe pas encore
        try:
            idx = self.ETAPES_WORKFLOW.index(etape)
            if idx + 1 < len(self.ETAPES_WORKFLOW):
                etape_suivante = self.ETAPES_WORKFLOW[idx + 1]
                cursor.execute(
                    "SELECT 1 FROM suivi_editorial WHERE asin = ? AND etape = ?",
                    (asin, etape_suivante)
                )
                if not cursor.fetchone():
                    cursor.execute(
                        "SELECT serie_jp, tome FROM suivi_editorial WHERE asin = ? LIMIT 1",
                        (asin,)
                    )
                    base = cursor.fetchone()
                    if base:
                        cursor.execute('''
                            INSERT INTO suivi_editorial
                            (asin, serie_jp, tome, etape, statut, date_declenchement, nb_relances)
                            VALUES (?, ?, ?, ?, 'en_attente', ?, 0)
                        ''', (asin, base[0], base[1], etape_suivante, date_completion))
                        logger.info(f"   📑 Étape suivante créée: {etape_suivante} pour [{asin}]")
        except ValueError:
            pass
        conn.commit()

    def get_actions_en_retard(self, delai_jours: int = 10) -> List[Dict]:
        """Retourne toutes les étapes en_attente dont la date de déclenchement dépasse delai_jours."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT asin, serie_jp, tome, etape, date_declenchement, nb_relances
            FROM suivi_editorial
            WHERE statut = 'en_attente'
            AND date(date_declenchement, '+' || ? || ' days') < date('now')
            AND (pause_jusqu_au IS NULL OR date(pause_jusqu_au) < date('now'))
            ORDER BY date_declenchement ASC
        ''', (delai_jours,))
        result = []
        for row in cursor.fetchall():
            asin, serie_jp, tome, etape, date_decl, nb_relances = row
            try:
                from datetime import date
                jours = (date.today() - datetime.strptime(date_decl, '%Y-%m-%d').date()).days
            except Exception:
                jours = delai_jours + 1
            result.append({
                'asin': asin,
                'serie_jp': serie_jp,
                'tome': tome,
                'etape': etape,
                'label': self.LABELS_ETAPES.get(etape, etape),
                'date_declenchement': date_decl,
                'jours_ecoules': jours,
                'nb_relances': nb_relances,
            })
        return result

    def incrementer_relances(self, asin: str, etape: str):
        """Incrémente le compteur de relances pour une étape."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE suivi_editorial SET nb_relances = nb_relances + 1
            WHERE asin = ? AND etape = ?
        ''', (asin, etape))
        conn.commit()

    def get_tous_workflows_actifs(self) -> Dict[str, Dict]:
        """
        Retourne un dict {asin: workflow_info} pour tous les ASIN ayant une étape en_attente.
        Utilisé pour enrichir l'export manga_collection.json.
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT asin, etape, date_declenchement, nb_relances, pause_jusqu_au
            FROM suivi_editorial
            WHERE statut = 'en_attente'
        ''')
        workflows = {}
        for row in cursor.fetchall():
            asin, etape, date_decl, nb_relances, pause_jusqu_au = row
            try:
                from datetime import date
                jours = (date.today() - datetime.strptime(date_decl, '%Y-%m-%d').date()).days
            except Exception:
                jours = 0
            if asin not in workflows:
                etapes_faites = self._get_etapes_faites(asin)
                workflows[asin] = {
                    'etape_courante': etape,
                    'label': self.LABELS_ETAPES.get(etape, etape),
                    'date_declenchement': date_decl,
                    'jours_ecoules': jours,
                    'nb_relances': nb_relances,
                    'etapes_faites': etapes_faites,
                    'pause_jusqu_au': pause_jusqu_au,
                }
        return workflows

    def definir_pause_workflow(self, asin: str, etape: str, date_pause: str):
        """Définit une pause sur une étape jusqu'à date_pause (format YYYY-MM-DD)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE suivi_editorial SET pause_jusqu_au = ?
            WHERE asin = ? AND etape = ? AND statut = 'en_attente'
        ''', (date_pause, asin, etape))
        conn.commit()
        logger.info(f"   ⏸ Pause workflow [{asin}] étape {etape} jusqu'au {date_pause}")

    def effacer_pause_workflow(self, asin: str, etape: str):
        """Efface la pause d'une étape (reprend le suivi normal)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE suivi_editorial SET pause_jusqu_au = NULL
            WHERE asin = ? AND etape = ?
        ''', (asin, etape))
        conn.commit()

    def get_pauses_expirees(self) -> List[Dict]:
        """Retourne les étapes en pause dont la date de pause est dépassée (aujourd'hui)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT asin, serie_jp, tome, etape, date_declenchement, nb_relances, pause_jusqu_au
            FROM suivi_editorial
            WHERE statut = 'en_attente'
            AND pause_jusqu_au IS NOT NULL
            AND date(pause_jusqu_au) <= date('now')
            ORDER BY pause_jusqu_au ASC
        ''')
        result = []
        for row in cursor.fetchall():
            asin, serie_jp, tome, etape, date_decl, nb_relances, pause_jusqu_au = row
            result.append({
                'asin': asin,
                'serie_jp': serie_jp,
                'tome': tome,
                'etape': etape,
                'label': self.LABELS_ETAPES.get(etape, etape),
                'date_declenchement': date_decl,
                'nb_relances': nb_relances,
                'pause_jusqu_au': pause_jusqu_au,
            })
        return result

    # ========================================================================
    # MÉTHODES POUR LES STATUTS MANUELS (validé/rejeté)
    # ========================================================================
    
    
    def set_statut_manuel(self, asin: str, statut: str, commentaire: str = None):
        """Définit le statut manuel d'un ASIN"""
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
            INSERT OR REPLACE INTO statuts_manuels (asin, statut, commentaire, date_modification)
            VALUES (?, ?, ?, ?)
        ''', (asin, statut, commentaire, now))
        conn.commit()
    
    def get_asins_rejetes(self) -> Set[str]:
        """Récupère tous les ASINs marqués comme rejetés"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT asin FROM statuts_manuels WHERE statut = 'rejete'")
        asins = {row[0] for row in cursor.fetchall()}
        return asins
    
    def get_asins_valides(self) -> Set[str]:
        """Récupère tous les ASINs marqués comme validés"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT asin FROM statuts_manuels WHERE statut = 'valide'")
        asins = {row[0] for row in cursor.fetchall()}
        return asins
    
    def get_asin_reference(self, serie_jp: str) -> Optional[str]:
        """
        Récupère un ASIN de référence fiable pour une série.
        
        Un ASIN de référence est un volume validé manuellement pour cette série.
        Il peut être utilisé pour accéder directement au Bulk Amazon si la recherche Featured échoue.
        
        Returns:
            ASIN validé ou None si aucun n'existe
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # Chercher un volume validé pour cette série
        cursor.execute('''
            SELECT v.asin 
            FROM volumes v
            JOIN statuts_manuels s ON v.asin = s.asin
            WHERE v.serie_jp = ? AND s.statut = 'valide'
            ORDER BY v.tome DESC
            LIMIT 1
        ''', (serie_jp,))
        
        row = cursor.fetchone()
        
        return row[0] if row else None
    
    def get_volumes_valides_sans_tome(self) -> List[Dict]:
        """
        Récupère les volumes validés manuellement qui ont un tome manquant (?, N/A, NULL).
        Ces volumes ont été ajoutés manuellement et nécessitent une recherche du numéro de tome.
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # Jointure entre statuts_manuels (validés) et volumes (tome manquant)
        cursor.execute('''
            SELECT v.asin, v.serie_jp, v.url, v.titre_volume
            FROM volumes v
            JOIN statuts_manuels s ON v.asin = s.asin
            WHERE s.statut = 'valide'
            AND (v.tome IS NULL OR v.tome = 0 OR v.tome = -1)
        ''')
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'asin': row[0],
                'serie_jp': row[1],
                'url': row[2],
                'titre_volume': row[3]
            })
        return results
    
    
    def update_tome_volume(self, asin: str, tome: int):
        """Met à jour le numéro de tome d'un volume"""
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Mettre à jour dans la table volumes
        cursor.execute('''
            UPDATE volumes SET tome = ?, date_maj = ? WHERE asin = ?
        ''', (tome, now, asin))
        
        # Mettre à jour aussi dans le cache de vérifications
        # BUG CORRIGÉ: le monolithe utilisait "verifications" au lieu de "verifications_cache"
        cursor.execute('''
            UPDATE verifications_cache SET tome = ? WHERE asin = ?
        ''', (str(tome), asin))
        
        conn.commit()
        logger.debug(f"   📝 Tome mis à jour: {asin} → T{tome}")
    
    def importer_statuts_json(self, filepath: str) -> Dict[str, int]:
        """
        Importe les statuts depuis un fichier JSON (corrections.json ou statuts.json).
        
        Formats supportés:
        - corrections.json: {"hors_sujet": ["ASIN1", "ASIN2"], "commentaires": {...}}
        - statuts.json: {"rejetes": ["ASIN1"], "valides": ["ASIN2"]}
        - volume_serie_override: {"ASIN": "Nouveau nom série"}
        - series_scindees: [{"nom_original": "...", "nouveau_nom": "...", "editeur": "..."}]
        
        Retourne le nombre d'imports par type.
        """
        if not os.path.exists(filepath):
            return {'rejetes': 0, 'valides': 0, 'overrides': 0, 'scissions': 0}
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"⚠️  Erreur lecture {filepath}: {e}")
            return {'rejetes': 0, 'valides': 0, 'overrides': 0, 'scissions': 0}
        
        counts = {'rejetes': 0, 'valides': 0, 'overrides': 0, 'scissions': 0}
        commentaires = data.get('commentaires', {})
        
        # Format corrections.json (hors_sujet = rejetés)
        for asin in data.get('hors_sujet', []):
            self.set_statut_manuel(asin, 'rejete', commentaires.get(asin))
            counts['rejetes'] += 1
        
        # Format statuts.json (plus complet)
        for asin in data.get('rejetes', []):
            self.set_statut_manuel(asin, 'rejete', commentaires.get(asin))
            counts['rejetes'] += 1
        
        for asin in data.get('valides', []):
            self.set_statut_manuel(asin, 'valide', commentaires.get(asin))
            counts['valides'] += 1
        
        # Importer les overrides de série (ASIN → nom de série alternatif)
        volume_overrides = data.get('volume_serie_override', {})
        for asin, nouveau_nom in volume_overrides.items():
            self.set_volume_serie_override(asin, nouveau_nom)
            counts['overrides'] += 1
        
        # Importer les séries scindées → ajouter au dictionnaire TRADUCTIONS_FR
        series_scindees = data.get('series_scindees', [])
        for scission in series_scindees:
            nouveau_nom = scission.get('nouveau_nom', '')
            if nouveau_nom:
                # Ajouter la traduction pour la nouvelle série
                config.TRADUCTIONS_FR[nouveau_nom] = nouveau_nom
                counts['scissions'] += 1
        
        return counts
    

    def get_asins_serie(self, manga_nom: str) -> set:
        """Récupère tous les ASIN associés à une série (pour nettoyage Gist)"""
        conn = self._get_conn()
        cursor = conn.cursor()
        asins = set()
        
        # Depuis volumes
        try:
            cursor.execute('SELECT asin FROM volumes WHERE serie_jp = ?', (manga_nom,))
            asins.update(row[0] for row in cursor.fetchall())
        except sqlite3.OperationalError:
            pass
        
        # Depuis featured_history
        try:
            cursor.execute('SELECT asin FROM featured_history WHERE serie = ?', (manga_nom,))
            asins.update(row[0] for row in cursor.fetchall() if row[0])
        except sqlite3.OperationalError:
            pass
        
        return asins

    def purger_serie(self, manga_nom: str):
        """Supprime toutes les données en cache pour une série."""
        conn = self._get_conn()
        cursor = conn.cursor()
        tables_nettoyees = []
        
        purges = [
            ('featured_history', 'serie'),
            ('featured_progression', 'serie'),
            ('volumes', 'serie_jp'),
            ('series_editeurs', 'serie_id'),
            ('alertes', 'nom'),
            ('traductions', 'titre_japonais'),
        ]
        
        for table, colonne in purges:
            try:
                cursor.execute(f'DELETE FROM {table} WHERE {colonne} = ?', (manga_nom,))
                if cursor.rowcount > 0:
                    tables_nettoyees.append(f"{table} ({cursor.rowcount})")
            except sqlite3.OperationalError as e:
                logger.debug(f"⚠️ Purge {table}: {e}")
        
        conn.commit()
        
        if tables_nettoyees:
            logger.info(f"   🗑️  Cache purgé pour {manga_nom[:30]}: {', '.join(tables_nettoyees)}")
        return tables_nettoyees
