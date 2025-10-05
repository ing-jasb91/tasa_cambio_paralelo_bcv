# app/main.py
from app.notifier import start_bot
from src.database_manager import initialize_db

def main():
    print("🤖 Iniciando Bot de Telegram...")
    initialize_db()  # Asegurarse de que la DB y tablas existen
    start_bot() 


if __name__ == "__main__":
    main()