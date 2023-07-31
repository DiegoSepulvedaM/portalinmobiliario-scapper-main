import os
import requests
import json
from dotenv import load_dotenv
import time
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup

def get_page_source(url):
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Para ejecutar Chrome en modo headless (sin interfaz gráfica)
    driver = webdriver.Chrome(options=options)
    driver.get(url)
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//div[@class='andes-tag andes-tag--large']")))
        page_source = driver.page_source
    except TimeoutException:
        page_source = None
    driver.quit()
    return page_source


user_agents = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
    'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36',
    # Add more User-Agent here...
]

def get_page_source_with_random_user_agent(url):
    headers = {
        'User-Agent': random.choice(user_agents)
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.text
    else:
        return None

load_dotenv()

# URL to the locations we want to scrape
CHILE_URL = 'https://www.portalinmobiliario.com/venta/departamento'
CHILEARRIENDO_URL = 'https://www.portalinmobiliario.com/arriendo/departamento'

COMMUNES = [
    {
        'name': 'Chile',
        'link': CHILE_URL
    },
    {
        'name': 'ChileA',
        'link': CHILEARRIENDO_URL
    }
]

ALREADY_SEEN_FILE = 'already_seen.json'

def load_already_seen_data():
    """Load data from the JSON file with previously seen apartments."""
    try:
        with open(ALREADY_SEEN_FILE, 'r', encoding='utf8') as jfile:
            return json.load(jfile)
    except FileNotFoundError:
        return {}

def save_already_seen_data(data):
    """Save data to the JSON file."""
    with open(ALREADY_SEEN_FILE, 'w', encoding='utf8') as jfile:
        json.dump(data, jfile, indent=4, ensure_ascii=False)

def get_all_apartments(url):
    """Get all available apartments from all pages of the portal.

    Args:
        url (string): URL of the first page of the real estate portal.

    Returns:
        list(list)
    """
    all_apartments = []
    while url:
        try:
            user_agent = random.choice(user_agents)
            headers = {'User-Agent': user_agent}
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # Raise an exception if there's an error in the request
            page_source = response.text
        except requests.RequestException as e:
            print(f"Error fetching the page: {e}")
            break

        most_recent_apartments = get_recent_apartments(page_source)
        all_apartments.extend(most_recent_apartments)

        time.sleep(5)

        soup = BeautifulSoup(page_source, 'html.parser')
        next_page_link = soup.find("a", class_="andes-pagination__link", title="Siguiente")
        if next_page_link:
            url = next_page_link["href"]
        else:
            url = None

    return all_apartments

def check_if_are_new_apartments(commune, most_recent_apartments):
    """Check for new apartments and return them."""
    already_seen_data = load_already_seen_data()
    titles_seen = already_seen_data.get(commune, [])
    titles_already_seen = [title for title, _ in titles_seen]
    new_apartments = [(title, url) for title, url in most_recent_apartments if title not in titles_already_seen]
    return new_apartments

def update_most_recent_file(commune, most_recent_apartments):
    """Actualiza el archivo JSON con los departamentos notificados."""
    already_seen_data = load_already_seen_data()

    # Obtenemos los títulos de los apartamentos ya vistos para esta comuna
    titles_seen = {apartment['title'] for apartment in already_seen_data.get(commune, [])}

    # Agregamos solo los nuevos apartamentos a la lista ya vista
    new_apartments = [apartment for apartment in most_recent_apartments if apartment['title'] not in titles_seen]

    # Agregamos los nuevos apartamentos a la lista ya vista para esta comuna
    already_seen_data.setdefault(commune, []).extend(new_apartments)

    # Guardamos los datos actualizados en el archivo JSON
    save_already_seen_data(already_seen_data)

    
def get_recent_apartments(page):
    """Get the latest apartments from the current page.

    Args:
        page (string): HTML of the real estate portal page.

    Returns:
        list(dict): List of dictionaries with apartment data.
    """
    soup = BeautifulSoup(page, 'html.parser')
    items = soup.find_all("li", class_="ui-search-layout__item")
    apartments = []

    session = requests.Session()
    session.max_redirects = 5  # Limit the number of redirects

    for item in items:
        link = item.find('a', class_='ui-search-link')
        if link:
            link = link['href'].split('#')[0]  # Extract the link and remove any anchors

            try:
                user_agent = random.choice(user_agents)
                headers = {'User-Agent': user_agent}
                response = session.get(link, headers=headers)
                response.raise_for_status()
                apartment_page_source = response.text
                apartment_data = extract_apartment_data(apartment_page_source)

                if apartment_data:
                    apartments.append(apartment_data)
                    print(apartment_data)  # Add this line to print the apartment data

            except requests.RequestException as e:
                print(f"Error fetching apartment data: {e}")
                print(f"Apartment page URL: {link}")
                continue

    return apartments

def get_value_by_label(soup, label):
    """Obtiene el valor asociado a una etiqueta específica en el HTML.

    Args:
        soup (BeautifulSoup): Objeto BeautifulSoup del HTML de la página.
        label (string): Etiqueta que se quiere buscar.

    Returns:
        string: Valor asociado a la etiqueta o 'N/A' si no se encuentra.
    """
    label_elements = soup.find_all('span', class_='ui-pdp-label')
    for element in label_elements:
        if label in element.text:
            value_element = element.find_next('span', class_='ui-pdp-color--BLACK')
            if not value_element:
                value_element = element.find_next('span', class_='ui-pdp-family--REGULAR')
            if value_element:
                return value_element.text.strip()
    return "N/A"

def extract_apartment_data(apartment_page_source):
    """Extrae los datos de un apartamento de la página individual del apartamento.

    Args:
        apartment_page_source (string): Código fuente de la página del apartamento.

    Returns:
        dict: Diccionario con los datos del apartamento (titulo, imagen, precio, dimensiones,
              dormitorios, baños, ubicacion y mapa).
    """
    apartment_data = {}

    apartment_soup = BeautifulSoup(apartment_page_source, 'html.parser')

    apartment_data['title'] = apartment_soup.select_one('h1').text.strip()

    image_element = apartment_soup.find('meta', property='og:image')
    apartment_data['image'] = image_element['content'] if image_element else 'No image available'

    apartment_data['price'] = apartment_soup.select_one('span.andes-money-amount__fraction').text.strip()

    apartment_data['dimensions'] = apartment_soup.select_one('div.ui-pdp-highlighted-specs-res__icon-label:nth-of-type(1) span').text.strip()

    apartment_data['bedrooms'] = apartment_soup.select_one('div.ui-pdp-highlighted-specs-res__icon-label:nth-of-type(2) span').text.strip()

    apartment_data['bathrooms'] = apartment_soup.select_one('div:nth-of-type(3) span.ui-pdp-size--SMALL.ui-pdp-family--REGULAR').text.strip()

    apartment_data['location'] = apartment_soup.select_one('.ui-vip-location__subtitle p').text.strip()

    map_element = apartment_soup.select_one('.ui-vip-location__map img')
    apartment_data['map_link'] = map_element['src'] if map_element else 'N/A'

    # Utilizar Selenium para obtener el contenido de la página
    modalidad_page_source = get_page_source(apartment_data['location'])
    if modalidad_page_source:
        modalidad_soup = BeautifulSoup(modalidad_page_source, 'html.parser')
        apartment_data['modalidad'] = modalidad_soup.select_one('a.andes-breadcrumb__link[title="Propiedades usadas"]').text.strip()
    else:
        apartment_data['modalidad'] = 'N/A'

        

    return apartment_data


def parse_map_link(soup):
    """Extract the map link from the script element.

    Args:
        soup (BeautifulSoup): BeautifulSoup object of the individual apartment page.

    Returns:
        str: Map link.
    """
    try:
        scripts = soup.find_all('script', {'type': 'application/ld+json'})
        for script in scripts:
            json_data = json.loads(script.string.strip())
            if isinstance(json_data, list):
                for item in json_data:
                    if item.get('@type') == 'Map':
                        map_link = item['url']
                        return map_link
            elif json_data.get('@type') == 'Map':
                map_link = json_data['url']
                return map_link
    except Exception as e:
        print(f"Error extracting map link: {e}")
        print(f"Script string: {script.string.strip()}")

    return "N/A"

if __name__ == "__main__":
    WEBHOOK_URL = os.getenv('WEBHOOK_URL')
    for commune in COMMUNES:
        all_apartments = get_all_apartments(commune['link'])
        new_apartments = check_if_are_new_apartments(commune['name'], all_apartments)
        if len(new_apartments) > 0:
            requests.post(WEBHOOK_URL, json={'data': new_apartments})
            update_most_recent_file(commune['name'], all_apartments)