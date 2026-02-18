"""
MangaVega API Server — Serveur local pour piloter le tracker depuis le viewer.

Endpoints:
    GET  /              → Sert le viewer HTML
    GET  /api/status    → État du serveur + infos BDD
    POST /api/sync      → Applique les corrections du Gist à la BDD
    POST /api/scan      → Lance un scan (complet ou --serie)
    POST /api/backup    → Sauvegarde la BDD
    GET  /api/log       → Dernières lignes du log en cours

Usage:
    python api_server.py
    → Ouvre automatiquement http://localhost:5000 dans le navigateur
"""

import os
import sys
import json
import shutil
import sqlite3
import asyncio
import subprocess
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Autorise les requêtes cross-origin (si viewer ouvert depuis GitHub Pages)

# === CONFIG ===
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / 'manga_alerts.db'
LOG_PATH = BASE_DIR / 'manga_tracker.log'
BACKUP_DIR = BASE_DIR / 'backups'
VIEWER_FILE = BASE_DIR / 'manga_collection_viewer.html'

# État global du scan
scan_state = {
    'running': False,
    'started_at': None,
    'process': None,
    'last_result': None,
    'last_finished': None
}


# =============================================================================
# ROUTES
# =============================================================================

@app.route('/')
def serve_viewer():
    """Sert le viewer HTML directement depuis Flask."""
    if VIEWER_FILE.exists():
        return send_file(VIEWER_FILE)
    return '<h1>Viewer non trouvé</h1><p>Placez manga_collection_viewer.html dans le même dossier.</p>', 404


@app.route('/api/status')
def api_status():
    """Retourne l'état du serveur et des stats BDD."""
    stats = {'server': 'online', 'scan_running': scan_state['running']}
    
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM volumes')
            stats['total_volumes'] = cursor.fetchone()[0]
            cursor.execute('SELECT COUNT(DISTINCT serie_jp) FROM volumes')
            stats['total_series'] = cursor.fetchone()[0]
            cursor.execute('SELECT COUNT(*) FROM featured_history')
            stats['total_featured'] = cursor.fetchone()[0]
            
            # Dernier scan
            cursor.execute('SELECT MAX(date_maj) FROM volumes')
            r = cursor.fetchone()
            stats['last_scan'] = r[0] if r and r[0] else None
            
            conn.close()
        except Exception as e:
            stats['db_error'] = str(e)
    else:
        stats['db_exists'] = False
    
    if scan_state['running'] and scan_state['started_at']:
        stats['scan_started_at'] = scan_state['started_at']
    if scan_state['last_result']:
        stats['last_result'] = scan_state['last_result']
    if scan_state['last_finished']:
        stats['last_finished'] = scan_state['last_finished']
    
    return jsonify(stats)


@app.route('/api/sync', methods=['POST'])
def api_sync():
    """Applique les corrections du Gist à la BDD locale (sans relancer le scan)."""
    if scan_state['running']:
        return jsonify({'error': 'Un scan est déjà en cours'}), 409
    
    try:
        # Importer les modules MangaVega
        sys.path.insert(0, str(BASE_DIR))
        import config
        from database import DatabaseManager
        import sync as sync_module
        
        db = DatabaseManager()
        
        # Charger et appliquer les corrections depuis le Gist
        sync_module.charger_gist_config()
        counts = sync_module.charger_corrections(db)
        
        # Charger la config des séries
        sync_module.charger_series_config(db)
        
        db.close()
        
        return jsonify({
            'success': True,
            'message': 'Corrections appliquées depuis le Gist',
            'details': counts if counts else 'Aucune nouvelle correction'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/scan', methods=['POST'])
def api_scan():
    """Lance un scan en arrière-plan."""
    if scan_state['running']:
        return jsonify({'error': 'Un scan est déjà en cours'}), 409
    
    data = request.get_json(silent=True) or {}
    serie = data.get('serie', None)
    no_email = data.get('no_email', True)
    no_push = data.get('no_push', False)
    
    # Construire la commande
    cmd = [sys.executable, str(BASE_DIR / 'app.py')]
    if serie:
        cmd.extend(['--serie', serie])
    if no_email:
        cmd.append('--no-email')
    if no_push:
        cmd.append('--no-push')
    
    def run_scan():
        scan_state['running'] = True
        scan_state['started_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        scan_state['last_result'] = None
        try:
            result = subprocess.run(
                cmd, cwd=str(BASE_DIR),
                capture_output=True, text=True, timeout=7200  # 2h max
            )
            scan_state['last_result'] = 'success' if result.returncode == 0 else 'error'
        except subprocess.TimeoutExpired:
            scan_state['last_result'] = 'timeout'
        except Exception as e:
            scan_state['last_result'] = f'error: {e}'
        finally:
            scan_state['running'] = False
            scan_state['last_finished'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    thread = threading.Thread(target=run_scan, daemon=True)
    thread.start()
    
    return jsonify({
        'success': True,
        'message': f'Scan lancé {"(série: " + serie + ")" if serie else "(complet)"}',
        'command': ' '.join(cmd)
    })


@app.route('/api/backup', methods=['POST'])
def api_backup():
    """Sauvegarde la BDD avec horodatage."""
    if not DB_PATH.exists():
        return jsonify({'error': 'BDD non trouvée'}), 404
    
    BACKUP_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime('%Y-%m-%d_%Hh%M')
    backup_name = f'manga_alerts_{timestamp}.db'
    backup_path = BACKUP_DIR / backup_name
    
    try:
        shutil.copy2(str(DB_PATH), str(backup_path))
        
        # Garder les 10 derniers backups
        backups = sorted(BACKUP_DIR.glob('manga_alerts_*.db'))
        while len(backups) > 10:
            backups[0].unlink()
            backups.pop(0)
        
        size_mb = backup_path.stat().st_size / (1024 * 1024)
        return jsonify({
            'success': True,
            'message': f'Backup créé : {backup_name}',
            'size_mb': round(size_mb, 2),
            'total_backups': len(list(BACKUP_DIR.glob('manga_alerts_*.db')))
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/log')
def api_log():
    """Retourne les dernières lignes du log."""
    lines = int(request.args.get('lines', 50))
    
    if not LOG_PATH.exists():
        return jsonify({'log': '', 'message': 'Pas de log disponible'})
    
    try:
        with open(LOG_PATH, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
        
        tail = all_lines[-lines:] if len(all_lines) > lines else all_lines
        return jsonify({
            'log': ''.join(tail),
            'total_lines': len(all_lines),
            'showing': len(tail)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 MangaVega API Server")
    print(f"📁 Dossier: {BASE_DIR}")
    print(f"🗃️  BDD: {'✅' if DB_PATH.exists() else '❌'} {DB_PATH.name}")
    print(f"📄 Viewer: {'✅' if VIEWER_FILE.exists() else '❌'} {VIEWER_FILE.name}")
    print("=" * 60)
    print(f"🌐 Viewer:  http://localhost:5000")
    print(f"📡 API:     http://localhost:5000/api/status")
    print("=" * 60)
    
    # Ouvrir le navigateur automatiquement
    threading.Timer(1.5, lambda: webbrowser.open('http://localhost:5000')).start()
    
    app.run(host='127.0.0.1', port=5000, debug=False)
