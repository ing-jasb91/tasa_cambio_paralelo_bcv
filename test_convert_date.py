from datetime import datetime
import re
import locale

def _convert_date_format_strptime(date_string):
    """
    Convierte la fecha (ej: 'Martes, 07 Octubre 2025') a 'DD/MM/YYYY'.
    - Configura el locale a español para reconocer días y meses.
    - Limpia la cadena de espacios múltiples o duros.
    """
    
    # 1. Configurar el locale a español (necesario para reconocer "Octubre")
    try:
        # Intentos para encontrar un locale español de Venezuela/Latinoamérica/España
        # Se prueban varias convenciones comunes:
        locales_espanol = ['es_VE.UTF-8', 'es_VE', 'es_ES.UTF-8', 'es_ES', 'Spanish', 'es']
        
        locale_encontrado = False
        for loc in locales_espanol:
            try:
                locale.setlocale(locale.LC_TIME, loc)
                locale_encontrado = True
                # print(f"Locale configurado con éxito: {loc}") # Opcional: para debug
                break
            except locale.Error:
                continue # Intenta el siguiente locale
        
        if not locale_encontrado:
            print("Error: No se pudo configurar un locale español válido en el sistema.")
            return None

    except Exception as e:
        print(f"Error al intentar configurar el locale: {e}")
        return None

# ---

    try:
        # 2. Limpieza de la cadena
        # Reemplaza cualquier secuencia de espacios (\s+ incluye espacios duros, tabs, etc.) 
        # por un único espacio ASCII (' '). Esto arregla tu problema de "  ".
        string_limpio = re.sub(r'\s+', ' ', date_string).strip()
        
        # El string limpio debe ser: "Martes, 07 Octubre 2025"
        
        # 3. Parseo de la fecha (Patrón de formato estricto)
        # %A: Día de la semana (ej: Martes)
        # %d: Día del mes (ej: 07)
        # %B: Mes (ej: Octubre)
        # %Y: Año (ej: 2025)
        
        fecha_obj = datetime.strptime(string_limpio, "%A, %d %B %Y")
        
        # 4. Formateo al formato final DD/MM/AAAA
        return fecha_obj.strftime("%d/%m/%Y")
        
    except ValueError as e:
        # Este error puede ser porque el patrón de fecha no coincide (p. ej., si la coma no está)
        print(f"Error al parsear la fecha con strptime. Verifica el patrón de formato '%A, %d %B %Y': {e}")
        return None
    except Exception as e:
        print(f"Error inesperado: {e}")
        return None

# --- Prueba con tu string ---
test_string = "Martes, 07 Octubre    2025" 
test_strptime = _convert_date_format_strptime(test_string)

print(f"Cadena original: '{test_string}'")
print(f"Resultado: {test_strptime}")