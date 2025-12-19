# scraperDenon_v1.1.3.py
# LOGOVANJE PO MODELU scraperArgon.py
# INKREMENTALNO + POPRAVKE SKU & KATEGORIJE
# POPRAVKA: Dodata logika za izbegavanje duplikata po clean URL-u (bez parametara)
# POPRAVKA: Normalizovani URL-ovi u existing_urls, incomplete_urls i processed_urls
# POPRAVKA: URL_proizvoda se čuva bez parametara
# POPRAVKA: Uklonjeno 'Wireless Speakers' iz invalid seta
# POPRAVKA: Ispravljen regex za SKU da radi bez .html
# POPRAVKA: Ispravljeni nazivi LOG_FILE i OUTPUT_JSON

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
LOG_FILE = "denon_v1.1.3.log"
OUTPUT_JSON = "denon_products_v1.1.3.json"
MAIN_URL = "https://www.denon.com/en-us"

scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
)

# --- LOGOVANJE (kao Argon) ---
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

# --- UČITAVANJE POSTOJEĆIH ---
def load_existing_data():
    existing_urls = set()
    incomplete_urls = set()
    data = []

    if os.path.exists(OUTPUT_JSON):
        try:
            with open(OUTPUT_JSON, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logging.info(f"UČITANO: {len(data)} postojećih")
            for p in data:
                url = p.get("url_proizvoda", "")
                clean_url = url.split('?')[0]
                if clean_url:
                    if is_complete(p):
                        existing_urls.add(clean_url)
                    else:
                        incomplete_urls.add(clean_url)
        except Exception as e:
            logging.error(f"GREŠKA UČITAVANJA: {e}")
    else:
        logging.info("NEMA POSTOJEĆEG JSON-a – POČINJE OD NULE")

    return data, existing_urls, incomplete_urls

def is_complete(p):
    req = ["ime_proizvoda", "sku", "cena", "url_proizvoda", "kategorije"]
    return all(p.get(k) and p[k] != "Nedostupan" for k in req) and len(p.get("url_slika", [])) > 0

# --- KATEGORIJE ---
def get_categories():
    logging.info("DOHVATANJE KATEGORIJA...")
    cats = {}
    invalid = {'Featured Products', 'All Products', 'Outlet', 'Discover', 'Learn more', 'Help Me Choose'}  # Uklonjeno 'Wireless Speakers'

    try:
        r = scraper.get(MAIN_URL, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')

        for sel in ['header li.category-item a[href*="/category/"]', 'header li.nav-item-product a[href*="/category/"]']:
            links = soup.select(sel)
            if links:
                for l in links:
                    name_el = l.select_one('.dropdown-item--title, .nav-link--category-name')
                    href = l.get('href')
                    if name_el and href:
                        name = name_el.get_text(strip=True)
                        if name in invalid:
                            continue
                        full = "https://www.denon.com" + href if not href.startswith('http') else href
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
        el = soup.select_one('a.logo-home img, img[alt="Denon"]')
        if el and 'src' in el.attrs:
            src = el['src']
            return "https://www.denon.com" + src if not src.startswith('http') else src
    except:
        pass
    return None

# --- SKREJP DETALJA ---
def scrape_details(url, logo):
    clean_url = url.split('?')[0]
    logging.info(f"SKREJPUJEM: {url}")
    try:
        r = scraper.get(url, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')

        name = "Nedostupan"
        for s in ['h1.product-hero__product-name', 'h1.product-name']:
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

        price = soup.select_one('div.price .value')
        price = price.get_text(strip=True) if price else "Cena nije definisana"

        imgs = []
        for img in soup.select('div.product-hero__image-wrapper img, picture img.img-fluid'):
            src = img.get('src')
            if src:
                full = "https://www.denon.com" + src if not src.startswith('http') else src
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

        # SKU - POPRAVLJENO: Uzima poslednji segment URL-a
        m = re.search(r'/([^/]+)$', clean_url)
        sku = m.group(1) if m else "Nedostupan"

        # KATEGORIJA
        cat = "Kategorija nedostupna"
        bc = soup.select_one('ul.breadcrumb li:last-child a, nav[aria-label="breadcrumb"] li:last-child a')
        if bc:
            cat = bc.get_text(strip=True)
        else:
            m2 = re.search(r'/en-us/product/([^/]+)/', clean_url)
            if m2:
                cat = m2.group(1).replace('-', ' ').title()

        # BOJE
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
                        img_url = "https://www.denon.com" + img_url
                colors.append({"boja": n.get_text(strip=True), "url_uzorka": img_url})

        result = {
            "ime_proizvoda": name,
            "sku": sku,
            "brend_logo_url": logo,
            "cena": price,
            "opis": desc,
            "url_proizvoda": clean_url,
            "url_slika": imgs,
            "specifikacije": specs,
            "kategorije": cat,
            "dodatne_informacije": {
                "tagline": tagline,
                "dostupne_boje": colors
            }
        }

        if is_complete(result):
            logging.info(f"ZAVRŠENO: {name} | Cena: {price} | Boje: {len(colors)}")
        else:
            logging.warning(f"NEPOTPUN: {name}")

        return result

    except Exception as e:
        logging.error(f"GREŠKA: {url} | {e}")
        return None

# --- MAIN ---
def main():
    setup_logging()
    try:
        existing_data, done_urls, retry_urls = load_existing_data()
        logo = get_logo()
        cats = get_categories()
        if not cats:
            logging.critical("NEMA KATEGORIJA – PREKID")
            return

        new_products = []
        new_count = 0
        updated_count = 0
        processed_urls = set()

        for name, url in cats.items():
            logging.info(f"KATEGORIJA: '{name}' → {url}")
            time.sleep(random.uniform(1, 2))

            try:
                r = scraper.get(url, timeout=15)
                r.raise_for_status()
                soup = BeautifulSoup(r.text, 'html.parser')

                links = []
                for sel in ['a.product-tile-link', 'div.product-tile-wrapper a']:
                    els = soup.select(sel)
                    if els:
                        for el in els:
                            h = el.get('href')
                            if h and 'product' in h:
                                full = "https://www.denon.com" + h if not h.startswith('http') else h
                                links.append(full)
                        break

                unique = list(set(links))
                logging.info(f"PRONAĐENO: {len(unique)} linkova")

                for link in unique:
                    clean_link = link.split('?')[0]
                    if clean_link in processed_urls:
                        logging.info(f"PRESKOČENO (već procesuirano u ovom run-u): {clean_link}")
                        continue
                    if clean_link in done_urls and clean_link not in retry_urls:
                        logging.info(f"PRESKOČENO (već kompletan): {clean_link}")
                        continue
                    if clean_link in retry_urls:
                        logging.info(f"PONOVO: {link}")

                    time.sleep(random.uniform(0.5, 1.5))
                    res = scrape_details(link, logo)

                    if res:
                        processed_urls.add(clean_link)
                        if is_complete(res):
                            if clean_link in retry_urls:
                                updated_count += 1
                                logging.info(f"AŽURIRANO: {res['ime_proizvoda']}")
                            else:
                                new_count += 1
                                logging.info(f"NOVO: {res['ime_proizvoda']}")
                        else:
                            logging.warning(f"NEPOTPUN: {res['ime_proizvoda']}")
                        new_products.append(res)

            except Exception as e:
                logging.error(f"GREŠKA KATEGORIJA '{name}': {e}")

        # ČUVANJE
        final = existing_data + new_products
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(final, f, indent=4, ensure_ascii=False)

        logging.info(f"UKUPNO SAČUVANO: {len(final)} | NOVO: {new_count} | AŽURIRANO: {updated_count}")

    except KeyboardInterrupt:
        logging.warning("PREKINUTO")
    except Exception as e:
        logging.critical(f"KRITIČNA GREŠKA: {e}")
    finally:
        shutdown_logging()

if __name__ == "__main__":
    main()
