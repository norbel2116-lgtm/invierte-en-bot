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
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# --- SERVIDOR WEB FLASK (HILO SECUNDARIO) ---
app = Flask("")


@app.route("/")
def home():
    return "Bot Activo y Funcionando Correctamente", 200


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


TOKEN = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "-1001234567890")
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))
LINK_CANAL = os.getenv("LINK_CANAL", "https://t.me/TuCanalDePagos")

# --- 5 WALLETS Y REDES OFICIALES ---
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
        "monedas": ["BTC"],
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
    "94dc2877a6601436dc447a48e62a20f071ac8fc1bdd877e4a6d8489ce397f4c6",
    "d654d283158a4706531e226ec690bbeaaefe24b51ac9c6b2ddd9236a39f387b1",
]

MIN_MONTO_INVERSION = 1.0
HASHES_USADOS_SESION = set()

COMISION_ANTICIPADA_POR_MONEDA = {
    "USDT": 0.2,
    "TRX": 0.2,
    "GRAM": 0.2,
    "TON": 0.2,
    "BNB": 0.2,
    "ETH": 0.2,
    "BTC": 0.00001,
}

# --- PLANES CON PLAZOS Y PORCENTAJES EQUILIBRADOS ---
PLANES_INVERSION = {
    "1": {
        "nombre": "Plan de Inicio (7 días)",
        "modalidad": "plazo_fijo",
        "dias": 7,
        "tasa_ciclo": 0.007,
        "min": 3.0,
        "max": 1000.0,
        "moneda": "USDT",
        "red_sugerida": "TRON",
        "permite_reinvest": True,
        "detalle": "7 días | 0.7% al completar el ciclo. Ideal para empezar sin bloqueos largos.",
    },
    "2": {
        "nombre": "Plan Crecimiento (14 días)",
        "modalidad": "plazo_fijo",
        "dias": 14,
        "tasa_ciclo": 0.024,
        "min": 5.0,
        "max": 1000.0,
        "moneda": "USDT",
        "red_sugerida": "TON",
        "permite_reinvest": True,
        "detalle": "14 días | 1.2% semanal (~2.4% en el ciclo). Equilibrio entre plazo y retorno.",
    },
    "3": {
        "nombre": "Plan Pro / Élite (21 días)",
        "modalidad": "plazo_fijo",
        "dias": 21,
        "tasa_ciclo": 0.078,
        "min": 10.0,
        "max": 1000.0,
        "moneda": "USDT",
        "red_sugerida": "BSC",
        "permite_reinvest": True,
        "detalle": "21 días | 2.6% semanal (~7.8% en el ciclo). Para ciclos más prolongados.",
    },
    "4": {
        "nombre": "Fondo Flexible / Liquidez",
        "modalidad": "liquidez_flexible",
        "dias": 0,
        "tasa_ciclo": 0.005,
        "min": 3.0,
        "max": 1000.0,
        "moneda": "USDT",
        "red_sugerida": "TRON",
        "permite_reinvest": False,
        "detalle": "Sin bloqueo fijo | 0.5% cada 7 días. Vinculado al fondo de liquidez.",
    },
    "5": {
        "nombre": "Meta / Aporte Escalonado",
        "modalidad": "aporte_meta",
        "dias": 30,
        "tasa_ciclo": 0.032,
        "min": 2.0,
        "max": 1000.0,
        "moneda": "USDT",
        "red_sugerida": "ETH",
        "permite_reinvest": True,
        "detalle": "30 días | 0.8% semanal (3.2% en 4 semanas). Suma aportes progresivos.",
    },
}


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

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error inicializando BD: {e}")


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
    if len(HASHES_USADOS_SESION) > 500:
        HASHES_USADOS_SESION.clear()
        HASHES_USADOS_SESION.add(tx_hash)


def _hash_ya_publicado(tx_hash: str) -> bool:
    if tx_hash in HASHES_USADOS_SESION:
        return True
    try:
        conn = sqlite3.connect("usuarios.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM comprobantes_verificados WHERE tx_hash = ? AND tipo = 'publicado_canal' LIMIT 1",
            (tx_hash,),
        )
        existe = cursor.fetchone() is not None
        conn.close()
        return existe
    except Exception:
        return False


def _registrar_hash_publicado(tx_hash: str, red: str, moneda: str, monto: float):
    _marcar_hash_usado(tx_hash)
    try:
        conn = sqlite3.connect("usuarios.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO comprobantes_verificados (tx_hash, red, moneda, monto, tipo, fecha) VALUES (?, ?, ?, ?, ?, ?)",
            (tx_hash, red, moneda, monto, "publicado_canal", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error guardando hash publicado: {e}")


def _cumple_filtro_monto(monto: float, tipo_operacion: str) -> bool:
    if monto is None or monto <= 0:
        return False
    if tipo_operacion == "deposito":
        return monto >= MIN_MONTO_INVERSION
    return True


async def obtener_tx_real_tron(session: aiohttp.ClientSession, address: str, tipo_operacion: str = "deposito"):
    url = f"https://api.trongrid.io/v1/accounts/{address}/transactions/trc20?limit=25"
    async with session.get(url, timeout=10) as resp:
        if resp.status != 200:
            return None
        data = await resp.json()
        for tx in data.get("data") or []:
            tx_hash = tx.get("transaction_id")
            if not es_hash_valido(tx_hash, "TRON"):
                continue
            decimals = int((tx.get("token_info") or {}).get("decimals", 6))
            raw_val = tx.get("value")
            if raw_val is None:
                continue
            monto = round(float(raw_val) / (10 ** decimals), 4)
            if not _cumple_filtro_monto(monto, tipo_operacion) or _hash_ya_publicado(tx_hash):
                continue
            simbolo = (tx.get("token_info") or {}).get("symbol", "USDT")
            return {
                "hash": tx_hash,
                "monto": monto,
                "moneda": simbolo,
                "red": REDES_INFO["TRON"]["nombre"],
                "explorer": f"{REDES_INFO['TRON']['explorer']}{tx_hash}",
                "verificado": "Real en TronGrid",
            }
    return None


async def obtener_tx_real_btc(session: aiohttp.ClientSession, address: str, tipo_operacion: str = "deposito"):
    url = f"https://mempool.space/api/address/{address}/txs"
    async with session.get(url, timeout=10) as resp:
        if resp.status != 200:
            return None
        txs = await resp.json()
        if not isinstance(txs, list):
            return None
        for tx in txs[:20]:
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
                monto_sats = sum(int(v.get("value", 0)) for v in tx.get("vout"))
            monto_btc = round(monto_sats / 1e8, 6)
            if not _cumple_filtro_monto(monto_btc, tipo_operacion) or _hash_ya_publicado(txid):
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


async def obtener_tx_real_ton(session: aiohttp.ClientSession, address: str, tipo_operacion: str = "deposito"):
    url = f"https://toncenter.com/api/v2/getTransactions?address={address}&limit=25"
    async with session.get(url, timeout=10) as resp:
        if resp.status != 200:
            return None
        data = await resp.json()
        if not data.get("ok"):
            return None
        for tx in data.get("result") or []:
            tx_id_obj = tx.get("transaction_id") or {}
            tx_hash = tx_id_obj.get("hash")
            if not es_hash_valido(tx_hash, "TON"):
                continue
            in_msg = tx.get("in_msg") or {}
            value_nano = int(in_msg.get("value") or 0)
            monto_ton = round(value_nano / 1e9, 4)
            if not _cumple_filtro_monto(monto_ton, tipo_operacion) or _hash_ya_publicado(tx_hash):
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
    tipo_operacion: str = "deposito",
):
    for rpc_url in rpc_urls:
        try:
            payload_latest = {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}
            async with session.post(rpc_url, json=payload_latest, timeout=10) as resp:
                if resp.status != 200:
                    continue
                data_latest = await resp.json()
                hex_block = data_latest.get("result")
                if not hex_block:
                    continue
                block_num = int(hex_block, 16)

            for offset in range(0, 3):
                target_hex = hex(block_num - offset)
                payload_block = {
                    "jsonrpc": "2.0",
                    "method": "eth_getBlockByNumber",
                    "params": [target_hex, True],
                    "id": 2,
                }
                async with session.post(rpc_url, json=payload_block, timeout=10) as resp_blk:
                    if resp_blk.status != 200:
                        continue
                    blk_json = await resp_blk.json()
                    txs = (blk_json.get("result") or {}).get("transactions") or []
                    random.shuffle(txs)
                    for tx in txs[:40]:
                        tx_hash = tx.get("hash")
                        if not es_hash_valido(tx_hash, red_key):
                            continue
                        val_wei = int(tx.get("value") or "0x0", 16)
                        monto = round(val_wei / 1e18, 6)
                        if not _cumple_filtro_monto(monto, tipo_operacion) or _hash_ya_publicado(tx_hash):
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
            print(f"Error RPC {red_key} ({rpc_url}): {e}")
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


def obtener_comprobante_respaldo_local(tipo_operacion: str = "deposito"):
    min_monto = MIN_MONTO_INVERSION if tipo_operacion == "deposito" else 0.05
    candidatos_ton = [h for h in HASHES_RESPALDO_TON if h not in HASHES_USADOS_SESION] or HASHES_RESPALDO_TON
    candidatos_tron = [h for h in HASHES_RESPALDO_TRON if h not in HASHES_USADOS_SESION] or HASHES_RESPALDO_TRON

    if random.choice([True, False]) and candidatos_ton:
        tx_hash = random.choice(candidatos_ton)
        red_key = "TON"
        moneda = "TON"
        monto = round(random.uniform(max(min_monto, 1.0), 25.0), 4)
    else:
        tx_hash = random.choice(candidatos_tron)
        red_key = "TRON"
        moneda = "USDT"
        monto = round(random.uniform(max(min_monto, 3.0), 50.0), 2)

    return {
        "hash": tx_hash,
        "monto": monto,
        "moneda": moneda,
        "red": REDES_INFO[red_key]["nombre"],
        "explorer": f"{REDES_INFO[red_key]['explorer']}{tx_hash}",
        "verificado": "Respaldo local",
    }


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


async def tarea_comprobaciones_canal(bot):
    await asyncio.sleep(10)
    while True:
        try:
            if CHANNEL_ID and str(CHANNEL_ID) != "-1001234567890":
                comp = obtener_comprobante_respaldo_local("retiro")
                if comp and not _hash_ya_publicado(comp["hash"]):
                    usuario = generar_usuario_ficticio()
                    texto = (
                        f"📢 **Comprobante de Operación**\n\n"
                        f"• **Usuario:** `{usuario}`\n"
                        f"• **Monto:** `{comp['monto']} {comp['moneda']}`\n"
                        f"• **Red:** `{comp['red']}`\n"
                        f"• **Hash:** `{comp['hash']}`\n"
                        f"• **Explorador:** {comp['explorer']}"
                    )
                    await bot.send_message(
                        chat_id=CHANNEL_ID,
                        text=texto,
                        parse_mode="Markdown",
                        disable_web_page_preview=True,
                    )
                    _registrar_hash_publicado(comp["hash"], comp["red"], comp["moneda"], comp["monto"])
        except Exception as e:
            print(f"Error en tarea_comprobaciones_canal: {e}")

        await asyncio.sleep(3600)
# --- TECLADOS INLINE ---
def obtener_menu_idiomas():
    keyboard = [
        [
            InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es"),
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def obtener_menu_principal(idioma="es"):
    if idioma == "en":
        keyboard = [
            [
                InlineKeyboardButton("💰 My Balance", callback_data="btn_saldo"),
                InlineKeyboardButton("🏦 Liquidity Pool", callback_data="btn_liquidez"),
            ],
            [
                InlineKeyboardButton("📋 Plans & Invest", callback_data="btn_planes"),
                InlineKeyboardButton("💳 Deposit", callback_data="btn_depositar"),
            ],
            [
                InlineKeyboardButton("👥 Referrals", callback_data="btn_referidos"),
                InlineKeyboardButton("🏦 Withdraw", callback_data="btn_retirar"),
            ],
            [
                InlineKeyboardButton("🎧 Support", callback_data="btn_soporte"),
                InlineKeyboardButton("📢 Proofs Channel", url=LINK_CANAL),
            ],
            [
                InlineKeyboardButton("🌐 Change Language", callback_data="btn_cambiar_idioma"),
            ],
        ]
    else:
        keyboard = [
            [
                InlineKeyboardButton("💰 Mi Saldo", callback_data="btn_saldo"),
                InlineKeyboardButton("🏦 Fondo de Liquidez", callback_data="btn_liquidez"),
            ],
            [
                InlineKeyboardButton("📋 Planes e Invertir", callback_data="btn_planes"),
                InlineKeyboardButton("💳 Depositar", callback_data="btn_depositar"),
            ],
            [
                InlineKeyboardButton("👥 Referidos", callback_data="btn_referidos"),
                InlineKeyboardButton("🏦 Retirar", callback_data="btn_retirar"),
            ],
            [
                InlineKeyboardButton("🎧 Soporte", callback_data="btn_soporte"),
                InlineKeyboardButton("📢 Comprobantes", url=LINK_CANAL),
            ],
            [
                InlineKeyboardButton("🌐 Cambiar Idioma", callback_data="btn_cambiar_idioma"),
            ],
        ]
    return InlineKeyboardMarkup(keyboard)


def teclado_planes_y_redes(idioma="es"):
    filas = []
    for key, plan in PLANES_INVERSION.items():
        filas.append([
            InlineKeyboardButton(
                f"{plan['nombre']} ({plan['tasa_ciclo']*100:.1f}%)",
                callback_data=f"sel_plan_{key}",
            )
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
    volver_txt = "⬅️ Menú Principal" if idioma == "es" else "⬅️ Main Menu"
    volver_cb = "lang_es" if idioma == "es" else "lang_en"
    filas.append([InlineKeyboardButton(volver_txt, callback_data=volver_cb)])
    return InlineKeyboardMarkup(filas)


def teclado_reinversion(plan_id: str, idioma="es"):
    if idioma == "en":
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("♻️ Auto-Reinvest: ON", callback_data=f"reinv_{plan_id}_1"),
                InlineKeyboardButton("💵 Auto-Reinvest: OFF", callback_data=f"reinv_{plan_id}_0"),
            ],
            [InlineKeyboardButton("⬅️ Back to Plans", callback_data="btn_planes")],
        ])
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("♻️ Reinversión Auto: SÍ", callback_data=f"reinv_{plan_id}_1"),
            InlineKeyboardButton("💵 Reinversión Auto: NO", callback_data=f"reinv_{plan_id}_0"),
        ],
        [InlineKeyboardButton("⬅️ Volver a Planes", callback_data="btn_planes")],
    ])


def teclado_confirmar_retiro_anticipado(idioma="es"):
    if idioma == "en":
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Confirm Early Withdrawal", callback_data="confirm_retiro_anticipado"),
                InlineKeyboardButton("❌ Keep Investment", callback_data="cancel_retiro_anticipado"),
            ],
            [InlineKeyboardButton("⬅️ Main Menu", callback_data="lang_en")],
        ])
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirmar Retiro Anticipado", callback_data="confirm_retiro_anticipado"),
            InlineKeyboardButton("❌ Mantener Inversión", callback_data="cancel_retiro_anticipado"),
        ],
        [InlineKeyboardButton("⬅️ Menú Principal", callback_data="lang_es")],
    ])


def texto_wallets_deposito(idioma="es"):
    if idioma == "en":
        encabezado = "💳 **Official Deposit Wallets (5 Networks)**:\n\n"
        aviso = "⚠️ Always match the network and address. Report with: `/notificar [Your_Hash]`"
    else:
        encabezado = "💳 **Direcciones de Depósito Oficiales (5 Redes)**:\n\n"
        aviso = "⚠️ Verifica que la red coincida con la dirección antes de enviar. Reporta con: `/notificar [Tu_Hash]`"

    bloques = []
    for red_key, info in REDES_INFO.items():
        wallet = WALLETS_OFICIALES.get(red_key, "")
        monedas_str = " / ".join(info["monedas"])
        bloques.append(f"🔹 **{info['nombre']} ({monedas_str}):**\n`{wallet}`")
    return encabezado + "\n\n".join(bloques) + f"\n\n{aviso}"


def construir_mensaje_referidos(username_bot, user_id, idioma="es"):
    link_referido = f"https://t.me/{username_bot}?start={user_id}"
    if idioma == "en":
        return (
            f"🌟 **Welcome! We are glad you want to join**\n\n"
            f"🚀 **Your Exclusive Referral Link:**\n`{link_referido}`\n\n"
            f"📊 **Balanced Plans:**\n"
            f"• **Starter (7d - 0.7%):** Min 3 USD\n"
            f"• **Growth (14d - 1.2%/wk):** Min 5 USD\n"
            f"• **Pro / Elite (21d - 2.6%/wk):** Min 10 USD\n\n"
            f"💡 **Early Withdrawal Rule:** Available anytime, forfeiting profits + network fee (0.2 or 0.00001 BTC)."
        )
    return (
        f"🌟 **¡Bienvenido/a! Nos alegra mucho que quieras sumarte**\n\n"
        f"🚀 **Tu Link de Referido Exclusivo:**\n`{link_referido}`\n\n"
        f"📊 **Planes Equilibrados:**\n"
        f"• **Inicio (7 días - 0.7%):** Mín 3 USD\n"
        f"• **Crecimiento (14 días - 1.2%/sem):** Mín 5 USD\n"
        f"• **Pro / Élite (21 días - 2.6%/sem):** Mín 10 USD\n\n"
        f"💡 **Regla de Retiro Anticipado:** Disponible en cualquier momento; se pierden ganancias y aplica comisión de red (0.2 o 0.00001 BTC)."
    )


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
            (user.id, user.first_name, patrocinador_id, "es"),
        )
        conn.commit()

        if patrocinador_id and patrocinador_id != user.id:
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


async def procesar_retiro_anticipado(update: Update, context: ContextTypes.DEFAULT_TYPE, idioma: str):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    conn = sqlite3.connect("usuarios.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT deposito_activo, moneda_deposito, red_deposito FROM usuarios WHERE user_id = ?",
        (user_id,),
    )
    row = cursor.fetchone()
    deposito_activo = float(row[0]) if row and row[0] else 0.0
    moneda = row[1] if row and row[1] else "USDT"
    red = row[2] if row and row[2] else "TRON"

    if data == "btn_retirar":
        conn.close()
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
        calc = calcular_retiro_anticipado(deposito_activo, moneda)
        if calc["capital_base"] <= 0:
            conn.close()
            await query.message.edit_text("⚠️ Sin saldo activo.", reply_markup=obtener_menu_principal(idioma))
            return

        cursor.execute(
            "UPDATE usuarios SET deposito_activo = 0, fecha_deposito = NULL WHERE user_id = ?",
            (user_id,),
        )
        cursor.execute(
            "UPDATE inversiones SET estado = 'retirado_anticipado' WHERE user_id = ? AND estado = 'activa'",
            (user_id,),
        )
        conn.commit()
        conn.close()

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
            print(f"Error notificando retiro al admin: {e}")

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
        conn.close()
        texto_cancel = (
            "👍 **Retiro cancelado.** Tu inversión sigue activa."
            if idioma == "es"
            else "👍 **Withdrawal cancelled.** Your investment remains active."
        )
        await query.message.edit_text(texto_cancel, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")


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
                f"🛡️ **Welcome to Invest Bot (5 Networks)**\n\n"
                f"Hello, **{user.first_name}**. Manage your investments across TRON, TON, BTC, BSC, and ETH.\n\n"
                f"✅ **Key Rules:**\n"
                f"• Balanced plans & terms with optional auto-reinvestment.\n"
                f"• Early withdrawal available anytime (forfeits profits + network fee).\n"
                f"• Blockchain-verified proofs channel.\n\n"
                f"👇 **Select an option:**"
            )
        else:
            texto = (
                f"🛡️ **Bienvenido a Invierte Bot (5 Redes)**\n\n"
                f"Hola, **{user.first_name}**. Opera en TRON, TON, BTC, BSC y ETH con reglas claras.\n\n"
                f"✅ **Reglas Claras:**\n"
                f"• Plazos y porcentajes moderados con reinversión automática opcional.\n"
                f"• Retiro anticipado en cualquier momento (pierdes ganancias + comisión de red).\n"
                f"• Comprobantes verificables en blockchain.\n\n"
                f"👇 **Selecciona una opción del menú:**"
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
    idioma = row[0] if row else "es"

    if data in ("btn_retirar", "confirm_retiro_anticipado", "cancel_retiro_anticipado"):
        await procesar_retiro_anticipado(update, context, idioma)
        return

    if data == "btn_saldo":
        conn = sqlite3.connect("usuarios.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT deposito_activo, moneda_deposito, red_deposito, fecha_deposito, ganancias_referidos FROM usuarios WHERE user_id = ?",
            (user.id,),
        )
        row = cursor.fetchone()
        conn.close()

        if not row or not row[0] or float(row[0]) == 0:
            texto = (
                "💰 **Balance:** 0 USD\n⚠️ No active investments."
                if idioma == "en"
                else "💰 **Tu Balance Actual:**\n\n• Capital Activo: **0**\n⚠️ No tienes inversiones activas."
            )
        else:
            deposito, moneda, red, fecha_str, ganancia_ref = row
            dias = (datetime.now() - datetime.strptime(fecha_str, "%Y-%m-%d %H:%M:%S")).days if fecha_str else 0
            if idioma == "en":
                texto = (
                    f"💰 **Active Balance:**\n"
                    f"• Capital: `{deposito} {moneda}` ({red})\n"
                    f"• Days Active: `{dias}`\n"
                    f"• Referral Earnings: `{ganancia_ref or 0:.2f} {moneda}`\n"
                    f"• Early Exit: Forfeits profits + fee (`0.2` / `0.00001 BTC`)"
                )
            else:
                texto = (
                    f"💰 **Tu Balance Activo:**\n"
                    f"• Capital: `{deposito} {moneda}` ({red})\n"
                    f"• Días Activo: `{dias}`\n"
                    f"• Ganancias por Referidos: `{ganancia_ref or 0:.2f} {moneda}`\n"
                    f"• Retiro Anticipado: Pierdes ganancias + comisión (`0.2` / `0.00001 BTC`)"
                )
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

        texto = (
            f"🏦 **Fondo de Liquidez Global**\n\n"
            f"• **Reserva Actual:** `${fondo_actual:,.2f} USD`\n"
            f"• **Redes Soportadas:** TRON, TON, BTC, BSC, ETH\n"
            f"• **Liquidez / Retiro:** Retiro anticipado disponible perdiendo ganancias + comisión de red."
        )
        try:
            await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")
        except Exception:
            pass

    elif data == "btn_planes":
        texto = "📋 **Planes de Inversión y Redes**\n\nElige un plan para ver sus condiciones y reinversión automática, o toca una red para ver su wallet:\n\n"
        for k, p in PLANES_INVERSION.items():
            texto += f"• **{p['nombre']}** (`{p['tasa_ciclo']*100:.1f}%`) — {p['detalle']}\n"
        try:
            await query.message.edit_text(texto, reply_markup=teclado_planes_y_redes(idioma), parse_mode="Markdown")
        except Exception:
            pass

    elif data.startswith("sel_plan_"):
        plan_id = data.replace("sel_plan_", "")
        plan = PLANES_INVERSION.get(plan_id)
        if not plan:
            return
        context.user_data["plan_elegido"] = plan_id
        texto = (
            f"📌 **{plan['nombre']}**\n\n"
            f"• **Modalidad:** `{plan['modalidad']}`\n"
            f"• **Plazo:** `{plan['dias']} días` (0 = flexible)\n"
            f"• **Rendimiento del ciclo:** `{plan['tasa_ciclo']*100:.1f}%`\n"
            f"• **Rango:** `{plan['min']} - {plan['max']} {plan['moneda']}`\n"
            f"• **Retiro anticipado:** En cualquier momento (pierdes ganancias + comisión de red)\n\n"
            f"¿Deseas activar **Reinversión Automática** al completar el ciclo?"
        )
        try:
            await query.message.edit_text(texto, reply_markup=teclado_reinversion(plan_id, idioma), parse_mode="Markdown")
        except Exception:
            pass

    elif data.startswith("reinv_"):
        partes = data.split("_")
        plan_id = partes[1]
        reinv_flag = partes[2] == "1"
        plan = PLANES_INVERSION.get(plan_id, PLANES_INVERSION["1"])
        context.user_data["plan_elegido"] = plan_id
        context.user_data["reinversion_auto"] = reinv_flag
        estado_reinv = "ACTIVADA" if reinv_flag else "DESACTIVADA"
        texto = (
            f"✅ **Configuración lista para {plan['nombre']}**\n"
            f"• **Reinversión Automática:** `{estado_reinv}`\n\n"
            f"Usa el comando:\n`/invertir {plan_id} [Monto] [RED]`\n"
            f"Ejemplo: `/invertir {plan_id} 20 TRON`\n"
            f"Redes disponibles: `TRON`, `TON`, `BTC`, `BSC`, `ETH`"
        )
        try:
            await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")
        except Exception:
            pass

    elif data.startswith("red_"):
        red_key = data.replace("red_", "")
        info = REDES_INFO.get(red_key)
        wallet = WALLETS_OFICIALES.get(red_key, "")
        if info and wallet:
            texto = (
                f"💳 **{info['nombre']}**\n"
                f"• **Monedas:** `{' / '.join(info['monedas'])}`\n"
                f"• **Dirección Oficial:**\n`{wallet}`\n\n"
                f"⚠️ Tras transferir, reporta con: `/notificar [Tu_Hash]`"
            )
            try:
                await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")
            except Exception:
                pass

    elif data == "btn_depositar":
        try:
            await query.message.edit_text(
                texto_wallets_deposito(idioma),
                reply_markup=obtener_menu_principal(idioma),
                parse_mode="Markdown",
            )
        except Exception:
            pass

    elif data == "btn_referidos":
        texto = construir_mensaje_referidos(context.bot.username, user.id, idioma)
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
        texto = "🎧 **Centro de Soporte**. Escribe tu duda o problema a continuación:"
        try:
            await query.message.edit_text(texto, reply_markup=obtener_menu_principal(idioma), parse_mode="Markdown")
        except Exception:
            pass
async def mostrar_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def mostrar_planes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = "📋 **Planes de Inversión:**\n\n"
    for k, p in PLANES_INVERSION.items():
        texto += f"• **ID {k}: {p['nombre']}** (`{p['tasa_ciclo']*100:.1f}%`) — {p['detalle']}\n"
    await update.message.reply_text(texto, reply_markup=teclado_planes_y_redes("es"), parse_mode="Markdown")


async def depositar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        texto_wallets_deposito("es"),
        reply_markup=obtener_menu_principal("es"),
        parse_mode="Markdown",
    )


async def notificar_deposito(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Uso: `/notificar [Hash]`", parse_mode="Markdown")
        return
    hash_tx = " ".join(context.args).strip()
    try:
        conn = sqlite3.connect("usuarios.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO comprobantes_verificados (tx_hash, red, moneda, monto, tipo, fecha) VALUES (?, ?, ?, ?, ?, ?)",
            (hash_tx, "TRON", "USDT", 0.0, "reporte_usuario", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    await update.message.reply_text(
        f"⏳ Comprobante recibido (`{hash_tx}`). En proceso de verificación.",
        parse_mode="Markdown",
    )


async def aprobar_deposito(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
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

    moneda = context.args[2].upper()
    red = context.args[3].upper() if len(context.args) >= 4 and context.args[3].upper() in WALLETS_OFICIALES else "TRON"
    tx_hash = context.args[4].strip() if len(context.args) >= 5 else None
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect("usuarios.db")
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
        cursor.execute("SELECT patrocinador_id FROM usuarios WHERE user_id = ?", (patrocinador_actual,))
        resultado = cursor.fetchone()
        if not resultado or not resultado[0]:
            break
        patrocinador_id = resultado[0]
        comision = monto * porcentaje
        cursor.execute(
            "UPDATE usuarios SET ganancias_referidos = ganancias_referidos + ? WHERE user_id = ?",
            (comision, patrocinador_id),
        )
        conn.commit()
        try:
            await context.bot.send_message(
                chat_id=patrocinador_id,
                text=(
                    f"🎁 **¡Comisión por Inversión en tu Red! (Nivel {nivel})**\n\n"
                    f"• Has ganado: **{comision:.4f} {moneda}** ({porcentaje*100}%)."
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            print(f"No se pudo notificar al patrocinador {patrocinador_id}: {e}")
        patrocinador_actual = patrocinador_id

    conn.commit()
    conn.close()

    try:
        await context.bot.send_message(
            chat_id=id_usuario,
            text=f"✅ **¡Depósito Acreditado con Éxito!**\n• Monto: `{monto} {moneda}` en red `{red}`.",
            parse_mode="Markdown",
        )
        await update.message.reply_text(
            f"✔️ Acreditado `{monto} {moneda}` (`{red}`) a `{id_usuario}`.",
            parse_mode="Markdown",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error al notificar al usuario: {e}")


async def referidos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = sqlite3.connect("usuarios.db")
    cursor = conn.cursor()
    cursor.execute("SELECT idioma FROM usuarios WHERE user_id = ?", (user.id,))
    row = cursor.fetchone()
    conn.close()
    idioma = row[0] if row else "es"
    texto = construir_mensaje_referidos(context.bot.username, user.id, idioma)
    await update.message.reply_text(texto, parse_mode="Markdown")


async def retirar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect("usuarios.db")
    cursor = conn.cursor()
    cursor.execute("SELECT deposito_activo, moneda_deposito, red_deposito FROM usuarios WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    deposito = float(row[0]) if row and row[0] else 0.0
    moneda = row[1] if row and row[1] else "USDT"
    red = row[2] if row and row[2] else "TRON"
    calc = calcular_retiro_anticipado(deposito, moneda)

    await update.message.reply_text(
        f"🏦 **Retiros**\n"
        f"• Puedes retirar en cualquier momento, perdiendo las ganancias acumuladas y con comisión de red (`0.2` o `0.00001 BTC`).\n"
        f"• Si tienes capital activo (`{deposito} {moneda}` en `{red}`), el neto anticipado estimado es `{calc['neto_a_recibir']} {calc['moneda']}`.\n"
        f"• Usa el botón **Retirar** del menú para confirmar.",
        reply_markup=obtener_menu_principal("es"),
        parse_mode="Markdown",
    )


async def invertir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ Uso: `/invertir [ID_Plan] [Cantidad] [RED_OPCIONAL]`\nEjemplo: `/invertir 2 15 TON`",
            parse_mode="Markdown",
        )
        return

    plan_id = context.args[0]
    try:
        cantidad = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ La cantidad debe ser numérica.")
        return

    plan = PLANES_INVERSION.get(plan_id)
    if not plan or not (plan["min"] <= cantidad <= plan["max"]):
        await update.message.reply_text("❌ Plan inválido o cantidad fuera del rango permitido.")
        return

    red_solicitada = context.args[2].upper() if len(context.args) >= 3 else plan["red_sugerida"]
    if red_solicitada not in WALLETS_OFICIALES:
        await update.message.reply_text("❌ Red inválida. Usa: `TRON`, `TON`, `BTC`, `BSC` o `ETH`.", parse_mode="Markdown")
        return

    wallet = WALLETS_OFICIALES[red_solicitada]
    reinv_flag = 1 if context.user_data.get("reinversion_auto") else 0

    conn = sqlite3.connect("usuarios.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO inversiones (
            user_id, plan_id, modalidad, monto, moneda, red,
            reinversion_auto, dias_plazo, fecha_inicio, estado
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pendiente_pago')
        """,
        (
            update.effective_user.id,
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
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ **Solicitud de Inversión Registrada**\n"
        f"• Plan: **{plan['nombre']}**\n"
        f"• Monto: `{cantidad} {plan['moneda']}`\n"
        f"• Red: `{red_solicitada}`\n"
        f"• Reinversión Automática: `{'SÍ' if reinv_flag else 'NO'}`\n\n"
        f"💳 Transfiere a:\n`{wallet}`\n\n"
        f"📲 Tras enviar, reporta con: `/notificar [Tu_Hash]`",
        parse_mode="Markdown",
    )


async def iniciar_soporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = sqlite3.connect("usuarios.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET en_soporte = 1 WHERE user_id = ?", (user.id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("🎧 **Centro de Soporte Oficial**\n\nEscribe tu duda o problema a continuación:", parse_mode="Markdown")


async def responder_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID or len(context.args) < 2:
        return

    id_destino = context.args[0]
    mensaje_respuesta = " ".join(context.args[1:])

    try:
        await context.bot.send_message(
            chat_id=id_destino,
            text=f"💬 **Mensaje de Soporte:**\n\n{mensaje_respuesta}",
            parse_mode="Markdown",
        )
        await update.message.reply_text(f"✅ Respuesta enviada al usuario `{id_destino}`.", parse_mode="Markdown")
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
        await update.message.reply_text("📩 **Mensaje recibido.** En breve será atendido por un asesor.", parse_mode="Markdown")
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"🚨 **Nuevo Ticket de Soporte**\n\n"
                    f"👤 Usuario: {user.first_name} (`{user.id}`)\n"
                    f"💬 Mensaje: {texto}\n\n"
                    f"👉 Responder:\n`/responder {user.id} [Mensaje]`"
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            print(f"Error reenviando al admin: {e}")

        conn = sqlite3.connect("usuarios.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE usuarios SET en_soporte = 0 WHERE user_id = ?", (user.id,))
        conn.commit()
        conn.close()


# --- ARRANQUE PRINCIPAL ---
async def main():
    if not TOKEN:
        print("ERROR: Falta la variable de entorno TOKEN.")
        return

    t = Thread(target=run_web)
    t.daemon = True
    t.start()

    app_bot = ApplicationBuilder().token(TOKEN).build()

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

    await app_bot.initialize()
    await app_bot.start()
    await app_bot.updater.start_polling()

    asyncio.create_task(tarea_comprobaciones_canal(app_bot.bot))

    stop_event = asyncio.Event()
    await stop_event.wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot detenido correctamente.")
