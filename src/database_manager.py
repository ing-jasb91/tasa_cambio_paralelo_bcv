# src/database_manager.py

import sqlite3
import os
import logging
from datetime import datetime, timedelta # <--- CORREGIDO: Añadido timedelta

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# La ubicación de la CARPETA 'data' (dos niveles arriba de src)
DB_FOLDER_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')

# La ubicación del archivo de la base de datos
DB_FILE_PATH = os.path.join(DB_FOLDER_PATH, 'exchange_rates.db')

def _connect_db():
    """Conecta o crea la base de datos SQLite."""
    try:
        # La conexión creará el archivo DB si no existe (asumiendo que la carpeta sí existe)
        conn = sqlite3.connect(DB_FILE_PATH)
        return conn
    except sqlite3.Error as e:
        logger.error(f"Error al conectar con SQLite: {e}")
        return None

def initialize_db():
    """Asegura que el directorio exista y crea la tabla exchange_rates si no existe."""
    
    # 1. Crear el directorio 'data' si no existe
    if not os.path.exists(DB_FOLDER_PATH):
        try:
            os.makedirs(DB_FOLDER_PATH)
            logger.info(f"Directorio de datos creado en: {DB_FOLDER_PATH}")
        except OSError as e:
            logger.error(f"Error al crear el directorio de datos: {e}")
            return # Fallo crítico, detenemos la inicialización
            
    # 2. Conectar y crear la tabla
    conn = _connect_db()
    if conn is None:
        return

    try:
        cursor = conn.cursor()
        
        # Definición de la tabla (incluyendo todas las divisas)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exchange_rates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL UNIQUE,
                date TEXT NOT NULL,
                USD_BCV REAL,
                EUR_BCV REAL,
                CNY_BCV REAL,
                TRY_BCV REAL,
                RUB_BCV REAL,
                USD_MERCADO_CRUDA REAL,
                EUR_USD_IMPLICITA REAL,
                EUR_USD_FOREX REAL
            )
        """)
        conn.commit()
        logger.info("Base de datos SQLite inicializada y tabla 'exchange_rates' verificada.")
    except sqlite3.Error as e:
        logger.error(f"Error al inicializar la base de datos: {e}")
    finally:
        if conn:
            conn.close()

def insert_rates(data):
    """Inserta una nueva fila de tasas en la tabla exchange_rates, forzando los tipos."""
    conn = _connect_db()
    if conn is None:
        return False # Indica fallo de conexión

    # Mapeo de columnas para asegurar el orden y la integridad
    columns = (
        'timestamp', 'date', 
        'USD_BCV', 'EUR_BCV', 
        'CNY_BCV', 'TRY_BCV', 'RUB_BCV', 
        'USD_MERCADO_CRUDA',
        'EUR_USD_IMPLICITA', 
        'EUR_USD_FOREX'
    )
    
    # Lógica de robustez: Asegura que las tasas sean float o None
    values = []
    rate_columns = [
        'USD_BCV', 'EUR_BCV', 'CNY_BCV', 'TRY_BCV', 'RUB_BCV', 
        'USD_MERCADO_CRUDA',
        'EUR_USD_IMPLICITA',
        'EUR_USD_FOREX'
    ]
    
    for col in columns:
        value = data.get(col)
        
        if col in rate_columns:
            # Intenta convertir a float. Si falla (ValueError) o es None, usa None.
            try:
                values.append(float(value) if value is not None else None)
            except (ValueError, TypeError):
                # Si el valor de la tasa no es un número válido, guarda None
                values.append(None)
        else:
            # Para 'timestamp' y 'date' (TEXT), usa el valor original
            values.append(value)
            
    values = tuple(values)

    placeholders = ', '.join(['?'] * len(columns))
    # NOTA: Asegúrate de usar el nombre de tabla correcto: 'exchange_rates'
    sql = f"INSERT INTO exchange_rates ({', '.join(columns)}) VALUES ({placeholders})"

    try:
        cursor = conn.cursor()
        cursor.execute(sql, values)
        conn.commit()
        logger.info(f"Tasas insertadas en SQLite: {data.get('date', 'Desconocida')}")
        return True
    except sqlite3.IntegrityError:
        # Fallo por repetición de clave primaria (timestamp)
        logger.warning(f"Error de integridad: Ya existe un registro para {data.get('timestamp', 'Desconocido')}.")
        return False
    except sqlite3.Error as e:
        logger.error(f"FALLO DE SQLITE: Error al insertar datos: {e}")
        return False
    finally:
        if conn:
            conn.close()
            
def get_latest_rates():
    """Obtiene el registro más reciente de tasas de la base de datos."""
    conn = _connect_db()
    if conn is None:
        return None

    try:
        cursor = conn.cursor()
        # Consulta SQL para seleccionar la fila con el ID más alto (el más reciente)
        cursor.execute("SELECT * FROM exchange_rates ORDER BY id DESC LIMIT 1")
        
        # Obtener los nombres de las columnas para crear un diccionario
        column_names = [description[0] for description in cursor.description]
        
        # Obtener el resultado
        latest_row = cursor.fetchone()
        
        if latest_row:
            # Combinar nombres de columnas y valores en un diccionario
            latest_rates = dict(zip(column_names, latest_row))
            return latest_rates
        else:
            return None
            
    except sqlite3.Error as e:
        logger.error(f"Error al obtener las últimas tasas de SQLite: {e}")
        return None
    finally:
        if conn:
            conn.close()

def get_24h_market_summary():
    """
    Calcula la tasa Máxima, Mínima y Promedio de USD_MERCADO_CRUDA
    para los registros dentro de las últimas 24 horas.
    """
    conn = _connect_db()
    if conn is None:
        return None

    try:
        cursor = conn.cursor()
        
        # 1. Definir la marca de tiempo de hace 24 horas
        time_24h_ago = datetime.now() - timedelta(hours=24)
        time_limit_iso = time_24h_ago.isoformat()
        
        # 2. Consulta SQL para la agregación
        cursor.execute("""
            SELECT 
                MAX(USD_MERCADO_CRUDA) AS Max_Tasa,
                MIN(USD_MERCADO_CRUDA) AS Min_Tasa,
                AVG(USD_MERCADO_CRUDA) AS Avg_Tasa,
                COUNT(id) AS Total_Registros
            FROM exchange_rates 
            WHERE timestamp >= ?
        """, (time_limit_iso,))
        
        summary_row = cursor.fetchone()

        if summary_row and summary_row[0] is not None:
            # Mapear la tupla de resultados a un diccionario
            return {
                'max': summary_row[0],
                'min': summary_row[1],
                'avg': summary_row[2],
                'count': summary_row[3],
                'period': 'Últimas 24h'
            }
        else:
            return None
            
    except sqlite3.Error as e:
        logger.error(f"Error al obtener el resumen de 24h: {e}")
        return None
    finally:
        if conn:
            conn.close()

# Inicializa la base de datos al importar el módulo (opcional, pero útil)
initialize_db()