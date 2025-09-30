# app/main.py
from app.notifier import start_bot 

def main():
    print("🤖 Iniciando Bot de Telegram...")
    start_bot() 

if __name__ == "__main__":
    main()