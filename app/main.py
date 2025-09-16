# app/main.py

from app.api_data import get_exchange_rates
from app.calculations import check_purchase_scenarios, calculate_opportunity_cost

def main():
    tasa_bcv, tasa_mercado_cruda, tasa_mercado_redondeada = get_exchange_rates()

    if tasa_bcv and tasa_mercado_cruda and tasa_mercado_redondeada:
        print(f"Tasa Oficial (BCV): {tasa_bcv:.4f} Bs/USD")
        print(f"Tasa de Mercado (consultada): {tasa_mercado_cruda:.4f} Bs/USD")
        print(f"Tasa de Mercado (redondeada): {tasa_mercado_redondeada:.4f} Bs/USD")

        try:
            dolares_a_evaluar = float(input("\nIngresa la cantidad de divisas a evaluar: "))
        except ValueError:
            print("Por favor, ingresa un número válido.")
            return

        # Generar las tasas para los escenarios (excluimos la tasa de mercado redondeada actual de la tabla de costo)
        # Si quieres incluirla, deberías ajustar el rango o la lógica. Por ahora, la omitimos para ver el "costo" de las menores.
        tasas_a_evaluar = [tasa_mercado_redondeada - (i * 10) for i in range(1, 6) if tasa_mercado_redondeada - (i * 10) > 0]

        # --- Tabla de Costo de Oportunidad ---
        resultados_costo = calculate_opportunity_cost(
            dolares_a_evaluar, tasa_mercado_redondeada, tasas_a_evaluar
        )

        # Ajustamos los anchos de las columnas y el total de la tabla
        separador_ancho = 125
        print("\n" + "=" * separador_ancho)
        print(f"Costo de Oportunidad por Negociación | Divisas: ${dolares_a_evaluar:.2f}")
        print("=" * separador_ancho)
        # Ajustamos los anchos: Tasa(12), Pérdida(Bs)(15), Pérdida($BCV)(15), Pérdida($Merc.)(15), Fact. Pérdida(18), Costo Oportunidad(30)
        print("{:<12} | {:<15} | {:<15} | {:<15} | {:<18} | {:<30}".format(
            "Tasa", "Pérdida (Bs)", "Pérdida ($BCV)", "Pérdida ($Merc.)", "Fact. Pérdida", "Costo de Oportunidad"
        ))
        print("-" * separador_ancho)

        for resultado in resultados_costo:
            # Asegurarnos de que la tasa BCV fija en calculations.py sea la correcta
            # Si tasa_bcv no está accesible aquí, deberías pasarla como argumento a calculate_opportunity_cost
            tasa_bcv_fija = 160.4479 # Debe coincidir con la usada en calculations.py o ser pasada como argumento
            
            print("{:<12.4f} | {:<15.2f} | {:<15.4f} | {:<15.4f} | {:<18.4f} | {:<30}".format(
                resultado['tasa'],
                resultado['perdida_bolivares'],
                resultado['perdida_usd_bcv'],
                resultado['perdida_usd_mercado'],
                resultado['factor_perdida'],
                "Pérdida por no vender a la mejor tasa" # Texto fijo para la última columna
            ))
        print("=" * separador_ancho)
        
if __name__ == "__main__":
    main()