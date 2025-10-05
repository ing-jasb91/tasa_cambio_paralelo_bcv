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
from src.database_manager import get_latest_rates, get_24h_market_summary 

# 🚨 CAMBIO CRÍTICO: Importar la nueva clase centralizada 🚨
from src.calculator import ExchangeRateCalculator 
from src.plot_generator import generate_market_plot


import os 
from dotenv import load_dotenv

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.ERROR 
)

# --- Configuración del Bot de Telegram ---
load_dotenv() 
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

# --- Constantes para los estados de conversación (MODIFICADAS) ---
# Estados para pedir la divisa
SELECT_CURRENCY_COMPRA = 10
SELECT_CURRENCY_OPORTUNIDAD = 20
SELECT_CURRENCY_CAMBIO = 30

# Estados para esperar el input numérico
AWAITING_INPUT_COMPRA = 11
AWAITING_INPUT_OPORTUNIDAD = 21
AWAITING_INPUT_CAMBIO = 31

# ❌ ELIMINAR _get_current_rates() y las funciones de cálculo (calculate_metrics_...) ❌
# La lógica de tasas es ahora manejada por ExchangeRateCalculator().

# --- Tarea Recurrente de Actualización de Datos (Cada 10 minutos) ---
# (Se mantiene igual)
async def update_exchange_rates(context: ContextTypes.DEFAULT_TYPE):
    """
    Ejecuta la extracción de tasas y el guardado condicional en la DB.
    """
    try:
        _, _, _ = get_exchange_rates()
        logging.info("Tasa actualizada y guardada (si aplica) por el JobQueue del bot.")
    except Exception as e:
        logging.error(f"FALLO en la tarea de actualización de tasas (10min): {e}")

# Función auxiliar para formatear tasas con 4 decimales (usada en el reporte)
def format_rate_report(rate):
    """Formatea la tasa con separador de miles y 4 decimales."""
    if rate is None:
        return "N/D"
    # Formato: X.XXX,XXXX
    return f"{rate:,.4f}".replace(",", "X").replace(".", ",").replace("X", ".")


# # --- Función para el reporte (send_hourly_report) ---
# async def send_hourly_report(context: ContextTypes.DEFAULT_TYPE):
#     """Genera y envía un reporte completo de las tasas de cambio con formato profesional."""
#     chat_id = context.job.data
    
#     # 🚨 Lógica de actualización forzada antes de leer la DB 🚨
#     try:
#         # Llama a la extracción. force_save=True anula la lógica de volatilidad del mercado.
#         # Asumiendo que get_exchange_rates es importada
#         from src.data_fetcher import get_exchange_rates 
#         get_exchange_rates(force_save=True)
#     except Exception as e:
#         logging.error(f"FALLO al forzar la actualización para el reporte horario: {e}")
        
#     # Crear una instancia del calculator para obtener la data completa
#     # Asumiendo que ExchangeRateCalculator es importada
#     from src.calculator import ExchangeRateCalculator
#     calc = ExchangeRateCalculator()
    
#     if not calc.is_valid():
#         await context.bot.send_message(chat_id=chat_id, text="❌ Error: No se pudieron obtener las tasas de cambio de la base de datos.")
#         return

#     # Usar los valores directamente de la instancia de calc para el reporte
#     tasa_bcv = calc.USD_BCV
#     eur_bcv = calc.EUR_BCV
#     tasa_mercado_cruda = calc.USD_MERCADO_CRUDA
#     tasa_mercado_redondeada = calc.USD_MERCADO_REDONDEADA # Nueva: Usar la tasa redondeada calculada
#     forex_eur_usd = calc.EUR_USD_FOREX

#     # 1. CÁLCULOS PRINCIPALES
#     paridad_bcv = eur_bcv / tasa_bcv if tasa_bcv else 0.0
#     tasa_eur_mercado = calc.EUR_MERCADO_CRUDA # Usamos el valor ya calculado en el init
#     diferencia_porcentaje = ((tasa_mercado_cruda / tasa_bcv) - 1) * 100
#     fpc = tasa_mercado_cruda / tasa_bcv
    
#     # Resumen de 24 horas (Volatilidad)
#     # Asumiendo que get_24h_market_summary es importada
#     from src.database_manager import get_24h_market_summary
#     market_summary = get_24h_market_summary()
#     max_24h = market_summary.get('max', tasa_mercado_cruda) if market_summary else tasa_mercado_cruda
#     min_24h = market_summary.get('min', tasa_mercado_cruda) if market_summary else tasa_mercado_cruda
#     avg_24h = market_summary.get('avg', tasa_mercado_cruda) if market_summary else tasa_mercado_cruda
#     count_24h = market_summary.get('count', 0) if market_summary else 0

#     # Lógica: Obtener la hora actual en VET (Se mantiene)
#     zona_horaria_vzla = pytz.timezone('America/Caracas')
#     hora_actual_vzla = datetime.datetime.now(zona_horaria_vzla)
#     hora_reporte_str = hora_actual_vzla.strftime('%d/%m/%Y %I:%M %p. VET').replace('AM', 'a.m.').replace('PM', 'p.m.') 

#     # 2. CONSTRUCCIÓN DEL REPORTE (AQUÍ ESTÁ LA MEJORA ESTÉTICA)
    
#     # Emojis de tendencia para la volatilidad
#     # Usamos la cruda para el cálculo de tendencia, comparada con el promedio
#     tendencia_icon = "🟢" 
#     if tasa_mercado_cruda > avg_24h:
#         tendencia_icon = "🔴" # Subida
#     elif tasa_mercado_cruda < avg_24h:
#         tendencia_icon = "🔵" # Bajada


#     reporte = (
#         f"🌟 *REPORTE DE TASAS* {tendencia_icon} *Stats Dev* 🇻🇪\n"
#         f"_{hora_reporte_str}_\n\n"
#         f"═════════════════════\n\n"
        
#         # --- SECCIÓN 1: TASAS CLAVE ---
#         f"💰 *BCV OFICIAL (USD):* {format_rate_report(tasa_bcv)} Bs\n"
#         f"💵 *MERCADO CRUDA (USD):* {format_rate_report(tasa_mercado_cruda)} Bs\n"
#         f"✨ *REFERENCIAL DE CÁLCULO:* {tasa_mercado_redondeada:.2f} Bs\n\n"
        
#         # --- SECCIÓN 2: OTROS VALORES ---
#         f"💶 *EURO (BCV):* {format_rate_report(eur_bcv)} Bs\n"
#         f"🇪🇺 *EURO (MERCADO):* {format_rate_report(tasa_eur_mercado)} Bs\n"
#         f"💹 *EUR/USD Forex:* {forex_eur_usd:.5f}\n"
#         f"⚖️ *EUR/USD BCV:* `{paridad_bcv:.4f}`\n\n"

#         # --- SECCIÓN 3: INDICADORES Y VOLATILIDAD ---
#         f"📊 *INDICADORES CLAVE*\n"
#         f"🔺 *Brecha BCV/Mercado:* `{diferencia_porcentaje:.2f}%`\n"
#         f"⚖️ *Factor de Ponderación (FPC):* `{fpc:.4f}`\n"
#         f"_{tendencia_icon} El mercado está a {fpc:.4f}x la tasa oficial_\n\n"
        
#         f"📈 *VOLATILIDAD (Últimas 24h)*\n"
#         f"⬆️ *Máximo:* {format_rate_report(max_24h)} Bs\n"
#         f"⬇️ *Mínimo:* {format_rate_report(min_24h)} Bs\n"
#         f" promedio de {count_24h} registros\n\n"
        
#         # --- SECCIÓN 4: OTRAS DIVISAS (REFERENCIAL BCV) ---
#         f"🌐 *OTRAS BCV* (Ref.)\n"
#         f"🇨🇳 *CNY:* `{calc.latest_rates.get('CNY_BCV', 0.0):.4f}` | 🇹🇷 *TRY:* `{calc.latest_rates.get('TRY_BCV', 0.0):.4f}` | 🇷🇺 *RUB:* `{calc.latest_rates.get('RUB_BCV', 0.0):.4f}`\n\n"
        
#         f"═════════════════════\n"
#         f"📲 Usa /start para acceder a las herramientas de cálculo."
#     )

#     await context.bot.send_message(chat_id=chat_id, text=reporte, parse_mode="Markdown")



# app/notifier.py

# ... (importaciones y constantes)

# --- Función para el reporte (send_hourly_report) MODIFICADA PARA ENVIAR FOTO ---
async def send_hourly_report(context: ContextTypes.DEFAULT_TYPE):
    """Genera y envía un reporte completo de las tasas de cambio (TEXTO + FOTO)."""
    chat_id = context.job.data
    
    # 🚨 Lógica de actualización forzada antes de leer la DB 🚨
    try:
        from src.data_fetcher import get_exchange_rates 
        get_exchange_rates(force_save=True)
    except Exception as e:
        logging.error(f"FALLO al forzar la actualización para el reporte horario: {e}")
        
    # Crear una instancia del calculator para obtener la data completa
    from src.calculator import ExchangeRateCalculator
    calc = ExchangeRateCalculator()
    
    if not calc.is_valid():
        await context.bot.send_message(chat_id=chat_id, text="❌ Error: No se pudieron obtener las tasas de cambio de la base de datos.")
        return

    # Usar los valores directamente de la instancia de calc para el reporte
    tasa_bcv = calc.USD_BCV
    eur_bcv = calc.EUR_BCV
    tasa_mercado_cruda = calc.USD_MERCADO_CRUDA
    tasa_mercado_redondeada = calc.USD_MERCADO_REDONDEADA 
    forex_eur_usd = calc.EUR_USD_FOREX

    # 1. CÁLCULOS PRINCIPALES (Se mantienen)
    paridad_bcv = eur_bcv / tasa_bcv if tasa_bcv else 0.0
    tasa_eur_mercado = calc.EUR_MERCADO_CRUDA 
    diferencia_porcentaje = ((tasa_mercado_cruda / tasa_bcv) - 1) * 100
    fpc = tasa_mercado_cruda / tasa_bcv
    
    # Resumen de 24 horas (Volatilidad)
    from src.database_manager import get_24h_market_summary
    market_summary = get_24h_market_summary()
    max_24h = market_summary.get('max', tasa_mercado_cruda) if market_summary else tasa_mercado_cruda
    min_24h = market_summary.get('min', tasa_mercado_cruda) if market_summary else tasa_mercado_cruda
    avg_24h = market_summary.get('avg', tasa_mercado_cruda) if market_summary else tasa_mercado_cruda
    count_24h = market_summary.get('count', 0) if market_summary else 0

    # Lógica: Obtener la hora actual en VET (Se mantiene)
    import pytz # Asegúrate de que pytz esté importado arriba
    import datetime # Asegúrate de que datetime esté importado arriba
    zona_horaria_vzla = pytz.timezone('America/Caracas')
    hora_actual_vzla = datetime.datetime.now(zona_horaria_vzla)
    hora_reporte_str = hora_actual_vzla.strftime('%d/%m/%Y %I:%M %p. VET').replace('AM', 'a.m.').replace('PM', 'p.m.') 

    # 2. CONSTRUCCIÓN DEL REPORTE DE TEXTO (CAPTION)
    
    # Emojis de tendencia para la volatilidad
    tendencia_icon = "🟢" 
    if tasa_mercado_cruda > avg_24h:
        tendencia_icon = "🔴" 
    elif tasa_mercado_cruda < avg_24h:
        tendencia_icon = "🔵" 

    # NOTA: Debes asegurarte de que la función format_rate_report esté definida
    # o usar format_currency si es la función correcta en tu proyecto.
    def format_rate_report(rate):
        from src.calculator import format_currency # Asume que está en calculator.py
        return format_currency(rate, decimals=4)
        
    reporte = (
        f"🌟 *REPORTE DE TASAS* {tendencia_icon} *Stats Dev* 🇻🇪\n"
        f"_{hora_reporte_str}_\n\n"
        f"═════════════════════\n\n"
        
        # --- SECCIÓN 1: TASAS CLAVE ---
        f"💰 *BCV OFICIAL (USD):* {format_rate_report(tasa_bcv)} Bs\n"
        f"💵 *MERCADO CRUDA (USD):* {format_rate_report(tasa_mercado_cruda)} Bs\n"
        f"✨ *REFERENCIAL DE CÁLCULO:* {tasa_mercado_redondeada:.2f} Bs\n\n"
        
        # --- SECCIÓN 2: OTROS VALORES ---
        f"💶 *EURO (BCV):* {format_rate_report(eur_bcv)} Bs\n"
        f"🇪🇺 *EURO (MERCADO):* {format_rate_report(tasa_eur_mercado)} Bs\n"
        f"💹 *EUR/USD Forex:* {forex_eur_usd:.5f}\n"
        f"⚖️ *EUR/USD BCV:* `{paridad_bcv:.4f}`\n\n"

        # --- SECCIÓN 3: INDICADORES Y VOLATILIDAD ---
        f"📊 *INDICADORES CLAVE*\n"
        f"🔺 *Brecha BCV/Mercado:* `{diferencia_porcentaje:.2f}%`\n"
        f"⚖️ *Factor de Ponderación (FPC):* `{fpc:.4f}`\n"
        f"_{tendencia_icon} El mercado está a {fpc:.4f}x la tasa oficial_\n\n"
        
        f"📈 *VOLATILIDAD (Últimas 24h) - Gráfico abajo*\n" # <<< AVISO DE LA FOTO
        f"⬆️ *Máximo:* {format_rate_report(max_24h)} Bs\n"
        f"⬇️ *Mínimo:* {format_rate_report(min_24h)} Bs\n"
        f" promedio de {count_24h} registros\n\n"
        
        # --- SECCIÓN 4: OTRAS DIVISAS (REFERENCIAL BCV) ---
        f"🌐 *OTRAS BCV* (Ref.)\n"
        f"🇨🇳 *CNY:* `{calc.latest_rates.get('CNY_BCV', 0.0):.4f}` | 🇹🇷 *TRY:* `{calc.latest_rates.get('TRY_BCV', 0.0):.4f}` | 🇷🇺 *RUB:* `{calc.latest_rates.get('RUB_BCV', 0.0):.4f}`\n\n"
        
        f"═════════════════════\n"
        f"📲 Usa /start para acceder a las herramientas de cálculo."
    )

    # 3. GENERAR Y ENVIAR EL GRÁFICO (FOTO)
    logging.info("Generando gráfico de mercado para el reporte...")
    plot_buffer = generate_market_plot(hours=24) # Devuelve el BytesIO

    if plot_buffer:
        # Enviar la FOTO con el reporte de texto como pie de foto (caption)
        try:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=plot_buffer, # Envía el buffer de bytes (la imagen)
                caption=reporte, # Usa el reporte como pie de foto
                parse_mode='Markdown'
            )
            plot_buffer.close() # Cierra el buffer después de enviarlo
            logging.info("Reporte horario enviado con éxito (Foto + Caption).")
            
        except Exception as e:
            logging.error(f"Fallo al enviar la foto de volatilidad: {e}. Enviando solo texto.")
            # Fallback si falla el envío de la foto
            await context.bot.send_message(
                chat_id=chat_id, 
                text="❌ Fallo al adjuntar el gráfico.\n\n" + reporte, 
                parse_mode='Markdown'
            )
            
    else:
        # Enviar solo el texto si el gráfico no se pudo generar
        logging.warning("No se pudo generar el gráfico. Enviando solo texto.")
        await context.bot.send_message(
            chat_id=chat_id, 
            text="❌ *Advertencia:* Fallo al generar el gráfico. Se adjunta el reporte de texto.\n\n" + reporte, 
            parse_mode='Markdown'
        )

# --- Funciones de Bot ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /start y muestra el menú de botones."""
    
    # Limpieza del estado al inicio para evitar errores de sesión
    context.user_data.pop('state', None)
    context.user_data.pop('currency', None)
    
    keyboard = [
        [InlineKeyboardButton("📊 Análisis de Compra", callback_data='analisis_compra')],
        [InlineKeyboardButton("📈 Costo de Oportunidad", callback_data='costo_oportunidad')],
        [InlineKeyboardButton("💱 Conversión de Precios", callback_data='cambio_divisas')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('¡Hola! Elige una opción para continuar:', reply_markup=reply_markup)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Maneja las selecciones de botones e implementa la selección de divisa (USD/EUR).
    """
    query = update.callback_query
    await query.answer()
    
    # Teclado genérico para selección de divisa
    keyboard_currency = [
        [InlineKeyboardButton("🇺🇸 USD", callback_data='CURRENCY_USD')],
        [InlineKeyboardButton("🇪🇺 EUR", callback_data='CURRENCY_EUR')],
    ]
    reply_markup_currency = InlineKeyboardMarkup(keyboard_currency)
    
    current_data = query.data
    current_state = context.user_data.get('state')
    
    # 1. El usuario selecciona la ACCIÓN -> Pedir Divisa
    if current_data == 'analisis_compra':
        context.user_data['state'] = SELECT_CURRENCY_COMPRA
        await query.edit_message_text(
            text="Por favor, selecciona la divisa para el *Análisis de Compra*:", 
            reply_markup=reply_markup_currency,
            parse_mode="Markdown"
        )
        
    elif current_data == 'costo_oportunidad':
        context.user_data['state'] = SELECT_CURRENCY_OPORTUNIDAD
        await query.edit_message_text(
            text="Por favor, selecciona la divisa para el *Costo de Oportunidad*:",
            reply_markup=reply_markup_currency,
            parse_mode="Markdown"
        )
        
    elif current_data == 'cambio_divisas':
        context.user_data['state'] = SELECT_CURRENCY_CAMBIO
        await query.edit_message_text(
            text="Por favor, selecciona la divisa para la *Conversión de Precios*:",
            reply_markup=reply_markup_currency,
            parse_mode="Markdown"
        )

    # 2. El usuario selecciona la DIVISA -> Pedir Input Numérico
    elif current_data.startswith('CURRENCY_') and current_state in [SELECT_CURRENCY_COMPRA, SELECT_CURRENCY_OPORTUNIDAD, SELECT_CURRENCY_CAMBIO]:
        currency_code = current_data.split('_')[1]
        context.user_data['currency'] = currency_code
        
        # Mapear la acción al nuevo estado de espera de input
        if current_state == SELECT_CURRENCY_COMPRA:
            context.user_data['state'] = AWAITING_INPUT_COMPRA
            msg = f"Ingresa el costo del producto y la cantidad de {currency_code} disponibles (ej: `300 150`)"
        elif current_state == SELECT_CURRENCY_OPORTUNIDAD:
            context.user_data['state'] = AWAITING_INPUT_OPORTUNIDAD
            msg = f"Ingresa la cantidad de {currency_code} a vender (ej: `300`)"
        elif current_state == SELECT_CURRENCY_CAMBIO:
            context.user_data['state'] = AWAITING_INPUT_CAMBIO
            msg = f"Ingresa el precio del producto o servicio en {currency_code} (ej: `50`)"
        else:
            msg = "❌ Error interno de estado. Por favor, reinicia con /start."
            
        await query.edit_message_text(f"Seleccionaste *{currency_code}*. {msg}", parse_mode="Markdown")
        
    else:
        await query.edit_message_text("Acción no reconocida. Por favor, usa /start para comenzar de nuevo.")


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los mensajes de texto del usuario según el estado actual."""
    
    current_state = context.user_data.get('state')
    currency_code = context.user_data.get('currency', 'USD') # Por defecto USD si falta
    
    if current_state not in [AWAITING_INPUT_COMPRA, AWAITING_INPUT_OPORTUNIDAD, AWAITING_INPUT_CAMBIO]:
        await update.message.reply_text("Por favor, elige una opción del menú primero usando /start.")
        return

    try:
        valores = [float(val) for val in update.message.text.split()]
        
        # 🚨 INSTANCIAR Y VALIDAR EL CALCULADOR 🚨
        calc = ExchangeRateCalculator()
        
        if not calc.is_valid():
            await update.message.reply_text("No se pudieron obtener las tasas de cambio de la base de datos para los cálculos. Intenta más tarde.")
            return

        response = ""

        if current_state == AWAITING_INPUT_COMPRA:
            if len(valores) != 2:
                await update.message.reply_text("❌ Entrada incorrecta. Debes ingresar dos números: costo y divisas (ej: `300 150`)")
                return
            response, _ = calc.analyze_purchase(valores[0], valores[1], currency=currency_code)
        
        elif current_state == AWAITING_INPUT_OPORTUNIDAD:
            if len(valores) != 1:
                await update.message.reply_text("❌ Entrada incorrecta. Debes ingresar un solo número: la cantidad de divisas (ej: `300`)")
                return
            response, _ = calc.analyze_opportunity_cost(valores[0], currency=currency_code)

        elif current_state == AWAITING_INPUT_CAMBIO:
            if len(valores) != 1:
                await update.message.reply_text("❌ Entrada incorrecta. Debes ingresar un solo número: el precio en la divisa seleccionada (ej: `50`)")
                return
            response, _ = calc.convert_price(valores[0], currency=currency_code)
        
        # Resetear estado y divisa
        context.user_data.pop('state', None)
        context.user_data.pop('currency', None)
        
        await update.message.reply_text(response, parse_mode="Markdown")
        await start(update, context) # Volver al menú principal
    
    except ValueError:
        await update.message.reply_text("❌ Formato incorrecto. Por favor, ingresa solo números separados por espacios.")

# --- Configuración de comandos del bot (se mantiene igual) ---
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
    
    # 1. Ejecución INMEDIATA: Dispara el primer reporte 1 segundo después de iniciar
    job_queue.run_once(send_hourly_report, when=1, data=CHAT_ID) 
    print("Primer reporte programado para enviarse en 1 segundo.")

    # 2. Actualización de DB RECURRENTE (Cada 600 segundos = 10 minutos)
    job_queue.run_repeating(update_exchange_rates, 
                            interval=600, 
                            data=None) # No necesita CHAT_ID, solo actualiza DB
    print("Actualización de DB recurrente programada cada 10 minutos.")
    
    # 3. Notificación RECURRENTE (Cada 3600 segundos = 1 hora)
    job_queue.run_repeating(send_hourly_report, 
                            interval=3600, 
                            data=CHAT_ID)
    print("Reporte recurrente programado para repetirse cada 1 hora.")
    
    # Añade los handlers para la interacción a demanda
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("Bot interactivo iniciado. Envía /start en Telegram para interactuar.")
    application.run_polling()