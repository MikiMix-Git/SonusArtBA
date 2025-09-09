# Ovaj skrejper je napisan u Pythonu i koristi biblioteku 'cloudscraper' da bi zaobišao Cloudflare zaštitu na Denon web stranici.
# Kod radi na principu sekvencijalnog (sinhronog) preuzimanja podataka.
# Prvo dohvaća glavne kategorije, a zatim iterira kroz svaku kategoriju, pronalazi URL-ove proizvoda i prikuplja detaljne informacije.
# Izdvojeni podaci uključuju naziv proizvoda, cenu, opis, URL-ove slika, specifikacije i druge relevantne informacije.
# Svi prikupljeni podaci se čuvaju u datoteci 'denon_products.json' u JSON formatu.

import cloudscraper
import json
from bs4 import BeautifulSoup
from requests.exceptions import RequestException
import os
import time
import random

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
    Pronalazi i vraća rečnik URL-ova svih glavnih kategorija proizvoda na Denon stranici.
    
    Args:
        main_url (str): Glavni URL Denon web stranice.
        
    Returns:
        dict: Rečnik s imenima kategorija kao ključevima i njihovim URL-ovima kao vrednostima.
    """
    categories = {}
    print(f"Traženje kategorija na glavnoj stranici: {main_url}")
    
    # Lista nevažećih kategorija koje treba preskočiti
    invalid_categories = {
        'Featured Products', 'All Featured Products', 'Products', 'All Products',
        '8K', 'Slimline', 'Dolby Atmos', 'Wireless Streaming', 'Home Theater',
        'Hi-Fi', 'AV Receivers & Amplifiers', 'Sound Bars & Home Theater',
        'Headphones', 'Hi-Fi Components', 'Turntables', 'Home Cinema Systems',
        'Wireless Speakers', 'Outlet', 'Special Offers', 'Discover', 'Explore', 'Learn more',
        'Learn About HEOS®', 'Help Me Choose' # Dodato
    }
    
    try:
        response = scraper.get(main_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Novi, precizniji selektori
        category_item_selectors = [
            'header li.category-item a[href*="/category/"]',  # Glavni linkovi u padajućem meniju
            'header li.nav-item-product a[href*="/category/"]' # Linkovi kategorija bez podkategorija
        ]
        
        all_links = []
        for selector in category_item_selectors:
            all_links.extend(soup.select(selector))
        
        if not all_links:
            print("Nema pronađenih kategorija. Proverite selektore.")
            return categories

        for item in all_links:
            category_name = item.select_one('.dropdown-item--title, .nav-link--category-name')
            link_url = item.get('href')

            if not category_name or not link_url:
                continue

            category_name = category_name.get_text(strip=True)
            
            # Provera da li je link validan URL i da li je kategorija u listi za preskakanje
            if category_name in invalid_categories or not (link_url.startswith('http') or link_url.startswith('/en-us/')):
                continue
            
            if not link_url.startswith('http'):
                full_link = "https://www.denon.com" + link_url
            else:
                full_link = link_url
            
            if full_link not in categories.values():
                categories[category_name] = full_link
        
        print(f"Pronađene kategorije: {', '.join(categories.keys())}")
        return categories
    
    except RequestException as e:
        print(f"Greška tokom pristupa web resursu: {e}")
        return categories
    except Exception as e:
        print(f"Došlo je do nepredviđene greške: {e}")
        return categories

def get_brand_logo(main_url):
    """
    Dohvaća URL logotipa brenda sa glavne stranice.
    """
    try:
        response = scraper.get(main_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        logo_element = soup.select_one('a.logo-home img, img[alt="Denon"]')
        
        if logo_element and 'src' in logo_element.attrs:
            logo_src = logo_element['src']
            if not logo_src.startswith('http'):
                full_logo_url = "https://www.denon.com" + logo_src
            else:
                full_logo_url = logo_src
            return full_logo_url
        
    except RequestException as e:
        print(f"Greška prilikom dohvaćanja logotipa: {e}")
        return None
    
    return None

def scrape_product_details(session, product_url, category_name, brand_logo_url):
    """
    Sinhrona funkcija za prikupljanje detalja o proizvodu.
    """
    try:
        print(f"Pristupanje stranici: {product_url}")
        
        response = session.get(product_url)
        response.raise_for_status()
        html = response.text
        soup = BeautifulSoup(html, 'html.parser')

        ratings = "Ocene nedostupne"
        ratings_element = soup.select_one('.yotpo-sr-bottom-line-text')
        if ratings_element:
            ratings = ratings_element.get_text(strip=True)

        top_features = []
        top_features_elements = soup.select('ul.top-features li, ul.features-list li')
        for li in top_features_elements:
            top_features.append(li.get_text(strip=True))

        name = "Naziv nedostupan"
        name_selectors = ['h1.product-hero__product-name', 'h1.product-name', 'h1.product-hero__title', 'div.product-hero__header h1']
        for selector in name_selectors:
            name_element = soup.select_one(selector)
            if name_element:
                name = name_element.get_text(strip=True)
                break
        
        description = "Opis nije dostupan"
        description_selectors = ['div.short-description p', 'div.product-hero__product-description p']
        for selector in description_selectors:
            description_element = soup.select_one(selector)
            if description_element:
                description = description_element.get_text(strip=True)
                break
        
        tagline = "Tagline nedostupan"
        tagline_selectors = ['p.product-tagline', 'div.product-tagline']
        for selector in tagline_selectors:
            tagline_element = soup.select_one(selector)
            if tagline_element:
                tagline = tagline_element.get_text(strip=True)
                break

        product_price_selector = 'div.price .value'
        price_element = soup.select_one(product_price_selector)
        
        price = "Cena nije definisana"
        if price_element:
            price = price_element.get_text(strip=True)
        
        image_urls = []
        image_elements = soup.select('div.product-hero__image-wrapper img, picture img.img-fluid, .product-gallery-item img, div.product-image-container img')
        for img_element in image_elements:
            image_src = img_element.get('src')
            if image_src:
                if not image_src.startswith('http'):
                    full_url = "https://www.denon.com" + image_src
                else:
                    full_url = image_src
                
                if full_url not in image_urls:
                    image_urls.append(full_url)
        
        if not image_urls:
            image_urls.append("URL slike nedostupan")

        specs_item_selector = 'ul.specifications-list li, table.technical-specifications tbody tr'
        spec_name_selector = 'span.name, td:nth-child(1)'
        spec_value_selector = 'span.value, td:nth-child(2)'
        
        specifications = {}
        spec_items = soup.select(specs_item_selector)
        for item in spec_items:
            name_element = item.select_one(spec_name_selector)
            value_element = item.select_one(spec_value_selector)
            if name_element and value_element:
                spec_name = name_element.get_text(strip=True)
                spec_value = value_element.get_text(strip=True)
                specifications[spec_name] = spec_value
        
        features = []
        feature_blocks = soup.select('div.pdp-animated-feature, div.product-feature-block')
        for block in feature_blocks:
            feature_title_element = block.select_one('a.btn-link, h2, h3')
            feature_desc_element = block.select_one('p.p-regular, p')
            if feature_title_element and feature_desc_element:
                feature_title = feature_title_element.get_text(strip=True)
                feature_desc = feature_desc_element.get_text(strip=True)
                features.append({
                    "naslov": feature_title,
                    "opis": feature_desc
                })

        product_id = product_url.split('/')[-1].replace('.html', '').replace('?dwvar_', '')

        return {
            "ime_proizvoda": name,
            "brend_logo_url": brand_logo_url,
            "cena": price,
            "opis": description,
            "url_proizvoda": product_url,
            "url_slika": list(image_urls),
            "specifikacije": specifications,
            "kategorije": [category_name],
            "dodatne_informacije": {
                "id": product_id,
                "tagline": tagline,
                "funkcije": features,
                "ocjene": ratings,
                "glavne_funkcije": top_features,
            }
        }

    except RequestException as e:
        print(f"Greška tokom pristupa detaljima za {product_url}: {e}")
        return None
    except Exception as e:
        print(f"Došlo je do nepredviđene greške prilikom obrade detalja za {product_url}: {e}")
        return None

def main():
    """
    Glavna sinhrona funkcija za pokretanje procesa preuzimanja podataka.
    """
    main_page_url = "https://www.denon.com/en-us"
    
    brand_logo_url = get_brand_logo(main_page_url)
    if brand_logo_url:
        print(f"Pronađen URL logotipa brenda: {brand_logo_url}")
    else:
        print("Nije pronađen URL logotipa brenda. Nastavlja se bez logotipa.")

    categories = get_categories(main_page_url)

    if not categories:
        print("Nema kategorija za prikupljanje. Prekidanje operacije.")
        return

    all_products_data = []
    scraped_urls = set()
    
    for category_name, list_url in categories.items():
        print(f"\nIniciranje procesa ekstrakcije URL-ova proizvoda za kategoriju: {category_name} sa domena: {list_url}")
        
        try:
            response = scraper.get(list_url)
            response.raise_for_status()
            html = response.text
            soup = BeautifulSoup(html, 'html.parser')
                
            product_links = []
            product_tile_selectors = [
                'a.product-tile-link',
                'div.product-tile-wrapper.plp-tile-wrapper a',
                'div.product-list__item a',
                'div.product-tile a'
            ]

            for selector in product_tile_selectors:
                links = soup.select(selector)
                if links:
                    for link_element in links:
                        href = link_element.get('href')
                        if href and 'product' in href:
                            full_link = "https://www.denon.com" + href if not href.startswith('http') else href
                            product_links.append(full_link)
                    break
            
            if not product_links:
                print(f"Nema pronađenih URL-ova proizvoda u kategoriji '{category_name}'. Proverite selektore.")
                continue
            
            print(f"Identifikovano je {len(set(product_links))} jedinstvenih URL-ova proizvoda.")
            
            for link in set(product_links):
                # Dodajte nasumičnu pauzu
                time.sleep(random.uniform(0.5, 1.5))
                result = scrape_product_details(scraper, link, category_name, brand_logo_url)
                
                if isinstance(result, dict):
                    product_url = result.get('url_proizvoda')
                    if product_url and product_url not in scraped_urls:
                        all_products_data.append(result)
                        scraped_urls.add(product_url)
                    else:
                        print(f"Preskakanje duplog proizvoda: {product_url}")
                else:
                    print(f"Zabeležena greška tokom prikupljanja podataka: {result}")
        
        except RequestException as e:
            print(f"Kritična greška tokom pristupa web resursu za kategoriju {category_name}: {e}")
        except Exception as e:
            print(f"Došlo je do nepredviđene greške: {e}")

    output_filename = "denon_products.json"
    if all_products_data:
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(all_products_data, f, indent=4, ensure_ascii=False)
            
        print(f"\nOperacija uspešno završena. {len(all_products_data)} artikala je zabeleženo u datoteci: {output_filename}.")
    else:
        print("\nNijedan proizvod nije pronađen. Kreiranje datoteke je preskočeno.")
    
    print("Proces preuzimanja podataka je finalizovan.")

if __name__ == "__main__":
    main()