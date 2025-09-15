import requests

# URL del endpoint de dolarapi.com que contiene ambas tasas
api_url = "https://ve.dolarapi.com/v1/dolares"

try:
    response = requests.get(api_url)
    data = response.json()

    # Buscar la tasa oficial (BCV) y la tasa paralela en el JSON
    tasa_bcv = next(item for item in data if item["fuente"] == "oficial")["promedio"]
    tasa_mercado = next(item for item in data if item["fuente"] == "paralelo")["promedio"]

    # Calcular los factores de conversión
    factor_para_vender = tasa_bcv / tasa_mercado
    factor_poder_compra = tasa_mercado / tasa_bcv

    print("--- Resultados de la API ---")
    print(f"Tasa Oficial (BCV): {tasa_bcv:.2f} Bs/USD")
    print(f"Tasa Paralela: {tasa_mercado:.2f} Bs/USD")

    print("\n--- Factores Calculados ---")
    print(f"Factor para vender tus dólares (ahorro): {factor_para_vender:.2f}")
    print(f"Factor para calcular tu poder de compra: {factor_poder_compra:.2f}")

    # Ejemplo práctico con una compra de $1000
    dolares_a_vender_por_1000 = 1000 * factor_para_vender
    poder_compra_con_1000 = 1000 * factor_poder_compra

    print("\n--- Ejemplo con $1000 ---")
    print(f"Para una compra de $1000 (a tasa BCV), solo necesitas vender {dolares_a_vender_por_1000:.2f} dólares en el mercado.")
    print(f"Si vendes $1000 en el mercado, obtienes el poder de compra de ${poder_compra_con_1000:.2f} (a tasa BCV).")

except requests.exceptions.RequestException as e:
    print(f"Error al obtener los datos de la API: {e}")
except (KeyError, StopIteration):
    print("La estructura de la API ha cambiado o los datos no están disponibles.")