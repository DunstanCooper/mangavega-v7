#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MangaVega Tracker - Synchronisation Gist et fichiers de configuration
"""

import json
import os
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List

import config
from utils import strip_type_suffix, normaliser_editeur

logger = config.logger


def sauvegarder_gist_config():
    """
    Sauvegarde series_config.json et corrections.json vers le Gist GitHub.
    Met à jour date_seuil pour le prochain run.
    """
        
    if not config.GIST_TOKEN:
        logger.warning("   ⚠️  Pas de token GitHub, impossible de sauvegarder le Gist")
        return False
    
    try:
        import urllib.request
        
        # Mettre à jour date_seuil : date d'aujourd'hui - 14 jours de marge
        # La marge permet de re-détecter un volume qui apparaîtrait rétroactivement
        nouvelle_date_seuil = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
        config.GIST_CORRECTIONS['date_seuil'] = nouvelle_date_seuil
        
        logger.info(f"☁️  Sauvegarde du Gist...")
        logger.info(f"   📅 Nouvelle date seuil: {nouvelle_date_seuil}")
        
        # Préparer les données à envoyer
        files_to_update = {
            "corrections.json": {
                "content": json.dumps(config.GIST_CORRECTIONS, ensure_ascii=False, indent=2)
            }
        }
        
        # Ajouter series_config.json seulement si modifié
        if config.GIST_MODIFIED:
            files_to_update["series_config.json"] = {
                "content": json.dumps(config.GIST_SERIES_CONFIG, ensure_ascii=False, indent=2)
            }
        
        data = { "files": files_to_update }
        
        req = urllib.request.Request(
            config.GIST_API_URL,
            data=json.dumps(data).encode('utf-8'),
            headers={
                'User-Agent': 'MangaTracker/1.0',
                'Authorization': f'token {config.GIST_TOKEN}',
                'Content-Type': 'application/json'
            },
            method='PATCH'
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                logger.info("   ✅ Gist mis à jour avec succès")
                config.GIST_MODIFIED = False
                return True
        
        return False
        
    except Exception as e:
        logger.warning(f"   ⚠️  Erreur sauvegarde Gist: {e}")
        return False

def charger_gist_config():
    """
    Charge corrections.json et series_config.json depuis le Gist GitHub.
    Ces fichiers sont synchronisés par le viewer web.
    
    Returns:
        tuple: (corrections_dict, series_config_dict)
    """
            
    try:
        import urllib.request
        
        logger.info("☁️  Chargement de la configuration depuis le Gist...")
        
        req = urllib.request.Request(config.GIST_API_URL, headers={'User-Agent': 'MangaTracker/1.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            gist_data = json.loads(response.read().decode('utf-8'))
        
        files = gist_data.get('files', {})
        
        # Charger corrections.json
        if 'corrections.json' in files:
            content = files['corrections.json'].get('content', '{}')
            config.GIST_CORRECTIONS = json.loads(content)
            nb_valides = len(config.GIST_CORRECTIONS.get('valides', []))
            nb_rejetes = len(config.GIST_CORRECTIONS.get('rejetes', []))
            logger.info(f"   ✅ corrections.json: {nb_valides} validé(s), {nb_rejetes} rejeté(s)")
            
            # Charger date_seuil dynamique
            if 'date_seuil' in config.GIST_CORRECTIONS:
                try:
                    config.DATE_SEUIL = datetime.strptime(config.GIST_CORRECTIONS['date_seuil'], '%Y-%m-%d')
                    logger.info(f"   📅 Date seuil nouveautés: {config.DATE_SEUIL.strftime('%Y/%m/%d')} (depuis Gist)")
                except (ValueError, TypeError):
                    logger.warning(f"   ⚠️  Date seuil invalide dans Gist: {config.GIST_CORRECTIONS['date_seuil']}, utilisation défaut")
            else:
                logger.info(f"   📅 Date seuil nouveautés: {config.DATE_SEUIL.strftime('%Y/%m/%d')} (défaut, premier run)")
        
        # Charger series_config.json
        if 'series_config.json' in files:
            content = files['series_config.json'].get('content', '{}')
            config.GIST_SERIES_CONFIG = json.loads(content)
            nb_urls = sum(len(urls) for urls in config.GIST_SERIES_CONFIG.get('urls_supplementaires', {}).values())
            nb_ajoutees = len(config.GIST_SERIES_CONFIG.get('series_ajoutees', []))
            logger.info(f"   ✅ series_config.json: {nb_urls} URL(s) supp., {nb_ajoutees} série(s) ajoutée(s)")
        
        return config.GIST_CORRECTIONS, config.GIST_SERIES_CONFIG
        
    except Exception as e:
        logger.warning(f"   ⚠️  Impossible de charger le Gist: {e}")
        return {}, {}

def charger_corrections(db: 'DatabaseManager' = None):
    """
    Charge les corrections depuis le Gist, la BDD et/ou le fichier corrections.json.
    
    Priorité:
    1. Charge depuis le Gist (synchronisé par le viewer)
    2. Importe corrections.json vers la BDD (si présent)
    3. Charge les ASINs rejetés depuis la BDD
    """
        
    # Si on a un db manager, utiliser la BDD
    if db:
        # NOUVEAU: Importer les rejets du Gist vers la BDD
        if config.GIST_CORRECTIONS:
            gist_rejetes = config.GIST_CORRECTIONS.get('rejetes', [])
            gist_valides = config.GIST_CORRECTIONS.get('valides', [])
            gist_tomes = config.GIST_CORRECTIONS.get('tomes', {})
            
            if gist_rejetes or gist_valides:
                # Comparer avec les statuts existants pour ne pas re-importer
                existing_rejetes = db.get_asins_rejetes()
                existing_valides = db.get_asins_valides()
                
                # Importer seulement les nouveaux
                imported_rejets = 0
                imported_valides = 0
                for asin in gist_rejetes:
                    if asin not in existing_rejetes:
                        db.set_statut_manuel(asin, 'rejete', 'Import Gist')
                        imported_rejets += 1
                for asin in gist_valides:
                    if asin not in existing_valides:
                        db.set_statut_manuel(asin, 'valide', 'Import Gist')
                        imported_valides += 1
                if imported_rejets > 0:
                    logger.info(f"☁️  {imported_rejets} nouveau(x) rejet(s) importé(s) depuis Gist")
                if imported_valides > 0:
                    logger.info(f"☁️  {imported_valides} nouvelle(s) validation(s) importée(s) depuis Gist")
            
            # Importer les corrections de tomes
            if gist_tomes:
                imported_tomes = 0
                for asin, tome in gist_tomes.items():
                    try:
                        db.update_tome_volume(asin, int(tome))
                        imported_tomes += 1
                    except Exception as e:
                        logger.debug(f"⚠️ Erreur import tome {asin}: {e}")
                if imported_tomes > 0:
                    logger.info(f"☁️  {imported_tomes} correction(s) de tome importée(s) depuis Gist")
            
            # Importer les éditeurs officiels du Gist vers la BDD
            gist_editeurs = config.GIST_CORRECTIONS.get('editeurs_officiels', {})
            if gist_editeurs:
                imported_editeurs = 0
                for serie_jp, editeur in gist_editeurs.items():
                    editeur_actuel = db.get_editeur_officiel(serie_jp)
                    if editeur_actuel != normaliser_editeur(editeur):
                        db.set_editeur_officiel(serie_jp, editeur)
                        imported_editeurs += 1
                if imported_editeurs > 0:
                    logger.info(f"☁️  {imported_editeurs} éditeur(s) officiel(s) importé(s) depuis Gist")
                else:
                    logger.info(f"📚 {len(gist_editeurs)} éditeur(s) officiel(s) (à jour)")

            # Importer les completions de workflow depuis le Gist vers la BDD
            gist_suivi = config.GIST_CORRECTIONS.get('suivi_editorial', {})
            if gist_suivi:
                today_str = datetime.now().strftime('%Y-%m-%d')
                nb_init = 0
                for asin, completions in gist_suivi.items():
                    if not isinstance(completions, dict):
                        continue
                    if not completions:
                        # {} = initiation manuelle depuis le viewer — créer le workflow si absent
                        try:
                            db.creer_workflow_depuis_asin(asin, today_str)
                            nb_init += 1
                        except Exception as e:
                            logger.warning(f"   ⚠️  Workflow init {asin[:12]}: {e}")
                    else:
                        for etape, valeur in completions.items():
                            if not valeur or not isinstance(valeur, str):
                                continue
                            try:
                                if etape.endswith('__pause'):
                                    # Clé pause : "draft_ad__pause" → "2026-03-15" ou "repris" (annulation)
                                    etape_reelle = etape[:-7]  # retirer "__pause"
                                    if valeur == 'repris':
                                        db.effacer_pause_workflow(asin, etape_reelle)
                                    else:
                                        db.definir_pause_workflow(asin, etape_reelle, valeur)
                                elif etape.endswith('__relance'):
                                    # Clé relance : ex "mail_nwk__relance" → "2026-02-26"
                                    etape_reelle = etape[:-9]  # retirer "__relance"
                                    db.marquer_relance_faite(asin, etape_reelle, valeur)
                                else:
                                    # Clé completion normale
                                    db.marquer_etape_faite(asin, etape, valeur)
                            except Exception as e:
                                logger.warning(f"   ⚠️  Workflow {asin[:12]}/{etape}: {e}")
                msg = f"📑 {len(gist_suivi)} workflow(s) suivi éditorial depuis Gist"
                if nb_init:
                    msg += f" ({nb_init} initialisé(s) manuellement)"
                logger.info(msg)

            # Supprimer les workflows marqués à supprimer depuis le Gist
            gist_supprimes = config.GIST_CORRECTIONS.get('suivi_supprimes', [])
            if gist_supprimes and isinstance(gist_supprimes, list) and db:
                nb_supprimes = 0
                for asin in gist_supprimes:
                    try:
                        db.supprimer_workflow(asin)
                        nb_supprimes += 1
                    except Exception as e:
                        logger.warning(f"   ⚠️  Suppression workflow {asin[:12]}: {e}")
                if nb_supprimes:
                    logger.info(f"🗑️  {nb_supprimes} workflow(s) supprimé(s) depuis Gist")

        # Importer corrections.json vers la BDD s'il existe (fichier local)
        if os.path.exists(config.CORRECTIONS_FILE):
            counts = db.importer_statuts_json(config.CORRECTIONS_FILE)
            has_imports = counts['rejetes'] > 0 or counts['overrides'] > 0 or counts['scissions'] > 0
            if has_imports:
                if counts['rejetes'] > 0:
                    logger.info(f"📋 {counts['rejetes']} rejet(s) importé(s) depuis {config.CORRECTIONS_FILE}")
                if counts['overrides'] > 0:
                    logger.info(f"🔀 {counts['overrides']} override(s) de série importé(s)")
                if counts['scissions'] > 0:
                    logger.info(f"✂️ {counts['scissions']} série(s) scindée(s) importée(s)")
                # Renommer le fichier pour éviter de re-importer
                backup_name = f"corrections_imported_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                os.rename(config.CORRECTIONS_FILE, backup_name)
                logger.info(f"   → Fichier renommé en {backup_name}")
        
        # Charger depuis la BDD
        config.ASINS_HORS_SUJET = db.get_asins_rejetes()
        if config.ASINS_HORS_SUJET:
            logger.info(f"🚫 {len(config.ASINS_HORS_SUJET)} ASIN(s) marqué(s) hors-sujet (depuis BDD)")
    else:
        # Fallback : charger directement depuis le fichier JSON
        if os.path.exists(config.CORRECTIONS_FILE):
            try:
                with open(config.CORRECTIONS_FILE, 'r', encoding='utf-8') as f:
                    corrections = json.load(f)
                config.ASINS_HORS_SUJET = set(corrections.get('hors_sujet', []))
                if config.ASINS_HORS_SUJET:
                    logger.info(f"📋 {len(config.ASINS_HORS_SUJET)} ASIN(s) hors-sujet (depuis {config.CORRECTIONS_FILE})")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"⚠️  Erreur lecture {config.CORRECTIONS_FILE}: {e}")



def charger_mangas_liste():
    """
    Charge la liste des mangas depuis mangas_liste.json.
    Ce fichier est la source principale et peut être modifié par le Gist.
    
    Returns:
        list: Liste des mangas à surveiller
    """
        
    if not os.path.exists(config.MANGAS_LISTE_FILE):
        logger.error(f"❌ {config.MANGAS_LISTE_FILE} non trouvé ! Ce fichier est obligatoire.")
        logger.error(f"   Créez-le avec le format: {{\"mangas\": [{{\"nom\": \"...\", \"url_suffix\": \"...\"}}]}}")
        return config.MANGAS_A_SUIVRE
    
    try:
        with open(config.MANGAS_LISTE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        mangas = data.get('mangas', [])
        if mangas:
            # Convertir type → filtre (ex: type="ln" → filtre="ln_only")
            for manga in mangas:
                if not manga.get('filtre') and manga.get('type'):
                    type_serie = manga['type']
                    if type_serie == 'ln':
                        manga['filtre'] = 'ln_only'
                    elif type_serie == 'manga':
                        manga['filtre'] = 'manga_only'
            config.MANGAS_A_SUIVRE = mangas
            logger.info(f"📋 {len(mangas)} série(s) chargée(s) depuis {config.MANGAS_LISTE_FILE}")
        return config.MANGAS_A_SUIVRE
        
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"⚠️  Erreur lecture {config.MANGAS_LISTE_FILE}: {e}")
        return config.MANGAS_A_SUIVRE


def sauvegarder_mangas_liste():
    """
    Sauvegarde la liste des mangas dans mangas_liste.json.
    Appelé après modification via le Gist (ajout/suppression).
    """
    try:
        # IMPORTANT: Ne persister que les clés structurelles (pas urls_supplementaires, asin_reference, etc.)
        mangas_clean = []
        for m in config.MANGAS_A_SUIVRE:
            mangas_clean.append({k: v for k, v in m.items() if k in config.CLES_PERSISTEES_MANGA and v})
        
        data = {
            "version": "2.0",
            "description": "MangaVega Tracker - Liste des séries à surveiller",
            "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "mangas": mangas_clean
        }
        
        with open(config.MANGAS_LISTE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"💾 Liste sauvegardée dans {config.MANGAS_LISTE_FILE} ({len(config.MANGAS_A_SUIVRE)} séries)")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur sauvegarde {config.MANGAS_LISTE_FILE}: {e}")
        return False



def charger_series_config(db: 'DatabaseManager' = None):
    """
    Charge series_config.json depuis le Gist et/ou le fichier local,
    puis fusionne les URLs supplémentaires dans config.MANGAS_A_SUIVRE.
    
    Le fichier peut contenir:
    - urls_supplementaires: {serie_jp: [url1, url2, ...]}
    - series_ajoutees: nouvelles séries à ajouter (intégrées à mangas_liste.json)
    - series_supprimees: séries à retirer (retirées de mangas_liste.json)
    - traductions: {serie_jp: titre_fr}
    
    NOUVEAU: Les séries ajoutées/supprimées modifient mangas_liste.json directement.
    """
        
    modifs = 0
    liste_modifiee = False  # Flag pour savoir si on doit sauvegarder mangas_liste.json
    
    # ====== ÉTAPE 1: Charger depuis le Gist (prioritaire) ======
    if config.GIST_SERIES_CONFIG:
        gist_urls = config.GIST_SERIES_CONFIG.get('urls_supplementaires', {})
        gist_added = config.GIST_SERIES_CONFIG.get('series_ajoutees', [])
        gist_removed = config.GIST_SERIES_CONFIG.get('series_supprimees', [])
        
        # 1a. Fusionner les URLs supplémentaires du Gist
        if gist_urls:
            for manga in config.MANGAS_A_SUIVRE:
                nom = manga.get('nom', '')
                if nom in gist_urls:
                    existing_urls = manga.get('urls_supplementaires', [])
                    new_urls = gist_urls[nom]
                    # Fusionner sans doublons
                    all_urls = list(set(existing_urls + new_urls))
                    if all_urls:
                        manga['urls_supplementaires'] = all_urls
                        logger.info(f"☁️  {len(new_urls)} URL(s) supp. (Gist) pour: {nom[:30]}...")
                        modifs += len(new_urls)
        
        # 1b. Retirer les séries supprimées du Gist → RETIRÉES DE mangas_liste.json
        # (AVANT l'ajout, pour permettre supprimer+réajouter dans le même run = purge du cache)
        if gist_removed:
            # Filtrer les entrées vides
            gist_removed = [s for s in gist_removed if s and s.strip()]
            
            if gist_removed:
                before = len(config.MANGAS_A_SUIVRE)
                # Matcher les noms exacts (avec suffixe) OU les noms de base (compatibilité)
                # Le viewer envoie le nom complet avec [LN]/[MANGA]
                noms_a_retirer = set(gist_removed)
                config.MANGAS_A_SUIVRE = [m for m in config.MANGAS_A_SUIVRE 
                                   if m['nom'] not in noms_a_retirer]
                removed_count = before - len(config.MANGAS_A_SUIVRE)
                if removed_count > 0:
                    logger.info(f"☁️  {removed_count} série(s) retirée(s) (Gist)")
                    modifs += removed_count
                    liste_modifiee = True
                    
                    # Purger le cache BDD ET le Gist pour les séries supprimées
                    if db:
                        for nom_serie in gist_removed:
                            try:
                                # Récupérer les ASIN AVANT la purge (pour nettoyer le Gist)
                                asins_serie = db.get_asins_serie(nom_serie)
                                
                                # Purger la BDD
                                db.purger_serie(nom_serie)
                                
                                # Nettoyer le Gist : retirer les ASIN de valides/rejetes/tomes
                                if asins_serie and config.GIST_CORRECTIONS:
                                    before_v = len(config.GIST_CORRECTIONS.get('valides', []))
                                    before_r = len(config.GIST_CORRECTIONS.get('rejetes', []))
                                    
                                    config.GIST_CORRECTIONS['valides'] = [
                                        a for a in config.GIST_CORRECTIONS.get('valides', []) 
                                        if a not in asins_serie
                                    ]
                                    config.GIST_CORRECTIONS['rejetes'] = [
                                        a for a in config.GIST_CORRECTIONS.get('rejetes', []) 
                                        if a not in asins_serie
                                    ]
                                    # Nettoyer les tomes
                                    for asin in asins_serie:
                                        config.GIST_CORRECTIONS.get('tomes', {}).pop(asin, None)
                                    
                                    removed_v = before_v - len(config.GIST_CORRECTIONS.get('valides', []))
                                    removed_r = before_r - len(config.GIST_CORRECTIONS.get('rejetes', []))
                                    if removed_v + removed_r > 0:
                                        logger.info(f"   ☁️  Gist nettoyé: {removed_v} validé(s), {removed_r} rejeté(s) retirés")
                                
                                # Nettoyer l'éditeur officiel du Gist
                                if config.GIST_CORRECTIONS and nom_serie in config.GIST_CORRECTIONS.get('editeurs_officiels', {}):
                                    del config.GIST_CORRECTIONS['editeurs_officiels'][nom_serie]
                                    logger.info(f"   ☁️  Éditeur officiel retiré du Gist")
                                    
                            except Exception as e:
                                logger.error(f"❌ Erreur purge série '{nom_serie}': {e}")
                
                # Vider series_supprimees après traitement
                config.GIST_SERIES_CONFIG['series_supprimees'] = []
                config.GIST_MODIFIED = True
                logger.info(f"   🧹 Séries retirées de {config.MANGAS_LISTE_FILE}, series_supprimees vidé")
        
        # 1c. Ajouter les nouvelles séries du Gist → INTÉGRÉES À mangas_liste.json
        if gist_added:
            for serie in gist_added:
                nom = serie.get('nom', '')
                url = serie.get('url', '')
                type_serie = serie.get('type', '')  # "ln", "manga", ou vide
                
                # Suffixe systématique [LN] ou [MANGA] pour le nom interne
                nom_interne = nom
                if not nom.endswith(' [LN]') and not nom.endswith(' [MANGA]'):
                    if type_serie == 'ln':
                        nom_interne = f"{nom} [LN]"
                    else:
                        nom_interne = f"{nom} [MANGA]"
                
                if nom and not any(m['nom'] == nom_interne for m in config.MANGAS_A_SUIVRE):
                    
                    # PURGE AUTOMATIQUE : si un vieux cache existe pour cette série, le nettoyer
                    # (cas suppression + ré-ajout, ou purge échouée au run précédent)
                    if db:
                        cache_existant = db.get_volumes_connus(nom_interne)
                        if cache_existant:
                            try:
                                asins_serie = db.get_asins_serie(nom_interne)
                                db.purger_serie(nom_interne)
                                
                                # Nettoyer le Gist aussi
                                if asins_serie and config.GIST_CORRECTIONS:
                                    config.GIST_CORRECTIONS['valides'] = [
                                        a for a in config.GIST_CORRECTIONS.get('valides', [])
                                        if a not in asins_serie
                                    ]
                                    config.GIST_CORRECTIONS['rejetes'] = [
                                        a for a in config.GIST_CORRECTIONS.get('rejetes', [])
                                        if a not in asins_serie
                                    ]
                                    for asin in asins_serie:
                                        config.GIST_CORRECTIONS.get('tomes', {}).pop(asin, None)
                                    config.GIST_CORRECTIONS.get('editeurs_officiels', {}).pop(nom_interne, None)
                                
                                logger.info(f"   🗑️  Cache + Gist purgés pour {nom_interne[:30]} (ré-ajout)")
                            except Exception as e:
                                logger.error(f"❌ Erreur purge (ré-ajout) '{nom_interne}': {e}")
                    
                    new_serie = {
                        'nom': nom_interne,
                        'url_suffix': serie.get('url_suffix', nom),  # Recherche Amazon = titre original (sans [LN])
                        'urls_supplementaires': []
                    }
                    
                    # Log si le nom de recherche diffère
                    if new_serie['url_suffix'] != nom:
                        logger.info(f"   🔍 Nom de recherche: {new_serie['url_suffix']}")
                    
                    # Sauvegarder les traductions FR/EN si fournies
                    nom_fr = serie.get('nom_fr', '')
                    nom_en = serie.get('nom_en', '')
                    if nom_fr or nom_en:
                        if db:
                            db.sauvegarder_traduction_complete(
                                nom_interne, 
                                titre_francais=nom_fr or None, 
                                titre_anglais=nom_en or None, 
                                source='viewer', 
                                est_officielle=True
                            )
                        if nom_fr:
                            config.TRADUCTIONS_FR[nom_interne] = nom_fr
                            logger.info(f"   🇫🇷 Traduction FR: {nom_fr}")
                        if nom_en:
                            logger.info(f"   🇬🇧 Traduction EN: {nom_en}")
                    
                    # Définir le filtre basé sur le type
                    if type_serie == 'ln':
                        new_serie['filtre'] = 'ln_only'
                        new_serie['type'] = 'ln'
                    elif type_serie == 'manga':
                        new_serie['filtre'] = 'manga_only'
                    # Si pas de type, pas de filtre (comportement par défaut = manga)
                    
                    # Si l'URL contient /dp/ASIN, extraire l'ASIN comme référence
                    if url and '/dp/' in url:
                        import re
                        match = re.search(r'/dp/([A-Z0-9]{10})', url)
                        if match:
                            asin = match.group(1)
                            new_serie['asin_reference'] = asin
                            new_serie['urls_supplementaires'] = [url]
                            type_label = f", type: {type_serie}" if type_serie else ""
                            logger.info(f"☁️  Nouvelle série (Gist): {nom} (ASIN ref: {asin}{type_label})")
                        else:
                            logger.info(f"☁️  Nouvelle série (Gist): {nom}")
                    elif url:
                        # URL de recherche classique
                        new_serie['url_suffix'] = url
                        logger.info(f"☁️  Nouvelle série (Gist): {nom}")
                    else:
                        logger.info(f"☁️  Nouvelle série (Gist): {nom}")
                    
                    config.MANGAS_A_SUIVRE.append(new_serie)
                    modifs += 1
                    liste_modifiee = True
            
            # Vider series_ajoutees après traitement (même si toutes les séries étaient déjà présentes)
            config.GIST_SERIES_CONFIG['series_ajoutees'] = []
            config.GIST_MODIFIED = True
            if liste_modifiee:
                logger.info(f"   🧹 Séries intégrées à {config.MANGAS_LISTE_FILE}, series_ajoutees vidé")
            else:
                logger.info(f"   🧹 series_ajoutees vidé (séries déjà présentes dans {config.MANGAS_LISTE_FILE})")
        
        # 1d. Importer les traductions personnalisées du Gist
        gist_traductions = config.GIST_SERIES_CONFIG.get('traductions', {})
        if gist_traductions:
            for serie_jp, titre_fr in gist_traductions.items():
                if serie_jp and titre_fr:
                    config.TRADUCTIONS_FR[serie_jp] = titre_fr
                    # Sauvegarder en BDD si disponible (erreur ignorée si BDD verrouillée)
                    if db:
                        try:
                            db.sauvegarder_traduction(serie_jp, titre_fr, source='gist', est_officielle=False)
                        except Exception as e:
                            logger.debug(f"Sauvegarde traduction ignorée (BDD): {e}")
                    logger.info(f"☁️  Traduction (Gist): {serie_jp[:25]}... → {titre_fr}")
            
            # Vider les traductions après import (elles sont en BDD et dans config.TRADUCTIONS_FR)
            config.GIST_SERIES_CONFIG['traductions'] = {}
            config.GIST_MODIFIED = True
            logger.info(f"   🧹 Traductions importées du Gist ({len(gist_traductions)}), traductions vidé")
    
    # ====== ÉTAPE 2: Sauvegarder mangas_liste.json si modifié ======
    if liste_modifiee:
        sauvegarder_mangas_liste()
    
    # ====== ÉTAPE 3: Charger depuis le fichier local (si présent) ======
    if not os.path.exists(config.SERIES_CONFIG_FILE):
        return
    
    try:
        with open(config.SERIES_CONFIG_FILE, 'r', encoding='utf-8') as f:
            local_config = json.load(f)
        
        urls_supp = local_config.get('urls_supplementaires', {})
        added = local_config.get('added', [])
        removed = local_config.get('removed', [])
        
        modifs = 0
        
        # 1. Fusionner les URLs supplémentaires avec les séries existantes
        if urls_supp:
            for manga in config.MANGAS_A_SUIVRE:
                nom = manga.get('nom', '')
                if nom in urls_supp:
                    existing_urls = manga.get('urls_supplementaires', [])
                    new_urls = urls_supp[nom]
                    # Fusionner sans doublons
                    all_urls = list(set(existing_urls + new_urls))
                    if all_urls:
                        manga['urls_supplementaires'] = all_urls
                        logger.info(f"🔗 {len(new_urls)} URL(s) supplémentaire(s) ajoutée(s) pour: {nom}")
                        modifs += len(new_urls)
        
        # 2. Ajouter les nouvelles séries
        if added:
            for serie in added:
                nom = serie.get('serie_jp', '')
                if nom and not any(m['nom'] == nom for m in config.MANGAS_A_SUIVRE):
                    config.MANGAS_A_SUIVRE.append({
                        'nom': nom,
                        'url_suffix': serie.get('url_suffix', nom),
                        'urls_supplementaires': serie.get('urls_supplementaires', [])
                    })
                    logger.info(f"➕ Nouvelle série ajoutée: {nom}")
                    modifs += 1
        
        # 3. Retirer les séries supprimées
        if removed:
            config.MANGAS_A_SUIVRE = [m for m in config.MANGAS_A_SUIVRE if m['nom'] not in removed]
            if removed:
                logger.info(f"🗑️ {len(removed)} série(s) retirée(s)")
                modifs += len(removed)
        
        # 4. Ajouter les traductions personnalisées au dictionnaire
        traductions = local_config.get('traductions', {})
        if traductions:
            for serie_jp, titre_fr in traductions.items():
                if serie_jp and titre_fr:
                    config.TRADUCTIONS_FR[serie_jp] = titre_fr
                    logger.info(f"🏷️ Traduction ajoutée: {serie_jp[:30]}... → {titre_fr}")
                    modifs += 1
        
        if modifs > 0:
            logger.info(f"📋 Configuration chargée depuis {config.SERIES_CONFIG_FILE}")
            # Renommer le fichier pour éviter de re-appliquer
            backup_name = f"series_config_applied_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            os.rename(config.SERIES_CONFIG_FILE, backup_name)
            logger.info(f"   → Fichier renommé en {backup_name}")
            
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"⚠️  Erreur lecture {config.SERIES_CONFIG_FILE}: {e}")


def git_push():
    """
    Push les fichiers modifiés (BDD + mangas_liste.json) vers le dépôt Git.
    Utilisé en fin de run pour sauvegarder les changements.
    """
    try:
        files_to_push = ['manga_alerts.db', 'mangas_liste.json', 'manga_collection.json']
        
        # Vérifier qu'on est dans un repo git
        result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            logger.warning("   ⚠️  Pas de dépôt Git détecté, skip git push")
            return False
        
        # Add les fichiers modifiés
        for f in files_to_push:
            if os.path.exists(f):
                subprocess.run(['git', 'add', f], capture_output=True, timeout=10)
        
        # Commit
        date_str = datetime.now().strftime('%Y-%m-%d %H:%M')
        result = subprocess.run(
            ['git', 'commit', '-m', f'Auto-update {date_str}'],
            capture_output=True, text=True, timeout=10
        )
        
        if 'nothing to commit' in result.stdout:
            logger.info("   ℹ️  Rien à commiter")
            return True
        
        # Push
        result = subprocess.run(['git', 'push'], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            logger.info("   ✅ Git push réussi")
            return True
        else:
            logger.warning(f"   ⚠️  Git push échoué: {result.stderr[:100]}")
            return False
            
    except Exception as e:
        logger.warning(f"   ⚠️  Erreur git push: {str(e)[:80]}")
        return False
