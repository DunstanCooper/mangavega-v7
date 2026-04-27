#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MangaVega Tracker - Configuration et constantes globales
"""

# ============================================================================
# VERSION
# ============================================================================
VERSION = "7.0.0"
VERSION_DATE = "2026-02-17"
# ============================================================================

import os
import logging
from datetime import datetime
from typing import Set

# ============================================================================
# FICHIERS ET CHEMINS
# ============================================================================
LOG_FILE = 'manga_tracker.log'
CORRECTIONS_FILE = "corrections.json"
SERIES_CONFIG_FILE = "series_config.json"
MANGAS_LISTE_FILE = "mangas_liste.json"

# ============================================================================
# DATE SEUIL (valeur par défaut, mise à jour depuis le Gist)
# ============================================================================
DATE_SEUIL = datetime(2025, 6, 1)

# ============================================================================
# CHARGEMENT DU FICHIER .env (secrets locaux)
# Le .env est chargé ICI, avant toute lecture de os.environ, pour que
# les variables soient disponibles dans les lignes qui suivent.
# ============================================================================
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(_env_path):
    with open(_env_path, 'r', encoding='utf-8') as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _key, _value = _line.split('=', 1)
                _key = _key.strip()
                _value = _value.strip().strip('"').strip("'")
                if _key and _value:
                    os.environ[_key] = _value

# ============================================================================
# EMAIL (lus depuis le .env — ne jamais mettre d'email/mot de passe ici)
# ============================================================================
EMAIL_DESTINATAIRE = os.environ.get('EMAIL_DESTINATAIRE', '')
EMAIL_DESTINATAIRE_WORKFLOW = os.environ.get('EMAIL_DESTINATAIRE_WORKFLOW', '') or os.environ.get('EMAIL_DESTINATAIRE', '')
EMAIL_EXPEDITEUR = os.environ.get('EMAIL_EXPEDITEUR', '')
MOT_DE_PASSE_APP = os.environ.get('MOT_DE_PASSE_APP', '')
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORTS = [465, 587, 25, 2525]

# ============================================================================
# GIST (synchronisation avec le viewer)
# ============================================================================
GIST_TOKEN = os.environ.get('GIST_TOKEN') or os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
GIST_ID = "30cd62947f2ea6c07a044ab3546fb08f"
GIST_API_URL = f"https://api.github.com/gists/{GIST_ID}"

# Debug: afficher si le token est présent (sans révéler la valeur)
if GIST_TOKEN:
    print(f"GIST_TOKEN detecte ({len(GIST_TOKEN)} caracteres)")
else:
    print("GIST_TOKEN non defini - les modifications du Gist ne seront pas sauvegardees")
    print("Variables verifiees: GIST_TOKEN, GH_TOKEN, GITHUB_TOKEN")

# ============================================================================
# FORMATS PAPIER VALIDES
# ============================================================================
FORMATS_PAPIER_VALIDES = ['単行本', 'ペーパーバック', '文庫', 'コミック', 'Paperback', 'Tankobon']

# ============================================================================
# LOGGING
# ============================================================================
# Rotation : le log précédent est archivé dans logs/, on garde les 10 derniers
import glob
import shutil

_LOGS_DIR = 'logs'
os.makedirs(_LOGS_DIR, exist_ok=True)

# Archiver le log précédent s'il existe
if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 0:
    # Nom d'archive basé sur la date de modification du fichier
    mtime = os.path.getmtime(LOG_FILE)
    archive_date = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d_%Hh%M')
    archive_name = os.path.join(_LOGS_DIR, f'manga_tracker_{archive_date}.log')
    # Éviter d'écraser une archive existante
    if not os.path.exists(archive_name):
        shutil.copy2(LOG_FILE, archive_name)
    # Nettoyer les vieux logs (garder les 10 plus récents)
    archives = sorted(glob.glob(os.path.join(_LOGS_DIR, 'manga_tracker_*.log')))
    for old_log in archives[:-10]:
        try:
            os.remove(old_log)
        except OSError:
            pass

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8'),  # Écrase à chaque run
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# HTTP CLIENT
# ============================================================================
try:
    from curl_cffi.requests import AsyncSession as CurlAsyncSession
    CURL_CFFI_DISPONIBLE = True
except ImportError:
    CURL_CFFI_DISPONIBLE = False

# Headers pour fallback aiohttp uniquement
# Note: quand curl_cffi est disponible avec impersonate="chrome",
# ces HEADERS sont utilisés uniquement en fallback aiohttp.
# curl_cffi génère automatiquement ses propres headers cohérents
# avec la version de Chrome impersonnée (Sec-Ch-Ua, Sec-Fetch-*, etc.)
# Passer des headers custom avec impersonate crée des conflits/doublons.
# Ref: https://curl-cffi.readthedocs.io/en/latest/quick_start.html
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,ja;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
}

# ============================================================================
# GLOBALS MUTABLES (modifiés par sync.py et pipeline.py)
# ============================================================================
ASINS_HORS_SUJET: Set[str] = set()
GIST_CORRECTIONS = {}
GIST_SERIES_CONFIG = {}
GIST_MODIFIED = False

MANGAS_A_SUIVRE = []
TRADUCTIONS_FR = {}

# ============================================================================
# TRADUCTIONS MANUELLES
# Format: "Titre japonais exact": "Titre français"
# Les clés correspondent aux noms dans MANGAS_A_SUIVRE (sans le suffixe [LN]/[MANGA])
# Utilisé comme fallback par rechercher_traductions() dans pipeline.py
# Les traductions sont sauvegardées en BDD au premier scan de chaque série
# ============================================================================
TRADUCTIONS_MANUELLES = {
    "拝啓見知らぬ旦那様、離婚していただきます": "Cher époux inconnu, je veux divorcer",
    "令和のダラさん": "Dame Dara de Reiwa",
    "マグメル深海水族館": "Deep sea aquarium Magmell",
    "ダンジョンバンド": "Dungeon Band",
    "ELDEN RING 遠き狭間の物語": "Elden Ring Distant Tales Between",
    "あくまでクジャクの話です。": "Fier comme un paon",
    "頼くんとヨリを戻すわけには!": "First Love, Worst Love",
    "ギフテッド": "Gifted",
    "機動戦士Ζガンダム Define": "Gundam Define",
    "ヒモクズ花くんは死にたがり": "Hane ne peut vivre sans moi",
    "氷菓": "Hyouka",
    "石神戦記": "Ishigami Senki",
    "ひねもすのたり日記": "Journal d'une vie tranquille",
    "カグライ ～神楽と雷人～": "KaguRai",
    "結界師の一輪華": "La Fiancée du maître des frontières",
    "泥の国": "Land of Mud",
    "今さらですが、幼なじみを好きになってしまいました": "L'année où je suis tombée amoureuse de lui",
    "イクサガミ": "Last Samurai Standing",
    "本なら売るほど": "Le Bouquiniste",
    "放課後帰宅びより": "Le Club des flâneurs",
    "ヤクザにお風呂で働かされてます。": "Le Yakuza des bains publics (et moi)",
    "大正學生愛妻家": "Les fiancés de l'ère Taisho",
    "開花アパートメント": "Les Mystères de la Résidence Kaika",
    "百瀬アキラの初恋破綻中。": "Les premières amours difficiles de Momose Akira",
    "ラブ・バレット": "Love Bullet",
    "鍛冶屋ではじめる異世界スローライフ": "Ma vie tranquille de forgeron dans un autre monde",
    "満州アヘンスクワッド": "Manchuria Opium Squad",
    "みなと商事コインランドリー": "Minato Laundry",
    "わたしの幸せな結婚": "My Happy Marriage (LN)",
    "くまぐらし": "Ours !",
    "夜分に吸血失礼します": "Permettez que je goûte votre sang",
    "現象X 超常現象捜査録": "Phenomenon X",
    "夫婦以上、恋人未満。": "Presque mariés, loin d'être amoureux",
    "峠鬼": "Primal Gods",
    "リビルドワールド": "Rebuild the World",
    "時々ボソッとロシア語でデレる隣のアーリャさん": "Alya Sometimes Hides Her Feelings in Russian",
    "佐々木とピーちゃん": "Sasaki to Pi-chan",
    "勇者刑に処す": "Sentenced to a Heroic Punishment",
    "サーヴァント ビースト": "Servant Beast",
    "死亡遊戯で飯を食う。": "Shiboyugi",
    "音盤紀行": "Sounds of Vinyl",
    "ニセモノの錬金術師": "The Fake Alchemist",
    "針子の乙女": "La jeune fille à l'aiguille",
    "となりの席のヤツがそういう目で見てくる": "Tu ne penses qu'à ça !",
    "アンダーク 新しい透明な力のすべて": "Undark",
    "誰が勇者を殺したか": "Who killed the hero",
    "ウィキッドスポット": "Wicked Spot",
    "成仏させてよ！": "Yakuza zen",
    "矢野くんの普通の日々": "Yano, une vie ordinaire",
    "対ありでした。 ～お嬢さまは格闘ゲームなんてしない～": "Young ladies Don't Play",
    "ユア・フォルマ": "Your Forma (LN)",
    "近畿地方のある場所について": "About a place in the Kinki region",
    # Séries avec serie_id (pour distinguer manga et LN)
    "alya-manga": "Roshidere Alya (Manga)",
    "alya-ln": "Roshidere Alya (LN)",
}

# ============================================================================
# CONSTANTES DE PIPELINE (extraites du monolithe pour centralisation)
# ============================================================================

# Mots-clés pour filtrer les produits dérivés (cosplay, figurines, etc.)
MOTS_CLES_DERIVES = [
    'コスプレ', 'コスチューム', '衣装', 'ウィッグ', '髪飾り', 'フィギュア',
    'グッズ', 'ポスター', 'タペストリー', '靴', 'バニー',
    'Official Book', 'オフィシャルブック', 'ガイドブック', 'ファンブック'
]

# Titres courts qui donnent trop de résultats sans guillemets
TITRES_GENERIQUES = ['ギフテッド']

# ============================================================================
# CLÉS STRUCTURELLES pour sauvegarder mangas_liste.json
# Seules ces clés sont persistées dans le fichier (pas urls_supplementaires, etc.)
# ============================================================================
CLES_PERSISTEES_MANGA = {'nom', 'url_suffix', 'filtre', 'type', 'serie_id'}
