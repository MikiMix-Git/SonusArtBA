import requests
import json
from bs4 import BeautifulSoup
from requests.exceptions import RequestException
import os

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


def scrape_marantz_to_json():
    """
    Prikuplja podatke iz više Marantz kategorija sa zvanične web stranice,
    obrađuje ih i organizuje u JSON strukturu.
    """
    main_page_url = "https://www.marantz.com/en-us"
    categories = get_categories(main_page_url)

    if not categories:
        print("Nema kategorija za prikupljanje. Prekidanje operacije.")
        return

    all_products_data = []

    for category_name, list_url in categories.items():
        print(f"\nIniciranje procesa ekstrakcije podataka za kategoriju: {category_name} sa domena: {list_url}")
        
        product_tile_selectors = [
            'div.product-tile-wrapper.plp-tile-wrapper',
            'div.product-list__item',
            'div.product-tile',
            'a.product-tile-wrapper'
        ]

        try:
            response = requests.get(list_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            product_tiles = []
            for selector in product_tile_selectors:
                product_tiles.extend(soup.select(selector))
                if product_tiles:
                    break
            
            if not product_tiles:
                print(f"Nema pronađenih kataloških artikala u kategoriji '{category_name}'. Proverite selektore radi neusklađenosti.")
                continue

            print(f"Identifikovano je {len(product_tiles)} proizvoda. Nastavlja se s detaljnom ekstrakcijom...")

            for tile in product_tiles:
                link_element = tile.select_one('a.product-tile-link, a')
                
                if not link_element or 'href' not in link_element.attrs:
                    print(f"Upozorenje: Link proizvoda nije pronađen unutar pločice u kategoriji '{category_name}'. Preskačem.")
                    continue

                product_link = "https://www.marantz.com" + link_element['href']
                
                product_data = scrape_product_details(product_link, category_name)
                if product_data:
                    all_products_data.append(product_data)
        
        except RequestException as e:
            print(f"Kritična greška tokom pristupa web resursu: {e}")
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


def scrape_product_details(product_url, category_name):
    """
    Dohvata specifikacije, opis i sve slike sa stranice pojedinog proizvoda,
    formatirajući ih u detaljan rečnik.
    """
    try:
        print(f"Pristupanje stranici: {product_url}")
        response = requests.get(product_url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')

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
        
        # **AŽURIRANO**
        # Čuvamo originalni string cene sa sajta.
        price = "Cena nije definisana"
        if price_element:
            price = price_element.get_text(strip=True)
        
        # Revidirani selektori za pronalaženje svih slika na stranici.
        image_urls = []
        
        # Prvo pokušaj da pronađeš glavnu sliku preko og:image meta taga (najpouzdanije)
        meta_image = soup.select_one('meta[property="og:image"]')
        if meta_image and meta_image.get('content'):
            image_urls.append(meta_image.get('content'))

        # Zatim pokušaj da pronađeš slike iz galerije ili glavnog bloka slika
        image_elements = soup.select('div.product-hero__image-wrapper img, picture img.img-fluid, .product-gallery-item img, div.product-image-container img')
        for img_element in image_elements:
            image_src = img_element.get('src')
            if image_src and image_src not in image_urls:
                if not image_src.startswith('http'):
                    full_url = "https://www.marantz.com" + image_src
                else:
                    full_url = image_src
                image_urls.append(full_url)
        
        if not image_urls:
            image_urls.append("URL slike nedostupan")

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
            "images": image_urls,
            "description": description,
            "specifications": specifications,
            "features": features,
            "link": product_url,
            "categories": [category_name]
        }

    except RequestException as e:
        print(f"Greška tokom pristupa detaljima za {product_url}: {e}")
        return None
    except Exception as e:
        print(f"Došlo je do greške prilikom obrade detalja za {product_url}: {e}")
        return None

if __name__ == "__main__":
    scrape_marantz_to_json()
