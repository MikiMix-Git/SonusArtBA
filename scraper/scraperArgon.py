# scraperArgonFINAL_V13.py
# VERZIJA A10.2: BOJE IZ --swatch-background + KATEGORIJA IZ HTML-a
# POPRAVKA: Poboljšano prikupljanje dostupnih boja – thumbnail slike iz labela (kao na sajtu)
# Dodato čišćenje URL uzorka (uklanjanje &width parametara)
# 100% AUTOMATSKI, BEZ MAPE, BEZ LOGIKE

import cloudscraper
import json
from bs4 import BeautifulSoup
import os
import time
import random
import logging
import sys
from urllib.parse import urljoin
from datetime import datetime
import re

# --- KONSTANTE ---
CODE_VERSION = "A10.2"
LOG_FILE = "argon_final_v13.log"
OUTPUT_FILENAME = "argon_audio_final_v13.json"
MAIN_URL = "https://argonaudio.com/"
COLLECTIONS_URL = "https://argonaudio.com/collections/"

SKIP_COLLECTIONS = {"Spareparts", "testbfcm", "Unwrap The Gift Of Sound", "Black Days", "test", "sale", "featured", "christmas"}

scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
)

# --- LOGOVANJE ---
def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if logger.hasHandlers():
        logger.handlers.clear()
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [V{}] %(message)s'.format(CODE_VERSION), datefmt='%H:%M:%S')
    file_handler = logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    logging.info("="*80)
    logging.info(f"FINAL SKREJPER ZAPOČET: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info(f"VERZIJA: {CODE_VERSION} – POPRAVLJENE DOSTUPNE BOJE (thumbnail iz labela)")
    logging.info("="*80)
    return logger

def shutdown_logging(logger):
    logging.info("="*80)
    logging.info(f"SKREJPER ZAVRŠEN: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info("="*80)
    for h in logger.handlers[:]:
        h.close()
        logger.removeHandler(h)

# --- LOGO ---
def get_brand_logo_url():
    logging.info("Dohvatanje logotipa...")
    try:
        resp = scraper.get(MAIN_URL, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        img = soup.select_one('img[alt="Argon Audio"], .site-header__logo img')
        if img and img.get('src'):
            src = img['src'].split('?')[0]
            full = urljoin(MAIN_URL, src)
            if 'argon' in full.lower():
                logging.info(f"Logo: {full}")
                return full
    except Exception as e:
        logging.warning(f"Logo greška: {e}")
    fallback = "https://argonaudio.com/cdn/shop/files/Argon_Audio_TextOnly_NEG.png"
    logging.info(f"Logo fallback: {fallback}")
    return fallback

# --- KATEGORIJE ---
def get_categories():
    logging.info(f"Dohvatanje kategorija sa: {COLLECTIONS_URL}")
    categories = {}
    seen = set()
    try:
        resp = scraper.get(COLLECTIONS_URL, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        for a in soup.select('a[href*="/collections/"]'):
            href = a.get('href')
            if not href:
                continue
            # Izvuci ime iz URL sluga umesto teksta linka – sprečava promo poruke
            slug = href.split('/')[-1].split('?')[0]
            name = slug.replace('-', ' ').title()
            if not name or name.lower() in ['all', 'shop', 'new', 'sale', 'home', 'featured']:
                continue
            if any(skip.lower() in name.lower() for skip in SKIP_COLLECTIONS):
                continue
            full = urljoin(COLLECTIONS_URL, href)
            if full not in seen:
                seen.add(full)
                categories[name] = full
                logging.info(f"Kategorija: '{name}' → {full}")
    except Exception as e:
        logging.error(f"Greška: {e}")
    logging.info(f"UKUPNO: {len(categories)}")
    return categories

# --- PROIZVODI ---
def get_product_links_from_category(cat_url, cat_name):
    logging.info(f"Obrađujem: '{cat_name}'")
    links = []
    try:
        resp = scraper.get(cat_url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        for a in soup.select('a[href*="/products/"]'):
            href = a.get('href')
            if href:
                full = urljoin(cat_url, href)
                if '?variant=' in full:
                    continue
                if full not in links:
                    links.append(full)
        logging.info(f"Kategorija '{cat_name}': {len(links)} proizvoda")
    except Exception as e:
        logging.error(f"Greška: {e}")
    return links

# --- JSON API ---
def get_json_data(product_url):
    json_api_url = product_url.split('?')[0] + '.json'
    try:
        response = scraper.get(json_api_url, timeout=15)
        response.raise_for_status()
        return response.json().get('product')
    except Exception as e:
        logging.warning(f"JSON greška: {e}")
        return None

# --- SKREJPOVANJE ---
def scrape_product(product_url, logo_url, assigned_collection):
    logging.info(f"SKREJPUJEM: {product_url}")
    json_data = get_json_data(product_url)
    if not json_data:
        return None

    title = json_data.get('title')
    description = json_data.get('body_html') or ''
    sku = json_data.get('variants', [{}])[0].get('sku')

    # CENA
    price_str = json_data.get('variants', [{}])[0].get('price')
    cena = None
    if price_str:
        try:
            cena_float = float(price_str)
            cena = f"{cena_float:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")
        except: pass

    # SLIKE
    images = [img['src'].split('?')[0] for img in json_data.get('images', [])]

    # HTML
    colors = []
    specs = {}
    product_category = None

    try:
        resp = scraper.get(product_url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        # SPECIFIKACIJE
        for row in soup.select('.feature-chart__table-row'):
            k = row.select_one('.feature-chart__heading')
            v = row.select_one('.feature-chart__value')
            if k and v:
                key = k.get_text(strip=True)
                val = v.get_text(separator=' ', strip=True)
                if key and val:
                    specs[key] = val

        # BOJE – POBOLJŠANI PARSER (thumbnail iz img u labelu, kao na sajtu)
        seen_colors = set()
        for label in soup.select('label.thumbnail-swatch, label.color-swatch'):
            # Ime boje iz sr-only
            sr = label.select_one('.sr-only')
            color_name = sr.get_text(strip=True) if sr else None
            if not color_name or color_name in seen_colors:
                continue
            seen_colors.add(color_name)

            # Thumbnail slika iz img unutar labela
            img_tag = label.find('img')
            img_url = None
            if img_tag and img_tag.get('src'):
                raw_url = img_tag['src']
                if raw_url.startswith('//'):
                    raw_url = 'https:' + raw_url
                # Čišćenje parametara (kao &width=...)
                img_url = re.sub(r'&width=\d+', '', raw_url.split('&v=')[0])

            # Fallback na stari parser ako nema thumbnaila
            if not img_url:
                style = label.get('style', '')
                url_match = re.search(r'url\(([^)]+)\)', style)
                if url_match:
                    raw_url = url_match.group(1)
                    if raw_url.startswith('//'):
                        raw_url = 'https:' + raw_url
                    img_url = re.sub(r'&width=\d+', '', raw_url)

            colors.append({
                "boja": color_name,
                "url_uzorka": img_url or ""
            })

        # KATEGORIJA
        if assigned_collection:
            logging.debug(f"Kategorija za {product_url}: koristim assigned_collection '{assigned_collection}'")
            product_category = assigned_collection

    except Exception as e:
        logging.warning(f"HTML greška: {e}")

    # KONAČNA KATEGORIJA
    category = product_category or "Ostalo"

    logging.info(f"ZAVRŠENO: {title} | Cena: {cena} | Boje: {len(colors)} | Kategorija: {category}")

    return {
        "ime_proizvoda": title,
        "sku": sku,
        "brend_logo_url": logo_url,
        "cena": cena,
        "opis": description,
        "url_proizvoda": product_url,
        "url_slika": images,
        "specifikacije": specs,
        "kategorije": category,
        "dodatne_informacije": {
            "tagline": None,
            "dostupne_boje": colors
        }
    }

# --- MAIN ---
def main():
    logger = setup_logging()
    try:
        existing_urls = set()
        if os.path.exists(OUTPUT_FILENAME):
            with open(OUTPUT_FILENAME, 'r', encoding='utf-8') as f:
                data = json.load(f)
                existing_urls = {item.get('url_proizvoda') for item in data if item.get('url_proizvoda')}

        final_data = []
        logo = get_brand_logo_url()
        categories = get_categories()

        for cat_name, cat_url in categories.items():
            time.sleep(random.uniform(1.5, 3.0))
            product_links = get_product_links_from_category(cat_url, cat_name)
            for link in product_links:
                if link in existing_urls:
                    continue
                time.sleep(random.uniform(0.8, 1.8))
                result = scrape_product(link, logo, cat_name)
                if result:
                    final_data.append(result)
                    existing_urls.add(link)

        with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, indent=4, ensure_ascii=False)

        logging.info(f"UKUPNO NOVO: {len(final_data)} | SAČUVANO U: {OUTPUT_FILENAME}")

    except KeyboardInterrupt:
        logging.warning("PREKINUTO – čuvam...")
    except Exception as e:
        logging.critical(f"Greška: {e}")
    finally:
        shutdown_logging(logger)

if __name__ == "__main__":
    main()
