import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

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

TOKEN = os.getenv("TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "**Bienvenido a Invierte Bot**\n\n"
        "Tu asistente personal para el seguimiento del mercado cripto.\n\n"
        "**Comandos disponibles:**\n"
        "• `/precio [cripto]` - Consulta el precio actual en USD (ej. btc, trx, ton).\n"
        "• `/calcular [cripto] [cantidad]` - Calcula el valor total de tus activos."
    )

async def obtener_precio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Indica una criptomoneda. Ejemplo: `/precio bitcoin` o `/precio btc`")
        return
    
    # Diccionario para traducir abreviaturas al ID oficial de CoinGecko
    mapeo_cripto = {
        "btc": "bitcoin",
        "eth": "ethereum",
        "trx": "tron",
        "ton": "the-open-network",
        "sol": "solana",
        "usdt": "tether"
    }
    
    entrada = context.args[0].lower()
    crypto = mapeo_cripto.get(entrada, entrada)
    
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto}&vs_currencies=usd"
    
    try:
        response = requests.get(url)
        data = response.json()
        if crypto in data:
            precio = data[crypto]["usd"]
            await update.message.reply_text(f"El precio actual de {crypto.capitalize()} es ${precio} USD.")
        else:
            await update.message.reply_text("❌ Criptomoneda no encontrada en CoinGecko.")
    except Exception:
        await update.message.reply_text("❌ Error al consultar el precio.")

def main():
    keep_alive()
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("precio", obtener_precio))
    
    application.run_polling()

if __name__ == '__main__':
    main()
