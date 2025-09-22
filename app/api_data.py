# app/api_data.py
import requests

def get_exchange_rates():
    """Obtiene las tasas de cambio del BCV y Paralelo de la API y redondea la tasa de mercado."""
    api_url = "https://ve.dolarapi.com/v1/dolares"
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()
        
        tasa_bcv = next(item for item in data if item["fuente"] == "oficial")["promedio"]
        tasa_mercado_cruda = next(item for item in data if item["fuente"] == "paralelo")["promedio"]
        
        # Redondear la tasa de mercado a la próxima decena
        tasa_mercado_redondeada = (int(tasa_mercado_cruda // 10) * 10) + 10
        
        return tasa_bcv, tasa_mercado_cruda, tasa_mercado_redondeada
    except requests.exceptions.RequestException as e:
        print(f"Error al obtener los datos de la API: {e}")
        return None, None, None
    except (KeyError, StopIteration):
        print("Error: La estructura de la API ha cambiado o los datos no están disponibles.")
        return None, None, None