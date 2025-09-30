# src/data_fetcher.py

import requests
from bs4 import BeautifulSoup
import re
from dateutil import parser # <-- Importar el parser


from src.database_manager import insert_rates # <-- Importar la función de SQLite
# import csv
# import os
from datetime import datetime
import logging
from urllib3.exceptions import InsecureRequestWarning
# Ignorar advertencias de SSL (no recomendado para producción)
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


# Configuración de logging para este módulo
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# La ubicación de tu archivo de datos
# DATA_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'daily_rates.csv')
BCV_URL = "https://www.bcv.org.ve"

# --- Funciones de Web Scraping ---


# src/data_fetcher.py

# ... (mantén las importaciones y la configuración de logging) ...

def _extract_rate_by_id(soup, currency_id, currency_code):
    """Extrae la tasa de una divisa usando su ID de contenedor único."""
    
    # 1. Buscar el div específico por su ID (e.g., id="dolar")
    div_container = soup.find('div', id=currency_id)
    
    if div_container:
        # 2. El valor de la tasa siempre está dentro del tag <strong>
        tasa_tag = div_container.find('strong')
        
        if tasa_tag:
            tasa_str = tasa_tag.text.strip().replace('.', '').replace(',', '.')
            try:
                return float(tasa_str)
            except ValueError:
                logger.warning(f"Advertencia: No se pudo convertir la tasa {currency_code} ('{tasa_str}') a número.")
                
    return None

def _scrape_bcv_rates():
    """Realiza web scraping en la página del BCV para obtener las tasas de múltiples divisas."""
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(BCV_URL, headers=headers, verify=False) 
        response.raise_for_status() 
        logger.info(f"Conexión exitosa con el BCV (Status: {response.status_code}). Procediendo a extraer datos.")

    except requests.exceptions.RequestException as e:
        logger.error(f"FALLO DE CONEXIÓN o HTTP NO 200: {e}")
        return {} # Devuelve un diccionario vacío en caso de fallo

    soup = BeautifulSoup(response.text, 'html.parser')
    all_rates = {}

    # 1. Extracción de Tasas usando ID's únicos:
    all_rates['USD_BCV'] = _extract_rate_by_id(soup, 'dolar', 'USD')
    all_rates['EUR_BCV'] = _extract_rate_by_id(soup, 'euro', 'EUR')
    all_rates['CNY_BCV'] = _extract_rate_by_id(soup, 'yuan', 'CNY')
    all_rates['TRY_BCV'] = _extract_rate_by_id(soup, 'lira', 'TRY')
    all_rates['RUB_BCV'] = _extract_rate_by_id(soup, 'rublo', 'RUB')
    
    # 2. Extracción de la Fecha
    date_info = None
    # El tag que contiene la fecha es un span dentro de un div con la clase 'pull-right dinpro center'
    date_container = soup.find('div', class_='pull-right dinpro center')
    
    if date_container:
        date_tag = date_container.find('span', class_='date-display-single')
        if date_tag:
            # La fecha está dentro del texto del span
            date_match = re.search(r'(\w+,\s\d{2}\s\w+\s\d{4})', date_tag.text)
            date_info = date_match.group(1) if date_match else date_tag.text.strip()
    
    all_rates['Fecha'] = date_info
        
    return all_rates

# ... (El resto del código sigue abajo) ...




def _get_mercado_rate():
    """
    [TASA TEMPORAL]
    Placeholder para obtener la Tasa del Mercado (paralela). 
    Usaremos un valor fijo o una API simple hasta que el scraping del BCV esté sólido.
    """
    # Valor temporal: Usa un valor representativo del mercado para las pruebas
    # Nota: Este valor no es preciso, pero permite que el bot funcione.
    return 300.00 


# --- Función de Almacenamiento ---

# def _save_rates_to_csv(data):
#     """Guarda una nueva fila de tasas en el archivo daily_rates.csv."""
    
#     # file_exists = os.path.exists(DATA_FILE_PATH)
#     fieldnames = ['timestamp', 'date', 'USD_BCV', 'EUR_BCV', 'USD_MERCADO_CRUDA']

#     try:
#         # with open(DATA_FILE_PATH, 'a', newline='', encoding='utf-8') as csvfile:
#             writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
#             if not file_exists:
#                 writer.writeheader()
            
#             writer.writerow(data)
#             logger.info("Tasas guardadas exitosamente en daily_rates.csv.")
            
#     except Exception as e:
#         logger.error(f"Error al escribir en el CSV: {e}")

# --- Función Principal para Obtener y Guardar Tasas ---

def get_exchange_rates():
    """
    Función principal para obtener todas las tasas de cambio requeridas,
    redondearlas y guardarlas.
    """
    
    # El scraper ahora devuelve un diccionario con todas las tasas
    scraped_data = _scrape_bcv_rates()
    tasa_mercado_cruda = _get_mercado_rate() # Sigue siendo el valor temporal 300.00

    tasa_bcv_usd = scraped_data.get('USD_BCV')
    date_info_raw = scraped_data.get('Fecha') 
    
    # ----------------------------------------------------
    # PASO CLAVE: LLAMADA A LA CONVERSIÓN DE FECHA
    # ----------------------------------------------------
    date_info_clean = _convert_date_format(date_info_raw)
    
    if not (tasa_bcv_usd and tasa_mercado_cruda):
        logger.error("Fallo la obtención de tasas criticas (USD BCV o USD Mercado).")
        return None, None, None

    # Redondeo de la tasa del mercado para su uso en los rangos
    tasa_mercado_redondeada = round(tasa_mercado_cruda, -1)
    
    # Preparar datos para guardar (incluye todas las divisas)
    now = datetime.now()
    data_to_save = {
        'timestamp': now.isoformat(),
        'date': date_info_clean if date_info_clean else now.strftime("%d/%m/%Y"),
        'USD_BCV': tasa_bcv_usd,
        'EUR_BCV': scraped_data.get('EUR_BCV'), 
        'CNY_BCV': scraped_data.get('CNY_BCV'), # <-- ¡Estas líneas deben estar aquí!
        'TRY_BCV': scraped_data.get('TRY_BCV'), # <-- ¡Estas líneas deben estar aquí!
        'RUB_BCV': scraped_data.get('RUB_BCV'), # <-- ¡Estas líneas deben estar aquí!
        'USD_MERCADO_CRUDA': tasa_mercado_cruda,
    }
    
    insertion_success = insert_rates(data_to_save) # Guardar en SQLite
    
    # Añadimos un registro de éxito/fracaso
    if insertion_success:
        logger.info(f"Registro de tasas guardado en DB para la fecha {data_to_save['date']}.")
    else:
        # Esto capturará fallos de IntegrityError o cualquier otro error de SQL.
        logger.error("FALLO CRÍTICO: No se pudo insertar el registro en la base de datos SQLite.")


    # Retornar las tasas en el formato esperado por notifier.py
    return tasa_bcv_usd, tasa_mercado_cruda, tasa_mercado_redondeada

def _convert_date_format(date_string):
    """Convierte la fecha extraída ('Martes, 30 Septiembre 2025') a 'DD/MM/YYYY' usando dateutil."""
    try:
        # dateutil.parser.parse es muy inteligente y puede inferir el idioma.
        # Solo necesitamos darle un hint de que el día viene antes del mes si es ambiguo (lo cual no es aquí).
        
        # Eliminar el día de la semana para simplificar y asegurar que dateutil lo reconozca
        match = re.search(r'(\d{1,2}\s\w+\s\d{4})', date_string) # Busca "30 Septiembre 2025"
        if not match:
            return None
        
        date_part = match.group(1).strip()
        
        # Parsea la cadena y la convierte a objeto datetime
        fecha_obj = parser.parse(date_part) 
        
        # Formateamos al formato final DD/MM/AAAA
        return fecha_obj.strftime("%d/%m/%Y")
        
    except Exception as e:
        logger.error(f"Error al parsear la fecha con dateutil: {e}")
        return None