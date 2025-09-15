# app/main.py

from app.api_data import get_exchange_rates
from app.calculations import check_purchase_scenarios

def main():
    tasa_bcv, tasa_mercado_cruda, tasa_mercado_redondeada = get_exchange_rates()

    if tasa_bcv and tasa_mercado_cruda and tasa_mercado_redondeada:
        print(f"Tasa Oficial (BCV): {tasa_bcv:.4f} Bs/USD")
        print(f"Tasa de Mercado (consultada): {tasa_mercado_cruda:.4f} Bs/USD")
        print(f"Tasa de Mercado (redondeada): {tasa_mercado_redondeada:.4f} Bs/USD")

        # El resto del código se mantiene igual
        try:
            costo_producto = float(input("\nIngresa el costo del producto en USD: "))
            dolares_disponibles = float(input("Ingresa la cantidad de divisas que tienes en USD: "))
        except ValueError:
            print("Por favor, ingresa un número válido.")
            return

        # Generar las tasas para los escenarios
        tasas_a_evaluar = [tasa_mercado_redondeada - (i * 10) for i in range(6)]

        # Llamar a la función que revisa los escenarios
        resultados = check_purchase_scenarios(dolares_disponibles, costo_producto, tasa_bcv, tasas_a_evaluar)
        
        print("\n" + "=" * 115)
        print(f"Análisis de Compra | Producto: ${costo_producto:.2f} | Divisas: ${dolares_disponibles:.2f}")
        print("=" * 115)
        print("{:<12} | {:<8} | {:<8} | {:<18} | {:<18} | {:<25}".format(
            "Tasa", "IAC (%)", "FPC", "Poder de Compra", "Monto Exacto", "Resultado"
        ))
        print("-" * 115)

        for resultado in resultados:
            tasa = resultado['tasa']
            poder_compra = dolares_disponibles * (tasa / tasa_bcv)
            suficiente = resultado['suficiente']
            diferencia = resultado['diferencia']

            # Calcular el IAC, FPC y el monto exacto
            IAC = ((tasa / tasa_bcv) - 1) * 100
            FPC = tasa / tasa_bcv
            monto_exacto = costo_producto * (tasa_bcv / tasa)

            if suficiente:
                estado = "Sí (Sobra: ${:.4f})".format(diferencia)
            else:
                estado = "No (Falta: ${:.4f})".format(abs(diferencia))
            
            print("{:<12.4f} | {:<8.4f} | {:<8.4f} | {:<18.4f} | {:<18.4f} | {:<25}".format(
                tasa,
                IAC,
                FPC,
                poder_compra,
                monto_exacto,
                estado
            ))
        print("=" * 115)
        
if __name__ == "__main__":
    main()