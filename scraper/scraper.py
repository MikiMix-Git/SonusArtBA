import requests
from bs4 import BeautifulSoup
import json
import time
import re

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

    # Nova logika za preuzimanje varijanti boja
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

def get_product_gallery_images(product_url):
    """
    Preuzima sve URL-ove slika iz galerije proizvoda na individualnoj stranici.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    image_urls = []
    
    try:
        response = requests.get(product_url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Greška pri preuzimanju galerije slika sa stranice {product_url}: {e}")
        return image_urls

    soup = BeautifulSoup(response.content, 'html.parser')

    image_elements = soup.select('div.product-gallery__media img, div.video-media img')
    
    for img_element in image_elements:
        src = img_element.get('src')
        srcset = img_element.get('srcset')
        
        if srcset:
            urls = srcset.split(',')
            url = urls[-1].strip().split(' ')[0]
            if url.startswith('//'):
                url = 'https:' + url
            if url not in image_urls:
                image_urls.append(url)
        elif src:
            if src.startswith('//'):
                src = 'https:' + src
            if src not in image_urls:
                image_urls.append(src)
                
    return image_urls

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
            
            description_element = item.find('p', class_='product-card__custom-description')
            description = description_element.get_text(strip=True) if description_element else 'N/A'
            
            product_link_element = item.find('a', class_='bold')
            product_link = 'https://argonaudio.com' + product_link_element['href'] if product_link_element and 'href' in product_link_element.attrs else 'N/A'
            
            badges = [badge.get_text(strip=True) for badge in item.find_all('span', class_='badge--primary')]

            if product_link != 'N/A':
                print(f"  > Preuzimanje detalja za: {title}")
                details = get_product_details(product_link)
                gallery_images = get_product_gallery_images(product_link)
                product_info = {
                    'naziv': title,
                    'cijena': price,
                    'images': gallery_images,
                    'opis': description,
                    'link': product_link,
                    'badge-ovi': badges,
                    **details
                }
            else:
                product_info = {
                    'naziv': title,
                    'cijena': price,
                    'images': [],
                    'opis': description,
                    'link': product_link,
                    'badge-ovi': badges,
                    'variants': []
                }
            
            all_products.append(product_info)
            time.sleep(1)
        
        page_number += 1
    
    return all_products

def save_to_json(data, filename='argon_audio_products_all_categories.json'):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

if __name__ == '__main__':
    base_domain = 'https://argonaudio.com'
    
    # Preuzimanje logotipa brenda
    print("Preuzimanje logotipa brenda sa početne stranice...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    brand_logo_url = None
    try:
        response = requests.get(base_domain, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        logo_container = soup.find('h1', class_='header__logo')
        
        if logo_container:
            print("  > Pronađen je kontejner logotipa.")
            
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

    except requests.exceptions.RequestException as e:
        print(f"Greška pri preuzimanju početne stranice: {e}")
    except Exception as e:
        print(f"Neočekivana greška prilikom parsiranja logotipa: {e}")


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

    for category_name, url in categories.items():
        print(f"=====================================================")
        print(f"Preuzimanje podataka za kategoriju: {category_name}")
        print(f"=====================================================")
        product_list = get_all_product_data(url)
        if product_list:
            all_scraped_data_by_category[category_name] = product_list
        else:
            print(f"Nijedan proizvod nije pronađen u kategoriji {category_name}. Preskakanje.")
        time.sleep(5)

    final_output = {
        'brand_logo': brand_logo_url,
        'categories': all_scraped_data_by_category
    }

    if all_scraped_data_by_category:
        save_to_json(final_output)
        print(f'\nPodaci o svim proizvodima sačuvani su u datoteci argon_audio_products_all_categories.json')
    else:
        print("Nijedan proizvod nije pronađen. Prekinut proces.")
