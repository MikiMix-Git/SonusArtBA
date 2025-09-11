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

def clean_price(price_string):
    """
    Čisti string cene i konvertuje ga u float, uklanjajući $ i ,.
    """
    if price_string:
        # Uklonite sve što nije cifra, tačka ili znak za par/komad
        cleaned_price = re.sub(r'[^\d.,/]+', '', price_string)
        # Zamena zareza tačkom za decimale
        cleaned_price = cleaned_price.replace(',', '')
        # Izolujte cenu pre znaka /
        if '/' in cleaned_price:
            cleaned_price = cleaned_price.split('/')[0].strip()
        # Proverite da li je string prazan nakon čišćenja
        if cleaned_price.strip():
            return float(cleaned_price)
    return None

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
        product_title = product_title_tag.text.strip() if product_title_tag else None

        tagline_tag = soup.find('p', class_='product-tagline')
        tagline = tagline_tag.text.strip() if tagline_tag else None

        # --- AŽURIRANO: Prikupljanje opisa pomoću više selektora ---
        description = None
        description_selectors = [
            'div.product-short-description',
            'div.short-description p',
            'div.product-description-container p',
            'div.product-details-intro__description p',
            'div.product-details__summary p'
        ]
        
        for selector in description_selectors:
            description_tag = soup.select_one(selector)
            if description_tag:
                description = description_tag.text.strip()
                break
        # --- KRAJ AŽURIRANJA ---

        price = None
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

        # --- AŽURIRANO: Izdvajanje dostupnih boja i URL-ova uzoraka ---
        available_colors = []
        color_swatches = soup.select('span.color-swatch') # Selektuje roditeljski span
        for swatch_span in color_swatches:
            color_name_tag = swatch_span.select_one('.swatch-value')
            color_image_tag = swatch_span.select_one('.swatch.color-value')
            
            color_name = color_name_tag.text.strip() if color_name_tag else None
            color_url = None
            
            if color_image_tag and 'style' in color_image_tag.attrs:
                style_attr = color_image_tag['style']
                # Koristite regularni izraz za pronalaženje URL-a unutar atributa stila
                match = re.search(r'url\((.*?)\)', style_attr)
                if match:
                    relative_url = match.group(1).replace('"', '').replace("'", '')
                    # Pretvorite relativni URL u apsolutni
                    color_url = urljoin(product_url, relative_url)
            
            if color_name:
                available_colors.append({
                    "boja": color_name,
                    "url_uzorka": color_url
                })
        # --- KRAJ AŽURIRANJA ---

        # Izdvajanje dostupnih kvaliteta
        available_qualities = []
        quality_options = soup.select('div[data-attr="quality"] select option')
        for option in quality_options:
            quality = option.text.strip()
            if quality and quality != 'Select Quality':
                available_qualities.append(quality)
        
        # Izdvajanje pogodnosti
        benefits = {}
        benefit_items = soup.select('ul.pdp-breadcrumb-features li')
        for item in benefit_items:
            title_tag = item.find('span', class_='pdp-breadcrumb-features--title')
            link_tag = item.find('a')
            if title_tag and link_tag:
                title = title_tag.text.strip()
                link = link_tag.get('href')
                if title and link:
                    benefits[title] = urljoin(product_url, link)

        # Izdvajanje kategorije iz URL-a proizvoda
        parsed_url = urlparse(product_url)
        path_segments = parsed_url.path.split('/')
        try:
            product_index = path_segments.index('product')
            category_slug = path_segments[product_index + 1]
        except (ValueError, IndexError):
            category_slug = 'N/A'

        return {
            "ime_proizvoda": product_title,
            "brend_logo_url": brand_logo_url,
            "cena": price,
            "opis": description,
            "url_proizvoda": product_url,
            "url_slika": image_urls,
            "specifikacije": specifications,
            "kategorije": category_slug,
            "dodatne_informacije": {
                "tagline": tagline,
                "ociscena_cena": clean_price(price),
                "dostupne_boje": available_colors,
                "dostupni_kvaliteti": available_qualities,
                "pogodnosti": benefits
            }
        }
        
    except RequestException as e:
        return f"Greška prilikom prikupljanja podataka za {product_url}: {e}"
    except Exception as e:
        return f"Došlo je do nepredviđene greške za {product_url}: {e}"

def get_brand_logo_url(main_url):
    """
    Dohvaća i vraća apsolutni URL logotipa brenda sa početne stranice.
    """
    try:
        response = scraper.get(main_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Pronalazimo <img> tag sa alt atributom 'Bowers & Wilkins'
        logo_img = soup.find('img', alt='Bowers & Wilkins')
        if logo_img and logo_img.get('src'):
            # Spajamo relativnu putanju sa osnovnim URL-om sajta da bismo dobili apsolutnu
            relative_logo_url = logo_img['src']
            return urljoin(main_url, relative_logo_url)
        
    except RequestException as e:
        print(f"Greška pri dohvaćanju URL-a logotipa: {e}")
        return None
    except Exception as e:
        print(f"Došlo je do nepredviđene greške: {e}")
        return None

def main():
    main_url = "https://www.bowerswilkins.com/en-us/"
    
    # Sada dinamički dohvaćamo URL logotipa umesto da ga hardkodiramo
    brand_logo_url = get_brand_logo_url(main_url)
    if not brand_logo_url:
        print("Upozorenje: Nije pronađen URL logotipa brenda. Skripta će nastaviti bez logotipa.")
    
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
                    product_url = result.get('url_proizvoda')
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
