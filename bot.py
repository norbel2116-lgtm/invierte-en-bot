import os
import sqlite3
import requests
from datetime import datetime
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

# --- CONFIGURACIÓN DE LA BASE DE DATOS SQLITE ---
def inicializar_db():
    conn = sqlite3.connect("usuarios.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            user_id INTEGER PRIMARY KEY,
            nombre TEXT,
            patrocinador_id INTEGER,
            deposito_activo REAL DEFAULT 0,
            moneda_deposito TEXT DEFAULT 'USDT',
            red_deposito TEXT DEFAULT 'TRON',
            fecha_deposito TEXT,
            ganancias_referidos REAL DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

inicializar_db()

PLANES_INVERSION = {
    "1": {"nombre": "Plan TRX (Red Tron)", "moneda": "TRX", "red": "TRC20 (Tron)"},
    "2": {"nombre": "Plan USDT (Red Tron)", "moneda": "USDT", "red": "TRC20 (Tron)"},
    "3": {"nombre": "Plan GRAM (Red TON)", "moneda": "GRAM", "red": "TON"},
    "4": {"nombre": "Plan USDT (Red TON)", "moneda": "USDT", "red": "TON"}
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    patrocinador_id = int(args[0]) if args and args[0].isdigit() else None
    
    conn = sqlite3.connect("usuarios.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, patrocinador_id FROM usuarios WHERE user_id = ?", (user.id,))
    existe = cursor.fetchone()
    
    if not existe:
        cursor.execute(
            "INSERT INTO usuarios (user_id, nombre, patrocinador_id) VALUES (?, ?, ?)",
            (user.id, user.first_name, patrocinador_id)
        )
        conn.commit()
        
        if patrocinador_id and patrocinador_id != user.id:
            try:
                await context.bot.send_message(
                    chat_id=patrocinador_id,
                    text=f"🎉 **¡Nuevo Referido Detectado!**\n\n"
                         f"El usuario **{user.first_name}** se acaba de unir a tu red a través de tu enlace de invitación (Nivel 1)."
                )
            except Exception as e:
                print(f"No se pudo notificar al patrocinador: {e}")
                
    conn.close()
    
    await update.message.reply_text(
        f"🤖 **Bienvenido a Invierte Bot (Multired)**\n\n"
        f"Hola {user.first_name}, gestiona tus inversiones y ganancias diarias.\n\n"
        f"**Comandos disponibles:**\n"
        f"• `/saldo` - Ver tu capital, ganancias diarias y referidos.\n"
        f"• `/planes` - Ver planes y rangos de ganancia.\n"
        f"• `/depositar` - Ver las wallets oficiales para depositar.\n"
        f"• `/invertir [id] [cantidad]` - Iniciar una solicitud de inversión.\n"
        f"• `/notificar [hash]` - Enviar tu hash de transferencia.\n"
        f"• `/referidos` - Enlace de invitación y niveles de comisión.\n"
        f"• `/retirar` - Consultar reglas de retiros (lunes, pasados 5 días)."
    )

async def mostrar_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = sqlite3.connect("usuarios.db")
    cursor = conn.cursor()
    cursor.execute("SELECT deposito_activo, moneda_deposito, fecha_deposito, ganancias_referidos FROM usuarios WHERE user_id = ?", (user.id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row or not row[0] or row[0] == 0:
        await update.message.reply_text(
            "💰 **Tu Balance Actual:**\n\n"
            "• Capital Depositado: **0 USD**\n"
            "• Ganancias Diarias Acumuladas: **0 USD**\n"
            "• Ganancias por Referidos: **0 USD**\n\n"
            "⚠️ No tienes inversiones activas. Usa `/planes` y `/invertir` para comenzar."
        )
        return

    deposito, moneda, fecha_str, ganancia_ref = row
    ganancia_diaria_acumulada = 0.0
    dias_transcurridos = 0
    
    if fecha_str:
        fecha_dep = datetime.strptime(fecha_str, "%Y-%m-%d %H:%M:%S")
        dias_transcurridos = (datetime.now() - fecha_dep).days
        
        if 2 <= deposito <= 5:
            rendimiento_5_dias = 0.021
        elif 5 < deposito <= 10:
            rendimiento_5_dias = 0.025
        else:
            rendimiento_5_dias = 0.029
            
        ganancia_por_dia = (deposito * rendimiento_5_dias) / 5
        ganancia_diaria_acumulada = ganancia_por_dia * dias_transcurridos

    texto = (
        "💰 **Tu Balance y Rendimiento en Vivo:**\n\n"
        f"• Capital en Inversión: **{deposito} {moneda}**\n"
        f"• Días Activo: **{dias_transcurridos} días**\n"
        f"• 📈 Ganancias Diarias Generadas: **{ganancia_diaria_acumulada:.4f} {moneda}** *(sumando diario)*\n"
        f"• 👥 Ganancias por Referidos: **{ganancia_ref} USD**\n\n"
        "💡 *Recuerda que puedes retirar tus ganancias o capital completo cada lunes, cumplidos al menos 5 días desde tu inversión.*"
    )
    await update.message.reply_text(texto)

async def mostrar_planes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (
        "📋 **Planes de Inversión y Rangos de Rendimiento**:\n\n"
        "🟢 **Reglas Generales:**\n"
        "• Inversión mínima: **2 USD**\n"
        "• Inversión máxima: **1000 USD**\n\n"
        "📊 **Estructura de Ganancias (cada 5 días):**\n"
        "• De **2 a 5 USD** ➡️ **2.1%**\n"
        "• De **5 a 10 USD** ➡️ **2.5%**\n"
        "• Más de **10 USD** ➡️ **2.9%**\n\n"
        "🔹 **Monedas y Redes:**\n"
    )
    for key, plan in PLANES_INVERSION.items():
        texto += f"• **ID {key}:** {plan['nombre']} (Red: {plan['red']})\n"
    
    texto += "\nPara invertir usa: `/invertir [ID] [Cantidad]` (Ej: `/invertir 2 15`)"
    await update.message.reply_text(texto)

async def depositar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (
        "💳 **Direcciones de Depósito Oficiales**:\n\n"
        "🔹 **Red TRON (TRX y USDT TRC20):**\n"
        "`TFWUrcxFh4oknNgmBfTY6jjixhNaGm8t5u`\n\n"
        "🔹 **Red TON (GRAM y USDT TON):**\n"
        "`UQBwUUdb52EJ9T9XMn4lgn625XUDSgQKI3cI_BnAVSA3p8_v`\n\n"
        "⚠️ *Tras transferir, reporta con:* `/notificar [Tu_Hash]`"
    )
    await update.message.reply_text(texto)

async def notificar_deposito(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Debes incluir el hash. Ejemplo: `/notificar 5J1...abc`")
        return
    hash_tx = " ".join(context.args)
    await update.message.reply_text(f"⏳ Comprobante recibido (`{hash_tx}`). En proceso de verificación en la red.")

async def aprobar_deposito(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text("⚠️ Uso administrativo: `/aprobar [ID_Usuario] [Monto] [Moneda]`")
        return
    
    id_usuario = context.args[0]
    monto = float(context.args[1])
    moneda = context.args[2].upper()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect("usuarios.db")
    cursor = conn.cursor()
    
    cursor.execute(
        "UPDATE usuarios SET deposito_activo = ?, moneda_deposito = ?, fecha_deposito = ? WHERE user_id = ?",
        (monto, moneda, fecha_actual, id_usuario)
    )
    
    comisiones = [0.03, 0.02, 0.01, 0.005]
    patrocinador_actual = id_usuario
    
    for nivel, porcentaje in enumerate(comisiones, start=1):
        cursor.execute("SELECT patrocinador_id FROM usuarios WHERE user_id = ?", (patrocinador_actual,))
        res = cursor.fetchone()
        if res and res[0]:
            patrocinador_id = res[0]
            comision = monto * porcentaje
            cursor.execute(
                "UPDATE usuarios SET ganancias_referidos = ganancias_referidos + ? WHERE user_id = ?",
                (comision, patrocinador_id)
            )
            try:
                await context.bot.send_message(
                    chat_id=patrocinador_id,
                    text=f"🎁 **¡Comisión por Inversión de Referido (Nivel {nivel})!**\nHas ganado **{comision:.2f} {moneda}**."
                )
            except:
                pass
            patrocinador_actual = patrocinador_id
        else:
            break

    conn.commit()
    conn.close()
    
    try:
        await context.bot.send_message(
            chat_id=id_usuario,
            text="✅ **¡Depósito Acreditado con Éxito!**\nTu capital y tus ganancias diarias ya han comenzado a correr. Revisa tu saldo con `/saldo`."
        )
        await update.message.reply_text(f"✔️ Depósito de {monto} {moneda} acreditado al usuario `{id_usuario}` y referidos procesados.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error al notificar al usuario: {e}")

async def referidos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bot_username = context.bot.username
    link_referido = f"https://t.me/{bot_username}?start={user.id}"
    
    texto = (
        "👥 **Sistema de Referidos Multinivel**\n\n"
        "Invita amigos y gana comisiones automáticas:\n"
        "• **Nivel 1 (Directos):** 3%\n"
        "• **Nivel 2:** 2%\n"
        "• **Nivel 3:** 1%\n"
        "• **Nivel 4:** 0.5%\n\n"
        "🔗 **Tu enlace personal:**\n"
        f"`{link_referido}`"
    )
    await update.message.reply_text(texto)

async def retirar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏦 **Sistema de Retiros**:\n\n"
        "• Puedes retirar tus ganancias o el capital completo **5 días después de tu inversión inicial**.\n"
        "• Los pagos se procesan **todos los lunes**.\n\n"
        "Contacta al soporte con tu wallet para procesar tu retiro."
    )

async def invertir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Uso: `/invertir [ID_Plan] [Cantidad]`\nEjemplo: `/invertir 2 15`")
        return
    
    plan_id = context.args[0]
    try:
        cantidad = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ La cantidad debe ser numérica.")
        return
    
    if plan_id not in PLANES_INVERSION:
        await update.message.reply_text("❌ Plan inválido. Usa `/planes`.")
        return
    
    if cantidad < 2 or cantidad > 1000:
        await update.message.reply_text("❌ La inversión debe estar entre **2 y 1000 USD**.")
        return
    
    if 2 <= cantidad <= 5:
        porcentaje = "2.1%"
    elif 5 < cantidad <= 10:
        porcentaje = "2.5%"
    else:
        porcentaje = "2.9%"

    plan = PLANES_INVERSION[plan_id]
    wallet = "TFWUrcxFh4oknNgmBfTY6jjixhNaGm8t5u" if "Tron" in plan["red"] else "UQBwUUdb52EJ9T9XMn4lgn625XUDSgQKI3cI_BnAVSA3p8_v"
    
    await update.message.reply_text(
        f"✅ **Inversión Registrada**\n\n"
        f"• Plan: {plan['nombre']}\n"
        f"• Monto: {cantidad} {plan['moneda']}\n"
        f"• Rendimiento: **{porcentaje}** cada 5 días\n\n"
        f"💳 Transfiere a:\n`{wallet}`\n\n"
        f"📲 Reporta
