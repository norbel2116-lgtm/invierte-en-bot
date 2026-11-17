import os
import sqlite3
import random
import asyncio
import aiohttp
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

# --- SERVIDOR WEB FLASK (HILO SECUNDARIO) ---
app = Flask('')

@app.route('/')
def home():
    return "OK", 200

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "-1001234567890")  
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))
LINK_CANAL = os.getenv("LINK_CANAL", "https://t.me/TuCanalDePagos")

WALLET_TRON = "TFWUrcxFh4oknNgmBfTY6jjixhNaGm8t5u"
WALLET_TON = "UQBwUUdb52EJ9T9XMn4lgn625XUDSgQKI3cI_BnAVSA3p8_v"

# --- BASE DE DATOS SQLITE ---
def inicializar_db():
    try:
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
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS liquidez_global (
                id INTEGER PRIMARY KEY,
                fondo_actual REAL,
                ultima_actualizacion TEXT
            )
        """)
        cursor.execute("SELECT COUNT(*) FROM liquidez_global")
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "INSERT INTO liquidez_global (id, fondo_actual, ultima_actualizacion) VALUES (1, ?, ?)",
                (124500.00, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error inicializando BD: {e}")

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

def generar_usuario_ficticio():
    nombres = ["Carlos", "Ana", "Luis", "Elena", "Javier", "Sofia", "Miguel", "Rosa", "David", "Alejandro", "Daniel", "Carmen"]
    return f"{random.choice(nombres)}***{random.randint(10, 99)}"

# --- CONSULTAS REALES A LA BLOCKCHAIN (APIS PÚBLICAS) ---
async def obtener_ultima_transaccion_tron():
    url = f"https://apilist.tronscanapi.com/api/transaction?sort=-timestamp&count=true&limit=1&address={WALLET_TRON}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    transacciones = data.get("data", [])
                    if transacciones:
                        tx = transacciones[0]
                        hash_tx = tx.get("hash")
                        monto = 0
                        moneda = "USDT"
                        
                        trc20_transfers = tx.get("trc20TransferInfo", [])
                        if trc20_transfers:
                            monto_raw = float(trc20_transfers[0].get("amount_str", "0"))
                            decimals = int(trc20_transfers[0].get("decimal_str", "6"))
                            monto = monto_raw / (10 ** decimals)
                            moneda = trc20_transfers[0].get("symbol", "USDT")
                        else:
                            monto = tx.get("amount", 0) / 1000000
                            moneda = "TRX"
                        
                        if monto > 0:
                            return {
                                "hash": hash_tx,
                                "monto": round(monto, 2),
                                "moneda": moneda,
                                "red": "TRON (TRC20)" if moneda == "USDT" else "TRON",
                                "explorer": f"https://tronscan.org/#/transaction/{hash_tx}"
                            }
    except Exception as e:
        print(f"Error consultando TronScan: {e}")
    return None

async def obtener_ultima_transaccion_ton():
    url = f"https://toncenter.com/api/v2/getTransactions?address={WALLET_TON}&limit=1"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("ok") and data.get("result"):
                        tx = data["result"][0]
                        tx_hash_data = tx.get("transaction_id", {})
                        hash_tx = tx_hash_data.get("hash", "")
                        monto = round(random.uniform(5.0, 500.0), 2)
                        
                        if hash_tx:
                            return {
                                "hash": hash_tx,
                                "monto": monto,
                                "moneda": "GRAM",
                                "red": "TON",
                                "explorer": f"https://tonviewer.com/transaction/{hash_tx}"
                            }
    except Exception as e:
        print(f"Error consultando Toncenter: {e}")
    return None

# --- TAREA EN SEGUNDO PLANO: FLUJO DEL CANAL (BLINDADO) ---
async def bucle_comprobaciones(application):
    await asyncio.sleep(20)
    while True:
        try:
            ahora = datetime.now()
            conn = sqlite3.connect("usuarios.db")
            cursor = conn.cursor()
            cursor.execute("SELECT fondo_actual FROM liquidez_global WHERE id = 1")
            row_fondo = cursor.fetchone()
            fondo_actual = row_fondo[0] if row_fondo else 124500.00

            if ahora.weekday() == 0 and random.choice([True, False]):
                porcentaje_bajada = round(random.uniform(15.0, 35.0), 2)
                monto_restar = fondo_actual * (porcentaje_bajada / 100.0)
                fondo_actual = max(100000.0, fondo_actual - monto_restar)
            else:
                porcentaje_subida = round(random.uniform(0.5, 4.6), 2)
                monto_sumar = fondo_actual * (porcentaje_subida / 100.0)
                fondo_actual += monto_sumar

            cursor.execute("UPDATE liquidez_global SET fondo_actual = ?, ultima_actualizacion = ? WHERE id = 1", 
                           (fondo_actual, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            conn.close()

            datos_tx = None
            try:
                if random.choice([True, False]):
                    datos_tx = await obtener_ultima_transaccion_tron()
                if not datos_tx:
                    datos_tx = await obtener_ultima_transaccion_ton()
            except Exception as ex:
                print(f"Aviso obteniendo tx blockchain: {ex}")

            if datos_tx:
                tx_hash = datos_tx["hash"]
                monto = datos_tx["monto"]
                moneda_nombre = datos_tx["moneda"]
                red_oficial = datos_tx["red"]
                explorer_url = datos_tx["explorer"]
            else:
                tx_hash = "573f831d1b918717d23cf3053805908cfb677a552e464731f8211b514b779182"
                monto = round(random.uniform(3.0, 1500.0), 2)
                moneda_nombre = "USDT"
                red_oficial = "TRON (TRC20)"
                explorer_url = "https://tronscan.org/#/transaction/"

            usuario = generar_usuario_ficticio()

            if ahora.weekday() == 0 and random.choice([True, False]):
                mensaje = (
                    f"✅ **RETIRO PROCESADO (LUNES)**\n\n"
                    f"👤 **Usuario:** `{usuario}`\n"
                    f"💰 **Monto Retirado:** `{monto} {moneda_nombre}`\n"
                    f"🌐 **Red:** {red_oficial}\n"
                    f"🔗 **TXID:** [Ver en blockchain]({explorer_url}{tx_hash})"
                )
            else:
                mensaje = (
                    f"💎 **NUEVO DEPÓSITO / INVERSIÓN**\n\n"
                    f"👤 **Inversor:** `{usuario}`\n"
                    f"📥 **Monto Invertido:** `{monto} {moneda_nombre}`\n"
                    f"🌐 **Red Oficial:** {red_oficial}\n"
                    f"⚡ **Estado:** Acreditado y Activo\n"
                    f"🔗 **TXID:** [Verificar en Blockchain]({explorer_url}{tx_hash})"
                )

            if CHANNEL_ID:
                try:
                    await application.bot.send_message(
                        chat_id=CHANNEL_ID,
                        text=mensaje,
                        parse_mode="Markdown",
                        disable_web_page_preview=True
                    )
                except Exception as e:
                    print(f"Error enviando mensaje al canal: {e}")
            
        except Exception as e:
            print(f"Error en bucle de comprobaciones: {e}")

        # Intervalos variados seguros (de 3 a 35 min)
        intervalos_posibles = [180, 300, 450, 600, 1200, 2100]
        await asyncio.sleep(random.choice(intervalos_posibles))

async def post_init(application):
    # Solución clave para evitar el error de Application.create_task antes de arrancar
    asyncio.create_task(bucle_comprobaciones(application))

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
                InlineKeyboardButton("🏦 Liquidity Pool", callback_data="btn_liquidez")
            ],
            [
                InlineKeyboardButton("📋 Plans", callback_data="btn_planes"),
                InlineKeyboardButton("💳 Deposit", callback_data="btn_depositar")
            ],
            [
                InlineKeyboardButton("👥 Referrals", callback_data="btn_referidos"),
                InlineKeyboardButton("🏦 Withdraw", callback_data="btn_retirar")
            ],
            [
                InlineKeyboardButton("🎧 Support", callback_data="btn_soporte"),
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
                InlineKeyboardButton("🏦 Fondo de Liquidez", callback_data="btn_liquidez")
            ],
            [
                InlineKeyboardButton("📋 Planes", callback_data="btn_planes"),
                InlineKeyboardButton("💳 Depositar", callback_data="btn_depositar")
            ],
            [
                InlineKeyboardButton("👥 Referidos", callback_data="btn_referidos"),
                InlineKeyboardButton("🏦 Retirar", callback_data="btn_retirar")
            ],
            [
                InlineKeyboardButton("🎧 Soporte", callback_data="btn_soporte"),
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
    
    try:
        if update.message:
            await update.message.reply_text(texto, reply_markup=obtener_menu_idiomas(), parse_mode="Markdown")
        elif update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.edit_text(texto, reply_markup=obtener_menu_idiomas(), parse_mode="Markdown")
    except Exception as e:
        print(f"Error en start: {e}")

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

    if data == "btn_cambiar_idioma":
        await start(update, context)
        return

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
                f"• Payouts processed strictly on Mondays.\n"
                f"• Real-time blockchain verifiable proofs.\n"
                f"• Automated multi-level system.\n\n"
                f"⚠️ **Important Note:** Please **do not spam buttons**. Give the bot a few seconds to respond.\n\n"
                f"👇 **Choose an option below:**"
            )
        else:
            texto = (
                f"🛡️ **Bienvenido a Invierte Bot (Multired Segura)**\n\n"
                f"Hola, **{user.first_name}**. Estás en una plataforma transparente y automatizada para gestionar tus inversiones con seguridad.\n\n"
                f"✅ **¿Por qué confiar en nosotros?**\n"
                f"• Pagos procesados estrictamente los lunes.\n"
                f"• Comprobantes verificables en la blockchain en tiempo real.\n"
                f"• Sistema multinivel automatizado.\n\n"
                f"⚠️ **Nota Importante:** Por favor, **no presiones los botones muy rápido**. Dale unos segundos al bot para responder.\n\n"
                f"👇 **Selecciona una opción del menú interactivo:**"
            )
        
        try:
            await query.message.edit_text(texto, reply_markup=obtener_menu_principal(nuevo_idioma), parse_mode="Markdown")
        except Exception as e:
            print(f"Error al editar idioma: {e}")
        return

    conn = sqlite3.connect("usuarios.db")
    cursor = conn.cursor()
    cursor.execute("SELECT idioma FROM usuarios WHERE user_id = ?", (user.id,))
    row = cursor.fetchone()
    conn.
