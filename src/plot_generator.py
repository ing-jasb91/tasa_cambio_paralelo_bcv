# src/plot_generator.py

import logging
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import os
import io # <<< AÑADE ESTO

# Importamos la ruta de la base de datos desde database_manager
from src.database_manager import DB_FILE_PATH

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def _get_historical_data(hours=48):
    """
    Consulta la base de datos para obtener los datos históricos del mercado 
    (USD_MERCADO_CRUDA) de las últimas 'hours' horas.

    Args:
        hours (int): Número de horas a consultar hacia atrás.

    Returns:
        pd.DataFrame: DataFrame de Pandas con columnas 'timestamp' y 'rate'.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE_PATH)
        
        # 1. Definir la marca de tiempo límite
        time_limit = datetime.now() - timedelta(hours=hours)
        time_limit_iso = time_limit.isoformat()
        
        # 2. Consulta SQL: Selecciona la tasa del mercado y el timestamp
        query = f"""
            SELECT 
                timestamp, 
                USD_MERCADO_CRUDA AS rate 
            FROM MARKET_RATES 
            WHERE timestamp >= ? 
            ORDER BY timestamp ASC
        """
        
        # Usamos read_sql_query de Pandas para obtener un DataFrame directamente
        df = pd.read_sql_query(query, conn, params=(time_limit_iso,))
        
        if df.empty:
            logger.warning("No se encontraron datos históricos para generar el gráfico.")
            return None
        
        # 3. Conversión de tipos y limpieza
        # Convertir 'timestamp' a objetos datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Limpiar y convertir 'rate' a float, eliminando filas con valores nulos (NaN)
        df['rate'] = pd.to_numeric(df['rate'], errors='coerce')
        df = df.dropna(subset=['rate'])
        
        return df

    except sqlite3.Error as e:
        logger.error(f"Error de SQLite al obtener datos históricos: {e}")
        return None
    except Exception as e:
        logger.error(f"Error inesperado al obtener datos históricos: {e}")
        return None
    finally:
        if conn:
            conn.close()


def generate_market_plot(output_filename="market_rate_plot.png", hours=48):
    """
    Genera un gráfico de línea de la tasa de cambio del mercado USD_MERCADO_CRUDA
    a lo largo del tiempo y lo guarda como un archivo PNG.

    Args:
        output_filename (str): Nombre del archivo donde se guardará el gráfico.
        hours (int): Rango de horas a graficar (por defecto 48h).

    Returns:
        str or None: La ruta completa del archivo PNG generado si es exitoso, 
                     o None si falla.
    """
    df = _get_historical_data(hours)
    
    if df is None or df.empty:
        return None

    # --- Configuración y Generación del Gráfico ---
    try:
        # Configurar estilo para mejor apariencia
        plt.style.use('seaborn-v0_8-whitegrid')
        
        # Crear la figura y el eje
        fig, ax = plt.subplots(figsize=(10, 6))

        # 1. Dibujar la línea de la tasa de mercado
        ax.plot(df['timestamp'], df['rate'], 
                label='Tasa P2P (USD/VES)', 
                color='#1f77b4', # Un azul vibrante
                linewidth=2.5, 
                marker='o', 
                markersize=4)

        # 2. Resaltar la tasa actual
        current_rate = df['rate'].iloc[-1]
        ax.scatter(df['timestamp'].iloc[-1], current_rate, 
                   color='red', 
                   s=100, 
                   zorder=5, # Asegura que el punto esté encima de la línea
                   label=f'Actual: {current_rate:.2f} VES')
        
        # 3. Calcular y dibujar la línea de promedio (opcional)
        avg_rate = df['rate'].mean()
        ax.axhline(avg_rate, 
                   color='orange', 
                   linestyle='--', 
                   linewidth=1, 
                   alpha=0.6,
                   label=f'Promedio {hours}h: {avg_rate:.2f} VES')

        # --- Formato del Eje X (Tiempo) ---
        
        # Formateador basado en el rango de tiempo
        if hours <= 24:
            # Mostrar cada hora y el formato H:M
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
        else:
            # Mostrar día y hora para rangos más grandes
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m %Hh'))
            # Rotar las etiquetas para que no se superpongan
            fig.autofmt_xdate(rotation=45) 
            # Intentar solo un marcador de tiempo por cada 8 horas (ajustable)
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=8)) 

        # --- Formato del Eje Y (Tasa) ---
        
        # Añadir un buffer del 5% al eje Y para que la línea no toque el borde
        rate_min = df['rate'].min() * 0.99 
        rate_max = df['rate'].max() * 1.01 
        ax.set_ylim([rate_min, rate_max])
        ax.set_ylabel('Tasa de Cambio (VES)', fontsize=12)
        
        # --- Título y Leyenda ---
        
        ax.set_title(f'Volatilidad USD Mercado (Últimas {hours} Horas)', 
                     fontsize=14, 
                     fontweight='bold')
        ax.legend(loc='best', fontsize=10)
        ax.grid(True, linestyle='--', alpha=0.7)
        
        # --- Guardar el Gráfico ---
        
        # # Aseguramos que la carpeta 'data' exista para guardar el archivo
        # plot_folder = os.path.dirname(DB_FILE_PATH)
        # os.makedirs(plot_folder, exist_ok=True)
        
        # # Ruta completa del archivo
        # full_path = os.path.join(plot_folder, output_filename)
        
        # # Guardar la figura con alta resolución y ajustando el layout
        # plt.tight_layout()
        # fig.savefig(full_path, dpi=fig.dpi * 1.5) # Aumentar DPI para Telegram
        
        # # Cerrar la figura para liberar memoria
        # plt.close(fig)
        
        # logger.info(f"Gráfico de volatilidad guardado exitosamente en: {full_path}")
        # return full_path



        # Reemplaza el bloque anterior con este:

        # --- Guardar el Gráfico en Memoria (BytesIO) ---
        buffer = io.BytesIO()

        plt.tight_layout()
        # 🚨 CRÍTICO: Guarda la figura en el buffer, NO en el archivo
        fig.savefig(buffer, format='png', dpi=fig.dpi * 1.5) 

        # Cerrar la figura para liberar memoria
        plt.close(fig)

        # Retroceder al inicio del buffer para que Telegram pueda leerlo
        buffer.seek(0)

        logger.info(f"Gráfico de mercado generado exitosamente en memoria (BytesIO).")

        # Devolvemos el buffer (objeto en memoria), NO la ruta de archivo
        return buffer


    except Exception as e:
        logger.error(f"Error al generar el gráfico de Matplotlib: {e}")
        return None

# Ejemplo de uso para prueba local (opcional)
if __name__ == '__main__':
    # Esto asume que tienes datos en exchange_rates.db
    print("--- Generando Gráfico de Prueba (48h) ---")
    plot_path = generate_market_plot(hours=48)
    if plot_path:
        print(f"✅ Éxito. Revisa el archivo: {plot_path}")
    else:
        print("❌ Fallo. Asegúrate de tener datos suficientes en la DB (MARKET_RATES).")
