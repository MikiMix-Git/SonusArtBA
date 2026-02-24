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
CODE_VERSION = "A10.8"
LOG_FILE = f"argon_final_{CODE_VERSION}.txt"
OUTPUT_FILENAME = f"argon_audio_final_{CODE_VERSION}.json"
MAIN_URL = "https://argonaudio.com/"

COLLECTION_JSON_ENDPOINTS_RAW = """
Svi proizvodi (glavni endpoint): https://argonaudio.com/products.json?limit=250
All kolekcija: https://argonaudio.com/collections/all/products.json

Active Speakers: https://argonaudio.com/collections/active-speakers/products.json
Fenris: https://argonaudio.com/collections/fenris/products.json
Forte: https://argonaudio.com/collections/forte/products.json
Forte Wifi: https://argonaudio.com/collections/forte-wifi/products.json
Passive Speakers: https://argonaudio.com/collections/passive-speakers/products.json
Subwoofers: https://argonaudio.com/collections/subwoofers/products.json
Amplifiers: https://argonaudio.com/collections/amplifiers/products.json
Music Streamers: https://argonaudio.com/collections/music-streamers/products.json
Turntables: https://argonaudio.com/collections/turntables/products.json
Headphones: https://argonaudio.com/collections/headphones/products.json
Cables: https://argonaudio.com/collections/cables/products.json
Accessories/Speaker Cable: https://argonaudio.com/collections/accessories/Speaker-Cable/products.json
Speaker Accessories: https://argonaudio.com/collections/speaker-accessories/products.json
Speaker Stands: https://argonaudio.com/collections/speaker-stands/products.json
Speakers Brackets: https://argonaudio.com/collections/speakers-brackets/products.json
Turntable Accessories: https://argonaudio.com/collections/turntable-accessories/products.json
Christmas: https://argonaudio.com/collections/christmas/products.json
Amplifiers Streaming: https://argonaudio.com/collections/amplifiers-streaming/products.json
Black Days: https://argonaudio.com/collections/black-days/products.json
Dts Play Fi: https://argonaudio.com/collections/dts-play-fi/products.json
Accessories: https://argonaudio.com/collections/accessories/products.json
Frontpage: https://argonaudio.com/collections/frontpage/products.json
Systems: https://argonaudio.com/collections/systems/products.json
Radio: https://argonaudio.com/collections/radio/products.json
Spareparts: https://argonaudio.com/collections/spareparts/products.json
Speakers: https://argonaudio.com/collections/speakers/products.json
"""

SKIP_KEYWORDS = {
    "black days", "christmas", "frontpage", "spareparts", "test",
    "all kolekcija", "svi proizvodi (glavni endpoint)"
}

CATEGORY_MAP = {
    "cable": "Cables",
    "cables": "Cables",
    "speaker cable": "Cables",
    "subwoofer cable": "Cables",
    "usb-c": "Cables",
    "connect kit": "Cables",
    "fenris / sa subwoofer connect kit": "Cables",
    "forte subwoofer connect kit": "Cables",
    "speakers brackets": "Speakers Brackets",
    "speaker brackets": "Speakers Brackets",
    "speaker stands": "Speaker Stands",
    "speaker accessories": "Speaker Accessories",
    "turntable accessories": "Turntable Accessories",
    "on-wall speakers": "On-Wall Speakers",
    "stereo amplifier": "Amplifiers",
    "music streamer": "Music Streamers",
    "turntable": "Turntables",
    "wireless headphone": "Headphones",
    "riaa": "Amplifiers",
    "wireless adapter": "Accessories",
}

scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
)

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [V{}] %(message)s'.format(CODE_VERSION),
        datefmt='%H:%M:%S'
    )

    file_handler = logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    logging.info("=" * 80)
    logging.info(f"FINAL SKREJPER ZAPOČET: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info(f"VERZIJA: {CODE_VERSION} - Korišćenje products.json endpointa za kategorije")
    logging.info("=" * 80)
    return logger

def shutdown_logging(logger):
    logging.info("=" * 80)
    logging.info(f"SKREJPER ZAVRŠEN: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info("=" * 80)
    for h in logger.handlers[:]:
        h.close()
        logger.removeHandler(h)

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

def normalize_category(cat_name):
    if not cat_name:
        logging.debug("normalize_category: prazna kategorija, vraćam 'Ostalo'")
        return "Ostalo"
    cat_key = cat_name.strip().lower()
    normalized = CATEGORY_MAP.get(cat_key, cat_name)
    if normalized == cat_name:
        logging.debug(f"normalize_category: nema mapiranja za '{cat_name}', vraćam original")
    else:
        logging.debug(f"normalize_category: '{cat_name}' mapirano na '{normalized}'")
    return normalized

def get_categories():
    logging.info("Parsiranje products.json endpointa za kategorije...")
    categories = {}
    seen_urls = set()

    for line in COLLECTION_JSON_ENDPOINTS_RAW.strip().split('\n'):
        line = line.strip()
        if not line or ':' not in line:
            continue

        try:
            cat_name_raw, json_url = line.split(':', 1)
            cat_name = cat_name_raw.strip()
            json_url = json_url.strip()

            if any(skip in cat_name.lower() for skip in SKIP_KEYWORDS):
                logging.info(f"Preskačem kategoriju (zbog ključne reči): '{cat_name}'")
                continue

            if json_url not in seen_urls:
                categories[cat_name] = json_url
                seen_urls.add(json_url)
                logging.info(f"Dodata kategorija: '{cat_name}' -> {json_url}")
            else:
                logging.debug(f"URL '{json_url}' već dodat, preskačem.")

        except Exception as e:
            logging.warning(f"Greška prilikom parsiranja linije '{line}': {e}")

    logging.info(f"UKUPNO kategorija za obradu: {len(categories)}")
    return categories

def get_product_links_from_category(products_json_url, cat_name):
    logging.info(f"Dohvatanje proizvoda iz JSON-a za kategoriju '{cat_name}' sa: {products_json_url}")
    links = []
    try:
        resp = scraper.get(products_json_url, timeout=15)
        resp.raise_for_status()
        json_data = resp.json()

        products = json_data.get('products', [])
        for product in products:
            handle = product.get('handle')
            if handle:
                full_product_url = urljoin(MAIN_URL, f"/products/{handle}")
                if full_product_url not in links:
                    links.append(full_product_url)

        logging.info(f"Kategorija '{cat_name}': pronađeno {len(links)} proizvoda iz JSON-a")
    except Exception as e:
        logging.error(f"Greška prilikom dohvatanja proizvoda iz JSON-a za kategoriju '{cat_name}' ({products_json_url}): {e}")
    return links

def get_json_data(product_url):
    json_api_url = product_url.split('?')[0] + '.json'
    try:
        response = scraper.get(json_api_url, timeout=15)
        response.raise_for_status()
        return response.json().get('product')
    except Exception as e:
        logging.warning(f"JSON greška za {product_url}: {e}")
        return None

def scrape_product(product_url, logo_url, assigned_collection):
    logging.info(f"Skrejpujem proizvod: {product_url}")
    json_data = get_json_data(product_url)
    if not json_data:
        return None

    title = json_data.get('title')
    description = json_data.get('body_html') or ''
    sku = json_data.get('variants', [{}])[0].get('sku')

    price_str = json_data.get('variants', [{}])[0].get('price')
    cena = None
    if price_str:
        try:
            cena_float = float(price_str)
            cena = f"{cena_float:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            pass

    images = [img['src'].split('?')[0] for img in json_data.get('images', [])]

    colors = []
    specs = {}
    precise_category = None

    try:
        resp = scraper.get(product_url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        for row in soup.select('.feature-chart__table-row'):
            k = row.select_one('.feature-chart__heading')
            v = row.select_one('.feature-chart__value')
            if k and v:
                key = k.get_text(strip=True)
                val = v.get_text(separator=' ', strip=True)
                if key and val:
                    specs[key] = val

        seen_colors = set()
        for label in soup.select('label.thumbnail-swatch, label.color-swatch'):
            sr = label.select_one('.sr-only')
            color_name = sr.get_text(strip=True) if sr else None
            if not color_name or color_name in seen_colors:
                continue
            seen_colors.add(color_name)

            img_tag = label.find('img')
            img_url = None
            if img_tag and img_tag.get('src'):
                raw_url = img_tag['src']
                if raw_url.startswith('//'):
                    raw_url = 'https:' + raw_url
                img_url = re.sub(r'&width=\d+', '', raw_url.split('&v=')[0])

            if not img_url:
                style = label.get('style', '')
                url_match = re.search(r'url$$([^)]+)$$', style)
                if url_match:
                    raw_url = url_match.group(1)
                    if raw_url.startswith('//'):
                        raw_url = 'https:' + raw_url
                    img_url = re.sub(r'&width=\d+', '', raw_url)

            colors.append({
                "boja": color_name,
                "url_uzorka": img_url or ""
            })

        product_type_div = soup.select_one('div.product-info__type a')
        if product_type_div:
            precise_category = product_type_div.get_text(strip=True)

        # Normalizacija i fallback logika
        if precise_category:
            precise_category = normalize_category(precise_category)

        if not precise_category or precise_category == "Ostalo":
            precise_category = normalize_category(assigned_collection)

        if not precise_category or precise_category == "Ostalo":
            precise_category = "Ostalo"

    except Exception as e:
        logging.warning(f"HTML greška za proizvod {product_url}: {e}")
        if not precise_category or precise_category == "Ostalo":
            precise_category = normalize_category(assigned_collection) or "Ostalo"

    logging.info(f"Gotova obrada: {title} | Cena: {cena} | Boje: {len(colors)} | Kategorija: {precise_category}")

    return {
        "ime_proizvoda": title,
        "sku": sku,
        "brend_logo_url": logo_url,
        "cena": cena,
        "opis": description,
        "url_proizvoda": product_url,
        "url_slika": images,
        "specifikacije": specs,
        "kategorije": precise_category,
        "dodatne_informacije": {
            "tagline": None,
            "dostupne_boje": colors
        }
    }

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

        logging.info("Sve kategorije za obradu:")
        for cat in categories:
            logging.info(f" - {cat}")

        for cat_name, products_json_url in categories.items():
            time.sleep(random.uniform(1.5, 3.0))
            product_links = get_product_links_from_category(products_json_url, cat_name)
            logging.info(f"Broj proizvoda u kategoriji '{cat_name}': {len(product_links)}")

            for link in product_links:
                if link in existing_urls:
                    logging.debug(f"Preskačem već postojeći proizvod: {link}")
                    continue
                time.sleep(random.uniform(0.8, 1.8))
                result = scrape_product(link, logo, cat_name)
                if result:
                    final_data.append(result)
                    existing_urls.add(link)

        # Dodatno logovanje kategorija neposredno pre čuvanja JSON fajla
        logging.info("Pregled kategorija proizvoda pre čuvanja JSON fajla:")
        category_counts = {}
        for item in final_data:
            cat = item.get("kategorije", "Ostalo")
            category_counts[cat] = category_counts.get(cat, 0) + 1
        for cat, count in category_counts.items():
            logging.info(f" - {cat}: {count} proizvoda")

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
