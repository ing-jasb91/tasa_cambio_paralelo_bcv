# from app.api_data import get_exchange_rates

# class DivisaCalculator:
#     def __init__(self):
#         self.tasa_bcv, self.tasa_mercado_cruda, self.tasa_mercado_redondeada = get_exchange_rates()
#         if not all([self.tasa_bcv, self.tasa_mercado_cruda, self.tasa_mercado_redondeada]):
#             print("No se pudo obtener la información de las tasas de cambio. Saliendo.")
#             exit()
        
#     def display_current_rates(self):
#         print(f"Tasa Oficial (BCV): {self.tasa_bcv:.4f} Bs/USD")
#         print(f"Tasa de Mercado (consultada): {self.tasa_mercado_cruda:.4f} Bs/USD")
#         print(f"Tasa de Mercado (redondeada): {self.tasa_mercado_redondeada:.4f} Bs/USD")
# app/calculator.py

from app.api_data import get_exchange_rates

class DivisaCalculator:
    def __init__(self):
        self.tasa_bcv, self.tasa_mercado_cruda, self.tasa_mercado_redondeada = get_exchange_rates()
        if not all([self.tasa_bcv, self.tasa_mercado_cruda, self.tasa_mercado_redondeada]):
            print("No se pudo obtener la información de las tasas de cambio. Saliendo.")
            exit()
        
    def get_exchange_rates_report(self):
        """Genera un reporte completo de las tasas de cambio."""
        
        # Diferencia cambiaria en cifras
        diferencia_cifras = self.tasa_mercado_cruda - self.tasa_bcv
        
        # Diferencia cambiaria en porcentaje
        diferencia_porcentaje = (diferencia_cifras / self.tasa_bcv) * 100
        
        # IAC (Índice de Ahorro para el Comprador)
        iac = ((self.tasa_mercado_cruda / self.tasa_bcv) - 1) * 100
        
        # FPC (Factor de Poder de Compra)
        fpc = self.tasa_mercado_cruda / self.tasa_bcv

        reporte = (
            f"📊 *Reporte de Tasas de Cambio*\n\n"
            f"Tasa Oficial (BCV): {self.tasa_bcv:.4f} Bs/USD\n"
            f"Tasa Mercado (Cruda): {self.tasa_mercado_cruda:.4f} Bs/USD\n"
            f"Tasa Mercado (Redondeada): {self.tasa_mercado_redondeada:.4f} Bs/USD\n\n"
            f"Diferencia Cambiaria: {diferencia_cifras:.4f} Bs/USD ({diferencia_porcentaje:.2f}%)\n"
            f"IAC (%): {iac:.2f}%\n"
            f"FPC: {fpc:.4f}\n"
        )
        return reporte

    def display_current_rates(self):
        # Esta función ahora será llamada por el nuevo método
        print(self.get_exchange_rates_report())
        
    def run_analysis_de_compra(self):
        try:
            costo_producto = float(input("\nIngresa el costo del producto en USD: "))
            dolares_disponibles = float(input("Ingresa la cantidad de divisas que tienes en USD: "))
        except ValueError:
            print("Por favor, ingresa un número válido.")
            return

        tasas_a_evaluar = [self.tasa_mercado_redondeada - (i * 10) for i in range(6)]
        
        print("\n" + "=" * 115)
        print(f"Análisis de Compra | Producto: ${costo_producto:.2f} | Divisas: ${dolares_disponibles:.2f}")
        print("=" * 115)
        print("{:<12} | {:<8} | {:<8} | {:<18} | {:<18} | {:<25}".format(
            "Tasa", "IAC (%)", "FPC", "Poder de Compra", "Monto Exacto", "Resultado"
        ))
        print("-" * 115)

        for tasa in tasas_a_evaluar:
            poder_compra = dolares_disponibles * (tasa / self.tasa_bcv)
            suficiente = poder_compra >= costo_producto
            diferencia = poder_compra - costo_producto

            IAC = ((tasa / self.tasa_bcv) - 1) * 100
            FPC = tasa / self.tasa_bcv
            monto_exacto = costo_producto * (self.tasa_bcv / tasa)

            estado = "Sí (Sobra: ${:.4f})".format(diferencia) if suficiente else "No (Falta: ${:.4f})".format(abs(diferencia))

            print("{:<12.4f} | {:<8.4f} | {:<8.4f} | {:<18.4f} | {:<18.4f} | {:<25}".format(
                tasa,
                IAC,
                FPC,
                poder_compra,
                monto_exacto,
                estado
            ))
        print("=" * 115)

    def run_costo_de_oportunidad(self):
        try:
            dolares_a_evaluar = float(input("\nIngresa la cantidad de divisas a evaluar: "))
        except ValueError:
            print("Por favor, ingresa un número válido.")
            return

        tasas_a_evaluar = [self.tasa_mercado_redondeada - (i * 10) for i in range(1, 6)]
        
        print("\n" + "=" * 135)
        print(f"Costo de Oportunidad por Negociación | Divisas: ${dolares_a_evaluar:.2f}")
        print("=" * 135)
        print("{:<12} | {:<12} | {:<15} | {:<15} | {:<12} | {:<18} | {:<25}".format(
            "Tasa", "Pérdida (Bs)", "Pérdida ($BCV)", "Pérdida ($Merc.)", "IAC (%)", "Factor de Pérdida", "Costo de Oportunidad"
        ))
        print("-" * 135)

        valor_max_bolivares = dolares_a_evaluar * self.tasa_mercado_redondeada

        for tasa_actual in tasas_a_evaluar:
            valor_actual_bolivares = dolares_a_evaluar * tasa_actual
            perdida_bolivares = valor_max_bolivares - valor_actual_bolivares
            perdida_usd_bcv = perdida_bolivares / self.tasa_bcv
            perdida_usd_mercado = perdida_bolivares / self.tasa_mercado_redondeada
            factor_perdida = 1 - (tasa_actual / self.tasa_mercado_redondeada)
            IAC = ((self.tasa_mercado_redondeada / tasa_actual) - 1) * 100

            print("{:<12.4f} | {:<12.2f} | {:<15.4f} | {:<15.4f} | {:<12.4f} | {:<18.4f} | {:<25}".format(
                tasa_actual,
                perdida_bolivares,
                perdida_usd_bcv,
                perdida_usd_mercado,
                IAC,
                factor_perdida,
                "Pérdida por no vender a la mejor tasa"
            ))
        print("=" * 135)