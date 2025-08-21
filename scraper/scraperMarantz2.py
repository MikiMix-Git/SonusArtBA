import requests
import json
from bs4 import BeautifulSoup
from requests.exceptions import RequestException
import os
import time
import asyncio
import aiohttp

def get_categories(main_url):
    """
    Pronalazi i vraća rečnik URL-ova svih glavnih kategorija proizvoda na Marantz stranici.
    
    Args:
        main_url (str): Glavni URL Marantz web stranice (npr. 'https://www.marantz.com/en-us').
        
    Returns:
        dict: Rečnik s imenima kategorija kao ključevima i njihovim URL-ovima kao vrednostima.
    """
    categories = {}
    print(f"Traženje kategorija na glavnoj stranici: {main_url}")
    
    try:
        response = requests.get(main_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        category_item_selector = 'header a[href*="/category/"]'
        
        category_items = soup.select(category_item_selector)
        
        if not category_items:
            print("Nema pronađenih kategorija. Proverite selektore.")
            return categories

        for item in category_items:
            category_name = item.get_text(strip=True)
            link_url = item['href']
            
            if '/category/' in link_url and category_name not in categories:
                if not link_url.startswith('http'):
                    full_link = "https://www.marantz.com" + link_url
                else:
                    full_link = link_url
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
        response = requests.get(main_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Selektor za Marantz logo
        logo_element = soup.select_one('a.logo-home img, img[alt="Marantz"]')
        
        if logo_element and 'src' in logo_element.attrs:
            logo_src = logo_element['src']
            if not logo_src.startswith('http'):
                full_logo_url = "https://www.marantz.com" + logo_src
            else:
                full_logo_url = logo_src
            return full_logo_url
        
    except RequestException as e:
        print(f"Greška prilikom dohvaćanja logotipa: {e}")
        return None
    
    return None

async def async_scrape_product_details(session, product_url, category_name, brand_logo_url):
    """
    Asinhrona verzija funkcije scrape_product_details.
    """
    try:
        print(f"Pristupanje stranici: {product_url}")
        async with session.get(product_url) as response:
            response.raise_for_status()
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')

            name = "Naziv nedostupan"
            name_selectors = ['h1.product-hero__product-name', 'h1.product-name', 'h1.product-hero__title', 'div.product-hero__header h1']
            for selector in name_selectors:
                name_element = soup.select_one(selector)
                if name_element:
                    name = name_element.get_text(strip=True)
                    break
            
            description = "Opis nije dostupan"
            description_selectors = ['p.short-description', 'div.product-hero__product-description p']
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
            
            image_urls = set()
            meta_image = soup.select_one('meta[property="og:image"]')
            if meta_image and meta_image.get('content'):
                image_urls.add(meta_image.get('content'))

            image_elements = soup.select('div.product-hero__image-wrapper img, picture img.img-fluid, .product-gallery-item img, div.product-image-container img')
            for img_element in image_elements:
                image_src = img_element.get('src')
                if image_src:
                    if not image_src.startswith('http'):
                        full_url = "https://www.marantz.com" + image_src
                    else:
                        full_url = image_src
                    image_urls.add(full_url)
            
            if not image_urls:
                image_urls.add("URL slike nedostupan")

            specs_item_selector = 'ul.specifications-list li'
            spec_name_selector = 'span.name'
            spec_value_selector = 'span.value'
            
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
            feature_blocks = soup.select('div.pdp-animated-feature')
            for block in feature_blocks:
                feature_title_element = block.select_one('a.btn-link')
                feature_desc_element = block.select_one('p.p-regular')
                if feature_title_element and feature_desc_element:
                    feature_title = feature_title_element.get_text(strip=True)
                    feature_desc = feature_desc_element.get_text(strip=True)
                    features.append({
                        "title": feature_title,
                        "description": feature_desc
                    })

            product_id = product_url.split('/')[-1].replace('.html', '').replace('?dwvar_', '')

            return {
                "id": product_id,
                "name": name,
                "tagline": tagline,
                "price": price,
                "images": list(image_urls), # Pretvori set u listu
                "brand_logo": brand_logo_url, # Dodaje logo brenda
                "description": description,
                "specifications": specifications,
                "features": features,
                "link": product_url,
                "categories": [category_name]
            }

    except aiohttp.ClientError as e:
        print(f"Greška tokom asinhronog pristupa detaljima za {product_url}: {e}")
        return None
    except Exception as e:
        print(f"Došlo je do nepredviđene greške prilikom obrade detalja za {product_url}: {e}")
        return None


async def main():
    """
    Glavna asinhrona funkcija za pokretanje procesa preuzimanja podataka.
    """
    main_page_url = "https://www.marantz.com/en-us"
    
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

    # Ograničenje: Requests i BeautifulSoup ne mogu da interpretiraju dinamički sadržaj koji se učitava
    # putem JavaScript-a. Ako web-stranica to koristi za proizvode, ovaj skrejper neće raditi.
    # U tom slučaju, bilo bi potrebno koristiti alat kao što je Selenium.
    
    async with aiohttp.ClientSession() as session:
        for category_name, list_url in categories.items():
            print(f"\nIniciranje procesa ekstrakcije URL-ova proizvoda za kategoriju: {category_name} sa domena: {list_url}")
            
            try:
                async with session.get(list_url) as response:
                    response.raise_for_status()
                    html = await response.text()
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
                                    full_link = "https://www.marantz.com" + href if not href.startswith('http') else href
                                    product_links.append(full_link)
                            break
                    
                    if not product_links:
                        print(f"Nema pronađenih URL-ova proizvoda u kategoriji '{category_name}'. Proverite selektore.")
                        continue
                    
                    print(f"Identifikovano je {len(set(product_links))} jedinstvenih URL-ova proizvoda.")
                    
                    tasks = []
                    for link in set(product_links):
                        tasks.append(async_scrape_product_details(session, link, category_name, brand_logo_url))
                    
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    for result in results:
                        if isinstance(result, dict):
                            all_products_data.append(result)
                        else:
                            print(f"Zabeležena greška tokom prikupljanja podataka: {result}")
            
            except aiohttp.ClientError as e:
                print(f"Kritična greška tokom pristupa web resursu za kategoriju {category_name}: {e}")
            except Exception as e:
                print(f"Došlo je do nepredviđene greške: {e}")

    output_filename = "marantz_all_products.json"
    if all_products_data:
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(all_products_data, f, indent=4, ensure_ascii=False)
            
        print(f"\nOperacija uspešno završena. {len(all_products_data)} artikala je zabeleženo u datoteci: {output_filename}.")
    else:
        print("\nNijedan proizvod nije pronađen. Kreiranje datoteke je preskočeno.")
    
    print("Proces preuzimanja podataka je finalizovan.")

if __name__ == "__main__":
    asyncio.run(main())
