# Ovaj skrejper je napisan u Pythonu i koristi biblioteku 'cloudscraper' da bi zaobišao Cloudflare zaštitu.
# NOVO U V3.3: Preimenovana 'cena_raw' u 'cena' i potpuno uklonjena 'cena_float' i prateća funkcija za čišćenje cene.
# NOVO U V3.2: Uklonjena su polja 'dostupni_kvaliteti' i 'pogodnosti' iz finalnog izlaznog rečnika.

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
from urllib.parse import urljoin, urlparse

# --- KONSTANTE ZA VERZIJU I LOGOVANJE ---
CODE_VERSION = "V3.3" # AŽURIRANO NA V3.3
LOG_FILE = "scraper.log"
OUTPUT_FILENAME = "bowers_wilkins_products.json"

# Kreiranje jedne, sinhrone cloudscraper instance
scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'mobile': False
    }
)

def setup_logging():
    """
    Konfiguriše standardni Python modul za logovanje.
    Postavlja logovanje i u fajl (scraper.log) i na konzolu.
    """
    logger = logging.getLogger()
    # Podesite root logger na INFO nivo
    logger.setLevel(logging.INFO) 
    
    # Uklanjanje postojećih handlera da bi se sprečilo dupliranje izlaza
    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [V{}] %(message)s'.format(CODE_VERSION), 
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 1. Fajl Handler (Za čuvanje logova u datoteku)
    file_handler = logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # 2. Stream Handler (Za prikaz logova u konzoli)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.INFO)
    logger.addHandler(stream_handler)
    
    logging.info(f"--- Logovanje započeto (Verzija: {CODE_VERSION}) ---")
    
    return logger

def shutdown_logging(logger):
    """
    Pravilno zatvara sve handlere povezane sa logerom.
    """
    logging.info(f"--- Logovanje završeno (Fajl: {LOG_FILE}) ---")
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)

def load_existing_data(filename=OUTPUT_FILENAME):
    """
    Učitava postojeće podatke iz JSON fajla.
    """
    existing_data = []
    existing_urls = set()
    incomplete_urls = set()
    
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                logging.info(f"Uspešno učitano {len(existing_data)} postojećih artikala iz {filename}.")
                
                for item in existing_data:
                    url = item.get('url_proizvoda')
                    if url:
                        existing_urls.add(url)
                        # Provera da li su podaci nekompletni (minimalno 3 specifikacije)
                        is_incomplete = (
                            not item.get('opis') or 
                            not item.get('specifikacije') or 
                            len(item.get('specifikacije', {})) < 3
                        )
                        
                        if is_incomplete:
                            incomplete_urls.add(url)
                            logging.debug(f"Identifikovan nekompletan URL (za ponovno skrejpovanje): {url}")

        except json.JSONDecodeError:
            logging.error(f"Greška prilikom parsiranja JSON fajla: {filename}. Počinjem ponovno skrejpovanje svih podataka.")
            existing_data = []
        except Exception as e:
            logging.error(f"Neuspešno učitavanje fajla {filename}: {e}.")
            existing_data = []
            
    return existing_data, existing_urls, incomplete_urls

def get_categories(main_url):
    """
    Pronalazi i vraća rečnik URL-ova svih glavnih kategorija proizvoda na stranici.
    """
    logging.info("Pokretanje dohvatanja kategorija sa glavne stranice.")
    categories = {}
    try:
        response = scraper.get(main_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Ciljanje navigacionih linkova za kategorije
        category_links = soup.select('header nav a[href*="/category/"], header nav a[href*="/products/"]')
        # Ciljanje specijalnih kategorija (outlet, recertified, sale, archive)
        special_links_selector = 'a[href*="/category/outlet/"], a[href*="/category/recertified/"], a[href*="/category/sale/"], a[href*="/category/archive/"]'
        special_links = soup.select(special_links_selector)
        all_links = category_links + special_links

        for link in all_links:
            href = link.get('href')
            if href:
                full_url = urljoin(main_url, href)
                category_name = link.text.strip()
                
                if not category_name or category_name.lower() in ["products", "home", "discover"]:
                    continue
                
                # Provera da li link već postoji da bi se izbeglo dupliranje
                if category_name in categories:
                    continue
                    
                if href.startswith('/'):
                    full_url = urljoin(main_url, href)
                else:
                    full_url = href
                categories[category_name] = full_url
                
    except RequestException as e:
        logging.error(f"Kritična greška prilikom pristupa web resursu {main_url}: {e}")
    except Exception as e:
        logging.error(f"Došlo je do nepredviđene greške prilikom parsiranja kategorija: {e}")
        
    return categories

def get_product_links_from_category(category_url):
    """
    Pronalazi i vraća listu URL-ova proizvoda unutar date kategorije.
    """
    product_links = []
    try:
        response = scraper.get(category_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Ciljanje linkova koji sadrže '/product/' u href atributu
        product_elements = soup.select('a[href*="/product/"]')
        
        for product in product_elements:
            href = product.get('href')
            if href:
                full_url = urljoin(category_url, href)
                product_links.append(full_url)
                
    except RequestException as e:
        logging.error(f"Greška prilikom pristupa kategoriji {category_url}: {e}")
    except Exception as e:
        # Prikaz naziva kategorije u slučaju greške
        category_name = urlparse(category_url).path.split('/')[-2]
        logging.warning(f"Nije pronađen nijedan link za proizvod u kategoriji: {category_name}")
        
    return product_links

# Uklonjena je funkcija clean_price, jer konverzija u float više nije potrebna.

def scrape_product_details(scraper, product_url, brand_logo_url):
    """
    Prikuplja detaljne informacije o proizvodu.
    """
    try:
        response = scraper.get(product_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        product_title_tag = soup.find('h1', class_='product-name')
        product_title = product_title_tag.text.strip() if product_title_tag else None

        tagline_tag = soup.find('p', class_='product-tagline')
        tagline = tagline_tag.text.strip() if tagline_tag else None

        sku = None
        # Prošireni selektori za SKU (Model Number, Product Meta)
        sku_tag = soup.select_one('div.product-model-number, div.product-meta-item:has(strong:-soup-contains("Model")) span.product-meta-value, span.model-number')
        if sku_tag:
            sku = sku_tag.text.strip()
        
        description = None
        # Prošireni selektori za opis
        description_selectors = [
            'div.product-short-description', 'div.short-description p', 'div.product-description-container p',
            'div.product-details-intro__description p', 'div.product-details__summary p',
            'div.product-features-container .product-features-intro p', 'div[data-component-name="ProductShortDescription"] p'
        ]
        
        for selector in description_selectors:
            description_tag = soup.select_one(selector)
            if description_tag:
                description = description_tag.text.strip()
                break
        
        price_text = None
        # Prošireni selektori za cenu
        price_selectors = ['div.price', 'span.price-new', 'span.product-price', 'div[data-price-value]', '.price-value']

        for selector in price_selectors:
            price_tag = soup.select_one(selector)
            if price_tag:
                if 'data-price-value' in price_tag.attrs:
                    price_text = price_tag['data-price-value']
                else:
                    price_text = price_tag.get_text(strip=True)
                break
        
        cena = price_text # Direktno koristimo sirovu cenu

        # Prikupljanje URL-ova slika
        image_urls = [urljoin(product_url, img.get('data-pswp-src'))
                      for img in soup.select('div.pswp-gallery a[data-pswp-src]')]
        
        # --- LOGIKA ZA SPECIFIKACIJE (V3.3 - Prikuplja sve sekcije) ---
        specifications = {}
        
        # Prošireni selektori za kontejner specifikacija
        spec_containers = soup.select(
            'div.specifications-wrapper, div.specifications, div.product-specifications, table.spec-table, ul.specs-list, '
            'div.tech-specifications, div.product-features, div.spec-group, dl.tech-specs-list, '
            'div.pdp-specifications, div.tech-data-block' 
        )
        
        # Selektori za pojedinačne specifikacije
        row_selectors = 'ul.specifications-list > li, div.specs-item, tr, li, div.feature-item, div.spec-row, dt, dd, ' \
                        'div.tech-spec-row, div.spec-detail-item' 
        
        for spec_section in spec_containers:
            spec_rows = spec_section.select(row_selectors)
            
            if not spec_rows:
                 # Backup plan: traži sve unutar sekcije (ako je kontejner pronađen, ali selektori reda nisu radili)
                 spec_rows = spec_section.find_all(['li', 'div', 'tr', 'dt', 'dd']) 

            last_key = None # Koristi se za dt/dd parove
            
            for row in spec_rows:
                key = None
                value = None
                
                # 1. Prioritetno traženje klasa 'name' i 'value' (i specifičnih tehničkih labele)
                key_tag = row.select_one('span.name, .tech-spec-label') 
                value_tag = row.select_one('span.value, .tech-spec-value') 
                
                if key_tag and value_tag:
                    key = key_tag.text.strip()
                    
                    # Bolje rukovanje višestrukim vrednostima unutar value tag-a (npr. dimenzije u više redova)
                    for br in value_tag.find_all(['br', 'br/']): 
                        br.replace_with('[NEWLINE_BR]')
                        
                    value = value_tag.get_text(separator=' ', strip=True) 
                    value = value.replace('[NEWLINE_BR]', '\n').strip()
                    last_key = key # Resetujemo last_key nakon uspešnog pronalaska para

                # 2. Povratak na opšte selektore (postojeća V2.8 logika)
                elif row.name in ['li', 'div', 'tr']:
                    # Prošireni ključevi (naslovi, strong tagovi)
                    key_tag = row.select_one('div.specs-item-title, th, strong, .feature-title, .spec-label, .tech-spec-key, h3, .key-title') 
                    # Proširene vrednosti (td, p tagovi, value tekst klase)
                    value_tag = row.select_one('div.specs-item-info, td, .feature-value, .spec-value, .tech-spec-value, p, .value-text') 
                    
                    if key_tag and value_tag:
                        key = key_tag.text.strip()
                        value = value_tag.get_text(separator=' ', strip=True)
                        last_key = key # Resetujemo last_key nakon uspešnog pronalaska para
                    
                # 3. Logika za DL (Definition List) - DT/DD parove
                elif row.name == 'dt':
                    last_key = row.get_text(strip=True)
                    continue 
                    
                elif row.name == 'dd' and last_key:
                    key = last_key
                    value = row.get_text(separator=' ', strip=True)
                    last_key = None 
                    
                else:
                    continue # Nije pronađen validan par u ovom redu
                
                # Dodavanje u rečnik specifikacija (uz proveru dužine ključa zbog neželjenih tagova)
                if key and value and len(key) < 100:
                    specifications[key] = value
            
        # --- KRAJ LOGIKE ZA SPECIFIKACIJE ---

        # Prikupljanje dostupnih boja
        available_colors = []
        color_swatches = soup.select('span.color-swatch, .product-color-selector .color-item')
        for swatch_span in color_swatches:
            color_name_tag = swatch_span.select_one('.swatch-value')
            color_image_tag = swatch_span.select_one('.swatch.color-value, .color-swatch-image')
            
            color_name = color_name_tag.text.strip() if color_name_tag else swatch_span.get('data-color-name')
            color_url = None
            
            if color_image_tag and 'style' in color_image_tag.attrs:
                style_attr = color_image_tag['style']
                match = re.search(r'url\((.*?)\)', style_attr)
                if match:
                    relative_url = match.group(1).replace('"', '').replace("'", '')
                    color_url = urljoin(product_url, relative_url)
            
            if color_name:
                available_colors.append({"boja": color_name, "url_uzorka": color_url})

        # Ekstrakcija kategorije iz URL-a
        parsed_url = urlparse(product_url)
        path_segments = parsed_url.path.split('/')
        category_slug = 'N/A'
        try:
            # Traži se segment posle '/product/'
            product_index = path_segments.index('product')
            if len(path_segments) > product_index + 1:
                category_slug = path_segments[product_index + 1]
        except ValueError:
            # Ako 'product' nije u URL-u, pokušaj da nađeš 'category'
            try:
                category_index = path_segments.index('category')
                if len(path_segments) > category_index + 1:
                    category_slug = path_segments[category_index + 1]
            except ValueError:
                 category_slug = 'N/A' # Ostaje N/A

        logging.info(f"Uspešno prikupljeni detalji za: {product_title}")

        return {
            "ime_proizvoda": product_title,
            "sku": sku, 
            "brend_logo_url": brand_logo_url,
            "cena": cena, # PROMENJENO: Sada se zove 'cena'
            "opis": description,
            "url_proizvoda": product_url,
            "url_slika": image_urls,
            "specifikacije": specifications,
            "kategorije": category_slug,
            "dodatne_informacije": {
                "tagline": tagline,
                "dostupne_boje": available_colors,
                # Uklonjeno: 'dostupni_kvaliteti' i 'pogodnosti'
            }
        }
        
    except RequestException as e:
        logging.error(f"Greška prilikom prikupljanja podataka za {product_url}: {e}")
        return f"Greška prilikom prikupljanja podataka za {product_url}: {e}"
    except Exception as e:
        logging.error(f"Došlo je do nepredviđene greške za {product_url}: {e}")
        return f"Došlo je do nepredviđene greške za {product_url}: {e}"

def get_brand_logo_url(main_url):
    """
    Dohvaća i vraća apsolutni URL logotipa brenda sa početne stranice.
    """
    try:
        response = scraper.get(main_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Ciljanje img taga u headeru
        logo_img = soup.select_one('header img[alt*="Bowers"], header img.site-logo, header a[aria-label="Home"] img')
        
        if logo_img and logo_img.get('src'):
            relative_logo_url = logo_img['src']
            return urljoin(main_url, relative_logo_url)
        
    except RequestException as e:
        logging.error(f"Greška pri dohvaćanju URL-a logotipa: {e}")
        return None
    except Exception as e:
        logging.error(f"Došlo je do nepredviđene greške pri dohvaćanju logotipa: {e}")
        return None

def main():
    # 1. Postavljanje logovanja
    logger = setup_logging()
    
    try:
        logging.info(f"Skripta započeta (Inkementalno skrejpovanje).")
        main_url = "https://www.bowerswilkins.com/en-us/"
        
        # 2. Učitavanje postojećih podataka i identifikacija URL-ova
        existing_data, existing_urls, incomplete_urls = load_existing_data(OUTPUT_FILENAME)
        
        # Filter: uklanjamo nekompletne proizvode iz postojećih podataka. Oni će biti zamenjeni novim podacima.
        final_products_data = [
            item for item in existing_data 
            if item.get('url_proizvoda') not in incomplete_urls
        ]
        
        newly_scraped_data = []
        scraped_in_this_run = set() 

        brand_logo_url = get_brand_logo_url(main_url)
        
        logging.info("Pronalazim kategorije...")
        categories = get_categories(main_url)
        
        if not categories:
            logging.error("Nije pronađena nijedna kategorija. Izlazak iz skripte.")
            return
            
        logging.info(f"Pronađeno {len(categories)} kategorija.")

        for category_name, category_url in categories.items():
            logging.info(f"\n--- Obrađujem kategoriju: {category_name} ---")
            
            # Pauza za smanjenje opterećenja servera
            time.sleep(random.uniform(1.0, 2.5)) 
            
            product_links = get_product_links_from_category(category_url)

            if not product_links:
                logging.info(f"Nije pronađen nijedan link za proizvod u kategoriji: {category_name}")
                continue

            unique_product_links = list(set(product_links))
            
            logging.info(f"Pronađeno {len(unique_product_links)} jedinstvenih URL-ova za proizvode.")
            
            for link in unique_product_links:
                # Odluka o skrejpovanju: 
                # Skrejpovati ako je URL POTPUNO NOV 
                # ILI ako je bio ranije skrejpovan ali je OZBILJNO NEKOMPLETAN.
                should_scrape = link not in existing_urls or link in incomplete_urls
                
                # Provera da li je već skrejpovan u ovom ciklusu (zbog dupliranih linkova u različitim kategorijama)
                if link in scraped_in_this_run:
                    continue 

                if not should_scrape:
                    logging.info(f"Preskakanje kompletnog i postojećeg proizvoda: {link}")
                    continue
                
                # Pauza pre skrejpovanja detalja proizvoda
                time.sleep(random.uniform(0.5, 1.5))
                
                result = scrape_product_details(scraper, link, brand_logo_url)
                
                if isinstance(result, dict):
                    newly_scraped_data.append(result)
                    scraped_in_this_run.add(link)
                else:
                    logging.warning(f"Zabeležena greška za link: {link}. Nije dodato u nove podatke.")

        # 3. KOMBINOVANJE I ČUVANJE
        final_products_data.extend(newly_scraped_data)

        if final_products_data:
            try:
                with open(OUTPUT_FILENAME, "w", encoding="utf-8") as f:
                    json.dump(final_products_data, f, indent=4, ensure_ascii=False)
                    
                total_scraped = len(final_products_data)
                newly_added = len(newly_scraped_data)
                
                logging.info(f"\nOperacija uspešno završena. {newly_added} novih/ažuriranih artikala je prikupljeno.")
                logging.info(f"Ukupno {total_scraped} artikala je sačuvano u datoteci: {OUTPUT_FILENAME}.")
            except Exception as e:
                logging.critical(f"Kritična greška pri čuvanju JSON datoteke '{OUTPUT_FILENAME}': {e}")
        else:
            logging.warning("\nOperacija završena. Nije prikupljen nijedan artikal.")
            
    finally:
        # 4. Pravilno zatvaranje handlera
        shutdown_logging(logger)

if __name__ == "__main__":
    main()
