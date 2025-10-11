# src/calculator.py
import logging
from src.database_manager import get_latest_rates, get_24h_market_summary, get_historical_rates
# Asegúrate de importar get_24h_market_summary si la usas en el futuro para análisis
# (Aunque no está aquí, es buena práctica si la vas a usar).
import pytz
from datetime import datetime
import numpy as np 

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


        # Tasas de BCV adicionales (CORRECCIÓN DEL ERROR)
        self.CNY_BCV = float(self.latest_rates.get('CNY_BCV', 0.0))
        self.TRY_BCV = float(self.latest_rates.get('TRY_BCV', 0.0))
        self.RUB_BCV = float(self.latest_rates.get('RUB_BCV', 0.0))

        if self.USD_BCV > 0.0 and self.USD_MERCADO_CRUDA > 0.0 and self.EUR_USD_FOREX > 0.0:
            self.valid = True
            
            # 🚨 LÍNEA AÑADIDA PARA RESOLVER EL ERROR 🚨
            # Calcula la tasa EUR/USD implícita (EUR_BCV / USD_BCV)
            self.EUR_USD_IMPLICITA = self.EUR_BCV / self.USD_BCV 

            # Tasa redondeada a la decena (ej: 35.80 -> 40.00, 31.20 -> 30.00)
            self.USD_MERCADO_REDONDEADA = round(self.USD_MERCADO_CRUDA / 10) * 10
            self.EUR_MERCADO_CRUDA = self.USD_MERCADO_CRUDA * self.EUR_USD_FOREX
            self.EUR_MERCADO_REDONDEADA = round(self.EUR_MERCADO_CRUDA / 10) * 10
        else:
            logger.warning("Faltan tasas críticas (BCV USD o Mercado USD o Forex EUR/USD). Cálculos deshabilitados.")

        # Tasa de Compra (Referencia USD a VEF)
        self.USD_MERCADO_COMPRA = self.USD_MERCADO_CRUDA * 1.02 # Tasa de Mercado + 2%
        # Tasa de Venta (Referencia VEF a USD)
        self.USD_MERCADO_VENTA = self.USD_MERCADO_CRUDA * 0.98  # Tasa de Mercado - 2%

        # 1. Tasa del Punto de Equilibrio (Break-Even Point) 🚨
        # Es la tasa a la que tengo que vender los VEF que compré a BCV para igualar el costo USD.
        # Se calcula asumiendo que el costo inicial de los dólares es BCV.
        if self.USD_BCV is not None and self.USD_MERCADO_COMPRA is not None:
            # Fórmula: Costo BCV / (1 - %Comisión)
            # Asumamos una comisión de venta de 0.5% sobre la transacción.
            COMISION_VENTA = 0.005
            self.USD_BREAK_EVEN = self.USD_BCV / (1 - COMISION_VENTA)
        else:
            self.USD_BREAK_EVEN = None 



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
            f"🛒 *Análisis de Poder de Compra ({emoji} {code})* \n"
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
                f"\n{icono_tasa} Tasa: *{format_currency(tasa, decimals=2)} Bs* \n"
                f"   • Poder de Compra: *{format_currency(poder_compra, decimals=2)} {code}* \n"
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
                f"💱 *Conversión a Tasa BCV ({emoji} {code})* \n\n"
                f"Monto Base: *{format_currency(price_amount)} {code}* \n\n"
                
                f"• *Tasas Clave (Bs/{code})* •\n" # <-- Separador visual más seguro que '---'
                f"🏦 Tasa BCV: *{format_currency(tasa_base, decimals=4)}* \n"
                f"💸 Mercado (Ref.): *{format_currency(tasa_ref, decimals=4)}* \n\n"
                
                f"• *Resultado Final* •\n"
                f"Precio Final: *{format_currency(precio_bcv)} Bs* \n"
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
            f"💱 *Conversión de Precios ({emoji} {code})* \n"
            f"Monto Base: *{format_currency(price_amount)} {code}* \n\n"
            f"--- *Tasas Clave (Bs/{code})* ---\n"
            f"🏦 BCV: *{format_currency(tasa_bcv, decimals=4)}* \n"
            f"💸 Mercado (Cruda): *{format_currency(tasa_mercado_cruda, decimals=4)}* \n"
            f" _(Brecha vs BCV: {format_currency(diferencia_cifras, decimals=4)} Bs | `{diferencia_porcentaje:.2f}%`)_\n\n"
            f"--- *Resultado Final (Precio en Bs)* ---\n"
            f"Precio BCV: {format_currency(precio_bcv)}\n"
            f"Precio Mercado (Puro): *{format_currency(precio_mercado)}* \n"
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
                f"\n{icono_tasa} Tasa: *{format_currency(tasa, decimals=2)} Bs* \n"
                f"   • Precio Final: *{format_currency(precio_rango)} Bs* \n"
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
            f"💸 *Costo de Oportunidad ({emoji} {code})* \n"
            f"Monto a Vender: *{format_currency(sell_amount)} {code}* \n"
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
                f"\n{icono} Tasa: *{format_currency(tasa_actual, decimals=2)} Bs* \n"
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
    def get_exchange_rates_report(self, summary_24h: dict = None):
        """Genera un reporte completo de las tasas de cambio (principalmente USD) con un resumen de 24h."""
        if not self.is_valid():
            return "❌ No se pudieron obtener las tasas de cambio desde la base de datos."
            
        tasa_bcv_usd = self.USD_BCV
        tasa_bcv_eur = self.EUR_BCV
        tasa_mercado_cruda = self.USD_MERCADO_CRUDA
        tasa_mercado_redondeada = self.USD_MERCADO_REDONDEADA
        eurusd_impl = self.EUR_USD_IMPLICITA
        eurusd_forex = self.EUR_USD_FOREX

        # Cálculo de métricas del USD (se mantienen)
        diferencia_cifras = tasa_mercado_cruda - tasa_bcv_usd
        diferencia_porcentaje = (diferencia_cifras / tasa_bcv_usd) * 100

        # 🚨 NUEVO CÁLCULO: Tasa Implícita de Ganancia / Markup Implícito
        # Se asume que el costo es el BCV y la venta es la tasa de mercado
        # Markup = ((Venta - Costo) / Costo) * 100
        if tasa_bcv_usd > 0:
            markup_implicito = ((tasa_mercado_cruda - tasa_bcv_usd) / tasa_bcv_usd) * 100
        else:
            markup_implicito = 0.0
        
        # --- Generación del Reporte (Formato Requerido) ---
        
        # NOTA: Usar el formato de fecha y hora que usa tu sistema, aquí un ejemplo
        now_utc = datetime.now(pytz.utc)
        now_venezuela = now_utc.astimezone(pytz.timezone('America/Caracas'))
        timestamp_str = now_venezuela.strftime('%d/%m/%Y %I:%M a.m. VET').replace('AM', 'a.m.').replace('PM', 'p.m.')

        # Obtener análisis de riesgo
        risk_analysis = self.analyze_risk_and_trend()

        reporte = (
            f"🌟 *REPORTE DE TASAS* 🔵 *Stats Dev* 🇻🇪\n"
            f"{timestamp_str}\n\n"
            
            f"═════════════════════\n\n"
            
            f"💰 *BCV OFICIAL (USD)*: {format_currency(tasa_bcv_usd, decimals=4)} Bs\n"
            f"💵 *MERCADO CRUDA (USD)*: {format_currency(tasa_mercado_cruda, decimals=4)} Bs\n"
            f"✨ *REFERENCIAL DE CÁLCULO*: {format_currency(tasa_mercado_redondeada, decimals=2)} Bs\n\n"
            f"**Ganancia Implícita (Markup): {format_currency(markup_implicito, decimals=2)}%**\\n\\n"


            f"💶 *EURO (BCV)*: {format_currency(tasa_bcv_eur, decimals=4)} Bs\n"
            f"🇪🇺 *EURO (MERCADO)*: {format_currency(tasa_mercado_cruda * eurusd_forex, decimals=4)} Bs\n" # Asumiendo EUR Mercado = USD Mercado * EUR/USD FOREX
            f"💹 *EUR/USD Forex*: {format_currency(eurusd_forex, decimals=5)}\n"
            f"⚖️ *EUR/USD BCV*: {format_currency(eurusd_impl, decimals=4)}\n\n"
            
            f"📊 *INDICADORES CLAVE* \n"
            f"🔺 *Brecha BCV/Mercado*: {format_currency(diferencia_porcentaje, decimals=2)}%\n"
            f"⚖️ *Factor de Ponderación (FPC)*: {format_currency(tasa_mercado_cruda / tasa_bcv_usd, decimals=4)}\n" # Factor = Mercado / BCV
            f"🔵 El mercado está a {format_currency(tasa_mercado_cruda / tasa_bcv_usd, decimals=4)}x la tasa oficial\n\n"
        )
        
        # Bloque de Volatilidad (Requiere get_24h_market_summary)
        if summary_24h and summary_24h.get('count', 0) > 0:
            reporte += (
                f"📈 *VOLATILIDAD (Últimas 24h) - Gráfico abajo* \n"
                f"⬆️ *Máximo*: {format_currency(summary_24h['max'], decimals=4)} Bs\n"
                f"⬇️ *Mínimo*: {format_currency(summary_24h['min'], decimals=4)} Bs\n"
                f"promedio de {summary_24h['count']} registros\n\n"
            )

            # 🚨 MÉTRICAS AVANZADAS 🚨
            if risk_analysis['std_dev'] is not None:
                reporte += (\
                    f"σ *Desviación Estándar*: {format_currency(risk_analysis['std_dev'], decimals=4)} Bs\n"
                    f"_(Riesgo: ⬆️ mayor valor = mayor volatilidad)_\n"
                    f"🔸 *Media Móvil (SMA 24h)*: {format_currency(risk_analysis['sma_24h'], decimals=4)} Bs\n"
                    f"📊 *Tendencia*: {risk_analysis['trend']}\n\n"
                )
            else:
                 reporte += f"_No hay suficientes datos históricos (24h) para el análisis avanzado._\n\n"


        else:
            reporte += f"📈 *VOLATILIDAD (Últimas 24h) - Gráfico abajo* \n_No hay suficientes datos históricos (24h) para el resumen._\n\n"

        # OTRAS BCV
        reporte += (
            f"🌐 *OTRAS BCV (Ref.)* \n"
            f"🇨🇳 CNY: {format_currency(self.CNY_BCV, decimals=4)} | 🇹🇷 TRY: {format_currency(self.TRY_BCV, decimals=4)} | 🇷🇺 RUB: {format_currency(self.RUB_BCV, decimals=4)}\n\n"
            
            f"═════════════════════\n"
            f"📲 Usa /start para acceder a las herramientas de cálculo.\n"
        )

        return reporte
    
    # ----------------------------------------------------------------------
    # 5. REPORTE DE PUNTO DE EQUILIBRIO (NUEVO)
    # ----------------------------------------------------------------------
    def get_break_even_report(self) -> str:
        """Calcula y reporta el Punto de Equilibrio al vender los bolívares."""
        if not self.is_valid():
            return "❌ No se pudieron obtener las tasas de cambio desde la base de datos."

        tasa_bcv = self.USD_BCV
        tasa_break_even = self.USD_BREAK_EVEN
        tasa_mercado_venta = self.USD_MERCADO_VENTA
        
        # Asumimos que la comisión de venta es 0.5% (definida en _set_rates)
        COMISION_VENTA = 0.005 # 0.5%

        if tasa_break_even is None:
             return "❌ No se pudo calcular el Punto de Equilibrio."
             
        diferencia_break_even = tasa_mercado_venta - tasa_break_even
        
        if diferencia_break_even > 0:
            recomendacion = "✅ *¡Venta con Ganancia!* Tu tasa de venta actual está *POR ENCIMA* del punto de equilibrio."
        elif diferencia_break_even < 0:
            recomendacion = "⚠️ *¡Venta con Pérdida!* Tu tasa de venta actual está *POR DEBAJO* del punto de equilibrio."
        else:
            recomendacion = "Neutral. Estás vendiendo exactamente en el punto de equilibrio."

        reporte = (
            f"⚖️ *Análisis de Punto de Equilibrio (Break-Even)*\n\n"
            f"1. *Tasa de Compra Inicial* (Costo USD): {format_currency(tasa_bcv, decimals=4)} Bs/USD (BCV)\n"
            f"2. *Costo de Salida* (Comisión venta): {format_currency(COMISION_VENTA * 100, decimals=2)}% (Ej. P2P)\n\n"
            f"🔥 *Punto de Equilibrio (Break-Even)*:\n"
            f"  `{format_currency(tasa_break_even, decimals=4)}` Bs/USD\n"
            f"  _(Tasa a la que debes vender para *no perder* dinero.)_\n\n"
            f"💰 *Tasa de Venta Actual* (Referencial): {format_currency(tasa_mercado_venta, decimals=4)} Bs/USD\n\n"
            f"{recomendacion}\n"
            f"Diferencia: {format_currency(abs(diferencia_break_even), decimals=4)} Bs"
        )
        return reporte
    
    def display_current_rates(self):
        print(self.get_exchange_rates_report())

# src/calculator.py (Dentro de la clase ExchangeRateCalculator)

    # ----------------------------------------------------------------------
    # 5. ANÁLISIS DE VOLATILIDAD Y TENDENCIA (NUEVO)
    # ----------------------------------------------------------------------

    def analyze_risk_and_trend(self):
        """Calcula la Desviación Estándar y la Tendencia (SMA) de 24h."""
        
        # 1. Obtener datos históricos de las últimas 24 horas
        # NOTA: Necesitas implementar 'get_historical_rates(24)' en database_manager.py
        # para que devuelva una lista de solo los valores de USD_MERCADO_CRUDA.
        # Por ahora, usamos una función ficticia que llamaremos:
        from src.database_manager import get_historical_rates 
        historical_rates = get_historical_rates(hours=24) 
        
        if not historical_rates or len(historical_rates) < 5:
            return {
                'std_dev': None, 
                'sma_24h': None,
                'trend': 'Insuficientes datos históricos (menos de 5 registros en 24h).'
            }

        rates_array = np.array(historical_rates)
        
        # 2. Cálculo de Desviación Estándar (Métrica de Riesgo)
        std_dev = np.std(rates_array)
        
        # 3. Cálculo de Media Móvil Simple (SMA de 24 horas)
        sma_24h = np.mean(rates_array)
        
        # 4. Determinación de Tendencia (Métrica de Dirección)
        current_rate = self.USD_MERCADO_CRUDA
        
        if current_rate > sma_24h:
            trend = "📈 Alcista (El precio actual está por encima del promedio de 24h)"
        elif current_rate < sma_24h:
            trend = "📉 Bajista (El precio actual está por debajo del promedio de 24h)"
        else:
            trend = "➡️ Lateral (El precio actual está cerca del promedio de 24h)"

        return {
            'std_dev': std_dev,
            'sma_24h': sma_24h,
            'trend': trend
        }