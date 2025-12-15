# scraperPolkAudio.py
# =============================================
# VERZIJA: v1.1.1 (12.12.2025.)
# =============================================
# • Specifikacije bez prefiksa grupe (samo ključ: vrednost)
# • Slike, boje, SKU, kategorije – sve ispravno
# =============================================

import cloudscraper
import json
from bs4 import BeautifulSoup
import os
import time
import random
import logging
import sys
import re
import base64
import requests
from urllib.parse import urljoin
from PIL import Image
from io import BytesIO

CODE_VERSION = "v1.1.1"
LOG_FILE = "polkaudio_production.log"
OUTPUT_JSON = "polkaudio_products.json"
MAIN_URL = "https://www.polkaudio.com"
CATEGORIES_URL = "https://www.polkaudio.com/en-us/"

scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False},
    delay=15
)

# === SVG FALLBACK ===
def get_svg_fallback(color_name):
    simple_map = {"Black": "#000000", "White": "#FFFFFF", "Walnut": "#8B5A2B", "Brown": "#8B4513", "Grey": "#888888"}
    hex_color = simple_map.get(color_name, "#CCCCCC")
    svg = f'<svg width="100" height="100" xmlns="http://www.w3.org/2000/svg"><rect width="100" height="100" fill="{hex_color}"/></svg>'
    return f"data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}"

# === 100×100 px REALNI ISEČAK ===
def get_real_color_sample(image_url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(image_url, headers=headers, timeout=12)
        if resp.status_code != 200: return None
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        w, h = img.size
        box_size = 100
        left = w - (w // 3) + ((w // 3 - box_size) // 2)
        top = (h - box_size) // 2
        left = max(0, min(left, w - box_size))
        top = max(0, min(top, h - box_size))
        cropped = img.crop((left, top, left + box_size, top + box_size))
        buf = BytesIO()
        cropped.save(buf, format="JPEG", quality=95, optimize=True)
        return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"
    except: return None

# === LOGOVANJE ===
def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    if logger.hasHandlers(): logger.handlers.clear()
    formatter = logging.Formatter(f'[%(asctime)s] [v1.1.1] [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
    file_handler = logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    logging.info("========== POLK AUDIO SKREJPER v1.1.1 – START ==========")

def shutdown_logging():
    logging.info("========== POLK AUDIO SKREJPER v1.1.1 – KRAJ ==========")
    for h in logging.getLogger().handlers[:]:
        h.close()
        logging.getLogger().removeHandler(h)

# === UČITAVANJE POSTOJEĆIH ===
def load_existing_data():
    existing_urls = set()
    data = []
    if os.path.exists(OUTPUT_JSON):
        try:
            with open(OUTPUT_JSON, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logging.info(f"Učitano {len(data)} postojećih proizvoda")
            for p in data:
                url = p.get("url_proizvoda", "")
                if url: existing_urls.add(url.split('?')[0])
        except Exception as e:
            logging.error(f"Greška učitavanja: {e}")
    return data, existing_urls

# === LOGO ===
def get_brand_logo():
    return "https://www.polkaudio.com/on/demandware.static/Sites-Polkaudio-US-Site/-/default/dw1f0c7e6f/images/polkaudio-logo.svg"

# === KATEGORIJE ===
def get_categories():
    logging.info("Dohvatanje kategorija...")
    cats = {
        "Home Speakers": "https://www.polkaudio.com/en-us/category/home-speakers/",
        "Sound Bars": "https://www.polkaudio.com/en-us/category/sound-bars/",
        "Built-in Speakers": "https://www.polkaudio.com/en-us/category/built-in-speakers/",
        "Outdoor Speakers": "https://www.polkaudio.com/en-us/category/outdoor-speakers/",
        "Car & Marine": "https://www.polkaudio.com/en-us/category/car-and-marine-speakers/"
    }
    logging.info(f"Pronađeno {len(cats)} kategorija")
    return cats

# === LINKOVI IZ KATEGORIJE ===
def get_product_links_from_category(cat_url):
    links = []
    try:
        r = scraper.get(cat_url, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        for a in soup.select('a[href*="/product/"]'):
            href = a.get('href')
            if href and '/product/' in href:
                full = urljoin(MAIN_URL, href).split('?')[0]
                if full not in links:
                    links.append(full)
    except Exception as e:
        logging.error(f"Greška kategorija {cat_url}: {e}")
    return links

# === PARSIRANJE HTML-a – specifikacije BEZ prefiksa grupe ===
def parse_html(soup, json_data, handle):
    opis = ""
    meta = soup.find('meta', {'name': 'description'})
    if meta and meta.get('content'): opis = meta['content'].strip()
    if len(opis) < 100:
        sec = soup.select_one('#product-description, .product__description, section[data-tab="OVERVIEW"]')
        if sec:
            opis = ' '.join([p.get_text(strip=True) for p in sec.find_all('p') if p.get_text(strip=True)]) or sec.get_text(strip=True)

    specs = {}
    for wrapper in soup.select('.specifications-wrapper'):
        ul = wrapper.select_one('ul.specifications-list')
        if ul:
            for li in ul.find_all('li'):
                name = li.select_one('.name')
                value = li.select_one('.value')
                if name and value:
                    k = name.get_text(strip=True).rstrip(':')
                    v = value.get_text(strip=True)
                    specs[k] = v

    # Agresivni fallback ako je malo specifikacija
    if len(specs) < 8:
        logging.debug(f"[v1.1.1] Agresivni parser aktiviran za {handle}")
        all_text = soup.get_text(separator='\n')
        lines = [l.strip() for l in all_text.split('\n') if l.strip() and len(l) < 200]
        banned = ['in stock','add to cart','reviews','shipping','warranty','buy now','price','sale','save','free delivery','rating']
        for line in lines:
            if any(b in line.lower() for b in banned): continue
            if ':' in line:
                k, v = line.split(':', 1)
                k = k.strip(); v = v.strip()
                if k and v and k not in specs: specs[k] = v

    cat = "Nepoznato"
    breadcrumb = soup.select_one('.breadcrumb, .breadcrumbs')
    if breadcrumb:
        links = breadcrumb.find_all('a')
        if links and len(links) > 1:
            cat = links[-2].get_text(strip=True)

    return opis or "Opis nedostupan", specs, cat

# === GLAVNA FUNKCIJA ===
def scrape_product(product_url, logo):
    logging.debug(f"Obrađujem: {product_url}")
    try:
        r = scraper.get(product_url, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')

        title = soup.select_one('h1.product-name, h1.title').get_text(strip=True) if soup.select_one('h1.product-name, h1.title') else "Nepoznato"

        sku = soup.select_one('[data-productid]')
        sku = sku['data-productid'].strip() if sku and 'data-productid' in sku.attrs else "Nedostupan"

        price = soup.select_one('.price-sales, .price, .sales').get_text(strip=True) if soup.select_one('.price-sales, .price, .sales') else "N/A"

        opis = soup.select_one('meta[name="description"]')
        opis = opis['content'].strip() if opis else "Opis nedostupan"

        # Slike – iz srcset
        images = []
        for img in soup.select('img[srcset], img[data-srcset]'):
            srcset = img.get('srcset') or img.get('data-srcset')
            if srcset:
                srcs = [s.strip().split(' ')[0] for s in srcset.split(',')]
                largest = max(srcs, key=lambda x: int(re.search(r'width=(\d+)', x).group(1)) if re.search(r'width=(\d+)', x) else 0)
                images.append(largest)

        # Specifikacije – bez prefiksa
        opis, specs, cat = parse_html(soup, None, product_url)

        # Boje
        colors = []
        for sw in soup.select('.swatch, .color-swatch, .swatch-item'):
            color_name = sw.get('data-color') or sw.get('title') or sw.get_text(strip=True)
            if not color_name or color_name in ["Select Color", ""]: continue
            img_tag = sw.find('img')
            img_url = img_tag['src'] if img_tag and 'src' in img_tag.attrs else images[0] if images else None
            if img_url:
                img_url = urljoin(MAIN_URL, img_url.split('?')[0])
            sample = get_real_color_sample(img_url) if img_url else get_svg_fallback(color_name)
            colors.append({"boja": color_name, "url_uzorka": sample})

        category = cat if cat != "Nepoznato" else "Nepoznato"

        result = {
            "ime_proizvoda": title,
            "sku": sku,
            "brend_logo_url": logo,
            "cena": price,
            "opis": opis,
            "url_proizvoda": product_url,
            "url_slika": images[:10],
            "specifikacije": specs,
            "kategorije": category,
            "dodatne_informacije": {
                "tagline": None,
                "dostupne_boje": colors,
                "dostupne_dužine": []
            }
        }
        logging.info(f"ZAVRŠENO: {title} | Boja: {len(colors)} | Spec: {len(specs)}")
        return result
    except Exception as e:
        logging.error(f"Greška za {product_url}: {e}")
        return None

# === MAIN ===
def main():
    setup_logging()
    try:
        existing_data, existing_urls = load_existing_data()
        logo = get_brand_logo()
        cats = get_categories()

        new_products = []

        for name, url in cats.items():
            logging.info(f"KATEGORIJA: {name}")
            time.sleep(random.uniform(1.5, 3))
            links = get_product_links_from_category(url)
            for link in links:
                clean_url = link.split('?')[0]
                if clean_url in existing_urls: continue
                time.sleep(random.uniform(0.8, 1.8))
                prod = scrape_product(link, logo)
                if prod:
                    new_products.append(prod)
                    existing_urls.add(clean_url)

        final = existing_data + new_products
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(final, f, indent=4, ensure_ascii=False)
        logging.info(f"SAČUVANO: {len(final)} proizvoda → {OUTPUT_JSON}")

    except KeyboardInterrupt:
        logging.warning("PREKINUTO")
    except Exception as e:
        logging.critical(f"KRITIČNA GREŠKA: {e}")
    finally:
        shutdown_logging()

if __name__ == "__main__":
    main()
