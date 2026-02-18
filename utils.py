#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MangaVega Tracker - Fonctions utilitaires pures
"""

import re
import unicodedata
from typing import List, Dict, Optional, Set

import config


def strip_type_suffix(nom: str) -> str:
    """Retire le suffixe [LN] ou [MANGA] d'un nom de série pour l'affichage"""
    if nom.endswith(' [LN]'):
        return nom[:-5]
    if nom.endswith(' [MANGA]'):
        return nom[:-8]
    return nom


def est_format_papier(format_str: str) -> bool:
    """
    Vérifie si le format correspond à un livre papier.
    
    Formats valides:
    - 単行本 (tankōbon - format manga standard)
    - ペーパーバック (paperback)
    - 文庫 (bunko - format poche/LN)
    - コミック (comic - manga papier)
    - Paperback, Tankobon (versions anglaises)
    
    Formats exclus:
    - Kindle版 (ebook)
    - 雑誌 (magazine)
    - ムック (mook - sauf si explicitement papier)
    """
    if not format_str:
        return False
    return any(f in format_str for f in config.FORMATS_PAPIER_VALIDES)


def est_asin_hors_sujet_manuel(asin: str) -> bool:
    """Vérifie si un ASIN est marqué manuellement comme hors-sujet"""
    return asin in config.ASINS_HORS_SUJET


# ============================================================================
# NORMALISATION ÉDITEUR
# ============================================================================

def normaliser_editeur(editeur: str) -> str:
    """
    Normalise le nom d'un éditeur pour permettre la comparaison.
    
    Résout un label/collection vers son éditeur parent.
    Exemples:
    - "少年マガジンKC" → "kodansha"  (label Kodansha)
    - "角川コミックス・エース" → "kadokawa"  (label Kadokawa)
    - "Kadokawa Sneaker Bunko" → "kadokawa"
    - "Shonen Magazine" → "kodansha"
    """
    if not editeur:
        return ""
    
    # Table label → éditeur parent (en minuscules, sans espaces/ponctuation)
    # Appliquée APRÈS le nettoyage de base
    LABEL_VERS_PARENT = {
        # === KODANSHA ===
        'shonenmagazine': 'kodansha',
        'shonenmagazinekc': 'kodansha',
        'magazinekc': 'kodansha',
        'kcdeluxe': 'kodansha',
        'kc': 'kodansha',
        'youngmagazine': 'kodansha',
        'youngmagazinekc': 'kodansha',
        'morning': 'kodansha',
        'morningkc': 'kodansha',
        'afternoon': 'kodansha',
        'afternoonkc': 'kodansha',
        'eveningkc': 'kodansha',
        'kodansha': 'kodansha',
        'kodanshacomics': 'kodansha',
        'kcmanga': 'kodansha',
        'sirius': 'kodansha',
        'siriuskc': 'kodansha',
        'rivierekc': 'kodansha',
        'palcykc': 'kodansha',
        'dayscomics': 'kodansha',
        # === KADOKAWA ===
        'kadokawa': 'kadokawa',
        'kadokawacomics': 'kadokawa',
        'kadokawacomicsace': 'kadokawa',
        'kadokawasneakerbunko': 'kadokawa',
        'dengeki': 'kadokawa',
        'dengekicomics': 'kadokawa',
        'dengekibunko': 'kadokawa',
        'dengekidaioh': 'kadokawa',
        'asciimediaworks': 'kadokawa',
        'mediaworks': 'kadokawa',
        'enterbrain': 'kadokawa',
        'mfbunko': 'kadokawa',
        'mfbunkoj': 'kadokawa',
        'mfc': 'kadokawa',
        'dragoncomicsage': 'kadokawa',
        'dragoncomics': 'kadokawa',
        'compace': 'kadokawa',
        'comptiq': 'kadokawa',
        'bcomicskadoboku': 'kadokawa',
        'flos': 'kadokawa',
        'floscomics': 'kadokawa',
        # === SHUEISHA ===
        'shueisha': 'shueisha',
        'jumpcomics': 'shueisha',
        'youngjump': 'shueisha',
        'youngjumpcomics': 'shueisha',
        'grandjump': 'shueisha',
        'ultrajump': 'shueisha',
        'margaretcomics': 'shueisha',
        'ribon': 'shueisha',
        'ribbon': 'shueisha',
        'dashxbunko': 'shueisha',
        # === SHOGAKUKAN ===
        'shogakukan': 'shogakukan',
        'sunday': 'shogakukan',
        'sundaycomics': 'shogakukan',
        'bigcomics': 'shogakukan',
        'bigcomic': 'shogakukan',
        'bigcomicsspirits': 'shogakukan',
        'flowercomics': 'shogakukan',
        'gangan': 'shogakukan',
        'uracomics': 'shogakukan',
        # === SQUARE ENIX ===
        'squareenix': 'squareenix',
        'gangancomics': 'squareenix',
        'gangancomicsonline': 'squareenix',
        'gangancomicsjoker': 'squareenix',
        'gfantasy': 'squareenix',
        'younggangan': 'squareenix',
        'biggangancomics': 'squareenix',
        # === HAKUSENSHA ===
        'hakusensha': 'hakusensha',
        'younganimal': 'hakusensha',
        'younganimalcomics': 'hakusensha',
        'hanatoname': 'hakusensha',
        'hanatoamecomics': 'hakusensha',
        'lala': 'hakusensha',
        'melody': 'hakusensha',
        'jets': 'hakusensha',
        'jetscomics': 'hakusensha',
        # === AKITA SHOTEN ===
        'akitashoten': 'akitashoten',
        'champion': 'akitashoten',
        'championcomics': 'akitashoten',
        'shonenchampion': 'akitashoten',
        # === AUTRES ===
        'ichijinsha': 'ichijinsha',
        'gene': 'ichijinsha',
        'rexcomics': 'ichijinsha',
        'futabasha': 'futabasha',
        'action': 'futabasha',
        'actioncomics': 'futabasha',
        'houbunsha': 'houbunsha',
        'harta': 'kadokawa',    # Harta est un label Kadokawa (via Enterbrain)
        'hartacomics': 'kadokawa',
        'hue': 'kadokawa',
        'bunch': 'coamix',
        'bunchcomics': 'coamix',
        'coamix': 'coamix',
        'overlap': 'overlap',
        'overlapbunko': 'overlap',
        'hobbyjapan': 'hobbyjapan',
        'hjbunko': 'hobbyjapan',
        'sbcreative': 'sbcreative',
        'gabunko': 'sbcreative',
        'heroes': 'heroes',
        'heroescomics': 'heroes',
        'flexcomics': 'flexcomics',
        'maggarden': 'maggarden',
        'bladecomics': 'maggarden',
        'leed': 'leed',
        'ran': 'leed',
        'northstarspictures': 'northstarspictures',
        'shinchosha': 'shinchosha',
        'bungeishunju': 'bungeishunju',
        'kobunsha': 'kobunsha',
        'gentosha': 'gentosha',
        'shonengazosha': 'shonengazosha',
        'pixiv': 'pixiv',
    }
    
    # Supprimer les espaces
    editeur = editeur.replace(' ', '').replace('　', '')
    
    # Supprimer les caractères de ponctuation
    editeur = editeur.replace('・', '').replace('-', '').replace('−', '')
    
    # Convertir en minuscules pour la comparaison
    editeur = editeur.lower()
    
    # Résoudre le label vers l'éditeur parent
    if editeur in LABEL_VERS_PARENT:
        return LABEL_VERS_PARENT[editeur]
    
    return editeur


def editeur_match(editeur_volume: str, editeur_officiel: str) -> bool:
    """
    Vérifie si l'éditeur d'un volume correspond à l'éditeur officiel de la série.
    Gère les cas comme "Kadokawa Comics" (label) vs "kadokawa" (éditeur de base).
    Comparaison normalisée : l'un doit contenir l'autre.
    """
    if not editeur_volume or not editeur_officiel:
        return True  # Pas de filtre si info manquante
    a = normaliser_editeur(editeur_volume)
    b = normaliser_editeur(editeur_officiel) if editeur_officiel == editeur_officiel.lower() else normaliser_editeur(editeur_officiel)
    # L'un contient l'autre (kadokawacomics contient kadokawa, ou l'inverse)
    return a in b or b in a


def convertir_editeur_romaji(editeur: str) -> str:
    """
    Convertit le nom d'un éditeur japonais en romaji.
    
    Maintient une table de correspondance des éditeurs majeurs.
    """
    if not editeur:
        return ""
    
    # Table de correspondance éditeurs japonais → romaji
    EDITEURS_ROMAJI = {
        # Majeurs
        'KADOKAWA': 'Kadokawa',
        '角川書店': 'Kadokawa',
        'カドカワ': 'Kadokawa',
        '角川': 'Kadokawa',
        '講談社': 'Kodansha',
        '小学館': 'Shogakukan',
        '集英社': 'Shueisha',
        'スクウェア・エニックス': 'Square Enix',
        'スクエニ': 'Square Enix',
        '白泉社': 'Hakusensha',
        '秋田書店': 'Akita Shoten',
        '双葉社': 'Futabasha',
        '芳文社': 'Houbunsha',
        '一迅社': 'Ichijinsha',
        'アスキー・メディアワークス': 'ASCII Media Works',
        'メディアワークス': 'Media Works',
        '電撃': 'Dengeki',
        'マッグガーデン': 'Mag Garden',
        'エンターブレイン': 'Enterbrain',
        'ホビージャパン': 'Hobby Japan',
        'オーバーラップ': 'Overlap',
        'アース・スター': 'Earth Star',
        'SBクリエイティブ': 'SB Creative',
        'ソフトバンク': 'SoftBank',
        '新潮社': 'Shinchosha',
        '文藝春秋': 'Bungeishunju',
        '光文社': 'Kobunsha',
        '幻冬舎': 'Gentosha',
        'リイド社': 'Leed',
        '少年画報社': 'Shonen Gahosha',
        'コアミックス': 'Coamix',
        'ノース・スターズ・ピクチャーズ': 'North Stars Pictures',
        # Labels/Collections
        '角川コミックス': 'Kadokawa Comics',
        '角川スニーカー文庫': 'Kadokawa Sneaker Bunko',
        '電撃コミックス': 'Dengeki Comics',
        '電撃文庫': 'Dengeki Bunko',
        '少年マガジン': 'Shonen Magazine',
        'マガジンKC': 'Magazine KC',
        'ヤングマガジン': 'Young Magazine',
        'ジャンプコミックス': 'Jump Comics',
        'サンデー': 'Sunday',
        'ガンガン': 'Gangan',
        'ビッグコミックス': 'Big Comics',
        'ビッグコミック': 'Big Comics',
        'モーニング': 'Morning',
        'アフタヌーン': 'Afternoon',
        'ハルタ': 'Harta',
        'ハルタコミックス': 'Harta Comics',
        'MFC': 'MFC',
        'MF文庫': 'MF Bunko',
        'フレックスコミックス': 'Flex Comics',
        'ヒーローズ': 'Heroes',
        'バンチ': 'Bunch',
        'BUNCH': 'Bunch',
        'アクション': 'Action',
        'ヤングアニマル': 'Young Animal',
        'チャンピオン': 'Champion',
        'ジーン': 'Gene',
        'ピクシブ': 'Pixiv',
        'フロース': 'Flos',
        'ヒュー': 'Hue',
        '乱': 'Ran',
        'KC': 'KC',
        'KCデラックス': 'KC Deluxe',
    }
    
    # Chercher une correspondance exacte
    if editeur in EDITEURS_ROMAJI:
        return EDITEURS_ROMAJI[editeur]
    
    # Chercher une correspondance partielle (du plus long au plus court pour éviter les faux positifs)
    for jp, romaji in sorted(EDITEURS_ROMAJI.items(), key=lambda x: -len(x[0])):
        if jp in editeur:
            return romaji
    
    # Si déjà en romaji/anglais, retourner tel quel
    if re.match(r'^[A-Za-z\s\-\.]+$', editeur):
        return editeur
    
    # Sinon retourner l'original
    return editeur


def extraire_editeur(titre: str) -> Optional[str]:
    """
    Extrait l'éditeur du titre Amazon.
    
    Le format typique est: "タイトル (X) (エディター)"
    L'éditeur est généralement dans les dernières parenthèses.
    """
    if not titre:
        return None
    
    # Trouver tous les groupes entre parenthèses
    matches = re.findall(r'\(([^()]+)\)', titre)
    
    if not matches:
        # Essayer avec les parenthèses japonaises
        matches = re.findall(r'（([^（）]+)）', titre)
    
    if not matches:
        return None
    
    # Parcourir à partir de la fin pour trouver l'éditeur
    for match in reversed(matches):
        # Ignorer les nombres (numéros de tome)
        if re.match(r'^\d+$', match):
            continue
        # Ignorer les indicateurs de volume
        if match in ['完', '上', '下', '前編', '後編']:
            continue
        # Ignorer les formats comme "第1集"
        if re.match(r'^第\d+集$', match):
            continue
        # C'est probablement l'éditeur
        return match
    
    return None


# ============================================================================
# FONCTIONS ASIN / URL
# ============================================================================

def extraire_asin(url: str) -> str:
    """Extrait l'ASIN d'une URL"""
    match = re.search(r'/dp/([A-Za-z0-9]{10})', url)
    return match.group(1) if match else "?"


def est_asin_papier(asin: str) -> bool:
    """
    Vérifie si l'ASIN correspond à un livre papier japonais.
    
    Règles ASIN Amazon Japon :
    - Livres papier : commencent par un chiffre (généralement 4 pour ISBN japonais)
    - Ebooks/Kindle : commencent par 'B'
    - Lots/Sets : commencent souvent par 'B'
    
    Returns:
        True si c'est potentiellement un livre papier, False sinon
    """
    if not asin or asin == "?":
        return False
    
    # Les ASINs de livres papier japonais commencent par un chiffre (ISBN)
    # Les ebooks/Kindle/lots commencent par 'B'
    return asin[0].isdigit()


def est_ebook(url: str, titre: str) -> bool:
    """Détermine si c'est un ebook"""
    if '/ebook/dp/' in url or '-ebook/dp/' in url or 'kindle' in url.lower():
        return True
    mots_cles = ['Kindle版', 'kindle版', '電子書籍', 'ebook', 'Ebook', 'eBook']
    return any(mot in titre for mot in mots_cles)


# ============================================================================
# NORMALISATION TITRE
# ============================================================================

def normaliser_titre(texte: str) -> str:
    """
    Normalise les variations de caractères pour la comparaison de titres.
    Gère : NFKC (pleine largeur→demi), lettres grecques→latines, tirets,
    ponctuation, équivalences hiragana/kanji.
    Note : ne met PAS en lowercase (les appelants le font si nécessaire).
    """
    # NFKC : pleine largeur → demi-largeur, ligatures, compatibilité
    texte = unicodedata.normalize('NFKC', texte)
    
    # Lettres grecques visuellement similaires aux latines
    greek_to_latin = {
        'Α': 'A', 'Β': 'B', 'Ε': 'E', 'Ζ': 'Z', 'Η': 'H', 'Ι': 'I',
        'Κ': 'K', 'Μ': 'M', 'Ν': 'N', 'Ο': 'O', 'Ρ': 'P', 'Τ': 'T',
        'Υ': 'Y', 'Χ': 'X',
        'α': 'a', 'β': 'b', 'ε': 'e', 'ζ': 'z', 'η': 'h', 'ι': 'i',
        'κ': 'k', 'μ': 'm', 'ν': 'n', 'ο': 'o', 'ρ': 'p', 'τ': 't',
        'υ': 'y', 'χ': 'x',
    }
    for greek, latin in greek_to_latin.items():
        texte = texte.replace(greek, latin)
    
    # Tirets variés → tiret ASCII (SAUF ー chōon katakana U+30FC)
    for ch in ['―', '─', '—', '–', '−', '〜', '～']:
        texte = texte.replace(ch, '-')
    
    # Ponctuation pleine largeur → ASCII (certaines survivent à NFKC)
    texte = texte.replace('！', '!').replace('？', '?')
    texte = texte.replace('（', '(').replace('）', ')')
    texte = texte.replace('：', ':').replace('；', ';')
    texte = texte.replace('，', ',').replace('。', '.')
    
    # Équivalences hiragana/kanji courantes
    equivalences = [
        ('わたし', '私'),      # watashi
        ('わたしの', '私の'),  # watashi no
        ('ぼく', '僕'),        # boku
        ('おれ', '俺'),        # ore
        ('かれ', '彼'),        # kare
        ('かのじょ', '彼女'),  # kanojo
    ]
    for hiragana, kanji in equivalences:
        texte = texte.replace(hiragana, kanji)
    
    # Espaces multiples → espace simple
    texte = ' '.join(texte.split())
    
    return texte.strip()


def normaliser_url(url: str) -> str:
    """Normalise URL Amazon"""
    match = re.search(r'/dp/([A-Z0-9]{10})', url)
    if match:
        return f"https://www.amazon.co.jp/dp/{match.group(1)}"
    return url


# ============================================================================
# EXTRACTION NUMÉRO DE TOME
# ============================================================================

# Chiffres romains : dictionnaire partagé (utilisé par le parser de tome)
CHIFFRES_ROMAINS = {
    'XV': 15, 'XIV': 14, 'XIII': 13, 'XII': 12, 'XI': 11,
    'VIII': 8, 'VII': 7, 'IX': 9, 'X': 10,
    'IV': 4, 'VI': 6, 'V': 5,
    'III': 3, 'II': 2, 'I': 1,
}

# Chiffres kanji : du plus long au plus court pour éviter les faux positifs
CHIFFRES_KANJI = {
    '二十': 20, '十九': 19, '十八': 18, '十七': 17, '十六': 16,
    '十五': 15, '十四': 14, '十三': 13, '十二': 12, '十一': 11,
    '十': 10, '九': 9, '八': 8, '七': 7, '六': 6,
    '五': 5, '四': 4, '三': 3, '二': 2, '一': 1,
}

# Formats spéciaux japonais (上/下/前/後)
FORMATS_SPECIAUX = {
    r'[（(]上[)）]': 1,    # (上)
    r'[（(]下[)）]': 2,    # (下)
    r'上巻': 1,            # 上巻
    r'下巻': 2,            # 下巻
    r'前編': 1,            # 前編
    r'後編': 2,            # 後編
    r'完結編': 'FIN',      # 完結編
}

# Classe de caractères japonais (hiragana + katakana + kanji + prolongation)
_JP = r'[ぁ-んァ-ヿ一-龯ー々〆]'


def extraire_numero_tome(titre: str) -> Optional[int]:
    """
    Extrait le numéro de tome depuis un titre Amazon japonais.
    
    Fonction UNIQUE de parsing de tome, appelée par :
    - extraire_infos_produit() (page produit /dp/)
    - extraire_infos_featured() (résultat de recherche)
    - pipeline.py (corrections et recherche étendue)
    
    Patterns testés dans l'ordre (du plus spécifique au plus générique) :
    1.  第X巻 / 第X集         — format japonais formel
    2.  X巻                   — format japonais simple
    3.  (X) / （X）           — parenthèses (le plus courant)
    4.  X（完）               — tome final
    5.  Vol.X / Volume X      — format occidental
    6.  Chiffres romains      — I, II, III...
    7.  Chiffres kanji        — 一, 二, 三...
    8.  上/下/前/後           — formats spéciaux
    9.  " X (" avant paren   — chiffre isolé devant parenthèse
    10. -X / −X              — tiret suivi d'un numéro
    11. Collé fin JP          — しました1 MFC
    12. Entre japonais        — す 1 懲 (chiffre entre deux kanji/kana)
    13. Fin de titre          — タイトル 7
    14. Dernier recours       — chiffre 1-2 digits isolé (après 10 premiers chars)
    
    Returns:
        int ou None. Peut aussi retourner 'FIN' pour 完結編.
    """
    if not titre:
        return None
    
    titre = str(titre)
    
    # --- Patterns précis (sans ambiguïté) ---
    
    # 1. 第X巻 / 第X集 (format japonais formel)
    match = re.search(r'第\s*(\d+)\s*[巻集]', titre)
    if match:
        return int(match.group(1))
    
    # 2. X巻 (format japonais simple, hors lots)
    if '巻セット' not in titre:
        match = re.search(r'0*(\d+)\s*巻', titre)
        if match:
            return int(match.group(1))
    
    # 3. (X) / （X） (parenthèses — le plus courant)
    match = re.search(r'[（(]\s*0*(\d+)\s*[)）]', titre)
    if match:
        return int(match.group(1))
    
    # 4. X（完）— tome final avec marqueur de fin
    match = re.search(r'[\s　](\d{1,2})[（(]完[)）]', titre)
    if match:
        return int(match.group(1))
    
    # 5. Vol.X / Volume X / vol X (format occidental)
    match = re.search(r'vol(?:ume)?\.?\s*0*(\d+)', titre, re.IGNORECASE)
    if match:
        return int(match.group(1))
    
    # 6. Chiffres romains isolés (espace avant + espace/fin/parenthèse/巻 après)
    for romain, numero in CHIFFRES_ROMAINS.items():
        if re.search(r'\s' + romain + r'(\s|$|[)）]|巻)', titre):
            return numero
    
    # 7. Chiffres kanji (espace avant + espace/fin/parenthèse/巻 après)
    for kanji, numero in CHIFFRES_KANJI.items():
        if re.search(r'[\s　]' + kanji + r'(\s|　|$|[)）(（]|巻)', titre):
            return numero
    
    # 8. Formats spéciaux japonais 上/下/前/後/完結
    for pattern, numero in FORMATS_SPECIAUX.items():
        if re.search(pattern, titre):
            return numero
    
    # --- Patterns moins précis (fallbacks) ---
    
    # 9. Chiffre isolé devant parenthèse : " 2 (" ou " 2 （"
    match = re.search(r'\s(\d+)\s+[（(]', titre)
    if match:
        return int(match.group(1))
    
    # 10. Tiret suivi d'un numéro : "-4" ou "−4"
    match = re.search(r'[\s　]?[-−]\s*(\d{1,2})(?:\s|$|[（(])', titre)
    if match:
        return int(match.group(1))
    
    # 11. Numéro collé à la fin d'un mot japonais : "しました1 MFC"
    match = re.search(_JP + r'(\d{1,2})\s+\S', titre)
    if match:
        return int(match.group(1))
    
    # 12. Chiffre isolé entre caractères japonais : "す 1 懲"
    match = re.search(_JP + r'\s+(\d{1,2})\s+' + _JP, titre)
    if match and int(match.group(1)) <= 50:
        return int(match.group(1))
    
    # 13. Chiffre en fin de titre : "タイトル 7"
    match = re.search(r'[\s　](\d{1,2})\s*$', titre)
    if match:
        return int(match.group(1))
    
    # 14. Dernier recours : chiffre 1-2 digits isolé (après les 10 premiers chars)
    # Ignore les grands nombres comme 9004 qui font partie du titre
    if len(titre) > 10:
        match = re.search(r'(?<![0-9])(\d{1,2})(?![0-9])', titre[10:])
        if match and int(match.group(1)) <= 50:
            return int(match.group(1))
    
    return None


def analyser_tomes_manquants(volumes: List[Dict]) -> Dict:
    """
    Analyse une liste de volumes pour détecter les tomes manquants.
    
    Retourne:
    - tomes_trouves: set des numéros de tomes trouvés
    - tome_max: le plus grand numéro de tome
    - tomes_manquants: set des numéros de tomes manquants (entre 1 et tome_max)
    - nb_tomes_attendus: tome_max (on s'attend à avoir tous les tomes de 1 à max)
    - complet: True si aucun tome manquant
    """
    tomes_trouves = set()
    
    for vol in volumes:
        tome = vol.get('tome', '')
        if tome and str(tome).isdigit():
            tomes_trouves.add(int(tome))
    
    if not tomes_trouves:
        return {
            'tomes_trouves': set(),
            'tome_max': 0,
            'tomes_manquants': set(),
            'nb_tomes_attendus': 0,
            'complet': True
        }
    
    tome_max = max(tomes_trouves)
    tomes_attendus = set(range(1, tome_max + 1))
    tomes_manquants = tomes_attendus - tomes_trouves
    
    return {
        'tomes_trouves': tomes_trouves,
        'tome_max': tome_max,
        'tomes_manquants': tomes_manquants,
        'nb_tomes_attendus': tome_max,
        'complet': len(tomes_manquants) == 0
    }
