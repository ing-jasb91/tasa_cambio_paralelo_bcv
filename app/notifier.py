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
from app.api_data import get_exchange_rates

# Habilitar el logging para ver mensajes de error
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- Configuración del Bot de Telegram ---
BOT_TOKEN = '8237802820:AAHqF-v8UO1lUPLD4SL9x3AoK3QzYepN_Ok'
CHAT_ID = '552061604'

# --- Constantes para los estados de conversación ---
ANALISIS_COMPRA = 1
COSTO_OPORTUNIDAD = 2

# --- Funciones de Cálculo ---
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
        poder_compra_bcv = (dolares_a_vender * tasa_actual) / tasa_bcv # NUEVO CÁLCULO
        
        response += "{:<10.2f} | {:<10.2f} | {:<12.2f} | {:<20.2f}\n".format(tasa_actual, perdida_bolivares, perdida_usd_mercado, poder_compra_bcv)
    
    return response

# --- Función para el reporte ---
async def send_hourly_report(context: ContextTypes.DEFAULT_TYPE):
    """Genera y envía un reporte completo de las tasas de cambio."""
    chat_id = context.job.data
    
    tasa_bcv, tasa_mercado_cruda, tasa_mercado_redondeada = get_exchange_rates()
    if not all([tasa_bcv, tasa_mercado_cruda, tasa_mercado_redondeada]):
        await context.bot.send_message(chat_id=chat_id, text="No se pudieron obtener las tasas de cambio.")
        return

    diferencia_cifras = tasa_mercado_cruda - tasa_bcv
    diferencia_porcentaje = (diferencia_cifras / tasa_bcv) * 100
    iac = ((tasa_mercado_cruda / tasa_bcv) - 1) * 100
    fpc = tasa_mercado_cruda / tasa_bcv

    reporte = (
        f"⏰ *Reporte de Tasas de Cambio (Automático)*\n\n"
        f"Tasa Oficial (BCV): {tasa_bcv:.4f} Bs/USD\n"
        f"Tasa Mercado (Cruda): {tasa_mercado_cruda:.4f} Bs/USD\n"
        f"Tasa Mercado (Redondeada): {tasa_mercado_redondeada:.4f} Bs/USD\n\n"
        f"Diferencia Cambiaria: {diferencia_cifras:.4f} Bs/USD ({diferencia_porcentaje:.2f}%)\n"
        f"IAC (%): {iac:.2f}%\n"
        f"FPC: {fpc:.4f}\n"
    )
    
    await context.bot.send_message(chat_id=chat_id, text=reporte, parse_mode="Markdown")

# --- Funciones de Bot ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /start y muestra el menú de botones."""
    keyboard = [
        [InlineKeyboardButton("📊 Análisis de Compra", callback_data='analisis_compra')],
        [InlineKeyboardButton("📈 Costo de Oportunidad", callback_data='costo_oportunidad')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('¡Hola! Elige una opción para continuar:', reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja las selecciones de botones y pide la información necesaria."""
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

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los mensajes de texto del usuario según el estado actual."""
    if 'state' not in context.user_data:
        await update.message.reply_text("Por favor, elige una opción del menú primero usando /start.")
        return

    try:
        valores = [float(val) for val in update.message.text.split()]
        tasa_bcv, _, tasa_mercado_redondeada = get_exchange_rates()
        
        if not all([tasa_bcv, tasa_mercado_redondeada]):
            await update.message.reply_text("No se pudieron obtener las tasas de cambio.")
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

        await update.message.reply_text(response, parse_mode="Markdown")
        context.user_data.pop('state', None) # Limpiar el estado
        await start(update, context) # Volver a mostrar el menú
    
    except ValueError:
        await update.message.reply_text("❌ Formato incorrecto. Por favor, ingresa solo números.")

# --- Configuración de comandos del bot ---
async def post_init(application: ApplicationBuilder):
    """Registra los comandos del bot en la API de Telegram."""
    commands = [
        BotCommand("start", "Inicia una conversación con el bot y muestra el menú."),
    ]
    await application.bot.set_my_commands(commands)
    logging.info("Comandos del bot registrados correctamente.")

if __name__ == "__main__":
    application = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    
    # Crea el JobQueue para tareas programadas
    job_queue = application.job_queue

    # 1. Programa el envío del reporte cada 3600 segundos (1 hora)
    job_queue.run_repeating(send_hourly_report, interval=3600, first=datetime.time(tzinfo=pytz.timezone('America/Caracas')), data=CHAT_ID)

    # 2. Lanza el primer reporte inmediatamente al iniciar
    job_queue.run_once(send_hourly_report, when=1, data=CHAT_ID)

    # Añade los handlers para la interacción a demanda
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("Bot interactivo iniciado. Envía /start en Telegram para interactuar.")
    application.run_polling()