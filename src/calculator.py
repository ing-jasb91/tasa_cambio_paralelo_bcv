# src/calculator.py

# Importamos SOLO lo que necesitamos de la DB
from src.database_manager import get_latest_rates 

class DivisaCalculator:
    def __init__(self):
        # 1. Obtener los datos del último registro de la base de datos
        latest_rates = get_latest_rates()
        
        if not latest_rates:
            # Si no hay datos, inicializamos con None o 0 para evitar fallos
            self.tasa_bcv = None
            self.tasa_mercado_cruda = None
            self.tasa_mercado_redondeada = None
            return 
            
        # 2. Asignar las tasas desde el diccionario de la DB
        self.tasa_bcv = latest_rates.get('USD_BCV')
        self.tasa_mercado_cruda = latest_rates.get('USD_MERCADO_CRUDA')
        
        # 3. Calcular o obtener la tasa redondeada (si no está ya en la DB)
        if self.tasa_mercado_cruda:
            # Recalculamos la redondeada por si acaso (ajusta el redondeo según tu lógica)
            self.tasa_mercado_redondeada = round(self.tasa_mercado_cruda, -1) 
        else:
            self.tasa_mercado_redondeada = None
            
        # Verificación final de tasas críticas
        if not all([self.tasa_bcv, self.tasa_mercado_cruda, self.tasa_mercado_redondeada]):
             print("Advertencia: Se obtuvieron datos de la DB, pero faltan tasas críticas (USD/Mercado).")
            
    def is_valid(self):
        """Verifica si la calculadora se inicializó con tasas válidas."""
        return all([self.tasa_bcv, self.tasa_mercado_cruda, self.tasa_mercado_redondeada])

    def get_exchange_rates_report(self):
        """Genera un reporte completo de las tasas de cambio."""
        
        if not self.is_valid():
            return "❌ No se pudieron obtener las tasas de cambio desde la base de datos."
            
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
        
    # def run_analysis_de_compra(self, costo_producto: float, dolares_disponibles: float):
    #     """
    #     Calcula el análisis de compra en un rango de tasas.
    #     Adaptado para ser llamado directamente desde el bot (sin input()).
    #     """
    #     if not self.is_valid():
    #         return "❌ No se pudieron obtener las tasas de cambio para el análisis."
            
    #     tasas_a_evaluar = [self.tasa_mercado_redondeada - (i * 10) for i in range(6)]
        
    #     # Reemplaza la impresión de la consola con la generación de una cadena para el bot
    #     reporte_str = (
    #         f"\n💰 Análisis de Compra\n"
    #         f"Producto: ${costo_producto:.2f} | Divisas disponibles: ${dolares_disponibles:.2f}\n"
    #         f"===================================\n"
    #         f"{'Tasa':<12} | {'Poder Compra':<15} | {'Resultado':<20}\n"
    #         f"-----------------------------------\n"
    #     )
        
    #     for tasa in tasas_a_evaluar:
    #         poder_compra = dolares_disponibles * (tasa / self.tasa_bcv)
    #         suficiente = poder_compra >= costo_producto
    #         diferencia = poder_compra - costo_producto

    #         estado = f"Sí (+${diferencia:.2f})" if suficiente else f"No (-${abs(diferencia):.2f})"
            
    #         reporte_str += f"{tasa:<12.4f} | {poder_compra:<15.4f} | {estado:<20}\n"
            
    #     reporte_str += "===================================\n"
    #     return reporte_str

# src/calculator.py (dentro de la clase DivisaCalculator)

    def run_analysis_de_compra(self):
        if not self.is_valid():
            print("❌ No se pudieron obtener las tasas de cambio para el análisis.")
            return

        try:
            # Revertir al uso de input()
            costo_producto = float(input("\nIngresa el costo del producto en USD: "))
            dolares_disponibles = float(input("Ingresa la cantidad de divisas que tienes en USD: "))
        except ValueError:
            print("Por favor, ingresa un número válido.")
            return

        tasas_a_evaluar = [self.tasa_mercado_redondeada - (i * 10) for i in range(6)]
        
        # ... (Mantener la lógica de impresión de consola de tu código original) ...

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


    # def run_costo_de_oportunidad(self, dolares_a_evaluar: float):
    #     """
    #     Calcula el costo de oportunidad.
    #     Adaptado para ser llamado directamente desde el bot (sin input()).
    #     """
    #     if not self.is_valid():
    #         return "❌ No se pudieron obtener las tasas de cambio para el análisis."
            
    #     tasas_a_evaluar = [self.tasa_mercado_redondeada - (i * 10) for i in range(1, 6)]
        
    #     valor_max_bolivares = dolares_a_evaluar * self.tasa_mercado_redondeada

    #     # Reemplaza la impresión de la consola con la generación de una cadena para el bot
    #     reporte_str = (
    #         f"\n💸 Costo de Oportunidad\n"
    #         f"Divisas: ${dolares_a_evaluar:.2f}\n"
    #         f"===================================\n"
    #         f"{'Tasa':<10} | {'Pérdida (Bs)':<15} | {'Pérdida ($Merc.)':<15}\n"
    #         f"-----------------------------------\n"
    #     )
        
    #     for tasa_actual in tasas_a_evaluar:
    #         valor_actual_bolivares = dolares_a_evaluar * tasa_actual
    #         perdida_bolivares = valor_max_bolivares - valor_actual_bolivares
    #         perdida_usd_mercado = perdida_bolivares / self.tasa_mercado_redondeada

    #         reporte_str += f"{tasa_actual:<10.2f} | {perdida_bolivares:<15.2f} | {perdida_usd_mercado:<15.2f}\n"

    #     reporte_str += "===================================\n"
    #     return reporte_str
    
    # src/calculator.py (dentro de la clase DivisaCalculator)

    def run_costo_de_oportunidad(self):
        if not self.is_valid():
            print("❌ No se pudieron obtener las tasas de cambio para el análisis.")
            return
            
        try:
            # Revertir al uso de input()
            dolares_a_evaluar = float(input("\nIngresa la cantidad de divisas a evaluar: "))
        except ValueError:
            print("Por favor, ingresa un número válido.")
            return

        tasas_a_evaluar = [self.tasa_mercado_redondeada - (i * 10) for i in range(1, 6)]
        
        # ... (Mantener la lógica de impresión de consola de tu código original) ...
        
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