import requests
import json
from bs4 import BeautifulSoup
from requests.exceptions import RequestException
import os
import time
import asyncio
import aiohttp
import random # Uvezeno za nasumične pauze
import re
from urllib.parse import urljoin

def get_categories(main_url):
    """
    Pronalazi i vraća rečnik URL-ova svih glavnih kategorija proizvoda sa Dynaudio stranice.
    
    Args:
        main_url (str): Glavni URL Dynaudio web stranice ('https://dynaudio.com').
        
    Returns:
        dict: Rečnik s imenima kategorija kao ključevima i njihovim URL-ovima kao vrednostima.
    """
    categories = {}
    print(f"Traženje kategorija na glavnoj stranici: {main_url}")
    
    # Ključne reči u URL-u za filtriranje relevantnih kategorija
    category_keywords = ['home-audio', 'professional-audio', 'car-audio', 'custom-install']
    
    try:
        response = requests.get(main_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Novi, robustniji selektor koji pronalazi sve linkove na stranici
        all_links = soup.find_all('a')
        
        if not all_links:
            print("Nema pronađenih navigacionih linkova. Proverite selektore.")
            return categories

        for link in all_links:
            href = link.get('href')
            name = link.get_text(strip=True)
            
            if href and name:
                # Provera da li link pripada nekoj od ključnih kategorija
                for keyword in category_keywords:
                    if keyword in href:
                        full_link = "https://dynaudio.com" + href if href.startswith('/') else href
                        if full_link not in categories.values():
                            categories[name] = full_link
                            break # Prekidamo unutrašnju petlju čim nađemo podudaranje
        
        if not categories:
            print("Nema pronađenih kategorija. Proverite da li su ključne reči u linkovima tačne.")
            return categories

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
    Dohvaća URL logotipa brenda sa glavne stranice koristeći pouzdanije selektore.
    """
    try:
        response = requests.get(main_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Poboljšani, robusniji selektori za Dynaudio logo
        logo_selectors = [
            'img[alt="logo"]',     # Najpouzdaniji selektor baziran na alt atributu
            'div.logo-burger img', # Selektor baziran na vašem primeru
            'a.logo img',          # Originalni selektor (radi na nekim stranicama)
        ]

        logo_element = None
        for selector in logo_selectors:
            logo_element = soup.select_one(selector)
            if logo_element:
                break  # Pronašli smo logo, prekidamo petlju

        if logo_element and 'src' in logo_element.attrs:
            logo_src = logo_element['src']
            full_logo_url = urljoin(main_url, logo_src)
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
        # Dodavanje nasumične pauze prije svakog zahtjeva
        await asyncio.sleep(random.uniform(0.5, 1.5))
        
        print(f"Pristupanje stranici: {product_url}")
        async with session.get(product_url) as response:
            response.raise_for_status()
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            # --- DODAN RANI IZLAZAK AKO STRANICA NIJE PROIZVODNA STRANICA ---
            name_element = soup.select_one('h1.product-title')
            if not name_element:
                print(f"Preskakanje URL-a: {product_url} jer se ne čini kao stranica proizvoda.")
                return None
            
            name = name_element.get_text(strip=True)
            
            # --- Ažurirana logika za preuzimanje opisa ---
            description = "Opis nije dostupan"
            # Prvo probamo naći sažeti opis
            short_description_element = soup.select_one('div.product-description p')
            if short_description_element:
                description = short_description_element.get_text(strip=True)

            # Zatim tražimo detaljni opis unutar `content-text`
            full_description_parts = soup.select('div.content-text p')
            if full_description_parts:
                full_description = ' '.join([p.get_text(strip=True) for p in full_description_parts])
                description = full_description # Prepisujemo sažeti opis potpunim opisom

            product_price_selector = 'span.product-price'
            price_element = soup.select_one(product_price_selector)
            
            price = "Cena nije definisana"
            if price_element:
                price = price_element.get_text(strip=True)
            
            # --- Nova, poboljšana logika za slike iz galerije ---
            image_urls = set()
            
            gallery_items = soup.select('li[itemprop="associatedMedia"]')
            
            if gallery_items:
                for item in gallery_items:
                    link_element = item.find('a')
                    image_url = None
                    
                    if link_element:
                        image_url = urljoin("https://dynaudio.com", link_element.get('href'))
                        
                    if image_url:
                        image_urls.add(image_url)
            
            if not image_urls:
                image_urls.add("URL slike nedostupan")
                
            # --- DODAN NOVI BLOK KODA ZA DOHVAT DOSTUPNIH BOJA ---
            available_colors = []
            color_picker_links = soup.select('div.color-pickers a.color-selected')
            if color_picker_links:
                for link in color_picker_links:
                    color_name = link.get('title')
                    # Izdvajanje URL-a iz 'style' atributa
                    style_str = link.select_one('div.colorpicker')['style']
                    match = re.search(r'url\((.*?)\)', style_str)
                    color_image_url = match.group(1) if match else None
                    
                    if color_name and color_image_url:
                        available_colors.append({
                            "ime_boje": color_name,
                            "url_slike": urljoin("https://dynaudio.com", color_image_url)
                        })
            else:
                # Ako nema birača boja, pokušaj dohvaćanje iz galerije (stara metoda)
                gallery_items = soup.select('li[itemprop="associatedMedia"]')
                if gallery_items:
                    for item in gallery_items:
                        color_name = item.get('data-name')
                        if color_name:
                            color_exists = any(d['ime_boje'] == color_name for d in available_colors)
                            if not color_exists:
                                # Uzimamo prvu sliku za tu boju
                                link_element = item.find('a')
                                image_url = urljoin("https://dynaudio.com", link_element.get('href')) if link_element else None
                                available_colors.append({
                                    "ime_boje": color_name,
                                    "url_slike": image_url
                                })

            # --- Ažurirana logika za specifikacije ---
            specifications = {}
            specs_selectors = [
                'div#product_specifications table tr',
                'div.specs-table tr',
                'div.specs-container tr',
                'div.features-and-specs table tr',
                'ul.product-specs-table li',  # Novi selektor za li-based specifikacije
                'div.product-specs-list li'   # Dodatni robustni selektor
            ]

            spec_items = []
            for selector in specs_selectors:
                spec_items = soup.select(selector)
                if spec_items:
                    break # Pronašli smo podudaranje, prekidamo petlju

            if spec_items:
                for item in spec_items:
                    # Provjeravamo da li je element li (nova struktura) ili tr (stara struktura)
                    if item.name == 'li':
                        spec_name_element = item.select_one('.spec-label')
                        spec_value_element = item.select_one('.spec-value')
                        if spec_name_element and spec_value_element:
                            spec_name = spec_name_element.get_text(strip=True)
                            spec_value = spec_value_element.get_text(strip=True)
                            if spec_name and spec_value:
                                specifications[spec_name] = spec_value
                    elif item.name == 'tr':
                        cols = item.find_all(['td', 'th'])
                        if len(cols) == 2:
                            spec_name = cols[0].get_text(strip=True)
                            spec_value = cols[1].get_text(strip=True)
                            if spec_name and spec_value:
                                specifications[spec_name] = spec_value

            # --- Nova logika za preuzimanje linkova ---
            download_links = []
            link_elements = soup.select('div.content-links ul li a')
            for link in link_elements:
                link_href = link.get('href')
                link_name = link.get_text(strip=True)
                if link_href and link_name:
                    full_link_url = urljoin("https://dynaudio.com", link_href)
                    download_links.append({
                        "ime_linka": link_name,
                        "url": full_link_url
                    })

            return {
                "ime_proizvoda": name,
                "brend_logo_url": brand_logo_url,
                "cena": price,
                "opis": description,
                "url_proizvoda": product_url,
                "url_slika": list(image_urls),
                "dostupne_boje": available_colors,
                "linkovi_i_preuzimanja": download_links,
                "specifikacije": specifications,
                "kategorije": [category_name]
            }

    except aiohttp.ClientError as e:
        print(f"Greška tokom asinhronog pristupa detaljima za {product_url}: {e}")
        return None
    except Exception as e:
        print(f"Došlo je do nepredviđene greške prilikom obrade detalja za {product_url}: {e}")
        return None

async def find_series_urls(session, category_url):
    """
    Pronalazi i vraća listu URL-ova serija na stranici kategorije.
    """
    series_urls = []
    try:
        print(f"Traženje serija na stranici kategorije: {category_url}")
        async with session.get(category_url) as response:
            response.raise_for_status()
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')

            # Robusni selektori za pronalaženje linkova na stranice serija
            series_selectors = [
                'div.feature-box a',
                'div.series-list-container a',
                'div.categories-grid a',
                'div.categories-list a'
            ]

            for selector in series_selectors:
                links = soup.select(selector)
                if links:
                    for link in links:
                        href = link.get('href')
                        if href and not href.startswith('#'):
                            full_url = urljoin("https://dynaudio.com", href)
                            series_urls.append(full_url)
                    break
            
            if not series_urls:
                print(f"Nema pronađenih URL-ova serija na stranici: {category_url}. Nastavlja se sa pretragom proizvoda na samoj stranici.")
                series_urls.append(category_url) # Ako nema serija, nastavi sa pretragom na istoj stranici
            
            return list(set(series_urls)) # Vraća jedinstvene URL-ove

    except aiohttp.ClientError as e:
        print(f"Greška prilikom preuzimanja stranice serije: {category_url}: {e}")
        return []
    
async def main():
    """
    Glavna asinhrona funkcija za pokretanje procesa preuzimanja podataka.
    """
    main_page_url = "https://dynaudio.com"
    
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
    
    async with aiohttp.ClientSession() as session:
        for category_name, category_url in categories.items():
            
            # Prvo pronalazimo sve stranice serija unutar kategorije
            series_urls = await find_series_urls(session, category_url)
            
            print(f"\nU kategoriji '{category_name}' pronađeno je {len(series_urls)} stranica serija.")

            for series_url in series_urls:
                print(f"Pristupanje stranici serije: {series_url}")
                try:
                    async with session.get(series_url) as response:
                        response.raise_for_status()
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        product_links = []
                        # Ažurirani selektori za pronalaženje kartica proizvoda
                        product_tile_selectors = [
                            'a.product-card',
                            'div.feature-box a',
                            'div.product-list-container a',
                            'div.product-grid a',
                            'div.product-item a',
                            'div.product-bycategory a', # Dodat za vaš primer
                        ]

                        for selector in product_tile_selectors:
                            links = soup.select(selector)
                            if links:
                                for link_element in links:
                                    href = link_element.get('href')
                                    if href:
                                        full_link = urljoin("https://dynaudio.com", href)
                                        product_links.append(full_link)
                                break
                        
                        if not product_links:
                            print(f"Nema pronađenih URL-ova proizvoda na stranici serije '{series_url}'.")
                            continue
                        
                        print(f"Identifikovano je {len(set(product_links))} jedinstvenih URL-ova proizvoda.")
                        
                        tasks = []
                        for link in set(product_links):
                            tasks.append(async_scrape_product_details(session, link, category_name, brand_logo_url))
                        
                        results = await asyncio.gather(*tasks, return_exceptions=True)
                        
                        for result in results:
                            if isinstance(result, dict):
                                product_url = result.get('url_proizvoda')
                                if product_url and product_url not in scraped_urls:
                                    all_products_data.append(result)
                                    scraped_urls.add(product_url)
                                else:
                                    print(f"Preskakanje duplog proizvoda: {product_url}")
                            else:
                                print(f"Zabeležena greška tokom prikupljanja podataka: {result}")
                
                except aiohttp.ClientError as e:
                    print(f"Kritična greška tokom pristupa web resursu za seriju {series_url}: {e}")
                except Exception as e:
                    print(f"Došlo je do nepredviđene greške: {e}")

    output_filename = "dynaudio_products.json"
    if all_products_data:
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(all_products_data, f, indent=4, ensure_ascii=False)
            
        print(f"\nOperacija uspešno završena. {len(all_products_data)} artikala je zabeleženo u datoteci: {output_filename}.")
    else:
        print("\nNijedan proizvod nije pronađen. Kreiranje datoteke je preskočeno.")
    
    print("Proces preuzimanja podataka je finalizovan.")

if __name__ == "__main__":
    asyncio.run(main())
