import requests
from bs4 import BeautifulSoup
import json
import time
import re
import asyncio
import aiohttp

async def fetch_url(session, url, headers=None, max_retries=3):
    """
    Asinhrona pomoćna funkcija za preuzimanje HTML sadržaja sa rukovanjem greškama
    i eksponencijalnim povlačenjem.
    """
    if headers is None:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    for attempt in range(max_retries):
        try:
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
                return await response.text()
        except aiohttp.ClientError as e:
            print(f"Greška pri preuzimanju {url}, pokušaj {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt) # Eksponencijalno povlačenje
    return None

def get_product_gallery_images(content):
    """
    Preuzima sve URL-ove slika iz galerije proizvoda iz HTML sadržaja.
    """
    image_urls = [] # Promijenjeno sa seta na listu kako bi se sačuvao redoslijed
    seen_urls = set()
    if not content:
        return image_urls

    soup = BeautifulSoup(content, 'html.parser')
    image_elements = soup.select('div.product-gallery__media img, div.video-media img')
    
    for img_element in image_elements:
        src = img_element.get('src')
        srcset = img_element.get('srcset')
        
        url_to_add = None
        if srcset:
            urls = srcset.split(',')
            url_to_add = urls[-1].strip().split(' ')[0]
        elif src:
            url_to_add = src
        
        if url_to_add:
            if url_to_add.startswith('//'):
                url_to_add = 'https:' + url_to_add
            if url_to_add not in seen_urls: # Provjerava duplikate prije dodavanja
                image_urls.append(url_to_add) # Dodavanje u listu
                seen_urls.add(url_to_add) # Dodavanje u set za praćenje
                
    return image_urls

def get_product_details_from_content(content):
    """
    Parsira detalje i specifikacije s HTML sadržaja individualne stranice proizvoda.
    """
    details = {}
    if not content:
        return details
    
    soup = BeautifulSoup(content, 'html.parser')

    # Pronalazi tabelu s karakteristikama
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

    # Preuzimanje varijanti boja
    color_variants_list = []
    variant_fieldset = soup.find('fieldset', class_='variant-picker__option')
    if variant_fieldset:
        color_swatches = variant_fieldset.find_all('label', class_='color-swatch')
        for swatch in color_swatches:
            name_element = swatch.find('span', class_='sr-only')
            name = name_element.get_text(strip=True) if name_element else 'N/A'

            swatch_style = swatch.get('style')
            swatch_url = None
            if swatch_style:
                match = re.search(r'url\((.*?)\)', swatch_style)
                if match:
                    url = match.group(1).strip("'\"")
                    if url.startswith('//'):
                        swatch_url = 'https:' + url
                    else:
                        swatch_url = url
                else:
                    match = re.search(r'linear-gradient\(.*\)', swatch_style)
                    if match:
                        swatch_url = match.group(0)

            color_variants_list.append({
                'name': name,
                'swatch_url': swatch_url
            })
    
    details['variants'] = color_variants_list

    return details

async def async_get_product_data(session, product_link, brand_logo_url):
    """
    Asinhrono preuzima i parsira podatke za pojedinačni proizvod.
    """
    content = await fetch_url(session, product_link)
    if not content:
        return None

    soup = BeautifulSoup(content, 'html.parser')
    
    title_element = soup.find('h1', class_='product-info__title')
    title = title_element.get_text(strip=True) if title_element else 'N/A'
    
    price_element = soup.find('div', class_='product-info__price') # Ispravljen selektor
    price = price_element.get_text(strip=True) if price_element else 'N/A'
    
    description_element = soup.find('div', class_='product-info__description') # Ispravljen selektor
    description = description_element.get_text(strip=True) if description_element else 'N/A'
    
    details = get_product_details_from_content(content)
    gallery_images = get_product_gallery_images(content)

    product_info = {
        'naziv': title,
        'cijena': price,
        'opis': description,
        'images': gallery_images,
        'link': product_link,
        'specifikacije': details.get('specifikacije', {}),
        'variants': details.get('variants', []),
        'brand_logo': brand_logo_url
    }
    return product_info

async def async_get_all_product_data(session, base_url, brand_logo_url):
    """
    Asinhrono iterira kroz sve stranice kategorije i prikuplja podatke.
    """
    all_products = []
    page_number = 1
    
    while True:
        url = f'{base_url}?page={page_number}'
        print(f"Preuzimanje podataka sa stranice: {url}")
        
        content = await fetch_url(session, url)
        if not content:
            break
            
        soup = BeautifulSoup(content, 'html.parser')
        product_items = soup.find_all('product-card')
        
        if not product_items:
            print("Nema više proizvoda. Preuzimanje završeno.")
            break
        
        tasks = []
        for item in product_items:
            product_link_element = item.find('a', class_='bold')
            if product_link_element and 'href' in product_link_element.attrs:
                product_link = 'https://argonaudio.com' + product_link_element['href']
                tasks.append(async_get_product_data(session, product_link, brand_logo_url))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, dict):
                all_products.append(result)
            elif result is not None:
                print(f"Zabeležena greška tokom prikupljanja podataka: {result}")
        
        page_number += 1
        await asyncio.sleep(5) # Odmor između stranica

    return all_products

def save_to_json(data, filename='argon_audio_products_all_categories.json'):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

async def main():
    """
    Glavna asinhrona funkcija za pokretanje procesa.
    """
    # Ograničenje: Requests i BeautifulSoup ne mogu da interpretiraju dinamički sadržaj koji se učitava
    # putem JavaScript-a. Ako web-stranica to koristi za proizvode, ovaj skrejper neće raditi.
    # U tom slučaju, bilo bi potrebno koristiti alat kao što je Selenium.
    
    base_domain = 'https://argonaudio.com'
    
    print("Preuzimanje logotipa brenda sa početne stranice...")
    logo_content = requests.get(base_domain).text
    brand_logo_url = None
    if logo_content:
        soup = BeautifulSoup(logo_content, 'html.parser')
        logo_container = soup.find('h1', class_='header__logo')
        
        if logo_container:
            logo_img = logo_container.find('img')
            if logo_img and 'src' in logo_img.attrs:
                src_url = logo_img['src']
                if src_url.startswith('//'):
                    brand_logo_url = 'https:' + src_url
                else:
                    brand_logo_url = src_url
                print(f"  > Pronađen je URL logotipa: {brand_logo_url}")
            else:
                print("  > Nije pronađen img tag sa 'src' atributom unutar kontejnera.")
        else:
            print("  > Nije pronađen kontejner logotipa brenda ('h1.header__logo').")
    else:
        print("Greška pri preuzimanju početne stranice. Preskakanje preuzimanja logotipa.")


    categories = {
        "Active Speakers": f'{base_domain}/collections/active-speakers',
        "Passive Speakers": f'{base_domain}/collections/passive-speakers',
        "Amplifiers": f'{base_domain}/collections/amplifiers',
        "Music Streamers": f'{base_domain}/collections/music-streamers',
        "Turntables": f'{base_domain}/collections/turntables',
        "Subwoofers": f'{base_domain}/collections/subwoofers',
        "Headphones": f'{base_domain}/collections/headphones',
        "Cables": f'{base_domain}/collections/cables',
        "Speaker accessories": f'{base_domain}/collections/speaker-accessories',
        "Turntable Accessories": f'{base_domain}/collections/turntable-accessories'
    }

    all_scraped_data_by_category = {}

    async with aiohttp.ClientSession() as session:
        for category_name, url in categories.items():
            print(f"=====================================================")
            print(f"Preuzimanje podataka za kategoriju: {category_name}")
            print(f"=====================================================")
            product_list = await async_get_all_product_data(session, url, brand_logo_url)
            if product_list:
                all_scraped_data_by_category[category_name] = product_list
            else:
                print(f"Nijedan proizvod nije pronađen u kategoriji {category_name}. Preskakanje.")
            
    final_output = {
        'categories': all_scraped_data_by_category
    }

    if all_scraped_data_by_category:
        save_to_json(final_output)
        print(f'\nPodaci o svim proizvodima sačuvani su u datoteci argon_audio_products_all_categories.json')
    else:
        print("Nijedan proizvod nije pronađen. Prekinut proces.")

if __name__ == '__main__':
    asyncio.run(main())
