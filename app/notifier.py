# notifier.py

import logging
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Habilitar el logging para ver mensajes de error
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- Configuración del Bot de Telegram ---
BOT_TOKEN = '8237802820:AAHqF-v8UO1lUPLD4SL9x3AoK3QzYepN_Ok'
CHAT_ID = '552061604'

# --- Funciones de Bot ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /start y da la bienvenida al usuario."""
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="¡Hola! Soy tu bot de análisis de divisas. Usa / para ver los comandos disponibles."
    )

async def analizar_compra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analiza el poder de compra con los argumentos del usuario."""
    try:
        costo_producto = float(context.args[0])
        dolares_disponibles = float(context.args[1])
    except (IndexError, ValueError):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Comando incorrecto. Usa: /analizar_compra [costo_producto] [dolares_disponibles]"
        )
        return

    # Aquí iría tu lógica de cálculo para el análisis de compra
    # Por simplicidad, se omite el código del cálculo que ya tienes,
    # ya que tu enfoque es agregar el autocompletado.
    
    # Ejemplo de respuesta
    response = (
        f"📊 *Análisis de Compra*\n"
        f"Producto: ${costo_producto:.2f} | Divisas: ${dolares_disponibles:.2f}\n"
        "Tu análisis de compra se mostrará aquí."
    )
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=response,
        parse_mode="Markdown"
    )

async def costo_oportunidad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Calcula el costo de oportunidad con los argumentos del usuario."""
    try:
        dolares_a_vender = float(context.args[0])
    except (IndexError, ValueError):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Comando incorrecto. Usa: /costo_oportunidad [dolares_a_vender]"
        )
        return

    # Aquí iría tu lógica de cálculo para el costo de oportunidad
    # Por simplicidad, se omite el código del cálculo que ya tienes,
    # ya que tu enfoque es agregar el autocompletado.

    # Ejemplo de respuesta
    response = (
        f"📊 *Costo de Oportunidad*\n"
        f"Divisas: ${dolares_a_vender:.2f}\n"
        "Tu análisis de costo de oportunidad se mostrará aquí."
    )
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=response,
        parse_mode="Markdown"
    )

# --- Configuración de comandos de bot ---
async def post_init(application: ApplicationBuilder):
    """Registra los comandos del bot en la API de Telegram."""
    commands = [
        BotCommand("start", "Inicia una conversación con el bot"),
        BotCommand("analizar_compra", "Analiza el poder de compra (ej. /analizar_compra 300 150)"),
        BotCommand("costo_oportunidad", "Calcula el costo de oportunidad (ej. /costo_oportunidad 300)")
    ]
    await application.bot.set_my_commands(commands)
    logging.info("Comandos del bot registrados correctamente.")

if __name__ == "__main__":
    application = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('analizar_compra', analizar_compra))
    application.add_handler(CommandHandler('costo_oportunidad', costo_oportunidad))
    
    print("Bot interactivo iniciado. Envía /start en Telegram para interactuar.")
    application.run_polling()