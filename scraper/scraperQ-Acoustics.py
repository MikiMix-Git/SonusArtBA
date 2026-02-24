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
CODE_VERSION = "Q1.10"  # Verzija sa najnovijom izmenom za boje
LOG_FILE = f"q_acoustics_scraper_{CODE_VERSION}.log"
OUTPUT_FILENAME = f"q_acoustics_products_{CODE_VERSION}.json"
MAIN_URL = "https://www.qacoustics.com/"

COLLECTION_JSON_ENDPOINTS_RAW = """
Svi proizvodi (glavni endpoint): https://www.qacoustics.com/products.json
All kolekcija: https://www.qacoustics.com/collections/all/products.json

Bookshelf Speakers: https://www.qacoustics.com/collections/bookshelf-speakers/products.json
Floorstanding Speakers: https://www.qacoustics.com/collections/floorstanding-speakers/products.json
Home Theater: https://www.qacoustics.com/collections/home-theater/products.json
Subwoofers: https://www.qacoustics.com/collections/sunwoofers/products.json
Active Speakers: https://www.qacoustics.com/collections/active-speakers/products.json
Centered: https://www.qacoustics.com/collections/centered/products.json
"""

SKIP_KEYWORDS = {
    "test", "black friday", "sale"
}

CATEGORY_MAP = {
    "bookshelf speakers": "Bookshelf Speakers",
    "floorstanding speakers": "Floorstanding Speakers",
    "home theater": "Home Theater",
    "subwoofers": "Subwoofers",
    "active speakers": "Active Speakers",
    "centered": "Centered",
}

scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
)

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)  # DEBUG nivo za detaljne logove
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
    logging.info(f"Q-Acoustics scraper started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info("=" * 80)
    return logger

def shutdown_logging(logger):
    logging.info("=" * 80)
    logging.info(f"Q-Acoustics scraper finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info("=" * 80)
    for h in logger.handlers[:]:
        try:
            h.close()
        finally:
            logger.removeHandler(h)

def normalize_category(cat_name):
    if not cat_name:
        return "Other"
    cat_key = cat_name.strip().lower()
    if cat_key == "sunwoofers":
        cat_key = "subwoofers"
    return CATEGORY_MAP.get(cat_key, cat_name)

def get_brand_logo_url():
    logging.info("Fetching brand logo...")
    try:
        resp = scraper.get(MAIN_URL, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        img = soup.select_one('img.logo, img[alt*="Q Acoustics"], .site-header__logo img')
        if img and img.get('src'):
            src = img['src'].split('?')[0]
            full = urljoin(MAIN_URL, src)
            logging.info(f"Logo URL found: {full}")
            return full
    except Exception as e:
        logging.warning(f"Logo fetch error: {e}")

    fallback = "https://www.qacoustics.com/favicon.ico"
    logging.info(f"Using fallback logo: {fallback}")
    return fallback

def get_categories():
    logging.info("Parsing JSON endpoints for categories...")
    categories = {}
    seen_urls = set()

    for line in COLLECTION_JSON_ENDPOINTS_RAW.strip().split('\n'):
        line = line.strip()
        if not line or ':' not in line:
            continue

        try:
            cat_name_raw, json_url = line.split(':', 1)
            cat_name = cat_name_raw.strip()
            if cat_name.lower() == "sunwoofers":
                cat_name = "Subwoofers"
            json_url = json_url.strip()

            if any(skip in cat_name.lower() for skip in SKIP_KEYWORDS):
                logging.info(f"Skipping category due to keyword: '{cat_name}'")
                continue

            if json_url not in seen_urls:
                categories[cat_name] = json_url
                seen_urls.add(json_url)
                logging.info(f"Added category: '{cat_name}' -> {json_url}")
            else:
                logging.debug(f"URL '{json_url}' already added, skipping.")

        except Exception as e:
            logging.warning(f"Error parsing line '{line}': {e}")

    logging.info(f"Total categories to process: {len(categories)}")
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
        logging.error(
            f"Greška prilikom dohvatanja proizvoda iz JSON-a za kategoriju '{cat_name}' ({products_json_url}): {e}"
        )
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

def parse_specifications(soup):
    specs = {}
    details_tags = soup.find_all('details', class_='details')
    for details in details_tags:
        summary = details.find('summary')
        if summary and 'Specification' in summary.get_text():
            p_tags = details.select('div.specification p')
            if not p_tags:
                p_tags = details.find_all('p')
            for p in p_tags:
                strong_tag = p.find('strong')
                if strong_tag:
                    key = strong_tag.get_text(strip=True).rstrip(':')
                    value = p.get_text(strip=True).replace(strong_tag.get_text(strip=True), '').strip()
                    specs[key] = value
            break
    return specs

def parse_available_colors(soup):
    colors = []
    ul = soup.select_one('ul.swatches')
    if not ul:
        logging.debug("parse_available_colors: Nije pronađen 'ul.swatches' element.")
        return colors

    for li in ul.find_all('li'):
        magnet = li.find('magnet-element')
        if not magnet:
            logging.debug("parse_available_colors: Nije pronađen 'magnet-element' unutar 'li'.")
            colors.append({"boja": "Unknown", "url_uzorka": ""})
            continue

        input_tag = magnet.find('input', {'type': 'radio'})
        label = magnet.find('label', class_='color-swatch')
        if not input_tag or not label:
            logging.debug("parse_available_colors: Nije pronađen 'input' ili 'label.color-swatch' unutar 'magnet-element'.")
            colors.append({"boja": "Unknown", "url_uzorka": ""})
            continue

        color_name = input_tag.get('value') or label.get('title') or ''
        color_name = color_name.strip()
        logging.debug(f"parse_available_colors: Obrađujem boju: '{color_name}'")

        style = label.get('style', '')
        logging.debug(f"parse_available_colors: Raw style attribute for '{color_name}' (repr): {repr(style)}")
        logging.debug(f"parse_available_colors: Raw style attribute for '{color_name}': '{style}'")

        img_url = ''

        if not style or not isinstance(style, str):
            logging.warning(f"parse_available_colors: 'style' atribut je prazan ili nije string za '{color_name}'. Vrednost: {repr(style)}")
            colors.append({"boja": color_name, "url_uzorka": ""})
            continue

        if '--swatch-background-image:' in style:
            try:
                start_url_func = style.find('url(')
                if start_url_func != -1:
                    end_url_func = style.find(')', start_url_func)
                    if end_url_func != -1:
                        raw_img_url = style[start_url_func + 4:end_url_func].strip()
                        if raw_img_url.startswith("'") and raw_img_url.endswith("'"):
                            raw_img_url = raw_img_url[1:-1]
                        elif raw_img_url.startswith('"') and raw_img_url.endswith('"'):
                            raw_img_url = raw_img_url[1:-1]

                        img_url = raw_img_url
                        img_url = img_url.replace('&amp;', '&')
                        if img_url.startswith('//'):
                            img_url = 'https:' + img_url
                        elif img_url.startswith('/'):
                            img_url = urljoin(MAIN_URL, img_url)
                        logging.debug(f"parse_available_colors: Uspešno izvučen i obrađen 'url_uzorka' za '{color_name}': '{img_url}'")
                    else:
                        logging.warning(f"parse_available_colors: Nije pronađena zatvorena zagrada ')' za 'url(' u stilu za '{color_name}'. Stil: '{style}'")
                else:
                    logging.warning(f"parse_available_colors: Nije pronađena 'url(' funkcija u stilu za '{color_name}'. Stil: '{style}'")
            except Exception as e:
                logging.error(f"parse_available_colors: Greška pri parsiranju URL-a string metodama za '{color_name}'. Stil: '{style}'. Greška: {e}")
        else:
            logging.debug(f"parse_available_colors: '--swatch-background-image:' nije pronađen u stilu za '{color_name}'. Stil: '{style}'")

        colors.append({
            "boja": color_name,
            "url_uzorka": img_url
        })

    return colors

def scrape_product(product_url, logo_url, assigned_collection):
    logging.info(f"Skrejpujem proizvod: {product_url}")
    json_data = get_json_data(product_url)
    if not json_data:
        logging.warning(f"Nema JSON podataka za proizvod: {product_url}")
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

    precise_category = None
    colors = []

    try:
        resp = scraper.get(product_url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        specs = parse_specifications(soup)
        colors = parse_available_colors(soup)

        product_type_div = soup.select_one('div.product-info__type a')
        if product_type_div:
            precise_category = product_type_div.get_text(strip=True)

        if precise_category:
            precise_category = normalize_category(precise_category)

        if not precise_category or precise_category == "Ostalo":
            precise_category = normalize_category(assigned_collection)

        if not precise_category or precise_category == "Ostalo":
            precise_category = "Ostalo"

    except Exception as e:
        logging.warning(f"HTML greška za proizvod {product_url}: {e}")
        specs = {}
        if not precise_category or precise_category == "Ostalo":
            precise_category = normalize_category(assigned_collection) or "Ostalo"

    result = {
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

    try:
        logging.debug(
            f"Scrape result preview ({product_url}): {json.dumps(result, ensure_ascii=False)[:500]}..."
        )
    except Exception:
        logging.debug(f"Scrape result preview ({product_url}): (nije moguće dump-ovati)")

    logging.info(
        f"Gotova obrada: {title} | Cena: {cena} | Boje: {len(colors)} | Kategorija: {precise_category}"
    )
    return result

def main():
    logger = setup_logging()
    try:
        logging.info(f"Output fajl (relativno): {OUTPUT_FILENAME}")
        logging.info(f"Output fajl (apsolutno): {os.path.abspath(OUTPUT_FILENAME)}")

        final_data = []
        existing_urls = set()
        if os.path.exists(OUTPUT_FILENAME):
            try:
                with open(OUTPUT_FILENAME, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    final_data.extend(data)
                    existing_urls = {item.get('url_proizvoda') for item in data if item.get('url_proizvoda')}
                logging.info(f"Učitano iz postojećeg JSON-a: {len(existing_urls)} URL-ova i {len(final_data)} proizvoda u memoriju.")
            except Exception as e:
                logging.warning(f"Ne mogu da učitam postojeći JSON ({OUTPUT_FILENAME}): {e}")
        else:
            logging.info("Ne postoji postojeći output JSON fajl (kreiraću novi).")

        logo = get_brand_logo_url()
        categories = get_categories()

        logging.info("Sve kategorije za obradu:")

        priority_cats = [
            "Bookshelf Speakers",
            "Floorstanding Speakers",
            "Home Theater",
            "Subwoofers",
            "Centered"
        ]

        for cat_name in priority_cats:
            if cat_name in categories:
                logging.info(f" - {cat_name}")
                products_json_url = categories[cat_name]
                time.sleep(random.uniform(1.5, 3.0))
                product_links = get_product_links_from_category(products_json_url, cat_name)
                logging.info(f"Broj proizvoda u kategoriji '{cat_name}': {len(product_links)}")

                for link in product_links:
                    time.sleep(random.uniform(0.8, 1.8))
                    result = scrape_product(link, logo, cat_name)
                    if result:
                        final_data.append(result)
                        existing_urls.add(link)
                        logging.info(
                            f"Dodat u final_data: {result.get('ime_proizvoda')} | ukupno u memoriji: {len(final_data)}"
                        )
                    else:
                        logging.warning(f"result=None za proizvod: {link}")

                categories.pop(cat_name)

        for cat_name, products_json_url in categories.items():
            logging.info(f" - {cat_name}")
            time.sleep(random.uniform(1.5, 3.0))
            product_links = get_product_links_from_category(products_json_url, cat_name)
            logging.info(f"Broj proizvoda u kategoriji '{cat_name}': {len(product_links)}")

            for link in product_links:
                time.sleep(random.uniform(0.8, 1.8))
                result = scrape_product(link, logo, cat_name)
                if result:
                    final_data.append(result)
                    existing_urls.add(link)
                    logging.info(
                        f"Dodat u final_data: {result.get('ime_proizvoda')} | ukupno u memoriji: {len(final_data)}"
                    )
                else:
                    logging.warning(f"result=None za proizvod: {link}")

        logging.info("Pregled kategorija proizvoda pre čuvanja JSON fajla (samo NOVO u ovom run-u):")
        category_counts = {}
        for item in final_data:
            cat = item.get("kategorije", "Ostalo")
            category_counts[cat] = category_counts.get(cat, 0) + 1
        for cat, count in category_counts.items():
            logging.info(f" - {cat}: {count} proizvoda")

        logging.info(f"Spremam upis u fajl. final_data size = {len(final_data)}")

        with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, indent=4, ensure_ascii=False)

        try:
            size_bytes = os.path.getsize(OUTPUT_FILENAME)
            logging.info(f"Upis završen. Veličina fajla: {size_bytes} bytes")
        except Exception as e:
            logging.warning(f"Upis završen, ali ne mogu da pročitam veličinu fajla: {e}")

        logging.info(f"UKUPNO NOVO: {len(final_data)} | SAČUVANO U: {OUTPUT_FILENAME}")

    except KeyboardInterrupt:
        logging.warning("PREKINUTO – čuvam...")
    except Exception as e:
        logging.critical(f"Greška: {e}")
    finally:
        shutdown_logging(logger)

if __name__ == "__main__":
    main()
