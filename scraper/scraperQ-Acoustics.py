# scraperQ-Acoustics.py
# =============================================
# VERZIJA: v1.2.9 (02.12.2025.) — KONAČNA & 100% ISPRAVNA
# =============================================
# • QED kablovi → samo "dužina" (bez url_uzorka)
# • Zvučnici → "boja" + realni 100×100 px url_uzorka
# • Sve greške ispravljene (c_name_name → c_name)
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

CODE_VERSION = "v1.2.9"
LOG_FILE = "qacoustics_production.log"
OUTPUT_JSON = "qacoustics_products.json"
MAIN_URL = "https://www.qacoustics.com"
COLLECTIONS_URL = "https://www.qacoustics.com/collections"
MAX_PRODUCTS = 999

scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False},
    delay=15
)

# === SVG FALLBACK ZA BOJE ===
def get_svg_fallback(color_name):
    simple_map = {"Black": "#000000", "White": "#FFFFFF", "Walnut": "#8B5A2B", "Oak": "#D2B48C", "Grey": "#888888"}
    hex_color = simple_map.get(color_name, "#CCCCCC")
    svg = f'<svg width="100" height="100" xmlns="http://www.w3.org/2000/svg"><rect width="100" height="100" fill="{hex_color}"/></svg>'
    return f"data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}"

# === 100×100 px REALNI ISEČAK (samo za zvučnike) ===
def get_real_color_sample(image_url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(image_url, headers=headers, timeout=12)
        if resp.status_code != 200:
            return None
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
    except Exception as e:
        logging.debug(f"Greška pri 100×100 isečku: {e}")
        return None

# === LOGOVANJE ===
def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    if logger.hasHandlers(): logger.handlers.clear()
    formatter = logging.Formatter(f'[%(asctime)s] [v1.2.9] [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
    file_handler = logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    logging.info("========== Q ACOUSTICS SKREJPER v1.2.9 – START ==========")

def shutdown_logging():
    logging.info("========== Q ACOUSTICS SKREJPER v1.2.9 – KRAJ ==========")
    for h in logging.getLogger().handlers[:]:
        h.close()
        logging.getLogger().removeHandler(h)

# === UČITAVANJE POSTOJEĆIH ===
def load_existing_data():
    existing_handles = set()
    data = []
    if os.path.exists(OUTPUT_JSON):
        try:
            with open(OUTPUT_JSON, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logging.info(f"Učitano {len(data)} postojećih proizvoda")
            for p in data:
                h = p.get("url_proizvoda", "").split('/products/')[-1].split('?')[0]
                if h: existing_handles.add(h)
        except Exception as e:
            logging.error(f"Greška učitavanja: {e}")
    return data, existing_handles

# === LOGO BRENDA ===
def get_brand_logo():
    try:
        r = scraper.get(MAIN_URL, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        el = soup.select_one('img[alt="Q Acoustics"], a.logo img')
        if el and el.get('src'):
            return urljoin(MAIN_URL, el['src'])
    except: pass
    return "https://www.qacoustics.com/cdn/shop/files/qalogo_small.png?v=1617783915"

# === KATEGORIJE ===
def get_categories():
    logging.info("Dohvatanje kategorija...")
    cats = {}
    try:
        r = scraper.get(COLLECTIONS_URL, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        for a in soup.select('a[href*="/collections/"]'):
            href = a.get('href')
            name = a.get_text(strip=True)
            if not href or not name or '/products/' in href: continue
            blocked = ['all','shop','new','sale','spares','3000i','3000c','5000','q acoustics 3000c range','concept range','concept series']
            if any(b in name.lower() for b in blocked): continue
            full = urljoin(COLLECTIONS_URL, href).split('?')[0]
            if full not in cats.values():
                cats[name] = full
        logging.info(f"Pronađeno {len(cats)} kategorija: {', '.join(cats.keys())}")
    except Exception as e:
        logging.error(f"Greška kategorije: {e}")
    return cats

# === JSON API ===
def get_product_json(handle):
    url = f"{MAIN_URL}/products/{handle}.json"
    try:
        r = scraper.get(url, timeout=15)
        r.raise_for_status()
        return r.json().get('product', {})
    except: return {}

# === PARSIRANJE HTML-a ===
def parse_html(soup, json_data, handle):
    opis = ""
    meta = soup.find('meta', {'name': 'description'})
    if meta and meta.get('content'): opis = meta['content'].strip()
    if len(opis) < 100:
        sec = soup.select_one('#product-description, .product__description, section[data-tab="OVERVIEW"]')
        if sec:
            opis = ' '.join([p.get_text(strip=True) for p in sec.find_all('p') if p.get_text(strip=True)]) or sec.get_text(strip=True)

    specs = {}
    ul = soup.select_one('ul.specs, ul.product-specs, div.specs ul, ul.product-details, ul.key-specs')
    if ul:
        for li in ul.find_all('li', recursive=False):
            text = li.get_text(strip=True)
            if ':' in text:
                k, v = text.split(':', 1)
                specs[k.strip()] = v.strip()

    if len(specs) < 8:
        table = soup.select_one('table.specs-table, table')
        if table:
            for tr in table.find_all('tr'):
                cells = tr.find_all(['td', 'th'])
                if len(cells) >= 2:
                    k = cells[0].get_text(strip=True).rstrip(':').strip()
                    v = cells[1].get_text(strip=True)
                    specs[k] = v

    if len(specs) < 8:
        logging.debug(f"[v1.2.9] Agresivni parser za {handle}")
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
    bc = soup.select_one('nav.breadcrumb, .breadcrumbs')
    if bc:
        links = bc.find_all('a')
        if links: cat = links[-1].get_text(strip=True).title()

    return opis or "Opis nedostupan", specs, cat

# === LINKOVI IZ KOLEKCIJE ===
def get_links(coll_url, coll_name):
    links = []
    handle = coll_url.split('/collections/')[-1].split('?')[0]
    json_url = f"{MAIN_URL}/collections/{handle}/products.json"
    try:
        r = scraper.get(json_url, timeout=15)
        if r.status_code == 200:
            for p in r.json().get('products', []):
                links.append((f"{MAIN_URL}/products/{p['handle']}", coll_name))
            return links
    except: pass

    try:
        r = scraper.get(coll_url, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        for a in soup.select('a[href*="/products/"]'):
            h = a.get('href')
            if h and '/products/' in h:
                full = urljoin(coll_url, h).split('?')[0]
                if full not in [l[0] for l in links]:
                    links.append((full, coll_name))
    except Exception as e:
        logging.error(f"Greška kolekcija {coll_name}: {e}")
    return links

# === GLAVNA FUNKCIJA ===
def scrape_product(product_url, logo, coll_name):
    handle = product_url.split('/products/')[-1].split('?')[0]
    logging.debug(f"\nv1.2.9 | OBRAĐUJEM: {handle}")
    data = get_product_json(handle)
    if not data: return None

    title = data.get('title', 'Nepoznato')
    variants = data.get('variants', [])
    price = f"${float(variants[0]['price']):,.2f}" if variants else "$0.00"
    sku = variants[0].get('sku', '') if variants else ''
    title_lower = title.lower()

    # DETEKCIJA QED KABLOVA
    is_qed_cable = (
        str(sku).upper().startswith(('QE', 'QED')) or
        ('qed' in title_lower and any(word in title_lower for word in ['cable', 'subwoofer', 'hdmi', 'optical', 'speaker cable', 'interconnect', 'performance', 'reference']))
    )

    images = []
    variant_img_map = {}
    for img in data.get('images', []):
        src = img.get('src', '').split('?')[0]
        full = urljoin("https://cdn.shopify.com", src)
        images.append(full)
        for vid in img.get('variant_ids', []):
            variant_img_map[vid] = full

    try:
        r = scraper.get(product_url, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        opis, specs, cat = parse_html(soup, data, handle)
    except:
        opis, specs, cat = "Opis nedostupan", {}, coll_name

    colors = []
    lengths = []

    for v in variants:
        opt = v.get('option1')
        if not opt or opt == "Default Title": continue

        img_url = variant_img_map.get(v['id']) or (images[0] if images else None)

        if is_qed_cable:
            lengths.append({"dužina": opt})
        else:
            sample = get_real_color_sample(img_url) if img_url else None
            if not sample:
                sample = get_svg_fallback(opt)
            colors.append({"boja": opt, "url_uzorka": sample})

    category = cat if cat != "Nepoznato" else coll_name

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
            "dostupne_boje": colors,
            "dostupne_dužine": lengths
        }
    }
    logging.info(f"v1.2.9 | ZAVRŠENO: {title} | Boja: {len(colors)} | Dužina: {len(lengths)} | Spec: {len(specs)}")
    return result

# === MAIN ===
def main():
    setup_logging()
    try:
        existing_data, existing_handles = load_existing_data()
        logo = get_brand_logo()
        cats = get_categories()
        if not cats:
            logging.critical("NEMA KATEGORIJA – PREKID")
            return

        new = []
        count = 0

        for name, url in cats.items():
            if count >= MAX_PRODUCTS: break
            logging.info(f"KATEGORIJA: {name}")
            time.sleep(random.uniform(1, 2))
            for p_url, c_name in get_links(url, name):
                if count >= MAX_PRODUCTS: break
                h = p_url.split('/products/')[-1].split('?')[0]
                if h in existing_handles: continue
                time.sleep(random.uniform(0.6, 1.3))
                prod = scrape_product(p_url, logo, c_name)   # ← ISPRAVLJENO: c_name_name → c_name
                if prod:
                    new.append(prod)
                    existing_handles.add(h)
                    count += 1

        final = existing_data + new
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(final, f, indent=4, ensure_ascii=False)
        logging.info(f"v1.2.9 | SAČUVANO: {len(final)} proizvoda → {OUTPUT_JSON}")

    except KeyboardInterrupt:
        logging.warning("PREKINUTO OD KORISNIKA")
    except Exception as e:
        logging.critical(f"KRITIČNA GREŠKA: {e}")
    finally:
        shutdown_logging()

if __name__ == "__main__":
    main()
