# src/data_fetcher.py

import requests
from bs4 import BeautifulSoup
import re
from dateutil import parser 
from src.database_manager import insert_rates
# Debes importar la función del mercado P2P (asumo que está en src/market_fetcher.py)
from src.market_fetcher import fetch_binance_p2p_rate 
from datetime import datetime
import logging
from urllib3.exceptions import InsecureRequestWarning
# Ignorar advertencias de SSL (no recomendado para producción)
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


# Configuración de logging para este módulo
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BCV_URL = "https://www.bcv.org.ve"

# --- CONFIGURACIÓN DE LA API GRATUITA DE FOREX (ALPHA VANTAGE) ---
# Separamos el valor de la clave real del placeholder de error
ALPHA_VANTAGE_API_KEY = "QODS5X4TDMDRNRSM" 
ALPHA_VANTAGE_PLACEHOLDER = "TU_CLAVE_API_AV" 

FOREX_URL = f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency=EUR&to_currency=USD&apikey={ALPHA_VANTAGE_API_KEY}"

# --- Funciones de Web Scraping y Auxiliares (COMPLETADAS) ---

def _extract_rate_by_id(soup, currency_id, currency_code):
    """Extrae la tasa de una divisa usando su ID de contenedor único."""
    
    # 1. Buscar el div específico por su ID (e.g., id="dolar")
    div_container = soup.find('div', id=currency_id)
    
    if div_container:
        # 2. El valor de la tasa siempre está dentro del tag <strong>
        tasa_tag = div_container.find('strong')
        
        if tasa_tag:
            # Reemplazar separador de miles '.' y separador decimal ',' por el formato estándar de Python '.'
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
        logger.error(f"FALLO DE CONEXIÓN o HTTP NO 200 con BCV: {e}")
        return {} # Devuelve un diccionario vacío en caso de fallo crítico de conexión

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
    date_container = soup.find('div', class_='pull-right dinpro center')
    
    if date_container:
        date_tag = date_container.find('span', class_='date-display-single')
        if date_tag:
            # Buscar el patrón de fecha
            date_match = re.search(r'(\w+,\s\d{2}\s\w+\s\d{4})', date_tag.text)
            date_info = date_match.group(1) if date_match else date_tag.text.strip()
    
    all_rates['Fecha'] = date_info
        
    return all_rates

def _convert_date_format(date_string):
    """Convierte la fecha extraída ('Martes, 30 Septiembre 2025') a 'DD/MM/YYYY' usando dateutil."""
    try:
        # Eliminar el día de la semana para simplificar y asegurar que dateutil lo reconozca
        # Busca "30 Septiembre 2025" o similar
        match = re.search(r'(\d{1,2}\s\w+\s\d{4})', date_string) 
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
    

# --- Función de Tasa de Mercado Temporal (AHORA USARÁS LA REAL) ---
def _get_mercado_rate():
    """
    Función que envuelve la llamada a la tasa P2P. Se mantiene por consistencia
    con el nombre anterior de la función temporal.
    """
    return fetch_binance_p2p_rate() 
    
# --- Función de Fetch de FOREX (CON CORRECCIÓN DE KEY) ---
def fetch_forex_eur_usd_rate():
    """
    Obtiene la tasa EUR/USD del mercado Forex usando la API gratuita de Alpha Vantage.
    """
    try:
        logger.info("Conectando con Alpha Vantage para obtener la tasa EUR/USD del mercado...")
        response = requests.get(FOREX_URL, timeout=8)
        response.raise_for_status()
        data = response.json()
        
        if "Error Message" in data or "Note" in data:
            logger.error(f"Error de la API de Alpha Vantage: {data.get('Error Message') or data.get('Note')}")
            return 0.0
            
        rate_info = data.get("Realtime Currency Exchange Rate", {})
        rate_str = rate_info.get("5. Exchange Rate")
        
        if rate_str:
            forex_rate = float(rate_str)
            logger.info(f"Tasa EUR/USD del mercado obtenida: {forex_rate:.4f}")
            return forex_rate
        
        logger.warning("Respuesta de Alpha Vantage válida, pero no se encontró la tasa de conversión en el formato esperado.")
        return 0.0

    except requests.exceptions.RequestException as e:
        logger.error(f"Error de conexión con la API de Alpha Vantage: {e}")
        return 0.0


# --- Función Principal para Obtener y Guardar Tasas (CORREGIDA para manejar None) ---

def get_exchange_rates():
    """
    Función principal para obtener todas las tasas de cambio requeridas,
    redondearlas y guardarlas.
    """
    
    # 1. Obtención de datos
    scraped_data = _scrape_bcv_rates()
    # TRUCO PARA EVITAR ATTRIBUTEERROR: Si el scrapeo falla, usamos un diccionario vacío
    if scraped_data is None:
        scraped_data = {} 
        logger.warning("BCV Scraper devolvió None. Usando un diccionario vacío para los datos del BCV.")

    tasa_mercado_cruda = _get_mercado_rate()
    tasa_bcv_usd = scraped_data.get('USD_BCV')
    tasa_bcv_eur = scraped_data.get('EUR_BCV')
    date_info_raw = scraped_data.get('Fecha') 

    tasa_forex_eur_usd = fetch_forex_eur_usd_rate()
    
    # ----------------------------------------------------
    # CÁLCULO DE LA TASA IMPLÍCITA
    # ----------------------------------------------------
    bcv_eur_usd_implicita = 0.0
    if isinstance(tasa_bcv_usd, (int, float)) and isinstance(tasa_bcv_eur, (int, float)) and tasa_bcv_usd > 0:
        bcv_eur_usd_implicita = tasa_bcv_eur / tasa_bcv_usd
        
    date_info_clean = _convert_date_format(date_info_raw)
    
    # Verificación crítica: Fallo si no tenemos los datos principales
    if not (tasa_bcv_usd and tasa_mercado_cruda):
        logger.error("Fallo la obtención de tasas críticas (USD BCV o USD Mercado). Retornando None.")
        return None, None, None

    tasa_mercado_redondeada = round(tasa_mercado_cruda, 0) # Redondeamos al entero más cercano
    
    # ----------------------------------------------------
    # ASIGNACIÓN FINAL PARA LA BASE DE DATOS
    # ----------------------------------------------------
    now = datetime.now()
    data_to_save = {
        'timestamp': now.isoformat(),
        'date': date_info_clean if date_info_clean else now.strftime("%d/%m/%Y"),
        'USD_BCV': tasa_bcv_usd,
        'EUR_BCV': tasa_bcv_eur, 
        'CNY_BCV': scraped_data.get('CNY_BCV'),
        'TRY_BCV': scraped_data.get('TRY_BCV'),
        'RUB_BCV': scraped_data.get('RUB_BCV'), 
        'USD_MERCADO_CRUDA': tasa_mercado_cruda,
        'EUR_USD_IMPLICITA': bcv_eur_usd_implicita,
        'EUR_USD_FOREX': tasa_forex_eur_usd,
    }
    
    insertion_success = insert_rates(data_to_save) # Guardar en SQLite
    
    if insertion_success:
        logger.info(f"Registro de tasas guardado en DB para la fecha {data_to_save['date']}.")
    else:
        logger.error("FALLO CRÍTICO: No se pudo insertar el registro en la base de datos SQLite.")


    return tasa_bcv_usd, tasa_mercado_cruda, tasa_mercado_redondeada