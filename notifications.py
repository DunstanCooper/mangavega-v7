#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MangaVega Tracker - Notifications email
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from typing import List, Dict

import config

logger = config.logger


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


def envoyer_email_relances_workflow(destinataire: str, actions_retard: List[Dict]):
    """Envoie un email de relance pour les étapes du workflow éditorial en retard."""
    if not actions_retard:
        return

    VIEWER_URL = "https://dunstancooper.github.io/mangavega-v7/manga_collection_viewer.html"

    lignes_html = ""
    for a in actions_retard:
        serie = a.get('serie_jp', '')[:35]
        tome = a.get('tome', '?')
        label = a.get('label', a.get('etape', ''))
        jours = a.get('jours_ecoules', 0)
        relances = a.get('nb_relances', 0)
        bg = '#ffeaea' if jours > 10 else '#fff8e1'
        lignes_html += f'''
        <tr style="background:{bg};">
            <td style="padding:8px 12px;border-bottom:1px solid #eee;">{serie}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:center;">T{tome}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;">{label}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:center;color:#e53e3e;font-weight:600;">{jours}j</td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:center;color:#999;">{relances}</td>
        </tr>'''

    html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;background:#f5f5f5;margin:0;padding:20px;">
<table width="600" style="margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
<tr><td style="background:linear-gradient(135deg,#e53e3e,#c0392b);padding:24px 30px;">
    <h1 style="color:#fff;margin:0;font-size:1.3rem;">⏰ Relances Suivi Éditorial</h1>
    <p style="color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:0.9rem;">
        {len(actions_retard)} action(s) en attente depuis plus de 10 jours
    </p>
</td></tr>
<tr><td style="padding:24px 30px;">
    <table width="100%" style="border-collapse:collapse;font-size:0.85rem;">
        <thead>
            <tr style="background:#f7f7f7;">
                <th style="padding:8px 12px;text-align:left;border-bottom:2px solid #ddd;">Série</th>
                <th style="padding:8px 12px;text-align:center;border-bottom:2px solid #ddd;">Tome</th>
                <th style="padding:8px 12px;text-align:left;border-bottom:2px solid #ddd;">Étape</th>
                <th style="padding:8px 12px;text-align:center;border-bottom:2px solid #ddd;">Délai</th>
                <th style="padding:8px 12px;text-align:center;border-bottom:2px solid #ddd;">Relances</th>
            </tr>
        </thead>
        <tbody>{lignes_html}</tbody>
    </table>
    <div style="margin-top:20px;text-align:center;">
        <a href="{VIEWER_URL}" style="display:inline-block;background:#e53e3e;color:#fff;padding:10px 24px;border-radius:8px;text-decoration:none;font-weight:600;">
            📑 Ouvrir le Suivi éditorial →
        </a>
    </div>
</td></tr>
</table>
</body></html>'''

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"⏰ Relances workflow éditorial — {len(actions_retard)} action(s) en attente"
    msg['From'] = config.EMAIL_EXPEDITEUR
    msg['To'] = destinataire
    msg.attach(MIMEText(html, 'html'))

    for port in config.SMTP_PORTS:
        try:
            logger.info(f"📧 Envoi relances workflow via port {port}...")
            if port == 465:
                server = smtplib.SMTP_SSL(config.SMTP_SERVER, port, timeout=10)
            else:
                server = smtplib.SMTP(config.SMTP_SERVER, port, timeout=10)
                if port == 587:
                    server.starttls()
            server.login(config.EMAIL_EXPEDITEUR, config.MOT_DE_PASSE_APP)
            server.send_message(msg)
            server.quit()
            logger.info("✅ Email relances workflow envoyé!\n")
            return
        except Exception as e:
            logger.warning(f"⚠️  Port {port}: {str(e)[:80]}")

    logger.error("❌ Échec envoi relances workflow sur tous les ports\n")


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
    "Il est temps de demander à NWK de faire une offre pour ce titre !"
    """
    if not volumes:
        return

    VIEWER_URL = "https://dunstancooper.github.io/mangavega-v7/manga_collection_viewer.html"

    lignes_html = ""
    for v in volumes:
        serie = (v.get('nom_fr') or v.get('serie_jp', ''))[:40]
        tome = v.get('tome', '?')
        date_jp = v.get('date_sortie_jp', '')
        lignes_html += f'''
        <tr>
            <td style="padding:10px 14px;border-bottom:1px solid #eee;font-weight:600;">{serie}</td>
            <td style="padding:10px 14px;border-bottom:1px solid #eee;text-align:center;">T{tome}</td>
            <td style="padding:10px 14px;border-bottom:1px solid #eee;text-align:center;color:#555;">{date_jp}</td>
        </tr>'''

    nb = len(volumes)
    titre_email = f"📚 {nb} tome(s) sorti(s) au Japon — Il est temps de contacter NWK"

    html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;background:#f5f5f5;margin:0;padding:20px;">
<table width="620" style="margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
<tr><td style="background:linear-gradient(135deg,#667eea,#764ba2);padding:28px 32px;">
    <h1 style="color:#fff;margin:0;font-size:1.4rem;">📚 Il est temps de contacter NWK !</h1>
    <p style="color:rgba(255,255,255,0.85);margin:8px 0 0;font-size:0.95rem;">
        {nb} tome(s) sorti(s) au Japon aujourd'hui — démarrez les démarches éditoriales
    </p>
</td></tr>
<tr><td style="padding:28px 32px;">
    <p style="color:#444;margin:0 0 20px;font-size:0.95rem;">
        Les tomes suivants sont disponibles au Japon. Transmettez à NWK pour qu'il/elle
        sollicite une offre auprès de l'éditeur japonais.
    </p>
    <table width="100%" style="border-collapse:collapse;font-size:0.88rem;">
        <thead>
            <tr style="background:#f0f0f8;">
                <th style="padding:10px 14px;text-align:left;border-bottom:2px solid #ddd;">Titre</th>
                <th style="padding:10px 14px;text-align:center;border-bottom:2px solid #ddd;">Tome</th>
                <th style="padding:10px 14px;text-align:center;border-bottom:2px solid #ddd;">Sortie JP</th>
            </tr>
        </thead>
        <tbody>{lignes_html}</tbody>
    </table>
    <div style="margin-top:24px;padding:16px;background:#f8f4ff;border-radius:8px;border-left:4px solid #667eea;">
        <p style="margin:0;font-size:0.88rem;color:#555;">
            <strong>Action requise :</strong> Contacter NWK pour demander une offre auprès de l'éditeur JP.
            Une relance automatique sera envoyée si l'étape 1 n'est pas complétée sous 10 jours.
        </p>
    </div>
    <div style="margin-top:20px;text-align:center;">
        <a href="{VIEWER_URL}#tab-editorial" style="display:inline-block;background:#667eea;color:#fff;padding:11px 28px;border-radius:8px;text-decoration:none;font-weight:600;font-size:0.9rem;">
            📑 Ouvrir le Suivi éditorial →
        </a>
    </div>
</td></tr>
</table>
</body></html>'''

    msg = MIMEMultipart('alternative')
    msg['Subject'] = titre_email
    msg['From'] = config.EMAIL_EXPEDITEUR
    msg['To'] = destinataire
    msg.attach(MIMEText(html, 'html'))

    for port in config.SMTP_PORTS:
        try:
            logger.info(f"📧 Envoi email début workflow via port {port}...")
            if port == 465:
                server = smtplib.SMTP_SSL(config.SMTP_SERVER, port, timeout=10)
            else:
                server = smtplib.SMTP(config.SMTP_SERVER, port, timeout=10)
                if port == 587:
                    server.starttls()
            server.login(config.EMAIL_EXPEDITEUR, config.MOT_DE_PASSE_APP)
            server.send_message(msg)
            server.quit()
            logger.info("✅ Email début workflow envoyé!\n")
            return
        except Exception as e:
            logger.warning(f"⚠️  Port {port}: {str(e)[:80]}")

    logger.error("❌ Échec envoi email début workflow sur tous les ports\n")
