import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Lee el token de forma segura desde la nube
TOKEN = os.getenv("TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mensaje de bienvenida y menú de inversión"""
    await update.message.reply_text(
        "🚀 **Bienvenido a Invierte Bot**\n\n"
        "Tu asistente personal para el seguimiento del mercado cripto.\n\n"
        "📊 **Comandos disponibles:**\n"
        "• `/precio [cripto]` - Consulta el precio actual en USD (ej. `/precio bitcoin`).\n"
        "• `/calcular [cripto] [cantidad]` - Calcula el valor total de tus activos (ej. `/calcular solana 2.5`)."
    )

async def obtener_precio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Consulta el precio actual de una criptomoneda"""
    if not context.args:
        await update.message.reply_text("⚠️ Indica una criptomoneda. Ejemplo: `/precio bitcoin`")
        return
    
    crypto = context.args[0].lower()
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto}&vs_currencies=usd,usd_24h_change"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if crypto in data:
            precio = data[crypto]["usd"]
            cambio_24h = data[crypto].get("usd_24h_change", 0)
            icono = "📈" if cambio_24h >= 0 else "📉"
            
            await update.message.reply_text(
                f"💵 **{crypto.capitalize()}**\n"
                f"• Precio: **${precio:,.2f} USD**\n"
                f"• Cambio 24h: {icono} {cambio_24h:.2f}%"
            )
        else:
            await update.message.reply_text("❌ No encontré esa criptomoneda. Escribe su nombre en inglés (ej. bitcoin, ethereum, cardano).")
    except Exception:
        await update.message.reply_text("⚠️ Error al conectar con el servidor de precios.")

async def calcular_inversion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Calcula el valor total de una cantidad de criptomonedas"""
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Uso correcto: `/calcular [cripto] [cantidad]`\nEjemplo: `/calcular ethereum 0.5`")
        return
    
    crypto = context.args[0].lower()
    try:
        cantidad = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ La cantidad debe ser un número válido.")
        return

    url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto}&vs_currencies=usd"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if crypto in data:
            precio_unitario = data[crypto]["usd"]
            total = precio_unitario * cantidad
            await update.message.reply_text(
                f"💼 **Cálculo de Inversión**\n"
                f"• Activo: {crypto.capitalize()}\n"
                f"• Cantidad: {cantidad}\n"
                f"• Valor Total: **${total:,.2f} USD**"
            )
        else:
            await update.message.reply_text("❌ Criptomoneda no encontrada.")
    except Exception:
        await update.message.reply_text("⚠️ Ocurrió un error al procesar el cálculo.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("precio", obtener_precio))
    app.add_handler(CommandHandler("calcular", calcular_inversion))

    print("🤖 Bot de inversión configurado y en ejecución 24/7...")
    app.run_polling()
