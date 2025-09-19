# notifier.py

import asyncio
import schedule
import time
from telegram import Bot
from telegram.constants import ParseMode
from app.api_data import get_exchange_rates

# --- Configuración del Bot de Telegram ---
# Reemplaza 'YOUR_BOT_TOKEN' con el token de tu bot de Telegram
# Reemplaza 'YOUR_CHAT_ID' con tu ID de chat. Puedes obtenerlo con el bot '@userinfobot'
BOT_TOKEN = '8237802820:AAHqF-v8UO1lUPLD4SL9x3AoK3QzYepN_Ok'
CHAT_ID = '552061604'
bot = Bot(token=BOT_TOKEN)

# --- Funciones de Cálculo ---
def calculate_metrics(monto_a_vender, tasa_elegida, tasa_mercado_max, tasa_bcv):
    # Factor de Pérdida con respecto a la tasa de mercado
    factor_perdida_mercado = 1 - (tasa_elegida / tasa_mercado_max)
    
    # Pérdida en USD (a tasa de mercado)
    perdida_usd_mercado = monto_a_vender * factor_perdida_mercado
    
    # Índice de Ahorro de Compra
    IAC = ((tasa_mercado_max / tasa_elegida) - 1) * 100
    
    # Factor de Pérdida con respecto a la tasa BCV (ahora en valor absoluto)
    factor_perdida_bcv = abs(1 - (tasa_elegida / tasa_bcv))
    
    return perdida_usd_mercado, factor_perdida_mercado, IAC, factor_perdida_bcv

# --- Lógica de Notificación Asíncrona ---
async def send_daily_report():
    try:
        tasa_bcv, tasa_mercado_cruda, tasa_mercado_redondeada = get_exchange_rates()
        if not all([tasa_bcv, tasa_mercado_cruda, tasa_mercado_redondeada]):
            message = "¡Alerta! No se pudo obtener la información de las tasas de cambio."
            await bot.send_message(chat_id=CHAT_ID, text=message)
            return

        # Cálculos para la diferencia y el error de redondeo
        diferencia_tasa = abs(tasa_mercado_cruda - tasa_mercado_redondeada)
        error_porcentual = (diferencia_tasa / tasa_mercado_redondeada) * 100

        monto_a_vender = 300
        tasa_elegida = 230.00
        tasa_mercado_max = tasa_mercado_redondeada

        perdida_usd, factor_perdida_mercado, IAC, factor_perdida_bcv = calculate_metrics(
            monto_a_vender, tasa_elegida, tasa_mercado_max, tasa_bcv
        )

        # Construir el mensaje con la información adicional
        message = (
            "📊 *Reporte de Tasas de Cambio*\n\n"
            f"BCV: {tasa_bcv:.4f} Bs/USD\n"
            f"Mercado (API): {tasa_mercado_cruda:.4f} Bs/USD\n"
            f"Mercado (Redondeada): {tasa_mercado_redondeada:.4f} Bs/USD\n\n"
            f"Diferencia de Redondeo: {diferencia_tasa:.4f} Bs/USD\n"
            f"Error de Muestreo de Redondeo: {error_porcentual:.4f}%\n\n"
            f"--- Análisis de Venta a 230 Bs/USD ---\n"
            f"Tasa Elegida: {tasa_elegida:.2f} Bs/USD\n"
            f"Pérdida ($Mercado) por Venta: ${perdida_usd:.2f}\n"
            f"Factor de Pérdida (vs Mercado): {factor_perdida_mercado:.4f}\n"
            f"Factor de Pérdida (vs BCV): {factor_perdida_bcv:.4f}\n"
            f"Índice de Ahorro para el Comprador: {IAC:.2f}%\n"
        )
        await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode=ParseMode.MARKDOWN)
        print("Reporte enviado con éxito.")
    except Exception as e:
        print(f"Error al enviar el reporte: {e}")

# --- Programación de las Tareas Asíncronas ---
async def main():
    print("El bot de notificaciones ha sido iniciado. Presiona Ctrl+C para detenerlo.")
    
    # Enviar un mensaje inmediatamente al ejecutar el script
    await send_daily_report() 

    # Programar las tareas recurrentes
    schedule.every().hour.do(lambda: asyncio.create_task(send_daily_report()))
    
    while True:
        schedule.run_pending()
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())