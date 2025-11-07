# scraperDynaudio_v1.2.8.py
# POPRAVKA: Uklonjeno ograničenje na top 5 slika – SVE slike se čuvaju
# BAZA: v1.2.7 – sve slike, sortirane po veličini

import cloudscraper
import json
from bs4 import BeautifulSoup
import os
import time
import random
import logging
import sys
import re
import requests
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

# --- KONSTANTE ---
CODE_VERSION = "VA10.3"
LOG_FILE = "argon_style_dynaudio_v1.2.8.log"
OUTPUT_JSON = "dynaudio_products_v1.2.8.json"
MAIN_URL = "https://dynaudio.com"
SITEMAP_URL = "https://dynaudio.com/sitemap.xml"
REAL_LOGO = "https://dynaudio.com/hubfs/logo.svg"

scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False},
    delay=15
)

# --- LOGOVANJE ---
def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if logger.hasHandlers():
        logger.handlers.clear()
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [{}] %(message)s'.format(CODE_VERSION),
        datefmt='%H:%M:%S'
    )
    file_handler = logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    logging.info("========== SKREJPER ZAPOČET (SVE SLIKE – BEZ OGRANIČENJA) ==========")
    logging.info(f"LOG: {LOG_FILE} | IZLAZ: {OUTPUT_JSON}")
    logging.info("=================================================================")

def shutdown_logging():
    logging.info("========== SKREJPER ZAVRŠEN ==========")
    for handler in logging.getLogger().handlers[:]:
        handler.close()
        logging.getLogger().removeHandler(handler)

# --- UČITAVANJE ---
def load_existing_data():
    existing_urls = set()
    data = []
    if os.path.exists(OUTPUT_JSON):
        try:
            with open(OUTPUT_JSON, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logging.info(f"UČITANO: {len(data)} postojećih")
            for p in data:
                url = p.get("url_proizvoda")
                if url:
                    existing_urls.add(url)
        except Exception as e:
            logging.error(f"GREŠKA UČITAVANJA: {e}")
    else:
        logging.info("POČINJE OD NULE")
    return data, existing_urls

# --- SITEMAP ---
def discover_products():
    product_urls = set()
    try:
        logging.info(f"DOHVATAM SITEMAP: {SITEMAP_URL}")
        r = requests.get(SITEMAP_URL, timeout=20)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        for url in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc'):
            loc = url.text.strip()
            if '/home-audio/' in loc and loc.count('/') >= 5 and 'blog' not in loc and 'news' not in loc:
                clean_loc = loc.split('?')[0]
                product_urls.add(clean_loc)
        logging.info(f"PRONAĐENO IZ SITEMAP: {len(product_urls)} PROIZVODA")
    except Exception as e:
        logging.error(f"GREŠKA PRI SITEMAP-U: {e}")
    return list(product_urls)

# --- POMOĆNE FUNKCIJE ---
def get_largest_srcset(srcset):
    urls = []
    if not srcset:
        return None
    for part in srcset.split(','):
        if 'http' in part:
            url = part.strip().split(' ')[0]
            urls.append(url)
    return urls[-1] if urls else None

def extract_bg_image(style):
    if not style:
        return ""
    match = re.search(r'url\((["\']?)(.*?)\1\)', style)
    if match:
        url = match.group(2)
        return url if url.startswith('http') else "https://dynaudio.com" + url
    return ""

# --- SKREJP PROIZVODA ---
def scrape_product(url, logo):
    clean_url = url.split('?')[0]
    logging.info(f"SKREJPUJEM: {clean_url}")
    try:
        r = scraper.get(url, timeout=25)
        if r.status_code != 200:
            logging.warning(f"404: {clean_url}")
            return None
        soup = BeautifulSoup(r.text, 'html.parser')

        # IME
        title = soup.title.get_text(strip=True) if soup.title else "Nedostupan"
        name = title.split('|')[0].strip() if '|' in title else title

        # OPIS
        desc_meta = soup.find('meta', {'name': 'description'})
        desc = desc_meta['content'] if desc_meta and 'content' in desc_meta.attrs else "Opis nije dostupan"

        # SLIKE – PRIORITET: SLAJDER, ZATIM SPECIFICATIONS-MODULE
        candidates = []
        # 1. Iz slajdera
        for li in soup.select('li.product-slider__dnd_area_module_1'):
            img = li.find('img')
            if img:
                srcset = img.get('data-srcset') or img.get('srcset')
                if srcset:
                    largest = get_largest_srcset(srcset)
                    if largest:
                        candidates.append(largest)
                src = img.get('src')
                if src and src.startswith('http'):
                    candidates.append(src)

        # 2. Fallback za Black Edition
        if 'black-edition' in clean_url.lower() and not candidates:
            for img in soup.select('div.specifications-module img'):
                src = img.get('src')
                if src and src.startswith('http'):
                    candidates.append(src)

        # SVE SLIKE – SORTIRANE PO VELIČINI (najveće prvo), BEZ OGRANIČENJA
        imgs = sorted(
            candidates,
            key=lambda x: int(re.search(r'width=(\d+)', x).group(1)) if 'width=' in x else 0,
            reverse=True
        )  # BEZ [:5] – SVE SLIKE

        if not imgs:
            logging.warning(f"NEMA SLIKA: {name}")
        else:
            logging.info(f"PRONAĐENO SLIKA: {len(imgs)}")

        # BOJE
        colors = []
        color_div = soup.select_one('div.color-pickers')
        if color_div:
            for a in color_div.select('a.color-selected'):
                title = a.get('title')
                div = a.find('div', class_='colorpicker')
                if title and div:
                    style = div.get('style', '')
                    url_uzorka = extract_bg_image(style)
                    if title not in [c['boja'] for c in colors]:
                        colors.append({"boja": title, "url_uzorka": url_uzorka})

        # SPECIFIKACIJE
        specs = {}
        specs_ul = soup.select_one('ul.product-specs-table')
        if specs_ul:
            for li in specs_ul.find_all('li', class_=re.compile('col-spec_')):
                label = li.find('span', class_='spec-label')
                value = li.find('span', 'spec-value')
                if label and value:
                    k = label.get_text(strip=True).rstrip(':')
                    if 'inches' in k.lower() or 'Packaged' in k or 'incl.' in k.lower():
                        continue
                    v = value.get_text(strip=True)
                    specs[k] = v

        # KATEGORIJA
        path = urlparse(clean_url).path
        path_parts = [p for p in path.split('/') if p and p not in ['home-audio']]
        kategorija_raw = path_parts[0] if path_parts else "Home Audio"
        kategorija = kategorija_raw.replace('-', ' ').replace('xd', ' XD').title()

        result = {
            "ime_proizvoda": name,
            "sku": "Nedostupan",
            "brend_logo_url": logo,
            "cena": "Cena nije definisana",
            "opis": desc,
            "url_proizvoda": clean_url,
            "url_slika": imgs,  # SVE SLIKE – SORTIRANE, BEZ OGRANIČENJA
            "specifikacije": specs,
            "kategorije": kategorija,
            "dodatne_informacije": {
                "tagline": "Tagline nedostupan",
                "dostupne_boje": colors
            }
        }

        logging.info(f"ZAVRŠENO: {name} | Slike: {len(imgs)} | Boje: {len(colors)}")
        return result

    except Exception as e:
        logging.error(f"GREŠKA: {clean_url} | {e}")
        return None

# --- MAIN ---
def main():
    setup_logging()
    try:
        existing_data, existing_urls = load_existing_data()
        logo = REAL_LOGO
        product_urls = discover_products()
        new_products = []

        for url in product_urls:
            clean_url = url.split('?')[0]
            if clean_url in existing_urls:
                logging.info(f"PRESKOČENO: {clean_url}")
                continue
            time.sleep(random.uniform(2, 4))
            res = scrape_product(url, logo)
            if res:
                new_products.append(res)
                existing_urls.add(clean_url)

        final = existing_data + new_products
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(final, f, indent=4, ensure_ascii=False)

        logging.info(f"SAČUVANO: {len(final)} | NOVO: {len(new_products)}")

    except KeyboardInterrupt:
        logging.warning("PREKINUTO")
    except Exception as e:
        logging.critical(f"KRITIČNA GREŠKA: {e}")
    finally:
        shutdown_logging()

if __name__ == "__main__":
    main()
