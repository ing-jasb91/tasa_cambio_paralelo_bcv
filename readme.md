🇻🇪 Exchange Rate Bot - Monitor de Tasas BCV & Mercado P2P
Este proyecto es un bot de Telegram diseñado para monitorear y reportar las tasas de cambio oficiales del Banco Central de Venezuela (BCV) y la tasa de Mercado P2P (obtenida de Binance), calculando métricas de disparidad y volatilidad clave para la toma de decisiones financieras.

El bot proporciona:

Reportes Horarios automáticos.

Herramientas interactivas (/start) para análisis de compra, costo de oportunidad y conversión de divisas.

Registro histórico de tasas en una base de datos SQLite.

🚀 Inicio Rápido
1. Requisitos
Asegúrate de tener Python 3.8+ y pip instalados.

2. Clonación y Entorno Virtual
Clona el repositorio y configura tu entorno virtual:

# 1. Clonar el repositorio
git clone <URL_DE_TU_REPOSITORIO>
cd exchange-rate-bot # Ajusta al nombre de tu carpeta

# 2. Crear y activar el entorno virtual
python3 -m venv venv
source venv/bin/activate  # En Linux/macOS
# .\venv\Scripts\activate   # En Windows

3. Instalación de Dependencias
Instala todas las librerías necesarias:

pip install -r requirements.txt

4. Configuración de Variables de Entorno (Seguridad)
Para proteger tus credenciales, el bot utiliza variables de entorno cargadas desde un archivo .env.

Crea un nuevo archivo llamado .env en la raíz del proyecto.

Copia el contenido de .env.example en el nuevo archivo .env.

Reemplaza los placeholders con tus credenciales reales:

Variable

Descripción

Fuente

BOT_TOKEN

Token de tu bot de Telegram.

@BotFather

CHAT_ID

ID numérico del chat (o grupo) donde se enviarán los reportes automáticos.

@userinfobot

ALPHA_VANTAGE_API_KEY

Clave para la tasa EUR/USD del mercado (Forex).

Alpha Vantage

5. Ejecución
Ejecuta el bot desde el archivo principal:

python app/main.py

Al iniciar, el bot realizará una precarga de datos y enviará el primer reporte automático al CHAT_ID configurado en 1 segundo.

📂 Estructura del Proyecto
Directorio/Archivo

Descripción

Notas Clave

app/main.py

Punto de entrada principal para iniciar la aplicación.



app/notifier.py

Contiene toda la lógica del bot de Telegram (handlers, comandos, job queue).

Define el reporte horario y las herramientas interactivas.

src/

Módulo de núcleo (lógica de negocio y manejo de datos).



src/data_fetcher.py

Web Scraping al BCV, conexión a Forex y la lógica de guardado condicional.



src/market_fetcher.py

Conexión y cálculo de la tasa promedio ponderada del mercado P2P (Binance).



src/database_manager.py

Maneja la DB SQLite y define las tablas BCV_RATES y MARKET_RATES.



data/

Directorio que contiene el archivo de base de datos exchange_rates.db.

¡Ignorado por Git!

.env.example

Plantilla de configuración de variables de entorno (seguro para GitHub).



⚙️ Lógica de Actualización de Datos y Persistencia
El sistema de actualización sigue un modelo de doble tabla con lógica condicional:

Tabla

Frecuencia de Verificación

Condición de Guardado

BCV_RATES

Cada 10 minutos

La fecha de valor del BCV ha cambiado (generalmente una vez al día).

MARKET_RATES

Cada 10 minutos (JobQueue)

La tasa P2P ha cambiado en más de un 0.1% (volatilidad) O si se invoca con force_save=True (para el reporte horario).

Este diseño asegura que el historial se mantenga limpio y que el reporte por hora siempre contenga la tasa P2P más fresca, anulando el chequeo de volatilidad si es necesario.

💬 Uso Interactivo
Envía el comando /start a tu bot para acceder a las herramientas de análisis:

📊 Análisis de Compra: Evalúa si tu capital es suficiente para una compra específica, considerando diversas tasas de mercado.

📈 Costo de Oportunidad: Mide la pérdida potencial al vender tus divisas por debajo del precio de mercado.

💱 Cambio de Divisas: Calcula el precio en Bolívares usando la tasa BCV y la tasa de Mercado con IGTF (3.48%).

🛠️ Mantenimiento
Para aplicar cambios en el esquema de la base de datos o comenzar con un historial limpio, sigue estos pasos:

Detén el bot.

Elimina el archivo: data/exchange_rates.db.

Reinicia el bot (python app/main.py).

El database_manager.py recreará las tablas necesarias automáticamente al inicio.