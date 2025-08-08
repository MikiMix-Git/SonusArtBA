import requests
from bs4 import BeautifulSoup
import json
import time
import os
from googletrans import Translator
import re
import asyncio

async def async_translate(text, dest_lang):
    """Asinhrona funkcija za prevođenje teksta."""
    translator = Translator()
    try:
        translated_text = await translator.translate(text, dest=dest_lang)
        return translated_text.text
    except Exception as e:
        print(f"Greška pri asinhronom prevođenju teksta '{text}': {e}")
        return text

def translate_data(data, dest_lang='hr'):
    """
    Rekurzivno prevodi tekstualne vrijednosti u rječniku ili listi.
    """
    if isinstance(data, dict):
        new_data = {}
        for key, value in data.items():
            if isinstance(key, str):
                try:
                    if key == "specifikacije":
                        translated_key = key
                    else:
                        translated_key = asyncio.run(async_translate(key, dest_lang))
                except Exception as e:
                    translated_key = key
                    print(f"Greška pri prevođenju ključa '{key}': {e}")
            else:
                translated_key = key
            new_data[translated_key] = translate_data(value, dest_lang)
        return new_data
    
    elif isinstance(data, list):
        return [translate_data(item, dest_lang) for item in data]
    
    elif isinstance(data, str):
        technical_terms = ['aptX', 'Wi-Fi', 'DTS Play-Fi']
        if re.search(r'\d', data) or any(s in data for s in ['€', '€', 'W', 'kg', 'Hz', '"', "'"]) or any(term in data for term in technical_terms):
            return data
            
        try:
            translated_text = asyncio.run(async_translate(data, dest_lang))
            return translated_text
        except Exception as e:
            print(f"Greška pri prevođenju teksta '{data}': {e}")
            return data
    
    else:
        return data

def get_product_details(product_url):
    """
    Preuzima dodatne detalje i specifikacije s individualne stranice proizvoda.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    details = {}
    
    try:
        response = requests.get(product_url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Greška pri preuzimanju detalja sa stranice {product_url}: {e}")
        return details
 
    soup = BeautifulSoup(response.content, 'html.parser')
 
    feature_table = soup.find('div', class_='feature-chart__table')
    if feature_table:
        specs_dict = {}
        rows = feature_table.find_all('div', class_='feature-chart__table-row')
        
        for row in rows:
            heading_element = row.find('div', class_='feature-chart__heading')
            value_element = row.find('div', class_='feature-chart__value')
            
            if heading_element and value_element:
                heading = heading_element.get_text(strip=True)
                
                value_text = None
                if value_element.find('svg', class_='icon-success'):
                    value_text = 'Yes'
                elif value_element.find('ul'):
                    list_items = value_element.find_all('li')
                    value_text = [li.get_text(strip=True) for li in list_items]
                else:
                    value_text = value_element.get_text(strip=True)
                
                if value_text:
                    specs_dict[heading] = value_text
        
        details['specifikacije'] = specs_dict
 
    return details

def get_all_product_data(base_url):
    """
    Iterira kroz sve stranice kategorije i prikuplja podatke.
    """
    all_products = []
    page_number = 1
    
    while True:
        url = f'{base_url}?page={page_number}'
        print(f"Preuzimanje podataka sa stranice: {url}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Greška pri preuzimanju stranice {url}: {e}")
            break
 
        soup = BeautifulSoup(response.content, 'html.parser')
        product_items = soup.find_all('product-card')
        
        if not product_items:
            print("Nema više proizvoda. Preuzimanje završeno.")
            break
            
        for item in product_items:
            title_element = item.find('span', class_='product-card__title')
            title = title_element.find('a').get_text(strip=True) if title_element and title_element.find('a') else 'N/A'
            
            price_element = item.find('price-list')
            price = price_element.find('sale-price').get_text(strip=True) if price_element and price_element.find('sale-price') else 'N/A'
            
            image_element = item.find('img', class_='product-card__image--primary')
            image_url = 'https:' + image_element['src'] if image_element and 'src' in image_element.attrs else 'N/A'
            
            description_element = item.find('p', class_='product-card__custom-description')
            description = description_element.get_text(strip=True) if description_element else 'N/A'
            
            product_link_element = item.find('a', class_='bold')
            product_link = 'https://argonaudio.com' + product_link_element['href'] if product_link_element and 'href' in product_link_element.attrs else 'N/A'
            
            badges = [badge.get_text(strip=True) for badge in item.find_all('span', class_='badge--primary')]
 
            color_swatches = item.find_all('label', class_='color-swatch')
            colors = [swatch.find('span', class_='sr-only').get_text(strip=True).split(' (')[0].strip() for swatch in color_swatches if swatch.find('span')]
 
            if product_link != 'N/A':
                print(f"  > Preuzimanje detalja za: {title}")
                details = get_product_details(product_link)
                product_info = {
                    'naziv': title,
                    'cijena': price,
                    'slika_url': image_url,
                    'opis': description,
                    'link': product_link,
                    'badge-ovi': badges,
                    'boje': colors,
                    **details
                }
            else:
                product_info = {
                    'naziv': title,
                    'cijena': price,
                    'slika_url': image_url,
                    'opis': description,
                    'link': product_link,
                    'badge-ovi': badges,
                    'boje': colors
                }
            
            all_products.append(product_info)
            time.sleep(1)
        
        page_number += 1
    
    return all_products
 
def save_to_json(data, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
 
def load_from_json(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)
 
if __name__ == '__main__':
    categories = {
        "Speakers": 'https://argonaudio.com/collections/speakers',
        "Amplifiers & Streaming": 'https://argonaudio.com/collections/amplifiers-streaming',
        "Turntables": 'https://argonaudio.com/collections/turntables',
        "Subwoofers": 'https://argonaudio.com/collections/subwoofers',
        "Headphones": 'https://argonaudio.com/collections/headphones',
        "Accessories": 'https://argonaudio.com/collections/accessories'
    }
 
    scraped_file = 'argon_audio_products_all_categories.json'
    translated_file = 'argon_audio_products_all_categories_hr.json'
 
    if os.path.exists(scraped_file):
        print(f"Datoteka '{scraped_file}' već postoji. Preuzimanje podataka se preskače.")
        all_scraped_data = load_from_json(scraped_file)
    else:
        all_scraped_data = {}
        for category_name, url in categories.items():
            print(f"=====================================================")
            print(f"Preuzimanje podataka za kategoriju: {category_name}")
            print(f"=====================================================")
            product_list = get_all_product_data(url)
            if product_list:
                all_scraped_data[category_name] = product_list
            else:
                print(f"Nijedan proizvod nije pronađen u kategoriji {category_name}. Preskakanje.")
            time.sleep(5)
        
        if all_scraped_data:
            save_to_json(all_scraped_data, scraped_file)
            print(f'\nPodaci sačuvani u datoteci {scraped_file}')
        else:
            print("Nijedan proizvod nije pronađen. Prekinut proces.")
 
    print("Skripta je uspješno učitala podatke i spremna je za prevođenje.")
    if all_scraped_data:
        print("\nPrevođenje podataka na hrvatski jezik...")
        translated_data = translate_data(all_scraped_data)
        save_to_json(translated_data, translated_file)
        print(f'\nPrevedeni podaci sačuvani su u datoteci {translated_file}')