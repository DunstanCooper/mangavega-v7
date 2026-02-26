#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MangaVega Tracker - Pipeline de recherche et traitement
"""

import asyncio
import random
import re
from datetime import datetime, timedelta
from urllib.parse import quote_plus
from typing import List, Dict, Optional, Set
from bs4 import BeautifulSoup

import aiohttp

import config
from database import DatabaseManager
from utils import (
    strip_type_suffix, est_format_papier, est_asin_hors_sujet_manuel,
    normaliser_editeur, editeur_match, convertir_editeur_romaji,
    extraire_editeur, extraire_asin, est_asin_papier, est_ebook,
    normaliser_titre, normaliser_url, extraire_numero_tome, analyser_tomes_manquants
)
from scraper import (
    get_html, extraire_version_papier, extraire_infos_produit,
    extraire_item_amazon, extraire_infos_featured,
    extraire_volumes_depuis_page, extraire_volumes_depuis_page_flat
)

logger = config.logger


async def rechercher_volumes_via_bulk_etendu(session: aiohttp.ClientSession, db: 'DatabaseManager',
                                              nom_serie: str, volumes_connus: List[Dict],
                                              asins_connus: Set[str], asins_rejetes: Set[str],
                                              logger) -> List[Dict]:
    """
    Recherche étendue des volumes manquants via les sections Bulk de plusieurs volumes connus.
    
    Pour chaque volume connu, explore les sections Bulk/Frequently bought/From Publisher
    pour trouver des volumes qui n'auraient pas été détectés.
    
    Retourne: liste des nouveaux volumes trouvés
    """
    nouveaux_volumes = []
    
    if len(volumes_connus) < 2:
        return nouveaux_volumes
    
    # Prendre jusqu'à 3 volumes différents pour explorer leurs Bulk
    # Préférer les volumes avec des numéros différents (début, milieu, fin)
    volumes_tries = sorted(
        [v for v in volumes_connus if v.get('asin') and str(v.get('tome', '')).isdigit()],
        key=lambda x: int(x['tome'])
    )
    
    if not volumes_tries:
        return nouveaux_volumes
    
    # Sélectionner 3 volumes représentatifs
    asins_a_explorer = []
    if len(volumes_tries) >= 3:
        asins_a_explorer = [
            volumes_tries[0]['asin'],  # Premier tome
            volumes_tries[len(volumes_tries)//2]['asin'],  # Milieu
            volumes_tries[-1]['asin']  # Dernier
        ]
    else:
        asins_a_explorer = [v['asin'] for v in volumes_tries[:3]]
    
    # Dédupliquer
    asins_a_explorer = list(dict.fromkeys(asins_a_explorer))
    
    logger.info(f"   🔄 Recherche Bulk étendue via {len(asins_a_explorer)} volume(s)...")
    
    for asin_source in asins_a_explorer:
        try:
            # Utiliser extraire_volumes_depuis_page pour explorer les sections liées
            url_source = f"https://www.amazon.co.jp/dp/{asin_source}"
            
            # CASCADE: D'abord Bulk, puis Publisher, puis Carrousels
            # Les carrousels nécessitent un filtre hors-sujet (appliqué plus bas)
            result = await extraire_volumes_depuis_page(session, url_source, nom_serie, debug=False)
            volumes_lies = extraire_volumes_depuis_page_flat(result)
            
            for vol_url in volumes_lies:
                # Extraire l'ASIN
                match = re.search(r'/dp/([A-Z0-9]{10})', vol_url)
                if not match:
                    continue
                    
                asin_vol = match.group(1)
                
                # Skip si déjà connu ou rejeté
                if asin_vol in asins_connus or asin_vol in asins_rejetes:
                    continue
                
                # Skip si déjà en cache
                if db.est_verifie_aujourdhui(asin_vol):
                    continue
                
                # Récupérer les infos du produit
                html_vol = await get_html(session, vol_url)
                if not html_vol:
                    continue
                
                infos = await extraire_infos_produit(html_vol)
                if not infos or not infos.get('titre'):
                    continue
                
                # Vérifier que c'est un livre papier
                format_livre = infos.get('format', '')
                if not est_format_papier(format_livre):
                    continue
                
                # NOUVEAU: Vérifier que le titre contient le nom de la série
                # (les carrousels Amazon affichent des séries "similaires" qui sont hors-sujet)
                titre_volume = infos.get('titre', '')
                nom_serie_clean = strip_type_suffix(nom_serie)  # Sans [LN]/[MANGA] pour comparer au titre Amazon
                nom_serie_court = nom_serie_clean.split()[0] if ' ' in nom_serie_clean else nom_serie_clean
                
                # Normaliser pour gérer Ζ vs Z, pleine largeur, etc.
                titre_norm = normaliser_titre(titre_volume).lower()
                serie_norm = normaliser_titre(nom_serie_clean).lower()
                serie_court_norm = normaliser_titre(nom_serie_court).lower()
                
                if serie_norm not in titre_norm and serie_court_norm not in titre_norm:
                    logger.debug(f"      ⏭️ {asin_vol}: Hors-sujet (titre: {titre_volume[:40]}...)")
                    # Sauvegarder dans le cache pour ne pas re-vérifier
                    db.sauvegarder_verification(
                        asin_vol,
                        infos.get('date', ''),
                        infos.get('tome', '?'),
                        infos.get('titre', ''),
                        infos.get('editeur', 'Inconnu')
                    )
                    continue
                
                # Trouvé !
                tome = infos.get('tome', '?')
                logger.info(f"      ✅ Nouveau volume trouvé: {asin_vol} (T{tome})")
                
                # Sauvegarder
                db.sauvegarder_verification(
                    asin_vol,
                    infos.get('date', ''),
                    str(tome),
                    infos.get('titre', ''),
                    infos.get('editeur', 'Inconnu')
                )
                
                # Sauvegarder dans la table volumes (remplace sauvegarder_produit_papier)
                tome_int = None
                try:
                    if tome and str(tome).isdigit():
                        tome_int = int(tome)
                except (ValueError, TypeError):
                    pass
                db.sauvegarder_volume(
                    serie_jp=nom_serie, serie_fr=None,
                    tome=tome_int, asin=asin_vol, url=vol_url,
                    date_sortie_jp=infos.get('date', ''),
                    titre_volume=infos.get('titre', ''),
                    editeur=infos.get('editeur', 'Inconnu')
                )
                asins_connus.add(asin_vol)
                
                nouveaux_volumes.append({
                    'nom': nom_serie,
                    'tome': tome,
                    'date': infos.get('date', ''),
                    'asin': asin_vol,
                    'url': vol_url,
                    'editeur': infos.get('editeur', 'Inconnu'),
                    'titre_volume': infos.get('titre', ''),
                    'source': 'bulk_etendu',
                    'serie_recherchee': nom_serie  # Même série
                })
                
                await asyncio.sleep(random.uniform(0.3, 0.6))
                
        except Exception as e:
            logger.debug(f"      ⚠️ Erreur exploration {asin_source}: {e}")
            continue
    
    return nouveaux_volumes


async def corriger_tomes_manquants(session: aiohttp.ClientSession, db: 'DatabaseManager', logger) -> int:
    """
    Recherche les numéros de tome pour les volumes validés manuellement
    qui ont un tome manquant (?, N/A, NULL, 0).
    
    Cette fonction est utile quand l'utilisateur ajoute manuellement une URL
    d'un tome manquant et le valide sans que le script ait pu extraire le numéro.
    
    Retourne: nombre de tomes corrigés
    """
    # Récupérer les volumes validés sans tome
    volumes_sans_tome = db.get_volumes_valides_sans_tome()
    
    if not volumes_sans_tome:
        return 0
    
    logger.info(f"\n🔍 Correction des tomes manquants: {len(volumes_sans_tome)} volume(s) à vérifier...")
    corriges = 0
    
    for vol in volumes_sans_tome:
        asin = vol['asin']
        url = vol.get('url') or f"https://www.amazon.co.jp/dp/{asin}"
        
        try:
            logger.debug(f"   📖 Vérification {asin}...")
            
            html = await get_html(session, url)
            if not html:
                continue
            
            infos = await extraire_infos_produit(html)
            if not infos:
                continue
            
            tome = infos.get('tome')
            
            # Vérifier si le tome est valide (nombre)
            if tome and str(tome).isdigit() and int(tome) > 0:
                tome_int = int(tome)
                db.update_tome_volume(asin, tome_int)
                logger.info(f"   ✅ {asin}: Tome corrigé → T{tome_int}")
                corriges += 1
            else:
                # Essayer d'extraire depuis le titre
                titre = infos.get('titre', '') or vol.get('titre_volume', '')
                tome_extrait = extraire_numero_tome(titre)
                
                if tome_extrait and str(tome_extrait).isdigit() and int(tome_extrait) > 0:
                    tome_int = int(tome_extrait)
                    db.update_tome_volume(asin, tome_int)
                    logger.info(f"   ✅ {asin}: Tome extrait du titre → T{tome_int}")
                    corriges += 1
                else:
                    logger.debug(f"   ⏭️ {asin}: Tome toujours inconnu")
            
            await asyncio.sleep(random.uniform(0.3, 0.5))
            
        except Exception as e:
            logger.debug(f"   ⚠️ Erreur {asin}: {e}")
            continue
    
    if corriges > 0:
        logger.info(f"   📝 {corriges} tome(s) corrigé(s)")
    
    return corriges


async def rechercher_traductions(session: aiohttp.ClientSession, titre_japonais: str, db: DatabaseManager) -> tuple:
    """
    Recherche la traduction FR pour un titre japonais.
    
    V6.1 : Simplifié — uniquement config.TRADUCTIONS_MANUELLES et BDD.
    Logique:
    1. Vérifie en BDD si la traduction existe déjà
    2. Si titre FR manquant → cherche dans config.TRADUCTIONS_MANUELLES
    3. Sauvegarde en BDD
    
    Retourne: (titre_fr, source_fr, est_officielle)
    """
    
    # Récupérer la traduction existante en BDD
    trad_existante = db.get_traduction_complete(titre_japonais)
    
    titre_fr = trad_existante['titre_francais'] if trad_existante else None
    source_fr = trad_existante['source'] if trad_existante else None
    est_officielle = trad_existante['est_officielle'] if trad_existante else False
    
    if titre_fr:
        logger.info(f"    💾 FR existant: {titre_fr}")
        return titre_fr, source_fr, est_officielle
    
    # Chercher dans config.TRADUCTIONS_MANUELLES
    # Essayer avec le nom exact, puis sans suffixe [MANGA]/[LN]
    nom_clean = strip_type_suffix(titre_japonais)
    
    if titre_japonais in config.TRADUCTIONS_MANUELLES:
        titre_fr = config.TRADUCTIONS_MANUELLES[titre_japonais]
        source_fr = 'manuel'
        est_officielle = True
    elif nom_clean in config.TRADUCTIONS_MANUELLES:
        titre_fr = config.TRADUCTIONS_MANUELLES[nom_clean]
        source_fr = 'manuel'
        est_officielle = True
    
    if titre_fr:
        logger.info(f"    📝 FR trouvé (manuel): {titre_fr}")
        db.sauvegarder_traduction_complete(
            titre_japonais, 
            titre_francais=titre_fr,
            source=source_fr,
            est_officielle=est_officielle
        )
        return titre_fr, source_fr, est_officielle
    
    # Fallback : chercher la traduction de la variante LN/MANGA de la même série
    # Ex: si on cherche "Titre [LN]" et qu'il existe "Titre [MANGA]" avec une traduction
    nom_base = strip_type_suffix(titre_japonais)
    if nom_base != titre_japonais:  # Le titre avait un suffixe
        # Chercher toutes les variantes possibles
        variantes = []
        if titre_japonais.endswith(' [LN]'):
            variantes.append(nom_base + ' [MANGA]')
        elif titre_japonais.endswith(' [MANGA]'):
            variantes.append(nom_base + ' [LN]')
        # Aussi chercher sans suffixe (cas ancien format)
        variantes.append(nom_base)
        
        for variante in variantes:
            trad_variante = db.get_traduction_complete(variante)
            if trad_variante and trad_variante.get('titre_francais'):
                titre_fr = trad_variante['titre_francais']
                source_fr = f"fallback_{trad_variante.get('source', 'auto')}"
                est_officielle = trad_variante.get('est_officielle', False)
                logger.info(f"    🔄 FR trouvé via variante [{variante}]: {titre_fr}")
                db.sauvegarder_traduction_complete(
                    titre_japonais,
                    titre_francais=titre_fr,
                    source=source_fr,
                    est_officielle=est_officielle
                )
                return titre_fr, source_fr, est_officielle
    
    return titre_fr, source_fr, est_officielle


async def rechercher_manga(session: aiohttp.ClientSession, db: DatabaseManager, nom: str, url_suffix: str, filtre: str = None, serie_id: str = None, asin_reference: str = None, urls_supplementaires: list = None) -> tuple[List[Dict], List[Dict]]:
    """Recherche pour un manga - Retourne (nouveautés, tous_papiers)
    
    V6.1 : Pipeline simplifié en 2 phases
    - Phase A : Découverte (collecter des ASINs candidats)
    - Phase B : Vérification (valider chaque ASIN, filtrer éditeur, détecter nouveautés)
    
    Args:
        session: Session HTTP
        db: Gestionnaire de base de données
        nom: Nom japonais de la série (avec suffixe [MANGA]/[LN])
        url_suffix: Suffixe pour la recherche Amazon
        filtre: "ln_only", "manga_only", "both" ou None
        serie_id: Identifiant unique pour distinguer manga/LN
        asin_reference: ASIN de départ pour les nouvelles séries
        urls_supplementaires: URLs Amazon ajoutées manuellement
    """
    
    # === INIT ===
    nom_bdd = serie_id if serie_id else nom
    
    # Récupérer les infos de traduction
    traduction_info = db.get_traduction_info(nom_bdd)
    
    logger.info("\n" + "="*80)
    if traduction_info:
        traduction_existante = traduction_info['titre_francais']
        est_officielle = traduction_info['est_officielle']
        source = traduction_info['source']
        
        logger.info(f"📚 MANGA: {nom}")
        if serie_id:
            logger.info(f"   🔖 Serie ID: {serie_id}")
        if filtre:
            filtre_label = {"ln_only": "📖 LN uniquement", "manga_only": "📕 Manga uniquement", "both": "📚 LN + Manga"}.get(filtre, filtre)
            logger.info(f"   {filtre_label}")
        if est_officielle:
            logger.info(f"   🇫🇷 {traduction_existante} (officielle, {source})")
        else:
            logger.info(f"   🌍 {traduction_existante} (fallback, {source})")
    else:
        traduction_existante = None
        logger.info(f"📚 MANGA: {nom}")
        if serie_id:
            logger.info(f"   🔖 Serie ID: {serie_id}")
        if filtre:
            filtre_label = {"ln_only": "📖 LN uniquement", "manga_only": "📕 Manga uniquement", "both": "📚 LN + Manga"}.get(filtre, filtre)
            logger.info(f"   {filtre_label}")
    logger.info("="*80)
    
    if traduction_existante and nom_bdd not in config.TRADUCTIONS_FR:
        config.TRADUCTIONS_FR[nom_bdd] = traduction_existante
    
    # =========================================================================
    # PHASE A : DÉCOUVERTE — Collecter des ASINs candidats
    # =========================================================================
    
    # Structure : {asin: url} — dédupliqué naturellement par le dict
    candidats = {}
    asin_deja_vus = set()  # Inclut ebooks et hors-sujet pour ne pas les re-traiter
    editeur_officiel_serie = db.get_editeur_officiel(nom_bdd)
    
    # --- A0. Charger les volumes déjà connus depuis la BDD ---
    volumes_connus = db.get_volumes_connus(nom_bdd)
    for asin_connu, url_connu in volumes_connus.items():
        if not est_asin_hors_sujet_manuel(asin_connu):
            candidats[asin_connu] = url_connu
            asin_deja_vus.add(asin_connu)
    
    # Charger l'historique Featured (tous les ASINs déjà croisés et classifiés)
    featured_deja_vus = db.get_featured_history_asins(nom_bdd, filtre)
    asin_deja_vus |= featured_deja_vus
    
    nb_connus = len(candidats)
    nb_featured_cache = len(featured_deja_vus - set(candidats.keys()))  # Exclure les doublons volumes
    if nb_connus > 0:
        logger.info(f"💾 {nb_connus} volume(s) déjà connu(s) en BDD")
    if nb_featured_cache > 0:
        featured_stats = db.get_featured_stats(nom_bdd)
        stats_detail = " | ".join(f"{v} {k}" for k, v in sorted(featured_stats.items()))
        logger.info(f"💾 {nb_featured_cache} ASIN(s) déjà classifié(s) (skip) [{stats_detail}]")
    
    featured_metadata = {}  # Infos extraites depuis Featured (fallback si captcha /dp/)
    bulk_tomes_mapping = {}  # {asin: tome_num} — tomes extraits du Bulk

    # --- Helper : exécuter le Bulk depuis un ASIN et intégrer les résultats ---
    bulk_effectue = False
    bulk_asins_essayes = set()  # ASINs déjà tentés pour le Bulk (évite les doublons)

    async def executer_bulk(asin_source: str, inclure_frequently_bought: bool = False) -> bool:
        """
        Exécute le Bulk depuis un ASIN, ajoute les résultats à candidats{}.
        Retourne True si de nouveaux volumes ont été trouvés.
        bulk_effectue est levé uniquement si la section Bulk est effectivement trouvée,
        permettant de retenter avec un autre ASIN si la page n'a pas de section Bulk statique.
        """
        nonlocal bulk_effectue
        if bulk_effectue or asin_source in bulk_asins_essayes:
            return False
        bulk_asins_essayes.add(asin_source)

        logger.info(f"🔄 Exploration Bulk depuis [{asin_source}]...\n")
        
        sources_bulk = ["bulk", "publisher"]
        if inclure_frequently_bought:
            sources_bulk.append("frequently_bought")
        
        result_bulk = await extraire_volumes_depuis_page(
            session, asin_source, nom,
            debug=False,
            sources=sources_bulk
        )
        
        # Section trouvée → marquer comme effectué (sinon on retente avec le prochain ASIN)
        if result_bulk.get("bulk") or result_bulk.get("frequently_bought"):
            bulk_effectue = True
        else:
            logger.info(f"   ℹ️  Pas de section Bulk statique sur [{asin_source}], retentable depuis un autre ASIN")

        # Récupérer le mapping ASIN→tome depuis le Bulk
        for b_asin, b_tome in result_bulk.get("bulk_tomes", {}).items():
            bulk_tomes_mapping[b_asin] = b_tome

        trouva_nouveau = False
        for source_name in ["bulk", "publisher", "frequently_bought"]:
            for vol_asin in result_bulk.get(source_name, []):
                if not vol_asin or vol_asin in asin_deja_vus:
                    continue
                if not est_asin_papier(vol_asin):
                    asin_deja_vus.add(vol_asin)
                    db.sauvegarder_featured(nom_bdd, vol_asin, 'non_papier', 'bulk')
                    continue
                
                candidats[vol_asin] = f"https://www.amazon.co.jp/dp/{vol_asin}"
                asin_deja_vus.add(vol_asin)
                db.sauvegarder_featured(nom_bdd, vol_asin, 'papier', 'bulk')
                
                if vol_asin not in volumes_connus:
                    trouva_nouveau = True
                    tome_info = f" (T{bulk_tomes_mapping[vol_asin]})" if vol_asin in bulk_tomes_mapping else ""
                    logger.info(f"   ✨ [{vol_asin}] Nouveau volume{tome_info} (source: {source_name})")
        
        return trouva_nouveau
    
    # --- A1. ASIN de référence (série ajoutée manuellement) ---
    if not candidats and asin_reference:
        # Vérifier si l'ASIN de référence est un ebook (commence par B)
        if not est_asin_papier(asin_reference):
            logger.info(f"⚠️  ASIN de référence [{asin_reference}] semble être un ebook, recherche version papier...")
            try:
                url_ebook = f"https://www.amazon.co.jp/dp/{asin_reference}"
                html_ebook = await get_html(session, url_ebook)
                if html_ebook:
                    url_papier = await extraire_version_papier(html_ebook)
                    if url_papier:
                        asin_papier = extraire_asin(url_papier)
                        if asin_papier and asin_papier != "?" and est_asin_papier(asin_papier):
                            logger.info(f"   ✅ Version papier trouvée: [{asin_papier}] (remplace ebook [{asin_reference}])")
                            asin_reference = asin_papier
                        else:
                            logger.warning(f"   ⚠️  Pas de version papier trouvée, utilisation de l'ebook comme fallback")
                    else:
                        logger.warning(f"   ⚠️  Pas de lien papier sur la page ebook, utilisation comme fallback")
            except Exception as e:
                logger.warning(f"   ⚠️  Erreur vérification ebook: {e}")
        
        url_reference = f"https://www.amazon.co.jp/dp/{asin_reference}"
        candidats[asin_reference] = url_reference
        asin_deja_vus.add(asin_reference)
        logger.info(f"🎯 NOUVELLE SÉRIE - ASIN de référence: {asin_reference}")
    
    # --- A2. URLs supplémentaires (depuis Gist, plus fiables que Featured) ---
    if urls_supplementaires:
        logger.info(f"\n🔗 {len(urls_supplementaires)} URL(s) supplémentaire(s)...")
        for url_supp in urls_supplementaires:
            match_asin = re.search(r'/dp/([A-Z0-9]{10})', url_supp)
            if not match_asin:
                continue
            asin_supp = match_asin.group(1)
            if asin_supp not in asin_deja_vus:
                candidats[asin_supp] = url_supp
                asin_deja_vus.add(asin_supp)
                logger.info(f"   📖 [{asin_supp}] Ajouté depuis URL manuelle")
    
    # --- BULK : dès qu'on a un premier ASIN papier, explorer ses volumes liés ---
    # Se déclenche après A0/A1/A2, sur le premier candidat papier disponible.
    # Une seule exécution : si A0 fournit des candidats, Bulk tourne ici.
    # Sinon, il tournera après Featured (A4) si un nouveau papier est trouvé.
    if candidats:
        premier_asin = next(iter(candidats))
        inclure_fb = True  # FBT activé comme source complémentaire (même pour séries existantes)
        await executer_bulk(premier_asin, inclure_frequently_bought=inclure_fb)
    
    # --- A2. Source FEATURED (recherche Amazon par nom) ---
    # Plus de cooldown : grâce à featured_history, les ASINs déjà classifiés sont
    # skippés instantanément (0 fetch HTTP). Seuls les vrais nouveaux ASINs coûtent.
    stats = {'ebook': 0, 'sponsorise': 0, 'hors_sujet': 0, 'papier': 0, 'sans_info': 0, 'deja_vu': 0}
    
    # Construction de l'URL de recherche
    if len(url_suffix) <= 10 and url_suffix not in config.TITRES_GENERIQUES:
        recherche_exacte = url_suffix
    else:
        recherche_exacte = f'"{url_suffix}"'
    
    titre_cle = normaliser_titre(url_suffix[:8] if len(url_suffix) >= 8 else url_suffix)
    
    # Progression : déterminer les pages à scanner
    derniere_page_traitee, exploration_complete = db.get_featured_progression(nom_bdd)
    
    # Toujours scanner page 1 (détection nouveautés en tête de résultats)
    # Puis progresser au-delà si tout est déjà connu
    pages_a_scanner = [1]
    if exploration_complete:
        # Tout a déjà été exploré → page 1 suffit pour détecter les nouveautés
        pass
    else:
        # Ajouter les pages suivantes à explorer (progression)
        for p in range(max(2, derniere_page_traitee + 1), derniere_page_traitee + 4):  # max 3 nouvelles pages par run
            pages_a_scanner.append(p)
    
    # Log de progression Featured
    if exploration_complete:
        logger.info(f"📄 Featured: exploration complète (page 1 uniquement pour nouveautés)")
    elif derniere_page_traitee > 0:
        logger.info(f"📄 Featured: reprise page {derniere_page_traitee + 1} (pages déjà traitées: 1-{derniere_page_traitee})")
    else:
        logger.info(f"📄 Featured: première exploration (pages {pages_a_scanner})")
    
    nouveaux_trouves_featured = False  # Si on trouve un nouveau candidat, on s'arrête de progresser
    page_max_atteinte = derniere_page_traitee
    
    for page_num in pages_a_scanner:
        if nouveaux_trouves_featured and page_num > 1:
            # On a trouvé du nouveau → on s'arrête, le reste au prochain run
            break
        
        if page_num == 1:
            url_page = f"https://www.amazon.co.jp/s?k={quote_plus(recherche_exacte)}&i=stripbooks&s=relevancerank&rh=p_6%3AAN1VRQENFRJN5"
        else:
            url_page = f"https://www.amazon.co.jp/s?k={quote_plus(recherche_exacte)}&i=stripbooks&s=relevancerank&rh=p_6%3AAN1VRQENFRJN5&page={page_num}"
        
        if page_num == 1:
            logger.info(f"\n🔍 Recherche Featured...\n")
        else:
            logger.info(f"\n🔍 Featured page {page_num}...\n")
        
        html = await get_html(session, url_page)
        
        if not html:
            if page_num == 1 and not candidats:
                logger.warning("❌ Impossible de récupérer la page Featured")
                return [], []
            elif page_num == 1:
                logger.warning("❌ Featured inaccessible, utilisation des volumes connus")
            break
        
        soup = BeautifulSoup(html, 'lxml')
        items = soup.select('.s-result-item')

        # Détecter la dernière vraie page via la pagination Amazon :
        # si le bouton "次へ" (s-pagination-next) est absent ou désactivé → dernière page
        btn_next = soup.select_one('.s-pagination-next')
        derniere_vraie_page = (btn_next is None) or ('s-pagination-disabled' in btn_next.get('class', []))

        if not items:
            # Page vide → exploration terminée
            if page_num > 1:
                db.set_featured_progression(nom_bdd, page_num - 1, complete=True)
                logger.info(f"   📄 Page {page_num} vide → exploration Featured terminée")
            break
        
        logger.info(f"🔍 Analyse de {len(items)} résultats Featured (page {page_num})...")
        logger.info("-" * 80)
        
        page_stats = {'nouveaux': 0, 'deja_vus': 0}
        
        for item in items:
            titre_txt, url_complete, asin = extraire_item_amazon(item)
            if not titre_txt:
                stats['sans_info'] += 1
                continue
            
            if asin and asin in asin_deja_vus:
                page_stats['deja_vus'] += 1
                stats['deja_vu'] += 1
                continue
            
            source_label = f'featured_p{page_num}'
            
            # Filtre manuel hors-sujet (rejeté depuis viewer)
            if est_asin_hors_sujet_manuel(asin):
                stats['hors_sujet'] += 1
                asin_deja_vus.add(asin)
                db.sauvegarder_featured(nom_bdd, asin, 'hors_sujet_titre', source_label, titre_txt)
                logger.info(f"  🚫 [{asin}] Rejeté manuellement → saved")
                continue
            
            # Filtre titre
            titre_txt_normalise = normaliser_titre(titre_txt)
            if titre_cle not in titre_txt_normalise:
                stats['hors_sujet'] += 1
                asin_deja_vus.add(asin)
                db.sauvegarder_featured(nom_bdd, asin, 'hors_sujet_titre', source_label, titre_txt)
                logger.info(f"  ❌ [{asin}] Hors-sujet titre: {titre_txt[:40]}... → saved")
                continue
            
            # Filtre produits dérivés (liste centralisée dans config.py)
            if any(mot in titre_txt for mot in config.MOTS_CLES_DERIVES):
                stats['hors_sujet'] += 1
                asin_deja_vus.add(asin)
                db.sauvegarder_featured(nom_bdd, asin, 'derive', source_label, titre_txt)
                logger.info(f"  ❌ [{asin}] Produit dérivé: {titre_txt[:40]}... → saved")
                continue
            
            # Sponsorisé
            if '/sspa/click' in url_complete or 'sspa' in url_complete:
                stats['sponsorise'] += 1
                asin_deja_vus.add(asin)
                db.sauvegarder_featured(nom_bdd, asin, 'sponsorise', source_label, titre_txt)
                logger.info(f"  💰 [{asin}] Sponsorisé: {titre_txt[:40]}... → saved")
                continue
            
            # Ebook → chercher version papier (SANS Bulk en cascade)
            if est_ebook(url_complete, titre_txt):
                stats['ebook'] += 1
                asin_deja_vus.add(asin)
                
                if filtre == "ln_only":
                    format_cible = "ln"
                elif filtre == "both":
                    format_cible = "all"
                else:
                    format_cible = "manga"
                
                html_ebook = await get_html(session, url_complete)
                if html_ebook:
                    logger.info(f"  📱 [{asin}] Ebook → recherche version papier ({format_cible})...")
                    url_papier = await extraire_version_papier(html_ebook, format_cible=format_cible, debug=(filtre == "ln_only"))
                    if url_papier:
                        asin_papier = extraire_asin(url_papier)
                        if asin_papier and est_asin_papier(asin_papier) and asin_papier not in asin_deja_vus:
                            candidats[asin_papier] = url_papier
                            asin_deja_vus.add(asin_papier)
                            stats['papier'] += 1
                            page_stats['nouveaux'] += 1
                            nouveaux_trouves_featured = True
                            logger.info(f"      🔗 Version papier: [{asin_papier}]")
                        db.sauvegarder_featured(nom_bdd, asin, 'ebook', source_label, titre_txt, asin_papier)
                    else:
                        db.sauvegarder_featured(nom_bdd, asin, 'ebook', source_label, titre_txt)
                else:
                    db.sauvegarder_featured(nom_bdd, asin, 'ebook', source_label, titre_txt)
                continue
            
            # Lots/Sets
            if '巻セット' in titre_txt or ('セット' in titre_txt and ('1-' in titre_txt or '全巻' in titre_txt)):
                stats['hors_sujet'] += 1
                asin_deja_vus.add(asin)
                db.sauvegarder_featured(nom_bdd, asin, 'lot', source_label, titre_txt)
                logger.info(f"  📦 [{asin}] Lot/Set: {titre_txt[:40]}... → saved")
                continue
            
            # Non-papier (ASIN B*)
            if not est_asin_papier(asin):
                stats['ebook'] += 1
                asin_deja_vus.add(asin)
                db.sauvegarder_featured(nom_bdd, asin, 'non_papier', source_label, titre_txt)
                logger.info(f"  📱 [{asin}] Non-papier (B*): {titre_txt[:40]}... → saved")
                continue
            
            # C'est un papier valide !
            logger.info(f"  ✅ Papier [{asin}] {titre_txt[:50]}...")
            candidats[asin] = url_complete
            asin_deja_vus.add(asin)
            stats['papier'] += 1
            page_stats['nouveaux'] += 1
            nouveaux_trouves_featured = True
            db.sauvegarder_featured(nom_bdd, asin, 'papier', source_label, titre_txt)
            
            # Extraire les métadonnées directement depuis Featured
            feat_infos = extraire_infos_featured(item, titre_txt)
            if feat_infos:
                featured_metadata[asin] = feat_infos
        
        logger.info("-" * 80)
        logger.info(f"📊 Page {page_num}: {page_stats['nouveaux']} nouveau(x) | {page_stats['deja_vus']} déjà vu(s)")

        # Arrêt si Amazon signale qu'il n'y a pas de page suivante :
        # 1. Bouton "次へ" absent ou désactivé (signal officiel Amazon)
        # 2. Fallback : page creuse < 8 items (Amazon retourne ~16-24 items/page normalement)
        if derniere_vraie_page:
            db.set_featured_progression(nom_bdd, page_num, complete=True)
            logger.info(f"   📄 Page {page_num}: pas de page suivante (pagination) → exploration terminée")
            break
        if page_num > 1 and len(items) < 8:
            db.set_featured_progression(nom_bdd, page_num, complete=True)
            logger.info(f"   📄 Page {page_num} creuse ({len(items)} items < 8) → exploration terminée")
            break

        # Mettre à jour la progression
        if page_num > page_max_atteinte:
            page_max_atteinte = page_num
            db.set_featured_progression(nom_bdd, page_num)
    
    # --- BULK post-Featured : si pas encore fait et Featured a trouvé des papiers ---
    if not bulk_effectue and candidats:
        # Préférer un ASIN du bon type pour le Bulk (manga avec コミック, LN avec 文庫)
        # pour éviter de lancer le Bulk sur un artbook ou un produit du mauvais type
        asin_bulk = None
        for asin_c in candidats:
            meta = featured_metadata.get(asin_c, {})
            titre_c = meta.get('titre', '')
            if filtre == "ln_only" and '文庫' in titre_c:
                asin_bulk = asin_c
                break
            elif filtre != "ln_only" and ('コミック' in titre_c or 'コミックス' in titre_c):
                asin_bulk = asin_c
                break
        if not asin_bulk:
            asin_bulk = next(iter(candidats))
        await executer_bulk(asin_bulk)
        # Retry sur les autres candidats si la section Bulk était absente
        if not bulk_effectue:
            for asin_c in candidats:
                await executer_bulk(asin_c)  # no-op si déjà essayé (bulk_asins_essayes)
                if bulk_effectue:
                    break
    
    # --- Bilan Phase A ---
    nb_nouveaux = len(candidats) - nb_connus
    logger.info(f"\n📦 Phase A terminée: {len(candidats)} candidat(s) ({nb_connus} connus + {nb_nouveaux} nouveaux)")
    
    if len(candidats) == 0:
        logger.info("")
        return [], []
    
    # =========================================================================
    # PHASE B : VÉRIFICATION — Valider chaque ASIN
    # =========================================================================
    
    logger.info(f"\n🔍 Vérification des {len(candidats)} produit(s) papier...")
    logger.info("-" * 80)
    
    # Traductions
    titre_fr_serie = None

    
    # Vérifier si on doit chercher/re-vérifier la traduction
    besoin_traduction = not traduction_existante
    besoin_reverif = False
    raisons = []
    
    if traduction_info:
        if not traduction_info['est_officielle']:
            raisons.append("non-officielle")
            besoin_reverif = True
        if traduction_info['source'] == 'ai_generated':
            raisons.append("AI-generated")
            besoin_reverif = True
        dernier_check = traduction_info.get('derniere_verification')
        if dernier_check:
            try:
                jours = (datetime.now() - datetime.strptime(dernier_check, "%Y-%m-%d %H:%M:%S")).days
                if jours > 14:
                    raisons.append(f"vérifié il y a {jours}j")
                    besoin_reverif = True
            except:
                pass
    
    if besoin_traduction or besoin_reverif:
        if besoin_reverif:
            logger.info(f"🔄 Re-vérification traduction pour: {nom}")
        else:
            logger.info(f"🔍 Recherche traduction pour: {nom} ({', '.join(raisons)})")
        
        titre_fr_serie, source_fr, est_off = await rechercher_traductions(session, nom, db)
        
        if titre_fr_serie:
            config.TRADUCTIONS_FR[nom] = titre_fr_serie
            logger.info(f"✅ Traduction FR officielle: {titre_fr_serie}")
    
    urls_alertees = db.get_alertes_existantes(nom)
    nouveautes = []
    tous_papiers = []
    captcha_consecutifs = 0  # Circuit breaker captcha
    
    for asin, url_prod in candidats.items():
        url_norm = normaliser_url(url_prod)
        
        # Filtre hors-sujet manuel
        if est_asin_hors_sujet_manuel(asin):
            logger.info(f"  🚫 [{asin}] Marqué hors-sujet (skip)")
            continue
        
        est_deja_alerte = url_norm in urls_alertees
        
        # Précommandes : re-vérifier si date future
        force_refetch = False
        date_alerte_enregistree = None
        if est_deja_alerte:
            date_alerte_enregistree = db.get_alerte_date(nom_bdd, url_norm)
            if date_alerte_enregistree and date_alerte_enregistree != 'Date inconnue':
                try:
                    date_alerte = datetime.strptime(date_alerte_enregistree, "%Y/%m/%d")
                    if date_alerte > datetime.now():
                        force_refetch = True
                except (ValueError, TypeError):
                    pass
        
        # Cache vérification
        cache = db.est_verifie_aujourdhui(asin) if not force_refetch else None
        if cache:
            editeur_cache = cache.get('editeur', '')
            
            # Filtre éditeur
            if editeur_officiel_serie and editeur_cache and editeur_cache != 'Inconnu':
                if not editeur_match(editeur_cache, editeur_officiel_serie):
                    logger.info(f"  📚 [{asin}] Autre éditeur (cache): {editeur_cache} ≠ {editeur_officiel_serie} → skip")
                    continue
            
            if est_deja_alerte:
                logger.info(f"  ✓  [{asin}] Tome alerté précédemment (depuis cache)")
            else:
                logger.info(f"  💾 [{asin}] Utilisation du cache (vérifié aujourd'hui)")
            
            papier_info = {
                'nom': nom,
                'nom_fr': config.TRADUCTIONS_FR.get(nom, strip_type_suffix(nom)),
                'tome': cache['tome'],
                'date': cache['date'],
                'editeur': editeur_cache or 'Inconnu',
                'url': url_norm,
                'asin': asin,
                'couverture': '',
                'est_nouveaute': False,
                'deja_alerte': est_deja_alerte,
                'serie_recherchee': nom_bdd
            }
            
            if cache['date'] != 'Date inconnue' and cache['tome'] != 'N/A':
                if editeur_cache:
                    logger.info(f"      📖 {cache['date']}, Tome: {cache['tome']}, 📚 {editeur_cache}")
                else:
                    logger.info(f"      📖 {cache['date']}, Tome: {cache['tome']}")
            elif cache['date'] != 'Date inconnue':
                logger.info(f"      📅 {cache['date']}")
            
            tous_papiers.append(papier_info)
            
            # Nouveauté ?
            if not est_deja_alerte and cache['date'] != 'Date inconnue':
                try:
                    date_parsee = datetime.strptime(cache['date'], "%Y/%m/%d")
                    if date_parsee > config.DATE_SEUIL:
                        logger.info(f"      ✨ Nouveauté (depuis cache): {cache['date']}, Tome: {cache['tome']}")
                        papier_info['est_nouveaute'] = True
                        nouveautes.append(papier_info)
                        db.marquer_comme_alerte(nom, url_norm, cache['date'])
                        urls_alertees.add(url_norm)
                except ValueError:
                    pass
            continue
        
        # Pas de cache → fetch page produit
        if force_refetch:
            logger.info(f"  🔄 [{asin}] Re-vérification précommande ({date_alerte_enregistree})...")
        html_prod = await get_html(session, url_prod)
        if not html_prod:
            logger.warning(f"  ❌ [{asin}] Impossible de récupérer la page")
            logger.warning(f"      → {url_norm}")
            # Fallback cache ancien
            cache_fallback = db.get_verification_cache(asin)
            if cache_fallback:
                logger.info(f"      🔄 Utilisation du cache (fallback)")
                papier_info = {
                    'nom': nom, 'nom_fr': config.TRADUCTIONS_FR.get(nom, strip_type_suffix(nom)),
                    'tome': cache_fallback['tome'], 'date': cache_fallback['date'],
                    'editeur': cache_fallback.get('editeur', 'Inconnu'),
                    'url': url_norm, 'asin': asin, 'couverture': '',
                    'est_nouveaute': False, 'deja_alerte': est_deja_alerte,
                    'serie_recherchee': nom_bdd
                }
                tous_papiers.append(papier_info)
            continue
        
        infos = await extraire_infos_produit(html_prod, debug=False)
        
        # Fallback Bulk : si le tome n'est pas détecté depuis le titre, utiliser le mapping Bulk
        if 'tome' not in infos and asin in bulk_tomes_mapping:
            infos['tome'] = bulk_tomes_mapping[asin]
            logger.info(f"  📦 [{asin}] Tome depuis Bulk: T{infos['tome']}")
        
        if 'tome' not in infos and not infos.get('est_lot') and not infos.get('_page_invalide'):
            logger.warning(f"  ⚠️  [{asin}] Tome non détecté")
        
        # Page invalide (captcha, rate limit)
        if infos.get('_page_invalide'):
            if force_refetch:
                logger.warning(f"  ⚠️  [{asin}] Précommande non vérifiable ({infos['_page_invalide']}), date non comparée")
            else:
                logger.warning(f"  ⚠️  [{asin}] Page invalide: {infos['_page_invalide']}")
            logger.warning(f"      → {url_norm}")
            captcha_consecutifs += 1
            # Fallback 1 : cache de vérification (runs précédents)
            cache_fallback = db.get_verification_cache(asin)
            if cache_fallback:
                logger.info(f"      🔄 Utilisation du cache (fallback captcha)")
                papier_info = {
                    'nom': nom, 'nom_fr': config.TRADUCTIONS_FR.get(nom, strip_type_suffix(nom)),
                    'tome': cache_fallback['tome'], 'date': cache_fallback['date'],
                    'editeur': cache_fallback.get('editeur', 'Inconnu'),
                    'url': url_norm, 'asin': asin, 'couverture': '',
                    'est_nouveaute': False, 'deja_alerte': est_deja_alerte,
                    'serie_recherchee': nom_bdd
                }
                tous_papiers.append(papier_info)
            # Fallback 2 : infos extraites depuis Featured (même sans /dp/)
            elif asin in featured_metadata:
                feat = featured_metadata[asin]
                feat_tome = feat.get('tome', 'N/A')
                feat_date = feat.get('date', 'Date inconnue')
                feat_editeur = feat.get('editeur', 'Inconnu')
                feat_titre = feat.get('titre', '')
                logger.info(f"      📋 Utilisation des infos Featured: T{feat_tome}, {feat_date}, {feat_editeur}")
                
                # Sauvegarder dans le cache pour les prochains runs
                db.sauvegarder_verification(asin, feat_date, str(feat_tome), feat_titre[:100], feat_editeur)
                
                # Sauvegarder dans la table volumes
                tome_int = None
                try:
                    if feat_tome and feat_tome != 'N/A':
                        tome_int = int(feat_tome)
                except (ValueError, TypeError):
                    pass
                
                # Filtre format depuis Featured metadata
                feat_format = feat.get('format', '')
                if filtre != "both" and feat_format:
                    if filtre == "ln_only" and '文庫' not in feat_format:
                        logger.info(f"      📚 Format Featured non-LN: {feat_format} → skip")
                        continue
                    elif filtre != "ln_only" and 'コミック' not in feat_format:
                        logger.info(f"      📚 Format Featured non-manga: {feat_format} → skip")
                        continue
                
                # Filtre éditeur
                if editeur_officiel_serie and feat_editeur and feat_editeur != 'Inconnu':
                    if not editeur_match(feat_editeur, editeur_officiel_serie):
                        logger.info(f"      📚 Éditeur Featured: {feat_editeur} ≠ {editeur_officiel_serie} → skip")
                        continue
                
                db.sauvegarder_volume(
                    serie_jp=nom, serie_fr=titre_fr_serie or config.TRADUCTIONS_FR.get(nom),
                    tome=tome_int, asin=asin, url=url_norm,
                    date_sortie_jp=feat_date, titre_volume=feat_titre[:200],
                    editeur=feat_editeur
                )
                
                papier_info = {
                    'nom': nom, 'nom_fr': config.TRADUCTIONS_FR.get(nom, strip_type_suffix(nom)),
                    'tome': feat_tome, 'date': feat_date,
                    'editeur': feat_editeur, 'url': url_norm,
                    'asin': asin, 'couverture': '', 'est_nouveaute': False,
                    'deja_alerte': est_deja_alerte, 'serie_recherchee': nom_bdd
                }
                tous_papiers.append(papier_info)
                
                # Vérifier nouveauté
                if not est_deja_alerte and feat_date != 'Date inconnue':
                    try:
                        date_parsee = datetime.strptime(feat_date, "%Y/%m/%d")
                        if date_parsee > config.DATE_SEUIL:
                            logger.info(f"      ✨ Nouveauté (Featured): {feat_date}, Tome: {feat_tome}")
                            papier_info['est_nouveaute'] = True
                            nouveautes.append(papier_info)
                            db.marquer_comme_alerte(nom, url_norm, feat_date)
                            urls_alertees.add(url_norm)
                    except ValueError:
                        pass
            # Circuit breaker : après 3 captchas consécutifs, pause longue
            if captcha_consecutifs >= 3:
                remaining = len([a for a in candidats if a not in {p.get('asin') for p in tous_papiers}])
                if remaining > 0:
                    logger.warning(f"  🛑 Circuit breaker: {captcha_consecutifs} captchas consécutifs, pause 30s...")
                    await asyncio.sleep(30)
                    captcha_consecutifs = 0  # Reset après la pause
            continue
        
        # Éditeur
        captcha_consecutifs = 0  # Reset : page OK
        
        # Filtre format : vérifier que le produit est du bon type (manga vs LN)
        # Le format vient du champ Amazon : コミック (紙) / Comics (Paper) pour manga,
        # 文庫 / Paperback Bunko pour LN
        format_livre = infos.get('format', '')
        if filtre != "both" and format_livre:
            if filtre == "ln_only":
                # Formats acceptés pour LN : 文庫 (bunko), ペーパーバック (paperback)
                if ('文庫' not in format_livre and 'Bunko' not in format_livre
                        and 'ペーパーバック' not in format_livre and 'Paperback' not in format_livre):
                    logger.info(f"  📚 [{asin}] Format non-LN: {format_livre[:30]} → skip")
                    continue
            else:
                # Manga par défaut : exiger コミック ou Comics
                if 'コミック' not in format_livre and 'Comic' not in format_livre:
                    logger.info(f"  📚 [{asin}] Format non-manga: {format_livre[:30]} → skip")
                    continue
        
        editeur_volume = infos.get('editeur')
        if not editeur_volume:
            editeur_titre = extraire_editeur(infos.get('titre', ''))
            if editeur_titre:
                editeur_volume = convertir_editeur_romaji(editeur_titre)
        
        # Sauvegarder dans le cache de vérification
        db.sauvegarder_verification(
            asin, 
            infos.get('date', 'Date inconnue'),
            str(infos.get('tome', 'N/A')),
            infos.get('titre', '')[:100],
            editeur_volume
        )
        
        # Filtre éditeur
        if editeur_officiel_serie and editeur_volume and editeur_volume != 'Inconnu':
            if not editeur_match(editeur_volume, editeur_officiel_serie):
                logger.info(f"      📚 Éditeur: {editeur_volume} ≠ officiel {editeur_officiel_serie} → skip")
                continue
        
        if editeur_volume:
            logger.info(f"      📚 Éditeur: {editeur_volume}")
        
        # Sauvegarder dans la table volumes
        tome_int = None
        try:
            tome_val = infos.get('tome', 'N/A')
            if tome_val and tome_val != 'N/A':
                tome_int = int(tome_val)
        except (ValueError, TypeError):
            pass
        
        db.sauvegarder_volume(
            serie_jp=nom,
            serie_fr=titre_fr_serie or config.TRADUCTIONS_FR.get(nom),
            tome=tome_int,
            asin=asin,
            url=url_norm,
            date_sortie_jp=infos.get('date', 'Date inconnue'),
            titre_volume=infos.get('titre', '')[:200],
            editeur=editeur_volume
        )
        
        # Construire papier_info
        papier_info = {
            'nom': nom,
            'nom_fr': config.TRADUCTIONS_FR.get(nom, strip_type_suffix(nom)),
            'tome': infos.get('tome', 'N/A'),
            'date': infos.get('date', 'Date inconnue'),
            'editeur': infos.get('editeur', 'Inconnu'),
            'url': url_norm,
            'asin': asin,
            'couverture': infos.get('couverture_url', ''),
            'est_nouveaute': False,
            'serie_recherchee': nom_bdd
        }
        
        if not infos.get('date'):
            logger.warning(f"  ❌ [{asin}] Pas de date trouvée")
            tous_papiers.append(papier_info)
            continue
        
        try:
            date_clean = infos['date'].replace('\u200e', '').strip()
            # Format japonais standard : YYYY/M/D
            try:
                date_parsee = datetime.strptime(date_clean, "%Y/%m/%d")
            except ValueError:
                # Format anglais fallback : "January 9, 2026" (si page servie en EN)
                try:
                    date_parsee = datetime.strptime(date_clean, "%B %d, %Y")
                except ValueError:
                    raise  # Remonter pour le except ValueError extérieur
            
            # Précommandes : changement de date ?
            if force_refetch and date_alerte_enregistree:
                nouvelle_date = date_clean
                if nouvelle_date != date_alerte_enregistree:
                    logger.warning(f"  ⚠️  [{asin}] DATE MODIFIÉE ! {date_alerte_enregistree} → {nouvelle_date}")
                    db.update_alerte_date(nom_bdd, url_norm, nouvelle_date)
                    db.sauvegarder_verification(asin, nouvelle_date, infos.get('tome', 'N/A'), infos.get('titre', '')[:200], infos.get('editeur', ''))
                    papier_info['est_nouveaute'] = True
                    papier_info['date_modifiee'] = True
                    papier_info['ancienne_date'] = date_alerte_enregistree
                    papier_info['deja_alerte'] = True
                    nouveautes.append(papier_info)
                    tous_papiers.append(papier_info)
                    continue
                else:
                    logger.info(f"  🔄 [{asin}] Précommande re-vérifiée: date inchangée ({nouvelle_date})")
                    tous_papiers.append(papier_info)
                    continue
            
            if date_parsee <= config.DATE_SEUIL:
                if infos.get('est_lot'):
                    if infos.get('lot_debut') and infos.get('lot_fin'):
                        tome_display = f"📦 LOT volumes {infos['lot_debut']}-{infos['lot_fin']}"
                    elif infos.get('lot_total'):
                        tome_display = f"📦 COFFRET {infos['lot_total']} volumes"
                    else:
                        tome_display = "📦 LOT/SET"
                else:
                    tome_display = f"Tome: {infos.get('tome', 'N/A')}"
                logger.info(f"  ⏳ [{asin}] Trop ancien: {infos['date']}, {tome_display}")
                tous_papiers.append(papier_info)
                continue
            
            # NOUVEAUTÉ !
            if infos.get('est_lot'):
                if infos.get('lot_debut') and infos.get('lot_fin'):
                    lot_info = f"📦 LOT volumes {infos['lot_debut']}-{infos['lot_fin']}"
                elif infos.get('lot_total'):
                    lot_info = f"📦 COFFRET {infos['lot_total']} volumes"
                else:
                    lot_info = "📦 LOT/SET"
                logger.info(f"  ✨ [{asin}] NOUVEAUTÉ ! Date: {infos['date']}, {lot_info}")
                logger.warning(f"      ⚠️  ATTENTION : Ceci est un LOT/SET, pas un volume individuel")
            else:
                logger.info(f"  ✨ [{asin}] NOUVEAUTÉ ! Date: {infos['date']}, Tome: {infos.get('tome', 'N/A')}")
            
            logger.info(f"      → {url_norm}")
            
            db.marquer_comme_alerte(nom, url_norm, infos['date'])
            urls_alertees.add(url_norm)
            
            papier_info['est_lot'] = infos.get('est_lot', False)
            if infos.get('lot_debut') and infos.get('lot_fin'):
                papier_info['lot_debut'] = infos['lot_debut']
                papier_info['lot_fin'] = infos['lot_fin']
            elif infos.get('lot_total'):
                papier_info['lot_total'] = infos['lot_total']
            
            papier_info['est_nouveaute'] = True
            nouveautes.append(papier_info)
            tous_papiers.append(papier_info)
            
        except ValueError:
            logger.warning(f"  ⚠️  [{asin}] Date invalide: {infos.get('date')}")
            tous_papiers.append(papier_info)
    
    # =========================================================================
    # PHASE C : RECHERCHE ÉTENDUE (après vérification, quand on connaît les tomes)
    # =========================================================================
    
    tomes_trouves_set = set()
    for p in tous_papiers:
        try:
            tome_num = int(p.get('tome', 0))
            if tome_num > 0:
                tomes_trouves_set.add(tome_num)
        except (ValueError, TypeError):
            pass
    
    if tomes_trouves_set:
        tome_max = max(tomes_trouves_set)
        tomes_attendus = set(range(1, tome_max + 1))
        tomes_manquants = tomes_attendus - tomes_trouves_set
        
        if tomes_manquants and len(tous_papiers) > 0:
            logger.info(f"\n⚠️  Tomes manquants: {sorted(tomes_manquants)}")
            logger.info(f"   Trouvés: {sorted(tomes_trouves_set)} | Attendus: 1-{tome_max}")
            logger.info(f"🔄 Recherche étendue (pages 2-4)...\n")
            
            if len(url_suffix) <= 10 and url_suffix not in config.TITRES_GENERIQUES:
                recherche_exacte = url_suffix
            else:
                recherche_exacte = f'"{url_suffix}"'
            
            titre_cle = normaliser_titre(url_suffix[:8] if len(url_suffix) >= 8 else url_suffix)
            
            for page_num in range(2, 5):
                if not tomes_manquants:
                    break
                
                url_page = f"https://www.amazon.co.jp/s?k={quote_plus(recherche_exacte)}&i=stripbooks&s=relevancerank&rh=p_6%3AAN1VRQENFRJN5&page={page_num}"
                html_page = await get_html(session, url_page)
                
                if not html_page:
                    continue
                
                soup_page = BeautifulSoup(html_page, 'lxml')
                items_page = soup_page.select('.s-result-item')[:30]
                
                if not items_page:
                    break
                
                nouveaux_cette_page = 0
                for item in items_page:
                    titre_txt, url_complete, asin = extraire_item_amazon(item)
                    if not titre_txt or not asin or asin in asin_deja_vus:
                        continue
                    
                    titre_txt_normalise = normaliser_titre(titre_txt)
                    if titre_cle not in titre_txt_normalise:
                        continue
                    
                    if est_ebook(url_complete, titre_txt) or not est_asin_papier(asin):
                        asin_deja_vus.add(asin)
                        continue
                    
                    # Nouveau papier → vérifier directement
                    logger.info(f"  ✅ Page {page_num}: [{asin}] {titre_txt[:50]}...")
                    asin_deja_vus.add(asin)
                    nouveaux_cette_page += 1
                    
                    # Fetch et vérification inline
                    html_prod = await get_html(session, url_complete)
                    if html_prod:
                        infos = await extraire_infos_produit(html_prod)
                        if not infos.get('_page_invalide'):
                            editeur_ext = infos.get('editeur')
                            if not editeur_ext:
                                editeur_titre = extraire_editeur(infos.get('titre', ''))
                                if editeur_titre:
                                    editeur_ext = convertir_editeur_romaji(editeur_titre)
                            
                            db.sauvegarder_verification(asin, infos.get('date', 'Date inconnue'), str(infos.get('tome', 'N/A')), infos.get('titre', '')[:100], editeur_ext)
                            
                            # Filtre éditeur
                            if editeur_officiel_serie and editeur_ext and editeur_ext != 'Inconnu':
                                if not editeur_match(editeur_ext, editeur_officiel_serie):
                                    continue
                            
                            tome_int = None
                            try:
                                if infos.get('tome') and infos['tome'] != 'N/A':
                                    tome_int = int(infos['tome'])
                            except:
                                pass
                            
                            db.sauvegarder_volume(
                                serie_jp=nom, serie_fr=titre_fr_serie or config.TRADUCTIONS_FR.get(nom),
                                tome=tome_int, asin=asin,
                                url=normaliser_url(url_complete),
                                date_sortie_jp=infos.get('date', 'Date inconnue'),
                                titre_volume=infos.get('titre', '')[:200], editeur=editeur_ext
                            )
                            
                            papier_info = {
                                'nom': nom, 'nom_fr': config.TRADUCTIONS_FR.get(nom, strip_type_suffix(nom)),
                                'tome': infos.get('tome', 'N/A'), 'date': infos.get('date', 'Date inconnue'),
                                'editeur': editeur_ext or 'Inconnu', 'url': normaliser_url(url_complete),
                                'asin': asin, 'couverture': '', 'est_nouveaute': False,
                                'serie_recherchee': nom_bdd
                            }
                            tous_papiers.append(papier_info)
                            
                            # Mettre à jour les tomes manquants
                            if tome_int and tome_int in tomes_manquants:
                                tomes_manquants.discard(tome_int)
                
                if nouveaux_cette_page > 0:
                    logger.info(f"   Page {page_num}: {nouveaux_cette_page} nouveau(x)")
                else:
                    logger.info(f"   Page {page_num}: rien de nouveau")
    
    # =========================================================================
    # FINALISATION
    # =========================================================================
    
    logger.info("-" * 80)
    logger.info(f"✅ Résultat: {len(nouveautes)} nouveauté(s) | {len(tous_papiers)} papier(s) au total")
    
    # Cohérence
    tomes_trouves = [p.get('tome') for p in tous_papiers if isinstance(p.get('tome'), int)]
    tome_max = max(tomes_trouves, default=0)
    nb_volumes_reels = len([p for p in tous_papiers if not p.get('est_lot')])
    
    if tome_max >= 3 and nb_volumes_reels < tome_max - 2:
        logger.warning(f"\n⚠️  ALERTE COHÉRENCE : Tome max {tome_max} mais seulement {nb_volumes_reels} volume(s)")
        logger.warning(f"    → Il manque probablement ~{tome_max - nb_volumes_reels} volume(s)\n")
    
    # Traduction
    if nom in config.TRADUCTIONS_FR:
        titre_fr = config.TRADUCTIONS_FR[nom]
        for produit in tous_papiers:
            if produit['nom'] == nom:
                produit['nom_fr'] = titre_fr
        if nouveautes:
            logger.info(f"✨ Traduction appliquée: {titre_fr}\n")
    
    # Détection éditeur officiel
    if tous_papiers:
        editeur_officiel = db.detecter_et_sauvegarder_editeur_officiel(nom_bdd)
        if editeur_officiel and len(tous_papiers) >= 3:
            logger.info(f"📚 Éditeur officiel détecté pour {nom_bdd}: {editeur_officiel}")
    
    if not nouveautes:
        logger.info("")
    
    return nouveautes, tous_papiers


def generer_resume_log(tous_papiers: List[Dict], logger):
    """Génère un résumé dans le log par série"""
    
    # Grouper par série
    par_serie = {}
    for p in tous_papiers:
        nom = p.get('nom', 'Inconnu')
        if nom not in par_serie:
            par_serie[nom] = []
        par_serie[nom].append(p)
    
    logger.info("\n" + "="*80)
    logger.info("📊 RÉSUMÉ PAR SÉRIE")
    logger.info("="*80)
    
    for nom_serie in sorted(par_serie.keys()):
        tomes = par_serie[nom_serie]
        
        # Trier par tome
        tomes_tries = sorted(tomes, key=lambda x: (
            int(x.get('tome')) if isinstance(x.get('tome'), int) or (isinstance(x.get('tome'), str) and x.get('tome').isdigit()) else 999
        ))
        
        # Compter
        nb_tomes = len([t for t in tomes_tries if isinstance(t.get('tome'), int) or (isinstance(t.get('tome'), str) and t.get('tome').isdigit())])
        tome_max = max([int(t.get('tome')) for t in tomes_tries if isinstance(t.get('tome'), int) or (isinstance(t.get('tome'), str) and t.get('tome').isdigit())], default=0)
        nb_nouveautes = len([t for t in tomes_tries if t.get('est_nouveaute')])
        
        # Nom FR
        nom_fr = tomes[0].get('nom_fr', nom_serie) if tomes else nom_serie
        
        status = f"✨ {nb_nouveautes} nouveauté(s)" if nb_nouveautes > 0 else "✓"
        
        logger.info(f"\n📚 {nom_serie}")
        if nom_fr != nom_serie:
            logger.info(f"   ({nom_fr})")
        logger.info(f"   📖 {nb_tomes} tome(s) | Dernier: Tome {tome_max} | {status}")
        
        # Liste des tomes
        tomes_str = []
        for t in tomes_tries:
            tome_num = t.get('tome', '?')
            if t.get('est_nouveaute'):
                tomes_str.append(f"[{tome_num}🆕]")
            elif t.get('deja_alerte'):
                tomes_str.append(f"[{tome_num}✓]")
            else:
                tomes_str.append(f"{tome_num}")
        
        logger.info(f"   Tomes: {', '.join(tomes_str)}")


async def reverifier_toutes_traductions(db: DatabaseManager):
    """Re-vérifie les traductions non-officielles contre config.TRADUCTIONS_MANUELLES"""
    traductions = db.get_traductions_non_officielles()
    
    if not traductions:
        logger.info("✅ Aucune traduction non-officielle à re-vérifier")
        return
    
    logger.info(f"\n🔄 Re-vérification de {len(traductions)} traduction(s) non-officielle(s)...")
    logger.info("="*80)
    
    mises_a_jour = 0
    for trad in traductions:
        titre_jp = trad['titre_japonais']
        ancien_titre = trad['titre_francais']
        nom_clean = strip_type_suffix(titre_jp)
        
        logger.info(f"\n📚 {titre_jp}")
        logger.info(f"   Actuel: {ancien_titre} ({trad['source']})")
        
        # Chercher dans config.TRADUCTIONS_MANUELLES
        titre_fr = config.TRADUCTIONS_MANUELLES.get(titre_jp) or config.TRADUCTIONS_MANUELLES.get(nom_clean)
        
        if titre_fr:
            db.sauvegarder_traduction(titre_jp, titre_fr, source='manuel', est_officielle=True)
            logger.info(f"   ✨ MISE À JOUR: {titre_fr} (officielle, manuel)")
            mises_a_jour += 1
        else:
            db.marquer_verification_traduction(titre_jp)
            logger.info(f"   ℹ️  Pas de traduction officielle trouvée, garde: {ancien_titre}")
    
    logger.info("\n" + "="*80)
    logger.info(f"✅ Re-vérification terminée: {mises_a_jour} mise(s) à jour")
    logger.info("="*80)


