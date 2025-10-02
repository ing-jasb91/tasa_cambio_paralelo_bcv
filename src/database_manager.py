# src/database_manager.py

import sqlite3
import os
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# La ubicación de la CARPETA 'data' (dos niveles arriba de src)
DB_FOLDER_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')

# La ubicación del archivo de la base de datos
DB_FILE_PATH = os.path.join(DB_FOLDER_PATH, 'exchange_rates.db')

def _connect_db():
    """Conecta o crea la base de datos SQLite."""
    try:
        conn = sqlite3.connect(DB_FILE_PATH)
        # Habilitar el acceso por nombre de columna (útil para el diccionario)
        conn.row_factory = sqlite3.Row 
        return conn
    except sqlite3.Error as e:
        logger.error(f"Error al conectar con SQLite: {e}")
        return None

def initialize_db():
    """Asegura el directorio y crea las dos tablas: BCV_RATES y MARKET_RATES."""
    
    # 1. Crear el directorio 'data' si no existe
    if not os.path.exists(DB_FOLDER_PATH):
        try:
            os.makedirs(DB_FOLDER_PATH)
            logger.info(f"Directorio de datos creado en: {DB_FOLDER_PATH}")
        except OSError as e:
            logger.error(f"Error al crear el directorio de datos: {e}")
            return # Fallo crítico, detenemos la inicialización
            
    # 2. Conectar y crear las tablas
    conn = _connect_db()
    if conn is None:
        return

    try:
        cursor = conn.cursor()
        
        # 🚨 NUEVA TABLA 1: TASAS OFICIALES BCV (datos estables)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS BCV_RATES (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE, -- Unique: solo una actualización por día
                timestamp_saved TEXT NOT NULL,
                USD_BCV REAL,
                EUR_BCV REAL,
                CNY_BCV REAL,
                TRY_BCV REAL,
                RUB_BCV REAL
            )
        """)
        
        # 🚨 NUEVA TABLA 2: TASAS DE MERCADO (datos volátiles)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS MARKET_RATES (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL UNIQUE, -- Único y más detallado
                USD_MERCADO_CRUDA REAL,
                EUR_USD_FOREX REAL
            )
        """)
        
        conn.commit()
        logger.info("Base de datos SQLite inicializada. Tablas BCV_RATES y MARKET_RATES creadas/verificadas.")
    except sqlite3.Error as e:
        logger.error(f"Error al inicializar la base de datos: {e}")
    finally:
        if conn:
            conn.close()

# --- FUNCIONES DE GUARDADO ESPECÍFICAS ---

def save_bcv_rates(data):
    """Inserta las tasas BCV. Debe ser llamado solo si el 'date' ha cambiado."""
    conn = _connect_db()
    if conn is None:
        return False

    columns = ('date', 'timestamp_saved', 'USD_BCV', 'EUR_BCV', 'CNY_BCV', 'TRY_BCV', 'RUB_BCV')
    placeholders = ', '.join(['?'] * len(columns))
    sql = f"INSERT INTO BCV_RATES ({', '.join(columns)}) VALUES ({placeholders})"
    
    # Prepara los valores, asegurando que el timestamp_saved sea el de ahora
    values = (
        data['date'], 
        datetime.now().isoformat(),
        data['USD_BCV'], data['EUR_BCV'], 
        data['CNY_BCV'], data['TRY_BCV'], data['RUB_BCV']
    )

    try:
        cursor = conn.cursor()
        cursor.execute(sql, values)
        conn.commit()
        logger.info(f"Tasas BCV guardadas para la fecha: {data['date']}")
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"Error de integridad: Ya existe un registro BCV para la fecha {data['date']}.")
        return False
    except sqlite3.Error as e:
        logger.error(f"FALLO DE SQLITE: Error al insertar tasas BCV: {e}")
        return False
    finally:
        if conn:
            conn.close()

def save_market_rates(data):
    """Inserta las tasas de mercado y forex (volátiles)."""
    conn = _connect_db()
    if conn is None:
        return False
        
    columns = ('timestamp', 'USD_MERCADO_CRUDA', 'EUR_USD_FOREX')
    placeholders = ', '.join(['?'] * len(columns))
    sql = f"INSERT INTO MARKET_RATES ({', '.join(columns)}) VALUES ({placeholders})"

    values = (
        data['timestamp'], 
        data['USD_MERCADO_CRUDA'], 
        data['EUR_USD_FOREX']
    )

    try:
        cursor = conn.cursor()
        cursor.execute(sql, values)
        conn.commit()
        logger.info(f"Tasa de Mercado guardada: {data['USD_MERCADO_CRUDA']:.4f}")
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"Error de integridad: Ya existe un registro de mercado para el timestamp {data['timestamp']}.")
        return False
    except sqlite3.Error as e:
        logger.error(f"FALLO DE SQLITE: Error al insertar tasas de Mercado: {e}")
        return False
    finally:
        if conn:
            conn.close()

# Función antigua renombrada y modificada para el nuevo modelo
def insert_rates(data):
    """
    Función de utilidad (manteniendo la interfaz antigua): 
    Debe ser llamada por data_fetcher para guardar ambos tipos de tasas.
    Nota: En el nuevo modelo, data_fetcher.py debería llamar a save_bcv_rates y save_market_rates por separado.
    """
    logger.warning("ATENCIÓN: insert_rates es obsoleto. Usar save_bcv_rates y save_market_rates.")
    # Intenta guardar el mercado (más frecuente)
    market_success = save_market_rates(data)
    # Intenta guardar BCV (menos frecuente, se confía en la lógica de data_fetcher para la unicidad de 'date')
    bcv_success = save_bcv_rates(data) 
    return market_success or bcv_success

# --- FUNCIÓN DE LECTURA COMBINADA ---

def get_latest_rates():
    """Obtiene el último registro de BCV_RATES y el último de MARKET_RATES y los combina."""
    conn = _connect_db()
    if conn is None:
        return None

    try:
        # 1. Obtener la última fila de BCV
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM BCV_RATES ORDER BY id DESC LIMIT 1")
        bcv_row = cursor.fetchone()
        
        # 2. Obtener la última fila de Mercado
        cursor.execute("SELECT * FROM MARKET_RATES ORDER BY id DESC LIMIT 1")
        market_row = cursor.fetchone()

        latest_rates = {}
        
        if bcv_row:
            # Combina columnas y valores de BCV
            latest_rates.update(dict(bcv_row))
        
        if market_row:
            # Combina columnas y valores de Mercado, sobrescribiendo si hay colisión (no debería)
            latest_rates.update(dict(market_row))
        
        if not latest_rates:
            return None

        # Arreglo de tipos: Convertir los valores a float si son números
        for key, value in latest_rates.items():
            if isinstance(value, (int, float)):
                latest_rates[key] = float(value)
        
        return latest_rates
            
    except sqlite3.Error as e:
        logger.error(f"Error al obtener las últimas tasas combinadas de SQLite: {e}")
        return None
    finally:
        if conn:
            conn.close()

# --- FUNCIÓN DE RESUMEN DE 24H (ADAPTADA) ---

def get_24h_market_summary():
    """
    Calcula la tasa Máxima, Mínima y Promedio de USD_MERCADO_CRUDA
    para los registros de MARKET_RATES dentro de las últimas 24 horas.
    """
    conn = _connect_db()
    if conn is None:
        return None

    try:
        cursor = conn.cursor()
        
        # 1. Definir la marca de tiempo de hace 24 horas
        time_24h_ago = datetime.now() - timedelta(hours=24)
        time_limit_iso = time_24h_ago.isoformat()
        
        # 2. Consulta SQL adaptada a la nueva tabla MARKET_RATES
        cursor.execute("""
            SELECT 
                MAX(USD_MERCADO_CRUDA) AS Max_Tasa,
                MIN(USD_MERCADO_CRUDA) AS Min_Tasa,
                AVG(USD_MERCADO_CRUDA) AS Avg_Tasa,
                COUNT(id) AS Total_Registros
            FROM MARKET_RATES 
            WHERE timestamp >= ?
        """, (time_limit_iso,))
        
        summary_row = cursor.fetchone()

        if summary_row and summary_row['Max_Tasa'] is not None:
            # Mapear la tupla de resultados a un diccionario (funciona gracias a row_factory)
            return {
                'max': summary_row['Max_Tasa'],
                'min': summary_row['Min_Tasa'],
                'avg': summary_row['Avg_Tasa'],
                'count': summary_row['Total_Registros'],
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

# Inicializa la base de datos al importar el módulo
initialize_db()