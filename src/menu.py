# # app/menu.py

# def show_menu():
#     """Muestra el menú de opciones y devuelve la selección del usuario."""
#     print("====================================")
#     print("      Calculadora de Divisas")
#     print("====================================")
#     print("Selecciona una opción:")
#     print("1. Análisis de Compra")
#     print("2. Costo de Oportunidad por Negociación")
#     print("3. Salir")
#     print("------------------------------------")
    
#     try:
#         opcion = int(input("Ingresa el número de tu elección: "))
#         return opcion
#     except ValueError:
#         print("Opción no válida. Por favor, ingresa un número.")
#         return None

# app/menu.py

def show_menu():
    print("\n" + "="*30)
    print("      Menú Principal")
    print("="*30)
    print("1. Análisis de Compra")
    print("2. Costo de Oportunidad")
    print("3. Salir")
    print("="*30)
    try:
        opcion = int(input("Selecciona una opción: "))
        return opcion
    except ValueError:
        return 0