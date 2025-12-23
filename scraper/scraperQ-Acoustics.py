# scraperQ-Acoustics.py
# =============================================
# VERZIJA: v1.6.0 (23.12.2025.) — OČIŠĆENA + ISPRAVKA KATEGORIJE
# =============================================
# • Dodavanje "No Category" za proizvode iz /collections/all ako nema bolje kategorije
# • Ostale funkcionalnosti ostaju netaknute
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

CODE_VERSION = "v1.6.0"
LOG_FILE = "qacoustics_production.log"
OUTPUT_JSON = "qacoustics_products.json"
MAIN_URL = "https://www.qacoustics.com"
COLLECTIONS_URL = "https://www.qacoustics.com/collections"
MAX_PRODUCTS = 999

scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False},
    delay=15
)

# === POMOĆNA FUNKCIJA ZA FORMATIRANJE HANDLE-A ===
def to_title_case(handle):
    if not handle:
        return "Nepoznata Kategorija"
    
    if handle.lower() == "sunwoofers":
        return "Subwoofers"
    
    return handle.replace('-', ' ').title()

# === SVG FALLBACK ZA BOJE ===
def get_svg_fallback(color_name):
    normalized_name = color_name.lower().replace(' ', '')
    
    color_hex_map = {
        "black": "#000000",
        "satinblack": "#1f1f1f", 
        "carbonblack": "#181818", 
        "white": "#FFFFFF",
        "arcticwhite": "#f0f0f0", 
        "walnut": "#6E4527",
        "englishwalnut": "#7B5338", 
        "rosewood": "#A0525C", 
        "oak": "#A08060", 
        "pineoak": "#C2B280", 
        "grey": "#808080",
        "graphitegrey": "#3A3A3A", 
        "lacqueredblack": "#0D0D0D", 
        "lacqueredwhite": "#F9F9F9", 
        "naturaloak": "#C0A060"
    }
    
    hex_color = color_hex_map.get(normalized_name, "#CCCCCC") 
    
    svg = f'<svg width="100" height="100" xmlns="http://www.w3.org/2000/svg"><rect width="100" height="100" fill="{hex_color}"/></svg>'
    return f"data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}"

# === GENERISANJE URL-a UZORKA BOJE ===
def get_color_sample_url(image_url):
    if not image_url:
        return None
    
    base_url = image_url.split('?')[0]
    
    parts = base_url.rsplit('.', 1)
    if len(parts) == 2:
        return f"{parts[0]}_100x.{parts[1]}"
    
    return image_url

# === LOGOVANJE ===
def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    if logger.hasHandlers(): logger.handlers.clear()
    formatter = logging.Formatter(f'[%(asctime)s] [{CODE_VERSION}] [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
    file_handler = logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    logging.info(f"========== Q ACOUSTICS SKREJPER {CODE_VERSION} – START ==========")

def shutdown_logging():
    logging.info(f"========== Q ACOUSTICS SKREJPER {CODE_VERSION} – KRAJ ==========")
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
    
    blocked = ['all','shop','new','sale','spares', 'q acoustics 3000c range', 'concept range', 'concept series']
    mandatory = ['speaker-cables', 'accessories']
    
    try:
        r = scraper.get(COLLECTIONS_URL, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        
        for a in soup.select('a[href*="/collections/"]'):
            href = a.get('href')
            if not href or '/products/' in href: continue
            
            url_handle = href.split('/collections/')[-1].split('?')[0].lower()
            
            if url_handle == "sunwoofers":
                url_handle = "subwoofers"
                logging.info("Ispravljena greška sajta: sunwoofers → subwoofers")
            
            is_blocked = any(b in url_handle for b in blocked)
            if is_blocked: continue
                
            name = to_title_case(url_handle)
            full = urljoin(COLLECTIONS_URL, href).split('?')[0]
            
            if full not in cats.values():
                cats[name] = full
        
        # Fallback obavezne kategorije
        for m_handle in mandatory:
            if not any(f"/collections/{m_handle}" in url for url in cats.values()):
                name = to_title_case(m_handle)
                full_url = urljoin(MAIN_URL, f"/collections/{m_handle}")
                cats[name] = full_url
                logging.info(f"Dodata obavezna kategorija (fallback): {name}")
        
        # Dodavanje /collections/all
        all_url = "https://www.qacoustics.com/collections/all"
        if all_url not in cats.values():
            cats["All Products"] = all_url
            logging.info("Dodata kategorija 'All Products' za potpuno hvatanje")
                
        logging.info(f"Pronađeno {len(cats)} kategorija")
        
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
        p_list = soup.select('div.col-span-full p, .product-specs p, .spec-data p, .tech-specs p, section[data-tab="SPECIFICATIONS"] p')
        for p_tag in p_list:
            if p_tag.find('br') and p_tag.find('strong'):
                temp_html = str(p_tag)
                temp_html = re.sub(r'<br\s*/?>\s*<br\s*/?>', '###SPEC_SEP###', temp_html, flags=re.IGNORECASE)
                temp_html = re.sub(r'<br\s*/?>', ' ', temp_html, flags=re.IGNORECASE)
                temp_text = BeautifulSoup(temp_html, 'html.parser').get_text(separator=' ', strip=True)
                segments = temp_text.split('###SPEC_SEP###')
                for segment in segments:
                    segment = segment.strip()
                    if not segment: continue
                    if ':' in segment:
                        k, v = segment.split(':', 1)
                        k_stripped = k.strip().rstrip(':') 
                        v_stripped = v.strip()
                        if k_stripped and v_stripped and k_stripped not in specs:
                            v_stripped = re.sub(r'\s+', ' ', v_stripped)
                            specs[k_stripped] = v_stripped
                if len(specs) >= 8: break

    if len(specs) < 8:
        p_specs = soup.select('div.col-span-full p, .product-specs p, .spec-data p, .tech-specs p, section[data-tab="SPECIFICATIONS"] p')
        for p_tag in p_specs:
            strong_tag = p_tag.find('strong')
            full_text = p_tag.get_text(strip=True)
            if strong_tag:
                key = strong_tag.get_text(strip=True).rstrip(':').strip()
                key_with_colon = f"{key}:"
                if key_with_colon in full_text:
                    idx = full_text.find(key_with_colon)
                    value = full_text[idx + len(key_with_colon):].strip()
                    if key and value and key not in specs:
                        specs[key] = value
            elif ':' in full_text:
                k, v = full_text.split(':', 1)
                k_stripped = k.strip()
                v_stripped = v.strip()
                if k_stripped and v_stripped and k_stripped not in specs:
                    specs[k_stripped] = v_stripped

    if len(specs) < 8:
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
        if links: 
            last_link = links[-1].get('href', '')
            if '/collections/' in last_link:
                url_handle = last_link.split('/collections/')[-1].split('?')[0]
                cat = to_title_case(url_handle)
            else:
                cat = links[-1].get_text(strip=True).title()
            
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

# === PARSIRANJE BOJA IZ HTML-a ===
def parse_colors_from_html(soup, is_qed_cable, product_images):
    colors = []
    swatches_ul = soup.select_one('ul.swatches, ul.swatches--round, div.product-form__variants ul, .color-swatch-list')
    if swatches_ul:
        for li in swatches_ul.find_all('li'):
            label = li.find('label', class_='color-swatch')
            if not label: continue
            
            color_name = label.get('title')
            style = label.get('style', '')
            
            url_uzorka_base = None
            
            match = re.search(r'--swatch-background-image:\s*url\((.*?)\);', style)
            if match:
                raw_url = match.group(1).strip(" '\"")
                url_uzorka_base = raw_url.split('?')[0]
            
            if not url_uzorka_base:
                match = re.search(r'background-image:\s*url\((.*?)\)', style)
                if match:
                    raw_url = match.group(1).strip(" '\"")
                    url_uzorka_base = raw_url.split('?')[0]
            
            full_url_uzorka = urljoin(MAIN_URL, url_uzorka_base) if url_uzorka_base else None

            if color_name:
                if is_qed_cable:
                    if 'Length' in color_name or re.search(r'\d+(\.\d+)?\s*(m|ft)', color_name, re.IGNORECASE):
                        if not any(l.get('dužina') == color_name for l in colors):
                             colors.append({"dužina": color_name})
                else:
                    sample_url = None
                    
                    if full_url_uzorka:
                        sample_url = get_color_sample_url(full_url_uzorka)
                    else:
                        sample_url = get_svg_fallback(color_name)
                        
                    if sample_url and not any(c.get('boja') == color_name for c in colors):
                        colors.append({"boja": color_name, "url_uzorka": sample_url})

    return colors

# === GLAVNA FUNKCIJA ===
def scrape_product(product_url, logo, coll_name):
    handle = product_url.split('/products/')[-1].split('?')[0]
    logging.debug(f"\n{CODE_VERSION} | OBRAĐUJEM: {handle}")
    data = get_product_json(handle)
    if not data: return None

    title = data.get('title', 'Nepoznato')
    variants = data.get('variants', [])
    
    price = f"${float(variants[0]['price']):,.2f}" if variants and variants[0].get('price') else "$0.00"
    sku = variants[0].get('sku', '') if variants else ''
    title_lower = title.lower()

    is_qed_cable = (
        str(sku).upper().startswith(('QE', 'QED')) or
        ('qed' in title_lower and any(word in title_lower for word in ['cable', 'subwoofer', 'hdmi', 'optical', 'speaker cable', 'interconnect', 'performance', 'reference']))
    )

    product_images = []
    for img in data.get('images', []):
        src = img.get('src', '').split('?')[0]
        full = urljoin("https://cdn.shopify.com", src)
        product_images.append(full)

    try:
        r = scraper.get(product_url, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        opis, specs, cat = parse_html(soup, data, handle)
    except Exception as e:
        logging.error(f"Greška pri dohvatanju HTML-a ili parsiranju: {e}")
        opis, specs, cat = "Opis nedostupan", {}, coll_name
        
    extracted_variants = parse_colors_from_html(soup, is_qed_cable, product_images)
    
    colors = []
    lengths = []
    
    if is_qed_cable:
        lengths = [v for v in extracted_variants if 'dužina' in v]
        if not lengths and variants:
            for v in variants:
                opt = v.get('option1')
                if opt and opt != "Default Title":
                    if not any(l['dužina'] == opt for l in lengths):
                        lengths.append({"dužina": opt})
    else:
        colors = [v for v in extracted_variants if 'boja' in v]
        if not colors and variants:
            for v in variants:
                opt = v.get('option1')
                if opt and opt != "Default Title":
                    sample = get_svg_fallback(opt)
                    if not any(c['boja'] == opt for c in colors):
                        colors.append({"boja": opt, "url_uzorka": sample})

    # === ISPRAVKA KATEGORIJE ===
    category = cat if cat != "Nepoznato" else coll_name
    if category == "All Products":
        # Ako je iz /collections/all, a nema bolje kategorije, koristi "No Category"
        if cat in ["All", "Shop", "Nepoznato", "All Products"]:
            category = "No Category"

    result = {
        "ime_proizvoda": title,
        "sku": sku,
        "brend_logo_url": logo,
        "cena": price,
        "opis": opis,
        "url_proizvoda": product_url,
        "url_slika": product_images,
        "specifikacije": specs,
        "kategorije": category,
        "dodatne_informacije": {
            "tagline": None,
            "dostupne_boje": colors,
            "dostupne_dužine": lengths
        }
    }
    logging.info(f"{CODE_VERSION} | ZAVRŠENO: {title} | Boja: {len(colors)} | Dužina: {len(lengths)} | Spec: {len(specs)} | Kategorija: {category}")
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
            
            product_links = get_links(url, name)
            if not product_links:
                logging.warning(f"Nema linkova u kategoriji: {name}")
                continue

            for p_url, c_name in product_links:
                if count >= MAX_PRODUCTS: break
                h = p_url.split('/products/')[-1].split('?')[0]
                if h in existing_handles: continue
                    
                time.sleep(random.uniform(0.6, 1.3))
                prod = scrape_product(p_url, logo, c_name)
                
                if prod:
                    is_duplicate = any(p.get('sku') == prod['sku'] for p in existing_data + new)
                    if not is_duplicate:
                        new.append(prod)
                        existing_handles.add(h)
                        count += 1

        final = existing_data + new
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(final, f, indent=4, ensure_ascii=False)
        logging.info(f"{CODE_VERSION} | SAČUVANO: {len(final)} proizvoda → {OUTPUT_JSON}")

    except KeyboardInterrupt:
        logging.warning("PREKINUTO OD KORISNIKA")
    except Exception as e:
        logging.critical(f"KRITIČNA GREŠKA: {e}")
    finally:
        shutdown_logging()

if __name__ == "__main__":
    main()
