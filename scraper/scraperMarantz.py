# scraperMarantz_v1.0.1.py
# POPRAVKA: 1. Uklanjanje dupliranih proizvoda (po čistom URL-u)
# OSTALO: Identicno kao v1.0.0

import cloudscraper
import json
from bs4 import BeautifulSoup
from requests.exceptions import RequestException
import os
import time
import random
import re
import logging
import sys

# --- KONSTANTE ---
CODE_VERSION = "VA10.3"
LOG_FILE = "argon_style_marantz_v1.0.1.log"
OUTPUT_JSON = "marantz_products_v1.0.1.json"
MAIN_URL = "https://www.marantz.com/en-us"

scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
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

    logging.info("========== FINAL SKREJPER ZAPOČET ==========")
    logging.info(f"LOG: {LOG_FILE} | IZLAZ: {OUTPUT_JSON}")
    logging.info(f"GLAVNI URL: {MAIN_URL}")
    logging.info("===========================================")

def shutdown_logging():
    logging.info("========== SKREJPER ZAVRŠEN ==========")
    for handler in logging.getLogger().handlers[:]:
        handler.close()
        logging.getLogger().removeHandler(handler)

# --- UČITAVANJE POSTOJEĆIH (sa čišćenjem URL-a) ---
def load_existing_data():
    existing_clean_urls = set()  # ČISTI URL-ovi za proveru duplikata
    data = []

    if os.path.exists(OUTPUT_JSON):
        try:
            with open(OUTPUT_JSON, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logging.info(f"UČITANO: {len(data)} postojećih")
            for p in data:
                url = p.get("url_proizvoda", "")
                clean_url = url.split('?')[0]  # ČIST URL
                existing_clean_urls.add(clean_url)
        except Exception as e:
            logging.error(f"GREŠKA UČITAVANJA: {e}")
    else:
        logging.info("NEMA POSTOJEĆEG JSON-a – POČINJE OD NULE")

    return data, existing_clean_urls

# --- KATEGORIJE ---
def get_categories():
    logging.info("DOHVATANJE KATEGORIJA...")
    cats = {}
    invalid = {'Featured Products', 'All Products', 'Outlet', 'Discover', 'Learn more', 'Help Me Choose', 'Support'}

    try:
        r = scraper.get(MAIN_URL, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')

        for sel in [
            'header li.category-item a[href*="/category/"]',
            'header li.nav-item-product a[href*="/category/"]',
            'nav.main-navigation a[href*="/en-us/category/"]'
        ]:
            links = soup.select(sel)
            if links:
                for l in links:
                    name = l.get_text(strip=True)
                    href = l.get('href')
                    if name and href and name not in invalid:
                        full = "https://www.marantz.com" + href if not href.startswith('http') else href
                        if full not in cats.values():
                            cats[name] = full
                break

        logging.info(f"KATEGORIJE PRONAĐENE: {len(cats)}")
        return cats
    except Exception as e:
        logging.error(f"GREŠKA KATEGORIJE: {e}")
        return {}

# --- LOGO ---
def get_logo():
    try:
        r = scraper.get(MAIN_URL, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        el = soup.select_one('a.logo-home img, img[alt="Marantz"]')
        if el and 'src' in el.attrs:
            src = el['src']
            return "https://www.marantz.com" + src if not src.startswith('http') else src
    except:
        pass
    return None

# --- SKREJP DETALJA ---
def scrape_details(raw_url, logo):
    logging.info(f"SKREJPUJEM: {raw_url}")
    try:
        r = scraper.get(raw_url, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')

        name = "Nedostupan"
        for s in ['h1.product-hero__product-name', 'h1.product-name', 'h1.product-hero__title']:
            el = soup.select_one(s)
            if el:
                name = el.get_text(strip=True)
                break

        desc = "Opis nije dostupan"
        for s in ['div.short-description p', 'div.product-hero__product-description p']:
            el = soup.select_one(s)
            if el:
                desc = el.get_text(strip=True)
                break

        tagline = "Tagline nedostupan"
        for s in ['p.product-tagline', 'div.product-tagline']:
            el = soup.select_one(s)
            if el:
                tagline = el.get_text(strip=True)
                break

        price_el = soup.select_one('div.price .value')
        price = price_el.get_text(strip=True) if price_el else "Cena nije definisana"

        imgs = []
        for img in soup.select('div.product-hero__image-wrapper img, picture img.img-fluid, .product-gallery-item img'):
            src = img.get('src')
            if src:
                full = "https://www.marantz.com" + src if not src.startswith('http') else src
                if full not in imgs:
                    imgs.append(full)
        if not imgs:
            imgs = ["URL slike nedostupan"]

        specs = {}
        for row in soup.select('ul.specifications-list li, table.technical-specifications tbody tr'):
            k = row.select_one('span.name, td:nth-child(1)')
            v = row.select_one('span.value, td:nth-child(2)')
            if k and v:
                specs[k.get_text(strip=True)] = v.get_text(strip=True)

        # SKU (isto kao pre)
        m = re.search(r'/([^/]+)\.html', raw_url)
        sku = m.group(1) if m else "Nedostupan"

        # KATEGORIJA (isto kao pre)
        cat = "Kategorija nedostupna"
        bc = soup.select_one('ul.breadcrumb li:last-child a, nav[aria-label="breadcrumb"] li:last-child a')
        if bc:
            cat = bc.get_text(strip=True)
        else:
            m2 = re.search(r'/en-us/product/([^/]+)/', raw_url)
            if m2:
                cat = m2.group(1).replace('-', ' ').title()

        # BOJE (isto kao pre)
        colors = []
        for sw in soup.select('span.color-swatch'):
            n = sw.select_one('.swatch-value')
            i = sw.select_one('.color-value')
            if n and i:
                style = i.get('style', '')
                img_url = ''
                if 'background-image: url(' in style:
                    img_url = style.split('url(')[1].split(')')[0].strip("'\"")
                    if not img_url.startswith('http'):
                        img_url = "https://www.marantz.com" + img_url
                colors.append({"boja": n.get_text(strip=True), "url_uzorka": img_url})

        result = {
            "ime_proizvoda": name,
            "sku": sku,
            "brend_logo_url": logo,
            "cena": price,
            "opis": desc,
            "url_proizvoda": raw_url,  # PUN URL (sa bojom)
            "url_slika": imgs,
            "specifikacije": specs,
            "kategorije": cat,
            "dodatne_informacije": {
                "tagline": tagline,
                "dostupne_boje": colors
            }
        }

        logging.info(f"ZAVRŠENO: {name} | Cena: {price} | Boje: {len(colors)}")
        return result

    except Exception as e:
        logging.error(f"GREŠKA: {raw_url} | {e}")
        return None

# --- MAIN ---
def main():
    setup_logging()
    try:
        existing_data, existing_clean_urls = load_existing_data()
        logo = get_logo()
        cats = get_categories()
        if not cats:
            logging.critical("NEMA KATEGORIJA – PREKID")
            return

        new_products = []

        for name, url in cats.items():
            logging.info(f"KATEGORIJA: '{name}' → {url}")
            time.sleep(random.uniform(1, 2))

            try:
                r = scraper.get(url, timeout=15)
                r.raise_for_status()
                soup = BeautifulSoup(r.text, 'html.parser')

                links = []
                for sel in [
                    'a.product-tile-link',
                    'div.product-tile-wrapper a',
                    'div.product-tile a',
                    'a[href*="/product/"]'
                ]:
                    els = soup.select(sel)
                    if els:
                        for el in els:
                            h = el.get('href')
                            if h and '/product/' in h:
                                full = "https://www.marantz.com" + h if not h.startswith('http') else h
                                if full not in links:
                                    links.append(full)
                        break

                logging.info(f"PRONAĐENO: {len(links)} linkova")

                for raw_link in links:
                    clean_url = raw_link.split('?')[0]  # ČIST URL za proveru

                    # === POPRAVKA: PRESKOČI AKO VEĆ POSTOJI ===
                    if clean_url in existing_clean_urls:
                        logging.info(f"PRESKOČENO (već postoji): {clean_url}")
                        continue

                    time.sleep(random.uniform(0.5, 1.5))
                    res = scrape_details(raw_link, logo)

                    if res:
                        new_products.append(res)
                        existing_clean_urls.add(clean_url)  # Dodaj odmah da spreči duplikat

            except Exception as e:
                logging.error(f"GREŠKA KATEGORIJA '{name}': {e}")

        # ČUVANJE
        final = existing_data + new_products
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(final, f, indent=4, ensure_ascii=False)

        logging.info(f"UKUPNO SAČUVANO: {len(final)} | NOVO: {len(new_products)}")

    except KeyboardInterrupt:
        logging.warning("PREKINUTO")
    except Exception as e:
        logging.critical(f"KRITIČNA GREŠKA: {e}")
    finally:
        shutdown_logging()

if __name__ == "__main__":
    main()
