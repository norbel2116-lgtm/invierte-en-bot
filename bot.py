import os
import re
import sqlite3
import random
import asyncio
from datetime import datetime
from threading import Thread
import aiohttp
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Conflict, NetworkError, TimedOut, TelegramError
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


TOKEN = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "-1001234567890")
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))
LINK_CANAL = os.getenv("LINK_CANAL", "https://t.me/TuCanalDePagos")
DB_PATH = os.getenv("DB_PATH", "usuarios.db")
SELF_PING_URL = (
    os.getenv("SELF_PING_URL")
    or (
        f"{os.getenv('RENDER_EXTERNAL_URL').rstrip('/')}/health"
        if os.getenv("RENDER_EXTERNAL_URL")
        else ""
    )
)

# --- 5 WALLETS Y REDES OFICIALES (USDT HABILITADO EN TODAS) ---
WALLETS_OFICIALES = {
    "TRON": os.getenv("WALLET_TRON", "TFWUrcxFh4oknNgmBfTY6jjixhNaGm8t5u"),
    "TON": os.getenv("WALLET_TON", "UQBwUUdb52EJ9T9XMn4lgn625XUDSgQKI3cI_BnAVSA3p8_v"),
    "BTC": os.getenv("WALLET_BTC", "bc1qsejk806afnhztv7lqcsaes9s7a32p4grstwru7"),
    "BSC": os.getenv("WALLET_BSC", "0xAB75fD4D65A1A82E0eF5BbbFdFE6908E95F995EC"),
    "ETH": os.getenv("WALLET_ETH", "0xAB75fD4D65A1A82E0eF5BbbFdFE6908E95F995EC"),
}

REDES_INFO = {
    "TRON": {
        "nombre": "TRON (TRC20)",
        "monedas": ["USDT", "TRX"],
        "explorer": "https://tronscan.org/#/transaction/",
    },
    "TON": {
        "nombre": "TON",
        "monedas": ["USDT", "TON", "GRAM"],
        "explorer": "https://tonviewer.com/transaction/",
    },
    "BSC": {
        "nombre": "BSC (BEP20)",
        "monedas": ["USDT", "BNB"],
        "explorer": "https://bscscan.com/tx/",
    },
    "ETH": {
        "nombre": "ETH (ERC20)",
        "monedas": ["USDT", "ETH"],
        "explorer": "https://etherscan.io/tx/",
    },
    "BTC": {
        "nombre": "Bitcoin (BTC)",
        "monedas": ["USDT", "BTC"],
        "explorer": "https://mempool.space/tx/",
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
HASHES_USADOS_SESION = set()

# Rangos realistas por moneda para comprobantes multired
RANGOS_COMPROBANTES = {
    "USDT": (0.5, 500.0),
    "TRX": (1.0, 5000.0),
    "TON": (0.5, 250.0),
    "GRAM": (1.0, 5000.0),
    "BNB": (0.002, 8.0),
    "ETH": (0.001, 4.0),
    "BTC": (0.00005, 0.08),
}

COMISION_ANTICIPADA_POR_MONEDA = {
    "USDT": 0.2,
    "TRX": 0.2,
    "GRAM": 0.2,
    "TON": 0.2,
    "BNB": 0.2,
    "ETH": 0.2,
    "BTC": 0.00001,
}

# --- PLANES CON MÍNIMO DESDE 0.5 USDT ---
PLANES_INVERSION = {
    "1": {
        "nombre": "Plan de Inicio (7 días)",
        "boton": "🟢 Inicio · 7d (0.7%)",
        "modalidad": "plazo_fijo",
        "dias": 7,
        "tasa_ciclo": 0.007,
        "min": 0.5,
        "max": 1000.0,
        "moneda": "USDT",
        "red_sugerida": "TRON",
        "permite_reinvest": True,
        "detalle": "7 días | 0.7% al completar el ciclo. Desde 0.5 USDT sin bloqueos largos.",
    },
    "2": {
        "nombre": "Plan Crecimiento (14 días)",
        "boton": "🔵 Crecimiento · 14d (2.4%)",
        "modalidad": "plazo_fijo",
        "dias": 14,
        "tasa_ciclo": 0.024,
        "min": 0.5,
        "max": 1000.0,
        "moneda": "USDT",
        "red_sugerida": "TON",
        "permite_reinvest": True,
        "detalle": "14 días | 1.2% semanal (~2.4% en el ciclo). Equilibrio entre plazo y retorno.",
    },
    "3": {
        "nombre": "Plan Pro / Élite (21 días)",
        "boton": "🟣 Pro / Élite · 21d (7.8%)",
        "modalidad": "plazo_fijo",
        "dias": 21,
        "tasa_ciclo": 0.078,
        "min": 1.0,
        "max": 1000.0,
        "moneda": "USDT",
        "red_sugerida": "BSC",
        "permite_reinvest": True,
        "detalle": "21 días | 2.6% semanal (~7.8% en el ciclo). Para ciclos más prolongados.",
    },
    "4": {
        "nombre": "Fondo Flexible / Liquidez",
        "boton": "🟡 Flexible · Liquidez (0.5%)",
        "modalidad": "liquidez_flexible",
        "dias": 0,
        "tasa_ciclo": 0.005,
        "min": 0.5,
        "max": 1000.0,
        "moneda": "USDT",
        "red_sugerida": "TRON",
        "permite_reinvest": False,
        "detalle": "Sin bloqueo fijo | 0.5% cada 7 días. Vinculado al fondo de liquidez.",
    },
    "5": {
        "nombre": "Meta / Aporte Escalonado",
        "boton": "🟠 Meta · 30d (3.2%)",
        "modalidad": "aporte_meta",
        "dias": 30,
        "tasa_ciclo": 0.032,
        "min": 0.5,
        "max": 1000.0,
        "moneda": "USDT",
        "red_sugerida": "ETH",
        "permite_reinvest": True,
        "detalle": "30 días | 0.8% semanal (3.2% en 4 semanas). Suma aportes progresivos.",
    },
}


def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


async def db_exec(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


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
                    moneda_deposito TEXT DEFAULT 'USDT',
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

            cursor.execute("SELECT COUNT(*) FROM liquidez_global")
            if cursor.fetchone()[0] == 0:
                cursor.execute(
                    "INSERT INTO liquidez_global (id, fondo_actual, ultima_actualizacion) VALUES (1, ?, ?)",
                    (124500.00, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                )

            fecha_respaldo = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for h_ton in HASHES_RESPALDO_TON:
                cursor.execute(
                    "INSERT OR IGNORE INTO comprobantes_verificados (tx_hash, red, moneda, monto, tipo, fecha) VALUES (?, ?, ?, ?, ?, ?)",
                    (h_ton, "TON", "TON", 10.0, "respaldo_ton", fecha_respaldo),
                )
            for h_tron in HASHES_RESPALDO_TRON:
                cursor.execute(
                    "INSERT OR IGNORE INTO comprobantes_verificados (tx_hash, red, moneda, monto, tipo, fecha) VALUES (?, ?, ?, ?, ?, ?)",
                    (h_tron, "TRON", "USDT", 25.0, "respaldo_tron", fecha_respaldo),
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
    if red == "TON":
        return bool(re.fullmatch(r"[0-9a-fA-F]{64}|[A-Za-z0-9+/=_-]{32,128}", h))
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


def _registrar_hash_publicado(tx_hash: str, red: str, moneda: str, monto: float):
    _marcar_hash_usado(tx_hash)
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO comprobantes_verificados (tx_hash, red, moneda, monto, tipo, fecha) VALUES (?, ?, ?, ?, ?, ?)",
                (tx_hash, red, moneda, monto, "publicado_canal", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
    except Exception as e:
        print(f"Error guardando hash publicado: {e}", flush=True)


def _cumple_filtro_monto(monto: float, moneda: str = "USDT") -> bool:
    if monto is None or monto <= 0:
        return False
    m_upper = (moneda or "USDT").upper()
    min_val, max_val = RANGOS_COMPROBANTES.get(m_upper, (MIN_MONTO_INVERSION, 1000.0))
    return min_val <= monto <= max_val


async def obtener_tx_real_tron(session: aiohttp.ClientSession, address: str, _tipo_operacion: str = "deposito"):
    url = f"https://api.trongrid.io/v1/accounts/{address}/transactions/trc20?limit=50"
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
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
                "verificado": "Real en TronGrid",
            }
    return None


async def obtener_tx_real_btc(session: aiohttp.ClientSession, address: str, _tipo_operacion: str = "deposito"):
    url = f"https://mempool.space/api/address/{address}/txs"
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
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
                "verificado": "Real en Mempool",
            }
    return None


async def obtener_tx_real_ton(session: aiohttp.ClientSession, address: str, _tipo_operacion: str = "deposito"):
    url = f"https://toncenter.com/api/v2/getTransactions?address={address}&limit=50"
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
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
                "verificado": "Real en Toncenter",
            }
    return None


async def _obtener_tx_evm_rpc(
    session: aiohttp.ClientSession,
    rpc_urls: list[str],
    red_key: str,
    simbolo: str,
    _tipo_operacion: str = "deposito",
):
    req_timeout = aiohttp.ClientTimeout(total=8)
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
                            "verificado": f"Real en bloque ({red_key})",
                        }
        except Exception as e:
            print(f"Error RPC {red_key} ({rpc_url}): {e}", flush=True)
    return None


async def obtener_tx_real_bsc(session: aiohttp.ClientSession, _address: str, tipo_operacion: str = "deposito"):
    rpcs_bsc = [
        "https://bsc-dataseed.binance.org/",
        "https://bsc-dataseed1.defibit.io/",
        "https://bsc-rpc.publicnode.com",
    ]
    return await _obtener_tx_evm_rpc(session, rpcs_bsc, "BSC", "BNB", tipo_operacion)


async def obtener_tx_real_eth(session: aiohttp.ClientSession, _address: str, tipo_operacion: str = "deposito"):
    rpcs_eth = [
        "https://ethereum-rpc.publicnode.com",
        "https://cloudflare-eth.com",
    ]
    return await _obtener_tx_evm_rpc(session, rpcs_eth, "ETH", "ETH", tipo_operacion)


def calcular_retiro_anticipado(capital_base: float, moneda: str):
    capital = max(float(capital_base or 0.0), 0.0)
    moneda_upper = (moneda or "USDT").upper()
    comision = COMISION_ANTICIPADA_POR_MONEDA.get(moneda_upper, 0.2)
    neto = round(max(capital - comision, 0.0), 6)
    return {
        "capital_base": round(capital, 6),
        "moneda": moneda_upper,
        "comision_red": comision,
        "neto_a_recibir": neto,
    }


async def obtener_comprobante_multired(tipo_operacion: str = "retiro"):
    prioritarias = ["TRON", "TON", "BTC"]
    secundarias = ["BSC", "ETH"]
    random.shuffle(prioritarias)
    random.shuffle(secundarias)
    orden_redes = prioritarias + secundarias

    consultores = {
        "TRON": obtener_tx_real_tron,
        "TON": obtener_tx_real_ton,
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
                print(f"Error consultando blockchain {red_key}: {e}", flush=True)

    print(f"Multired sin tx válida en ciclo ({tipo_operacion}): {', '.join(sin_resultado)}", flush=True)
    return None


async def tarea_comprobaciones_canal(bot):
    await asyncio.sleep(10)
    try:
        while True:
            try:
                if CHANNEL_ID and str(CHANNEL_ID) != "-1001234567890":
                    cantidad_envios = random.randint(1, 5)
                    enviados = 0

                    for _ in range(cantidad_envios):
                        tipo_op = random.choice(["deposito", "retiro"])
                        comp = await obtener_comprobante_multired(tipo_op)
                        if comp and comp.get("hash") and not _hash_ya_publicado(comp["hash"]):
                            usuario = generar_usuario_ficticio()
                            etiqueta_tipo = "Depósito" if tipo_op == "deposito" else "Retiro"
                            texto = (
                                f"📢 **Comprobante de {etiqueta_tipo}**\n\n"
                                f"• **Usuario:** `{usuario}`\n"
                                f"• **Monto:** `{comp['monto']} {comp['moneda']}`\n"
                                f"• **Red:** `{comp['red']}`\n"
                                f"• **Hash:** `{comp['hash']}`\n"
                                f"• **Explorador:** {comp['explorer']}"
                            )
                            try:
                                await bot.send_message(
                                    chat_id=CHANNEL_ID,
                                    text=texto,
                                    parse_mode="Markdown",
                                    disable_web_page_preview=True,
                                )
                                await db_exec(
                                    _registrar_hash_publicado,
                                    comp["hash"], comp["red"], comp["moneda"], comp["monto"],
                                )
                                enviados += 1
                            except TelegramError as te:
                                print(f"Error enviando comprobante al canal: {te}", flush=True)
                            await asyncio.sleep(1.5)

                    print(f"Ciclo comprobaciones: enviados {enviados}/{cantidad_envios}", flush=True)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"Error en tarea_comprobaciones_canal: {e}", flush=True)

            espera_segundos = random.randint(300, 1200)
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
                print(f"Aviso en keep-alive interno: {e}", flush=True)

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


def obtener_menu_principal(idioma="es"):
    if idioma == "en":
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("💰 Balance", callback_data="btn_saldo"),
                InlineKeyboardButton("🏦 Pool", callback_data="btn_liquidez"),
            ],
            [
                InlineKeyboardButton("📈 Invest", callback_data="btn_planes"),
                InlineKeyboardButton("💳 Wallets (USDT)", callback_data="btn_depositar"),
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
        ])

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💰 Mi Saldo", callback_data="btn_saldo"),
            InlineKeyboardButton("🏦 Liquidez", callback_data="btn_liquidez"),
        ],
        [
            InlineKeyboardButton("📈 Invertir", callback_data="btn_planes"),
            InlineKeyboardButton("💳 Wallets (USDT)", callback_data="btn_depositar"),
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
    ])


def teclado_tras_direccion(idioma="es"):
    volver_txt = "⬅️ Menú" if idioma == "es" else "⬅️ Menu"
    volver_cb = "lang_es" if idioma == "es" else "lang_en"
    enviar_txt = "📩 Enviar Hash / TXID" if idioma == "es" else "📩 Send Hash / TXID"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(enviar_txt, callback_data="enviar_hash_pago")],
        [InlineKeyboardButton(volver_txt, callback_data=volver_cb)],
    ])


def teclado_planes_y_redes(idioma="es"):
    filas = []
    for _, plan in PLANES_INVERSION.items():
        filas.append([
            InlineKeyboardButton(plan["boton"], callback_data=f"sel_plan_{key}")
        ])
    filas.append([
        InlineKeyboardButton("TRON", callback_data="red_TRON"),
        InlineKeyboardButton("TON", callback_data="red_TON"),
        InlineKeyboardButton("BTC", callback_data="red_BTC"),
    ])
    filas.append([
        InlineKeyboardButton("BSC", callback_data="red_BSC"),
        InlineKeyboardButton("ETH", callback_data="red_ETH"),
    ])
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
        [InlineKeyboardButton("♻️ Reinversión: SÍ", callback_data=f"reinv_{plan_id}_1")],
        [InlineKeyboardButton("💵 Reinversión: NO", callback_data=f"reinv_{plan_id}_0")],
        [InlineKeyboardButton("⬅️ Volver", callback_data="btn_planes")],
    ])


def teclado_montos_inversion(plan_id: str, idioma="es"):
    plan = PLANES_INVERSION.get(plan_id, PLANES_INVERSION["1"])
    moneda = plan["moneda"]
    sugeridos = [0.5, 1, 5, 10, 50, 100]
    validos = [m for m in sugeridos if plan["min"] <= m <= plan["max"]]
    if not validos:
        validos = [0.5]

    filas = []
    fila_actual = []
    for m in validos:
        etiqueta = f"{m:g} {moneda}"
        fila_actual.append(InlineKeyboardButton(etiqueta, callback_data=f"monto_{plan_id}_{m}"))
        if len(fila_actual) == 2:
            filas.append(fila_actual)
            fila_actual = []
    if fila_actual:
        filas.append(fila_actual)

    txt_otro = "✏️ Otro monto" if idioma == "es" else "✏️ Custom amount"
    txt_volver = "⬅️ Volver" if idioma == "es" else "⬅️ Back"
    filas.append([InlineKeyboardButton(txt_otro, callback_data=f"otro_monto_{plan_id}")])
    filas.append([InlineKeyboardButton(txt_volver, callback_data=f"sel_plan_{plan_id}")])
    return InlineKeyboardMarkup(filas)


def teclado_redes_inversion(plan_id: str, monto: float, idioma="es"):
    filas = [
        [
            InlineKeyboardButton("TRON", callback_data=f"invred_{plan_id}_{monto}_TRON"),
            InlineKeyboardButton("TON", callback_data=f"invred_{plan_id}_{monto}_TON"),
            InlineKeyboardButton("BTC", callback_data=f"invred_{plan_id}_{monto}_BTC"),
        ],
        [
            InlineKeyboardButton("BSC", callback_data=f"invred_{plan_id}_{monto}_BSC"),
            InlineKeyboardButton("ETH", callback_data=f"invred_{plan_id}_{monto}_ETH"),
        ],
        [
            InlineKeyboardButton(
                "⬅️ Montos" if idioma == "es" else "⬅️ Amounts",
                callback_data=f"reinv_{plan_id}_0",
            )
        ],
    ]
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


def texto_wallets_deposito(idioma="es"):
    if idioma == "en":
        encabezado = "💳 **Official Deposit Wallets (USDT Supported on All 5 Networks)**:\n\n"
        aviso = "⚠️ Always match the network and address. After sending your transfer, tap **Send Hash / TXID** below."
    else:
        encabezado = "💳 **Direcciones de Depósito Oficiales (USDT en las 5 Redes)**:\n\n"
        aviso = "⚠️ Verifica que la red coincida con la dirección antes de enviar. Tras hacer la transferencia, toca **Enviar Hash / TXID** abajo."

    bloques = []
    for red_key, info in REDES_INFO.items():
        wallet = WALLETS_OFICIALES.get(red_key, "")
        monedas_str = " / ".join(info["monedas"])
        bloques.append(f"🔹 **{info['nombre']} ({monedas_str}):**\n`{wallet}`")
    return encabezado + "\n\n".join(bloques) + f"\n\n{aviso}"


def construir_mensaje_referidos(username_bot, user_id, idioma="es"):
    bot_user = username_bot or "TuBot"
    link_referido = f"https://t.me/{bot_user}?start={user_id}"
    if idioma == "en":
        return (
            f"🌟 **Welcome! We are glad you want to join**\n\n"
            f"🚀 **Your Exclusive Referral Link:**\n`{link_referido}`\n\n"
            f"📊 **Balanced Plans (From 0.5 USDT):**\n"
            f"• **Starter (7d - 0.7%):** Min 0.5 USDT\n"
            f"• **Growth (14d - 1.2%/wk):** Min 0.5 USDT\n"
            f"• **Pro / Elite (21d - 2.6%/wk):** Min 1 USDT\n\n"
            f"💡 **Early Withdrawal Rule:** Available anytime, forfeiting profits + network fee (0.2 or 0.00001 BTC)."
        )
    return (
        f"🌟 **¡Bienvenido/a! Nos alegra mucho que quieras sumarte**\n\n"
        f"🚀 **Tu Link de Referido Exclusivo:**\n`{link_referido}`\n\n"
        f"📊 **Planes Equilibrados (Desde 0.5 USDT):**\n"
        f"• **Inicio (7 días - 0.7%):** Mín 0.5 USDT\n"
        f"• **Crecimiento (14 días - 1.2%/sem):** Mín 0.5 USDT\n"
        f"• **Pro / Élite (21 días - 2.6%/sem):** Mín 1 USDT\n\n"
        f"💡 **Regla de Retiro Anticipado:** Disponible en cualquier momento; se pierden ganancias y aplica comisión de red (0.2 o 0.00001 BTC)."
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
                cantidad,
                plan["moneda"],
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
    await db_exec(
        _db_registrar_solicitud_sync,
        user_id, plan_id, cantidad, red_solicitada, reinv_flag,
    )
    return (
        f"✅ **Solicitud Registrada**\n\n"
        f"• **Plan:** {plan['nombre']}\n"
        f"• **Monto:** `{cantidad:g} {plan['moneda']}`\n"
        f"• **Red:** `{red_solicitada}` (USDT habilitado)\n"
        f"• **Reinversión Auto:** `{'SÍ' if reinv_flag else 'NO'}`\n\n"
        f"💳 **Envía a esta dirección:**\n`{wallet}`\n\n"
        f"📩 **Una vez que hagas la transferencia, envía aquí el Hash / TXID** (ya quedó habilitado para que lo pegues directamente o uses `/notificar [Tu_Hash]`)."
    )


def _db_start_sync(user_id: int, first_name: str, patrocinador_id):
    notificar_patrocinador = False
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, patrocinador_id, idioma FROM usuarios WHERE user_id = ?", (user_id,))
        existe = cursor.fetchone()
        idioma = existe[2] if existe and existe[2] else "es"

        if not existe:
            cursor.execute(
                "INSERT INTO usuarios (user_id, nombre, patrocinador_id, idioma) VALUES (?, ?, ?, ?)",
                (user_id, first_name, patrocinador_id, "es"),
            )
            if patrocinador_id and patrocinador_id != user_id:
                notificar_patrocinador = True

        cursor.execute(
            "UPDATE usuarios SET esperando_monto = 0, esperando_hash = 0, en_soporte = 0 WHERE user_id = ?",
            (user_id,),
        )
    return notificar_patrocinador, idioma


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    args = context.args
    patrocinador_id = int(args[0]) if args and args[0].isdigit() else None

    notificar_patrocinador, _ = await db_exec(
        _db_start_sync, user.id, user.first_name, patrocinador_id
    )

    if notificar_patrocinador and patrocinador_id:
        try:
            await context.bot.send_message(
                chat_id=patrocinador_id,
                text=(
                    f"🎉 **¡Nuevo Referido Detectado!**\n\n"
                    f"El usuario **{user.first_name}** se unió a tu red de referidos."
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            print(f"No se pudo notificar al patrocinador: {e}", flush=True)

    texto = "🌐 **Welcome / Bienvenido**\n\nSelecciona tu idioma / Select your language:"
    try:
        if update.message:
            await update.message.reply_text(texto, reply_markup=obtener_menu_idiomas(), parse_mode="Markdown")
        elif update.callback_query:
            await update.callback_query.message.edit_text(texto, reply_markup=obtener_menu_idiomas(), parse_mode="Markdown")
    except Exception as e:
        print(f"Error en start: {e}", flush=True)


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
            "UPDATE usuarios SET idioma = ?, esperando_monto = 0, esperando_hash = 0, en_soporte = 0 WHERE user_id = ?",
            (nuevo_idioma, user_id),
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
        cursor.execute("SELECT fondo_actual FROM liquidez_global WHERE id = 1")
        row = cursor.fetchone()
    return row[0] if row else 124500.00


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
            "SELECT deposito_activo, moneda_deposito, red_deposito FROM usuarios WHERE user_id = ?",
            (user_id,),
        )
        return cursor.fetchone()


def _db_retiro_confirmar_sync(user_id: int):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT deposito_activo, moneda_deposito, red_deposito FROM usuarios WHERE user_id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        deposito_activo = float(row[0]) if row and row[0] else 0.0
        moneda = row[1] if row and row[1] else "USDT"
        red = row[2] if row and row[2] else "TRON"
        calc = calcular_retiro_anticipado(deposito_activo, moneda)
        if calc["capital_base"] <= 0:
            return None, moneda, red
        cursor.execute(
            "UPDATE usuarios SET deposito_activo = 0, fecha_deposito = NULL WHERE user_id = ?",
            (user_id,),
        )
        cursor.execute(
            "UPDATE inversiones SET estado = 'retirado_anticipado' WHERE user_id = ? AND estado = 'activa'",
            (user_id,),
        )
        return calc, moneda, red


async def procesar_retiro_anticipado(update: Update, context: ContextTypes.DEFAULT_TYPE, idioma: str):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    if data == "btn_retirar":
        row = await db_exec(_db_retiro_consultar_sync, user_id)
        deposito_activo = float(row[0]) if row and row[0] else 0.0
        moneda = row[1] if row and row[1] else "USDT"
        red = row[2] if row and row[2] else "TRON"

        if deposito_activo <= 0:
            texto = (
                "🏦 **Retiros:** No tienes capital activo disponible para retirar."
                if idioma == "es"
                else "🏦 **Withdrawals:** You have no active capital available to withdraw."
            )
            await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")
            return

        calc = calcular_retiro_anticipado(deposito_activo, moneda)
        if idioma == "en":
            texto = (
                f"⚠️ **Early Withdrawal Notice**\n\n"
                f"You can withdraw anytime, **but you forfeit accrued profits** and a network fee applies.\n\n"
                f"• **Base Capital:** `{calc['capital_base']} {calc['moneda']}` ({red})\n"
                f"• **Accrued Profits:** `Forfeited (0)`\n"
                f"• **Network Fee:** `-{calc['comision_red']} {calc['moneda']}`\n"
                f"• **Net to Receive:** `{calc['neto_a_recibir']} {calc['moneda']}`"
            )
        else:
            texto = (
                f"⚠️ **Aviso de Retiro Anticipado**\n\n"
                f"Puedes retirar en cualquier momento, **pero pierdes las ganancias acumuladas** y se descuenta comisión de red.\n\n"
                f"• **Capital Base:** `{calc['capital_base']} {calc['moneda']}` ({red})\n"
                f"• **Ganancias:** `Se pierden al retirar antes (0)`\n"
                f"• **Comisión de Red:** `-{calc['comision_red']} {calc['moneda']}`\n"
                f"• **Neto a Recibir:** `{calc['neto_a_recibir']} {calc['moneda']}`"
            )
        await query.message.edit_text(texto, reply_markup=teclado_confirmar_retiro_anticipado(idioma), parse_mode="Markdown")
        return

    if data == "confirm_retiro_anticipado":
        calc, moneda, red = await db_exec(_db_retiro_confirmar_sync, user_id)
        if not calc:
            await query.message.edit_text("⚠️ Sin saldo activo.", reply_markup=obtener_menu_principal(idioma))
            return

        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"💸 **Retiro Anticipado Solicitado**\n\n"
                    f"• **Usuario ID:** `{user_id}`\n"
                    f"• **Red:** `{red}`\n"
                    f"• **Capital Base:** `{calc['capital_base']} {calc['moneda']}`\n"
                    f"• **Comisión Red:** `-{calc['comision_red']} {calc['moneda']}`\n"
                    f"• **Neto a Enviar:** `{calc['neto_a_recibir']} {calc['moneda']}`"
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            print(f"Error notificando retiro al admin: {e}", flush=True)

        texto_ok = (
            f"✅ **Retiro Anticipado Registrado**\n\n"
            f"• **Neto a Recibir:** `{calc['neto_a_recibir']} {calc['moneda']}`\n"
            f"• **Comisión Red:** `-{calc['comision_red']} {calc['moneda']}`\n"
            f"• **Ganancias:** `Anuladas por retiro anticipado`"
            if idioma == "es"
            else (
                f"✅ **Early Withdrawal Recorded**\n\n"
                f"• **Net to Receive:** `{calc['neto_a_recibir']} {calc['moneda']}`\n"
                f"• **Network Fee:** `-{calc['comision_red']} {calc['moneda']}`\n"
                f"• **Profits:** `Forfeited due to early withdrawal`"
            )
        )
        await query.message.edit_text(texto_ok, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")
        return

    if data == "cancel_retiro_anticipado":
        texto_cancel = (
            "👍 **Retiro cancelado.** Tu inversión sigue activa."
            if idioma == "es"
            else "👍 **Withdrawal cancelled.** Your investment remains active."
        )
        await query.message.edit_text(texto_cancel, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")


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

    if data == "btn_cambiar_idioma":
        await start(update, context)
        return

    if data.startswith("lang_"):
        nuevo_idioma = data.split("_")[1]
        await db_exec(_db_set_idioma_sync, user.id, user.first_name, nuevo_idioma)

        if nuevo_idioma == "en":
            texto = (
                f"🛡️ **Welcome to Invest Bot (5 Networks · USDT Ready)**\n\n"
                f"Hello, **{user.first_name}**. Minimum investment starts at **0.5 USDT**.\n\n"
                f"👇 **Select an option:**"
            )
        else:
            texto = (
                f"🛡️ **Bienvenido a Invierte Bot (5 Redes · USDT en Todas)**\n\n"
                f"Hola, **{user.first_name}**. Inversión mínima desde **0.5 USDT**.\n\n"
                f"👇 **Selecciona una opción:**"
            )

        try:
            await query.message.edit_text(texto, reply_markup=obtener_menu_principal(nuevo_idioma), parse_mode="Markdown")
        except Exception as e:
            print(f"Error al editar idioma: {e}", flush=True)
        return

    idioma = await db_exec(_db_obtener_idioma_sync, user.id)

    if data in ("btn_retirar", "confirm_retiro_anticipado", "cancel_retiro_anticipado"):
        await procesar_retiro_anticipado(update, context, idioma)
        return

    if data == "btn_saldo":
        row = await db_exec(_db_obtener_saldo_sync, user.id)
        if not row or not row[0] or float(row[0]) == 0:
            texto = (
                "💰 **Balance:** 0 USDT\n⚠️ No active investments (min 0.5 USDT)."
                if idioma == "en"
                else "💰 **Tu Balance Actual:**\n\n• Capital Activo: **0 USDT**\n⚠️ No tienes inversiones activas (mínimo 0.5 USDT)."
            )
        else:
            deposito, moneda, red, fecha_str, ganancia_ref = row
            dias = (datetime.now() - datetime.strptime(fecha_str, "%Y-%m-%d %H:%M:%S")).days if fecha_str else 0
            if idioma == "en":
                texto = (
                    f"💰 **Active Balance:**\n"
                    f"• Capital: `{deposito:g} {moneda}` ({red})\n"
                    f"• Days Active: `{dias}`\n"
                    f"• Referral Earnings: `{ganancia_ref or 0:.2f} {moneda}`\n"
                    f"• Early Exit: Forfeits profits + fee (`0.2` / `0.00001 BTC`)"
                )
            else:
                texto = (
                    f"💰 **Tu Balance Activo:**\n"
                    f"• Capital: `{deposito:g} {moneda}` ({red})\n"
                    f"• Días Activo: `{dias}`\n"
                    f"• Ganancias por Referidos: `{ganancia_ref or 0:.2f} {moneda}`\n"
                    f"• Retiro Anticipado: Pierdes ganancias + comisión (`0.2` / `0.00001 BTC`)"
                )
        try:
            await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")
        except Exception as e:
            print(f"Error en btn_saldo: {e}", flush=True)

    elif data == "btn_liquidez":
        fondo_actual = await db_exec(_db_obtener_liquidez_sync)
        texto = (
            f"🏦 **Fondo de Liquidez Global**\n\n"
            f"• **Reserva Actual:** `${fondo_actual:,.2f} USD`\n"
            f"• **Redes y USDT:** TRON, TON, BTC, BSC, ETH (USDT habilitado en todas)\n"
            f"• **Mínimo de Inversión:** `0.5 USDT`\n"
            f"• **Retiro Anticipado:** Disponible perdiendo ganancias + comisión de red."
        )
        try:
            await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")
        except Exception as e:
            print(f"Error en btn_liquidez: {e}", flush=True)

    elif data == "btn_historial":
        filas = await db_exec(_db_obtener_historial_sync, user.id)
        if not filas:
            texto = (
                "📜 **Historial de Inversiones:**\n\nAún no tienes inversiones registradas."
                if idioma == "es"
                else "📜 **Investment History:**\n\nYou have no recorded investments yet."
            )
        else:
            lineas = []
            for plan_id, monto, moneda, red, dias, fecha_ini, estado in filas:
                nombre_plan = (PLANES_INVERSION.get(str(plan_id)) or {}).get("nombre", f"Plan {plan_id}")
                fecha_corta = (fecha_ini or "")[:10]
                lineas.append(
                    f"• *{nombre_plan}* — `{float(monto):g} {moneda}` ({red})\n"
                    f"  Plazo: `{dias}d` | Estado: `{estado}` | Fecha: `{fecha_corta}`"
                )
            encabezado = "📜 **Tus Últimas Inversiones:**\n\n" if idioma == "es" else "📜 **Your Recent Investments:**\n\n"
            texto = encabezado + "\n\n".join(lineas)

        try:
            await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")
        except Exception as e:
            print(f"Error en btn_historial: {e}", flush=True)

    elif data == "btn_planes":
        bloques_planes = []
        for _, p in PLANES_INVERSION.items():
            rango = f"{p['min']:g}–{p['max']:g} {p['moneda']}"
            bloques_planes.append(
                f"🔹 *{p['nombre']}*\n"
                f"• Ciclo: `{p['tasa_ciclo']*100:.1f}%` | Rango: `{rango}`\n"
                f"• {p['detalle']}"
            )
        texto = (
            "📈 *Elige un Plan (Desde 0.5 USDT)*\n"
            "Toca un botón abajo para continuar:\n\n"
            + "\n\n".join(bloques_planes)
        )
        try:
            await query.message.edit_text(texto, reply_markup=teclado_planes_y_redes(idioma), parse_mode="Markdown")
        except Exception as e:
            print(f"Error en btn_planes: {e}", flush=True)

    elif data.startswith("sel_plan_"):
        plan_id = data.replace("sel_plan_", "")
        plan = PLANES_INVERSION.get(plan_id)
        if not plan:
            return
        context.user_data["plan_elegido"] = plan_id
        texto = (
            f"📌 **{plan['nombre']}**\n\n"
            f"• **Plazo:** `{plan['dias']} días` (0 = flexible)\n"
            f"• **Ciclo:** `{plan['tasa_ciclo']*100:.1f}%`\n"
            f"• **Límites:** `{plan['min']:g} - {plan['max']:g} {plan['moneda']}`\n\n"
            f"¿Quieres **Reinversión Automática** al terminar el ciclo?"
        )
        try:
            await query.message.edit_text(texto, reply_markup=teclado_reinversion(plan_id, idioma), parse_mode="Markdown")
        except Exception as e:
            print(f"Error en sel_plan: {e}", flush=True)

    elif data.startswith("reinv_"):
        partes = data.split("_")
        plan_id = partes[1]
        reinv_flag = partes[2] == "1"
        plan = PLANES_INVERSION.get(plan_id, PLANES_INVERSION["1"])
        context.user_data["plan_elegido"] = plan_id
        context.user_data["reinversion_auto"] = reinv_flag
        estado_reinv = "SÍ" if reinv_flag else "NO"

        texto = (
            f"💵 **Elige el Monto · {plan['nombre']}**\n"
            f"• **Reinversión Auto:** `{estado_reinv}`\n"
            f"• **Rango:** `{plan['min']:g} - {plan['max']:g} {plan['moneda']}`\n\n"
            f"Toca un monto rápido o elige **Otro monto**:"
        )
        try:
            await query.message.edit_text(texto, reply_markup=teclado_montos_inversion(plan_id, idioma), parse_mode="Markdown")
        except Exception as e:
            print(f"Error en reinv: {e}", flush=True)

    elif data.startswith("otro_monto_"):
        plan_id = data.replace("otro_monto_", "")
        plan = PLANES_INVERSION.get(plan_id, PLANES_INVERSION["1"])
        context.user_data["plan_elegido"] = plan_id
        await db_exec(_db_set_estado_sync, user.id, 1, 0, 0)

        texto = (
            f"✏️ **Escribe el Monto a Invertir**\n\n"
            f"• **Plan:** {plan['nombre']}\n"
            f"• **Permitido:** `{plan['min']:g}` a `{plan['max']:g} {plan['moneda']}`\n\n"
            f"Envía solo el número (ejemplo: `0.5` o `25`)."
        )
        try:
            await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")
        except Exception as e:
            print(f"Error en otro_monto: {e}", flush=True)

    elif data.startswith("monto_"):
        partes = data.split("_")
        plan_id = partes[1]
        monto_val = float(partes[2])
        plan = PLANES_INVERSION.get(plan_id, PLANES_INVERSION["1"])
        context.user_data["plan_elegido"] = plan_id
        context.user_data["monto_elegido"] = monto_val

        texto = (
            f"🌐 **Elige la Red de Pago (USDT en Todas)**\n\n"
            f"• **Plan:** {plan['nombre']}\n"
            f"• **Monto:** `{monto_val:g} {plan['moneda']}`\n\n"
            f"Toca la red que vas a usar:"
        )
        try:
            await query.message.edit_text(texto, reply_markup=teclado_redes_inversion(plan_id, monto_val, idioma), parse_mode="Markdown")
        except Exception as e:
            print(f"Error en monto: {e}", flush=True)

    elif data.startswith("invred_"):
        partes = data.split("_")
        plan_id = partes[1]
        monto_val = float(partes[2])
        red_solicitada = partes[3]
        if plan_id not in PLANES_INVERSION or red_solicitada not in WALLETS_OFICIALES:
            return
        reinv_flag = 1 if context.user_data.get("reinversion_auto") else 0
        texto = await registrar_solicitud_inversion(user.id, plan_id, monto_val, red_solicitada, reinv_flag)
        try:
            await query.message.edit_text(texto, reply_markup=teclado_tras_direccion(idioma), parse_mode="Markdown")
        except Exception as e:
            print(f"Error en invred: {e}", flush=True)

    elif data.startswith("red_"):
        red_key = data.replace("red_", "")
        info = REDES_INFO.get(red_key)
        wallet = WALLETS_OFICIALES.get(red_key, "")
        if info and wallet:
            await db_exec(_db_set_estado_sync, user.id, 0, 1, 0)
            texto = (
                f"💳 **{info['nombre']}**\n"
                f"• **Monedas (incluye USDT):** `{' / '.join(info['monedas'])}`\n"
                f"• **Dirección Oficial:**\n`{wallet}`\n\n"
                f"📩 **Tras realizar la transferencia, envía aquí el Hash / TXID** o toca **Enviar Hash / TXID**."
            )
            try:
                await query.message.edit_text(texto, reply_markup=teclado_tras_direccion(idioma), parse_mode="Markdown")
            except Exception as e:
                print(f"Error en red: {e}", flush=True)

    elif data == "btn_depositar":
        await db_exec(_db_set_estado_sync, user.id, 0, 1, 0)
        try:
            await query.message.edit_text(
                texto_wallets_deposito(idioma),
                reply_markup=teclado_tras_direccion(idioma),
                parse_mode="Markdown",
            )
        except Exception as e:
            print(f"Error en btn_depositar: {e}", flush=True)

    elif data == "enviar_hash_pago":
        await db_exec(_db_set_estado_sync, user.id, 0, 1, 0)
        texto = (
            "📩 **Enviar Hash de Transferencia**\n\n"
            "Pega aquí el **Hash / TXID** de la transacción que acabas de realizar:"
            if idioma == "es"
            else (
                "📩 **Send Transfer Hash**\n\n"
                "Paste here the **Hash / TXID** of the transfer you just made:"
            )
        )
        try:
            await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")
        except Exception as e:
            print(f"Error en enviar_hash_pago: {e}", flush=True)

    elif data == "btn_referidos":
        texto = construir_mensaje_referidos(context.bot.username, user.id, idioma)
        try:
            await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")
        except Exception as e:
            print(f"Error en btn_referidos: {e}", flush=True)

    elif data == "btn_soporte":
        await db_exec(_db_set_estado_sync, user.id, 0, 0, 1)
        texto = (
            "🎧 ¡Hola! Escríbeme aquí abajo qué duda tienes o qué necesitas revisar y lo vemos enseguida."
            if idioma == "es"
            else "🎧 Hey! Write below what you need help with or want us to check and we'll look into it right away."
        )
        try:
            await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")
        except Exception as e:
            print(f"Error en btn_soporte: {e}", flush=True)


async def mostrar_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def mostrar_planes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bloques_planes = []
    for _, p in PLANES_INVERSION.items():
        rango = f"{p['min']:g}–{p['max']:g} {p['moneda']}"
        bloques_planes.append(
            f"🔹 *{p['nombre']}*\n"
            f"• Ciclo: `{p['tasa_ciclo']*100:.1f}%` | Rango: `{rango}`\n"
            f"• {p['detalle']}"
        )
    texto = "📈 *Planes de Inversión (Desde 0.5 USDT)*\n\n" + "\n\n".join(bloques_planes)
    await update.message.reply_text(texto, reply_markup=teclado_planes_y_redes("es"), parse_mode="Markdown")


async def depositar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user:
        await db_exec(_db_set_estado_sync, update.effective_user.id, 0, 1, 0)
    await update.message.reply_text(
        texto_wallets_deposito("es"),
        reply_markup=teclado_tras_direccion("es"),
        parse_mode="Markdown",
    )


def _db_guardar_hash_sync(user_id: int, hash_tx: str, limpiar_estado: bool = True):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO comprobantes_verificados (tx_hash, red, moneda, monto, tipo, fecha) VALUES (?, ?, ?, ?, ?, ?)",
            (hash_tx, "TRON", "USDT", 0.0, "reporte_usuario", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        if limpiar_estado:
            cursor.execute("UPDATE usuarios SET esperando_hash = 0 WHERE user_id = ?", (user_id,))


async def notificar_deposito(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Uso: `/notificar [Hash]`", parse_mode="Markdown")
        return
    hash_tx = " ".join(context.args).strip()
    user_id = update.effective_user.id if update.effective_user else 0
    try:
        await db_exec(_db_guardar_hash_sync, user_id, hash_tx, False)
    except Exception:
        pass
    await update.message.reply_text(
        f"⏳ Comprobante recibido (`{hash_tx}`). En proceso de verificación.",
        parse_mode="Markdown",
    )


def _db_aprobar_deposito_sync(id_usuario: str, monto: float, moneda: str, red: str, tx_hash):
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    notificaciones = []
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE usuarios SET deposito_activo = deposito_activo + ?, moneda_deposito = ?, red_deposito = ?, fecha_deposito = ? WHERE user_id = ?",
            (monto, moneda, red, fecha_actual, id_usuario),
        )
        cursor.execute(
            """
            INSERT INTO inversiones (
                user_id, plan_id, modalidad, monto, moneda, red,
                reinversion_auto, dias_plazo, fecha_inicio, estado
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'activa')
            """,
            (id_usuario, "1", "plazo_fijo", monto, moneda, red, 0, 7, fecha_actual),
        )
        if tx_hash:
            cursor.execute(
                "INSERT OR IGNORE INTO comprobantes_verificados (tx_hash, red, moneda, monto, tipo, fecha) VALUES (?, ?, ?, ?, ?, ?)",
                (tx_hash, red, moneda, monto, "aprobado_admin", fecha_actual),
            )

        porcentajes_niveles = [0.03, 0.02, 0.01, 0.005]
        patrocinador_actual = id_usuario
        for nivel, porcentaje in enumerate(porcentajes_niveles, start=1):
            cursor.execute(
                "SELECT patrocinador_id FROM usuarios WHERE user_id = ?",
                (patrocinador_actual,),
            )
            resultado = cursor.fetchone()
            if not resultado or not resultado[0]:
                break
            patrocinador_id = resultado[0]
            comision = monto * porcentaje
            cursor.execute(
                "UPDATE usuarios SET ganancias_referidos = ganancias_referidos + ? WHERE user_id = ?",
                (comision, patrocinador_id),
            )
            notificaciones.append((
                patrocinador_id,
                f"🎁 **¡Comisión por Inversión en tu Red! (Nivel {nivel})**\n\n"
                f"• Has ganado: **{comision:.4f} {moneda}** ({porcentaje*100}%).",
            ))
            patrocinador_actual = patrocinador_id
    return notificaciones


async def aprobar_deposito(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or user.id != ADMIN_ID:
        return

    if len(context.args) < 3:
        await update.message.reply_text(
            "⚠️ Uso: `/aprobar [ID_Usuario] [Monto] [Moneda] [RED_OPCIONAL] [HASH_OPCIONAL]`",
            parse_mode="Markdown",
        )
        return

    id_usuario = context.args[0]
    try:
        monto = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ El monto debe ser un número válido.")
        return

    if monto < MIN_MONTO_INVERSION:
        await update.message.reply_text(f"❌ El monto mínimo permitido es `{MIN_MONTO_INVERSION:g}`.", parse_mode="Markdown")
        return

    moneda = context.args[2].upper()
    red = (
        context.args[3].upper()
        if len(context.args) >= 4 and context.args[3].upper() in WALLETS_OFICIALES
        else "TRON"
    )
    tx_hash = context.args[4].strip() if len(context.args) >= 5 else None

    notificaciones = await db_exec(
        _db_aprobar_deposito_sync, id_usuario, monto, moneda, red, tx_hash
    )

    for pat_id, msg in notificaciones:
        try:
            await context.bot.send_message(chat_id=pat_id, text=msg, parse_mode="Markdown")
        except Exception as e:
            print(f"No se pudo notificar al patrocinador {pat_id}: {e}", flush=True)

    await update.message.reply_text(
        f"✅ Depósito aprobado para `{id_usuario}`: `{monto:g} {moneda}` en `{red}`.",
        parse_mode="Markdown",
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
            await update.message.reply_text(
                "❌ Envía un número válido (ejemplo: `0.5` o `25`).",
                parse_mode="Markdown",
            )
            return

        if monto_val < plan["min"] or monto_val > plan["max"]:
            await update.message.reply_text(
                f"❌ El monto debe estar entre `{plan['min']:g}` y `{plan['max']:g} {plan['moneda']}`.",
                parse_mode="Markdown",
            )
            return

        context.user_data["monto_elegido"] = monto_val
        await update.message.reply_text(
            f"🌐 **Elige la Red de Pago (USDT en Todas)**\n\n"
            f"• **Plan:** {plan['nombre']}\n"
            f"• **Monto:** `{monto_val:g} {plan['moneda']}`\n\n"
            f"Toca la red que vas a usar:",
            reply_markup=teclado_redes_inversion(plan_id, monto_val, idioma),
            parse_mode="Markdown",
        )
        return

    if esperando_hash:
        await db_exec(_db_guardar_hash_sync, user.id, texto_msg, True)
        if ADMIN_ID:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        f"📲 **Nuevo Hash Reportado**\n\n"
                        f"• **Usuario:** {user.first_name} (`{user.id}`)\n"
                        f"• **Hash:** `{texto_msg}`"
                    ),
                    parse_mode="Markdown",
                )
            except Exception as e:
                print(f"Error notificando hash al admin: {e}", flush=True)

        await update.message.reply_text(
            f"⏳ Comprobante recibido (`{texto_msg}`). En proceso de verificación.",
            reply_markup=obtener_menu_principal(idioma),
            parse_mode="Markdown",
        )
        return

    if en_soporte:
        await db_exec(_db_set_estado_sync, user.id, 0, 0, 0)
        if ADMIN_ID:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        f"🎧 **Mensaje de Soporte**\n\n"
                        f"• **Usuario:** {user.first_name} (`{user.id}`)\n"
                        f"• **Mensaje:** {texto_msg}"
                    ),
                    parse_mode="Markdown",
                )
            except Exception as e:
                print(f"Error enviando soporte al admin: {e}", flush=True)

        await update.message.reply_text(
            "✅ ¡Listo! Ya pasé tu mensaje a soporte y te respondemos en cuanto lo revisemos.",
            reply_markup=obtener_menu_principal(idioma),
            parse_mode="Markdown",
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
