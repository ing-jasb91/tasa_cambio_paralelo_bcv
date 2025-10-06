# src/market_fetcher.py

import requests
import logging

# --- CONFIGURACIÓN DE LOGGING: Asegura que los mensajes se vean ---
# Configuramos el nivel de registro global a INFO y el formato.
# logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(message)s') 
logger = logging.getLogger(__name__)

# Nota: Los umbrales de MIN_ORDERS y MIN_FINISH_RATE ya no se usan para
# un filtrado estricto, sino que están incorporados en la lógica de PONDERACIÓN.

def fetch_binance_p2p_rate():
    """
    Obtiene los 10 mejores anuncios de USDT/VES y calcula una tasa promedio
    ponderada basada en el Factor de Confianza (Órdenes * Tasa de Finalización)
    de cada anunciante.
    """
    URL = 'https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search' 
    HEADERS = {
        'Accept': '*/*',
        'Content-Type': 'application/json',
        # User-Agent es CRÍTICO para simular un navegador
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    }
    PAYLOAD = {
        # Obtenemos los 10 mejores precios para promediar
        "asset": "USDT",
        "fiat": "VES",
        "tradeType": "BUY",
        "page": 1,
        "rows": 20,  # Pedimos 30 anuncios para tener más datos
        "filterType": "all",
        "payTypes": [] 
    }

    try:
        logger.info("Conectando con Binance P2P API para obtener la tasa del mercado (Promedio Ponderado)...")
        response = requests.post(URL, headers=HEADERS, json=PAYLOAD, timeout=10)
        response.raise_for_status() 
        data = response.json()
        
        if data and data.get('data'):
            
            total_weighted_rate = 0.0
            total_weight = 0.0
            best_price_fallback = None # Para usar como fallback si el peso total es cero
            
            # --- CÁLCULO DEL PROMEDIO PONDERADO ---
            for ad in data['data']:
                adv_data = ad.get('adv', {})
                advertiser_data = ad.get('advertiser', {})
                
                # 1. Extracción y validación de datos
                try:
                    price = float(adv_data.get('price'))
                    order_count = advertiser_data.get('monthOrderCount', 0) 
                    finish_rate = float(advertiser_data.get('monthFinishRate', 0.0))
                except (TypeError, ValueError, IndexError):
                    continue # Saltar si algún valor es inválido
                
                # Si es el primer anuncio válido, guardamos su precio para el fallback
                if best_price_fallback is None:
                    best_price_fallback = price

                # 2. Calcular el Factor de Confianza (Peso)
                # Peso = Órdenes Completadas del Mes * Tasa de Finalización (0.0 a 1.0)
                weight = order_count * finish_rate
                
                if weight > 0:
                    # 3. Sumar el Producto de la Tasa por el Peso
                    total_weighted_rate += (price * weight)
                    # 4. Sumar el Peso
                    total_weight += weight
            
            # 5. Calcular el Promedio Ponderado
            if total_weight > 0:
                weighted_average_rate = total_weighted_rate / total_weight
                logger.info(f"Tasa de mercado PONDERADA calculada: {weighted_average_rate:.4f} Bs/USDT (Peso Total: {total_weight:.2f})")
                return weighted_average_rate
            elif best_price_fallback is not None:
                logger.warning("No se pudieron calcular pesos válidos. Usando la mejor oferta como fallback.")
                return best_price_fallback
            else:
                # No hay anuncios en los datos
                logger.warning("Respuesta de Binance P2P válida, pero no se encontraron anuncios para el cálculo.")
                return None

    except requests.exceptions.HTTPError as e:
        logger.error(f"ERROR HTTP {e.response.status_code}: Fallo al conectar con Binance P2P. ¿Endpoint o Payload incorrecto? Detalle: {e}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"ERROR DE CONEXIÓN: Fallo de red o timeout. Detalle: {e}")
        return None
    except Exception as e:
        logger.error(f"ERROR INESPERADO: {e}")
        return None


if __name__ == '__main__':
    print("\n--- Ejecutando Prueba de Tasa de Mercado P2P (Ponderada) ---")
    
    # Restablecer el formato de logging si es necesario, aunque ya está al inicio
    # logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(message)s') 

    tasa = fetch_binance_p2p_rate()
    
    if tasa:
        print(f"\n✅ Prueba Exitosa. Tasa de Mercado Ponderada Obtenida: {tasa:.4f} Bs/USDT")
    else:
        print("\n❌ Prueba Fallida. No se pudo obtener la tasa de mercado.")
    print("--------------------------------------------------")