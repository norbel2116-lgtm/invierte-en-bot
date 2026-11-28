import os
import re
import html
import sqlite3
import random
import asyncio
from datetime import datetime
from threading import Thread
import aiohttp
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Conflict, NetworkError, TimedOut, TelegramError, BadRequest
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.request import HTTPXRequest

# --- SERVIDOR WEB FLASK (HILO SECUNDARIO) ---
app = Flask("")


@app.route("/")
@app.route("/health")
def home():
    return "Bot Activo y Funcionando Correctamente", 200


def run_web():
    port = int(os.environ.get("PORT", 10000))
    print(f"Arrancando servidor web Flask en puerto {port}...", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


def _parse_admin_id() -> int:
    raw = (os.getenv("ADMIN_ID") or "123456789").strip()
    try:
        return int(raw)
    except ValueError:
        print(f"Aviso: ADMIN_ID inválido ('{raw}'), usando valor por defecto.", flush=True)
        return 123456789


TOKEN = (os.getenv("TOKEN") or "").strip()
CHANNEL_ID = (os.getenv("CHANNEL_ID") or "-1001234567890").strip()
ADMIN_ID = _parse_admin_id()
LINK_CANAL = (os.getenv("LINK_CANAL") or "https://t.me/TuCanalDePagos").strip()
DB_PATH = (os.getenv("DB_PATH") or "usuarios.db").strip()
_render_url = (os.getenv("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
SELF_PING_URL = (os.getenv("SELF_PING_URL") or "").strip() or (
    f"{_render_url}/health" if _render_url else ""
)

# --- FONDO DE LIQUIDEZ (INICIA EN 10,000 USD Y NUNCA BAJA DE 5,000 USD) ---
FONDO_INICIAL_USD = 10000.0
PISO_FONDO_USD = 5000.0

TASAS_REFERENCIA_USD = {
    "USD": 1.0,
    "USDT": 1.0,
    "USDC": 1.0,
    "TON": 3.5,
    "SOL": 140.0,
    "TRX": 0.16,
    "GRAM": 0.01,
    "BNB": 600.0,
    "ETH": 2500.0,
    "BTC": 75000.0,
}

# --- WALLETS Y REDES OFICIALES ---
WALLETS_OFICIALES = {
    "TRON": os.getenv("WALLET_TRON", "TFWUrcxFh4oknNgmBfTY6jjixhNaGm8t5u"),
    "TON": os.getenv("WALLET_TON", "UQBwUUdb52EJ9T9XMn4lgn625XUDSgQKI3cI_BnAVSA3p8_v"),
    "BTC": os.getenv("WALLET_BTC", "bc1qsejk806afnhztv7lqcsaes9s7a32p4grstwru7"),
    "BSC": os.getenv("WALLET_BSC", "0xAB75fD4D65A1A82E0eF5BbbFdFE6908E95F995EC"),
    "ETH": os.getenv("WALLET_ETH", "0xAB75fD4D65A1A82E0eF5BbbFdFE6908E95F995EC"),
    "SOL": os.getenv("WALLET_SOL", "2yns47xDAsMeM7Zdr1ujj17955CBHhk2kNkXqdpJGAyk"),
}

REDES_INFO = {
    "TRON": {
        "nombre": "TRON (TRC20)",
        "monedas": ["USDT", "TRX", "TRC20"],
        "explorer": "https://tronscan.org/#/transaction/",
    },
    "TON": {
        "nombre": "TON",
        "monedas": ["USDT", "TON", "GRAM", "Jettons"],
        "explorer": "https://tonviewer.com/transaction/",
    },
    "BSC": {
        "nombre": "BSC (BEP20)",
        "monedas": ["USDT", "BNB", "BEP20"],
        "explorer": "https://bscscan.com/tx/",
    },
    "ETH": {
        "nombre": "ETH (ERC20)",
        "monedas": ["USDT", "ETH", "ERC20"],
        "explorer": "https://etherscan.io/tx/",
    },
    "BTC": {
        "nombre": "Bitcoin (BTC)",
        "monedas": ["BTC", "USDT", "Tokens"],
        "explorer": "https://mempool.space/tx/",
    },
    "SOL": {
        "nombre": "Solana (SOL)",
        "monedas": ["USDT", "SOL", "SPL"],
        "explorer": "https://solscan.io/tx/",
    },
}

# --- HASHES DE RESPALDO VERIFICABLES (SOLO TON Y TRON, 64 HEX) ---
HASHES_RESPALDO_TON = [
    "07e8122c8ae5bba139ee091298a8c1f39bc0691b9be987dd68c287f69de5c359",
    "d789dfa8cadf9976259114a3609aa6e01378e3109883cee4a175ceee8c405a83",
    "fbc9e75185b260d0fd172a84e8f4ec6e2f0f91d6e3d39d19577b59f0ec4d983d",
    "e4f7f0c440d59af7b820f66f138c58e556989875bdb37cf015b6a16eb00252f0",
    "545a5a864b65aa92445f2c1da0d3a7dc16c8e7d12d2e77b4326fb9a8d9b94126",
    "58ba2676a11c9417b64afad9301d95339a0531872d2a626a56d2b0f66d5faeb7",
    "c65aad57ab22b5f1cb7118939d505d235213163d247eb6ab5a522cb8d244bee8",
    "1fc2464fca68b255cfd7a98cbbd172fa5316e4886195433d3945412edb40d51e",
    "1470537fbb640fa949460b0f44fe16427d2d0420b1a808210fb14b229f8259d3",
    "4af87bbb8b9a744f283c8e95b474fc8288820ecda25a956f660f71f546f99383",
    "d657a8b3af7715f6753de77dfec4babef43a91a36557294b6a295f380e7d3fcc",
    "55ba70950c0fe847049d0117b86714944b3a4498eb7c4439a7705020bc6169ab",
    "1795e3de8ce187e536a7ec8a7602d2e3f60a0fa6c0d48281da42b4014156a0ac",
    "96d5cc65f4b18aa405eb628948d3bbbf7f1e3b89eb75beb388fddaceef446453",
]

HASHES_RESPALDO_TRON = [
    "b6ea2bbf397db123c0129b530c056d828b761ed376b80e8fd5adfd7590c88b87",
    "94dc2877a6601436dc447a48e62a20f071ac8fc1bdd877e4a6d8489ce397f4c6",
    "925fc6f8bc0025b566328963ddb4204008aa6aa30c5b1d2992d46111f47048dc",
    "34868cbc8a07b1904bb27564ba92105707b27af38606a829e7376f5b8bf7961c",
    "a77fe87c31bcf5faf116226c3747a47ee7a927a2b9a3c6f2e9e35a3233c16a4f",
    "ac73ce4600cf0f1d444de841aaf71e697b6e591c230f27c2143f25c1eb6d8620",
    "1767b236bbe823c3724118ffd6f3d25d1227a4a259f5482438cdc78a795cda8d",
    "d654d283158a4706531e226ec690bbeaaefe24b51ac9c6b2ddd9236a39f387b1",
]

MIN_MONTO_INVERSION = 0.5
MIN_MONTO_RETIRO = 0.5
BONO_ENTRADA_REFERIDO_USD = 0.05
HASHES_USADOS_SESION = set()
DB_WRITE_LOCK = asyncio.Lock()

# Rangos realistas por token para comprobantes en el canal
RANGOS_COMPROBANTES = {
    "USDT": (0.5, 500.0),
    "TON": (0.5, 250.0),
    "SOL": (0.01, 20.0),
    "TRX": (5.0, 5000.0),
    "GRAM": (1.0, 5000.0),
    "BNB": (0.002, 8.0),
    "ETH": (0.001, 4.0),
    "BTC": (0.00005, 0.08),
}

COMISION_ANTICIPADA_POR_MONEDA = {
    "USD": 0.2,
    "USDT": 0.2,
    "TRX": 0.2,
    "GRAM": 0.2,
    "TON": 0.2,
    "BNB": 0.2,
    "ETH": 0.2,
    "SOL": 0.2,
    "BTC": 0.00001,
}

# --- PLANES CON VALORES EN USD Y MÍNIMO DESDE 0.5 USD ---
PLANES_INVERSION = {
    "1": {
        "nombre": "Plan Inicio (7 días)",
        "boton": "🟢 Inicio · 7d (0.7%)",
        "modalidad": "plazo_fijo",
        "dias": 7,
        "tasa_ciclo": 0.007,
        "min": 0.5,
        "max": 1000.0,
        "moneda": "USD",
        "red_sugerida": "TRON",
        "permite_reinvest": True,
        "detalle": "Ideal para empezar rápido sin plazos largos.",
    },
    "2": {
        "nombre": "Plan Crecimiento (14 días)",
        "boton": "🔵 Crecimiento · 14d (2.4%)",
        "modalidad": "plazo_fijo",
        "dias": 14,
        "tasa_ciclo": 0.024,
        "min": 0.5,
        "max": 1000.0,
        "moneda": "USD",
        "red_sugerida": "TON",
        "permite_reinvest": True,
        "detalle": "Buen equilibrio entre duración y rendimiento.",
    },
    "3": {
        "nombre": "Plan Pro / Élite (21 días)",
        "boton": "🟣 Pro / Élite · 21d (7.8%)",
        "modalidad": "plazo_fijo",
        "dias": 21,
        "tasa_ciclo": 0.078,
        "min": 1.0,
        "max": 1000.0,
        "moneda": "USD",
        "red_sugerida": "BSC",
        "permite_reinvest": True,
        "detalle": "Pensado para ciclos de mayor duración.",
    },
    "4": {
        "nombre": "Fondo Flexible",
        "boton": "🟡 Flexible · Liquidez (0.5%)",
        "modalidad": "liquidez_flexible",
        "dias": 0,
        "tasa_ciclo": 0.005,
        "min": 0.5,
        "max": 1000.0,
        "moneda": "USD",
        "red_sugerida": "TRON",
        "permite_reinvest": False,
        "detalle": "Sin plazo fijo, respaldado por el fondo de liquidez.",
    },
    "5": {
        "nombre": "Meta Escalonada (30 días)",
        "boton": "🟠 Meta · 30d (3.2%)",
        "modalidad": "aporte_meta",
        "dias": 30,
        "tasa_ciclo": 0.032,
        "min": 0.5,
        "max": 1000.0,
        "moneda": "USD",
        "red_sugerida": "SOL",
        "permite_reinvest": True,
        "detalle": "Permite ir sumando aportes progresivos durante el mes.",
    },
}


def esc(valor) -> str:
    return html.escape(str(valor if valor is not None else ""))


async def editar_o_responder_texto(
    update: Update,
    texto: str,
    reply_markup=None,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = False,
):
    query = update.callback_query
    if query and query.message:
        try:
            await query.message.edit_text(
                texto,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
            )
            return
        except BadRequest as e:
            if "message is not modified" in str(e).lower():
                return
            try:
                await query.message.reply_text(
                    texto,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                    disable_web_page_preview=disable_web_page_preview,
                )
            except Exception as err2:
                print(f"Error respondiendo mensaje tras BadRequest: {err2}", flush=True)
        except Exception as e:
            print(f"Error editando mensaje: {e}", flush=True)
    elif update.message:
        try:
            await update.message.reply_text(
                texto,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
            )
        except Exception as e:
            print(f"Error enviando mensaje: {e}", flush=True)


def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=20, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=15000;")
    return conn


async def db_exec(fn, *args, write: bool = False, **kwargs):
    if write:
        async with DB_WRITE_LOCK:
            return await asyncio.to_thread(fn, *args, **kwargs)
    return await asyncio.to_thread(fn, *args, **kwargs)


def convertir_a_usd(monto: float, moneda: str) -> float:
    m_upper = (moneda or "USD").upper()
    tasa = TASAS_REFERENCIA_USD.get(m_upper, 1.0)
    return round(float(monto) * tasa, 4)


# --- BASE DE DATOS SQLITE ---
def inicializar_db():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    user_id INTEGER PRIMARY KEY,
                    nombre TEXT,
                    patrocinador_id INTEGER,
                    deposito_activo REAL DEFAULT 0,
                    moneda_deposito TEXT DEFAULT 'USD',
                    red_deposito TEXT DEFAULT 'TRON',
                    fecha_deposito TEXT,
                    ganancias_referidos REAL DEFAULT 0,
                    en_soporte INTEGER DEFAULT 0,
                    esperando_monto INTEGER DEFAULT 0,
                    esperando_hash INTEGER DEFAULT 0,
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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS inversiones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    plan_id TEXT,
                    modalidad TEXT,
                    monto REAL,
                    moneda TEXT,
                    red TEXT,
                    reinversion_auto INTEGER DEFAULT 0,
                    dias_plazo INTEGER DEFAULT 0,
                    fecha_inicio TEXT,
                    estado TEXT DEFAULT 'activa'
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS comprobantes_verificados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tx_hash TEXT UNIQUE,
                    red TEXT,
                    moneda TEXT,
                    monto REAL,
                    tipo TEXT,
                    fecha TEXT
                )
            """)

            cursor.execute("PRAGMA table_info(usuarios)")
            columnas = [col[1] for col in cursor.fetchall()]
            if "red_deposito" not in columnas:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN red_deposito TEXT DEFAULT 'TRON'")
            if "esperando_monto" not in columnas:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN esperando_monto INTEGER DEFAULT 0")
            if "esperando_hash" not in columnas:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN esperando_hash INTEGER DEFAULT 0")

            ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("SELECT fondo_actual FROM liquidez_global WHERE id = 1")
            fila_fondo = cursor.fetchone()
            if not fila_fondo:
                cursor.execute(
                    "INSERT INTO liquidez_global (id, fondo_actual, ultima_actualizacion) VALUES (1, ?, ?)",
                    (FONDO_INICIAL_USD, ahora),
                )
            else:
                fondo_previo = float(fila_fondo[0] or 0.0)
                if fondo_previo == 124500.0:
                    cursor.execute(
                        "UPDATE liquidez_global SET fondo_actual = ?, ultima_actualizacion = ? WHERE id = 1",
                        (FONDO_INICIAL_USD, ahora),
                    )
                elif fondo_previo < PISO_FONDO_USD:
                    cursor.execute(
                        "UPDATE liquidez_global SET fondo_actual = ?, ultima_actualizacion = ? WHERE id = 1",
                        (PISO_FONDO_USD, ahora),
                    )

            for h_ton in HASHES_RESPALDO_TON:
                cursor.execute(
                    "INSERT OR IGNORE INTO comprobantes_verificados (tx_hash, red, moneda, monto, tipo, fecha) VALUES (?, ?, ?, ?, ?, ?)",
                    (h_ton, "TON", "TON", 10.0, "respaldo_ton", ahora),
                )
            for h_tron in HASHES_RESPALDO_TRON:
                cursor.execute(
                    "INSERT OR IGNORE INTO comprobantes_verificados (tx_hash, red, moneda, monto, tipo, fecha) VALUES (?, ?, ?, ?, ?, ?)",
                    (h_tron, "TRON", "USDT", 25.0, "respaldo_tron", ahora),
                )
    except Exception as e:
        print(f"Error inicializando BD: {e}", flush=True)


inicializar_db()


def generar_usuario_ficticio():
    nombres = [
        "Carlos", "Ana", "Luis", "Elena", "Javier", "Sofia",
        "Miguel", "Rosa", "David", "Alejandro", "Daniel", "Carmen",
    ]
    return f"{random.choice(nombres)}***{random.randint(10, 99)}"


def es_hash_valido(tx_hash: str, red: str) -> bool:
    if not tx_hash or not isinstance(tx_hash, str):
        return False
    h = tx_hash.strip()
    if red in ("TRON", "BSC", "ETH", "BTC"):
        return bool(re.fullmatch(r"(0x)?[0-9a-fA-F]{64}", h))
    if red in ("TON", "SOL"):
        return bool(re.fullmatch(r"[0-9a-fA-F]{64}|[1-9A-HJ-NP-Za-km-z]{32,128}|[A-Za-z0-9+/=_-]{32,128}", h))
    return False


def _marcar_hash_usado(tx_hash: str):
    HASHES_USADOS_SESION.add(tx_hash)
    if len(HASHES_USADOS_SESION) > 2000:
        recientes = list(HASHES_USADOS_SESION)[-500:]
        HASHES_USADOS_SESION.clear()
        HASHES_USADOS_SESION.update(recientes)
        HASHES_USADOS_SESION.add(tx_hash)


def _hash_ya_publicado(tx_hash: str) -> bool:
    if tx_hash in HASHES_USADOS_SESION:
        return True
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM comprobantes_verificados WHERE tx_hash = ? AND tipo = 'publicado_canal' LIMIT 1",
                (tx_hash,),
            )
            return cursor.fetchone() is not None
    except Exception:
        return False


def _registrar_hash_y_ajustar_fondo(
    tx_hash: str,
    red: str,
    moneda: str,
    monto: float,
    tipo_op: str,
) -> float:
    _marcar_hash_usado(tx_hash)
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    delta_usd = convertir_a_usd(monto, moneda)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO comprobantes_verificados (tx_hash, red, moneda, monto, tipo, fecha) VALUES (?, ?, ?, ?, ?, ?)",
            (tx_hash, red, moneda, monto, "publicado_canal", ahora),
        )
        cursor.execute("SELECT fondo_actual FROM liquidez_global WHERE id = 1")
        row = cursor.fetchone()
        fondo_actual = float(row[0]) if row and row[0] is not None else FONDO_INICIAL_USD

        if tipo_op == "deposito":
            nuevo_fondo = round(max(fondo_actual + delta_usd, PISO_FONDO_USD), 2)
        else:
            nuevo_fondo = round(max(fondo_actual - delta_usd, PISO_FONDO_USD), 2)

        if row:
            cursor.execute(
                "UPDATE liquidez_global SET fondo_actual = ?, ultima_actualizacion = ? WHERE id = 1",
                (nuevo_fondo, ahora),
            )
        else:
            cursor.execute(
                "INSERT INTO liquidez_global (id, fondo_actual, ultima_actualizacion) VALUES (1, ?, ?)",
                (nuevo_fondo, ahora),
            )
    return nuevo_fondo


def _cumple_filtro_monto(monto: float, moneda: str = "USDT") -> bool:
    if monto is None or monto <= 0:
        return False
    m_upper = (moneda or "USDT").upper()
    min_val, max_val = RANGOS_COMPROBANTES.get(m_upper, (MIN_MONTO_INVERSION, 500.0))
    return min_val <= monto <= max_val


async def obtener_tx_real_tron(session: aiohttp.ClientSession, address: str, _tipo_operacion: str = "deposito"):
    url = f"https://api.trongrid.io/v1/accounts/{address}/transactions/trc20?limit=50"
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=7)) as resp:
        if resp.status != 200:
            return None
        data = await resp.json()
        txs = data.get("data") or []
        random.shuffle(txs)
        for tx in txs:
            tx_hash = tx.get("transaction_id")
            if not es_hash_valido(tx_hash, "TRON"):
                continue
            decimals = int((tx.get("token_info") or {}).get("decimals", 6))
            raw_val = tx.get("value")
            if raw_val is None:
                continue
            monto = round(float(raw_val) / (10 ** decimals), 4)
            simbolo = ((tx.get("token_info") or {}).get("symbol") or "USDT").upper()
            if not _cumple_filtro_monto(monto, simbolo) or _hash_ya_publicado(tx_hash):
                continue
            return {
                "hash": tx_hash,
                "monto": monto,
                "moneda": simbolo,
                "red": REDES_INFO["TRON"]["nombre"],
                "explorer": f"{REDES_INFO['TRON']['explorer']}{tx_hash}",
            }
    return None


async def obtener_tx_real_btc(session: aiohttp.ClientSession, address: str, _tipo_operacion: str = "deposito"):
    url = f"https://mempool.space/api/address/{address}/txs"
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=7)) as resp:
        if resp.status != 200:
            return None
        txs = await resp.json()
        if not isinstance(txs, list):
            return None
        candidatos = txs[:30]
        random.shuffle(candidatos)
        for tx in candidatos:
            txid = tx.get("txid")
            if not es_hash_valido(txid, "BTC"):
                continue
            status = tx.get("status") or {}
            if not status.get("confirmed"):
                continue
            monto_sats = sum(
                int(vout.get("value", 0))
                for vout in (tx.get("vout") or [])
                if vout.get("scriptpubkey_address") == address
            )
            if monto_sats == 0 and tx.get("vout"):
                monto_sats = sum(int(vout.get("value", 0)) for vout in (tx.get("vout") or []))
            monto_btc = round(monto_sats / 1e8, 6)
            if not _cumple_filtro_monto(monto_btc, "BTC") or _hash_ya_publicado(txid):
                continue
            return {
                "hash": txid,
                "monto": monto_btc,
                "moneda": "BTC",
                "red": REDES_INFO["BTC"]["nombre"],
                "explorer": f"{REDES_INFO['BTC']['explorer']}{txid}",
            }
    return None


async def obtener_tx_real_ton(session: aiohttp.ClientSession, address: str, _tipo_operacion: str = "deposito"):
    url = f"https://toncenter.com/api/v2/getTransactions?address={address}&limit=50"
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=7)) as resp:
        if resp.status != 200:
            return None
        data = await resp.json()
        if not data.get("ok"):
            return None
        txs = data.get("result") or []
        random.shuffle(txs)
        for tx in txs:
            tx_id_obj = tx.get("transaction_id") or {}
            tx_hash = tx_id_obj.get("hash")
            if not es_hash_valido(tx_hash, "TON"):
                continue
            in_msg = tx.get("in_msg") or {}
            value_nano = int(in_msg.get("value") or 0)
            monto_ton = round(value_nano / 1e9, 4)
            if not _cumple_filtro_monto(monto_ton, "TON") or _hash_ya_publicado(tx_hash):
                continue
            return {
                "hash": tx_hash,
                "monto": monto_ton,
                "moneda": "TON",
                "red": REDES_INFO["TON"]["nombre"],
                "explorer": f"{REDES_INFO['TON']['explorer']}{tx_hash}",
            }
    return None


async def _obtener_tx_evm_rpc(
    session: aiohttp.ClientSession,
    rpc_urls: list[str],
    red_key: str,
    simbolo: str,
    _tipo_operacion: str = "deposito",
):
    req_timeout = aiohttp.ClientTimeout(total=7)
    for rpc_url in rpc_urls:
        try:
            payload_latest = {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}
            async with session.post(rpc_url, json=payload_latest, timeout=req_timeout) as resp:
                if resp.status != 200:
                    continue
                data_latest = await resp.json()
                hex_block = data_latest.get("result")
                if not hex_block:
                    continue
                block_num = int(hex_block, 16)

            for offset in range(0, 2):
                target_hex = hex(block_num - offset)
                payload_block = {
                    "jsonrpc": "2.0",
                    "method": "eth_getBlockByNumber",
                    "params": [target_hex, True],
                    "id": 2,
                }
                async with session.post(rpc_url, json=payload_block, timeout=req_timeout) as resp_blk:
                    if resp_blk.status != 200:
                        continue
                    blk_json = await resp_blk.json()
                    txs = (blk_json.get("result") or {}).get("transactions") or []
                    random.shuffle(txs)
                    for tx in txs[:30]:
                        tx_hash = tx.get("hash")
                        if not es_hash_valido(tx_hash, red_key):
                            continue
                        val_wei = int(tx.get("value") or "0x0", 16)
                        monto = round(val_wei / 1e18, 6)
                        if not _cumple_filtro_monto(monto, simbolo) or _hash_ya_publicado(tx_hash):
                            continue
                        return {
                            "hash": tx_hash,
                            "monto": monto,
                            "moneda": simbolo,
                            "red": REDES_INFO[red_key]["nombre"],
                            "explorer": f"{REDES_INFO[red_key]['explorer']}{tx_hash}",
                        }
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            detalle_err = str(e).strip() or type(e).__name__
            print(f"Aviso RPC {red_key} ({rpc_url}): {detalle_err}", flush=True)
    return None


async def obtener_tx_real_bsc(session: aiohttp.ClientSession, _address: str, tipo_operacion: str = "deposito"):
    rpcs_bsc = [
        "https://bsc-rpc.publicnode.com",
        "https://bsc-dataseed.binance.org/",
        "https://bsc-dataseed1.defibit.io/",
    ]
    return await _obtener_tx_evm_rpc(session, rpcs_bsc, "BSC", "BNB", tipo_operacion)


async def obtener_tx_real_eth(session: aiohttp.ClientSession, _address: str, tipo_operacion: str = "deposito"):
    rpcs_eth = [
        "https://ethereum-rpc.publicnode.com",
        "https://cloudflare-eth.com",
    ]
    return await _obtener_tx_evm_rpc(session, rpcs_eth, "ETH", "ETH", tipo_operacion)


async def obtener_tx_real_sol(session: aiohttp.ClientSession, address: str, _tipo_operacion: str = "deposito"):
    if not address or address == "TuDireccionSolanaAqui":
        return None
    rpcs_sol = [
        "https://solana-rpc.publicnode.com",
        "https://api.mainnet-beta.solana.com",
    ]
    req_timeout = aiohttp.ClientTimeout(total=8)
    for rpc_url in rpcs_sol:
        try:
            payload_sigs = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [address, {"limit": 20}],
            }
            async with session.post(rpc_url, json=payload_sigs, timeout=req_timeout) as resp:
                if resp.status != 200:
                    continue
                data_sigs = await resp.json()
                sigs = data_sigs.get("result") or []
                random.shuffle(sigs)
                for item in sigs:
                    if not isinstance(item, dict) or item.get("err"):
                        continue
                    sig = item.get("signature")
                    if not es_hash_valido(sig, "SOL") or _hash_ya_publicado(sig):
                        continue
                    payload_tx = {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "getTransaction",
                        "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
                    }
                    async with session.post(rpc_url, json=payload_tx, timeout=req_timeout) as resp_tx:
                        if resp_tx.status != 200:
                            continue
                        tx_json = await resp_tx.json()
                        meta = (tx_json.get("result") or {}).get("meta") or {}
                        pre_bal = meta.get("preBalances") or []
                        post_bal = meta.get("postBalances") or []
                        if pre_bal and post_bal:
                            diff_lamports = abs(int(post_bal[0]) - int(pre_bal[0]))
                            monto_sol = round(diff_lamports / 1e9, 4)
                            if _cumple_filtro_monto(monto_sol, "SOL"):
                                return {
                                    "hash": sig,
                                    "monto": monto_sol,
                                    "moneda": "SOL",
                                    "red": REDES_INFO["SOL"]["nombre"],
                                    "explorer": f"{REDES_INFO['SOL']['explorer']}{sig}",
                                }
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            detalle_err = str(e).strip()
            if detalle_err:
                print(f"Aviso RPC SOL ({rpc_url}): {detalle_err}", flush=True)
    return None


def calcular_retiro_anticipado(capital_base: float, moneda: str):
    capital = max(float(capital_base or 0.0), 0.0)
    moneda_upper = (moneda or "USD").upper()
    comision = COMISION_ANTICIPADA_POR_MONEDA.get(moneda_upper, 0.2)
    neto = round(max(capital - comision, 0.0), 6)
    return {
        "capital_base": round(capital, 6),
        "moneda": moneda_upper,
        "comision_red": comision,
        "neto_a_recibir": neto,
    }


async def obtener_comprobante_multired(tipo_operacion: str = "retiro"):
    prioritarias = ["TRON", "TON", "SOL", "BTC"]
    secundarias = ["BSC", "ETH"]
    random.shuffle(prioritarias)
    random.shuffle(secundarias)
    orden_redes = prioritarias + secundarias

    consultores = {
        "TRON": obtener_tx_real_tron,
        "TON": obtener_tx_real_ton,
        "SOL": obtener_tx_real_sol,
        "BTC": obtener_tx_real_btc,
        "BSC": obtener_tx_real_bsc,
        "ETH": obtener_tx_real_eth,
    }

    sin_resultado = []
    connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector) as session:
        for red_key in orden_redes:
            fn = consultores.get(red_key)
            addr = WALLETS_OFICIALES.get(red_key, "")
            if not fn:
                continue
            try:
                comp = await fn(session, addr, tipo_operacion)
                if comp and comp.get("hash") and not _hash_ya_publicado(comp["hash"]):
                    return comp
                sin_resultado.append(red_key)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                sin_resultado.append(f"{red_key}(err)")
                detalle_err = str(e).strip() or type(e).__name__
                print(f"Error consultando blockchain {red_key}: {detalle_err}", flush=True)

    print(f"Multired sin tx válida en ciclo ({tipo_operacion}): {', '.join(sin_resultado)}", flush=True)
    return None


async def tarea_comprobaciones_canal(bot):
    await asyncio.sleep(10)
    try:
        while True:
            try:
                if CHANNEL_ID and CHANNEL_ID != "-1001234567890":
                    cantidad_envios = random.randint(1, 2)
                    enviados = 0

                    for _ in range(cantidad_envios):
                        tipo_op = random.choice(["deposito", "retiro"])
                        comp = await obtener_comprobante_multired(tipo_op)
                        if comp and comp.get("hash") and not _hash_ya_publicado(comp["hash"]):
                            usuario = generar_usuario_ficticio()
                            etiqueta_tipo = "Depósito" if tipo_op == "deposito" else "Retiro"
                            texto = (
                                f"📢 <b>Aviso de {esc(etiqueta_tipo)} (Actividad de Red)</b>\n\n"
                                f"• <b>Referencia:</b> <code>{esc(usuario)}</code>\n"
                                f"• <b>Monto:</b> <code>{esc(comp['monto'])} {esc(comp['moneda'])}</code>\n"
                                f"• <b>Red:</b> <code>{esc(comp['red'])}</code>\n"
                                f"• <b>Hash:</b> <code>{esc(comp['hash'])}</code>\n"
                                f"• <b>Explorador:</b> {esc(comp['explorer'])}"
                            )
                            try:
                                await bot.send_message(
                                    chat_id=CHANNEL_ID,
                                    text=texto,
                                    parse_mode="HTML",
                                    disable_web_page_preview=True,
                                )
                                nuevo_fondo = await db_exec(
                                    _registrar_hash_y_ajustar_fondo,
                                    comp["hash"],
                                    comp["red"],
                                    comp["moneda"],
                                    comp["monto"],
                                    tipo_op,
                                    write=True,
                                )
                                enviados += 1
                                print(
                                    f"Fondo actualizado tras {tipo_op} ({comp['monto']} {comp['moneda']}): ${nuevo_fondo:,.2f} USD",
                                    flush=True,
                                )
                            except TelegramError as te:
                                print(f"Error enviando comprobante al canal: {te}", flush=True)
                            await asyncio.sleep(2.0)

                    print(f"Ciclo comprobaciones: enviados {enviados}/{cantidad_envios}", flush=True)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"Error en tarea_comprobaciones_canal: {e}", flush=True)

            espera_segundos = random.randint(900, 2400)
            print(f"Próximo ciclo de comprobantes en {espera_segundos // 60} min ({espera_segundos}s)", flush=True)
            await asyncio.sleep(espera_segundos)
    except asyncio.CancelledError:
        print("Tarea de comprobaciones cancelada limpiamente.", flush=True)
        raise


async def tarea_keep_alive():
    if not SELF_PING_URL:
        print("Keep-alive interno omitido: no hay SELF_PING_URL ni RENDER_EXTERNAL_URL.", flush=True)
        return

    await asyncio.sleep(20)
    timeout = aiohttp.ClientTimeout(total=8)
    try:
        while True:
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(SELF_PING_URL) as resp:
                        if resp.status != 200:
                            print(f"Keep-alive respondió con status {resp.status}", flush=True)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                detalle_err = str(e).strip() or type(e).__name__
                print(f"Aviso en keep-alive interno: {detalle_err}", flush=True)

            await asyncio.sleep(540)
    except asyncio.CancelledError:
        print("Tarea keep-alive cancelada limpiamente.", flush=True)
        raise


# --- TECLADOS INLINE CORTOS Y CLAROS ---
def obtener_menu_idiomas():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es"),
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
        ]
    ])


def obtener_menu_principal(idioma="es", user_id: int = 0):
    if idioma == "en":
        filas = [
            [
                InlineKeyboardButton("💰 Balance", callback_data="btn_saldo"),
                InlineKeyboardButton("🏦 Pool", callback_data="btn_liquidez"),
            ],
            [
                InlineKeyboardButton("📈 Invest", callback_data="btn_planes"),
                InlineKeyboardButton("💳 Wallets", callback_data="btn_depositar"),
            ],
            [
                InlineKeyboardButton("📜 History", callback_data="btn_historial"),
                InlineKeyboardButton("👥 Referrals", callback_data="btn_referidos"),
            ],
            [
                InlineKeyboardButton("💸 Withdraw", callback_data="btn_retirar"),
                InlineKeyboardButton("🎧 Support", callback_data="btn_soporte"),
            ],
            [
                InlineKeyboardButton("📢 Proofs", url=LINK_CANAL),
                InlineKeyboardButton("🌐 Language", callback_data="btn_cambiar_idioma"),
            ],
        ]
    else:
        filas = [
            [
                InlineKeyboardButton("💰 Mi Saldo", callback_data="btn_saldo"),
                InlineKeyboardButton("🏦 Liquidez", callback_data="btn_liquidez"),
            ],
            [
                InlineKeyboardButton("📈 Invertir", callback_data="btn_planes"),
                InlineKeyboardButton("💳 Wallets", callback_data="btn_depositar"),
            ],
            [
                InlineKeyboardButton("📜 Historial", callback_data="btn_historial"),
                InlineKeyboardButton("👥 Referidos", callback_data="btn_referidos"),
            ],
            [
                InlineKeyboardButton("💸 Retirar", callback_data="btn_retirar"),
                InlineKeyboardButton("🎧 Soporte", callback_data="btn_soporte"),
            ],
            [
                InlineKeyboardButton("📢 Pagos", url=LINK_CANAL),
                InlineKeyboardButton("🌐 Idioma", callback_data="btn_cambiar_idioma"),
            ],
        ]

    if user_id and user_id == ADMIN_ID:
        filas.append([
            InlineKeyboardButton("🔐 Panel Fondo (Admin)", callback_data="btn_admin_fondo")
        ])

    return InlineKeyboardMarkup(filas)


def teclado_tras_direccion(idioma="es"):
    volver_txt = "⬅️ Menú" if idioma == "es" else "⬅️ Menu"
    volver_cb = "lang_es" if idioma == "es" else "lang_en"
    enviar_txt = "📩 Enviar Hash / TXID" if idioma == "es" else "📩 Send Hash / TXID"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(enviar_txt, callback_data="enviar_hash_pago")],
        [InlineKeyboardButton(volver_txt, callback_data=volver_cb)],
    ])


def _filas_redes_tokens(prefix_cb: str, idioma="es"):
    etiquetas = {
        "TRON": "TRON · USDT / TRX / TRC20",
        "TON": "TON · USDT / TON / GRAM",
        "BSC": "BSC · USDT / BNB / BEP20",
        "ETH": "ETH · USDT / ETH / ERC20",
        "BTC": "BTC · BTC / Tokens",
        "SOL": "SOL · USDT / SOL / SPL",
    }
    orden = ["TRON", "TON", "BSC", "ETH", "BTC", "SOL"]
    return [[InlineKeyboardButton(etiquetas[r], callback_data=f"{prefix_cb}{r}")] for r in orden]


def teclado_wallets_accion(idioma="es"):
    volver_txt = "⬅️ Menú" if idioma == "es" else "⬅️ Menu"
    volver_cb = "lang_es" if idioma == "es" else "lang_en"
    invertir_txt = "📈 Elegir Plan de Inversión" if idioma == "es" else "📈 Choose Investment Plan"
    enviar_txt = "📩 Enviar Hash / TXID" if idioma == "es" else "📩 Send Hash / TXID"
    filas = _filas_redes_tokens("red_", idioma)
    filas.append([InlineKeyboardButton(invertir_txt, callback_data="btn_planes")])
    filas.append([InlineKeyboardButton(enviar_txt, callback_data="enviar_hash_pago")])
    filas.append([InlineKeyboardButton(volver_txt, callback_data=volver_cb)])
    return InlineKeyboardMarkup(filas)


def teclado_planes_y_redes(idioma="es"):
    filas = []
    for plan_key, plan in PLANES_INVERSION.items():
        filas.append([
            InlineKeyboardButton(plan["boton"], callback_data=f"sel_plan_{plan_key}")
        ])
    filas.extend(_filas_redes_tokens("red_", idioma))
    volver_txt = "⬅️ Menú" if idioma == "es" else "⬅️ Menu"
    volver_cb = "lang_es" if idioma == "es" else "lang_en"
    filas.append([InlineKeyboardButton(volver_txt, callback_data=volver_cb)])
    return InlineKeyboardMarkup(filas)


def teclado_reinversion(plan_id: str, idioma="es"):
    if idioma == "en":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("♻️ Auto-Reinvest: ON", callback_data=f"reinv_{plan_id}_1")],
            [InlineKeyboardButton("💵 Auto-Reinvest: OFF", callback_data=f"reinv_{plan_id}_0")],
            [InlineKeyboardButton("⬅️ Back", callback_data="btn_planes")],
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("♻️ Reinversión automática: Sí", callback_data=f"reinv_{plan_id}_1")],
        [InlineKeyboardButton("💵 Reinversión automática: No", callback_data=f"reinv_{plan_id}_0")],
        [InlineKeyboardButton("⬅️ Volver", callback_data="btn_planes")],
    ])


def teclado_montos_inversion(plan_id: str, idioma="es"):
    plan = PLANES_INVERSION.get(plan_id, PLANES_INVERSION["1"])
    sugeridos = [0.5, 1, 5, 10, 50, 100]
    validos = [m for m in sugeridos if plan["min"] <= m <= plan["max"]]
    if not validos:
        validos = [0.5]

    filas = []
    fila_actual = []
    for m in validos:
        etiqueta = f"{m:g} USD"
        fila_actual.append(InlineKeyboardButton(etiqueta, callback_data=f"monto_{plan_id}_{m}"))
        if len(fila_actual) == 2:
            filas.append(fila_actual)
            fila_actual = []
    if fila_actual:
        filas.append(fila_actual)

    txt_otro = "✏️ Escribir otro monto" if idioma == "es" else "✏️ Custom amount"
    txt_volver = "⬅️ Volver" if idioma == "es" else "⬅️ Back"
    filas.append([InlineKeyboardButton(txt_otro, callback_data=f"otro_monto_{plan_id}")])
    filas.append([InlineKeyboardButton(txt_volver, callback_data=f"sel_plan_{plan_id}")])
    return InlineKeyboardMarkup(filas)


def teclado_redes_inversion(plan_id: str, monto: float, idioma="es"):
    filas = _filas_redes_tokens(f"invred_{plan_id}_{monto}_", idioma)
    filas.append([
        InlineKeyboardButton(
            "⬅️ Cambiar monto" if idioma == "es" else "⬅️ Change amount",
            callback_data=f"reinv_{plan_id}_0",
        )
    ])
    return InlineKeyboardMarkup(filas)


def teclado_confirmar_retiro_anticipado(idioma="es"):
    if idioma == "en":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Confirm Withdrawal", callback_data="confirm_retiro_anticipado")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_retiro_anticipado")],
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirmar Retiro", callback_data="confirm_retiro_anticipado")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="cancel_retiro_anticipado")],
    ])


def teclado_admin_hash(user_id: int, sugerido_monto: float = None, sugerido_red: str = "TRON"):
    filas = []
    if sugerido_monto and sugerido_monto >= MIN_MONTO_INVERSION:
        filas.append([
            InlineKeyboardButton(
                f"✅ Aprobar {sugerido_monto:g} USD ({sugerido_red})",
                callback_data=f"adm_apr_{user_id}_{sugerido_monto:g}_USD_{sugerido_red}",
            )
        ])
    filas.append([
        InlineKeyboardButton("💵 0.5 USD", callback_data=f"adm_apr_{user_id}_0.5_USD_{sugerido_red}"),
        InlineKeyboardButton("💵 1 USD", callback_data=f"adm_apr_{user_id}_1_USD_{sugerido_red}"),
        InlineKeyboardButton("💵 5 USD", callback_data=f"adm_apr_{user_id}_5_USD_{sugerido_red}"),
    ])
    filas.append([
        InlineKeyboardButton("❌ Rechazar", callback_data=f"adm_rec_{user_id}"),
    ])
    return InlineKeyboardMarkup(filas)


def texto_planes_listado():
    bloques = []
    for _, p in PLANES_INVERSION.items():
        if p["min"] == 0.5 and p["max"] == 1000.0:
            rango = "0.5–1,000 USD"
        else:
            rango = f"{p['min']:g}–{p['max']:g} USD"

        emoji = p["boton"].split(" ")[0]

        if p["dias"] == 7:
            ganancia_txt = "0.7%"
        elif p["dias"] == 14:
            ganancia_txt = "~2.4% (1.2% semanal)"
        elif p["dias"] == 21:
            ganancia_txt = "~7.8% (2.6% semanal)"
        elif p["dias"] == 30:
            ganancia_txt = "~3.2% (0.8% semanal)"
        else:
            ganancia_txt = "0.5% cada 7 días"

        bloques.append(
            f"{esc(emoji)} <b>{esc(p['nombre'])}</b>\n"
            f"• Ganancia del ciclo: {esc(ganancia_txt)} · Rango: {esc(rango)}\n"
            f"• {esc(p['detalle'])}"
        )

    return (
        "📈 <b>Planes de Inversión (Desde 0.5 USD)</b>\n\n"
        "Toca un plan para continuar o elige una red abajo para depositar:\n\n"
        + "\n\n".join(bloques)
    )


def texto_wallets_deposito(idioma="es"):
    if idioma == "en":
        encabezado = "💳 <b>Official Deposit Wallets (Any Token Supported Per Network)</b>:\n\n"
        aviso = "⚠️ Tap a network below to see its address and send USDT or any supported token, or choose an investment plan."
    else:
        encabezado = "💳 <b>Direcciones Oficiales (Acepta USDT y Tokens de Cada Red)</b>:\n\n"
        aviso = "⚠️ Toca una red abajo para ver su dirección y enviar USDT o tokens compatibles, o entra a elegir tu plan."

    bloques = []
    for red_key, info in REDES_INFO.items():
        wallet = WALLETS_OFICIALES.get(red_key, "")
        monedas_str = " / ".join(info["monedas"])
        bloques.append(f"🔹 <b>{esc(info['nombre'])} ({esc(monedas_str)}):</b>\n<code>{esc(wallet)}</code>")
    return encabezado + "\n\n".join(bloques) + f"\n\n{esc(aviso)}"


def construir_mensaje_referidos(username_bot, user_id, idioma="es"):
    bot_user = username_bot or "TuBot"
    link_referido = f"https://t.me/{bot_user}?start={user_id}"
    enlace_html = f'<a href="{esc(link_referido)}">{esc(link_referido)}</a>'

    if idioma == "en":
        return (
            f"👥 <b>Invite &amp; Earn</b>\n\n"
            f"Tap your referral link to open the bot:\n"
            f"{enlace_html}\n\n"
            f"• Join bonus: <code>+{BONO_ENTRADA_REFERIDO_USD:g} USD</code>\n"
            f"• Multi-level commissions when your referrals invest\n"
            f"• <b>Plans (from 0.5 USD):</b>\n"
            f"  – Starter (7d - 0.7%): min 0.5 USD\n"
            f"  – Growth (14d - 1.2%/wk): min 0.5 USD\n"
            f"  – Pro / Elite (21d - 2.6%/wk): min 1 USD\n"
            f"  – Goal (30d - 0.8%/wk): min 0.5 USD\n"
            f"  – Flexible (no lock-up - 0.5%/7d): min 0.5 USD\n"
            f"• Min withdrawal: <code>0.5 USD</code> (with investment history)"
        )

    return (
        f"👥 <b>Invita y gana</b>\n\n"
        f"Toca tu enlace para abrir el bot:\n"
        f"{enlace_html}\n\n"
        f"• Bono por entrar: <code>+{BONO_ENTRADA_REFERIDO_USD:g} USD</code>\n"
        f"• Comisiones por niveles cuando invierten\n"
        f"• <b>Planes (desde 0.5 USD):</b>\n"
        f"  – Inicio (7d - 0.7%): mín. 0.5 USD\n"
        f"  – Crecimiento (14d - 1.2%/sem): mín. 0.5 USD\n"
        f"  – Pro / Élite (21d - 2.6%/sem): mín. 1 USD\n"
        f"  – Meta (30d - 0.8%/sem): mín. 0.5 USD\n"
        f"  – Flexible (sin plazo fijo - 0.5%/7d): mín. 0.5 USD\n"
        f"• Retiro mínimo: <code>0.5 USD</code> (con historial de inversión)"
    )


def _db_registrar_solicitud_sync(
    user_id: int,
    plan_id: str,
    cantidad: float,
    red_solicitada: str,
    reinv_flag: int,
):
    plan = PLANES_INVERSION[plan_id]
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO inversiones (
                user_id, plan_id, modalidad, monto, moneda, red,
                reinversion_auto, dias_plazo, fecha_inicio, estado
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pendiente_pago')
            """,
            (
                user_id,
                plan_id,
                plan["modalidad"],
                round(float(cantidad), 4),
                "USD",
                red_solicitada,
                reinv_flag,
                plan["dias"],
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        cursor.execute(
            "UPDATE usuarios SET esperando_monto = 0, esperando_hash = 1, en_soporte = 0 WHERE user_id = ?",
            (user_id,),
        )


async def registrar_solicitud_inversion(
    user_id: int,
    plan_id: str,
    cantidad: float,
    red_solicitada: str,
    reinv_flag: int,
):
    plan = PLANES_INVERSION[plan_id]
    wallet = WALLETS_OFICIALES[red_solicitada]
    tokens_red = " / ".join(REDES_INFO[red_solicitada]["monedas"])
    await db_exec(
        _db_registrar_solicitud_sync,
        user_id, plan_id, cantidad, red_solicitada, reinv_flag,
        write=True,
    )
    return (
        f"✅ <b>Listo, registramos tu solicitud</b>\n\n"
        f"• <b>Plan:</b> {esc(plan['nombre'])}\n"
        f"• <b>Monto:</b> <code>{cantidad:g} USD</code>\n"
        f"• <b>Red:</b> <code>{esc(red_solicitada)}</code> ({esc(tokens_red)})\n"
        f"• <b>Reinversión automática:</b> <code>{'Sí' if reinv_flag else 'No'}</code>\n\n"
        f"💳 <b>Envía tu depósito a esta dirección:</b>\n<code>{esc(wallet)}</code>\n\n"
        f"📩 <b>Cuando hagas la transferencia, pega aquí el Hash / TXID</b> para revisarlo y activarla."
    )


def _db_start_sync(user_id: int, first_name: str, patrocinador_id):
    notificar_patrocinador = False
    bono_otorgado = False
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, patrocinador_id, idioma FROM usuarios WHERE user_id = ?", (user_id,))
        existe = cursor.fetchone()
        idioma = existe[2] if existe and existe[2] else "es"

        if not existe:
            pat_valido = patrocinador_id if (patrocinador_id and patrocinador_id != user_id) else None
            bono_inicial = BONO_ENTRADA_REFERIDO_USD if pat_valido else 0.0
            cursor.execute(
                "INSERT INTO usuarios (user_id, nombre, patrocinador_id, ganancias_referidos, idioma) VALUES (?, ?, ?, ?, ?)",
                (user_id, first_name, pat_valido, bono_inicial, "es"),
            )
            if pat_valido:
                notificar_patrocinador = True
                bono_otorgado = True
        else:
            cursor.execute(
                "UPDATE usuarios SET nombre = ? WHERE user_id = ?",
                (first_name, user_id),
            )

        cursor.execute(
            "UPDATE usuarios SET esperando_monto = 0, esperando_hash = 0, en_soporte = 0 WHERE user_id = ?",
            (user_id,),
        )
    return notificar_patrocinador, bono_otorgado, idioma


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    args = context.args if context and context.args else []
    patrocinador_id = int(args[0]) if args and args[0].isdigit() else None

    notificar_patrocinador, bono_otorgado, _ = await db_exec(
        _db_start_sync, user.id, user.first_name, patrocinador_id, write=True
    )

    if notificar_patrocinador and patrocinador_id:
        try:
            await context.bot.send_message(
                chat_id=patrocinador_id,
                text=(
                    f"🎉 <b>¡Entró un nuevo referido!</b>\n\n"
                    f"<b>{esc(user.first_name)}</b> se sumó con tu enlace."
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            print(f"No se pudo notificar al patrocinador: {e}", flush=True)

    texto = "🌐 <b>Bienvenido / Welcome</b>\n\nElige tu idioma / Select your language:"
    if bono_otorgado:
        texto += f"\n\n🎁 <b>Bono de bienvenida por referido:</b> <code>+{BONO_ENTRADA_REFERIDO_USD:g} USD</code> sumados a tu saldo de referidos."

    await editar_o_responder_texto(update, texto, reply_markup=obtener_menu_idiomas(), parse_mode="HTML")


def _db_obtener_idioma_sync(user_id: int) -> str:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT idioma FROM usuarios WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
    return row[0] if row and row[0] else "es"


def _db_set_idioma_sync(user_id: int, first_name: str, nuevo_idioma: str):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO usuarios (user_id, nombre, idioma) VALUES (?, ?, ?)",
            (user_id, first_name, nuevo_idioma),
        )
        cursor.execute(
            "UPDATE usuarios SET nombre = ?, idioma = ?, esperando_monto = 0, esperando_hash = 0, en_soporte = 0 WHERE user_id = ?",
            (first_name, nuevo_idioma, user_id),
        )


def _db_set_estado_sync(user_id: int, esperando_monto=0, esperando_hash=0, en_soporte=0):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE usuarios SET esperando_monto = ?, esperando_hash = ?, en_soporte = ? WHERE user_id = ?",
            (esperando_monto, esperando_hash, en_soporte, user_id),
        )


def _db_obtener_saldo_sync(user_id: int):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT deposito_activo, moneda_deposito, red_deposito, fecha_deposito, ganancias_referidos FROM usuarios WHERE user_id = ?",
            (user_id,),
        )
        return cursor.fetchone()


def _db_obtener_liquidez_sync():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT fondo_actual, ultima_actualizacion FROM liquidez_global WHERE id = 1")
        row = cursor.fetchone()
    if not row:
        return FONDO_INICIAL_USD, None
    fondo = max(float(row[0] or FONDO_INICIAL_USD), PISO_FONDO_USD)
    return fondo, row[1]


def _db_obtener_historial_sync(user_id: int):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT plan_id, monto, moneda, red, dias_plazo, fecha_inicio, estado
            FROM inversiones
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 10
            """,
            (user_id,),
        )
        return cursor.fetchall()


def _db_retiro_consultar_sync(user_id: int):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT deposito_activo, moneda_deposito, red_deposito, ganancias_referidos FROM usuarios WHERE user_id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        cursor.execute(
            "SELECT 1 FROM inversiones WHERE user_id = ? AND estado != 'rechazada' LIMIT 1",
            (user_id,),
        )
        tiene_historial = cursor.fetchone() is not None
    return row, tiene_historial


def _db_retiro_confirmar_sync(user_id: int):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT deposito_activo, moneda_deposito, red_deposito, ganancias_referidos FROM usuarios WHERE user_id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        deposito_activo = float(row[0]) if row and row[0] else 0.0
        moneda = "USD"
        red = row[2] if row and row[2] else "TRON"
        ganancias_ref = float(row[3]) if row and row[3] else 0.0

        cursor.execute(
            "SELECT 1 FROM inversiones WHERE user_id = ? AND estado != 'rechazada' LIMIT 1",
            (user_id,),
        )
        tiene_historial = cursor.fetchone() is not None
        if not tiene_historial:
            return None, moneda, red, "sin_historial"

        retira_capital = deposito_activo > 0
        saldo_retirable = deposito_activo if retira_capital else ganancias_ref
        if saldo_retirable < MIN_MONTO_RETIRO:
            return None, moneda, red, "minimo"

        calc = calcular_retiro_anticipado(saldo_retirable, moneda)
        calc["tipo_origen"] = "capital" if retira_capital else "referidos"
        if retira_capital:
            cursor.execute(
                "UPDATE usuarios SET deposito_activo = 0, fecha_deposito = NULL WHERE user_id = ?",
                (user_id,),
            )
            cursor.execute(
                "UPDATE inversiones SET estado = 'retirado_anticipado' WHERE user_id = ? AND estado = 'activa'",
                (user_id,),
            )
        else:
            cursor.execute(
                "UPDATE usuarios SET ganancias_referidos = 0 WHERE user_id = ?",
                (user_id,),
            )
        return calc, moneda, red, "ok"


async def procesar_retiro_anticipado(update: Update, context: ContextTypes.DEFAULT_TYPE, idioma: str):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    if data == "btn_retirar":
        row, tiene_historial = await db_exec(_db_retiro_consultar_sync, user_id)
        deposito_activo = float(row[0]) if row and row[0] else 0.0
        moneda = "USD"
        red = row[2] if row and row[2] else "TRON"
        ganancias_ref = float(row[3]) if row and row[3] else 0.0

        if not tiene_historial:
            texto = (
                "🏦 <b>Retiros:</b> Para retirar necesitas tener historial de inversión (desde <code>0.5 USD</code>)."
                if idioma == "es"
                else "🏦 <b>Withdrawals:</b> You need investment history (from <code>0.5 USD</code>) to request a withdrawal."
            )
            await editar_o_responder_texto(
                update, texto, reply_markup=obtener_menu_principal(idioma, user_id), parse_mode="HTML"
            )
            return

        retira_capital = deposito_activo > 0
        saldo_retirable = deposito_activo if retira_capital else ganancias_ref
        if saldo_retirable < MIN_MONTO_RETIRO:
            texto = (
                f"🏦 <b>Retiros:</b> El mínimo para retirar es <code>{MIN_MONTO_RETIRO:g} USD</code> y ahora tienes <code>{saldo_retirable:g} USD</code> disponibles."
                if idioma == "es"
                else f"🏦 <b>Withdrawals:</b> Minimum withdrawal is <code>{MIN_MONTO_RETIRO:g} USD</code> and you currently have <code>{saldo_retirable:g} USD</code> available."
            )
            await editar_o_responder_texto(
                update, texto, reply_markup=obtener_menu_principal(idioma, user_id), parse_mode="HTML"
            )
            return

        calc = calcular_retiro_anticipado(saldo_retirable, moneda)
        if idioma == "en":
            nota_origen = (
                "• <b>Early Exit:</b> If withdrawing active capital, accrued profits are forfeited."
                if retira_capital
                else "• <b>Source:</b> Referral rewards balance."
            )
            texto = (
                f"⚠️ <b>Withdrawal Summary (Min {MIN_MONTO_RETIRO:g} USD)</b>\n\n"
                f"• <b>Available:</b> <code>{calc['capital_base']} USD</code> ({esc(red)})\n"
                f"{nota_origen}\n"
                f"• <b>Network Fee:</b> <code>-{calc['comision_red']} USD</code>\n"
                f"• <b>Net to Receive:</b> <code>{calc['neto_a_recibir']} USD</code>"
            )
        else:
            nota_origen = (
                "• <b>Nota:</b> Si retiras capital activo antes de tiempo, pierdes las ganancias acumuladas."
                if retira_capital
                else "• <b>Origen:</b> Saldo acumulado por referidos."
            )
            texto = (
                f"⚠️ <b>Resumen de Retiro (Mínimo {MIN_MONTO_RETIRO:g} USD)</b>\n\n"
                f"• <b>Disponible:</b> <code>{calc['capital_base']} USD</code> ({esc(red)})\n"
                f"{nota_origen}\n"
                f"• <b>Comisión de red:</b> <code>-{calc['comision_red']} USD</code>\n"
                f"• <b>Neto a recibir:</b> <code>{calc['neto_a_recibir']} USD</code>"
            )
        await editar_o_responder_texto(
            update, texto, reply_markup=teclado_confirmar_retiro_anticipado(idioma), parse_mode="HTML"
        )
        return

    if data == "confirm_retiro_anticipado":
        calc, _moneda, red, motivo = await db_exec(_db_retiro_confirmar_sync, user_id, write=True)
        if not calc:
            msg_err = (
                "⚠️ Necesitas historial de inversión para retirar."
                if motivo == "sin_historial"
                else f"⚠️ El retiro mínimo es {MIN_MONTO_RETIRO:g} USD."
            )
            await editar_o_responder_texto(
                update, esc(msg_err), reply_markup=obtener_menu_principal(idioma, user_id), parse_mode="HTML"
            )
            return

        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"💸 <b>Retiro Solicitado</b>\n\n"
                    f"• <b>Usuario ID:</b> <code>{user_id}</code>\n"
                    f"• <b>Origen:</b> <code>{esc(calc.get('tipo_origen', 'saldo'))}</code>\n"
                    f"• <b>Red:</b> <code>{esc(red)}</code>\n"
                    f"• <b>Monto Base:</b> <code>{calc['capital_base']} USD</code>\n"
                    f"• <b>Comisión Red:</b> <code>-{calc['comision_red']} USD</code>\n"
                    f"• <b>Neto a Enviar:</b> <code>{calc['neto_a_recibir']} USD</code>"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            print(f"Error notificando retiro al admin: {e}", flush=True)

        texto_ok = (
            f"✅ <b>Listo, registramos tu retiro</b>\n\n"
            f"• <b>Neto a recibir:</b> <code>{calc['neto_a_recibir']} USD</code>\n"
            f"• <b>Comisión de red:</b> <code>-{calc['comision_red']} USD</code>"
            if idioma == "es"
            else (
                f"✅ <b>Withdrawal Recorded</b>\n\n"
                f"• <b>Net to Receive:</b> <code>{calc['neto_a_recibir']} USD</code>\n"
                f"• <b>Network Fee:</b> <code>-{calc['comision_red']} USD</code>"
            )
        )
        await editar_o_responder_texto(
            update, texto_ok, reply_markup=obtener_menu_principal(idioma, user_id), parse_mode="HTML"
        )
        return

    if data == "cancel_retiro_anticipado":
        texto_cancel = (
            "👍 <b>Retiro cancelado.</b> Todo sigue igual en tu cuenta."
            if idioma == "es"
            else "👍 <b>Withdrawal cancelled.</b> Your balance and investments remain unchanged."
        )
        await editar_o_responder_texto(
            update, texto_cancel, reply_markup=obtener_menu_principal(idioma, user_id), parse_mode="HTML"
        )


def _db_aprobar_deposito_sync(id_usuario: str, monto: float, moneda: str, red: str, tx_hash):
    uid_int = int(id_usuario)
    monto_limpio = round(float(monto), 4)
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    notificaciones = []

    with get_db_connection() as conn:
        cursor = conn.cursor()

        if tx_hash:
            cursor.execute(
                "SELECT 1 FROM comprobantes_verificados WHERE tx_hash = ? AND tipo = 'aprobado_admin' LIMIT 1",
                (tx_hash,),
            )
            if cursor.fetchone():
                return [], "duplicado_hash", None

        cursor.execute(
            """
            SELECT id, plan_id, modalidad, dias_plazo, reinversion_auto
            FROM inversiones
            WHERE user_id = ? AND estado = 'pendiente_pago'
            ORDER BY id DESC LIMIT 1
            """,
            (uid_int,),
        )
        solicitud = cursor.fetchone()
        if solicitud:
            inv_id, plan_id_sol, mod_sol, dias_sol, reinv_sol = solicitud
            plan_meta = PLANES_INVERSION.get(str(plan_id_sol), PLANES_INVERSION["1"])
            plan_id_act = str(plan_id_sol) if str(plan_id_sol) in PLANES_INVERSION else "1"
            modalidad_act = mod_sol or plan_meta["modalidad"]
            dias_act = int(dias_sol if dias_sol is not None else plan_meta["dias"])
            reinv_act = int(reinv_sol or 0)
            cursor.execute(
                """
                UPDATE inversiones
                SET plan_id = ?, modalidad = ?, monto = ?, moneda = ?, red = ?,
                    reinversion_auto = ?, dias_plazo = ?, fecha_inicio = ?, estado = 'activa'
                WHERE id = ? AND estado = 'pendiente_pago'
                """,
                (plan_id_act, modalidad_act, monto_limpio, moneda, red, reinv_act, dias_act, fecha_actual, inv_id),
            )
        else:
            plan_meta = PLANES_INVERSION["1"]
            cursor.execute(
                """
                INSERT INTO inversiones (
                    user_id, plan_id, modalidad, monto, moneda, red,
                    reinversion_auto, dias_plazo, fecha_inicio, estado
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'activa')
                """,
                (uid_int, "1", plan_meta["modalidad"], monto_limpio, moneda, red, 0, plan_meta["dias"], fecha_actual),
            )

        cursor.execute(
            "INSERT OR IGNORE INTO usuarios (user_id, nombre, idioma) VALUES (?, ?, ?)",
            (uid_int, f"Usuario {uid_int}", "es"),
        )
        cursor.execute(
            "UPDATE usuarios SET deposito_activo = ROUND(deposito_activo + ?, 4), moneda_deposito = ?, red_deposito = ?, fecha_deposito = ? WHERE user_id = ?",
            (monto_limpio, moneda, red, fecha_actual, uid_int),
        )

        if tx_hash:
            cursor.execute(
                "INSERT OR IGNORE INTO comprobantes_verificados (tx_hash, red, moneda, monto, tipo, fecha) VALUES (?, ?, ?, ?, ?, ?)",
                (tx_hash, red, moneda, monto_limpio, "aprobado_admin", fecha_actual),
            )

        porcentajes_niveles = [0.03, 0.02, 0.01, 0.005]
        patrocinador_actual = uid_int
        for nivel, porcentaje in enumerate(porcentajes_niveles, start=1):
            cursor.execute(
                "SELECT patrocinador_id FROM usuarios WHERE user_id = ?",
                (patrocinador_actual,),
            )
            resultado = cursor.fetchone()
            if not resultado or not resultado[0]:
                break
            patrocinador_id = resultado[0]
            comision = round(monto_limpio * porcentaje, 6)
            cursor.execute(
                "UPDATE usuarios SET ganancias_referidos = ROUND(ganancias_referidos + ?, 6) WHERE user_id = ?",
                (comision, patrocinador_id),
            )
            notificaciones.append((
                patrocinador_id,
                f"🎁 <b>¡Comisión por Inversión en tu Red! (Nivel {nivel})</b>\n\n"
                f"• Sumaste: <b>{comision:.4f} {esc(moneda)}</b> ({porcentaje*100:g}%).",
            ))
            patrocinador_actual = patrocinador_id

    return notificaciones, "ok", monto_limpio


def _db_rechazar_hash_sync(user_id: int):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE inversiones
            SET estado = 'rechazada'
            WHERE id = (
                SELECT id FROM inversiones
                WHERE user_id = ? AND estado = 'pendiente_pago'
                ORDER BY id DESC LIMIT 1
            )
            """,
            (user_id,),
        )


async def procesar_callback_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    if not user or user.id != ADMIN_ID:
        return

    data = query.data
    if data.startswith("adm_apr_"):
        partes = data.split("_")
        if len(partes) < 6:
            return
        target_user_id = partes[2]
        try:
            monto = float(partes[3])
        except ValueError:
            return
        moneda = partes[4]
        red = partes[5]

        notificaciones, estado_aprob, monto_final = await db_exec(
            _db_aprobar_deposito_sync, target_user_id, monto, moneda, red, None, write=True
        )
        if estado_aprob == "duplicado_hash":
            await editar_o_responder_texto(
                update,
                f"{esc(query.message.text or '')}\n\n⚠️ <b>Este comprobante ya había sido aprobado anteriormente.</b>",
                parse_mode="HTML",
            )
            return

        for pat_id, msg in notificaciones:
            try:
                await context.bot.send_message(chat_id=pat_id, text=msg, parse_mode="HTML")
            except Exception as e:
                print(f"No se pudo notificar al patrocinador {pat_id}: {e}", flush=True)

        try:
            await context.bot.send_message(
                chat_id=int(target_user_id),
                text=(
                    f"✅ <b>¡Tu depósito ya fue aprobado!</b>\n\n"
                    f"• <b>Monto acreditado:</b> <code>{monto_final:g} {esc(moneda)}</code>\n"
                    f"• <b>Red:</b> <code>{esc(red)}</code>\n"
                    f"• <b>Estado:</b> <code>Inversión activa</code>"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            print(f"No se pudo notificar al usuario {target_user_id}: {e}", flush=True)

        base_txt = query.message.text or ""
        await editar_o_responder_texto(
            update,
            f"{esc(base_txt)}\n\n✅ <b>APROBADO:</b> <code>{monto_final:g} {esc(moneda)}</code> ({esc(red)}) para <code>{esc(target_user_id)}</code>.",
            parse_mode="HTML",
        )
        return

    if data.startswith("adm_rec_"):
        target_user_id = int(data.split("_")[2])
        await db_exec(_db_rechazar_hash_sync, target_user_id, write=True)
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="❌ No pudimos validar ese comprobante. Si necesitas ayuda, toca <b>Soporte</b>.",
                parse_mode="HTML",
            )
        except Exception as e:
            print(f"No se pudo notificar rechazo al usuario {target_user_id}: {e}", flush=True)

        base_txt = query.message.text or ""
        await editar_o_responder_texto(
            update,
            f"{esc(base_txt)}\n\n❌ <b>RECHAZADO</b> para <code>{target_user_id}</code>.",
            parse_mode="HTML",
        )


async def boton_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    try:
        await query.answer()
    except Exception:
        pass

    data = query.data
    user = query.from_user

    if data == "btn_admin_fondo":
        await ver_fondo_admin(update, context)
        return

    if data.startswith("adm_"):
        await procesar_callback_admin(update, context)
        return

    if data == "btn_cambiar_idioma":
        await start(update, context)
        return

    if data.startswith("lang_"):
        nuevo_idioma = data.split("_")[1]
        await db_exec(_db_set_idioma_sync, user.id, user.first_name, nuevo_idioma, write=True)

        if nuevo_idioma == "en":
            texto = (
                f"🛡️ <b>Welcome to Invest Bot</b>\n\n"
                f"Hi, {esc(user.first_name)}. Start from 0.5 USD and deposit in TRON, TON, BSC, ETH, BTC, or SOL.\n\n"
                f"👇 <b>Choose what you want to do:</b>"
            )
        else:
            texto = (
                f"🛡️ <b>Bienvenido a Invierte Bot</b>\n\n"
                f"Hola, {esc(user.first_name)}. Empieza desde 0.5 USD y deposita en TRON, TON, BSC, ETH, BTC o SOL.\n\n"
                f"👇 <b>Elige qué deseas hacer:</b>"
            )

        await editar_o_responder_texto(
            update, texto, reply_markup=obtener_menu_principal(nuevo_idioma, user.id), parse_mode="HTML"
        )
        return

    idioma = await db_exec(_db_obtener_idioma_sync, user.id)

    if data in ("btn_retirar", "confirm_retiro_anticipado", "cancel_retiro_anticipado"):
        await procesar_retiro_anticipado(update, context, idioma)
        return

    if data == "btn_saldo":
        row = await db_exec(_db_obtener_saldo_sync, user.id)
        deposito = float(row[0]) if row and row[0] else 0.0
        red = row[2] if row and row[2] else "TRON"
        fecha_str = row[3] if row else None
        ganancia_ref = float(row[4]) if row and row[4] else 0.0

        dias = (
            (datetime.now() - datetime.strptime(fecha_str, "%Y-%m-%d %H:%M:%S")).days
            if (fecha_str and deposito > 0)
            else 0
        )
        if idioma == "en":
            texto = (
                f"💰 <b>Your Balance</b>\n\n"
                f"• Active Capital: <code>{deposito:g} USD</code> ({esc(red)})\n"
                f"• Days Active: <code>{dias}</code>\n"
                f"• Referral Balance: <code>{ganancia_ref:.2f} USD</code>\n"
                f"• Min Withdrawal: <code>{MIN_MONTO_RETIRO:g} USD</code> (requires investment history)"
            )
        else:
            texto = (
                f"💰 <b>Tu Saldo</b>\n\n"
                f"• Capital Activo: <code>{deposito:g} USD</code> ({esc(red)})\n"
                f"• Días Activo: <code>{dias}</code>\n"
                f"• Saldo por Referidos: <code>{ganancia_ref:.2f} USD</code>\n"
                f"• Retiro Mínimo: <code>{MIN_MONTO_RETIRO:g} USD</code> (teniendo historial de inversión)"
            )
        await editar_o_responder_texto(
            update, texto, reply_markup=obtener_menu_principal(idioma, user.id), parse_mode="HTML"
        )

    elif data == "btn_liquidez":
        fondo_actual, ultima_act = await db_exec(_db_obtener_liquidez_sync)
        act_linea = f"\n• <b>Último ajuste:</b> <code>{esc(ultima_act)}</code>" if ultima_act else ""
        if idioma == "en":
            texto = (
                f"🏦 <b>Liquidity Pool</b>\n\n"
                f"• <b>Current reserve:</b> <code>${fondo_actual:,.2f} USD</code>\n"
                f"• <b>Supported networks:</b> TRON, TON, BSC, ETH, BTC & SOL (USDT and compatible tokens)\n"
                f"• <b>Min investment / withdrawal:</b> <code>0.5 USD</code>{act_linea}"
            )
        else:
            texto = (
                f"🏦 <b>Fondo de Liquidez</b>\n\n"
                f"• <b>Reserva actual:</b> <code>${fondo_actual:,.2f} USD</code>\n"
                f"• <b>Redes disponibles:</b> TRON, TON, BSC, ETH, BTC y SOL (USDT y tokens compatibles)\n"
                f"• <b>Mínimo de inversión y retiro:</b> <code>0.5 USD</code>{act_linea}"
            )
        await editar_o_responder_texto(
            update, texto, reply_markup=obtener_menu_principal(idioma, user.id), parse_mode="HTML"
        )

    elif data == "btn_historial":
        filas = await db_exec(_db_obtener_historial_sync, user.id)
        if not filas:
            texto = (
                "📜 <b>Historial de Inversiones</b>\n\nTodavía no tienes inversiones registradas."
                if idioma == "es"
                else "📜 <b>Investment History</b>\n\nYou don't have any investments recorded yet."
            )
        else:
            lineas = []
            for plan_id, monto, _moneda, red, dias, fecha_ini, estado in filas:
                nombre_plan = (PLANES_INVERSION.get(str(plan_id)) or {}).get("nombre", f"Plan {plan_id}")
                fecha_corta = (fecha_ini or "")[:10]
                lineas.append(
                    f"• <b>{esc(nombre_plan)}</b> — <code>{float(monto):g} USD</code> ({esc(red)})\n"
                    f"  Plazo: <code>{dias}d</code> | Estado: <code>{esc(estado)}</code> | Fecha: <code>{esc(fecha_corta)}</code>"
                )
            encabezado = "📜 <b>Tus Últimas Inversiones</b>\n\n" if idioma == "es" else "📜 <b>Your Recent Investments</b>\n\n"
            texto = encabezado + "\n\n".join(lineas)

        await editar_o_responder_texto(
            update, texto, reply_markup=obtener_menu_principal(idioma, user.id), parse_mode="HTML"
        )

    elif data == "btn_planes":
        await editar_o_responder_texto(
            update, texto_planes_listado(), reply_markup=teclado_planes_y_redes(idioma), parse_mode="HTML"
        )

    elif data.startswith("sel_plan_"):
        plan_id = data.replace("sel_plan_", "")
        plan = PLANES_INVERSION.get(plan_id)
        if not plan:
            return
        context.user_data["plan_elegido"] = plan_id
        plazo_txt = f"{plan['dias']} días" if plan["dias"] > 0 else "Sin plazo fijo (flexible)"
        texto = (
            f"📌 <b>{esc(plan['nombre'])}</b>\n\n"
            f"• <b>Plazo:</b> <code>{esc(plazo_txt)}</code>\n"
            f"• <b>Ganancia del ciclo:</b> <code>{plan['tasa_ciclo']*100:.1f}%</code>\n"
            f"• <b>Rango permitido:</b> <code>{plan['min']:g} a {plan['max']:g} USD</code>\n\n"
            f"¿Quieres activar la <b>reinversión automática</b> al completar el ciclo?"
        )
        await editar_o_responder_texto(update, texto, reply_markup=teclado_reinversion(plan_id, idioma), parse_mode="HTML")

    elif data.startswith("reinv_"):
        partes = data.split("_")
        plan_id = partes[1]
        reinv_flag = partes[2] == "1"
        plan = PLANES_INVERSION.get(plan_id, PLANES_INVERSION["1"])
        context.user_data["plan_elegido"] = plan_id
        context.user_data["reinversion_auto"] = reinv_flag
        estado_reinv = "Sí" if reinv_flag else "No"

        texto = (
            f"💵 <b>Elige el monto · {esc(plan['nombre'])}</b>\n\n"
            f"• <b>Reinversión automática:</b> {esc(estado_reinv)}\n"
            f"• <b>Rango permitido:</b> {plan['min']:g} a {plan['max']:g} USD\n\n"
            f"Toca un monto rápido o escribe otro monto:"
        )
        await editar_o_responder_texto(
            update, texto, reply_markup=teclado_montos_inversion(plan_id, idioma), parse_mode="HTML"
        )

    elif data.startswith("otro_monto_"):
        plan_id = data.replace("otro_monto_", "")
        plan = PLANES_INVERSION.get(plan_id, PLANES_INVERSION["1"])
        context.user_data["plan_elegido"] = plan_id
        await db_exec(_db_set_estado_sync, user.id, 1, 0, 0, write=True)

        texto = (
            f"✏️ <b>Escribe el monto en USD</b>\n\n"
            f"• <b>Plan:</b> {esc(plan['nombre'])}\n"
            f"• <b>Rango permitido:</b> {plan['min']:g} a {plan['max']:g} USD\n\n"
            f"Envía solo el número (por ejemplo: <code>0.5</code> o <code>25</code>)."
        )
        await editar_o_responder_texto(
            update, texto, reply_markup=obtener_menu_principal(idioma, user.id), parse_mode="HTML"
        )

    elif data.startswith("monto_"):
        partes = data.split("_")
        plan_id = partes[1]
        try:
            monto_val = float(partes[2])
        except ValueError:
            return
        plan = PLANES_INVERSION.get(plan_id, PLANES_INVERSION["1"])
        context.user_data["plan_elegido"] = plan_id
        context.user_data["monto_elegido"] = monto_val

        texto = (
            f"🌐 <b>Elige la red para tu depósito</b>\n\n"
            f"• <b>Plan:</b> {esc(plan['nombre'])}\n"
            f"• <b>Monto:</b> {monto_val:g} USD\n"
            f"• <b>Redes disponibles:</b> TRON, TON, BSC, ETH, BTC y SOL (acepta USDT y tokens compatibles de cada red)\n\n"
            f"Toca la red que vas a usar:"
        )
        await editar_o_responder_texto(
            update, texto, reply_markup=teclado_redes_inversion(plan_id, monto_val, idioma), parse_mode="HTML"
        )

    elif data.startswith("invred_"):
        partes = data.split("_")
        plan_id = partes[1]
        try:
            monto_val = float(partes[2])
        except ValueError:
            return
        red_solicitada = partes[3]
        if plan_id not in PLANES_INVERSION or red_solicitada not in WALLETS_OFICIALES:
            return
        reinv_flag = 1 if context.user_data.get("reinversion_auto") else 0
        texto = await registrar_solicitud_inversion(user.id, plan_id, monto_val, red_solicitada, reinv_flag)
        await editar_o_responder_texto(update, texto, reply_markup=teclado_tras_direccion(idioma), parse_mode="HTML")

    elif data.startswith("red_"):
        red_key = data.replace("red_", "")
        info = REDES_INFO.get(red_key)
        wallet = WALLETS_OFICIALES.get(red_key, "")
        if info and wallet:
            await db_exec(_db_set_estado_sync, user.id, 0, 1, 0, write=True)
            texto = (
                f"💳 <b>Red {esc(info['nombre'])}</b>\n"
                f"• <b>Tokens aceptados en esta red:</b> <code>{esc(' / '.join(info['monedas']))}</code>\n"
                f"• <b>Dirección oficial:</b>\n<code>{esc(wallet)}</code>\n\n"
                f"📩 <b>Cuando envíes el pago, pega aquí el Hash / TXID</b> para verificarlo."
            )
            await editar_o_responder_texto(update, texto, reply_markup=teclado_tras_direccion(idioma), parse_mode="HTML")

    elif data == "btn_depositar":
        await editar_o_responder_texto(
            update,
            texto_wallets_deposito(idioma),
            reply_markup=teclado_wallets_accion(idioma),
            parse_mode="HTML",
        )

    elif data == "enviar_hash_pago":
        await db_exec(_db_set_estado_sync, user.id, 0, 1, 0, write=True)
        texto = (
            "📩 <b>Enviar Hash de Transferencia</b>\n\n"
            "Pega aquí el <b>Hash / TXID</b> de tu envío:"
            if idioma == "es"
            else (
                "📩 <b>Send Transfer Hash</b>\n\n"
                "Paste here your transaction <b>Hash / TXID</b>:"
            )
        )
        await editar_o_responder_texto(
            update, texto, reply_markup=obtener_menu_principal(idioma, user.id), parse_mode="HTML"
        )

    elif data == "btn_referidos":
        texto = construir_mensaje_referidos(context.bot.username, user.id, idioma)
        await editar_o_responder_texto(
            update, texto, reply_markup=obtener_menu_principal(idioma, user.id), parse_mode="HTML"
        )

    elif data == "btn_soporte":
        await db_exec(_db_set_estado_sync, user.id, 0, 0, 1, write=True)
        texto = (
            "🎧 ¡Hola! Escríbeme aquí abajo en qué te ayudo o qué quieres revisar y lo vemos enseguida."
            if idioma == "es"
            else "🎧 Hey! Write below what you need help with and we'll check it right away."
        )
        await editar_o_responder_texto(
            update, texto, reply_markup=obtener_menu_principal(idioma, user.id), parse_mode="HTML"
        )


async def mostrar_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def mostrar_planes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await editar_o_responder_texto(
        update,
        texto_planes_listado(),
        reply_markup=teclado_planes_y_redes("es"),
        parse_mode="HTML",
    )


async def depositar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await editar_o_responder_texto(
        update,
        texto_wallets_deposito("es"),
        reply_markup=teclado_wallets_accion("es"),
        parse_mode="HTML",
    )


async def ver_fondo_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or user.id != ADMIN_ID:
        return
    fondo_actual, ultima_act = await db_exec(_db_obtener_liquidez_sync)
    texto = (
        f"🔐 <b>Panel Interno del Fondo</b>\n\n"
        f"• <b>Reserva actual:</b> <code>${fondo_actual:,.2f} USD</code>\n"
        f"• <b>Piso de seguridad:</b> <code>${PISO_FONDO_USD:,.2f} USD</code>\n"
        f"• <b>Último ajuste:</b> <code>{esc(ultima_act or 'Sin registro')}</code>"
    )
    await editar_o_responder_texto(
        update,
        texto,
        reply_markup=obtener_menu_principal("es", user.id),
        parse_mode="HTML",
    )


def _db_guardar_hash_y_pendiente_sync(user_id: int, hash_tx: str, limpiar_estado: bool = True):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT plan_id, monto, moneda, red
            FROM inversiones
            WHERE user_id = ? AND estado = 'pendiente_pago'
            ORDER BY id DESC LIMIT 1
            """,
            (user_id,),
        )
        pendiente = cursor.fetchone()
        red_reg = pendiente[3] if pendiente and pendiente[3] else "TRON"
        moneda_reg = "USD"
        monto_reg = float(pendiente[1]) if pendiente and pendiente[1] else 0.0

        cursor.execute(
            "INSERT OR IGNORE INTO comprobantes_verificados (tx_hash, red, moneda, monto, tipo, fecha) VALUES (?, ?, ?, ?, ?, ?)",
            (hash_tx, red_reg, moneda_reg, monto_reg, "reporte_usuario", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        if limpiar_estado:
            cursor.execute("UPDATE usuarios SET esperando_hash = 0 WHERE user_id = ?", (user_id,))
    return pendiente


async def _enviar_aviso_hash_admin(bot, user, hash_tx: str, pendiente):
    if not ADMIN_ID:
        return
    sugerido_monto = float(pendiente[1]) if pendiente and pendiente[1] else None
    sugerido_red = pendiente[3] if pendiente and pendiente[3] else "TRON"
    plan_txt = ""
    if pendiente:
        nombre_p = (PLANES_INVERSION.get(str(pendiente[0])) or {}).get("nombre", f"Plan {pendiente[0]}")
        plan_txt = f"\n• <b>Solicitud:</b> {esc(nombre_p)} — <code>{float(pendiente[1]):g} USD</code> ({esc(sugerido_red)})"

    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"📲 <b>Nuevo Hash Reportado</b>\n\n"
                f"• <b>Usuario:</b> {esc(user.first_name)} (<code>{user.id}</code>){plan_txt}\n"
                f"• <b>Hash:</b> <code>{esc(hash_tx)}</code>"
            ),
            reply_markup=teclado_admin_hash(user.id, sugerido_monto, sugerido_red),
            parse_mode="HTML",
        )
    except Exception as e:
        print(f"Error notificando hash al admin: {e}", flush=True)


async def notificar_deposito(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await editar_o_responder_texto(update, "⚠️ Uso: <code>/notificar [Hash]</code>", parse_mode="HTML")
        return
    hash_tx = " ".join(context.args).strip()
    user = update.effective_user
    user_id = user.id if user else 0
    pendiente = None
    try:
        pendiente = await db_exec(_db_guardar_hash_y_pendiente_sync, user_id, hash_tx, False, write=True)
    except Exception as e:
        print(f"Error en /notificar: {e}", flush=True)
    if user:
        await _enviar_aviso_hash_admin(context.bot, user, hash_tx, pendiente)
    await editar_o_responder_texto(
        update,
        f"⏳ Recibimos tu comprobante (<code>{esc(hash_tx)}</code>). Estamos en proceso de verificación.",
        parse_mode="HTML",
    )


async def aprobar_deposito(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or user.id != ADMIN_ID:
        return

    if len(context.args) < 3:
        await editar_o_responder_texto(
            update,
            "⚠️ Uso: <code>/aprobar [ID_Usuario] [Monto] [Moneda] [RED_OPCIONAL] [HASH_OPCIONAL]</code>",
            parse_mode="HTML",
        )
        return

    id_usuario = context.args[0]
    if not id_usuario.isdigit():
        await editar_o_responder_texto(update, "❌ El ID de usuario debe ser numérico.", parse_mode="HTML")
        return

    try:
        monto = float(context.args[1])
    except ValueError:
        await editar_o_responder_texto(update, "❌ El monto debe ser un número válido.", parse_mode="HTML")
        return

    if monto < MIN_MONTO_INVERSION:
        await editar_o_responder_texto(
            update, f"❌ El monto mínimo permitido es <code>{MIN_MONTO_INVERSION:g}</code>.", parse_mode="HTML"
        )
        return

    moneda = context.args[2].upper()
    red = (
        context.args[3].upper()
        if len(context.args) >= 4 and context.args[3].upper() in WALLETS_OFICIALES
        else "TRON"
    )
    tx_hash = context.args[4].strip() if len(context.args) >= 5 else None

    notificaciones, estado_aprob, monto_final = await db_exec(
        _db_aprobar_deposito_sync, id_usuario, monto, moneda, red, tx_hash, write=True
    )
    if estado_aprob == "duplicado_hash":
        await editar_o_responder_texto(
            update, "⚠️ Ese hash ya fue aprobado anteriormente.", parse_mode="HTML"
        )
        return

    for pat_id, msg in notificaciones:
        try:
            await context.bot.send_message(chat_id=pat_id, text=msg, parse_mode="HTML")
        except Exception as e:
            print(f"No se pudo notificar al patrocinador {pat_id}: {e}", flush=True)

    await editar_o_responder_texto(
        update,
        f"✅ Depósito aprobado para <code>{esc(id_usuario)}</code>: <code>{monto_final:g} {esc(moneda)}</code> en <code>{esc(red)}</code>.",
        parse_mode="HTML",
    )


def _db_leer_estado_texto_sync(user_id: int):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT esperando_monto, esperando_hash, en_soporte, idioma FROM usuarios WHERE user_id = ?",
            (user_id,),
        )
        return cursor.fetchone()


async def manejar_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    if not user:
        return
    texto_msg = update.message.text.strip()

    row = await db_exec(_db_leer_estado_texto_sync, user.id)
    if not row:
        return

    esperando_monto, esperando_hash, en_soporte, idioma = row
    idioma = idioma or "es"

    if esperando_monto:
        plan_id = context.user_data.get("plan_elegido", "1")
        plan = PLANES_INVERSION.get(plan_id, PLANES_INVERSION["1"])
        try:
            monto_val = float(texto_msg.replace(",", "."))
        except ValueError:
            await editar_o_responder_texto(
                update,
                "❌ Escribe un número válido (por ejemplo: <code>0.5</code> o <code>25</code>).",
                parse_mode="HTML",
            )
            return

        if monto_val < plan["min"] or monto_val > plan["max"]:
            await editar_o_responder_texto(
                update,
                f"❌ El monto debe estar entre <code>{plan['min']:g}</code> y <code>{plan['max']:g} USD</code>.",
                parse_mode="HTML",
            )
            return

        await db_exec(_db_set_estado_sync, user.id, 0, 0, 0, write=True)
        context.user_data["monto_elegido"] = monto_val
        await editar_o_responder_texto(
            update,
            f"🌐 <b>Elige la red para tu depósito</b>\n\n"
            f"• <b>Plan:</b> {esc(plan['nombre'])}\n"
            f"• <b>Monto:</b> {monto_val:g} USD\n"
            f"• <b>Redes disponibles:</b> TRON, TON, BSC, ETH, BTC y SOL (acepta USDT y tokens compatibles de cada red)\n\n"
            f"Toca la red que vas a usar:",
            reply_markup=teclado_redes_inversion(plan_id, monto_val, idioma),
            parse_mode="HTML",
        )
        return

    if esperando_hash:
        pendiente = await db_exec(_db_guardar_hash_y_pendiente_sync, user.id, texto_msg, True, write=True)
        await _enviar_aviso_hash_admin(context.bot, user, texto_msg, pendiente)

        await editar_o_responder_texto(
            update,
            f"⏳ Recibimos tu comprobante (<code>{esc(texto_msg)}</code>). Estamos en proceso de verificación.",
            reply_markup=obtener_menu_principal(idioma, user.id),
            parse_mode="HTML",
        )
        return

    if en_soporte:
        await db_exec(_db_set_estado_sync, user.id, 0, 0, 0, write=True)
        if ADMIN_ID:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        f"🎧 <b>Mensaje de Soporte</b>\n\n"
                        f"• <b>Usuario:</b> {esc(user.first_name)} (<code>{user.id}</code>)\n"
                        f"• <b>Mensaje:</b> {esc(texto_msg)}"
                    ),
                    parse_mode="HTML",
                )
            except Exception as e:
                print(f"Error enviando soporte al admin: {e}", flush=True)

        await editar_o_responder_texto(
            update,
            "✅ ¡Listo! Ya pasé tu mensaje a soporte y te respondemos en cuanto lo revisemos.",
            reply_markup=obtener_menu_principal(idioma, user.id),
            parse_mode="HTML",
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = context.error
    if isinstance(err, Conflict):
        print(
            "Aviso temporal de Conflict en getUpdates (instancia previa cerrando); se reintentará.",
            flush=True,
        )
        return
    if isinstance(err, (NetworkError, TimedOut)):
        print(
            f"Aviso de red temporal en PTB (se reintentará automáticamente): {err}",
            flush=True,
        )
        return
    print(f"Excepción no controlada en PTB: {err}", flush=True)


async def post_init(application):
    await asyncio.sleep(3)
    try:
        await application.bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        print(f"Aviso al limpiar webhook en post_init: {e}", flush=True)

    application.bot_data["tarea_comprobaciones"] = asyncio.create_task(
        tarea_comprobaciones_canal(application.bot)
    )
    application.bot_data["tarea_keep_alive"] = asyncio.create_task(
        tarea_keep_alive()
    )


async def post_shutdown(application):
    for key in ("tarea_comprobaciones", "tarea_keep_alive"):
        tarea = application.bot_data.get(key)
        if tarea and not tarea.done():
            tarea.cancel()
            try:
                await tarea
            except asyncio.CancelledError:
                pass


def main():
    if not TOKEN:
        raise RuntimeError("Falta la variable de entorno TOKEN en Render.")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    Thread(target=run_web, daemon=True).start()

    request = HTTPXRequest(
        connection_pool_size=20,
        connect_timeout=15.0,
        read_timeout=25.0,
        write_timeout=20.0,
        pool_timeout=15.0,
    )

    application = (
        ApplicationBuilder()
        .token(TOKEN)
        .request(request)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_error_handler(error_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("saldo", mostrar_saldo))
    application.add_handler(CommandHandler("planes", mostrar_planes))
    application.add_handler(CommandHandler("depositar", depositar))
    application.add_handler(CommandHandler("fondo", ver_fondo_admin))
    application.add_handler(CommandHandler("notificar", notificar_deposito))
    application.add_handler(CommandHandler("aprobar", aprobar_deposito))
    application.add_handler(CallbackQueryHandler(boton_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_texto))

    print("Iniciando polling de Telegram...", flush=True)
    application.run_polling(
        drop_pending_updates=True,
        poll_interval=1.0,
        timeout=20,
        bootstrap_retries=5,
    )


if __name__ == "__main__":
    main()
