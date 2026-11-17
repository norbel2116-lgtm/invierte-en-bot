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
CHANNEL_ID = os.getenv("CHANNEL_ID", "-1001234567890")  
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))
# Enlace público del canal para el botón interactivo (cámbialo si lo deseas)
LINK_CANAL = os.getenv("LINK_CANAL", "https://t.me/TuCanalDePagos")

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
    "1": {
        "nombre": "Plan TRX & Cripto Base", 
        "moneda": "TRX / USDT", 
        "red": "TRC20 (Tron) & TON", 
        "detalle": "Puedes depositar en USDT (Red Tron o TON), TRX o GRAM. Rendimiento optimizado."
    },
    "2": {
        "nombre": "Plan USDT Estándar", 
        "moneda": "USDT / TRX", 
        "red": "TRC20 (Tron) & TON", 
        "detalle": "Acepta USDT por Tron/TON, además de TRX y GRAM con acreditación automatizada."
    },
    "3": {
        "nombre": "Plan GRAM & TON Pro", 
        "moneda": "GRAM / USDT", 
        "red": "TON & TRC20 (Tron)", 
        "detalle": "Diseñado para operar fuertemente en red TON (GRAM, USDT) y red Tron (TRX, USDT)."
    },
    "4": {
        "nombre": "Plan Élite Multired", 
        "moneda": "Multidivisa", 
        "red": "TRC20 & TON", 
        "detalle": "Máxima flexibilidad: acepta USDT, TRX y GRAM en cualquiera de las dos redes oficiales."
    }
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
                
                espera = random.randint(600, 3600)  
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
                InlineKeyboardButton("📢 Proofs Channel", url=LINK_CANAL)
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
                InlineKeyboardButton("📢 Canal de Comprobantes", url=LINK_CANAL)
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

# --- GENERADOR DEL MENSAJE DE REFERIDOS ---
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
        if idioma == "en":
            texto = (
                "📋 **Investment Plans & Yields:**\n"
                "🔹 **Limits:** Min: 2 USD | Max: 1000 USD\n"
                "💡 *Note: In all plans you can deposit using USDT (Tron TRC20 or TON), TRX, or GRAM.*\n\n"
            )
            for key, plan in PLANES_INVERSION.items():
                texto += f"🔹 **ID {key}: {plan['nombre']}**\n   • Accepted: {plan['moneda']}\n   • Networks: {plan['red']}\n   • ℹ️ {plan['detalle']}\n\n"
        else:
            texto = (
                "📋 **Planes de Inversión y Rendimientos:**\n"
                "🔹 **Límites:** Mínimo: 2 USD | Máximo: 1000 USD\n"
                "💡 *Nota: En todos los planes puedes depositar en USDT (Red Tron o TON), TRX y GRAM.*\n\n"
            )
            for key, plan in PLANES_INVERSION.items():
                texto += f"🔹 **ID {key}: {plan['nombre']}**\n   • Divisas: {plan['moneda']}\n   • Redes: {plan['red']}\n   • ℹ️ {plan['detalle']}\n\n"
        
        await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")

    elif data == "btn_depositar":
        texto = (
            "💳 **Official Deposit Wallets**:\n\n"
            "🔹 **TR
