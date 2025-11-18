# scraperQAcoustics_v1.2.7.py
# PRODUKCIJA – v1.2.7 (18.11.2025.)
# IZMENE U ODNOSU NA v1.2.6:
# 1. Promenjen naziv izlaznog JSON fajla u qacoustics_products.json (po zahtevu)
# 2. Sve ostale funkcionalnosti identične v1.2.6 (specifikacije, debug logovi, kategorije)

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
OUTPUT_JSON = "qacoustics_products.json"  # ← PROMENJENO
MAIN_URL = "https://www.qacoustics.com"
COLLECTIONS_URL = "https://www.qacoustics.com/collections"
TEST_MODE = False
MAX_PRODUCTS = 999

scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False},
    delay=15
)

# --- MAPIRANJE BOJA ---
COLOR_MAP = {
    "Black": "#000000", "White": "#FFFFFF", "Satin Black": "#000000", "Satin White": "#FFFFFF",
    "Oak": "#D2B48C", "Holme Oak": "#D2B48C", "Rosewood": "#65000B", "Santos Rosewood": "#65000B",
    "Silver": "#CCCCCC"
}

# --- MAPIRANJE KATEGORIJA ---
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
    
    logging.info("========== Q-ACOUSTICS SKREJPER ZAPOČET (v1.2.7 – PROMENJEN NAZIV IZLAZNOG FAJLA) ==========")

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
            if not href or not name or name.lower() in ['all', 'shop', 'new', 'sale', 'spares']:
                continue
            if '/products/' in href:
                continue
            full = urljoin(COLLECTIONS_URL, href).split('?')[0]
            if full not in cats.values():
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

# --- EKSTREMNO DETALJNO PARSIRANJE HTML-a ---
def parse_html(soup, json_data, handle):
    opis = ""
    specs = {}

    # Opis – isti kao ranije
    meta_desc = soup.find('meta', {'name': 'description'})
    if meta_desc and meta_desc.get('content'):
        opis = meta_desc['content'].strip()
        logging.debug(f"[OPIS] Meta description: {opis[:150]}...")

    short_desc = soup.select_one('div.productsummary p, .product-short-description p')
    if short_desc and not opis:
        opis = short_desc.get_text(separator=' ', strip=True)
        logging.debug(f"[OPIS] Short description: {opis[:150]}...")

    if not opis or len(opis) < 100:
        overview = soup.select_one('section.tabsection[data-tab="OVERVIEW"], #product-description, .product__description')
        if overview:
            text_parts = [p.get_text(strip=True) for p in overview.find_all('p') if p.get_text(strip=True)]
            if text_parts:
                opis = ' '.join(text_parts)
                logging.debug(f"[OPIS] Detaljan opis iz tabova: {opis[:150]}...")

    # === SPECIJALNI PARSIRANJE SPECIFIKACIJA ===
    logging.debug(f"[SPECS] Počinjem parsiranje specifikacija za {handle}")

    # 1. PRIORITET: <ul><li>Key: Value</li></ul> ili <li>Key Value</li>
    ul_specs = soup.select_one('ul.specs, ul.product-specs, div.specs ul')
    if ul_specs:
        logging.debug(f"[SPECS] Aktiviran parser <ul><li> – pronađeno {len(ul_specs.find_all('li'))} stavki")
        for li in ul_specs.find_all('li'):
            text = li.get_text(strip=True)
            if ':' in text:
                key, val = text.split(':', 1)
                key = key.strip()
                val = val.strip()
                specs[key] = val
                logging.debug(f"   └─ <ul> SPEC: {key} → {val}")
            elif text:
                parts = text.split(None, 1)
                if len(parts) >= 2:
                    key = parts[0] + " " + " ".join(parts[1].split()[:1]) if len(parts) > 2 else parts[0]
                    val = " ".join(parts[1:] if len(parts) > 2 else parts[1:])
                    specs[key.strip()] = val.strip()
                    logging.debug(f"   └─ <ul> SPEC (bez :): {key.strip()} → {val.strip()}")

    # 2. FALLBACK: <table> redovi
    if not specs:
        table = soup.select_one('table.specs-table, table')
        if table:
            logging.debug(f"[SPECS] Aktiviran parser <table> – pronađeno redova: {len(table.find_all('tr'))}")
            for tr in table.find_all('tr'):
                cells = tr.find_all(['td', 'th'])
                if len(cells) >= 2:
                    key = cells[0].get_text(strip=True).rstrip(':')
                    val = cells[1].get_text(strip=True)
                    specs[key] = val
                    logging.debug(f"   └─ <table> SPEC: {key} → {val}")

    logging.debug(f"[SPECS] UKUPNO pronađeno specifikacija: {len(specs)}")

    # Kategorija – isti fallback kao ranije
    category = "Nepoznato"
    breadcrumb = soup.select_one('nav.breadcrumb, .breadcrumbs')
    if breadcrumb:
        crumbs = breadcrumb.find_all('a')
        if crumbs:
            category = crumbs[-1].get_text(strip=True)
            logging.debug(f"[KATEGORIJA] Iz breadcrumb-a: {category}")
    if category == "Nepoznato" and handle in CATEGORY_FALLBACK:
        category = CATEGORY_FALLBACK[handle]
        logging.debug(f"[KATEGORIJA] Fallback iz mape: {category}")

    return opis or "Opis nedostupan", specs, category

# --- DATA URI BOJE ---
def get_color_data_uri(color_name):
    hex_color = COLOR_MAP.get(color_name, "#CCCCCC")
    svg = f'<svg width="100" height="100" xmlns="http://www.w3.org/2000/svg"><rect width="100" height="100" fill="{hex_color}"/></svg>'
    b64 = base64.b64encode(svg.encode('utf-8')).decode('utf-8')
    return f"data:image/svg+xml;base64,{b64}"

# --- GLAVNA FUNKCIJA ZA JEDAN PROIZVOD ---
def scrape_product(product_url, logo, coll_name):
    handle = product_url.split('/products/')[-1].split('?')[0]
    logging.debug(f"\n=== POČINJEM OBRAĐIVATI: {handle} ===")
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
    images = []
    for img in json_data.get('images', []):
        src = img.get('src', '').split('?')[0]
        if src:
            full = urljoin("https://cdn.shopify.com", src)
            images.append(full)
    logging.debug(f"[SLIKE] Pronađeno {len(images)} slika")

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
            logging.debug(f"[BOJA] Dodata: {opt1}")

    category = precise_category if precise_category != "Nepoznato" else coll_name

    logging.debug(f"[ZAVRŠETAK] Specs ukupno: {len(specs)} | Boje: {len(colors)} | Kategorija: {category}")

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
            data = r.json()
            for p in data.get('products', []):
                url = f"{MAIN_URL}/products/{p['handle']}"
                links.append((url, coll_name))
            logging.info(f"Kolekcija '{coll_name}': {len(links)} proizvoda (JSON)")
            return links
    except:
        pass

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

            links_with_cat = get_product_links_from_collection(url, name)
            for product_url, coll_name in links_with_cat:
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
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:  # ← SADA qacoustics_products.json
            json.dump(final, f, indent=4, ensure_ascii=False)

        logging.info(f"SAČUVANO: {len(final)} proizvoda u fajl: {OUTPUT_JSON}")

    except KeyboardInterrupt:
        logging.warning("PREKINUTO OD STRANE KORISNIKA")
    except Exception as e:
        logging.critical(f"KRITIČNA GREŠKA: {e}")
    finally:
        shutdown_logging()

if __name__ == "__main__":
    main()
