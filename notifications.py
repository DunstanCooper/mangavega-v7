#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MangaVega Tracker - Notifications email
"""

import imaplib
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from typing import List, Dict

import config

logger = config.logger

BROUILLONS_DIR = os.path.join(os.path.dirname(__file__), 'brouillons')


def _deposer_brouillon_workflow(msg) -> bool:
    """
    Tente de déposer le message comme brouillon dans M365 via IMAP APPEND.
    Retourne True si succès, False sinon.
    Nécessite IMAP_MOT_DE_PASSE dans .env.
    """
    if not config.IMAP_MOT_DE_PASSE:
        return False
    try:
        imap = imaplib.IMAP4_SSL(config.IMAP_SERVER, config.IMAP_PORT)
        imap.login(config.EMAIL_DESTINATAIRE_WORKFLOW, config.IMAP_MOT_DE_PASSE)
        # M365 en français → "Brouillons", en anglais → "Drafts"
        dossier = None
        for nom in ['Brouillons', 'Drafts']:
            res = imap.select(f'"{nom}"')
            if res[0] == 'OK':
                dossier = nom
                break
        if not dossier:
            # Lister les dossiers pour trouver le bon nom
            _, dossiers = imap.list()
            for d in dossiers or []:
                d_str = d.decode() if isinstance(d, bytes) else d
                if 'draft' in d_str.lower() or 'brouillon' in d_str.lower():
                    dossier = d_str.split('"/"')[-1].strip().strip('"')
                    imap.select(f'"{dossier}"')
                    break
        if dossier:
            imap.append(f'"{dossier}"', r'(\Draft)', None, msg.as_bytes())
            logger.info(f"📥 Brouillon créé dans M365 ({dossier})")
            imap.logout()
            return True
        imap.logout()
    except Exception as e:
        logger.warning(f"⚠️  IMAP M365 échoué ({e}) → fallback .eml")
    return False


def _sauvegarder_eml(msg, nom_fichier: str):
    """Sauvegarde le message en fichier .eml dans le dossier brouillons/."""
    os.makedirs(BROUILLONS_DIR, exist_ok=True)
    chemin = os.path.join(BROUILLONS_DIR, nom_fichier)
    with open(chemin, 'wb') as f:
        f.write(msg.as_bytes())
    logger.info(f"📄 Brouillon sauvegardé : {chemin}")
    logger.info(f"   → Double-clic pour ouvrir dans Outlook, ou glisser dans Outlook Web")


def generer_email_html(nouvelles_publications: List[Dict]) -> str:
    """Génère l'email HTML"""
    
    cartes_html = ""
    for pub in nouvelles_publications:
        couverture_html = f'<img src="{pub.get("couverture", "")}" alt="Couverture" style="width:100%;height:100%;object-fit:cover;">' if pub.get('couverture') else '<div style="color:#667eea;font-size:11px;text-align:center;padding:10px;">Couverture non disponible</div>'
        
        # Badge et bordure selon le type d'alerte
        if pub.get('date_modifiee'):
            badge_html = '<span style="display:inline-block;background-color:#e53e3e;color:white;padding:5px 12px;border-radius:12px;font-size:11px;font-weight:600;margin-left:8px;">⚠️ DATE MODIFIÉE</span>'
            border_color = '#e53e3e'
            date_display = f"<s style='color:#999;'>{pub.get('ancienne_date', '')}</s> → <strong style='color:#e53e3e;'>{pub['date']}</strong>"
        else:
            badge_html = '<span style="display:inline-block;background-color:#48bb78;color:white;padding:5px 12px;border-radius:12px;font-size:11px;font-weight:600;margin-left:8px;">NOUVEAU</span>'
            border_color = '#667eea'
            date_display = pub['date']
        
        cartes_html += f'''
            <table cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color:#f9fafb;border-left:4px solid {border_color};border-radius:6px;margin-bottom:20px;">
                <tr>
                    <td style="padding:20px;">
                        <table cellpadding="0" cellspacing="0" border="0" width="100%">
                            <tr>
                                <td width="120" valign="top" style="padding-right:20px;">
                                    <div style="width:100px;height:140px;background:linear-gradient(135deg,#e0e7ff 0%,#c7d2fe 100%);border-radius:4px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.15);">
                                        {couverture_html}
                                    </div>
                                </td>
                                <td valign="top">
                                    <h2 style="font-size:18px;font-weight:600;color:#1a202c;margin:0 0 10px 0;">
                                        {pub['nom']}
                                        {badge_html}
                                    </h2>
                                    <p style="font-size:16px;color:#667eea;font-weight:500;margin:0 0 18px 0;">{pub['nom_fr']}</p>
                                    <table cellpadding="0" cellspacing="0" border="0" style="margin-bottom:18px;">
                                        <tr><td style="padding:8px 20px 8px 0;"><span style="font-size:18px;">📖</span><strong style="font-size:15px;color:#4a5568;margin-left:8px;">Tome {pub['tome']}</strong></td></tr>
                                        <tr><td style="padding:8px 20px 8px 0;"><span style="font-size:18px;">📅</span><span style="font-size:15px;color:#4a5568;margin-left:8px;">{date_display}</span></td></tr>
                                        <tr><td style="padding:8px 20px 8px 0;"><span style="font-size:18px;">🏢</span><span style="font-size:15px;color:#4a5568;margin-left:8px;">{pub['editeur']}</span></td></tr>
                                    </table>
                                    <a href="{pub['url']}" style="display:inline-block;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;padding:14px 28px;text-decoration:none;border-radius:8px;font-weight:600;font-size:14px;">Voir sur Amazon →</a>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        '''
    
    return f'''<!DOCTYPE html>
    <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
    <body style="margin:0;padding:0;background-color:#f0f4f8;font-family:system-ui,-apple-system,sans-serif;">
        <table cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color:#f0f4f8;padding:40px 20px;">
            <tr><td align="center">
                <table cellpadding="0" cellspacing="0" border="0" width="600" style="max-width:600px;background-color:white;border-radius:16px;overflow:hidden;box-shadow:0 10px 40px rgba(0,0,0,0.1);">
                    <tr><td style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);padding:40px 30px;text-align:center;">
                        <h1 style="color:white;margin:0;font-size:28px;">📚 Nouveautés Manga</h1>
                        <p style="color:rgba(255,255,255,0.95);margin:12px 0 0 0;font-size:16px;">{len(nouvelles_publications)} nouvelle(s) détectée(s)</p>
                    </td></tr>
                    <tr><td style="padding:30px;">{cartes_html}</td></tr>
                    <tr><td style="background-color:#f7fafc;padding:25px 30px;text-align:center;border-top:1px solid #e2e8f0;">
                        <p style="margin:0;color:#718096;font-size:13px;">Manga Tracker • {datetime.now().strftime("%d/%m/%Y")}</p>
                    </td></tr>
                </table>
            </td></tr>
        </table>
    </body></html>'''


def envoyer_email_rapport(destinataire: str, nb_series: int, nb_papiers: int, nb_nouveautes: int, nb_a_traiter: int, duree: float):
    """Envoie un email de rapport même sans nouveautés"""
    
    statut = "✅ Scan OK" if nb_nouveautes == 0 else f"🎉 {nb_nouveautes} nouveauté(s)"
    
    html = f'''<!DOCTYPE html>
    <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
    <body style="margin:0;padding:0;background-color:#f0f4f8;font-family:system-ui,-apple-system,sans-serif;">
        <table cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color:#f0f4f8;padding:40px 20px;">
            <tr><td align="center">
                <table cellpadding="0" cellspacing="0" border="0" width="600" style="max-width:600px;background-color:white;border-radius:16px;overflow:hidden;box-shadow:0 10px 40px rgba(0,0,0,0.1);">
                    <tr><td style="background:linear-gradient(135deg,#2d3748 0%,#4a5568 100%);padding:30px;text-align:center;">
                        <h1 style="color:white;margin:0;font-size:24px;">📊 Rapport MangaVega Tracker</h1>
                        <p style="color:rgba(255,255,255,0.8);margin:8px 0 0 0;font-size:14px;">v{config.VERSION} • {datetime.now().strftime("%d/%m/%Y %H:%M")}</p>
                    </td></tr>
                    <tr><td style="padding:30px;">
                        <table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-bottom:20px;">
                            <tr>
                                <td style="text-align:center;padding:15px;background:#f7fafc;border-radius:8px;width:20%;">
                                    <div style="font-size:28px;font-weight:700;color:#2d3748;">{nb_series}</div>
                                    <div style="font-size:12px;color:#718096;">Séries</div>
                                </td>
                                <td style="width:6px;"></td>
                                <td style="text-align:center;padding:15px;background:#f7fafc;border-radius:8px;width:20%;">
                                    <div style="font-size:28px;font-weight:700;color:#2d3748;">{nb_papiers}</div>
                                    <div style="font-size:12px;color:#718096;">Volumes</div>
                                </td>
                                <td style="width:6px;"></td>
                                <td style="text-align:center;padding:15px;background:{'#f0fff4' if nb_nouveautes > 0 else '#f7fafc'};border-radius:8px;width:20%;">
                                    <div style="font-size:28px;font-weight:700;color:{'#38a169' if nb_nouveautes > 0 else '#2d3748'};">{nb_nouveautes}</div>
                                    <div style="font-size:12px;color:#718096;">Nouveautés</div>
                                </td>
                                <td style="width:6px;"></td>
                                <td style="text-align:center;padding:15px;background:{'#fffff0' if nb_a_traiter > 0 else '#f7fafc'};border-radius:8px;width:20%;">
                                    <div style="font-size:28px;font-weight:700;color:{'#d69e2e' if nb_a_traiter > 0 else '#2d3748'};">{nb_a_traiter}</div>
                                    <div style="font-size:12px;color:#718096;">À traiter</div>
                                </td>
                                <td style="width:6px;"></td>
                                <td style="text-align:center;padding:15px;background:#f7fafc;border-radius:8px;width:20%;">
                                    <div style="font-size:28px;font-weight:700;color:#2d3748;">{duree:.0f}s</div>
                                    <div style="font-size:12px;color:#718096;">Durée</div>
                                </td>
                            </tr>
                        </table>
                        <p style="text-align:center;font-size:16px;color:#4a5568;margin:20px 0;">
                            {'🎉 De nouvelles sorties ont été détectées !' if nb_nouveautes > 0 else '📭 Aucune nouvelle sortie détectée cette fois-ci.'}
                        </p>
                        {f'<p style="text-align:center;font-size:14px;color:#d69e2e;margin:10px 0;">⏳ {nb_a_traiter} volume(s) en attente de validation dans le viewer.</p>' if nb_a_traiter > 0 else ''}
                        <p style="text-align:center;font-size:13px;color:#a0aec0;margin:10px 0 0 0;">
                            Consultez le détail sur le <a href="https://dunstancooper.github.io/mangavega-v7/manga_collection_viewer.html" style="color:#667eea;">viewer en ligne</a>.
                        </p>
                    </td></tr>
                    <tr><td style="background-color:#f7fafc;padding:20px 30px;text-align:center;border-top:1px solid #e2e8f0;">
                        <p style="margin:0;color:#718096;font-size:12px;">MangaVega Tracker v{config.VERSION} • {statut}</p>
                    </td></tr>
                </table>
            </td></tr>
        </table>
    </body></html>'''
    
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"📊 Manga Tracker: {nb_series} séries, {nb_papiers} volumes, {nb_nouveautes} nouveauté(s), {nb_a_traiter} à traiter"
    msg['From'] = config.EMAIL_EXPEDITEUR
    msg['To'] = destinataire
    msg.attach(MIMEText(html, 'html'))
    
    for port in config.SMTP_PORTS:
        try:
            logger.info(f"📧 Envoi rapport via port {port}...")
            if port == 465:
                server = smtplib.SMTP_SSL(config.SMTP_SERVER, port, timeout=10)
            else:
                server = smtplib.SMTP(config.SMTP_SERVER, port, timeout=10)
                if port == 587:
                    server.starttls()
            server.login(config.EMAIL_EXPEDITEUR, config.MOT_DE_PASSE_APP)
            server.send_message(msg)
            server.quit()
            logger.info(f"✅ Rapport envoyé avec succès!\n")
            return
        except Exception as e:
            logger.warning(f"⚠️  Port {port}: {str(e)[:80]}")
    
    logger.error("❌ Échec d'envoi du rapport sur tous les ports\n")


def envoyer_email(destinataire: str, nouvelles_publications: List[Dict]):
    """Envoie l'email"""
    if not nouvelles_publications:
        logger.info("📧 Aucune nouveauté, pas d'email envoyé")
        return
    
    msg = MIMEMultipart('alternative')
    nb_nouvelles = sum(1 for p in nouvelles_publications if not p.get('date_modifiee'))
    nb_dates_modifiees = sum(1 for p in nouvelles_publications if p.get('date_modifiee'))
    
    sujet_parts = []
    if nb_nouvelles > 0:
        sujet_parts.append(f"{nb_nouvelles} nouvelle(s) sortie(s)")
    if nb_dates_modifiees > 0:
        sujet_parts.append(f"⚠️ {nb_dates_modifiees} date(s) modifiée(s)")
    
    msg['Subject'] = f"📚 {' + '.join(sujet_parts)}"
    msg['From'] = config.EMAIL_EXPEDITEUR
    msg['To'] = destinataire
    
    html = generer_email_html(nouvelles_publications)
    msg.attach(MIMEText(html, 'html'))
    
    for port in config.SMTP_PORTS:
        try:
            logger.info(f"📧 Envoi email via port {port}...")
            
            if port == 465:
                server = smtplib.SMTP_SSL(config.SMTP_SERVER, port, timeout=10)
            else:
                server = smtplib.SMTP(config.SMTP_SERVER, port, timeout=10)
                if port == 587:
                    server.starttls()
            
            server.login(config.EMAIL_EXPEDITEUR, config.MOT_DE_PASSE_APP)
            server.send_message(msg)
            server.quit()
            
            logger.info(f"✅ Email envoyé avec succès!\n")
            return
            
        except Exception as e:
            logger.warning(f"⚠️  Port {port}: {str(e)[:80]}")
    
    logger.error("❌ Échec d'envoi sur tous les ports\n")


def _editeur_romaji(editeur_jp: str) -> str:
    """Convertit un nom d'éditeur japonais en romaji via utils.EDITEURS_ROMAJI."""
    if not editeur_jp:
        return 'Éditeur non renseigné'
    try:
        import utils as _u
        # Correspondance exacte d'abord
        if editeur_jp in _u.EDITEURS_ROMAJI:
            return _u.EDITEURS_ROMAJI[editeur_jp]
        # Correspondance partielle (cherche la clé JP la plus longue contenue dans editeur_jp)
        match = max(
            ((jp, rom) for jp, rom in _u.EDITEURS_ROMAJI.items() if jp in editeur_jp),
            key=lambda x: len(x[0]),
            default=None
        )
        if match:
            return match[1]
    except Exception:
        pass
    return editeur_jp  # Fallback : garder le nom JP


def _type_serie(serie_jp: str) -> str:
    """Retourne ' (LN)' ou ' (Manga)' selon le suffixe dans serie_jp."""
    if '[LN]' in (serie_jp or ''):
        return ' (LN)'
    if '[MANGA]' in (serie_jp or ''):
        return ' (Manga)'
    return ''


def _grouper_par_editeur(items: List[Dict]) -> dict:
    """Groupe une liste de volumes/actions par éditeur romaji (ordre alphabétique)."""
    from collections import defaultdict
    groupes: dict = defaultdict(list)
    for item in items:
        editeur_jp = (item.get('editeur') or '').strip()
        editeur = _editeur_romaji(editeur_jp)
        groupes[editeur].append(item)
    return dict(sorted(groupes.items()))


def _format_date_fr(date_iso: str) -> str:
    """Convertit 2026-03-26 en 26/03/2026."""
    try:
        return datetime.strptime(date_iso, '%Y-%m-%d').strftime('%d/%m/%Y')
    except Exception:
        return date_iso


def _envoyer_smtp(msg, label: str):
    """Envoi SMTP avec fallback sur les ports configurés."""
    for port in config.SMTP_PORTS:
        try:
            logger.info(f"📧 Envoi {label} via port {port}...")
            if port == 465:
                server = smtplib.SMTP_SSL(config.SMTP_SERVER, port, timeout=10)
            else:
                server = smtplib.SMTP(config.SMTP_SERVER, port, timeout=10)
                if port == 587:
                    server.starttls()
            server.login(config.EMAIL_EXPEDITEUR, config.MOT_DE_PASSE_APP)
            server.send_message(msg)
            server.quit()
            logger.info(f"✅ {label} envoyé!\n")
            return
        except Exception as e:
            logger.warning(f"⚠️  Port {port}: {str(e)[:80]}")
    logger.error(f"❌ Échec envoi {label} sur tous les ports\n")


def envoyer_email_workflow(destinataire: str, volumes_nouveaux: List[Dict], actions_retard: List[Dict]):
    """
    Email combiné : nouvelles demandes (jour J) + relances (> 10j), groupés par éditeur.
    Chaque ligne indique le contexte : nouveau ou dernière relance.
    """
    if not volumes_nouveaux and not actions_retard:
        return

    # Construire la liste unifiée avec marqueur de type
    items: List[Dict] = []
    for v in volumes_nouveaux:
        items.append({**v, '_type': 'nouveau'})
    for a in actions_retard:
        items.append({**a, '_type': 'relance'})

    groupes = _grouper_par_editeur(items)

    nb_n = len(volumes_nouveaux)
    nb_r = len(actions_retard)

    lignes = ["Bonjour Nicolas,", ""]
    if nb_n and nb_r:
        lignes.append("Voici les nouvelles demandes et les relances en cours :")
    elif nb_n:
        lignes.append("Il faudrait faire les offres pour :")
    else:
        lignes.append("As-tu pu envoyer les offres pour :")
    lignes.append("")

    for editeur, group_items in groupes.items():
        lignes.append(f"{editeur} :")
        for item in group_items:
            titre = item.get('nom_fr') or item.get('serie_jp', '')
            type_s = _type_serie(item.get('serie_jp', ''))
            tome = item.get('tome', '?')
            date_sortie = _format_date_fr(item.get('date_sortie_jp') or item.get('date_declenchement', ''))
            if item['_type'] == 'nouveau':
                contexte = "il vient de sortir et s'ajoute à la liste"
            else:
                date_contact = _format_date_fr(item.get('date_declenchement', ''))
                contexte = f"je t'avais fait un mail sur ce tome le {date_contact}"
            lignes.append(f"- {titre}{type_s} T{tome}, sortie le {date_sortie} — {contexte}")
        lignes.append("")

    lignes += ["Merci,", "", "Eloi"]

    if nb_n and nb_r:
        sujet = f"Offres éditoriales — {datetime.now().strftime('%d/%m/%Y')}"
    elif nb_n:
        sujet = f"Offres à demander — {datetime.now().strftime('%d/%m/%Y')}"
    else:
        sujet = f"Relance offres — {datetime.now().strftime('%d/%m/%Y')}"

    date_fichier = datetime.now().strftime('%Y-%m-%d_%Hh%M')
    nom_fichier = f"workflow_nwk_{date_fichier}.eml"

    msg = MIMEText("\n".join(lignes), 'plain', 'utf-8')
    msg['Subject'] = sujet
    msg['From'] = config.EMAIL_DESTINATAIRE_WORKFLOW
    msg['To'] = destinataire

    # 1. Essayer de créer un brouillon IMAP dans M365
    if _deposer_brouillon_workflow(msg):
        return
    # 2. Fallback : sauvegarder en .eml
    _sauvegarder_eml(msg, nom_fichier)


def envoyer_email_relances_workflow(destinataire: str, actions_retard: List[Dict]):
    """Conservé pour compatibilité — délègue à envoyer_email_workflow."""
    envoyer_email_workflow(destinataire, [], actions_retard)




def envoyer_email_fin_pause(destinataire: str, pauses_expirees: List[Dict]):
    """Envoie un email de notification quand des pauses workflow arrivent à expiration."""
    if not pauses_expirees:
        return

    VIEWER_URL = "https://dunstancooper.github.io/mangavega-v7/manga_collection_viewer.html"

    lignes_html = ""
    for p in pauses_expirees:
        serie = p.get('serie_jp', '')[:35]
        tome = p.get('tome', '?')
        label = p.get('label', p.get('etape', ''))
        pause_date = p.get('pause_jusqu_au', '')
        lignes_html += f'''
        <tr>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;">{serie}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:center;">T{tome}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;">{label}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:center;color:#2d8a4e;">{pause_date}</td>
        </tr>'''

    html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;background:#f5f5f5;margin:0;padding:20px;">
<table width="600" style="margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
<tr><td style="background:linear-gradient(135deg,#2d8a4e,#1a6035);padding:24px 30px;">
    <h1 style="color:#fff;margin:0;font-size:1.3rem;">▶️ Fin de pause — Suivi Éditorial</h1>
    <p style="color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:0.9rem;">
        {len(pauses_expirees)} étape(s) reprennent leur suivi normal
    </p>
</td></tr>
<tr><td style="padding:24px 30px;">
    <p style="color:#555;margin:0 0 16px;">Les pauses suivantes sont arrivées à expiration. Le suivi reprend normalement.</p>
    <table width="100%" style="border-collapse:collapse;font-size:0.85rem;">
        <thead>
            <tr style="background:#f7f7f7;">
                <th style="padding:8px 12px;text-align:left;border-bottom:2px solid #ddd;">Série</th>
                <th style="padding:8px 12px;text-align:center;border-bottom:2px solid #ddd;">Tome</th>
                <th style="padding:8px 12px;text-align:left;border-bottom:2px solid #ddd;">Étape</th>
                <th style="padding:8px 12px;text-align:center;border-bottom:2px solid #ddd;">Pause jusqu'au</th>
            </tr>
        </thead>
        <tbody>{lignes_html}</tbody>
    </table>
    <div style="margin-top:20px;text-align:center;">
        <a href="{VIEWER_URL}" style="display:inline-block;background:#2d8a4e;color:#fff;padding:10px 24px;border-radius:8px;text-decoration:none;font-weight:600;">
            📑 Ouvrir le Suivi éditorial →
        </a>
    </div>
</td></tr>
</table>
</body></html>'''

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"▶️ Fin de pause workflow — {len(pauses_expirees)} étape(s) reprennent"
    msg['From'] = config.EMAIL_EXPEDITEUR
    msg['To'] = destinataire
    msg.attach(MIMEText(html, 'html'))

    for port in config.SMTP_PORTS:
        try:
            logger.info(f"📧 Envoi fin-de-pause workflow via port {port}...")
            if port == 465:
                server = smtplib.SMTP_SSL(config.SMTP_SERVER, port, timeout=10)
            else:
                server = smtplib.SMTP(config.SMTP_SERVER, port, timeout=10)
                if port == 587:
                    server.starttls()
            server.login(config.EMAIL_EXPEDITEUR, config.MOT_DE_PASSE_APP)
            server.send_message(msg)
            server.quit()
            logger.info("✅ Email fin de pause workflow envoyé!\n")
            return
        except Exception as e:
            logger.warning(f"⚠️  Port {port}: {str(e)[:80]}")

    logger.error("❌ Échec envoi fin-de-pause workflow sur tous les ports\n")


def envoyer_email_debut_workflow(destinataire: str, volumes: List[Dict]):
    """
    Envoie un email le jour de sortie JP d'un tome :
    demande à NWK de faire les offres, groupé par éditeur.
    """
    if not volumes:
        return

    groupes = _grouper_par_editeur(volumes)

    lignes = ["Bonjour Nicolas,", "", "Il faudrait faire les offres pour :", ""]
    for editeur, vols in groupes.items():
        lignes.append(f"{editeur} :")
        for v in vols:
            titre = v.get('nom_fr') or v.get('serie_jp', '')
            type_s = _type_serie(v.get('serie_jp', ''))
            tome = v.get('tome', '?')
            date_jp = _format_date_fr(v.get('date_sortie_jp', ''))
            lignes.append(f"- {titre}{type_s} T{tome}, sortie le {date_jp}")
        lignes.append("")
    lignes += ["Merci,", "", "Eloi"]

    msg = MIMEText("\n".join(lignes), 'plain', 'utf-8')
    msg['Subject'] = f"Offres à demander — {datetime.now().strftime('%d/%m/%Y')}"
    msg['From'] = config.EMAIL_EXPEDITEUR
    msg['To'] = destinataire
    _envoyer_smtp(msg, "email début workflow")
