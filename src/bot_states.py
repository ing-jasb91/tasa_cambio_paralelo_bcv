# src/bot_states.py 

from enum import Enum, auto

class BotState(Enum):
    """
    Define los estados de conversación del bot para el ConversationHandler.
    Usar auto() evita conflictos de números y mejora la legibilidad.
    """
    # Menú Principal
    START = auto()
    
    # Análisis de Compra
    SELECT_CURRENCY_COMPRA = auto()
    AWAITING_INPUT_COMPRA = auto()
    
    # Costo de Oportunidad
    SELECT_CURRENCY_OPORTUNIDAD = auto()
    AWAITING_INPUT_OPORTUNIDAD = auto()
    
    # Conversión General
    SELECT_CURRENCY_CAMBIO = auto()
    AWAITING_INPUT_CAMBIO = auto()
    
    # 🚨 Alertas de Volatilidad (Flujo Completo) 🚨
    SELECT_ALERT_CURRENCY = auto()
    SELECT_ALERT_DIRECTION = auto() # <-- ¡ESTE FALTABA Y CAUSABA EL ERROR!
    AWAITING_INPUT_ALERT_PERCENTAGE = auto() # <-- Nombre ajustado para la lógica de input