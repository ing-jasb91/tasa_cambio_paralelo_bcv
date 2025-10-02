# app/notifier.py

import logging
import pytz
import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    JobQueue
)
from src.data_fetcher import get_exchange_rates
# NUEVA IMPORTACIÓN: Usaremos la DB como fuente de datos
from src.database_manager import get_latest_rates 

from src.database_manager import get_latest_rates, get_24h_market_summary 

# Habilitar el logging para ver mensajes de error
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    # Configurar en WARNING o ERROR para evitar la sobrecarga de logs en el servidor
    level=logging.ERROR 
)

# --- Configuración del Bot de Telegram ---
BOT_TOKEN = '8245434556:AAHbBZagDIxZul86yeUzYSXdxsr5fkRlG8I'
CHAT_ID = '552061604'

# --- Constantes para los estados de conversación ---
ANALISIS_COMPRA = 1
COSTO_OPORTUNIDAD = 2
CAMBIO_DIVISAS = 3 

def _get_current_rates():
    """Obtiene las tasas de USD, EUR y la tasa de mercado (cruda/redondeada) de la DB."""
    latest_data = get_latest_rates()
    
    if not latest_data:
        return None, None, None, None
        
    tasa_bcv = latest_data.get('USD_BCV')
    tasa_mercado_cruda = latest_data.get('USD_MERCADO_CRUDA')
    
    # 🚨 Lógica de Verificación CRÍTICA 🚨
    # Si alguno de los valores clave (BCV o Mercado) es None, fallamos inmediatamente.
    if tasa_bcv is None or tasa_mercado_cruda is None:
         return None, None, None, None

    # Intentamos convertir a float de forma segura
    try:
        tasa_bcv = float(tasa_bcv)
        tasa_mercado_cruda = float(tasa_mercado_cruda)
    except (ValueError, TypeError):
         # Si la conversión falla (e.g., el valor es 'N/A' o una cadena rota)
         return None, None, None, None
    
    # Solo calculamos la redondeada si tenemos el valor crudo válido
    tasa_mercado_redondeada = round(tasa_mercado_cruda, -1)
    
    return latest_data, tasa_bcv, tasa_mercado_cruda, tasa_mercado_redondeada

# --- Funciones de Cálculo (Sin Cambios) ---
# ... (calculate_metrics_compra, calculate_metrics_oportunidad, calculate_price_conversion) ...
# Estas funciones de cálculo se mantienen igual, ya que reciben las tasas como argumentos.
# Simplemente se pegan aquí tal cual estaban en tu código.

def calculate_metrics_compra(costo_producto, dolares_disponibles, tasa_bcv, tasa_mercado_redondeada):
    tasas_a_evaluar = [tasa_mercado_redondeada - (i * 10) for i in range(6)]
    
    response = (
        f"📊 *Análisis de Compra*\n"
        f"Producto: ${costo_producto:.2f} | Divisas: ${dolares_disponibles:.2f}\n"
        "=======================================\n"
        "{:<10} | {:<8} | {:<12}\n".format("Tasa", "Poder Compra", "Resultado")
    )
    
    for tasa in tasas_a_evaluar:
        poder_compra = dolares_disponibles * (tasa / tasa_bcv)
        suficiente = poder_compra >= costo_producto
        estado = "Sí" if suficiente else "No"
        response += "{:<10.2f} | {:<8.2f} | {:<12}\n".format(tasa, poder_compra, estado)

    return response

def calculate_metrics_oportunidad(dolares_a_vender, tasa_bcv, tasa_mercado_redondeada):
    tasas_a_evaluar = [tasa_mercado_redondeada - (i * 10) for i in range(1, 6)]
    valor_max_bolivares = dolares_a_vender * tasa_mercado_redondeada
    
    response = (
        f"📊 *Costo de Oportunidad*\n"
        f"Divisas: ${dolares_a_vender:.2f}\n"
        "=======================================\n"
        "{:<10} | {:<10} | {:<12} | {:<20}\n".format("Tasa", "Pérdida (Bs)", "Pérdida ($Merc)", "Poder de Compra (BCV USD)")
    )
    
    for tasa_actual in tasas_a_evaluar:
        valor_actual_bolivares = dolares_a_vender * tasa_actual
        perdida_bolivares = valor_max_bolivares - valor_actual_bolivares
        perdida_usd_mercado = perdida_bolivares / tasa_mercado_redondeada
        poder_compra_bcv = (dolares_a_vender * tasa_actual) / tasa_bcv
        
        response += "{:<10.2f} | {:<10.2f} | {:<12.2f} | {:<20.2f}\n".format(tasa_actual, perdida_bolivares, perdida_usd_mercado, poder_compra_bcv)
    
    return response

def calculate_price_conversion(usd_price, tasa_bcv, tasa_mercado_cruda, tasa_mercado_redondeada):
    precio_bcv = usd_price * tasa_bcv
    precio_mercado = usd_price * tasa_mercado_cruda
    tasa_mercado_con_igtf = tasa_mercado_cruda * 1.0348
    
    # Diferencia cambiaria (Mercado vs BCV)
    diferencia_cifras = tasa_mercado_con_igtf - tasa_bcv
    diferencia_porcentaje = (diferencia_cifras / tasa_bcv) * 100
    
    # Nuevo cálculo de diferencia con IGTF
    precio_mercado_con_igtf = precio_mercado * 1.0348
    diferencia_con_igtf = precio_mercado_con_igtf - precio_bcv

    response = (
        f"💰 *Conversión de Divisas*\n"
        f"Monto en USD: ${usd_price:.2f}\n"
        f"Tasa BCV: {tasa_bcv:.2f} Bs/USD\n"
        f"Tasa Mercado: {tasa_mercado_cruda:.2f} Bs/USD\n"
        f"Tasa Mercado + IGTF: {tasa_mercado_con_igtf:.2f} Bs/USD\n"
        f"  (Diferencia vs BCV: {diferencia_cifras:.2f} Bs/USD | {diferencia_porcentaje:.2f}%)\n"
        f"=======================================\n\n"
        f"Precio en Bs (BCV): {precio_bcv:.2f}\n"
        f"Precio en Bs (Mercado con IGTF): {precio_mercado_con_igtf:.2f}\n"
        f"Diferencia (con 3.48% IGTF): {diferencia_con_igtf:.2f}\n"
        "---------------------------------------\n\n"
        "Precios en un rango de tasas:\n"
        "{:<10} | {:<12} | {:<15}\n".format("Tasa", "Precio (Bs)", "Diferencia (Bs)")
    )

    tasas_a_evaluar = [tasa_mercado_redondeada - (i * 10) for i in range(6)]
    for tasa in tasas_a_evaluar:
        precio_rango = usd_price * tasa
        diferencia_precio = precio_rango - precio_bcv # Diferencia con el precio BCV
        response += "{:<10.2f} | {:<12.2f} | {:<15.2f}\n".format(tasa, precio_rango, diferencia_precio)
    
    return response

# --- Tarea Recurrente de Actualización de Datos (Cada 10 minutos) ---
async def update_exchange_rates(context: ContextTypes.DEFAULT_TYPE):
    """
    Ejecuta la extracción de tasas y el guardado condicional en la DB.
    Esta función se ejecuta cada 10 minutos.
    """
    try:
        # get_exchange_rates() contiene toda la lógica:
        # 1. Obtiene BCV, P2P, Forex.
        # 2. Aplica la lógica condicional (cambio BCV o cambio P2P > 0.1%).
        # 3. Guarda en DB SÓLO si se cumplen las condiciones.
        _, _, _ = get_exchange_rates()
        logging.info("Tasa actualizada y guardada (si aplica) por el JobQueue del bot.")
        
        # Opcional: Si quieres ver el resumen de 24h en el log cada 10 minutos
        # from src.database_manager import get_24h_market_summary
        # summary = get_24h_market_summary()
        # if summary:
        #    logging.info(f"Resumen P2P (24h): MAX={summary['max']:.4f}, AVG={summary['avg']:.4f}")
            
    except Exception as e:
        # Es CRÍTICO que la tarea programada no falle, solo loggeamos el error.
        logging.error(f"FALLO en la tarea de actualización de tasas (10min): {e}")

# # --- Función para el reporte (ESTRUCTURA PROFESIONAL - CON HORA) ---
# async def send_hourly_report(context: ContextTypes.DEFAULT_TYPE):
#     """Genera y envía un reporte completo de las tasas de cambio con formato profesional."""
#     chat_id = context.job.data
    
#     latest_data, tasa_bcv, tasa_mercado_cruda, tasa_mercado_redondeada = _get_current_rates()
    
#     if not latest_data:
#         await context.bot.send_message(chat_id=chat_id, text="❌ Error: No se pudieron obtener las tasas de cambio de la base de datos.")
#         return

#     # 1. CÁLCULOS PRINCIPALES
#     # ... (Cálculos de paridades, FPC, y volatilidad se mantienen igual) ...
    
#     # Obtener data de DB (asegurando floats para cálculos)
#     eur_bcv = float(latest_data.get('EUR_BCV', 0.0))
#     forex_eur_usd = float(latest_data.get('EUR_USD_FOREX', 0.0))
    
#     # Paridad BCV: EUR/USD = EUR_BCV / USD_BCV
#     paridad_bcv = eur_bcv / tasa_bcv if tasa_bcv else 0.0
    
#     # Euro Implícito Mercado: USD_Mercado * EUR_USD_Forex
#     tasa_eur_mercado = tasa_mercado_cruda * forex_eur_usd
    
#     # Indicadores de disparidad
#     diferencia_porcentaje = ((tasa_mercado_cruda / tasa_bcv) - 1) * 100
#     fpc = tasa_mercado_cruda / tasa_bcv
    
#     # Resumen de 24 horas (Volatilidad)
#     from src.database_manager import get_24h_market_summary
#     market_summary = get_24h_market_summary()
#     max_24h = market_summary.get('max', tasa_mercado_cruda)
#     min_24h = market_summary.get('min', tasa_mercado_cruda)

#     # 🚨 NUEVA LÓGICA: Obtener la hora actual en VET 🚨
#     zona_horaria_vzla = pytz.timezone('America/Caracas')
#     hora_actual_vzla = datetime.datetime.now(zona_horaria_vzla)
#     hora_reporte_str = hora_actual_vzla.strftime('%I:%M %p. VET').replace('AM', 'a.m.').replace('PM', 'p.m.') # Formato 12h con AM/PM

#     # 2. CONSTRUCCIÓN DEL REPORTE
    
#     reporte = (
#         f"🇻🇪 *REPORTE DIARIO DE TASAS* | Stats Dev 📊\n"
#         f"🗓️ *Fecha Valor:* `{latest_data.get('date', 'Desconocida')}` *({hora_reporte_str})*\n" # ¡CAMBIO AQUÍ!
#         f"\n"
        
#         # --- SECCIÓN 1: TASAS OFICIALES (BCV) ---
#         f"1️⃣ *Tasas Oficiales (BCV)*\n"
#         f"_La base legal y contable de los valores._\n"
#         f"\n"
#         f"🇺🇸 *Dólar (BCV):* `{tasa_bcv:,.4f}` Bs/USD\n"
#         f"🇪🇺 *Euro (BCV):* `{eur_bcv:,.4f}` Bs/EUR\n"
#         f"⚖️ *Paridad EUR/USD Implícita BCV:* `{paridad_bcv:.4f}`\n"
#         f"\n"

#         # --- SECCIÓN 2: TASAS DE OPORTUNIDAD DE MERCADO (P2P / Forex) ---
#         f"2️⃣ *Tasas de Oportunidad de Mercado (P2P / Forex)*\n"
#         f"_El valor real de su capital y las oportunidades de arbitraje._\n"
#         f"\n"
#         f"💸 *Dólar (Mercado):* `{tasa_mercado_cruda:,.4f}` Bs/USD {'⬆️' if max_24h > tasa_mercado_cruda else '⬇️'}\n"
#         f"💶 *Euro (Implícito):* `{tasa_eur_mercado:,.4f}` Bs/EUR\n"
#         f"💹 *Paridad EUR/USD Real (Forex):* `{forex_eur_usd:,.5f}`\n"
#         f"\n"

#         # --- SECCIÓN 3: INDICADORES CLAVE DE DISPARIDAD ---
#         f"3️⃣ *Indicadores Clave de Disparidad*\n"
#         f"_Cuantificación de la brecha y volatilidad para la toma de decisiones._\n"
#         f"\n"
#         f"📈 *Brecha BCV/Mercado:* `{diferencia_porcentaje:.2f}%`\n"
#         f"⚖️ *Factor de Ponderación (FPC):* `{fpc:.4f}`\n"
#         f"_ (El dólar vale {fpc:.4f} veces más en el mercado que en el BCV)_\n"
#         f"\n"
#         f"⏱️ *Volatilidad (Máx. 24h):* `{max_24h:,.4f}` Bs/USD\n"
#         f"⏱️ *Volatilidad (Mín. 24h):* `{min_24h:,.4f}` Bs/USD\n"
#         f"\n"

#         # --- SECCIÓN 4: OTRAS DIVISAS (REFERENCIAL BCV) ---
#         f"🌎 *Otras Divisas (Referencial BCV)*\n"
#         f"🇨🇳 *CNY:* `{latest_data.get('CNY_BCV', 0.0):.4f}` | 🇹🇷 *TRY:* `{latest_data.get('TRY_BCV', 0.0):.4f}` | 🇷🇺 *RUB:* `{latest_data.get('RUB_BCV', 0.0):.4f}`\n"
#     )

#     await context.bot.send_message(chat_id=chat_id, text=reporte, parse_mode="Markdown")

# app/notifier.py (Fragmento de código: Reemplaza tu función send_hourly_report)

# ... (Todo el código anterior de imports, constantes, _get_current_rates, y cálculos se mantiene igual) ...

# --- Función para el reporte (ESTRUCTURA PROFESIONAL - CON ACTUALIZACIÓN FORZADA) ---
async def send_hourly_report(context: ContextTypes.DEFAULT_TYPE):
    """Genera y envía un reporte completo de las tasas de cambio con formato profesional."""
    chat_id = context.job.data
    
    # 🚨 NUEVA LÓGICA CRÍTICA: Forzar la extracción y guardado de datos antes de leer la DB.
    try:
        from src.data_fetcher import get_exchange_rates
        # Llama a la extracción. force_save=True anula la lógica de volatilidad del mercado.
        get_exchange_rates(force_save=True)
        logging.info("Actualización forzada de la DB completada para el reporte horario.")
    except Exception as e:
        logging.error(f"FALLO al forzar la actualización para el reporte horario: {e}")
        # Si falla, el código continua usando los datos más viejos, pero evita un fallo del JobQueue.
    
    # --- Continúa la lógica de reporte leyendo la DB ---
    latest_data, tasa_bcv, tasa_mercado_cruda, tasa_mercado_redondeada = _get_current_rates()
    
    if not latest_data:
        await context.bot.send_message(chat_id=chat_id, text="❌ Error: No se pudieron obtener las tasas de cambio de la base de datos.")
        return

    # 1. CÁLCULOS PRINCIPALES (Se mantienen igual)
    # Obtener data de DB (asegurando floats para cálculos)
    eur_bcv = float(latest_data.get('EUR_BCV', 0.0))
    forex_eur_usd = float(latest_data.get('EUR_USD_FOREX', 0.0))
    
    # Paridad BCV: EUR/USD = EUR_BCV / USD_BCV
    paridad_bcv = eur_bcv / tasa_bcv if tasa_bcv else 0.0
    
    # Euro Implícito Mercado: USD_Mercado * EUR_USD_Forex
    tasa_eur_mercado = tasa_mercado_cruda * forex_eur_usd
    
    # Indicadores de disparidad
    diferencia_porcentaje = ((tasa_mercado_cruda / tasa_bcv) - 1) * 100
    fpc = tasa_mercado_cruda / tasa_bcv
    
    # Resumen de 24 horas (Volatilidad)
    from src.database_manager import get_24h_market_summary
    market_summary = get_24h_market_summary()
    # Usar get en market_summary para manejar el caso de DB vacía
    max_24h = market_summary.get('max', tasa_mercado_cruda) if market_summary else tasa_mercado_cruda
    min_24h = market_summary.get('min', tasa_mercado_cruda) if market_summary else tasa_mercado_cruda

    # Lógica: Obtener la hora actual en VET
    zona_horaria_vzla = pytz.timezone('America/Caracas')
    hora_actual_vzla = datetime.datetime.now(zona_horaria_vzla)
    hora_reporte_str = hora_actual_vzla.strftime('%I:%M %p. VET').replace('AM', 'a.m.').replace('PM', 'p.m.') # Formato 12h con AM/PM

    # 2. CONSTRUCCIÓN DEL REPORTE (Se mantiene igual)
    
    reporte = (
        f"🇻🇪 *REPORTE DIARIO DE TASAS* | Stats Dev 📊\n"
        f"🗓️ *Fecha Valor:* `{latest_data.get('date', 'Desconocida')}` *({hora_reporte_str})*\n"
        f"\n"
        
        # --- SECCIÓN 1: TASAS OFICIALES (BCV) ---
        f"1️⃣ *Tasas Oficiales (BCV)*\n"
        f"_La base legal y contable de los valores._\n"
        f"\n"
        f"🇺🇸 *Dólar (BCV):* `{tasa_bcv:,.4f}` Bs/USD\n"
        f"🇪🇺 *Euro (BCV):* `{eur_bcv:,.4f}` Bs/EUR\n"
        f"⚖️ *Paridad EUR/USD Implícita BCV:* `{paridad_bcv:.4f}`\n"
        f"\n"

        # --- SECCIÓN 2: TASAS DE OPORTUNIDAD DE MERCADO (P2P / Forex) ---
        f"2️⃣ *Tasas de Oportunidad de Mercado (P2P / Forex)*\n"
        f"_El valor real de su capital y las oportunidades de arbitraje._\n"
        f"\n"
        f"💸 *Dólar (Mercado):* `{tasa_mercado_cruda:,.4f}` Bs/USD {'⬆️' if max_24h > tasa_mercado_cruda else '⬇️'}\n"
        f"💶 *Euro (Implícito):* `{tasa_eur_mercado:,.4f}` Bs/EUR\n"
        f"💹 *Paridad EUR/USD Real (Forex):* `{forex_eur_usd:,.5f}`\n"
        f"\n"

        # --- SECCIÓN 3: INDICADORES CLAVE DE DISPARIDAD ---
        f"3️⃣ *Indicadores Clave de Disparidad*\n"
        f"_Cuantificación de la brecha y volatilidad para la toma de decisiones._\n"
        f"\n"
        f"📈 *Brecha BCV/Mercado:* `{diferencia_porcentaje:.2f}%`\n"
        f"⚖️ *Factor de Ponderación (FPC):* `{fpc:.4f}`\n"
        f"_ (El dólar vale {fpc:.4f} veces más en el mercado que en el BCV)_\n"
        f"\n"
        f"⏱️ *Volatilidad (Máx. 24h):* `{max_24h:,.4f}` Bs/USD\n"
        f"⏱️ *Volatilidad (Mín. 24h):* `{min_24h:,.4f}` Bs/USD\n"
        f"\n"

        # --- SECCIÓN 4: OTRAS DIVISAS (REFERENCIAL BCV) ---
        f"🌎 *Otras Divisas (Referencial BCV)*\n"
        f"🇨🇳 *CNY:* `{latest_data.get('CNY_BCV', 0.0):.4f}` | 🇹🇷 *TRY:* `{latest_data.get('TRY_BCV', 0.0):.4f}` | 🇷🇺 *RUB:* `{latest_data.get('RUB_BCV', 0.0):.4f}`\n"
    )

    await context.bot.send_message(chat_id=chat_id, text=reporte, parse_mode="Markdown")

# ... (Todo el resto del archivo se mantiene igual) ...

# --- Funciones de Bot (start, button_handler se mantienen iguales) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /start y muestra el menú de botones."""
    # ... (código sin cambios)
    keyboard = [
        [InlineKeyboardButton("📊 Análisis de Compra", callback_data='analisis_compra')],
        [InlineKeyboardButton("📈 Costo de Oportunidad", callback_data='costo_oportunidad')],
        [InlineKeyboardButton("💱 Cambio de Divisas", callback_data='cambio_divisas')] # NUEVO BOTÓN
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('¡Hola! Elige una opción para continuar:', reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja las selecciones de botones y pide la información necesaria."""
    # ... (código sin cambios)
    query = update.callback_query
    await query.answer()
    
    if query.data == 'analisis_compra':
        context.user_data['state'] = ANALISIS_COMPRA
        await query.edit_message_text(
            text="Ingresa el costo del producto en USD y la cantidad de divisas que tienes, separados por un espacio (ej: `300 150`)"
        )
    elif query.data == 'costo_oportunidad':
        context.user_data['state'] = COSTO_OPORTUNIDAD
        await query.edit_message_text(
            text="Ingresa la cantidad de divisas que tienes para vender (ej: `300`)"
        )
    elif query.data == 'cambio_divisas': # NUEVA LÓGICA
        context.user_data['state'] = CAMBIO_DIVISAS
        await query.edit_message_text(
            text="Ingresa el precio del producto o servicio en USD (ej: `50`)"
        )

# --- message_handler (MODIFICADA para usar la DB) ---
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los mensajes de texto del usuario según el estado actual."""
    if 'state' not in context.user_data:
        await update.message.reply_text("Por favor, elige una opción del menú primero usando /start.")
        return

    try:
        valores = [float(val) for val in update.message.text.split()]
        
        # OBTENER TASAS DE LA BASE DE DATOS
        _, tasa_bcv, tasa_mercado_cruda, tasa_mercado_redondeada = _get_current_rates()
        
        if not all([tasa_bcv, tasa_mercado_cruda, tasa_mercado_redondeada]):
            await update.message.reply_text("No se pudieron obtener las tasas de cambio de la base de datos.")
            return

        if context.user_data['state'] == ANALISIS_COMPRA:
            if len(valores) != 2:
                await update.message.reply_text("❌ Entrada incorrecta. Debes ingresar dos números: costo y divisas.")
                return
            response = calculate_metrics_compra(valores[0], valores[1], tasa_bcv, tasa_mercado_redondeada)
        
        elif context.user_data['state'] == COSTO_OPORTUNIDAD:
            if len(valores) != 1:
                await update.message.reply_text("❌ Entrada incorrecta. Debes ingresar un solo número: la cantidad de divisas.")
                return
            response = calculate_metrics_oportunidad(valores[0], tasa_bcv, tasa_mercado_redondeada)

        elif context.user_data['state'] == CAMBIO_DIVISAS:
            if len(valores) != 1:
                await update.message.reply_text("❌ Entrada incorrecta. Debes ingresar un solo número: el precio en USD.")
                return
            response = calculate_price_conversion(valores[0], tasa_bcv, tasa_mercado_cruda, tasa_mercado_redondeada)
        
        await update.message.reply_text(response, parse_mode="Markdown")
        context.user_data.pop('state', None)
        await start(update, context)
    
    except ValueError:
        await update.message.reply_text("❌ Formato incorrecto. Por favor, ingresa solo números.")

# --- Configuración de comandos del bot (se mantienen iguales) ---
async def post_init(application: ApplicationBuilder):
    """Registra los comandos del bot en la API de Telegram."""
    commands = [
        BotCommand("start", "Inicia una conversación con el bot y muestra el menú."),
    ]
    await application.bot.set_my_commands(commands)
    logging.info("Comandos del bot registrados correctamente.")

def start_bot():
    """Función para encapsular el inicio del bot, llamada desde app/main.py."""
    
    # ... (Tu lógica de precarga de datos se mantiene aquí) ...
    print("Pre-carga: Asegurando que la DB tenga datos frescos...")
    try:
        from src.data_fetcher import get_exchange_rates
        get_exchange_rates()
        print("Pre-carga exitosa: Datos del día insertados/actualizados en DB.")
    except Exception as e:
        print(f"ERROR: Fallo al insertar datos al inicio del bot. El bot usará datos viejos. Error: {e}")
    
    # Configuración de la aplicación
    application = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    
    # Crea el JobQueue para tareas programadas
    job_queue = application.job_queue
    
    # =========================================================================
    # CAMBIO CRÍTICO AQUÍ: Usar run_once para el primer envío
    # =========================================================================
    
    # 1. Ejecución INMEDIATA: Dispara el primer reporte 1 segundo después de iniciar
    # Esto asegura que el usuario que corre el bot reciba el mensaje al instante.
    job_queue.run_once(send_hourly_report, when=1, data=CHAT_ID) 
    print("Primer reporte programado para enviarse en 1 segundo.")

    # 3. Notificación RECURRENTE (Cada 3600 segundos = 1 hora)
    job_queue.run_repeating(send_hourly_report, 
                            interval=3600, 
                            data=CHAT_ID)
    print("Reporte recurrente programado para repetirse cada 1 hora.")
    
    # =========================================================================
    
    # Añade los handlers para la interacción a demanda
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("Bot interactivo iniciado. Envía /start en Telegram para interactuar.")
    application.run_polling()


if __name__ == "__main__":
    start_bot()