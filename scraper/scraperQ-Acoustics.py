# scraperQAcoustics_v1.2.1.py
# PRODUKCIJA – v1.2.1
# POPRAVKA: Sintaksa u re.sub() – dodato re. i zatvorena zagrada
# LOG_FILE = qacoustics_production.log
# OUTPUT_JSON = qacoustics_final.json

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

# --- KONSTANTE ---
CODE_VERSION = "VA10.3"
LOG_FILE = "qacoustics_production.log"
OUTPUT_JSON = "qacoustics_final.json"
MAIN_URL = "https://www.qacoustics.com"
COLLECTIONS_URL = "https://www.qacoustics.com/collections"
TEST_MODE = False
MAX_PRODUCTS = 999

scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False},
    delay=15
)

# --- KATEGORIJE PO TIPU ---
TYPE_MAPPING = {
    "Bookshelf": "Bookshelf Speakers",
    "Floorstanding": "Floorstanding Speakers",
    "Center": "Center Speakers",
    "Subwoofer": "Subwoofers",
    "Wall": "Wall Speakers",
    "Ceiling": "Ceiling Speakers",
    "Outdoor": "Outdoor Speakers"
}

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
    logging.info("========== Q-ACOUSTICS SKREJPER ZAPOČET (PRODUKCIJA v1.2.1) ==========")
    logging.info(f"LOG: {LOG_FILE} | IZLAZ: {OUTPUT_JSON}")
    logging.info(f"TEST MODE: {'UKLJUČENO' if TEST_MODE else 'ISKLJUČENO'} | MAX: {MAX_PRODUCTS}")
    logging.info(f"GLAVNI URL: {MAIN_URL}")
    logging.info("=================================================================")

def shutdown_logging():
    logging.info("========== SKREJPER ZAVRŠEN ==========")
    for handler in logging.getLogger().handlers[:]:
        handler.close()
        logging.getLogger().removeHandler(handler)

# --- UČITAVANJE PODATAKA ---
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
    else:
        logging.info("POČINJE OD NULE")
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
    return "https://www.qacoustics.com/cdn/shop/files/QAcoustics_Logo.png"

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

# --- HTML PARSIRANJE ---
def parse_html(soup, json_data):
    opis = ""
    specs = {}

    short_desc = soup.select_one('div.productsummary p')
    if short_desc:
        opis = short_desc.get_text(separator=' ', strip=True)

    if not opis or len(opis) < 100:
        overview = soup.select_one('section.tabsection[data-tab="OVERVIEW"]')
        if overview:
            text_parts = []
            for p in overview.find_all(['p', 'h3'], recursive=True):
                text = p.get_text(strip=True)
                if text and text not in ['OVERVIEW', 'Key Features']:
                    text_parts.append(text)
            if text_parts:
                opis = ' '.join(text_parts)

    ul_specs = soup.select_one('ul.specs')
    if ul_specs:
        for li in ul_specs.find_all('li'):
            text = li.get_text(strip=True)
            if '<b>' in str(li) or ':' in text:
                b = li.find('b')
                if b:
                    k = b.get_text(strip=True).rstrip(':')
                    v = li.get_text(separator=' ', strip=True).replace(k, '', 1).strip()
                    if k and v:
                        specs[k] = v

    return opis, specs

# --- JSON-LD FALLBACK ---
def parse_json_ld(soup):
    specs = {}
    try:
        script = soup.find('script', type='application/ld+json')
        if script and script.string:
            ld_data = json.loads(script.string)
            if isinstance(ld_data, dict):
                offers = ld_data.get('offers', {})
                if isinstance(offers, dict):
                    specs['MPN'] = offers.get('mpn', '')
                    specs['GTIN'] = offers.get('gtin13', offers.get('gtin', ''))
                specs['Brend'] = ld_data.get('brand', {}).get('name', '')
    except Exception as e:
        logging.warning(f"JSON-LD greška: {e}")
    return specs

# --- ODREĐIVANJE KATEGORIJE IZ NAZIVA ---
def get_category_from_title(title):
    title_upper = title.upper()
    for key, value in TYPE_MAPPING.items():
        if key.upper() in title_upper:
            return value
    match = re.search(r'(\d{3,4}[A-Za-z]?) SERIES', title_upper)
    if match:
        return f"Serija: {match.group(1)}"
    return "Uncategorized"

# --- SKREJP PROIZVODA ---
def scrape_product(product_url, logo, collection_name):
    handle = product_url.split('/products/')[-1].split('?')[0]
    json_data = get_product_json(handle)
    if not json_data:
        return None

    title = json_data.get('title', 'Nedostupan')
    category = get_category_from_title(title)

    try:
        r = scraper.get(product_url, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')

        opis, html_specs = parse_html(soup, json_data)
        ld_specs = parse_json_ld(soup)
        specs = {**ld_specs, **html_specs}

        if not opis:
            body_html = json_data.get('body_html', '')
            if body_html:
                opis = re.sub('<[^<]+?>', '', body_html).strip()  # ISPRAVLJENO

    except Exception as e:
        logging.warning(f"HTML greška: {e}")
        opis = re.sub('<[^<]+?>', '', json_data.get('body_html', '')).strip()
        specs = {}

    # CENA
    variants = json_data.get('variants', [])
    price = "Cena nije definisana"
    if variants:
        price_str = variants[0].get('price', '')
        try:
            price_float = float(price_str)
            price = f"${price_float:,.2f}"
        except:
            price = f"${price_str}"

    sku = variants[0].get('sku', 'Nedostupan') if variants else 'Nedostupan'
    available = any(v.get('available') for v in variants)

    # SLIKE
    images = []
    base_img_url = "https://www.qacoustics.com"
    for img in json_data.get('images', []):
        src = img.get('src', '')
        if src:
            src = src.replace('/cdn/', '/cdn/shop/')
            images.append(urljoin(base_img_url, src))

    # BOJE
    colors = []
    for i, v in enumerate(variants):
        opt1 = v.get('option1')
        if opt1 and opt1 != "Default Title":
            img_src = images[i] if i < len(images) else None
            colors.append({
                "boja": opt1,
                "url_uzorka": img_src
            })

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

    logging.info(f"ZAVRŠENO: {title} | Cena: {price} | Boje: {len(colors)} | Dostupno: {'Da' if available else 'Ne'} | Spec: {len(specs)} | Opis: {len(opis)} zn | Kategorija: {category}")
    return result

# --- LINKOVI IZ KOLEKCIJE ---
def get_product_links_from_collection(coll_url, coll_name):
    links = []
    handle = coll_url.split('/collections/')[-1].split('?')[0]
    json_url = f"{MAIN_URL}/collections/{handle}/products.json"
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
    logging.info(f"JSON nedostupan → HTML fallback za '{coll_name}'")
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
        logging.info(f"Kolekcija '{coll_name}': {len(links)} proizvoda (HTML)")
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
        updated_products = 0
        scraped_count = 0

        for name, url in cats.items():
            if scraped_count >= MAX_PRODUCTS and not TEST_MODE:
                logging.info(f"MAX DOSTIGNUT ({MAX_PRODUCTS}) – PREKID")
                break

            logging.info(f"KATEGORIJA: '{name}' → {url}")
            time.sleep(random.uniform(1.0, 2.0))

            links_with_cat = get_product_links_from_collection(url, name)
            for product_url, coll_name in links_with_cat:
                if scraped_count >= MAX_PRODUCTS and not TEST_MODE:
                    break

                handle = product_url.split('/products/')[-1].split('?')[0]

                if handle in existing_handles:
                    for p in existing_data:
                        if p.get("url_proizvoda", "").split('/products/')[-1].split('?')[0] == handle:
                            new_cat = get_category_from_title(p['ime_proizvoda'])
                            if p.get("kategorije") != new_cat:
                                p["kategorije"] = new_cat
                                updated_products += 1
                                logging.info(f"AŽURIRANO: {p['ime_proizvoda']} | Nova kategorija: {new_cat}")
                            break
                    continue

                time.sleep(random.uniform(0.5, 1.0))
                res = scrape_product(product_url, logo, coll_name)
                if res:
                    new_products.append(res)
                    existing_handles.add(handle)
                    scraped_count += 1
                    logging.info(f"SKREJPANO {scraped_count}")

        final = existing_data + new_products
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(final, f, indent=4, ensure_ascii=False)

        logging.info(f"SAČUVANO: {len(final)} | NOVO: {len(new_products)} | AŽURIRANO: {updated_products}")

    except KeyboardInterrupt:
        logging.warning("PREKINUTO OD STRANE KORISNIKA")
    except Exception as e:
        logging.critical(f"KRITIČNA GREŠKA: {e}")
    finally:
        shutdown_logging()

if __name__ == "__main__":
    main()
