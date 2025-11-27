# scraperQ-Acoustics.py
# PRODUKCIJA – v1.2.7 (18.11.2025.)
# POPRAVKE 26.11.2025.:
# 1. Savršeno parsiranje specifikacija (nested <ul> za "Inputs", strong tagovi, razdvajanje key/val)
# 2. Normalizacija kategorija (title case za sve kategorije)
# 3. Kompletan i tačan COLOR_MAP – uključuje Gloss, Satin, Holme Oak, English Walnut itd.

import cloudscraper
import json
from bs4 import BeautifulSoup
import os
import time
import random
import logging
import sys
from urllib.parse import urljoin
import re
import base64

# --- KONSTANTE ---
CODE_VERSION = "VA10.3"
LOG_FILE = "qacoustics_production.log"
OUTPUT_JSON = "qacoustics_products.json"
MAIN_URL = "https://www.qacoustics.com"
COLLECTIONS_URL = "https://www.qacoustics.com/collections"
TEST_MODE = False
MAX_PRODUCTS = 999

scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False},
    delay=15
)

# --- KOMPLETAN I TAČAN MAPIRANJE BOJA (27.11.2025.) ---
COLOR_MAP = {
    "Black": "#000000",
    "White": "#FFFFFF",
    "Satin Black": "#000000",
    "Satin White": "#FFFFFF",
    "Gloss Black": "#000000",
    "Gloss White": "#FFFFFF",
    "Gloss Silver": "#D0D0D0",      # tačan ton sa sajta
    "Carbon Black": "#000000",
    "Arctic White": "#FFFFFF",
    "Oak": "#D2B48C",
    "Holme Oak": "#2F1B12",         # 5000 serija
    "English Walnut": "#5C4033",    # najčešća "Walnut" varijanta
    "Walnut": "#5C4033",            # alias
    "Graphite Grey": "#333333",
    "Rosewood": "#65000B",
    "Santos Rosewood": "#65000B",
    "Silver": "#C0C0C0"
}

# --- MAPIRANJE KATEGORIJA (fallback za stendove i sl.) ---
CATEGORY_FALLBACK = {
    "concept-300-speaker-stand-pair": "Speaker Stands",
    "tensegrity-speaker-stand-pair-with-universal-adapter-plate": "Speaker Stands",
    "fs50-series-speaker-stand-pair": "Speaker Stands",
    "q-fs75-speaker-stand-pair": "Speaker Stands",
    "3030fsi-floor-stands": "Speaker Stands",
    "wb75-wall-bracket-single": "Wall Brackets"
}

# --- LOGOVANJE ---
def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    if logger.hasHandlers():
        logger.handlers.clear()
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    )
    file_handler = logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    logging.info("========== Q-ACOUSTICS SKREJPER ZAPOČET (v1.2.7 – FINALNA VERZIJA) ==========")

def shutdown_logging():
    logging.info("========== SKREJPER ZAVRŠEN =========")
    for handler in logging.getLogger().handlers[:]:
        handler.close()
        logging.getLogger().removeHandler(handler)

# --- UČITAVANJE POSTOJEĆIH PODATKA ---
def load_existing_data():
    existing_handles = set()
    data = []
    if os.path.exists(OUTPUT_JSON):
        try:
            with open(OUTPUT_JSON, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logging.info(f"UČITANO: {len(data)} postojećih")
            for p in data:
                handle = p.get("url_proizvoda", "").split('/products/')[-1].split('?')[0]
                if handle:
                    existing_handles.add(handle)
        except Exception as e:
            logging.error(f"GREŠKA UČITAVANJA: {e}")
    return data, existing_handles

# --- LOGO ---
def get_brand_logo():
    try:
        r = scraper.get(MAIN_URL, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        el = soup.select_one('img[alt="Q Acoustics"], a.logo img')
        if el and 'src' in el.attrs:
            return urljoin(MAIN_URL, el['src'])
    except Exception as e:
        logging.warning(f"Logo greška: {e}")
    return "https://www.qacoustics.com/cdn/shop/files/qalogo_small.png?v=1617783915"

# --- KATEGORIJE ---
def get_categories():
    logging.info("DOHVATANJE KATEGORIJA...")
    cats = {}
    try:
        r = scraper.get(COLLECTIONS_URL, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        for a in soup.select('a[href*="/collections/"]'):
            href = a.get('href')
            name = a.get_text(strip=True)
            if not href or not name:
                continue
            blocked = ['all', 'shop', 'new', 'sale', 'spares', '3000i', '3000c', '5000', 'q acoustics 3000c range', 'concept range', 'concept series']
            if any(block in name.lower() for block in blocked):
                continue
            if '/products/' in href:
                continue
            full = urljoin(COLLECTIONS_URL, href).split('?')[0]
            if full not in cats.values():
                name = name.title()
                cats[name] = full
        logging.info(f"KATEGORIJE PRONAĐENE: {len(cats)}")
    except Exception as e:
        logging.error(f"GREŠKA KATEGORIJE: {e}")
    return cats

# --- JSON API ---
def get_product_json(product_handle):
    url = f"{MAIN_URL}/products/{product_handle}.json"
    try:
        r = scraper.get(url, timeout=15)
        r.raise_for_status()
        return r.json().get('product', {})
    except Exception as e:
        logging.warning(f"JSON greška za {product_handle}: {e}")
        return {}

# --- PARSIRANJE HTML-a (SPECS + OPIS + KATEGORIJA) ---
def parse_html(soup, json_data, handle):
    opis = ""
    specs = {}

    # Opis
    meta_desc = soup.find('meta', {'name': 'description'})
    if meta_desc and meta_desc.get('content'):
        opis = meta_desc['content'].strip()

    if not opis or len(opis) < 100:
        overview = soup.select_one('section.tabsection[data-tab="OVERVIEW"], #product-description, .product__description')
        if overview:
            text_parts = [p.get_text(strip=True) for p in overview.find_all('p') if p.get_text(strip=True)]
            if text_parts:
                opis = ' '.join(text_parts)

    # SPECS – savršeno za M20 i sve ostale
    ul_specs = soup.select_one('section.tabsection[data-tab="SPECIFICATIONS"] ul, ul.specs, ul.product-specs, div.specs ul')
    if ul_specs:
        for li in ul_specs.find_all('li', recursive=False):
            # Key – najprije <strong>, pa direktan tekst
            strong = li.find('strong')
            if strong:
                key = strong.get_text(strip=True).rstrip(':')
            else:
                key_text = ''.join([t.strip() for t in li.find_all(text=True, recursive=False) if t.strip()])
                key = key_text.rstrip(':')

            if li.find('ul'):  # nested (Inputs)
                sub_vals = [sub_li.get_text(strip=True) for sub_li in li.find('ul').find_all('li')]
                val = '\n'.join(sub_vals)
            else:
                full_text = li.get_text(strip=True)
                if re.search(r'\d', full_text):
                    match = re.match(r'([^0-9]+?)\s*([0-9].*)', full_text)
                else:
                    match = re.match(r'([A-Za-z /]+?)\s*([A-Z].*)', full_text)
                if match:
                    key = match.group(1).strip()
                    val = match.group(2).strip()
                else:
                    key = full_text
                    val = ""

            if key:
                specs[key] = val

    # Fallback table
    if not specs:
        table = soup.select_one('table.specs-table, table')
        if table:
            for tr in table.find_all('tr'):
                cells = tr.find_all(['td', 'th'])
                if len(cells) >= 2:
                    key = cells[0].get_text(strip=True).rstrip(':')
                    val = cells[1].get_text(strip=True)
                    specs[key] = val

    # Kategorija
    category = "Nepoznato"
    breadcrumb = soup.select_one('nav.breadcrumb, .breadcrumbs')
    if breadcrumb:
        crumbs = breadcrumb.find_all('a')
        if crumbs:
            category = crumbs[-1].get_text(strip=True)
    if category == "Nepoznato" and handle in CATEGORY_FALLBACK:
        category = CATEGORY_FALLBACK[handle]
    category = category.title()

    return opis or "Opis nedostupan", specs, category

# --- SVG UZORAK BOJE ---
def get_color_data_uri(color_name):
    hex_color = COLOR_MAP.get(color_name.strip(), "#CCCCCC")
    svg = f'<svg width="100" height="100" xmlns="http://www.w3.org/2000/svg"><rect width="100" height="100" fill="{hex_color}"/></svg>'
    b64 = base64.b64encode(svg.encode('utf-8')).decode('utf-8')
    return f"data:image/svg+xml;base64,{b64}"

# --- JEDAN PROIZVOD ---
def scrape_product(product_url, logo, coll_name):
    handle = product_url.split('/products/')[-1].split('?')[0]
    logging.debug(f"\n=== OBRAĐUJEM: {handle} ===")
    json_data = get_product_json(handle)
    if not json_data:
        return None

    title = json_data.get('title', 'Nepoznato')
    variants = json_data.get('variants', [])
    price_str = variants[0].get('price', '0') if variants else '0'
    try:
        price = f"${float(price_str):,.2f}"
    except:
        price = f"${price_str}"
    sku = variants[0].get('sku', 'Nedostupan') if variants else 'Nedostupan'

    # Slike
    images = [urljoin("https://cdn.shopify.com", img.get('src', '').split('?')[0]) 
              for img in json_data.get('images', []) if img.get('src')]

    # HTML parsiranje
    try:
        r = scraper.get(product_url, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        opis, specs, precise_category = parse_html(soup, json_data, handle)
    except Exception as e:
        logging.warning(f"HTML greška za {handle}: {e}")
        opis, specs, precise_category = "Opis nedostupan", {}, coll_name

    # Boje
    colors = []
    for v in variants:
        opt1 = v.get('option1')
        if opt1 and opt1 != "Default Title":
            colors.append({"boja": opt1, "url_uzorka": get_color_data_uri(opt1)})

    category = precise_category if precise_category != "Nepoznato" else coll_name

    result = {
        "ime_proizvoda": title,
        "sku": sku,
        "brend_logo_url": logo,
        "cena": price,
        "opis": opis,
        "url_proizvoda": product_url,
        "url_slika": images,
        "specifikacije": specs,
        "kategorije": category,
        "dodatne_informacije": {
            "tagline": None,
            "dostupne_boje": colors
        }
    }

    logging.info(f"ZAVRŠENO: {title} | Spec: {len(specs)} | Boje: {len(colors)} | Kat: {category}")
    return result

# --- LINKOVI IZ KOLEKCIJE ---
def get_product_links_from_collection(coll_url, coll_name):
    links = []
    handle_coll = coll_url.split('/collections/')[-1].split('?')[0]
    json_url = f"{MAIN_URL}/collections/{handle_coll}/products.json"
    try:
        r = scraper.get(json_url, timeout=15)
        if r.status_code == 200:
            for p in r.json().get('products', []):
                links.append((f"{MAIN_URL}/products/{p['handle']}", coll_name))
            logging.info(f"Kolekcija '{coll_name}': {len(links)} proizvoda (JSON)")
            return links
    except: pass

    # fallback HTML
    try:
        r = scraper.get(coll_url, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        for a in soup.select('a[href*="/products/"]'):
            href = a.get('href')
            if href and '/products/' in href:
                full = urljoin(coll_url, href).split('?')[0]
                if full not in [l[0] for l in links]:
                    links.append((full, coll_name))
    except Exception as e:
        logging.error(f"Greška kolekcija '{coll_name}': {e}")
    return links

# --- MAIN ---
def main():
    setup_logging()
    try:
        existing_data, existing_handles = load_existing_data()
        logo = get_brand_logo()
        cats = get_categories()
        if not cats:
            logging.critical("NEMA KATEGORIJA – PREKID")
            return

        new_products = []
        scraped_count = 0

        for name, url in cats.items():
            if scraped_count >= MAX_PRODUCTS and not TEST_MODE:
                break
            logging.info(f"KATEGORIJA: '{name}' → {url}")
            time.sleep(random.uniform(1.0, 2.0))

            for product_url, coll_name in get_product_links_from_collection(url, name):
                if scraped_count >= MAX_PRODUCTS and not TEST_MODE:
                    break
                handle = product_url.split('/products/')[-1].split('?')[0]
                if handle in existing_handles:
                    continue
                time.sleep(random.uniform(0.5, 1.0))
                res = scrape_product(product_url, logo, coll_name)
                if res:
                    new_products.append(res)
                    existing_handles.add(handle)
                    scraped_count += 1

        final = existing_data + new_products
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(final, f, indent=4, ensure_ascii=False)

        logging.info(f"SAČUVANO: {len(final)} proizvoda u {OUTPUT_JSON}")

    except KeyboardInterrupt:
        logging.warning("PREKINUTO OD STRANE KORISNIKA")
    except Exception as e:
        logging.critical(f"KRITIČNA GREŠKA: {e}")
    finally:
        shutdown_logging()

if __name__ == "__main__":
    main()
