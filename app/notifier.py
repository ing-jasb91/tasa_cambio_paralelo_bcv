# app/notifier.py

import logging
import pytz
import datetime
import os
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    JobQueue,
    ConversationHandler # <--- NECESARIO para la refactorización
)

# Importaciones de módulos locales
from src.data_fetcher import get_exchange_rates
from src.database_manager import get_latest_rates, get_24h_market_summary 
from src.calculator import ExchangeRateCalculator, format_currency  # Clase centralizada
from src.plot_generator import generate_market_plot
from src.bot_states import BotState # Importar los estados desde bot_states.py
from src.database_manager import get_active_alerts, update_alert_rate_and_status


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.ERROR 
)

# --- Configuración del Bot de Telegram ---
load_dotenv() 
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

# --- Constantes de la Aplicación ---
# Las constantes de estado de conversación (10, 11, etc.) se ELIMINAN y se reemplazan por BotState


# ----------------------------------------------------------------------
# --- 1. Funciones Auxiliares (Reporte y Jobs) ---
# ----------------------------------------------------------------------

# (Asumiendo que format_rate_report está definido o se importa desde calculator)
def format_rate_report(rate):
    # Asume que esta función se usa para formatear tasas en el reporte. 
    # Si está en calculator.py, úsala:
    from src.calculator import format_currency 
    return format_currency(rate, decimals=4)


async def post_init(application: Application) -> None:
    """Configura los comandos del bot."""
    await application.bot.set_my_commands([
        BotCommand("start", "Inicia el bot y muestra el menú principal"),
        BotCommand("cancelar", "Cancela cualquier conversación actual"),
    ])


async def update_exchange_rates(context: ContextTypes.DEFAULT_TYPE):
    """Job recurrente para actualizar las tasas de cambio en la DB."""
    try:
        tasa_bcv, tasa_mercado_cruda, tasa_mercado_redondeada = get_exchange_rates()
        logging.info("Actualización de tasas en segundo plano ejecutada.")
        
        # 🚨 FUTURO: Lógica de verificación de alertas
        # await check_and_trigger_alerts(context) 
        
    except Exception as e:
        logging.error(f"FALLO al ejecutar el job de actualización de tasas: {e}")


async def send_hourly_report(context: ContextTypes.DEFAULT_TYPE):
    """Genera y envía un reporte completo (Texto + Gráfico)."""
    chat_id = context.job.data
    
    try:
        # Llama a la extracción. force_save=True anula la lógica de volatilidad.
        get_exchange_rates(force_save=True)
    except Exception as e:
        logging.error(f"FALLO al forzar la actualización para el reporte horario: {e}")
        
    calc = ExchangeRateCalculator()
    
    if not calc.is_valid():
        await context.bot.send_message(chat_id=chat_id, text="❌ Error: No se pudieron obtener las tasas de cambio de la base de datos.")
        return
    

# app/notifier.py (Añadir esta función)

from src.database_manager import get_active_alerts, update_alert_rate_and_status

async def check_and_trigger_alerts(context: ContextTypes.DEFAULT_TYPE):
    """Verifica si alguna alerta activa se ha disparado y notifica al usuario."""
    
    # 1. Obtener la tasa de mercado actual (la base para la comparación)
    calc = ExchangeRateCalculator()
    current_rate = calc.USD_MERCADO_CRUDA # Usamos la tasa cruda como referencia
    
    if current_rate <= 0:
        logging.error("No se pudo obtener la tasa actual para chequear alertas.")
        return

    # 2. Obtener la tasa de hace 24h para calcular el cambio
    market_summary = get_24h_market_summary() # Asume que esta función existe y obtiene el promedio/min/max de 24h
    avg_24h_rate = market_summary.get('avg', current_rate) # Usamos el promedio de 24h como línea base de volatilidad.
    
    if avg_24h_rate <= 0:
        logging.warning("No hay suficientes datos históricos (24h) para chequear alertas de volatilidad.")
        return

    # 3. Obtener todas las alertas activas
    active_alerts = get_active_alerts()
    
    for alert in active_alerts:
        alert_id = alert['id']
        chat_id = alert['chat_id']
        currency = alert['currency']
        direction = alert['direction']
        threshold = alert['threshold_percent'] # Ej: 1.5
        
        # Porcentaje de cambio actual respecto a la media de 24h
        change_from_24h_avg = ((current_rate / avg_24h_rate) - 1) * 100
        
        is_triggered = False
        
        if direction == 'UP' and change_from_24h_avg >= threshold:
            is_triggered = True
            message = (
                f"🔔 *ALERTA ACTIVADA (SUBIDA)* 📈\n\n"
                f"La tasa del *{currency}* ha subido *{change_from_24h_avg:.2f}%* en las últimas 24h, superando tu umbral de *{threshold:.2f}%*.\n"
                f"Tasa Actual: *{format_currency(current_rate, decimals=4)}* Bs."
            )
            
        elif direction == 'DOWN' and change_from_24h_avg <= -threshold: # Debe ser menor o igual al umbral negativo
            is_triggered = True
            message = (
                f"🔔 *ALERTA ACTIVADA (BAJADA)* 📉\n\n"
                f"La tasa del *{currency}* ha bajado *{abs(change_from_24h_avg):.2f}%* en las últimas 24h, superando tu umbral de *{threshold:.2f}%*.\n"
                f"Tasa Actual: *{format_currency(current_rate, decimals=4)}* Bs."
            )
        
        if is_triggered:
            # 4. Enviar la notificación al usuario
            try:
                await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
                logging.info(f"Alerta {alert_id} disparada para chat {chat_id}.")
                
                # 5. Desactivar la alerta (para que no se dispare en el siguiente chequeo)
                update_alert_rate_and_status(alert_id, current_rate, deactivate=True)
                
            except Exception as e:
                logging.error(f"Fallo al enviar la alerta a {chat_id}: {e}")
                # Si falla el envío, la mantenemos activa para intentar de nuevo.


#### B. Llamar la función en el Job Recurrente

# app/notifier.py (Modificar la función update_exchange_rates)

async def update_exchange_rates(context: ContextTypes.DEFAULT_TYPE):
    """Job recurrente para actualizar las tasas de cambio en la DB."""
    try:
        tasa_bcv, tasa_mercado_cruda, tasa_mercado_redondeada = get_exchange_rates()
        logging.info("Actualización de tasas en segundo plano ejecutada.")

        # 🚨 ANTES: Este job NO recibe chat_id, ya que su data es None
        chat_id = context.job.data 

        # 🚨 LLAMADA CRÍTICA: Chequear alertas después de actualizar las tasas 🚨
        await check_and_trigger_alerts(context)
        
    except Exception as e:
        logging.error(f"FALLO al ejecutar el job de actualización de tasas: {e}")

    calc = ExchangeRateCalculator() # Reinstancia para obtener las tasas actualizadas

    # 1. CÁLCULOS PRINCIPALES
    tasa_bcv = calc.USD_BCV
    tasa_mercado_cruda = calc.USD_MERCADO_CRUDA
    tasa_mercado_redondeada = calc.USD_MERCADO_REDONDEADA 
    eur_bcv = calc.EUR_BCV
    forex_eur_usd = calc.EUR_USD_FOREX

    paridad_bcv = eur_bcv / tasa_bcv if tasa_bcv else 0.0
    tasa_eur_mercado = calc.EUR_MERCADO_CRUDA 
    diferencia_porcentaje = ((tasa_mercado_cruda / tasa_bcv) - 1) * 100
    fpc = tasa_mercado_cruda / tasa_bcv
    
    # Resumen de 24 horas (Volatilidad)
    market_summary = get_24h_market_summary()
    max_24h = market_summary.get('max', tasa_mercado_cruda) if market_summary else tasa_mercado_cruda
    min_24h = market_summary.get('min', tasa_mercado_cruda) if market_summary else tasa_mercado_cruda
    avg_24h = market_summary.get('avg', tasa_mercado_cruda) if market_summary else tasa_mercado_cruda
    count_24h = market_summary.get('count', 0) if market_summary else 0

    # Lógica: Obtener la hora actual en VET
    zona_horaria_vzla = pytz.timezone('America/Caracas')
    hora_actual_vzla = datetime.datetime.now(zona_horaria_vzla)
    hora_reporte_str = hora_actual_vzla.strftime('%d/%m/%Y %I:%M %p. VET').replace('AM', 'a.m.').replace('PM', 'p.m.') 

    # Emojis de tendencia para la volatilidad
    tendencia_icon = "🟢" 
    if tasa_mercado_cruda > avg_24h:
        tendencia_icon = "🔴" 
    elif tasa_mercado_cruda < avg_24h:
        tendencia_icon = "🔵" 

    # 2. CONSTRUCCIÓN DEL REPORTE (CAPTION)
    reporte = (
        f"🌟 *REPORTE DE TASAS* {tendencia_icon} *Stats Dev* 🇻🇪\n"
        f"_{hora_reporte_str}_\n\n"
        f"═════════════════════\n\n"
        
        f"💰 *BCV OFICIAL (USD):* {format_rate_report(tasa_bcv)} Bs\n"
        f"💵 *MERCADO CRUDA (USD):* {format_rate_report(tasa_mercado_cruda)} Bs\n"
        f"✨ *REFERENCIAL DE CÁLCULO:* {tasa_mercado_redondeada:.2f} Bs\n\n"
        
        f"💶 *EURO (BCV):* {format_rate_report(eur_bcv)} Bs\n"
        f"🇪🇺 *EURO (MERCADO):* {format_rate_report(tasa_eur_mercado)} Bs\n"
        f"💹 *EUR/USD Forex:* {forex_eur_usd:.5f}\n"
        f"⚖️ *EUR/USD BCV:* `{paridad_bcv:.4f}`\n\n"

        f"📊 *INDICADORES CLAVE*\n"
        f"🔺 *Brecha BCV/Mercado:* `{diferencia_porcentaje:.2f}%`\n"
        f"⚖️ *Factor de Ponderación (FPC):* `{fpc:.4f}`\n"
        f"_{tendencia_icon} El mercado está a {fpc:.4f}x la tasa oficial_\n\n"
        
        f"📈 *VOLATILIDAD (Últimas 24h) - Gráfico adjunto*\n"
        f"⬆️ *Máximo:* {format_rate_report(max_24h)} Bs\n"
        f"⬇️ *Mínimo:* {format_rate_report(min_24h)} Bs\n"
        f" promedio de {count_24h} registros\n\n"
        
        f"🌐 *OTRAS BCV* (Ref.)\n"
        f"🇨🇳 *CNY:* `{calc.latest_rates.get('CNY_BCV', 0.0):.4f}` | 🇹🇷 *TRY:* `{calc.latest_rates.get('TRY_BCV', 0.0):.4f}` | 🇷🇺 *RUB:* `{calc.latest_rates.get('RUB_BCV', 0.0):.4f}`\n\n"
        
        f"═════════════════════\n"
        f"📲 Usa /start para acceder a las herramientas de cálculo."
    )

    # 3. GENERAR Y ENVIAR EL GRÁFICO (FOTO)
    plot_buffer = generate_market_plot(hours=24) # Devuelve el BytesIO



    if plot_buffer:
        try:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=plot_buffer, 
                caption=reporte, 
                parse_mode='Markdown'
            )
            plot_buffer.close()
        except Exception as e:
            logging.error(f"Fallo al enviar la foto de volatilidad: {e}. Enviando solo texto.")
            await context.bot.send_message(
                chat_id=chat_id, 
                text="❌ Fallo al adjuntar el gráfico.\n\n" + reporte, 
                parse_mode='Markdown'
            )
    else:
        logging.warning("No se pudo generar el gráfico. Enviando solo texto.")
        await context.bot.send_message(
            chat_id=chat_id, 
            text="❌ *Advertencia:* Fallo al generar el gráfico. Se adjunta el reporte de texto.\n\n" + reporte, 
            parse_mode='Markdown'
        )


# ----------------------------------------------------------------------
# --- 2. Funciones de Conversación (Refactorizadas con ConversationHandler) ---
# ----------------------------------------------------------------------

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela la conversación actual."""
    context.user_data.clear()
    await update.message.reply_text(
        'Operación cancelada. Usa /start para comenzar de nuevo.',
        reply_markup=InlineKeyboardMarkup([])
    )
    return ConversationHandler.END


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja el comando /start y muestra el menú de botones."""
    
    # Limpiamos solo datos auxiliares, el ConversationHandler maneja el estado
    context.user_data.pop('flow', None) 
    context.user_data.pop('currency', None) 
    
    keyboard = [
        [InlineKeyboardButton("📊 Análisis de Compra", callback_data='flow_compra')],
        [InlineKeyboardButton("📈 Costo de Oportunidad", callback_data='flow_oportunidad')],
        [InlineKeyboardButton("💱 Conversión de Precios", callback_data='flow_cambio')],
        [InlineKeyboardButton("🔔 Configurar Alerta", callback_data='flow_alerta')], # Listo para el futuro
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text('¡Hola! Elige una opción para continuar:', reply_markup=reply_markup)
    else: # Si viene de un callback fallback
        await update.callback_query.edit_message_text('¡Hola! Elige una opción para continuar:', reply_markup=reply_markup)

    # Retorna el estado START
    return BotState.START.value


async def select_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja la selección inicial del menú y pide la divisa, luego transiciona."""
    query = update.callback_query
    await query.answer()
    
    flow = query.data.split('_')[1] # 'compra', 'oportunidad', 'cambio', o 'alerta'
    context.user_data['flow'] = flow 
    
    # --- Lógica Específica para Alerta (Inicio del flujo) ---
    if flow == 'alerta':
        # Por simplicidad inicial, la alerta será solo para USD
        keyboard_alert = [
            [InlineKeyboardButton("🇺🇸 USD", callback_data='ALERT_CURRENCY_USD')]
        ]
        reply_markup_alert = InlineKeyboardMarkup(keyboard_alert)

        await query.edit_message_text(
            text="Has seleccionado *Configurar Alerta*. Por favor, selecciona la divisa que deseas monitorear:",
            reply_markup=reply_markup_alert,
            parse_mode="Markdown"
        )
        # Transiciona al estado de selección de divisa de alerta
        return BotState.SELECT_ALERT_CURRENCY.value 
        
    # --- Lógica General para Cálculo (Compra/Oportunidad/Cambio) ---
    
    keyboard_currency = [
        [InlineKeyboardButton("🇺🇸 USD", callback_data='CURRENCY_USD')],
        [InlineKeyboardButton("🇪🇺 EUR", callback_data='CURRENCY_EUR')],
    ]
    
    if flow == 'cambio':
        keyboard_currency.append([InlineKeyboardButton("🏦 BCV (Oficial)", callback_data='CURRENCY_BCV')])
    
    reply_markup_currency = InlineKeyboardMarkup(keyboard_currency)
    
    # Mapeo de flujo a estado y mensaje
    flow_map = {
        'compra': (BotState.SELECT_CURRENCY_COMPRA.value, "Selecciona la divisa para el *Análisis de Compra*:"),
        'oportunidad': (BotState.SELECT_CURRENCY_OPORTUNIDAD.value, "Selecciona la divisa para el *Costo de Oportunidad*:"),
        'cambio': (BotState.SELECT_CURRENCY_CAMBIO.value, "Selecciona la divisa para la *Conversión de Precios*:"),
    }
    
    next_state, msg_text = flow_map.get(flow, (BotState.START.value, "❌ Opción no válida. Reinicia con /start."))

    await query.edit_message_text(
        text=msg_text,
        reply_markup=reply_markup_currency,
        parse_mode="Markdown"
    )
    return next_state 


async def handle_currency_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja la selección de USD/EUR/BCV y pide el input numérico."""
    query = update.callback_query
    await query.answer()
    
    currency_code = query.data.split('_')[1]
    flow = context.user_data.get('flow')
    context.user_data['currency'] = currency_code
    
    # Mapeo del flujo actual al siguiente estado (AWAITING_INPUT)
    flow_msg_map = {
        'compra': (BotState.AWAITING_INPUT_COMPRA.value, f"Ingresa el costo del producto y la cantidad de {currency_code} disponibles (ej: `300 150`)"),
        'oportunidad': (BotState.AWAITING_INPUT_OPORTUNIDAD.value, f"Ingresa la cantidad de {currency_code} a vender (ej: `300`)"),
        'cambio': (BotState.AWAITING_INPUT_CAMBIO.value, f"Ingresa el precio del producto o servicio en {currency_code} (ej: `50`)"),
    }
    
    next_state, msg = flow_msg_map.get(flow, (ConversationHandler.END, "❌ Error de flujo. Por favor, reinicia con /start."))

    await query.edit_message_text(f"Seleccionaste *{currency_code}*. {msg}", parse_mode="Markdown")
    
    return next_state


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Procesa la entrada de texto numérico y realiza el cálculo final."""
    text = update.message.text
    flow = context.user_data.get('flow')
    currency = context.user_data.get('currency')
    
    # 🚨 NOTA IMPORTANTE: Aquí va la lógica de cálculo real 🚨
    # Debes implementar la validación de 'text' y la llamada a tu ExchangeRateCalculator.
    
    calc = ExchangeRateCalculator()
    
    try:
        if flow == 'compra':
            # Ejemplo: Validar y calcular la Compra
            costo, cantidad = map(float, text.split())
            reporte, tasa_ref = calc.get_compra_report(costo, cantidad, currency)
            await update.message.reply_text(f"✅ *Resultado Análisis de Compra ({currency}):*\n\n{reporte}", parse_mode='Markdown')
            
        elif flow == 'oportunidad':
            # Ejemplo: Validar y calcular la Oportunidad
            cantidad = float(text)
            reporte, tasa_ref = calc.get_oportunidad_report(cantidad, currency)
            await update.message.reply_text(f"✅ *Resultado Costo de Oportunidad ({currency}):*\n\n{reporte}", parse_mode='Markdown')

        elif flow == 'cambio':
            # Ejemplo: Validar y calcular el Cambio
            cantidad = float(text)
            reporte = calc.get_conversion_report(cantidad, currency)
            await update.message.reply_text(f"✅ *Resultado Conversión ({currency}):*\n\n{reporte}", parse_mode='Markdown')

        else:
            await update.message.reply_text("❌ Error: No se pudo determinar la operación a realizar.")
            
    except ValueError:
        await update.message.reply_text("❌ Error de formato. Asegúrate de ingresar solo números separados por espacio (si aplica).")
        return BotState(context.user_data['flow']).value # Vuelve al estado anterior de input
    except Exception as e:
        logging.error(f"Error en cálculo final para {flow}: {e}")
        await update.message.reply_text("❌ Error interno al procesar el cálculo. Por favor, intenta de nuevo.")
        
    # Finaliza y limpia
    context.user_data.clear() 
    await update.message.reply_text("✨ Proceso completado. Usa /start para un nuevo análisis.", reply_markup=InlineKeyboardMarkup([]))
    
    return ConversationHandler.END

# app/notifier.py (Añadir estas funciones a la sección de handlers)

from src.database_manager import save_user_alert # <--- Asegúrate de importar esto

async def handle_alert_direction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja la selección de la divisa (siempre USD por ahora) y pide la dirección (UP/DOWN)."""
    query = update.callback_query
    await query.answer()
    
    # Asumimos que la divisa ya fue seleccionada en 'select_flow' o que solo permites USD
    currency_code = "USD"
    context.user_data['currency'] = currency_code
    
    keyboard_direction = [
        [InlineKeyboardButton("📈 Sube por encima de", callback_data='ALERT_DIR_UP')],
        [InlineKeyboardButton("📉 Baja por debajo de", callback_data='ALERT_DIR_DOWN')],
    ]
    reply_markup_direction = InlineKeyboardMarkup(keyboard_direction)
    
    await query.edit_message_text(
        text=f"Monitoreando *{currency_code}*. ¿La alerta es por subida o bajada?",
        reply_markup=reply_markup_direction,
        parse_mode="Markdown"
    )
    
    return BotState.SELECT_ALERT_DIRECTION.value


async def handle_alert_percentage_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja la selección de dirección (UP/DOWN) y pide el umbral de porcentaje."""
    query = update.callback_query
    await query.answer()
    
    direction = query.data.split('_')[-1] # UP o DOWN
    context.user_data['direction'] = direction
    
    direction_text = "suba" if direction == 'UP' else "baje"
    
    await query.edit_message_text(
        text=f"Excelente. Ingresa el *porcentaje de cambio* (ej: `1.5` para que la tasa {direction_text} 1.5% con respecto al valor que tuvo hace 24 horas).",
        parse_mode="Markdown"
    )
    
    return BotState.AWAITING_INPUT_ALERT_PERCENTAGE.value


async def save_alert_and_end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Procesa la entrada del porcentaje, guarda la alerta y finaliza."""
    percentage_text = update.message.text
    chat_id = str(update.message.chat_id)
    currency = context.user_data.get('currency')
    direction = context.user_data.get('direction')

    try:
        threshold = float(percentage_text)
        if threshold <= 0:
            await update.message.reply_text("❌ El porcentaje debe ser un número positivo mayor a cero.")
            return BotState.AWAITING_INPUT_ALERT_PERCENTAGE.value # Vuelve a pedir input

        # Guardar la alerta en la base de datos
        success = save_user_alert(chat_id, currency, direction, threshold)
        
        if success:
            direction_word = "⬆️ Subida" if direction == 'UP' else "⬇️ Bajada"
            await update.message.reply_text(
                f"✅ *¡Alerta Activada!* Monitoreando el *{currency}* por una volatilidad de *{threshold:.2f}%* ({direction_word}).\n\n"
                f"Te notificaré tan pronto como se cumpla la condición. Usa /start para volver al menú.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("❌ Error al guardar la alerta. Por favor, intenta de nuevo más tarde.")

    except ValueError:
        await update.message.reply_text("❌ Formato no válido. Ingresa solo el número (ej: `1.5`).")
        return BotState.AWAITING_INPUT_ALERT_PERCENTAGE.value # Vuelve a pedir input

    # Finaliza la conversación
    context.user_data.clear()
    return ConversationHandler.END



# ----------------------------------------------------------------------
# --- 3. Configuración Principal del Bot ---
# ----------------------------------------------------------------------

def start_bot():
    """Configura y ejecuta el bot de Telegram."""
    if not BOT_TOKEN or not CHAT_ID:
        logging.critical("Falta BOT_TOKEN o CHAT_ID en .env. El bot no puede iniciar.")
        return

    # Intenta hacer una actualización forzada inicial
    try:
        get_exchange_rates(force_save=True)
    except Exception as e:
        logging.error(f"Fallo en la actualización inicial. El bot usará datos viejos. Error: {e}")
    
    # Configuración de la aplicación
    application = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    
    # Crea el JobQueue para tareas programadas
    job_queue = application.job_queue
    
    # Configuración de Jobs Recurrentes (Se mantiene igual)
    job_queue.run_once(send_hourly_report, when=1, data=CHAT_ID) 
    job_queue.run_repeating(update_exchange_rates, interval=600, data=None)
    job_queue.run_repeating(send_hourly_report, interval=3600, data=CHAT_ID)
    
    # ----------------------------------------------------------------------
    # --- HANDLER PRINCIPAL DE CONVERSACIÓN (REEMPLAZA EL FLUJO MANUAL) ---
    # ----------------------------------------------------------------------
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        
        states={
            # 0. ESTADO INICIAL: Espera la selección de flujo (Compra, Oportunidad, Cambio, Alerta)
            BotState.START.value: [
                CallbackQueryHandler(select_flow, pattern='^flow_'),
            ],
            
            # 1. FLUJO DE COMPRA
            BotState.SELECT_CURRENCY_COMPRA.value: [
                CallbackQueryHandler(handle_currency_selection, pattern='^CURRENCY_'),
            ],
            BotState.AWAITING_INPUT_COMPRA.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input),
            ],

            # 2. FLUJO DE OPORTUNIDAD
            BotState.SELECT_CURRENCY_OPORTUNIDAD.value: [
                CallbackQueryHandler(handle_currency_selection, pattern='^CURRENCY_'),
            ],
            BotState.AWAITING_INPUT_OPORTUNIDAD.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input),
            ],
            
            # 3. FLUJO DE CAMBIO
            BotState.SELECT_CURRENCY_CAMBIO.value: [
                CallbackQueryHandler(handle_currency_selection, pattern='^CURRENCY_'),
            ],
            BotState.AWAITING_INPUT_CAMBIO.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input),
            ],
            
            # 4. FLUJO DE ALERTA 🚨 NUEVOS ESTADOS 🚨
            BotState.SELECT_ALERT_CURRENCY.value: [
                # Si el callback es ALERT_CURRENCY_USD, llama a la función de dirección
                CallbackQueryHandler(handle_alert_direction, pattern='^ALERT_CURRENCY_USD$') 
            ],
            BotState.SELECT_ALERT_DIRECTION.value: [
                # Si el callback es ALERT_DIR_UP/DOWN, llama a pedir porcentaje
                CallbackQueryHandler(handle_alert_percentage_prompt, pattern='^ALERT_DIR_')
            ],
            BotState.AWAITING_INPUT_ALERT_PERCENTAGE.value: [
                # El input de texto llama a la función final de guardado
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_alert_and_end)
                ],
        },
        
        fallbacks=[CommandHandler('cancelar', cancel), CommandHandler('start', start)]
    )

    # 🚨 Sustitución: Eliminar handlers viejos y añadir el ConversationHandler 🚨
    # application.add_handler(CommandHandler('start', start)) # Esto ahora es parte del entry_point
    # application.add_handler(CallbackQueryHandler(button_handler)) # Eliminado

    application.add_handler(conv_handler)
    
    # Ejecuta el bot (polling)
    print("🚀 Bot iniciado y escuchando. Usa /start en Telegram.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)