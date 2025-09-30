# test_data.py

from src.data_fetcher import get_exchange_rates, _scrape_bcv_rates
from src.database_manager import get_latest_rates
import logging

# Configuración básica de logging para ver advertencias (como IntegrityError)
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')

# --- PRUEBA 1: Extracción y Guardado (ESTO HACE LA INSERCIÓN) ---
print("--- Ejecutando extracción y guardado ---")
tasa_bcv_usd, tasa_mercado_cruda, tasa_mercado_redondeada = get_exchange_rates()

if tasa_bcv_usd:
    print(f"\n✅ Extracción Completa (get_exchange_rates):")
    print(f"  Tasa BCV (USD):       {tasa_bcv_usd} Bs/USD")
    print(f"  Tasa Mercado (Cruda): {tasa_mercado_cruda} Bs/USD")
else:
    print("❌ Fallo crítico en la extracción de tasas.")

# --- PRUEBA 2: Consulta de la última tasa ---
print("\n--- Resultado de get_latest_rates() (Consulta SQL) ---")
latest_data = get_latest_rates()

if latest_data:
    print("✅ Último registro en DB:")
    # Imprime un formato legible del diccionario, excluyendo el ID y el timestamp
    print(f"  Fecha: {latest_data.get('date')}")
    print(f"  USD BCV: {latest_data.get('USD_BCV')}")
    print(f"  EUR BCV: {latest_data.get('EUR_BCV')}")
    print(f"  USD Mercado: {latest_data.get('USD_MERCADO_CRUDA')}")
    print(f"  Otras divisas: CNY={latest_data.get('CNY_BCV')}, TRY={latest_data.get('TRY_BCV')}, RUB={latest_data.get('RUB_BCV')}")
else:
    print("❌ No se encontraron registros en la base de datos.")