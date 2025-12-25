import telebot
import json
import os
import time
import requests
from telebot import types
from datetime import datetime

# --- CONFIGURACIÓN ---
TOKEN = "8531717834:AAExJEm2EI6Zce7ZKtyJfKb-qHPuMbCZyoE"
ADMIN_ID = "6280594821"  # Tu ID de Telegram
PLISIO_API_KEY = "N8pUsjMMygSzk3NytnvW1rHjRQq6tw0U3q7BgAC9yxlzHOwM8eABpsAJh5HDYK4k"

# Estrategias de límites para evitar KYC
LIMITE_KYC_USD = 50.0 
LIMITE_KYC_MXN = 900.0
COMISION_RETIRO = 0.15 # 15%

bot = telebot.TeleBot(TOKEN)
DB_FILE = "database_segura.json"

# --- GESTIÓN DE BASE DE DATOS ---
def cargar_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: return json.load(f)
    return {}

def guardar_db(db):
    with open(DB_FILE, "w") as f: json.dump(db, f, indent=4)

# --- PASARELA DE PAGO (ENTRADA: CC -> BINANCE USDT) ---
def crear_orden_plisio(monto, moneda, uid):
    # Convertimos a USD para la pasarela si es necesario
    monto_pago = monto if moneda == "USD" else (monto / 20) 
    
    url = "https://plisio.net/api/v1/invoices/new"
    params = {
        'api_key': PLISIO_API_KEY,
        'currency': 'USDT_TRC20',     # Lo que recibes
        'source_currency': 'USD',     # Moneda de cobro tarjeta
        'source_amount': monto_pago,
        'order_number': f"PAY_{uid}_{int(time.time())}",
        'order_name': 'Nexus Digital Assets',
        'email': 'pago@nexus.com' 
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if data['status'] == 'success':
            return data['data']['invoice_url']
        return None
    except Exception as e:
        print(f"Error en Plisio: {e}")
        return None

# --- COMANDOS DE INICIO ---
@bot.message_handler(commands=['start'])
def start(message):
    db = cargar_db()
    uid = str(message.from_user.id)
    if uid not in db:
        db[uid] = {
            "saldo": 0, 
            "nombre": message.from_user.first_name, 
            "racha_derrotas": 0,
            "compras_exitosas": 0,
            "historial": []
        }
        guardar_db(db)
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("👤 Perfil", "💎 Recargar")
    markup.add("🎲 Jugar", "🏦 Retirar")
    
    bot.send_message(message.chat.id, 
        f"👋 ¡Bienvenido, {message.from_user.first_name}!\n\n"
        f"💰 Tu saldo: `${db[uid]['saldo']} MXN`", 
        parse_mode="Markdown", reply_markup=markup)

# --- SISTEMA DE JUEGO (CASA GANA + ENGANCHE) ---
@bot.message_handler(func=lambda m: m.text == "🎲 Jugar")
def menu_juego(message):
    bot.send_message(message.chat.id, "🎰 *DADOS CASINO*\n\nGanas si sale **6**.\nUsa `/apostar [monto]`\nEjemplo: `/apostar 50`", parse_mode="Markdown")

@bot.message_handler(commands=['apostar'])
def apostar_coins(message):
    db = cargar_db()
    uid = str(message.from_user.id)
    if uid not in db: return
    
    try:
        monto_apuesta = float(message.text.split()[1])
        if monto_apuesta > db[uid]['saldo'] or monto_apuesta <= 0:
            return bot.reply_to(message, "❌ Saldo insuficiente o monto inválido.")
        
        msg_dado = bot.send_dice(message.chat.id, emoji='🎲')
        valor_dado = msg_dado.dice.value
        time.sleep(3.5) # Tiempo para que ruede el dado
        
        gano = False
        # Estrategia de Enganche: Si lleva 5 pérdidas, la 6ta gana sí o sí
        if db[uid].get("racha_derrotas", 0) >= 5:
            gano = True
            db[uid]["racha_derrotas"] = 0
        elif valor_dado == 6:
            gano = True
            db[uid]["racha_derrotas"] = 0
        else:
            db[uid]["racha_derrotas"] = db[uid].get("racha_derrotas", 0) + 1

        if gano:
            db[uid]['saldo'] += monto_apuesta
            bot.send_message(message.chat.id, f"🎉 ¡Ganaste! Salió {valor_dado}. Ganaste `${monto_apuesta}`.")
        else:
            db[uid]['saldo'] -= monto_apuesta
            bot.send_message(message.chat.id, f"💀 Perdiste. Salió {valor_dado}. ¡Suerte a la próxima!")
        
        guardar_db(db)
    except:
        bot.reply_to(message, "❌ Uso: `/apostar 10`")

# --- MENÚ DE RECARGA (ESTRATEGIA ANTI-KYC) ---
@bot.message_handler(func=lambda m: m.text == "💎 Recargar")
def menu_recarga(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_mx = types.InlineKeyboardButton("🇲🇽 Tarjeta Nacional (MXN)", callback_data="buy_mxn")
    btn_int = types.InlineKeyboardButton("🌎 Tarjeta Internacional (USD)", callback_data="buy_usd")
    markup.add(btn_mx, btn_int)
    bot.send_message(message.chat.id, "💎 *CENTRO DE CARGA*\nSelecciona origen de tu tarjeta:", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('p_'))
def seleccionar_monto(call):
    # IMPORTANTE: Detener el relojito de carga en el botón
    bot.answer_callback_query(call.id)
    
    moneda = "MXN" if "mxn" in call.data else "USD"
    
    # Borramos el mensaje anterior (el de elegir tarjeta) para limpiar el chat
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass

    # Enviamos la pregunta
    msg = bot.send_message(
        call.message.chat.id, 
        f"💰 ¿Cuánto deseas recargar en **{moneda}**?\n\n_Escribe solo el número (ejemplo: 100)_", 
        parse_mode="Markdown"
    )
    
    # Registramos el siguiente paso
    bot.register_next_step_handler(msg, generar_pago, moneda)

def generar_pago(message, moneda):
    try:
        # Limpiamos el texto por si el usuario pone '$' o espacios
        texto_limpio = message.text.replace('$', '').replace(' ', '')
        monto = float(texto_limpio)
        
        if monto < 10: # Ejemplo de monto mínimo
            bot.send_message(message.chat.id, "❌ El monto mínimo es de 10.")
            return

        uid = message.from_user.id
        url_pago = crear_orden_plisio(monto, moneda, uid)
        
        if url_pago:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💳 PAGAR AHORA", url=url_pago))
            bot.send_message(message.chat.id, f"✅ Orden creada por {monto} {moneda}.\nPresiona el botón para pagar con tu tarjeta:", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "❌ Error al generar el link. Intenta más tarde.")
            
    except ValueError:
        bot.send_message(message.chat.id, "❌ Por favor, envía solo números. Ejemplo: `150`", parse_mode="Markdown")

# --- CASHOUT (SALIDA: COINS -> TRANSFERENCIA) ---
@bot.message_handler(func=lambda m: m.text == "🏦 Retirar")
def retiro(message):
    db = cargar_db()
    uid = str(message.from_user.id)
    if db[uid]['saldo'] < 100:
        return bot.send_message(message.chat.id, "❌ Mínimo: $100 MXN")
    
    msg = bot.send_message(message.chat.id, "Escribe tu **CLABE** y **Nombre del Titular**:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, enviar_solicitud_retiro)

def enviar_solicitud_retiro(message):
    datos = message.text
    uid = str(message.from_user.id)
    db = cargar_db()
    monto = db[uid]['saldo']
    monto_final = monto * (1 - COMISION_RETIRO)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Confirmar SPEI Enviado", callback_data=f"pago_{uid}_{monto}"))
    
    bot.send_message(ADMIN_ID, f"🚨 *RETIRO PENDIENTE*\n\nUser: `{uid}`\nEnviar: `${monto_final}`\nDatos: `{datos}`", parse_mode="Markdown", reply_markup=markup)
    bot.send_message(message.chat.id, "⏳ Solicitud enviada. Recibirás tu SPEI en menos de 24h.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('pago_'))
def confirmar_retiro_admin(call):
    _, uid, monto = call.data.split('_')
    db = cargar_db()
    db[uid]['saldo'] = 0
    guardar_db(db)
    bot.send_message(uid, f"✅ Tu retiro de `${monto}` ha sido procesado por SPEI.")
    bot.edit_message_text(f"✅ Pagado a {uid}", call.message.chat.id, call.message.message_id)

# --- COMANDO DE ADMINISTRADOR (CARGA MANUAL TRAS RECIBIR EN BINANCE) ---
@bot.message_handler(commands=['dar'])
def dar_saldo(message):
    if str(message.from_user.id) == ADMIN_ID:
        try:
            _, target_id, cantidad = message.text.split()
            db = cargar_db()
            if target_id in db:
                db[target_id]['saldo'] += float(cantidad)
                db[target_id]['compras_exitosas'] += 1
                guardar_db(db)
                bot.send_message(target_id, f"✅ *¡RECARGA EXITOSA!*\nSe han acreditado `${cantidad} MXN`.", parse_mode="Markdown")
                bot.reply_to(message, "💰 Saldo cargado correctamente.")
        except:
            bot.reply_to(message, "Uso: `/dar ID MONTO`")

# --- PERFIL ---
@bot.message_handler(func=lambda m: m.text == "👤 Perfil")
def perfil(message):
    db = cargar_db()
    u = db.get(str(message.from_user.id), {})
    bot.send_message(message.chat.id, f"👤 *PERFIL*\n\n💰 Saldo: `${u.get('saldo', 0)} MXN`", parse_mode="Markdown")

bot.infinity_polling()
