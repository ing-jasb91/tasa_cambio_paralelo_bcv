# app/main.py

from app.calculator import DivisaCalculator
from app.menu import show_menu

def main():
    calculator = DivisaCalculator()
    print(calculator.get_exchange_rates_report())

    while True:
        opcion = show_menu()
        if opcion == 1:
            calculator.run_analysis_de_compra()
        elif opcion == 2:
            calculator.run_costo_de_oportunidad()
        elif opcion == 3:
            print("Saliendo de la aplicación.")
            break
        else:
            print("Opción no válida. Inténtalo de nuevo.")

if __name__ == "__main__":
    main()