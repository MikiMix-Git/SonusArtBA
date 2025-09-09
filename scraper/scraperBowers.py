# Ovaj skrejper je napisan u Pythonu i koristi biblioteku 'cloudscraper' da bi zaobišao Cloudflare zaštitu.
# Kod radi na principu sekvencijalnog (sinhronog) preuzimanja podataka.
# Prvo dohvaća glavne kategorije, a zatim iterira kroz svaku kategoriju, pronalazi URL-ove proizvoda i prikuplja detaljne informacije.
# Izdvojeni podaci uključuju naziv proizvoda, cenu, opis, URL-ove slika, specifikacije i druge relevantne informacije.
# Svi prikupljeni podaci se čuvaju u datoteci 'bowers_wilkins_products.json' u JSON formatu.

import cloudscraper
import json
from bs4 import BeautifulSoup
from requests.exceptions import RequestException
import os
import time
import random
import re
from urllib.parse import urljoin, urlparse

# Kreiranje jedne, sinhrone cloudscraper instance
scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'mobile': False
    }
)

def get_categories(main_url):
    """
    Pronalazi i vraća rečnik URL-ova svih glavnih kategorija proizvoda na stranici.
    
    Args:
        main_url (str): Glavni URL web stranice.
        
    Returns:
        dict: Rečnik s imenima kategorija kao ključevima i njihovim URL-ovima kao vrednostima.
    """
    categories = {}
    try:
        response = scraper.get(main_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Ažurirani selektor za pronalaženje glavnih kategorija iz glavnog menija
        category_links = soup.select('ul.main-menu-list > li.main-menu-item > a')
        
        # Dodavanje linkova za prodaju i outlet, koji se ne nalaze u glavnom meniju
        special_links_selector = 'a[href*="/category/outlet/"], a[href*="/category/recertified/"], a[href*="/category/sale/"], a[href*="/category/archive/"]'
        
        special_links = soup.select(special_links_selector)
        
        all_links = category_links + special_links

        for link in all_links:
            href = link.get('href')
            if href:
                full_url = urljoin(main_url, href)
                
                category_name = link.text.strip()
                if category_name in categories:
                    continue
                
                if href.startswith('/'):
                    full_url = urljoin(main_url, href)
                else:
                    full_url = href
                categories[category_name] = full_url
                
    except RequestException as e:
        print(f"Kritična greška prilikom pristupa web resursu: {e}")
    except Exception as e:
        print(f"Došlo je do nepredviđene greške: {e}")
        
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
        
        # Selektor za pronalaženje linkova proizvoda
        product_elements = soup.select('a[href*="/product/"]')
        
        for product in product_elements:
            href = product.get('href')
            if href:
                full_url = urljoin(category_url, href)
                product_links.append(full_url)
                
    except RequestException as e:
        print(f"Greška prilikom pristupa kategoriji {category_url}: {e}")
    except Exception as e:
        print(f"Nije pronađen nijedan link za proizvod u kategoriji: {urlparse(category_url).path.split('/')[-2]}")
        
    return product_links

def scrape_product_details(scraper, product_url, brand_logo_url):
    """
    Prikuplja detaljne informacije o proizvodu.
    """
    try:
        response = scraper.get(product_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Izdvajanje podataka
        product_title_tag = soup.find('h1', class_='product-name')
        product_title = product_title_tag.text.strip() if product_title_tag else 'N/A'

        description_tag = soup.find('div', class_='product-short-description')
        description = description_tag.text.strip() if description_tag else 'N/A'

        price = 'N/A'
        price_tag = soup.find('div', class_='price')
        if price_tag:
            price_text = price_tag.text
            # Regularni izraz za pronalaženje cijene, uključujući i opcionalni "/ pair"
            match = re.search(r'(\$\d{1,3}(?:,\d{3})*(?:\.\d+)?)(?:\s*/\s*pair)?', price_text)
            if match:
                price = match.group(1).strip()
        
        # Ažurirani selektor za URL-ove slika
        image_urls = [img.get('data-pswp-src') for img in soup.select('div.pswp-gallery a[data-pswp-src]')]
        
        specifications = {}
        spec_section = soup.find('div', class_='specifications')
        if spec_section:
            spec_rows = spec_section.find_all('div', class_='specs-item')
            for row in spec_rows:
                key_tag = row.find('div', class_='specs-item-title')
                value_tag = row.find('div', class_='specs-item-info')
                if key_tag and value_tag:
                    key = key_tag.text.strip()
                    value = value_tag.text.strip()
                    specifications[key] = value

        # Izdvajanje kategorije iz URL-a proizvoda
        parsed_url = urlparse(product_url)
        path_segments = parsed_url.path.split('/')
        try:
            product_index = path_segments.index('product')
            category_slug = path_segments[product_index + 1]
        except (ValueError, IndexError):
            category_slug = 'N/A'

        return {
            "Brend": "Bowers & Wilkins",
            "Brend Logo URL": brand_logo_url,
            "Naziv proizvoda": product_title,
            "Kategorija": category_slug,
            "Cena": price,
            "Opis": description,
            "Slike": image_urls,
            "Specifikacije": specifications,
            "URL proizvoda": product_url
        }
        
    except RequestException as e:
        return f"Greška prilikom prikupljanja podataka za {product_url}: {e}"
    except Exception as e:
        return f"Došlo je do nepredviđene greške za {product_url}: {e}"

def main():
    main_url = "https://www.bowerswilkins.com/en-us/"
    brand_logo_url = "https://www.bowerswilkins.com/on/demandware.static/Sites-bowers_us-Site/-/en_US/v1757417695243/images/icons/BW-logo-B-W-L.svg"
    
    print("Pronalazim kategorije...")
    categories = get_categories(main_url)
    
    if not categories:
        print("Nije pronađena nijedna kategorija. Proverite URL ili selektore.")
        return
        
    print(f"Pronađeno {len(categories)} kategorija. Pokrećem prikupljanje podataka...")

    all_products_data = []
    scraped_urls = set()

    for category_name, category_url in categories.items():
        print(f"\nObrađujem kategoriju: {category_name} ({category_url})")
        
        product_links = get_product_links_from_category(category_url)

        if not product_links:
            print(f"Nije pronađen nijedan link za proizvod u kategoriji: {category_name}")
            continue

        print(f"Pronađeno {len(product_links)} proizvoda. Prikupljam detalje...")
        
        for link in product_links:
            try:
                time.sleep(random.uniform(0.5, 1.5))
                result = scrape_product_details(scraper, link, brand_logo_url)
                
                if isinstance(result, dict):
                    product_url = result.get('URL proizvoda')
                    if product_url and product_url not in scraped_urls:
                        all_products_data.append(result)
                        scraped_urls.add(product_url)
                    else:
                        print(f"Preskakanje duplog proizvoda: {product_url}")
                else:
                    print(f"Zabeležena greška tokom prikupljanja podataka: {result}")
            
            except Exception as e:
                print(f"Došlo je do nepredviđene greške: {e}")

    output_filename = "bowers_wilkins_products.json"
    if all_products_data:
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(all_products_data, f, indent=4, ensure_ascii=False)
            
        print(f"\nOperacija uspešno završena. {len(all_products_data)} artikala je zabeleženo u datoteci: {output_filename}.")
    else:
        print("\nOperacija završena. Nije prikupljen nijedan artikal.")

if __name__ == "__main__":
    main()
