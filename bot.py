import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "¡Bot multired activo y funcionando!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

TOKEN = os.getenv("TOKEN")

# --- PLANES DE INVERSIÓN (Redes TRON y TON) ---
PLANES_INVERSION = {
    "1": {"nombre": "Plan TRX (Red Tron)", "moneda": "TRX", "min": 100, "retorno": "5% diario", "dias": 7, "red": "TRC20 (Tron)"},
    "2": {"nombre": "Plan USDT (Red Tron)", "moneda": "USDT", "min": 10, "retorno": "8% diario", "dias": 10, "red": "TRC20 (Tron)"},
    "3": {"nombre": "Plan GRAM (Red TON)", "moneda": "GRAM", "min": 50, "retorno": "6% diario", "dias": 7, "red": "TON"},
    "4": {"nombre": "Plan USDT (Red TON)", "moneda": "USDT", "min": 10, "retorno": "8% diario", "dias": 10, "red": "TON"}
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **Bienvenido a Invierte Bot (Multired)**\n\n"
        "Gestiona tus inversiones y precios en las redes **TRON** y **TON**.\n\n"
        "**Comandos disponibles:**\n"
        "• `/planes` - Ver los planes en TRX, USDT (Tron/TON) y GRAM.\n"
        "• `/invertir [id] [cantidad]` - Iniciar una solicitud de inversión.\n"
        "• `/precio [cripto]` - Consultar precios en USD (ej. btc, trx, usdt, ton, gram)."
    )

async def mostrar_planes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = "📋 **Planes de Inversión Disponibles**:\n\n"
    for key, plan in PLANES_INVERSION.items():
        texto += (
            f"🔹 **ID {key}: {plan['nombre']}**\n"
            f"   • Red: {plan['red']}\n"
            f"   • Mínimo: {plan['min']} {plan['moneda']}\n"
            f"   • Beneficio: {plan['retorno']}\n"
            f"   • Duración: {plan['dias']} días\n\n"
        )
    texto += "Para invertir usa: `/invertir [ID] [Cantidad]` (Ej: `/invertir 3 50`)"
    await update.message.reply_text(texto)

async def invertir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Formato incorrecto. Usa: `/invertir [ID_Plan] [Cantidad]`\nEjemplo: `/invertir 4 20`")
        return
    
    plan_id = context.args[0]
    try:
        cantidad = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ La cantidad debe ser un número válido.")
        return
    
    if plan_id not in PLANES_INVERSION:
        await update.message.reply_text("❌ El ID del plan no existe. Usa `/planes` para ver los disponibles.")
        return
    
    plan = PLANES_INVERSION[plan_id]
    
    if cantidad < plan["min"]:
        await update.message.reply_text(f"❌ La cantidad mínima para el {plan['nombre']} es de {plan['min']} {plan['moneda']}.")
        return
    
    # Billeteras de depósito según la red
    if "Tron" in plan["red"]:
        wallet_deposito = "TYourTronWalletAddressHerexxxx (TRC20)"
    else:
        wallet_deposito = "UYourTonWalletAddressHerexxxx (TON)"
    
    await update.message.reply_text(
        f"✅ **¡Solicitud de Inversión Registrada!**\n\n"
        f"• Plan: {plan['nombre']}\n"
        f"• Monto: {cantidad} {plan['moneda']}\n"
        f"• Red: {plan['red']}\n\n"
        f"💳 Para activar tu plan, transfiere exactamente **{cantidad} {plan['moneda']}** a la siguiente dirección:\n"
        f"`{wallet_deposito}`\n\n"
        f"⚠️ *Contacta al soporte con el hash de tu transacción para acreditar tu saldo.*"
    )

async def obtener_precio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Indica una criptomoneda. Ejemplo: `/precio trx`, `/precio ton` o `/precio gram`")
        return
    
    mapeo_cripto = {
        "btc": "bitcoin",
        "eth": "ethereum",
        "trx": "tron",
        "ton": "the-open-network",
        "sol": "solana",
        "usdt": "tether",
        "gram": "gram"
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
    application.add_handler(CommandHandler("planes", mostrar_planes))
    application.add_handler(CommandHandler("invertir", invertir))
    application.add_handler(CommandHandler("precio", obtener_precio))
    
    application.run_polling()

if __name__ == '__main__':
    main()
