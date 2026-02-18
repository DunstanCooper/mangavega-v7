#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MangaVega Tracker - Scraper Amazon (HTTP, extraction HTML)
"""

import asyncio
import random
import re
from typing import List, Dict, Optional

import aiohttp
from bs4 import BeautifulSoup

import config
from utils import (
    extraire_asin, extraire_numero_tome, extraire_editeur,
    convertir_editeur_romaji, est_format_papier,
    normaliser_titre, strip_type_suffix
)

logger = config.logger

# Importer curl_cffi si disponible
if config.CURL_CFFI_DISPONIBLE:
    from curl_cffi.requests import AsyncSession as CurlAsyncSession


async def get_html(session, url: str, delai: float = 0.6, max_retries: int = 2) -> Optional[str]:
    """Récupère le HTML d'une URL Amazon avec anti-détection."""
    est_recherche = '/s?' in url or '/s/' in url
    est_produit = '/dp/' in url
    url_courte = url.split('?')[0][-60:] if '?' in url else url[-60:]
    
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                wait = min(10 * (2 ** attempt) + random.uniform(0, 5), 60)
                logger.info(f"      ⏳ Backoff retry #{attempt}: {wait:.0f}s...")
                await asyncio.sleep(wait)
            elif est_recherche:
                wait = random.uniform(2.0, 4.5)
                await asyncio.sleep(wait)
            elif est_produit:
                wait = random.uniform(0.8, 2.0)
                await asyncio.sleep(wait)
            else:
                wait = random.uniform(delai * 0.5, delai * 1.5)
                await asyncio.sleep(wait)
            
            if config.CURL_CFFI_DISPONIBLE and hasattr(session, '_curl_cffi_session'):
                cffi_session = session._curl_cffi_session
                extra_headers = {"Accept-Language": "ja-JP,ja;q=0.9"}
                if est_produit:
                    extra_headers["Referer"] = "https://www.amazon.co.jp/"
                
                response = await cffi_session.get(url, headers=extra_headers, timeout=30, allow_redirects=True)
                status = response.status_code
                content_len = len(response.text) if response.text else 0
                cookies_count = len(cffi_session.cookies) if hasattr(cffi_session, 'cookies') else -1
                logger.info(f"      [HTTP] {status} | {content_len:,} chars | cookies:{cookies_count} | {url_courte}")
                
                if status == 200:
                    html = response.text
                    if html and len(html) < 5000:
                        html_lower = html.lower()
                        if 'captcha' in html_lower or 'robot' in html_lower or 'automated access' in html_lower:
                            logger.warning(f"      ⚠️  Captcha/bot détecté dans réponse 200 ({content_len} chars)")
                            continue
                    if html and content_len > 500:
                        return html
                    else:
                        logger.warning(f"      ⚠️  Réponse trop courte ({content_len} chars)")
                        continue
                elif status == 503:
                    logger.warning(f"      ⚠️  Rate limit (503)")
                    continue
                elif status == 404:
                    logger.info(f"      ℹ️  Page introuvable (404)")
                    return None
                else:
                    logger.warning(f"      ⚠️  HTTP {status}")
                    continue
            else:
                aio_session = session._aiohttp_session if hasattr(session, '_aiohttp_session') else session
                async with aio_session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    content = await response.text()
                    content_len = len(content) if content else 0
                    logger.info(f"      [HTTP-aio] {response.status} | {content_len:,} chars | {url_courte}")
                    if response.status == 200:
                        return content
                    elif response.status == 503:
                        logger.warning(f"      ⚠️  Rate limit (503), attente 10s...")
                        await asyncio.sleep(10)
                        continue
                    else:
                        logger.warning(f"      ⚠️  HTTP {response.status}")
                        return None
                    
        except asyncio.TimeoutError:
            logger.warning(f"      ⚠️  Timeout (attempt {attempt+1}/{max_retries+1})")
            if attempt >= max_retries:
                logger.error(f"      ❌ Timeout définitif")
        except Exception as e:
            err_str = str(e)[:80]
            logger.warning(f"      ⚠️  Erreur (attempt {attempt+1}/{max_retries+1}): {err_str}")
            if attempt >= max_retries:
                logger.error(f"      ❌ Erreur définitive: {err_str}")
    return None


class SessionWrapper:
    """Encapsule curl_cffi AsyncSession pour le scraping Amazon."""
    def __init__(self):
        self._curl_cffi_session = None
        self._aiohttp_session = None
        self._warmed_up = False
    
    async def __aenter__(self):
        if config.CURL_CFFI_DISPONIBLE:
            self._curl_cffi_session = CurlAsyncSession(impersonate="chrome", timeout=30)
            await self._curl_cffi_session.__aenter__()
            logger.info("🌐 Session HTTP: curl_cffi (impersonate=chrome, TLS+HTTP/2 fingerprint)")
            logger.info("   📋 Headers: Accept-Language: ja-JP (force pages japonaises)")
        else:
            self._aiohttp_session = aiohttp.ClientSession(headers=config.HEADERS)
            await self._aiohttp_session.__aenter__()
            logger.warning("🌐 Session HTTP: aiohttp (⚠️ PAS de TLS impersonation)")
            logger.warning("   ⚠️  curl_cffi non disponible - installer avec: pip install curl-cffi")
        return self
    
    async def __aexit__(self, *args):
        if self._curl_cffi_session:
            await self._curl_cffi_session.__aexit__(*args)
        if self._aiohttp_session:
            await self._aiohttp_session.__aexit__(*args)
    
    async def warm_up(self):
        """Visite amazon.co.jp pour initialiser les cookies de session."""
        if self._warmed_up:
            return
        try:
            logger.info("   🔥 Warm-up: visite amazon.co.jp pour recevoir les cookies...")
            if self._curl_cffi_session:
                response = await self._curl_cffi_session.get("https://www.amazon.co.jp/", timeout=15, allow_redirects=True)
                status = response.status_code
                
                # Forcer la langue japonaise via le cookie i18n-prefs
                # Amazon utilise ce cookie pour la devise et la langue de la page
                try:
                    self._curl_cffi_session.cookies.set("i18n-prefs", "JPY", domain=".amazon.co.jp")
                    logger.info("   🇯🇵 Cookie i18n-prefs=JPY injecté (force pages japonaises)")
                except Exception as e:
                    logger.warning(f"   ⚠️  Impossible d'injecter le cookie i18n-prefs: {e}")
                
                if hasattr(self._curl_cffi_session, 'cookies'):
                    cookies = self._curl_cffi_session.cookies
                    cookie_names = []
                    try:
                        for c in cookies:
                            if hasattr(c, 'name'):
                                cookie_names.append(c.name)
                            elif isinstance(c, str):
                                cookie_names.append(c)
                    except TypeError:
                        try:
                            cookie_names = list(cookies.keys()) if hasattr(cookies, 'keys') else []
                        except:
                            cookie_names = []
                    logger.info(f"   ✅ Warm-up: HTTP {status} | {len(cookie_names)} cookies: {', '.join(cookie_names[:8])}")
                else:
                    logger.info(f"   ✅ Warm-up: HTTP {status}")
            elif self._aiohttp_session:
                async with self._aiohttp_session.get("https://www.amazon.co.jp/", timeout=aiohttp.ClientTimeout(total=15)) as response:
                    logger.info(f"   ✅ Warm-up: HTTP {response.status}")
            self._warmed_up = True
            pause = random.uniform(2.0, 4.0)
            logger.info(f"   ⏸️  Pause post-warm-up: {pause:.1f}s")
            await asyncio.sleep(pause)
        except Exception as e:
            logger.warning(f"   ⚠️  Warm-up échoué: {str(e)[:80]}")
            logger.warning(f"   → On continue quand même (le scan fonctionnera, mais risque accru de 503)")
            self._warmed_up = True


async def extraire_version_papier(html: str, format_cible: str = None, debug: bool = False) -> Optional[str]:
    """Extrait le lien vers la version papier depuis une page Kindle
    
    Args:
        html: HTML de la page Kindle
        format_cible: Type de format à chercher
            - "manga" ou None : cherche コミック/Comic (défaut)
            - "ln" : cherche 文庫/Bunko (light novel)
            - "all" : cherche tous les formats papier
        debug: Afficher les logs de debug
    """
    if not html:
        return None
    
    soup = BeautifulSoup(html, 'lxml')
    
    # Définir les keywords selon le format cible
    if format_cible == "ln":
        # Light Novel : chercher Bunko
        papier_keywords = ['文庫', 'Bunko']
    elif format_cible == "all":
        # Tous les formats papier
        papier_keywords = ['コミック', 'Comic', '文庫', 'Bunko', '単行本', 'Tankobon', 'ペーパーバック', 'Paperback']
    else:
        # Par défaut : Manga uniquement
        papier_keywords = ['コミック', 'Comic']
    
    kindle_keywords = ['kindle', 'Kindle', 'デジタル', '電子']
    
    # Pattern pour extraire un ASIN depuis différents formats d'URL Amazon
    asin_patterns = [
        r'/dp/([A-Z0-9]{10})',           # /dp/ASIN (classique)
        r'/gp/product/([A-Z0-9]{10})',   # /gp/product/ASIN (ancien format)
        r'/product/([A-Z0-9]{10})',      # /product/ASIN
    ]
    
    def extraire_asin_from_href(href: str) -> Optional[str]:
        """Extrait un ASIN depuis un href avec plusieurs patterns"""
        for pattern in asin_patterns:
            match = re.search(pattern, href)
            if match:
                return match.group(1)
        return None
    
    def extraire_asin_from_element(element) -> Optional[str]:
        """Extrait un ASIN depuis un élément HTML (href, data-asin, data-value)"""
        # 1. Chercher dans le href
        href = element.get('href', '')
        asin = extraire_asin_from_href(href)
        if asin:
            return asin
        
        # 2. Chercher dans les attributs data-* de l'élément lui-même
        for attr in ['data-asin', 'data-value', 'data-dp-url']:
            val = element.get(attr, '')
            if val:
                asin = extraire_asin_from_href(val)
                if asin:
                    return asin
                # data-asin peut contenir directement l'ASIN sans URL
                if re.match(r'^[A-Z0-9]{10}$', val):
                    return val
        
        # 3. Chercher dans les attributs data-* du parent (li, span, div)
        parent = element.parent
        if parent:
            for attr in ['data-asin', 'data-value', 'data-dp-url']:
                val = parent.get(attr, '')
                if val:
                    asin = extraire_asin_from_href(val)
                    if asin:
                        return asin
                    if re.match(r'^[A-Z0-9]{10}$', val):
                        return val
        
        return None
    
    # Chercher dans la section des formats (tmmSwatches ou MediaMatrix)
    formats_section = soup.find("div", {"id": "tmmSwatches"}) or soup.find("div", {"id": "MediaMatrix"})
    
    if debug:
        logger.info(f"      [DEBUG] formats_section trouvée: {formats_section is not None}")
    
    if formats_section:
        for link in formats_section.find_all("a"):
            text = link.get_text().strip()
            href = link.get('href', '')
            
            is_papier = any(kw in text for kw in papier_keywords)
            is_kindle = any(kw in text for kw in kindle_keywords)
            
            if debug:
                logger.info(f"      [DEBUG] Link: '{text[:30]}' papier={is_papier} kindle={is_kindle} href={href[:50]}")
            
            if is_papier and not is_kindle:
                asin_papier = extraire_asin_from_element(link)
                if asin_papier:
                    if debug:
                        logger.info(f"      [DEBUG] ASIN extrait: {asin_papier}")
                    return f"https://www.amazon.co.jp/dp/{asin_papier}"
    
    # Alternative: chercher les swatches individuels
    swatches = soup.find_all("li", class_=lambda x: x and 'swatchElement' in x)
    
    if debug:
        logger.info(f"      [DEBUG] Swatches trouvés: {len(swatches)}")
    
    for swatch in swatches:
        text = swatch.get_text().strip()
        link = swatch.find("a", href=True)
        
        if link:
            is_papier = any(kw in text for kw in papier_keywords)
            is_kindle = any(kw in text for kw in kindle_keywords)
            
            if is_papier and not is_kindle:
                asin_papier = extraire_asin_from_element(link)
                # Aussi chercher dans le swatch (li) directement
                if not asin_papier:
                    asin_papier = extraire_asin_from_element(swatch)
                if asin_papier:
                    return f"https://www.amazon.co.jp/dp/{asin_papier}"
    
    return None


async def extraire_volumes_depuis_page(session: aiohttp.ClientSession, url_ou_asin: str, nom_manga: str, 
                                       debug=False, sources: List[str] = None) -> Dict[str, List[str]]:
    """
    Extrait les volumes liés depuis une page Amazon.
    
    Sources disponibles (dans l'ordre de fiabilité):
    1. "bulk" - Bulk purchases (新品まとめ買い) - Le plus fiable
    2. "publisher" - From the Publisher (出版社より) - Assez fiable
    
    NOTE: Les carrousels "Frequently bought together" et "Customers also bought" ont été
    supprimés car ils retournaient trop de hors-sujets (mangas "similaires" sans rapport).
    
    Args:
        sources: Liste des sources à chercher. Si None, cherche ["bulk", "publisher"].
                 
    Returns:
        Dict avec les ASINs par source: {"bulk": [...], "publisher": [...]}
    """
    result = {"bulk": [], "publisher": []}
    
    if sources is None:
        sources = ["bulk", "publisher"]
    
    # Extraire l'ASIN si c'est une URL
    if 'amazon.co.jp' in url_ou_asin:
        match = re.search(r'/dp/([A-Z0-9]{10})', url_ou_asin)
        if match:
            asin = match.group(1)
        else:
            logger.warning(f"      ⚠️ Impossible d'extraire l'ASIN de: {url_ou_asin}")
            return result
    else:
        asin = url_ou_asin
    
    url_produit = f"https://www.amazon.co.jp/dp/{asin}"
    logger.info(f"      🔍 Recherche volumes liés depuis [{asin}]...")
    
    html = await get_html(session, url_produit)
    if not html:
        return result
    
    # DEBUG: Sauvegarder le HTML pour analyse
    if debug:
        with open(f'debug_page_{asin}.html', 'w', encoding='utf-8') as f:
            f.write(html)
        logger.info(f"      🔍 HTML sauvegardé: debug_page_{asin}.html")
    
    soup = BeautifulSoup(html, 'lxml')
    asins_trouves = set()
    asins_trouves.add(asin)  # Ajouter l'ASIN source pour ne pas le re-traiter
    
    # ========================================
    # SECTION 1: Bulk purchases (新品まとめ買い)
    # Le plus fiable - contient uniquement les volumes de la série
    # ========================================
    if "bulk" in sources:
        bulk_asins = []
        bulk_tomes = {}  # {asin: tome_num} — mapping tome depuis le label Bulk
        
        # Méthode 1: pbnx-desktop-box avec titre du manga
        bulk_boxes = soup.find_all("div", class_="pbnx-desktop-box")
        for box in bulk_boxes:
            titre_span = box.find("span", class_="a-size-base")
            if titre_span:
                titre_texte = titre_span.get_text(strip=True)
                nom_clean = strip_type_suffix(nom_manga); titre_cle = nom_clean[:8] if len(nom_clean) >= 8 else nom_clean
                if normaliser_titre(titre_cle) in normaliser_titre(titre_texte):
                    # Extraire chaque item du Bulk avec son label de tome
                    items = box.find_all("div", class_="pbnx-single-product")
                    if not items:
                        items = box.find_all("li")
                    for item in items:
                        link = item.find("a", href=True)
                        if not link:
                            continue
                        match = re.search(r'/dp/([A-Z0-9]{10})', link.get('href', ''))
                        if match and match.group(1) not in asins_trouves:
                            vol_asin = match.group(1)
                            bulk_asins.append(vol_asin)
                            asins_trouves.add(vol_asin)
                            # Extraire le label de tome (ex: "1巻", "Vol. 1")
                            label = item.get_text()
                            tome_match = re.search(r'(?:Vol\.?\s*|第?\s*)(\d+)\s*巻?|(\d+)\s*巻', label)
                            if tome_match:
                                tome_num = int(tome_match.group(1) or tome_match.group(2))
                                bulk_tomes[vol_asin] = tome_num
                    # Fallback : si items non trouvés, extraire les liens bruts (ancien code)
                    if not bulk_asins:
                        for link in box.find_all("a", href=True):
                            match = re.search(r'/dp/([A-Z0-9]{10})', link.get('href', ''))
                            if match and match.group(1) not in asins_trouves:
                                bulk_asins.append(match.group(1))
                                asins_trouves.add(match.group(1))
                    break
        
        # Méthode 2: Header "Bulk purchases" ou "新品まとめ買い"
        if not bulk_asins:
            bulk_header = soup.find(lambda tag: tag.name in ['h2', 'h3', 'div', 'span'] and 
                                    ('Bulk purchases' in tag.get_text() or '新品まとめ買い' in tag.get_text()))
            if bulk_header:
                parent = bulk_header.find_parent('div', class_=lambda x: x and 'a-section' in x) or bulk_header.find_parent('div')
                if parent:
                    # Essayer d'extraire avec labels de tome
                    items = parent.find_all("div", class_="pbnx-single-product")
                    if not items:
                        items = parent.find_all("li")
                    for item in items:
                        link = item.find("a", href=True)
                        if link:
                            match = re.search(r'/dp/([A-Z0-9]{10})', link.get('href', ''))
                            if match and match.group(1) not in asins_trouves:
                                vol_asin = match.group(1)
                                bulk_asins.append(vol_asin)
                                asins_trouves.add(vol_asin)
                                label = item.get_text()
                                tome_match = re.search(r'(?:Vol\.?\s*|第?\s*)(\d+)\s*巻?|(\d+)\s*巻', label)
                                if tome_match:
                                    tome_num = int(tome_match.group(1) or tome_match.group(2))
                                    bulk_tomes[vol_asin] = tome_num
                    # Fallback liens bruts
                    if not bulk_asins:
                        for link in parent.find_all("a", href=True):
                            match = re.search(r'/dp/([A-Z0-9]{10})', link.get('href', ''))
                            if match and match.group(1) not in asins_trouves:
                                bulk_asins.append(match.group(1))
                                asins_trouves.add(match.group(1))
        
        if bulk_asins:
            if bulk_tomes:
                logger.info(f"      📦 Bulk: {len(bulk_asins)} volume(s) trouvé(s) ({len(bulk_tomes)} tome(s) identifié(s))")
            else:
                logger.info(f"      📦 Bulk: {len(bulk_asins)} volume(s) trouvé(s)")
        
        result["bulk"] = bulk_asins
        result["bulk_tomes"] = bulk_tomes
    
    # Si le Bulk a trouvé des résultats, pas besoin des sources moins fiables
    if result["bulk"]:
        return result
    
    # ========================================
    # SECTION 2: From the Publisher / 出版社より
    # Fallback si Bulk absent — même éditeur
    # ========================================
    if "publisher" in sources:
        publisher_asins = []
        
        # Chercher la section "From the Publisher" ou "出版社より"
        publisher_header = soup.find(lambda tag: tag.name in ['h2', 'h3', 'div', 'span'] and 
                                      ('From the Publisher' in tag.get_text() or 
                                       '出版社より' in tag.get_text() or
                                       'Products related' in tag.get_text()))
        
        if publisher_header:
            parent = publisher_header.find_parent('div', class_='a-section') or publisher_header.find_parent('div')
            if parent:
                for link in parent.find_all("a", href=True):
                    match = re.search(r'/dp/([A-Z0-9]{10})', link.get('href', ''))
                    if match and match.group(1) not in asins_trouves:
                        publisher_asins.append(match.group(1))
                        asins_trouves.add(match.group(1))
        
        if publisher_asins:
            logger.info(f"      🏢 From Publisher: {len(publisher_asins)} volume(s) trouvé(s)")
        
        result["publisher"] = publisher_asins
    
    # ========================================
    # SECTION 3: Frequently bought together / よく一緒に購入されている商品
    # Désactivé par défaut car retourne des hors-sujets
    # Mais utile pour les nouvelles séries ajoutées manuellement
    # ========================================
    if "frequently_bought" in sources:
        frequently_asins = []
        
        # Chercher la section "Frequently bought together" ou "よく一緒に購入されている商品"
        fbt_header = soup.find(lambda tag: tag.name in ['h2', 'h3', 'div', 'span'] and 
                                  ('Frequently bought together' in tag.get_text() or 
                                   'よく一緒に購入されている商品' in tag.get_text()))
        
        if fbt_header:
            # Remonter au conteneur parent
            parent = fbt_header.find_parent('div', id='sims-fbt') or \
                     fbt_header.find_parent('div', class_='a-section') or \
                     fbt_header.find_parent('div')
            if parent:
                for link in parent.find_all("a", href=True):
                    match = re.search(r'/dp/([A-Z0-9]{10})', link.get('href', ''))
                    if match and match.group(1) not in asins_trouves:
                        frequently_asins.append(match.group(1))
                        asins_trouves.add(match.group(1))
        
        # Alternative: chercher par ID "sims-fbt"
        if not frequently_asins:
            fbt_section = soup.find('div', id='sims-fbt')
            if fbt_section:
                for link in fbt_section.find_all("a", href=True):
                    match = re.search(r'/dp/([A-Z0-9]{10})', link.get('href', ''))
                    if match and match.group(1) not in asins_trouves:
                        frequently_asins.append(match.group(1))
                        asins_trouves.add(match.group(1))
        
        if frequently_asins:
            logger.info(f"      🛒 Frequently bought: {len(frequently_asins)} volume(s) trouvé(s)")
        
        result["frequently_bought"] = frequently_asins
    
    # Log total
    total = sum(len(v) for v in result.values())
    if total > 0:
        logger.info(f"      ✅ Total: {total} volume(s) potentiel(s) détecté(s)")
    
    return result


def extraire_volumes_depuis_page_flat(result_dict: Dict[str, List[str]]) -> List[str]:
    """
    Convertit le résultat de extraire_volumes_depuis_page en liste plate d'URLs.
    Utilisé pour la compatibilité avec l'ancien code.
    """
    all_asins = []
    for source in ["bulk", "publisher", "frequently_bought"]:
        all_asins.extend(result_dict.get(source, []))
    
    urls = []
    for asin in all_asins:
        url = f"https://www.amazon.co.jp/dp/{asin}"
        if url not in urls:
            urls.append(url)
    
    return urls


async def extraire_infos_produit(html: str, debug: bool = False) -> Dict:
    """Extrait les infos du produit"""
    if not html:
        return {}
    
    soup = BeautifulSoup(html, 'lxml')
    infos = {}
    
    # DÉTECTION PAGE INVALIDE (captcha, rate limit, etc.)
    # Si pas de titre ET pas de détails produit, c'est probablement une page invalide
    titre = soup.find("span", {"id": "productTitle"})
    titre_texte = titre.get_text(strip=True) if titre else ""
    
    if not titre_texte:
        # Vérifier si c'est un captcha ou une page d'erreur
        if 'captcha' in html.lower() or 'robot' in html.lower():
            infos['_page_invalide'] = 'captcha'
        elif 'To discuss automated access' in html:
            infos['_page_invalide'] = 'rate_limit'
        elif len(html) < 5000:  # Page trop courte = probablement erreur
            infos['_page_invalide'] = 'page_courte'
        else:
            infos['_page_invalide'] = 'titre_non_trouve'
    
    infos['titre'] = titre_texte  # Sauvegarder le titre pour debug
    
    # DEBUG: Afficher le titre brut si demandé
    if debug and titre_texte:
        logger.info(f"      [DEBUG] Titre brut: '{titre_texte}'")
    
    # Détecter si c'est un lot/set
    if '巻セット' in titre_texte or ('セット' in titre_texte and ('1-' in titre_texte or '全巻' in titre_texte)):
        infos['est_lot'] = True
        # Essayer d'extraire la plage (ex: "1-3巻" ou "全5巻")
        match_plage = re.search(r'(\d+)-(\d+)巻', titre_texte)
        if match_plage:
            infos['lot_debut'] = int(match_plage.group(1))
            infos['lot_fin'] = int(match_plage.group(2))
        elif '全' in titre_texte:
            match_total = re.search(r'全(\d+)巻', titre_texte)
            if match_total:
                infos['lot_total'] = int(match_total.group(1))
    else:
        infos['est_lot'] = False
    
    # Date et Éditeur
    # Note : Amazon peut servir la page en japonais (発売日/出版社) ou en anglais
    # (Publication date/Publisher) selon les cookies de session. On cherche les deux.
    details = soup.find("div", {"id": "detailBulletsWrapper_feature_div"})
    if details:
        for li in details.find_all("li"):
            text = li.get_text()
            if "発売日" in text or "Publication date" in text:
                date_texte = text.split(":")[-1].strip()
                # Nettoyer les caractères Unicode invisibles (U+200E, U+200F, etc.)
                date_texte = re.sub(r'[\u200e\u200f\u200b\u202a\u202b\u202c\xa0]', '', date_texte).strip()
                infos['date'] = date_texte
            elif "出版社" in text or "Publisher" in text:
                editeur_texte = text.split(":")[-1].strip()
                # Nettoyer les caractères Unicode invisibles
                editeur_texte = re.sub(r'[\u200e\u200f\u200b\u202a\u202b\u202c\xa0]', '', editeur_texte).strip()
                # Nettoyer l'éditeur (enlever la date entre parenthèses)
                editeur_brut = re.split(r'\s*\(', editeur_texte)[0].strip()
                # Convertir en romaji
                infos['editeur'] = convertir_editeur_romaji(editeur_brut)
                if debug:
                    logger.info(f"      [DEBUG] Éditeur trouvé: {editeur_brut} → {infos['editeur']}")
    
    # Tome — appel à la fonction unique de parsing (utils.py)
    # Seulement si ce n'est pas un lot
    if not infos.get('est_lot') and titre:
        tome = extraire_numero_tome(titre_texte)
        if tome is not None:
            infos['tome'] = tome
            if debug:
                logger.info(f"      [DEBUG] Tome trouvé: {tome}")
        elif debug:
            logger.warning(f"      [DEBUG] ⚠️  AUCUN TOME trouvé dans: '{titre_texte}'")
    
    # Couverture
    image = soup.find("img", {"id": "landingImage"})
    if image and image.get('src'):
        infos['couverture_url'] = image['src']
    
    # FORMAT DU LIVRE (単行本, 文庫, ペーパーバック, Kindle版, etc.)
    # Méthode 1: Chercher dans le sélecteur de format (tmmSwatches)
    format_section = soup.find("div", {"id": "tmmSwatches"})
    if format_section:
        selected = format_section.find("span", class_="a-button-selected") or format_section.find("li", class_="selected")
        if selected:
            format_text = selected.get_text(strip=True)
            infos['format'] = format_text
            if debug:
                logger.info(f"      [DEBUG] Format trouvé (tmmSwatches): {format_text}")
    
    # Méthode 2: Chercher dans les détails du produit
    if 'format' not in infos or not infos['format']:
        detail_bullets = soup.find("div", {"id": "detailBullets_feature_div"})
        if detail_bullets:
            for li in detail_bullets.find_all("li"):
                text = li.get_text()
                # Chercher les mots-clés de format
                if any(f in text for f in ['単行本', '文庫', 'ペーパーバック', 'コミック', 'Paperback', 'Tankobon']):
                    infos['format'] = text.strip()[:50]
                    if debug:
                        logger.info(f"      [DEBUG] Format trouvé (détails): {infos['format']}")
                    break
    
    # Méthode 3: Chercher dans le titre lui-même (souvent entre parenthèses)
    if 'format' not in infos or not infos['format']:
        # Patterns courants: (角川スニーカー文庫), (富士見L文庫), (コミックス), etc.
        if '文庫' in titre_texte:
            infos['format'] = '文庫'
            if debug:
                logger.info(f"      [DEBUG] Format trouvé (titre): 文庫")
        elif 'コミック' in titre_texte:
            infos['format'] = 'コミック'
            if debug:
                logger.info(f"      [DEBUG] Format trouvé (titre): コミック")
    
    # Méthode 4: Chercher le breadcrumb ou la catégorie
    if 'format' not in infos or not infos['format']:
        breadcrumb = soup.find("div", {"id": "wayfinding-breadcrumbs_feature_div"})
        if breadcrumb:
            bc_text = breadcrumb.get_text()
            if '文庫' in bc_text:
                infos['format'] = '文庫'
            elif 'コミック' in bc_text or 'マンガ' in bc_text:
                infos['format'] = 'コミック'
            elif '単行本' in bc_text:
                infos['format'] = '単行本'
    
    return infos


def extraire_item_amazon(item):
    """Extrait titre, lien, URL et ASIN d'un élément résultat Amazon.
    Retourne (titre_txt, url_complete, asin) ou (None, None, None) si invalide."""
    titre_elem = item.select_one('.a-text-normal') or item.select_one('h2 a span')
    if not titre_elem:
        return None, None, None
    
    lien_elem = item.select_one('.a-link-normal') or item.select_one('h2 a')
    if not lien_elem or not lien_elem.get('href'):
        return None, None, None
    
    url_complete = f"https://www.amazon.co.jp{lien_elem['href']}"
    titre_txt = titre_elem.get_text()
    asin = extraire_asin(url_complete)
    
    # Aussi essayer data-asin du parent
    if (not asin or asin == '?') and item.get('data-asin'):
        asin = item['data-asin']
    
    return titre_txt, url_complete, asin


def extraire_infos_featured(item, titre_txt: str) -> Dict:
    """
    Extrait les métadonnées d'un résultat de recherche Amazon Featured.
    Retourne un dict avec les infos disponibles (titre, date, editeur, tome, format).
    Ces infos permettent de remplir le cache SANS fetcher la page /dp/.
    """
    infos = {'titre': titre_txt}
    
    # Extraire le numéro de tome depuis le titre
    tome = extraire_numero_tome(titre_txt)
    if tome is not None:
        infos['tome'] = tome
    
    # Extraire l'éditeur depuis le titre (entre parenthèses japonaises ou normales)
    editeur_titre = extraire_editeur(titre_txt)
    if editeur_titre:
        infos['editeur'] = convertir_editeur_romaji(editeur_titre)
    
    # Extraire la date de publication depuis les spans sous le titre
    # Pattern Amazon JP : "コミック – 2026/1/23" ou "文庫 – 2024/8/30"
    for span in item.select('span.a-text-normal, span.a-size-base, span.a-color-secondary'):
        text = span.get_text(strip=True)
        # Chercher un pattern date YYYY/M/D ou YYYY/MM/DD
        date_match = re.search(r'(\d{4}/\d{1,2}/\d{1,2})', text)
        if date_match:
            infos['date'] = date_match.group(1)
            # Le format est souvent juste avant la date : "コミック – 2026/1/23"
            format_match = re.search(r'(コミック|文庫|単行本|新書|大型本|ムック)', text)
            if format_match:
                infos['format'] = format_match.group(1)
            break
    
    # Aussi chercher la date dans les sous-divs (parfois dans une structure différente)
    if 'date' not in infos:
        for div in item.select('.a-row'):
            div_text = div.get_text(strip=True)
            date_match = re.search(r'(\d{4}/\d{1,2}/\d{1,2})', div_text)
            if date_match:
                infos['date'] = date_match.group(1)
                break
    
    # Normaliser la date au format YYYY/MM/DD
    if 'date' in infos:
        parts = infos['date'].split('/')
        if len(parts) == 3:
            infos['date'] = f"{parts[0]}/{int(parts[1]):02d}/{int(parts[2]):02d}"
    
    return infos


