# src/data_fetcher.py

import requests
from bs4 import BeautifulSoup
import re
from dateutil import parser 
# 🚨 CAMBIO 1: Importamos las nuevas funciones específicas de la DB y la de lectura
from src.database_manager import save_bcv_rates, save_market_rates, get_latest_rates 
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

# --- Funciones de Web Scraping y Auxiliares (SE MANTIENEN IGUAL) ---

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
        # 🚨 NOTA: Asegúrate de que BCV_URL esté definido
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
        match = re.search(r'(\d{1,2}\s\w+\s\d{4})', date_string) 
        if not match:
            return None
        
        date_part = match.group(1).strip()
        fecha_obj = parser.parse(date_part) 
        
        # Formateamos al formato final DD/MM/AAAA
        return fecha_obj.strftime("%d/%m/%Y")
        
    except Exception as e:
        logger.error(f"Error al parsear la fecha con dateutil: {e}")
        return None
    
def _get_mercado_rate():
    """
    Función que envuelve la llamada a la tasa P2P. 
    """
    # 🚨 NOTA: fetch_binance_p2p_rate debe devolver float, o 0.0 si falla.
    return fetch_binance_p2p_rate() 
    
def fetch_forex_eur_usd_rate():
    """
    Obtiene la tasa EUR/USD del mercado Forex usando la API gratuita de Alpha Vantage.
    (Se mantiene igual)
    """
    try:
        logger.info("Conectando con Alpha Vantage para obtener la tasa EUR/USD del mercado...")
        # 🚨 NOTA: Asegúrate de que FOREX_URL esté definido
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


# --- Función Principal para Obtener y Guardar Tasas (ADAPTADA AL NUEVO MODELO) ---

def get_exchange_rates(force_save=False):
    """
    Función principal para obtener todas las tasas, aplicar lógica condicional de guardado 
    (separada para BCV y Mercado) y retornar las tasas principales.
    """
    
    # 1. Obtención de datos externos
    scraped_data = _scrape_bcv_rates()
    if scraped_data is None:
        scraped_data = {} 

    tasa_mercado_cruda = _get_mercado_rate()
    tasa_forex_eur_usd = fetch_forex_eur_usd_rate()
    
    tasa_bcv_usd = scraped_data.get('USD_BCV')
    date_info_raw = scraped_data.get('Fecha') 
    
    # Verificación crítica: Fallo si no tenemos los datos principales
    if not (tasa_bcv_usd and tasa_mercado_cruda):
        logger.error("Fallo la obtención de tasas críticas (USD BCV o USD Mercado). Retornando None.")
        return None, None, None

    # 2. Procesamiento de datos
    tasa_bcv_eur = scraped_data.get('EUR_BCV')
    bcv_eur_usd_implicita = 0.0
    if isinstance(tasa_bcv_usd, (int, float)) and isinstance(tasa_bcv_eur, (int, float)) and tasa_bcv_usd > 0:
        bcv_eur_usd_implicita = tasa_bcv_eur / tasa_bcv_usd
        
    date_info_clean = _convert_date_format(date_info_raw)
    tasa_mercado_redondeada = round(tasa_mercado_cruda, 0)
    now = datetime.now()
    now_iso = now.isoformat()
    current_date_str = date_info_clean if date_info_clean else now.strftime("%d/%m/%Y")

    # 3. Datos de la DB para la lógica condicional
    latest_data = get_latest_rates()
    latest_db_date = latest_data.get('date', '') if latest_data else ''
    latest_db_market_rate = latest_data.get('USD_MERCADO_CRUDA') if latest_data else None

    # ----------------------------------------------------
    # 4. LÓGICA DE GUARDADO CONDICIONAL
    # ----------------------------------------------------
    
    bcv_saved = False
    market_saved = False

    # A) Lógica BCV: Guardar solo si la fecha del BCV ha cambiado
    if current_date_str != latest_db_date:
        bcv_data_to_save = {
            'date': current_date_str,
            'USD_BCV': tasa_bcv_usd,
            'EUR_BCV': tasa_bcv_eur, 
            'CNY_BCV': scraped_data.get('CNY_BCV'),
            'TRY_BCV': scraped_data.get('TRY_BCV'),
            'RUB_BCV': scraped_data.get('RUB_BCV'), 
        }
        bcv_saved = save_bcv_rates(bcv_data_to_save)
    else:
        logger.info(f"Fecha BCV ({current_date_str}) no ha cambiado. Omitiendo inserción en BCV_RATES.")

    # B) Lógica de Mercado: Guardar si hay volatilidad O si se fuerza (para el reporte horario)
    
    # Calcular volatilidad
    if latest_db_market_rate is not None and latest_db_market_rate > 0:
        market_rate_change_percent = abs((tasa_mercado_cruda - latest_db_market_rate) / latest_db_market_rate)
    else:
        market_rate_change_percent = 1.0 # 100% de cambio si no hay datos previos (fuerza el primer guardado)
        
    if force_save or market_rate_change_percent > 0.001: # Umbral de 0.1%
        market_data_to_save = {
            'timestamp': now_iso,
            'USD_MERCADO_CRUDA': tasa_mercado_cruda,
            'EUR_USD_FOREX': tasa_forex_eur_usd,
        }
        market_saved = save_market_rates(market_data_to_save)
        
    else:
        logger.info(f"Volatilidad ({market_rate_change_percent*100:.3f}%) no supera el 0.1%. Omitiendo inserción en MARKET_RATES.")

    
    if bcv_saved or market_saved:
        logger.info(f"Proceso de guardado completado. BCV: {bcv_saved}, Mercado: {market_saved}.")
    elif not latest_data and not (bcv_saved or market_saved):
        logger.error("FALLO CRÍTICO: No se pudo insertar el registro inicial en la base de datos.")


    # 5. Retorno de las tasas principales
    # Retornamos los valores recién obtenidos para usarlos inmediatamente en el bot si es necesario
    return tasa_bcv_usd, tasa_mercado_cruda, tasa_mercado_redondeada