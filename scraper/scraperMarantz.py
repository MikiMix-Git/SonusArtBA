import requests
import json
from bs4 import BeautifulSoup
from requests.exceptions import RequestException

def scrape_marantz_to_json():
    """
    Prikuplja podatke o Marantz pojačivačima sa službene web stranice,
    obrađuje ih i organizira u JSON strukturu, oponašajući format Argon Audio.
    """
    list_url = "https://www.marantz.com/en-us/category/amplifiers/"
    
    # Selektori za listu proizvoda na stranici kategorije
    product_tile_selector = 'div.product-tile-wrapper.plp-tile-wrapper'
    product_link_selector = 'a.product-tile-link'

    all_products_data = []

    print(f"Iniciranje procesa ekstrakcije podataka sa domene: {list_url}")
    
    try:
        response = requests.get(list_url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        product_tiles = soup.select(product_tile_selector)
        
        if not product_tiles:
            print("Nema pronađenih kataloških artikala. Provjerite selektore radi neusklađenosti.")
            return

        print(f"Identificirano je {len(product_tiles)} proizvoda. Nastavlja se s detaljnom ekstrakcijom...")

        for tile in product_tiles:
            link_element = tile.select_one(product_link_selector)
            if not link_element or 'href' not in link_element.attrs:
                print("Upozorenje: Link proizvoda nije pronađen unutar pločice. Preskačem.")
                continue

            product_link = "https://www.marantz.com" + link_element['href']
            
            # Prikupljanje sveobuhvatnih detalja sa stranice svakog proizvoda
            product_data = scrape_product_details(product_link)
            if product_data:
                all_products_data.append(product_data)
        
        # Konačna JSON struktura je direktan niz proizvoda
        output_data = all_products_data

        # Perzistentno pohranjivanje podataka u JSON format
        output_filename = "marantz_products.json"
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=4, ensure_ascii=False)
            
        print(f"\nOperacija uspješno završena. {len(all_products_data)} artikala je zabilježeno u datoteci: {output_filename}.")

    except RequestException as e:
        print(f"Kritična greška tijekom pristupa web resursu: {e}")
    except Exception as e:
        print(f"Došlo je do nepredviđene greške: {e}")
    finally:
        print("Proces preuzimanja podataka je finaliziran.")


def scrape_product_details(product_url):
    """
    Dohvaća specifikacije i opis sa stranice pojedinog proizvoda,
    formatirajući ih u detaljan rječnik koji odgovara Argon Audio stilu.
    """
    try:
        print(f"Pristupanje stranici: {product_url}")
        response = requests.get(product_url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')

        # Potvrđeni selektori za stranicu s detaljima proizvoda
        product_name_selector = 'h1.product-hero__product-name'
        product_description_selector = 'div.product-hero__product-description p'
        product_price_selector = 'div.price .value'
        product_image_selector = 'div.product-hero__image-wrapper img'
        product_tagline_selector = 'div.product-tagline'
        
        # Ažurirani selektori za specifikacije
        specs_item_selector = 'ul.specifications-list li'
        spec_name_selector = 'span.name'
        spec_value_selector = 'span.value'

        name_element = soup.select_one(product_name_selector)
        name = name_element.get_text(strip=True) if name_element else "Naziv nedostupan"
        
        price_element = soup.select_one(product_price_selector)
        price = price_element.get_text(strip=True) if price_element else "Cijena nije definirana"
        
        description_elements = soup.select(product_description_selector)
        description = " ".join([p.get_text(strip=True) for p in description_elements]) if description_elements else "Opis nije dostupan"
        
        image_element = soup.select_one(product_image_selector)
        image_url = "https://www.marantz.com" + image_element['src'] if image_element and 'src' in image_element.attrs else "URL slike nedostupan"
        
        tagline_element = soup.select_one(product_tagline_selector)
        tagline = tagline_element.get_text(strip=True) if tagline_element else "Tagline nedostupan"

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
            "categories": ["Amplifiers"]
        }

    except RequestException as e:
        print(f"Greška tijekom pristupa detaljima za {product_url}: {e}")
        return None
    except Exception as e:
        print(f"Došlo je do greške prilikom obrade detalja za {product_url}: {e}")
        return None

if __name__ == "__main__":
    scrape_marantz_to_json()
