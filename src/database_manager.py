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
        conn.row_factory = sqlite3.Row 
        return conn
    except sqlite3.Error as e:
        logger.error(f"Error al conectar con SQLite: {e}")
        return None

def initialize_db():
    """Asegura el directorio y crea todas las tablas necesarias."""
    
    # 1. Crear el directorio 'data' si no existe
    if not os.path.exists(DB_FOLDER_PATH):
        try:
            os.makedirs(DB_FOLDER_PATH)
            logger.info(f"Directorio de datos creado en: {DB_FOLDER_PATH}")
        except OSError as e:
            logger.error(f"Error al crear el directorio de datos: {e}")
            return

    conn = _connect_db()
    if conn is None:
        return

    try:
        cursor = conn.cursor()
        
        # Tabla 1: BCV_RATES (Tasas BCV y otras)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS BCV_RATES (
                date TEXT PRIMARY KEY,
                USD_BCV REAL,
                EUR_BCV REAL,
                CNY_BCV REAL,
                TRY_BCV REAL,
                RUB_BCV REAL
            )
        """)

        # Tabla 2: MARKET_RATES (Tasas de Mercado y FOREX)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS MARKET_RATES (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL UNIQUE,
                USD_MERCADO_CRUDA REAL NOT NULL,
                EUR_USD_FOREX REAL,
                UNIQUE (timestamp)
            )
        """)
        
        # 🚨 NUEVA TABLA PARA ALERTAS 🚨
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS USER_ALERTS (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                currency TEXT NOT NULL,       -- Ej: USD
                direction TEXT NOT NULL,      -- Ej: UP o DOWN
                threshold_percent REAL NOT NULL, -- Ej: 1.0 para 1%
                last_checked_rate REAL,       -- Última tasa que ACTIVÓ la alerta
                is_active INTEGER NOT NULL,   -- 1 (Activa) o 0 (Inactiva)
                -- Aseguramos que solo haya una alerta UP y una DOWN por chat_id y currency
                UNIQUE (chat_id, currency, direction)
            )
        """)

        conn.commit()
        logger.info("Estructura de la base de datos asegurada (incluyendo USER_ALERTS).")

    except sqlite3.Error as e:
        logger.error(f"Error al inicializar las tablas de la DB: {e}")
    finally:
        if conn:
            conn.close()

# ----------------------------------------------------------------------
# --- FUNCIONES DE GUARDADO DE TASAS (Mantener las existentes) ---
# ----------------------------------------------------------------------

def save_bcv_rates(data: dict) -> bool:
    """Guarda las tasas del BCV en la tabla BCV_RATES."""
    conn = _connect_db()
    if conn is None:
        return False
    now_iso = datetime.now().isoformat()
    try:
        cursor = conn.cursor()
        # Se usa INSERT OR IGNORE para evitar errores si ya existe la fecha (clave primaria)
        # cursor.execute("""
        #     INSERT OR IGNORE INTO BCV_RATES (date, USD_BCV, EUR_BCV, CNY_BCV, TRY_BCV, RUB_BCV)
        #     VALUES (?, ?, ?, ?, ?, ?)
        # """, (
        cursor.execute("""
            INSERT OR IGNORE INTO BCV_RATES (date, timestamp_saved, USD_BCV, EUR_BCV, CNY_BCV, TRY_BCV, RUB_BCV)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            data['date'], now_iso, data['USD_BCV'], data['EUR_BCV'], 
            data.get('CNY_BCV', 0.0), data.get('TRY_BCV', 0.0), data.get('RUB_BCV', 0.0)
        ))
        conn.commit()
        return cursor.rowcount > 0 # Retorna True si se insertó algo
    except sqlite3.Error as e:
        logger.error(f"Error al guardar tasas BCV: {e}")
        return False
    finally:
        if conn:
            conn.close()

def save_market_rates(data: dict) -> bool:
    """Guarda la tasa de mercado y FOREX en la tabla MARKET_RATES."""
    conn = _connect_db()
    if conn is None:
        return False

    try:
        cursor = conn.cursor()
        # Se usa INSERT OR IGNORE para evitar errores si ya existe el timestamp (clave única)
        cursor.execute("""
            INSERT OR IGNORE INTO MARKET_RATES (timestamp, USD_MERCADO_CRUDA, EUR_USD_FOREX)
            VALUES (?, ?, ?)
        """, (data['timestamp'], data['USD_MERCADO_CRUDA'], data['EUR_USD_FOREX']))
        
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error(f"Error al guardar tasas de Mercado: {e}")
        return False
    finally:
        if conn:
            conn.close()

# ----------------------------------------------------------------------
# --- FUNCIONES DE CONSULTA (Mantener las existentes) ---
# ----------------------------------------------------------------------

def get_latest_rates() -> dict | None:
    """
    Combina y recupera el último registro de BCV y el más reciente de Mercado.
    Esto requiere consultar ambas tablas para obtener un resumen completo.
    """
    conn = _connect_db()
    if conn is None:
        return None

    result = {}
    try:
        cursor = conn.cursor()

        # 1. Obtener el último registro de BCV_RATES
        cursor.execute("""
            SELECT * FROM BCV_RATES
            ORDER BY date DESC
            LIMIT 1
        """)
        bcv_data = cursor.fetchone()
        
        if bcv_data:
            # Añadir todos los campos de BCV_RATES al resultado
            result.update(dict(bcv_data))

        # 2. Obtener el registro más reciente de MARKET_RATES
        cursor.execute("""
            SELECT * FROM MARKET_RATES
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        market_data = cursor.fetchone()

        if market_data:
            # Añadir los campos de MARKET_RATES al resultado
            result['timestamp'] = market_data['timestamp']
            result['USD_MERCADO_CRUDA'] = market_data['USD_MERCADO_CRUDA']
            result['EUR_USD_FOREX'] = market_data['EUR_USD_FOREX']
            
        return result if result else None

    except sqlite3.Error as e:
        logger.error(f"Error al obtener las últimas tasas: {e}")
        return None
    finally:
        if conn:
            conn.close()

def get_24h_market_summary() -> dict | None:
    """Calcula el máximo, mínimo, promedio y conteo de la tasa de Mercado en las últimas 24h."""
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
                MAX(USD_MERCADO_CRUDA) AS max,
                MIN(USD_MERCADO_CRUDA) AS min,
                AVG(USD_MERCADO_CRUDA) AS avg,
                COUNT(id) AS count
            FROM MARKET_RATES 
            WHERE timestamp >= ?
        """, (time_limit_iso,))
        
        summary_row = cursor.fetchone()


        # if summary_row and summary_row['max'] is not None:
        #     # Mapear la tupla de resultados a un diccionario (funciona gracias a row_factory)
        #     return dict(summary_row)
        summary = dict(summary_row) if summary_row else None

        # Verificamos si la fila existe Y si el conteo es mayor a 1 (para tener min/max/avg válidos)
        # O si es mayor a 0 para que al menos se muestre el gráfico (que usa otra consulta)
        if summary and summary.get('count', 0) > 1:
            return summary
        return None


    except sqlite3.Error as e:
        logger.error(f"Error al obtener el resumen de 24h: {e}")
        return None
    finally:
        if conn:
            conn.close()

# ----------------------------------------------------------------------
# --- NUEVAS FUNCIONES PARA LA GESTIÓN DE ALERTAS 🚨 ---
# ----------------------------------------------------------------------

def save_user_alert(chat_id: str, currency: str, direction: str, threshold_percent: float) -> bool:
    """Guarda o actualiza la configuración de una alerta de usuario."""
    conn = _connect_db()
    if conn is None:
        return False
    
    try:
        cursor = conn.cursor()
        # UPSERT (INSERT OR REPLACE)
        cursor.execute("""
            INSERT INTO USER_ALERTS 
            (chat_id, currency, direction, threshold_percent, last_checked_rate, is_active)
            VALUES (?, ?, ?, ?, NULL, 1)
            ON CONFLICT(chat_id, currency, direction) DO UPDATE SET
                threshold_percent = excluded.threshold_percent,
                last_checked_rate = NULL,  -- Reiniciar la tasa de chequeo al modificar
                is_active = 1              -- Asegurar que esté activa
        """, (chat_id, currency, direction, threshold_percent))
        
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Error al guardar la alerta de usuario: {e}")
        return False
    finally:
        if conn:
            conn.close()


def get_active_alerts():
    """Recupera todas las alertas activas (is_active = 1) de la base de datos."""
    conn = _connect_db()
    if conn is None:
        return []

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM USER_ALERTS WHERE is_active = 1")
        # Convierte los objetos Row a una lista de diccionarios para fácil uso
        alerts = [dict(row) for row in cursor.fetchall()] 
        return alerts
    except sqlite3.Error as e:
        logger.error(f"Error al obtener alertas activas: {e}")
        return []
    finally:
        if conn:
            conn.close()


def update_alert_rate_and_status(alert_id: int, new_rate: float, deactivate: bool) -> bool:
    """Actualiza la última tasa chequeada y desactiva la alerta si es necesario."""
    conn = _connect_db()
    if conn is None:
        return False

    try:
        cursor = conn.cursor()
        status = 0 if deactivate else 1
        
        cursor.execute("""
            UPDATE USER_ALERTS SET
                last_checked_rate = ?,
                is_active = ?
            WHERE id = ?
        """, (new_rate, status, alert_id))
        
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Error al actualizar estado de la alerta {alert_id}: {e}")
        return False
    finally:
        if conn:
            conn.close()


# src/database_manager.py (Añadir la nueva función)

def get_historical_rates(hours: int = 24) -> list[float]:
    """
    Consulta la base de datos para obtener una lista simple de las tasas de 
    USD_MERCADO_CRUDA registradas en las últimas 'hours' horas.
    
    Args:
        hours (int): Número de horas a consultar.
        
    Returns:
        list[float]: Lista de los valores de la tasa de mercado.
    """
    conn = _connect_db()
    if conn is None:
        return []

    try:
        cursor = conn.cursor()
        
        # 1. Definir la marca de tiempo límite (en formato ISO para SQLite)
        time_limit = datetime.now() - timedelta(hours=hours)
        time_limit_iso = time_limit.isoformat()
        
        # 2. Consulta SQL: Seleccionar solo la tasa
        query = f"""
            SELECT USD_MERCADO_CRUDA
            FROM MARKET_RATES 
            WHERE timestamp >= ? 
            ORDER BY timestamp ASC
        """
        cursor.execute(query, (time_limit_iso,))
        
        # 3. Extraer solo los valores de la tasa y devolverlos como una lista de floats
        rates = [row['USD_MERCADO_CRUDA'] for row in cursor.fetchall()]
        
        # Filtrar posibles valores None o cero
        return [rate for rate in rates if rate is not None and rate > 0]
        
    except sqlite3.Error as e:
        logger.error(f"Error al obtener tasas históricas para el análisis de riesgo: {e}")
        return []
    finally:
        if conn:
            conn.close()
