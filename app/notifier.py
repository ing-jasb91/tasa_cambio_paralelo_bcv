# app/notifier.py

import logging
import logging.handlers # <--- AÑADE ESTA LÍNEA
import pytz
import datetime
import os
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, error
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


# logging.basicConfig(
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
#     level=logging.DEBUG 
# )

# --- Configuración de Logging Avanzada ---
LOGS_DIR = 'logs'
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)


# 1. Crear un formateador con todos los detalles solicitados
# Formato: [TIEMPO-ZONA HORARIA] [SEVERIDAD] [MÓDULO.FUNCIÓN:LÍNEA] [MENSAJE]
log_formatter = logging.Formatter(
    fmt='%(asctime)s [%(levelname)s] [%(name)s.%(funcName)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


# 2. Configurar el logger principal (Root Logger)
# Establecer el nivel mínimo para el logger principal. 
# Si está en INFO, solo procesará INFO, WARNING, ERROR, CRITICAL.
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO) # Nivel base

# 3. Crear el Handler para Archivos de INFO (Incluye INFO, WARNING, ERROR)
info_handler = logging.handlers.RotatingFileHandler(
    os.path.join(LOGS_DIR, 'info.log'),
    maxBytes=1048576, # 1MB
    backupCount=5,
    encoding='utf-8'
)
info_handler.setLevel(logging.INFO)
info_handler.setFormatter(log_formatter)
root_logger.addHandler(info_handler)


# 4. Crear el Handler para Archivos de ERROR (Solo ERROR y CRITICAL)
error_handler = logging.handlers.RotatingFileHandler(
    os.path.join(LOGS_DIR, 'error.log'),
    maxBytes=1048576, # 1MB
    backupCount=5,
    encoding='utf-8'
)
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(log_formatter)
root_logger.addHandler(error_handler)


# 5. Handler de Consola (Opcional, pero útil)
# console_handler = logging.StreamHandler()
# console_handler.setLevel(logging.INFO)
# console_handler.setFormatter(log_formatter)
# root_logger.addHandler(console_handler)

# Ahora, el logger usado en notifier.py debe ser 'logger'
logger = logging.getLogger(__name__)
# El logger del módulo no necesita reconfigurar el nivel si ya lo hace el root.
# Sin embargo, lo mantendremos para coherencia:
logger.setLevel(logging.INFO) 


# --- Configuración del Bot de Telegram ---
load_dotenv() 
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
# print(CHAT_ID)
# --- Constantes de la Aplicación ---
# Las constantes de estado de conversación (10, 11, etc.) se ELIMINAN y se reemplazan por BotState


# ----------------------------------------------------------------------
# --- 1. Funciones Auxiliares (Reporte y Jobs) ---
# ----------------------------------------------------------------------

# Función Auxiliar
def build_main_keyboard() -> InlineKeyboardMarkup:
    """Crea y devuelve el teclado principal."""
    keyboard = [
        [InlineKeyboardButton("📊 Análisis de Compra", callback_data='flow_compra')],
        [InlineKeyboardButton("📈 Costo de Oportunidad", callback_data='flow_oportunidad')],
        [InlineKeyboardButton("💱 Conversión de Precios", callback_data='flow_cambio')],
        # 🚨 NUEVO BOTÓN 🚨
        [InlineKeyboardButton("⚖️ Punto de Equilibrio", callback_data='reporte_equilibrio')], 
        [InlineKeyboardButton("🔔 Configurar Alerta", callback_data='flow_alerta')],
        [InlineKeyboardButton("📊 Reporte Diario", callback_data='reporte_diario')],
        [InlineKeyboardButton("📈 Volatilidad (48h)", callback_data='volatilidad_48h')],
    ]
    return InlineKeyboardMarkup(keyboard)

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


# async def update_exchange_rates(context: ContextTypes.DEFAULT_TYPE):
#     """Job recurrente para actualizar las tasas de cambio en la DB."""
#     try:
#         tasa_bcv, tasa_mercado_cruda, tasa_mercado_redondeada = get_exchange_rates()
#         logging.info("Actualización de tasas en segundo plano ejecutada.")
        
#         # 🚨 FUTURO: Lógica de verificación de alertas
#         # await check_and_trigger_alerts(context) 
        
#     except Exception as e:
#         logging.error(f"FALLO al ejecutar el job de actualización de tasas: {e}")

async def send_hourly_report(context: ContextTypes.DEFAULT_TYPE):
    """
    Función que se ejecuta por JobQueue para enviar el reporte de tasas cada hora.
    Ahora envía un reporte de texto con el gráfico adjunto.
    """
    job = context.job
    chat_id = job.data

    # 1. Obtener datos y resumen
    calculator = ExchangeRateCalculator()
    summary_24h = get_24h_market_summary() # Obtener el resumen de 24h
    # 2. Generar el reporte de texto (usando el resumen)
    reporte_texto = calculator.get_exchange_rates_report(summary_24h)

    # 3. Generar el gráfico de volatilidad (devuelve un objeto BytesIO en memoria)
    image_buffer = generate_market_plot(hours=48) # Generamos el gráfico de 48h (el resumen es de 24h)
    
    # 4. Enviar el mensaje
    if image_buffer:
        # 🚨 CRÍTICO: Usar send_photo para adjuntar el texto como caption (título) 🚨
        try:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=image_buffer, # El objeto BytesIO (imagen)
                caption=reporte_texto,
                parse_mode='Markdown'
            )
            logging.info(f"Reporte de tasas y gráfico enviados a chat {chat_id}.")
        except Exception as e:
            logging.error(f"Error al enviar la foto/reporte al chat: {e}")
    else:
        # Enviar solo el texto si el gráfico falló
        await context.bot.send_message(
            chat_id=chat_id,
            text=reporte_texto,
            parse_mode='Markdown'
        )
        logging.warning("Gráfico falló. Reporte de tasas enviado solo como texto.")


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
 # 🚨 CORRECCIÓN CRÍTICA: Añadir esta verificación 🚨
    # El job de 10 minutos se programó con data=None, por lo que debe saltar el envío.
        if chat_id is None:
            logger.info("Job de actualización de DB completado. Omitiendo notificación por falta de chat_id.")
            # ⚠️ Si solo quiere notificar en el chat del job, puede usar 'return' aquí.
            # PERO, si también quiere enviar el reporte a un canal fijo (su CHAT_ID global),
            # debe usar el global como respaldo si está definido:
            if CHAT_ID: # Usamos la variable global importada del .env
                chat_id = CHAT_ID
            else:
                # Si no hay chat_id ni en el job ni en el global, salimos de la notificación
                return
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
# app/notifier.py (Añadir después de send_hourly_report)

async def send_volatility_plot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Genera y envía el gráfico de volatilidad del mercado."""
    chat_id = update.effective_chat.id if update.effective_chat else context.job.data
    
    # Llama a la función de src/plot_generator.py
    plot_path = generate_market_plot() 
    
    if plot_path and os.path.exists(plot_path):
        try:
            # Envía la foto (el gráfico)
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=open(plot_path, 'rb'),
                caption="📈 *Volatilidad del Dólar Mercado (Últimas 48h)*",
                parse_mode='Markdown'
            )
            logging.info(f"Gráfico de volatilidad enviado a chat_id: {chat_id}")
            
            # Opcional: Eliminar el archivo después de enviarlo para mantener la carpeta limpia
            os.remove(plot_path)
            
        except Exception as e:
            logging.error(f"Error al enviar el gráfico: {e}")
            await context.bot.send_message(chat_id=chat_id, text="❌ Error al enviar el gráfico.")
    else:
        await context.bot.send_message(chat_id=chat_id, text="❌ No hay suficientes datos históricos (mínimo 2) para generar el gráfico.")

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
    
    reply_markup = build_main_keyboard()
    
    if update.message:
        await update.message.reply_text('¡Hola! Elige una opción para continuar:', reply_markup=reply_markup)
    else: # Si viene de un callback fallback
        await update.callback_query.edit_message_text('¡Hola! Elige una opción para continuar:', reply_markup=reply_markup)

    # Retorna el estado START
    return BotState.START.value

def build_currency_selection_keyboard(flow_name: str):
    """
    Crea un teclado para seleccionar USD o EUR.
    flow_name debe ser 'COMPRA', 'OPORTUNIDAD', o 'CAMBIO'.
    """
    keyboard = [
        [
            InlineKeyboardButton("💵 USD", callback_data=f'{flow_name}_USD'),
            InlineKeyboardButton("💶 EUR", callback_data=f'{flow_name}_EUR')
        ],
        [InlineKeyboardButton("⬅️ Menú Principal", callback_data='start')]
    ]
    return InlineKeyboardMarkup(keyboard)


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
            reporte, _ = calc.get_compra_report(costo, cantidad, currency)
            await update.message.reply_text(f"✅ *Resultado Análisis de Compra ({currency}):*\n\n{reporte}", parse_mode='Markdown')
            
        elif flow == 'oportunidad':
            # Ejemplo: Validar y calcular la Oportunidad
            cantidad = float(text)
            reporte, _ = calc.get_oportunidad_report(cantidad, currency)
            await update.message.reply_text(f"✅ *Resultado Costo de Oportunidad ({currency}):*\n\n{reporte}", parse_mode='Markdown')

        elif flow == 'cambio':
            # Ejemplo: Validar y calcular el Cambio
            cantidad = float(text)
            reporte_str, _ = calc.get_conversion_report(cantidad, currency)
            await update.message.reply_text(f"✅ *Resultado Conversión ({currency}):*\n\n{reporte_str}", parse_mode='Markdown')

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

async def handle_main_menu_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja los callbacks de Reporte Diario y Volatilidad (48h)."""
    query = update.callback_query
    await query.answer() # Siempre responde al callback para quitar el reloj

    data = query.data
    chat_id = update.effective_chat.id
    
    # Reutilizamos el teclado principal
    reply_markup = build_main_keyboard()

    # --- 1. REPORTE DIARIO (Reporte Completo + Volatilidad 24h) ---
    if data == 'reporte_diario':
        await context.bot.send_message(chat_id=chat_id, text="⏳ Generando Reporte Diario...")
        summary_24h = get_24h_market_summary() # Obtener el resumen de 24h
        calculator = ExchangeRateCalculator()
        reporte_principal = calculator.get_exchange_rates_report(summary_24h)
        
        # 🚨 Solución al KeyError: Usar .get() y validar la data 🚨
        summary = get_24h_market_summary()
        reporte_24h = ""
        
        if isinstance(summary, dict) and summary.get('count', 0) > 0:
            # Usar .get() con un valor por defecto para prevenir KeyError
            period_text = summary.get('period', 'Últimas 24h') 
            
            # Formateamos el reporte de volatilidad
            reporte_24h = (
                f"\n--- *Volatilidad del Mercado ({period_text})* ---\n"
                f"📈 Máx: {format_currency(summary['max'], 4)} Bs/USD\n"
                f"📉 Mín: {format_currency(summary['min'], 4)} Bs/USD\n"
                f"⭐ Promedio: {format_currency(summary['avg'], 4)} Bs/USD\n"
                f"═════════════════════════\\n"
            )
        
        reporte_completo = reporte_principal + reporte_24h
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=reporte_completo,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        # Volvemos al estado START para que el menú se mantenga activo
        return BotState.START.value
    
    # --- 2. VOLATILIDAD (Gráfico de 48h) ---
    elif data == 'volatilidad_48h':
        await context.bot.send_message(chat_id=chat_id, text="⏳ Generando Gráfico de Volatilidad (48h)...")
        
        # generate_market_plot(hours=48) devuelve un BytesIO buffer
        # plot_buffer = generate_market_plot(hours=48)
        
        # if plot_buffer:
        #     await context.bot.send_photo(
        #         chat_id=chat_id,
        #         photo=plot_buffer,
        #         caption="📈 *Volatilidad del USD Mercado (Últimas 48 Horas)*\n\nEl gráfico muestra la variación del precio USD/VES en el mercado de referencia.",
        #         reply_markup=reply_markup,
        #         parse_mode='Markdown'
        #     )
        # else:
        #     await context.bot.send_message(
        #         chat_id=chat_id,
        #         text="❌ Error al generar el gráfico. Asegúrate de tener suficientes datos históricos.",
        #         reply_markup=reply_markup,
        #         parse_mode='Markdown'
        #     )
        try:
            plot_buffer = generate_market_plot(hours=48)
            await context.bot.send_photo(
                chat_id=chat_id, # Ahora chat_id tiene un valor válido
                photo=plot_buffer,
                caption="📈 *Volatilidad del USD Mercado (Últimas 48 Horas)*\n\nEl gráfico muestra la variación del precio USD/VES en el mercado de referencia.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
                )
        except error.BadRequest as e:
            # Esto solo debería ocurrir si el CHAT_ID es inválido (no empty) o el bot no tiene acceso
            logger.error(f"Fallo al enviar la foto de volatilidad: Chat_id is empty. Enviando solo texto. Error: {e}")
            # Line 357
            await context.bot.send_message(
                chat_id=chat_id, # Ahora chat_id tiene un valor válido
                text="❌ Error al generar el gráfico. Asegúrate de tener suficientes datos históricos.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
                )

        
        return BotState.START.value
        
    # Si no es un reporte, dejamos que el flujo normal (ConversationHandler) continúe.
    # Los flujos flow_compra, flow_oportunidad, etc., ya deben estar manejados
    # por otros handlers o por la función que llama a este handler.
    # Si quieres que este handler maneje todos los callbacks del menú,
    # puedes añadir aquí las redirecciones a los estados:
    # elif data == 'flow_compra':
    #     return BotState.SELECT_CURRENCY_COMPRA.value
    
    # Dejaremos que el ConversationHandler se encargue de los otros flujos para no tocar start.
    return BotState.START.value

# app/notifier.py (Añadir entre las funciones de comandos)

async def break_even_point_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Muestra el reporte del Punto de Equilibrio (Break-Even), manejando Command y Callback."""
    
    # 1. Identificar la fuente del Update y el objeto para responder
    if update.callback_query:
        query = update.callback_query
        await query.answer() 
        message_container = query.message
    elif update.message:
        message_container = update.message
    else:
        return BotState.START.value 

    # 2. Notificar que se está procesando
    if update.effective_chat:
        await update.effective_chat.send_chat_action(action='TYPING')
    
    # 3. Obtener la información de las tasas y el cálculo
    calculator = ExchangeRateCalculator()
    reporte = calculator.get_break_even_report() 

    # 4. Enviar el reporte
    await message_container.reply_text(
        text=reporte, 
        parse_mode='Markdown'
    )

    # 5. Finalizar la conversación y regresar al estado inicial
    return BotState.START.value
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


# app/notifier.py (Añade o verifica que estas funciones existen)

# Asumiendo que BotState está importado de src.bot_states
# from src.bot_states import BotState 

async def handle_flow_compra(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el flujo de Análisis de Compra."""
    query = update.callback_query
    await query.answer()
    # Lógica para pedir la divisa de compra
    await query.edit_message_text("💵 *Análisis de Compra:*\nSelecciona la divisa que deseas analizar (USD o EUR).", 
                                  reply_markup=build_currency_selection_keyboard('COMPRA'),
                                  parse_mode='Markdown')
    # Retorna el estado correcto para continuar el flujo
    return BotState.SELECT_CURRENCY_COMPRA.value 

# Debes hacer lo mismo con el resto de los flujos que uses en tu ConversationHandler:
async def handle_flow_oportunidad(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el flujo de Costo de Oportunidad."""
    # ... Lógica ...
    return BotState.SELECT_CURRENCY_OPORTUNIDAD.value

async def handle_flow_cambio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el flujo de Conversión de Precios."""
    # ... Lógica ...
    return BotState.SELECT_CURRENCY_CAMBIO.value

async def handle_flow_alerta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el flujo de Configuración de Alerta."""
    # ... Lógica ...
    return BotState.SELECT_ALERT_CURRENCY.value


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
        entry_points=[
            CommandHandler('start', start),
            CommandHandler('equilibrio', break_even_point_command), 
            ],
        
        states={
            # # 0. ESTADO INICIAL: Espera la selección de flujo (Compra, Oportunidad, Cambio, Alerta)
            # BotState.START.value: [
            #     CallbackQueryHandler(select_flow, pattern='^flow_'),
            # ],
                    # 1. ESTADO PRINCIPAL (MENÚ)
        BotState.START.value: [
            # 🚨 AÑADE ESTE HANDLER AQUÍ 🚨
            CallbackQueryHandler(select_flow, pattern='^flow_'),
                # 🚨 NUEVA LÍNEA: Manejar el botón de Punto de Equilibrio 🚨
            CallbackQueryHandler(break_even_point_command, pattern='^reporte_equilibrio$'), 
            CallbackQueryHandler(handle_main_menu_callbacks, pattern='^reporte_diario$|^volatilidad_48h$'),
            
            # Los otros handlers para los flujos principales (flow_compra, etc.)
            CallbackQueryHandler(handle_flow_compra, pattern='^flow_compra$'), # Ejemplo: Asegúrate de que esto exista
            # ...
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