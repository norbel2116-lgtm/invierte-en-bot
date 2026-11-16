import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- MINI SERVIDOR WEB PARA RENDER (Evita el error de puertos) ---
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "¡Bot activo y funcionando!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()
# -----------------------------------------------------------------

# Lee el token de forma segura desde las variables de entorno de Render
TOKEN = os.getenv("TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mensaje de bienvenida y menú de inversión"""
    await update.message.reply_text(
        "**Bienvenido a Invierte Bot**\n\n"
        "Tu asistente personal para el seguimiento del mercado cripto.\n\n"
        "**Comandos disponibles:**\n"
        "• `/precio [cripto]` - Consulta el precio actual en USD.\n"
        "• `/calcular [cripto] [cantidad]` - Calcula el valor total de tus activos."
    )

async def obtener_precio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Indica una criptomoneda. Ejemplo: `/precio bitcoin`")
        return
    
    crypto = context.args[0].lower()
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto}&vs_currencies=usd"
    
    try:
        response = requests.get(url)
        data = response.json()
        if crypto in data:
            precio = data[crypto]["usd"]
            await update.message.reply_text(f"El precio actual de {crypto.capitalize()} es ${precio} USD.")
        else:
            await update.message.reply_text("❌ Criptomoneda no encontrada.")
    except Exception:
        await update.message.reply_text("❌ Error al consultar el precio.")

def main():
    # Enciende el servidor web en segundo plano para abrir el puerto de Render
    keep_alive()

    # Configuración del bot de Telegram
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("precio", obtener_precio))
    
    # Arranca el bot
    application.run_polling()

if __name__ == '__main__':
    main()
