import requests
import json
from bs4 import BeautifulSoup
from requests.exceptions import RequestException
import os

def get_categories(main_url):
    """
    Pronalazi i vraća rječnik URL-ova svih glavnih kategorija proizvoda na Marantz stranici.
    
    Args:
        main_url (str): Glavni URL Marantz web stranice (npr. 'https://www.marantz.com/en-us').
        
    Returns:
        dict: Rječnik s imenima kategorija kao ključevima i njihovim URL-ovima kao vrijednostima.
    """
    categories = {}
    print(f"Traženje kategorija na glavnoj stranici: {main_url}")
    
    try:
        response = requests.get(main_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Ažurirani selektor koji je općenitiji i pouzdaniji.
        # Traži sve linkove unutar 'header' taga koji sadrže '/category/' u svom href atributu.
        category_item_selector = 'header a[href*="/category/"]'
        
        category_items = soup.select(category_item_selector)
        
        if not category_items:
            print("Nema pronađenih kategorija. Provjerite selektore.")
            return categories

        for item in category_items:
            category_name = item.get_text(strip=True)
            link_url = item['href']
            
            # Provjera da li link vodi na stranicu s kategorijom proizvoda i sprečavanje duplikata.
            if '/category/' in link_url and category_name not in categories:
                full_link = "https://www.marantz.com" + link_url
                categories[category_name] = full_link
        
        print(f"Pronađene kategorije: {', '.join(categories.keys())}")
        return categories
    
    except RequestException as e:
        print(f"Greška tijekom pristupa web resursu: {e}")
        return categories
    except Exception as e:
        print(f"Došlo je do nepredviđene greške: {e}")
        return categories


def scrape_marantz_to_json():
    """
    Prikuplja podatke iz više Marantz kategorija sa službene web stranice,
    obrađuje ih i organizira u JSON strukturu, oponašajući format Argon Audio.
    """
    main_page_url = "https://www.marantz.com/en-us"
    categories = get_categories(main_page_url)

    if not categories:
        print("Nema kategorija za prikupljanje. Prekidanje operacije.")
        return

    all_products_data = []

    for category_name, list_url in categories.items():
        print(f"\nIniciranje procesa ekstrakcije podataka za kategoriju: {category_name} sa domene: {list_url}")
        
        # Selektori za listu proizvoda na stranici kategorije
        product_tile_selector = 'div.product-tile-wrapper.plp-tile-wrapper'
        product_link_selector = 'a.product-tile-link'

        try:
            response = requests.get(list_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            product_tiles = soup.select(product_tile_selector)
            
            if not product_tiles:
                print(f"Nema pronađenih kataloških artikala u kategoriji '{category_name}'. Provjerite selektore radi neusklađenosti.")
                continue

            print(f"Identificirano je {len(product_tiles)} proizvoda. Nastavlja se s detaljnom ekstrakcijom...")

            for tile in product_tiles:
                link_element = tile.select_one(product_link_selector)
                if not link_element or 'href' not in link_element.attrs:
                    print(f"Upozorenje: Link proizvoda nije pronađen unutar pločice u kategoriji '{category_name}'. Preskačem.")
                    continue

                product_link = "https://www.marantz.com" + link_element['href']
                
                # Prikupljanje sveobuhvatnih detalja sa stranice svakog proizvoda
                product_data = scrape_product_details(product_link, category_name)
                if product_data:
                    all_products_data.append(product_data)
        
        except RequestException as e:
            print(f"Kritična greška tijekom pristupa web resursu: {e}")
        except Exception as e:
            print(f"Došlo je do nepredviđene greške: {e}")
    
    # Perzistentno pohranjivanje podataka u JSON format
    output_filename = "marantz_all_products.json"
    if all_products_data:
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(all_products_data, f, indent=4, ensure_ascii=False)
            
        print(f"\nOperacija uspješno završena. {len(all_products_data)} artikala je zabilježeno u datoteci: {output_filename}.")
    else:
        print("\nNijedan proizvod nije pronađen. Kreiranje datoteke je preskočeno.")
    
    print("Proces preuzimanja podataka je finaliziran.")


def scrape_product_details(product_url, category_name):
    """
    Dohvaća specifikacije i opis sa stranice pojedinog proizvoda,
    formatirajući ih u detaljan rječnik koji odgovara Argon Audio stilu.
    """
    try:
        print(f"Pristupanje stranici: {product_url}")
        response = requests.get(product_url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')

        # Pokušava pronaći naziv proizvoda koristeći više selektora radi pouzdanosti.
        name = "Naziv nedostupan"
        name_selectors = ['h1.product-hero__product-name', 'h1.product-name', 'h1.product-hero__title', 'div.product-hero__header h1']
        for selector in name_selectors:
            name_element = soup.select_one(selector)
            if name_element:
                name = name_element.get_text(strip=True)
                break
        
        # Ažurirani selektori za opis proizvoda
        description = "Opis nije dostupan"
        description_selectors = ['p.short-description', 'div.product-hero__product-description p']
        for selector in description_selectors:
            description_element = soup.select_one(selector)
            if description_element:
                description = description_element.get_text(strip=True)
                break
        
        # Ažurirani selektori za tagline proizvoda
        tagline = "Tagline nedostupan"
        tagline_selectors = ['p.product-tagline', 'div.product-tagline']
        for selector in tagline_selectors:
            tagline_element = soup.select_one(selector)
            if tagline_element:
                tagline = tagline_element.get_text(strip=True)
                break
        
        product_price_selector = 'div.price .value'
        
        # Ažurirani selektori za sliku
        image_url = "URL slike nedostupan"
        image_selectors = ['div.product-hero__image-wrapper img', 'picture img.img-fluid']
        for selector in image_selectors:
            image_element = soup.select_one(selector)
            if image_element and 'src' in image_element.attrs:
                image_url = "https://www.marantz.com" + image_element['src']
                break
        
        # Ažurirani selektori za specifikacije
        specs_item_selector = 'ul.specifications-list li'
        spec_name_selector = 'span.name'
        spec_value_selector = 'span.value'
        
        price_element = soup.select_one(product_price_selector)
        price = price_element.get_text(strip=True) if price_element else "Cijena nije definirana"
        
        # Prikupljanje specifikacija s ažuriranim selektorima
        specifications = {}
        spec_items = soup.select(specs_item_selector)
        for item in spec_items:
            name_element = item.select_one(spec_name_selector)
            value_element = item.select_one(spec_value_selector)
            if name_element and value_element:
                spec_name = name_element.get_text(strip=True)
                spec_value = value_element.get_text(strip=True)
                specifications[spec_name] = spec_value
        
        # Generisanje jedinstvenog ID-a (može biti i naprednije)
        product_id = product_url.split('/')[-1].replace('.html', '')

        # Strukturiranje izlaznih podataka za usklađenost s Argon Audio stilom
        return {
            "id": product_id,
            "name": name,
            "tagline": tagline,
            "price": price,
            "image": image_url,
            "description": description,
            "specifications": specifications,
            "link": product_url,
            "categories": [category_name]
        }

    except RequestException as e:
        print(f"Greška tijekom pristupa detaljima za {product_url}: {e}")
        return None
    except Exception as e:
        print(f"Došlo je do greške prilikom obrade detalja za {product_url}: {e}")
        return None

if __name__ == "__main__":
    scrape_marantz_to_json()
