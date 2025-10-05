# src/calculator.py
import logging
from src.database_manager import get_latest_rates, get_24h_market_summary 
# Asegúrate de importar get_24h_market_summary si la usas en el futuro para análisis
# (Aunque no está aquí, es buena práctica si la vas a usar).

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --- FUNCIÓN AUXILIAR DE FORMATO (DISPONIBLE PARA IMPORTACIÓN) ---
def format_currency(amount, decimals=2):
    """
    Formatea el monto con separador de miles (punto) y decimales (coma)
    para el formato de Venezuela.
    """
    if amount is None or amount == 0:
        return "0,00" if decimals > 0 else "0"
    
    # Formato: X.XXX,XX
    return f"{amount:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


class ExchangeRateCalculator:
    
    def __init__(self):
        self.latest_rates = get_latest_rates()
        self.valid = False 
        self._set_rates()

    def _set_rates(self):
        """Carga y calcula todas las tasas necesarias desde el último registro de la DB."""
        if not self.latest_rates:
            logger.warning("No se encontraron tasas en la DB.")
            return
            
        self.USD_BCV = float(self.latest_rates.get('USD_BCV', 0.0))
        self.USD_MERCADO_CRUDA = float(self.latest_rates.get('USD_MERCADO_CRUDA', 0.0))
        self.EUR_BCV = float(self.latest_rates.get('EUR_BCV', 0.0))
        self.EUR_USD_FOREX = float(self.latest_rates.get('EUR_USD_FOREX', 0.0))

        if self.USD_BCV > 0.0 and self.USD_MERCADO_CRUDA > 0.0 and self.EUR_USD_FOREX > 0.0:
            self.valid = True
            # Tasa redondeada a la decena (ej: 35.80 -> 40.00, 31.20 -> 30.00)
            self.USD_MERCADO_REDONDEADA = round(self.USD_MERCADO_CRUDA / 10) * 10
            self.EUR_MERCADO_CRUDA = self.USD_MERCADO_CRUDA * self.EUR_USD_FOREX
            self.EUR_MERCADO_REDONDEADA = round(self.EUR_MERCADO_CRUDA / 10) * 10
        else:
            logger.warning("Faltan tasas críticas (BCV USD o Mercado USD o Forex EUR/USD). Cálculos deshabilitados.")

    def is_valid(self):
        """Verifica si la calculadora se inicializó con tasas válidas."""
        return self.valid

    def _get_currency_rates(self, currency):
        """Devuelve las tasas requeridas (BCV, Mercado Cruda, Mercado Redondeada) para la divisa solicitada."""
        if currency.upper() == 'USD':
            return self.USD_BCV, self.USD_MERCADO_CRUDA, self.USD_MERCADO_REDONDEADA, 'USD', '🇺🇸'
        elif currency.upper() == 'EUR':
            return self.EUR_BCV, self.EUR_MERCADO_CRUDA, self.EUR_MERCADO_REDONDEADA, 'EUR', '🇪🇺'
        # El BCV no se usa como divisa base en estos flujos, pero se incluye para completar
        elif currency.upper() == 'BCV':
            # Solo se necesita la tasa BCV para la conversión, las otras son irrelevantes
            return self.USD_BCV, None, None, 'BCV', '🏦' 
        else:
            return None, None, None, None, None

    # ----------------------------------------------------------------------
    # 1. ANÁLISIS DE COMPRA 
    # ----------------------------------------------------------------------
    def get_compra_report(self, cost_amount, available_amount, currency='USD'):
        """
        Calcula el poder de compra para una divisa específica (USD o EUR) con formato estético.
        """
        tasa_bcv, _, tasa_mercado_redondeada, code, emoji = self._get_currency_rates(currency)
        if not tasa_bcv or not tasa_mercado_redondeada:
            return f"❌ No hay tasas válidas para {code}.", tasa_mercado_redondeada

        # Tasas a evaluar: Una más 10, y cinco menos 10 (con paso de 10)
        tasas_a_evaluar = [tasa_mercado_redondeada + 10] + [tasa_mercado_redondeada - (i * 10) for i in range(0, 6)]
        tasas_a_evaluar = sorted(list(set(tasas_a_evaluar)), reverse=True)
        
        # CONSTRUCCIÓN DEL REPORTE
        reporte = (
            f"🛒 *Análisis de Poder de Compra ({emoji} {code})*\n"
            f"💰 *Precio Producto:* {format_currency(cost_amount)} {code}\n"
            f"💵 *Capital Disponible:* {format_currency(available_amount)} {code}\n"
            f"_(Tasa BCV Referencial: {format_currency(tasa_bcv, decimals=4)} Bs)_\n\n"
            f"--- *Escenarios de Tasa* ---\n"
        )
        
        for tasa in tasas_a_evaluar:
            # La fórmula original es: (CantidadDisponible * TasaMercado) / TasaBCV
            # Sin embargo, para simular el poder de compra con tasa 'X', el cálculo correcto es:
            # PoderCompra = (Disponible en Bs a TasaX) / TasaBCV
            # Asumiendo que el poder de compra se mide por cuántas unidades de BCV obtienes por tu divisa
            
            # Una interpretación más simple y común: ¿Qué puedes comprar en bolívares con tu divisa,
            # y cuánto vale ese producto en bolívares según la tasa BCV?
            
            # Simplificamos a: ¿Cuál es el valor del capital disponible en bolívares a esta tasa 'X'?
            capital_en_bs_a_tasa = available_amount * tasa
            
            # Y cuánto de ese capital cubre el costo del producto en bolívares (usando Tasa BCV como base)
            costo_en_bs_a_bcv = cost_amount * tasa_bcv
            
            # Poder de compra (en unidades del producto)
            unidades_comprables = capital_en_bs_a_tasa / costo_en_bs_a_bcv
            
            # El resultado se presenta en la divisa original (USD/EUR)
            poder_compra = capital_en_bs_a_tasa / tasa_bcv 
            
            suficiente = poder_compra >= cost_amount
            diferencia = poder_compra - cost_amount
            
            icono_tasa = "🎯" if abs(tasa - tasa_mercado_redondeada) < 0.01 else "📊"
            icono_resultado = "🟢" if suficiente else "🔴"
            
            reporte += (
                f"\n{icono_tasa} Tasa: *{format_currency(tasa, decimals=2)} Bs*\n"
                f"   • Poder de Compra: *{format_currency(poder_compra, decimals=2)} {code}*\n"
                f"   • Resultado Neto: {icono_resultado} *{format_currency(abs(diferencia))}* {code}\n"
            )

        # PIE DE PÁGINA
        reporte += (
            f"\n═════════════════════\n"
            f"🎯 Tasa Redondeada de Referencia."
        )
        
        return reporte, tasa_mercado_redondeada

    # ----------------------------------------------------------------------
    # 2. CONVERSIÓN DE DIVISAS (Precio en Bs) 
    # ----------------------------------------------------------------------
    def get_conversion_report(self, price_amount, currency='USD'):
        """Convierte un precio de USD/EUR/BCV a Bolívares, sin considerar el IGTF."""
        
        # Lógica para manejar la conversión a BCV. Si la selección fue BCV, usamos USD_BCV como tasa base
        if currency.upper() == 'BCV':
            tasa_base = self.USD_BCV # Tasa para BCV
            tasa_ref = self.USD_MERCADO_CRUDA
            code, emoji = 'USD', '🏦'
            
            # Precio es la cantidad de USD a convertir
            precio_bcv = price_amount * tasa_base
            
            reporte = (
                f"💱 *Conversión a Tasa BCV ({emoji} {code})*\n"
                f"Monto Base: *{format_currency(price_amount)} {code}*\n\n"
                f"--- *Tasas Clave (Bs/{code})* ---\n"
                f"🏦 Tasa BCV: *{format_currency(tasa_base, decimals=4)}*\n"
                f"💸 Mercado (Ref.): *{format_currency(tasa_ref, decimals=4)}*\n\n"
                f"--- *Resultado Final* ---\n"
                f"Precio Final: *{format_currency(precio_bcv)} Bs*\n"
            )
            return reporte, tasa_base
            
        
        # Lógica para USD o EUR
        tasa_bcv, tasa_mercado_cruda, tasa_mercado_redondeada, code, emoji = self._get_currency_rates(currency)
        if not tasa_bcv or not tasa_mercado_cruda:
            return f"❌ No hay tasas válidas para {code}.", tasa_mercado_redondeada

        precio_bcv = price_amount * tasa_bcv
        precio_mercado = price_amount * tasa_mercado_cruda 
        
        diferencia_cifras = tasa_mercado_cruda - tasa_bcv
        diferencia_porcentaje = (diferencia_cifras / tasa_bcv) * 100
        diferencia_total_bs = precio_mercado - precio_bcv 

        # 1. ENCABEZADO Y RESUMEN PRINCIPAL
        reporte = (
            f"💱 *Conversión de Precios ({emoji} {code})*\n"
            f"Monto Base: *{format_currency(price_amount)} {code}*\n\n"
            f"--- *Tasas Clave (Bs/{code})* ---\n"
            f"🏦 BCV: *{format_currency(tasa_bcv, decimals=4)}*\n"
            f"💸 Mercado (Cruda): *{format_currency(tasa_mercado_cruda, decimals=4)}*\n"
            f" _(Brecha vs BCV: {format_currency(diferencia_cifras, decimals=4)} Bs | `{diferencia_porcentaje:.2f}%`)_\n\n"
            f"--- *Resultado Final (Precio en Bs)* ---\n"
            f"Precio BCV: {format_currency(precio_bcv)}\n"
            f"Precio Mercado (Puro): *{format_currency(precio_mercado)}*\n"
            f"Diferencia total: {format_currency(diferencia_total_bs)} Bs\n\n"
            f"--- *Precios por Rango de Tasas* ---\n"
        )

        tasas_a_evaluar = [tasa_mercado_redondeada + 10] + [tasa_mercado_redondeada - (i * 10) for i in range(0, 6)]
        tasas_a_evaluar = sorted(list(set(tasas_a_evaluar)), reverse=True)
        
        for tasa in tasas_a_evaluar:
            precio_rango = price_amount * tasa
            diferencia_precio = precio_rango - precio_bcv 
            
            icono_tasa = "🎯" if abs(tasa - tasa_mercado_redondeada) < 0.01 else "💰"
            
            reporte += (
                f"\n{icono_tasa} Tasa: *{format_currency(tasa, decimals=2)} Bs*\n"
                f"   • Precio Final: *{format_currency(precio_rango)} Bs*\n"
                f"   • Margen vs BCV: +{format_currency(diferencia_precio)} Bs\n"
            )
        
        return reporte, tasa_mercado_redondeada


    # ----------------------------------------------------------------------
    # 3. COSTO DE OPORTUNIDAD 
    # ----------------------------------------------------------------------
    def get_oportunidad_report(self, sell_amount, currency='USD'):
        """
        Calcula el costo de oportunidad (pérdida) de vender una divisa por debajo
        de la tasa de mercado redondeada (mejor precio), con formato estético.
        """
        tasa_bcv, _, tasa_mercado_redondeada, code, emoji = self._get_currency_rates(currency)
        if not tasa_bcv or not tasa_mercado_redondeada:
            return f"❌ No hay tasas válidas para {code}.", tasa_mercado_redondeada

        tasas_a_evaluar = [tasa_mercado_redondeada + 10] + [tasa_mercado_redondeada - (i * 10) for i in range(0, 6)]
        tasas_a_evaluar = sorted(list(set(tasas_a_evaluar)), reverse=True)
        
        valor_max_bolivares = sell_amount * tasa_mercado_redondeada
        
        # CONSTRUCCIÓN DEL REPORTE
        reporte = (
            f"💸 *Costo de Oportunidad ({emoji} {code})*\n"
            f"Monto a Vender: *{format_currency(sell_amount)} {code}*\n"
            f"_(Tasa Referencial: *{format_currency(tasa_mercado_redondeada, decimals=2)} Bs*)_\n\n"
            f"--- *Pérdida por Tasa de Venta* ---\n"
        )
        
        for tasa_actual in tasas_a_evaluar:
            valor_actual_bolivares = sell_amount * tasa_actual
            perdida_bolivares = valor_max_bolivares - valor_actual_bolivares
            
            perdida_divisa = perdida_bolivares / tasa_mercado_redondeada 
            iac_porcentaje = (1 - (tasa_actual / tasa_mercado_redondeada)) * 100
            
            # Lógica de íconos y formato
            if abs(tasa_actual - tasa_mercado_redondeada) < 0.01:
                icono = "👑" # Tasa ideal
                perdida_bs_str = "*0,00 Bs*"
                perdida_code_str = "0,00"
                iac_str = "`0.00%`"
            elif tasa_actual > tasa_mercado_redondeada:
                icono = "🎁" # Ganancia (vendiendo más caro que el referencial)
                perdida_bs_str = f"*+{format_currency(perdida_bolivares * -1, decimals=2)} Bs*" # Mostrar positivo
                perdida_code_str = f"+{format_currency(perdida_divisa * -1, decimals=2)}"
                iac_str = f"`{iac_porcentaje:.2f}%`"
            else:
                icono = "💔" # Pérdida
                perdida_bs_str = f"*{format_currency(perdida_bolivares, decimals=2)} Bs*"
                perdida_code_str = format_currency(perdida_divisa, decimals=2)
                iac_str = f"`{iac_porcentaje:.2f}%`"
            
            reporte += (
                f"\n{icono} Tasa: *{format_currency(tasa_actual, decimals=2)} Bs*\n"
                f"   • Pérdida Neta (Bs): {perdida_bs_str}\n"
                f"   • Pérdida en {code}: {perdida_code_str} {code}\n"
                f"   • IAC (Aceptación de Costo): {iac_str}\n"
            )

        # PIE DE PÁGINA
        reporte += (
            f"\n═════════════════════\n"
            f"💔 Pérdida por negociar bajo el referencial.\n"
            f"👑 Tasa de Referencia de Venta."
        )
        
        return reporte, tasa_mercado_redondeada

    # ----------------------------------------------------------------------
    # 4. REPORTE GENERAL
    # ----------------------------------------------------------------------
    def get_exchange_rates_report(self):
        """Genera un reporte completo de las tasas de cambio (principalmente USD)."""
        if not self.is_valid():
            return "❌ No se pudieron obtener las tasas de cambio desde la base de datos."
            
        tasa_bcv = self.USD_BCV
        tasa_mercado_cruda = self.USD_MERCADO_CRUDA

        diferencia_cifras = tasa_mercado_cruda - tasa_bcv
        diferencia_porcentaje = (diferencia_cifras / tasa_bcv) * 100
        
        reporte = (
            f"📊 *Reporte de Tasas de Cambio*\n\n"
            f"Tasa Oficial (BCV): {format_currency(tasa_bcv, decimals=4)} Bs/USD\n"
            f"Tasa Mercado (Cruda): {format_currency(tasa_mercado_cruda, decimals=4)} Bs/USD\n"
            f"Tasa Mercado (Redondeada): {format_currency(self.USD_MERCADO_REDONDEADA, decimals=4)} Bs/USD\n\n"
            f"Diferencia Cambiaria: {format_currency(diferencia_cifras, decimals=4)} Bs/USD ({diferencia_porcentaje:.2f}%)\n"
        )
        return reporte
    
    def display_current_rates(self):
        print(self.get_exchange_rates_report())