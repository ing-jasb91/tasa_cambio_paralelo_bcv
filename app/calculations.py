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