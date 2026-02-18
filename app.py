#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MangaVega Tracker - Point d'entrée principal (orchestrateur)
"""

import asyncio
import json
import os
import re
import random
import sys
import traceback as tb
from datetime import datetime
from typing import Dict

import config
from database import DatabaseManager
import utils
import sync
import notifications
import pipeline
from scraper import SessionWrapper

logger = config.logger


async def main():
    import argparse
    import traceback as tb
    
    # === ARGUMENTS CLI ===
    parser = argparse.ArgumentParser(description=f"MangaVega Tracker v{config.VERSION}")
    parser.add_argument('--serie', type=str, help='Scanner uniquement les séries contenant ce texte (match partiel)')
    parser.add_argument('--list', action='store_true', help='Afficher le contenu de la BDD et quitter')
    parser.add_argument('--no-push', action='store_true', help='Ne pas faire git push à la fin')
    parser.add_argument('--no-email', action='store_true', help='Ne pas envoyer les emails')
    parser.add_argument('--reverifier-traductions', action='store_true', help='Re-vérifier les traductions non-officielles')
    args = parser.parse_args()
    
    # Mode re-vérification traductions
    if args.reverifier_traductions:
        logger.info("\n" + "="*80)
        logger.info(f"🔄 MODE RE-VÉRIFICATION TRADUCTIONS")
        logger.info("="*80)
        db = DatabaseManager()
        await pipeline.reverifier_toutes_traductions(db)
        return
    
    # Mode liste BDD
    if args.list:
        db = DatabaseManager()
        db.init_table_volumes()
        db.init_table_editeurs()
        conn = db._get_conn()
        cursor = conn.cursor()
        
        # Stats générales
        cursor.execute("SELECT COUNT(*) FROM volumes")
        nb_volumes = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT serie_jp) FROM volumes")
        nb_series = cursor.fetchone()[0]
        
        logger.info(f"\n📊 BASE DE DONNÉES: {nb_volumes} volumes, {nb_series} séries\n")
        
        # Volumes par série
        cursor.execute("""
            SELECT serie_jp, serie_fr, COUNT(*) as nb, 
                   MIN(tome) as t_min, MAX(tome) as t_max,
                   MIN(date_sortie_jp) as date_min, MAX(date_sortie_jp) as date_max,
                   editeur
            FROM volumes 
            GROUP BY serie_jp 
            ORDER BY serie_jp
        """)
        for row in cursor.fetchall():
            serie_jp, serie_fr, nb, t_min, t_max, date_min, date_max, editeur = row
            nom_display = serie_fr if serie_fr else serie_jp
            logger.info(f"  📚 {nom_display}")
            logger.info(f"     {nb} tome(s) | T{t_min}-T{t_max} | {date_min} → {date_max} | {editeur or '?'}")
        
        db.close()
        return
    
    try:
        await _main_inner(args)
    except Exception as e:
        logger.error(f"\n❌ ERREUR FATALE: {e}")
        logger.error(tb.format_exc())
        # Ne PAS faire raise : la BDD et les fichiers générés doivent être commitées
        # Le workflow doit pouvoir faire git add même après une erreur partielle
        logger.info("⚠️  Le script a rencontré une erreur mais les données partielles sont conservées")


async def _main_inner(args):
    # NOUVEAU: Charger la liste des mangas depuis le fichier JSON externe
    sync.charger_mangas_liste()
    
    # === FILTRE --serie ===
    if args.serie:
        filtre_texte = args.serie.lower()
        avant = len(config.MANGAS_A_SUIVRE)
        config.MANGAS_A_SUIVRE = [
            m for m in config.MANGAS_A_SUIVRE 
            if filtre_texte in m['nom'].lower() 
            or filtre_texte in config.TRADUCTIONS_FR.get(m['nom'], '').lower()
        ]
        apres = len(config.MANGAS_A_SUIVRE)
        if apres == 0:
            logger.error(f"❌ Aucune série ne correspond au filtre '{args.serie}'")
            logger.info(f"   (sur {avant} séries disponibles)")
            return
        logger.info(f"🔍 Filtre --serie '{args.serie}': {apres}/{avant} série(s) sélectionnée(s)")
        for m in config.MANGAS_A_SUIVRE:
            logger.info(f"   → {m['nom']}")
    
    logger.info("\n" + "="*80)
    logger.info(f"🚀 MANGA TRACKER v{config.VERSION} ({config.VERSION_DATE})")
    logger.info("="*80)
    logger.info(f"📚 {len(config.MANGAS_A_SUIVRE)} mangas à surveiller")
    logger.info(f"📅 Date seuil nouveautés: {config.DATE_SEUIL.strftime('%Y/%m/%d')}")
    logger.info("="*80)
    
    debut = datetime.now()
    db = DatabaseManager()
    
    # INITIALISATION : Créer/vérifier les tables volumes et editeurs
    logger.info("\n📦 Initialisation de la base de données...")
    db.init_table_volumes()
    db.init_table_editeurs()
    logger.info("   ✅ Tables 'volumes' et 'series_editeurs' prêtes")
    # === NETTOYAGE : supprimer les doublons de traductions migration_v7 ===
    # Les traductions 'migration_v7' (sans suffixe [MANGA]/[LN]) sont redondantes
    # car rechercher_traductions() insère avec le bon nom (avec suffixe) source='manuel'
    try:
        conn = db._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM traductions WHERE source = 'migration_v7'")
        nb_supprimees = cursor.rowcount
        if nb_supprimees > 0:
            conn.commit()
            logger.info(f"   🗑️  {nb_supprimees} traduction(s) legacy 'migration_v7' supprimées (doublons)")
        cursor.execute("SELECT COUNT(*) FROM traductions")
        nb_trad = cursor.fetchone()[0]
        logger.info(f"   ✅ Traductions manuelles déjà en BDD ({nb_trad} entrées)")
    except Exception as e:
        logger.warning(f"   ⚠️  Nettoyage traductions: {e}")

    # === MIGRATION : ebooks_traites → featured_history (puis suppression table legacy) ===
    try:
        nb_migres = db.migrer_ebooks_vers_featured_history()
        if nb_migres > 0:
            logger.info(f"   ✅ {nb_migres} ebook(s) migrés vers featured_history")
        # Supprimer la table legacy après migration réussie
        try:
            conn = db._get_conn()
            conn.execute('DROP TABLE IF EXISTS ebooks_traites')
            conn.commit()
            logger.info("   🗑️  Table legacy 'ebooks_traites' supprimée")
        except Exception:
            pass  # Pas grave si elle n'existe déjà plus
    except Exception as e:
        logger.warning(f"   ⚠️  Migration featured_history: {e}")
    
    # Charger la configuration depuis le Gist GitHub (viewer sync)
    sync.charger_gist_config()
    
    # Charger les corrections manuelles (depuis Gist + BDD + fichier JSON)
    sync.charger_corrections(db)
    
    # Charger la configuration des séries (depuis Gist + fichier local)
    sync.charger_series_config(db)
    
    # Afficher le nombre de séries après fusion
    logger.info(f"📚 {len(config.MANGAS_A_SUIVRE)} mangas à surveiller (après fusion)")
    
    # VÉRIFICATION : Afficher les séries sans traduction FR
    series_manquantes = db.get_series_sans_traduction()
    # Exclure celles qui ont un titre dans config.TRADUCTIONS_FR (chargé depuis mangas_liste.json)
    series_manquantes = [s for s in series_manquantes 
                         if not config.TRADUCTIONS_FR.get(s['serie_jp'], '')
                         and not config.TRADUCTIONS_FR.get(utils.strip_type_suffix(s['serie_jp']), '')]
    if series_manquantes:
        nb_sans_fr = len(series_manquantes)
        if nb_sans_fr > 0:
            logger.info(f"   ⚠️  {nb_sans_fr} série(s) sans titre FR")
            logger.info(f"   → Les traductions seront recherchées automatiquement")
    
    logger.info("="*80)
    
    toutes_nouveautes = []
    tous_papiers = []  # NOUVEAU
    
    # OPTIMISATION: Trier les séries par priorité
    # INVERSÉ: Les séries avec cache passent en premier pour "débloquer" le rate limit Amazon
    # Priorité 1: Avec cache → passe en premier, survit au rate limit initial
    # Priorité 2: ASIN de référence + pas de cache → Bulk direct possible
    # Priorité 3: Pas de cache ni référence → passe à la fin quand Amazon s'est calmé
    
    def get_priorite_serie(manga: Dict) -> tuple:
        """
        Retourne un tuple (priorité, -nb_cache) pour le tri.
        Plus le tuple est petit, plus la série est prioritaire.
        """
        nom = manga['nom']
        urls_supp = manga.get('urls_supplementaires', [])
        
        # Compter le cache
        try:
            nb_cache = len(db.get_volumes_connus(nom))
        except:
            nb_cache = 0
        
        # Chercher un ASIN de référence
        asin_ref = None
        
        # Source 0: ASIN de référence explicite (depuis Gist)
        if manga.get('asin_reference'):
            asin_ref = manga['asin_reference']
        
        # Source 1: URL supplémentaire (ajoutée manuellement)
        if not asin_ref and urls_supp:
            for url in urls_supp:
                match = re.search(r'/dp/([A-Z0-9]{10})', url)
                if match:
                    asin_ref = match.group(1)
                    break
        
        # Source 2: Volume validé en BDD
        if not asin_ref:
            asin_ref = db.get_asin_reference(nom)
        
        # Déterminer la priorité (INVERSÉ par rapport à avant)
        if nb_cache > 0:
            priorite = 1  # 🥇 Avec cache → passe en premier
        elif asin_ref:
            priorite = 2  # 🥈 ASIN de référence + pas de cache
        else:
            priorite = 3  # 🥉 Pas de cache ni référence → à la fin
        
        # Stocker l'ASIN de référence pour usage ultérieur
        manga['_asin_reference'] = asin_ref
        
        return (priorite, -nb_cache)  # -nb_cache pour trier par cache décroissant
    
    # Trier les séries
    mangas_tries = sorted(config.MANGAS_A_SUIVRE, key=get_priorite_serie)
    
    # Logger l'ordre (utiliser les valeurs déjà calculées dans _asin_reference)
    p1 = 0
    p2 = 0
    p3 = 0
    for m in mangas_tries:
        nom = m['nom']
        try:
            nb_cache = len(db.get_volumes_connus(nom))
        except:
            nb_cache = 0
        asin_ref = m.get('_asin_reference')
        
        if nb_cache > 0:
            p1 += 1
        elif asin_ref:
            p2 += 1
        else:
            p3 += 1
    
    logger.info(f"📋 Ordre optimisé (cache en premier):")
    logger.info(f"   🥇 {p1} série(s) avec cache (passent d'abord)")
    logger.info(f"   🥈 {p2} série(s) avec ASIN de référence, sans cache")  
    logger.info(f"   🥉 {p3} série(s) sans cache ni référence (à la fin)")
    logger.info("")
    
    # NOTE: Le délai initial de 5 minutes a été testé mais n'aide pas
    # Le rate limit Amazon semble basé sur l'IP, pas sur le timing
    # On garde juste un petit délai de 10s pour "chauffer" la connexion
    import os
    if os.environ.get('GITHUB_ACTIONS'):
        logger.info(f"⏳ GitHub Actions détecté - Petit délai de 10s avant le scan...")
        await asyncio.sleep(10)
    
    # SÉQUENTIEL (un par un) avec délais anti-rate-limit
    async with SessionWrapper() as session:
        # Warm-up : visiter amazon.co.jp pour obtenir les cookies de session
        await session.warm_up()
        
        series_echouees = []  # Séries avec 0 résultat (probable 503)
        
        async def scanner_serie(manga, index, total, est_retry=False):
            """Scanne une série et retourne (nouveautes, papiers).
            Retourne None si la série est bloquée (0 résultat)."""
            prefix = "🔄 RETRY" if est_retry else "📚 MANGA"
            
            filtre = manga.get('filtre')
            serie_id = manga.get('serie_id')
            urls_supplementaires = manga.get('urls_supplementaires', [])
            asin_reference = manga.get('_asin_reference')
            
            nouveautes, papiers = await pipeline.rechercher_manga(
                session, db, 
                manga['nom'], 
                manga['url_suffix'],
                filtre=filtre,
                serie_id=serie_id,
                asin_reference=asin_reference,
                urls_supplementaires=urls_supplementaires if urls_supplementaires else None
            )
            
            # Nettoyage URLs supplémentaires du Gist
            if urls_supplementaires:
                serie_nom = manga['nom']
                if config.GIST_SERIES_CONFIG.get('urls_supplementaires', {}).get(serie_nom):
                    del config.GIST_SERIES_CONFIG['urls_supplementaires'][serie_nom]
                    config.GIST_MODIFIED = True
                    logger.info(f"   🧹 URL(s) supplémentaire(s) retirée(s) du Gist")
            
            # Recherche étendue des tomes manquants via Bulk
            analyse_tomes = utils.analyser_tomes_manquants(papiers)
            if not analyse_tomes['complet'] and len(analyse_tomes['tomes_manquants']) > 0:
                if len(analyse_tomes['tomes_manquants']) <= 5:
                    logger.info(f"\n   ⚠️ Tomes manquants détectés: {sorted(analyse_tomes['tomes_manquants'])} (sur {analyse_tomes['tome_max']} attendus)")
                    asins_deja_connus = {p['asin'] for p in papiers if p.get('asin')}
                    nouveaux_trouves = await pipeline.rechercher_volumes_via_bulk_etendu(
                        session, db, manga['nom'], papiers, 
                        asins_deja_connus, config.ASINS_HORS_SUJET, logger
                    )
                    if nouveaux_trouves:
                        logger.info(f"   🎉 {len(nouveaux_trouves)} nouveau(x) volume(s) trouvé(s) via Bulk étendu !")
                        papiers.extend(nouveaux_trouves)
                else:
                    logger.info(f"\n   ⚠️ {len(analyse_tomes['tomes_manquants'])} tomes manquants")
            
            return nouveautes, papiers
        
        # === BOUCLE PRINCIPALE ===
        for i, manga in enumerate(mangas_tries, 1):
          try:
            nouveautes, papiers = await scanner_serie(manga, i, len(mangas_tries))
            toutes_nouveautes.extend(nouveautes)
            tous_papiers.extend(papiers)
            
            # Détecter les séries bloquées (0 résultat)
            if len(papiers) == 0:
                series_echouees.append(manga)
            
            # Pause à mi-parcours pour éviter les 503
            if i == 28:  # À la moitié des 55 mangas
                logger.info("\n" + "="*80)
                logger.info("⏸️  PAUSE LONGUE DE 60 SECONDES À MI-PARCOURS")
                logger.info("    (Pour éviter le rate limiting Amazon)")
                logger.info("="*80 + "\n")
                await asyncio.sleep(60)
            
            # Délai adaptatif entre mangas
            if i < len(mangas_tries):
                serie_bloquee = (len(papiers) == 0 and len(nouveautes) == 0)
                
                if i % 15 == 0:  # Pause tous les 15 mangas
                    logger.info(f"\n⏸️  Pause de 8s après {i} mangas pour éviter le rate limiting...")
                    await asyncio.sleep(8)
                elif serie_bloquee:
                    logger.info(f"   ⏸️  Pause de 15s (récupération après blocage)...")
                    await asyncio.sleep(15)
                else:
                    await asyncio.sleep(random.uniform(1.5, 3))
          
          except Exception as e:
            logger.error(f"❌ ERREUR pour {manga.get('nom', '?')}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            series_echouees.append(manga)
            continue
        
        # === RETRY DES SÉRIES ÉCHOUÉES ===
        # À ce stade les cookies sont établis, les retries ont de bonnes chances de passer
        if series_echouees:
            logger.info("\n" + "="*80)
            logger.info(f"🔄 RETRY: {len(series_echouees)} série(s) sans résultat lors du premier passage")
            logger.info("   (Les cookies sont maintenant établis, retry après 30s de pause)")
            logger.info("="*80)
            await asyncio.sleep(30)
            
            nb_recuperees = 0
            for j, manga in enumerate(series_echouees, 1):
              try:
                logger.info(f"\n🔄 [{j}/{len(series_echouees)}] Retry: {manga['nom']}")
                nouveautes, papiers = await scanner_serie(manga, j, len(series_echouees), est_retry=True)
                toutes_nouveautes.extend(nouveautes)
                tous_papiers.extend(papiers)
                
                if len(papiers) > 0:
                    nb_recuperees += 1
                    logger.info(f"   ✅ Récupérée: {len(papiers)} volume(s)")
                else:
                    logger.warning(f"   ❌ Toujours aucun résultat")
                
                # Délai entre retries
                if j < len(series_echouees):
                    await asyncio.sleep(random.uniform(3, 6))
              
              except Exception as e:
                logger.error(f"❌ ERREUR retry {manga.get('nom', '?')}: {e}")
                continue
            
            logger.info(f"\n🔄 Retry terminé: {nb_recuperees}/{len(series_echouees)} série(s) récupérée(s)")
        
        # === CORRECTION DES TOMES MANQUANTS ===
        # Recherche les numéros de tome pour les volumes validés manuellement 
        # qui ont un tome = ? ou N/A (souvent des URLs ajoutées manuellement)
        tomes_corriges = await pipeline.corriger_tomes_manquants(session, db, logger)
    
    fin = datetime.now()
    duree = (fin - debut).total_seconds()
    
    logger.info("\n" + "="*80)
    logger.info("📊 RÉSUMÉ FINAL")
    logger.info("="*80)
    logger.info(f"⏱️  Temps: {duree:.1f}s")
    logger.info(f"📚 Scannés: {len(config.MANGAS_A_SUIVRE)}")
    logger.info(f"📦 Papiers trouvés: {len(tous_papiers)}")
    logger.info(f"✨ Nouveautés: {len(toutes_nouveautes)}")
    logger.info("="*80)
    
    # Générer le résumé par série dans le log
    if tous_papiers:
        pipeline.generer_resume_log(tous_papiers, logger)
    
    logger.info("\n" + "="*80)
    logger.info("📁 FICHIERS GÉNÉRÉS")
    logger.info("="*80)
    
    # Export JSON avec statuts (pour le viewer)
    nb_non_traites = 0
    if tous_papiers:
        asins_rejetes = db.get_asins_rejetes()
        asins_valides = db.get_asins_valides()
        volume_overrides = db.get_all_volume_serie_overrides()
        
        # Enrichir les volumes avec leur statut et nom_fr
        volumes_avec_statut = []
        for p in tous_papiers:
            p_copy = p.copy()
            asin = p.get('asin', '')
            nom = p.get('nom', '')
            
            # NOUVEAU: Appliquer l'override de série si défini
            if asin in volume_overrides:
                serie_alternative = volume_overrides[asin]
                p_copy['nom'] = serie_alternative  # Remplacer le nom de série
                p_copy['nom_fr'] = serie_alternative  # La série alternative est déjà en FR
                p_copy['serie_originale'] = nom  # Garder trace de l'origine
            else:
                # Ajouter nom_fr depuis le dictionnaire de traductions
                if 'nom_fr' not in p_copy or not p_copy.get('nom_fr'):
                    p_copy['nom_fr'] = config.TRADUCTIONS_FR.get(nom, '')
            
            # NOUVEAU: Ajouter la date de première détection
            # On utilise la date d'aujourd'hui (sera conservée lors des fusions avec l'historique)
            p_copy['date_detection'] = datetime.now().strftime('%Y-%m-%d')
            
            # Ajouter le statut
            if asin in asins_rejetes:
                p_copy['statut'] = 'rejete'
            elif asin in asins_valides:
                p_copy['statut'] = 'valide'
            else:
                p_copy['statut'] = 'non_traite'
            volumes_avec_statut.append(p_copy)
        
        # Calculer les stats basées uniquement sur les ASINs présents dans ce run
        asins_papiers = {p.get('asin', '') for p in tous_papiers}
        nb_valides = len(asins_valides & asins_papiers)
        nb_rejetes = len(asins_rejetes & asins_papiers)
        nb_non_traites = len(asins_papiers) - nb_valides - nb_rejetes
        
        json_data = {
            "generated_at": datetime.now().isoformat(),
            "version": config.VERSION,
            "total_volumes": len(tous_papiers),
            "total_series": len(set(p['nom'] for p in tous_papiers)),
            "stats": {
                "valides": nb_valides,
                "rejetes": nb_rejetes,
                "non_traites": nb_non_traites
            },
            "volumes": volumes_avec_statut
        }
        with open('manga_collection.json', 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        logger.info("📋 JSON collection: manga_collection.json")
    
    # === SAUVEGARDE DU GIST (nettoyage URLs traitées) ===
    try:
        sync.sauvegarder_gist_config()
    except Exception as e:
        logger.warning(f"⚠️  Erreur sauvegarde Gist (non-bloquant): {e}")
    
    if args.no_email:
        logger.info("📧 Emails désactivés (--no-email)")
    elif toutes_nouveautes:
        logger.info("\n")
        try:
            notifications.envoyer_email(config.EMAIL_DESTINATAIRE, toutes_nouveautes)
        except Exception as e:
            logger.warning(f"⚠️  Erreur envoi email nouveautés (non-bloquant): {e}")
    
    # Toujours envoyer un rapport de synthèse (sauf --no-email)
    if not args.no_email:
        try:
            notifications.envoyer_email_rapport(config.EMAIL_DESTINATAIRE, len(config.MANGAS_A_SUIVRE), len(tous_papiers), len(toutes_nouveautes), nb_non_traites, duree)
        except Exception as e:
            logger.warning(f"⚠️  Erreur envoi rapport (non-bloquant): {e}")
    
    # Fermer la connexion BDD
    db.close()
    
    # Git push (sauf --no-push)
    if args.no_push:
        logger.info("📤 Git push désactivé (--no-push)")
    else:
        try:
            sync.git_push()
        except Exception as e:
            logger.warning(f"⚠️  Erreur git push (non-bloquant): {e}")


if __name__ == "__main__":
    asyncio.run(main())
