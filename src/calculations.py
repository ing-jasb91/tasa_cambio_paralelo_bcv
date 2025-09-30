# app/calculations.py

def calculate_selling_factor(tasa_bcv, tasa_mercado):
    """Calcula el factor para saber cuántos dólares vender."""
    return tasa_bcv / tasa_mercado

def calculate_buying_power(tasa_bcv, tasa_mercado):
    """Calcula el factor para saber el poder de compra."""
    return tasa_mercado / tasa_bcv

def check_purchase_scenarios(dolares_disponibles, costo_producto, tasa_bcv, tasas_mercado):
    """
    Evalúa si la cantidad de dólares es suficiente para la compra
    en diferentes escenarios de tasas del mercado.
    """
    resultados = []
    for tasa_mercado in tasas_mercado:
        if tasa_mercado > 0:
            poder_de_compra = dolares_disponibles * (tasa_mercado / tasa_bcv)
            es_suficiente = poder_de_compra >= costo_producto
            diferencia = poder_de_compra - costo_producto
            
            resultados.append({
                'tasa': tasa_mercado,
                'suficiente': es_suficiente,
                'diferencia': diferencia
            })
    return resultados


def calculate_opportunity_cost(dolares_a_vender, tasa_mercado_max, tasas_a_evaluar):
    """
    Calcula el costo de oportunidad y la pérdida por aceptar una tasa inferior.
    """
    resultados_costo = []

    # Calcular el valor máximo en bolívares si se vende a la tasa más alta
    valor_max_bolivares = dolares_a_vender * tasa_mercado_max

    for tasa_actual in tasas_a_evaluar:
        # Calcular el valor actual en bolívares
        valor_actual_bolivares = dolares_a_vender * tasa_actual

        # Calcular la pérdida en bolívares
        perdida_bolivares = valor_max_bolivares - valor_actual_bolivares

        # Las tasas para la pérdida en USD se obtienen de la API, aquí usamos una fija de ejemplo para el cálculo
        # Deberías pasar la tasa BCV a esta función, pero para simplificar, usaremos una fija
        tasa_bcv_fija = 160.4479  # Ejemplo: Usar un valor fijo de la API
        
        # Calcular la pérdida en USD (a tasa BCV y a tasa de mercado)
        perdida_usd_bcv = perdida_bolivares / tasa_bcv_fija
        perdida_usd_mercado = perdida_bolivares / tasa_mercado_max

        # Calcular el factor de pérdida (como un "spread")
        factor_perdida = 1 - (tasa_actual / tasa_mercado_max)

        resultados_costo.append({
            'tasa': tasa_actual,
            'perdida_bolivares': perdida_bolivares,
            'perdida_usd_bcv': perdida_usd_bcv,
            'perdida_usd_mercado': perdida_usd_mercado,
            'factor_perdida': factor_perdida
        })

    return resultados_costo