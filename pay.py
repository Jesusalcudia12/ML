import telebot
import json
import os
import time
import requests
import stripe
from telebot import types
from flask import Flask, request

# --- CONFIGURACIÓN ---
TOKEN = "8531717834:AAExJEm2EI6Zce7ZKtyJfKb-qHPuMbCZyoE"
ADMIN_ID = "6280594821" 
PLISIO_API_KEY = "N8pUsjMMygSzk3NytnvW1rHjRQq6tw0U3q7BgAC9yxlzHOwM8eABpsAJh5HDYK4k"
STRIPE_API_KEY = "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"
MP_LINK_MANUAL = "https://link.mercadopago.com.mx/nexusdigitaloficial"

# ⚠️ PEGA AQUÍ TU URL DE NGROK
NGROK_URL = "https://6b9f260defd4.ngrok-free.app" 

TIPO_CAMBIO = 20.0
COMISION_RETIRO = 0.15
DB_FILE = "database_segura.json"

bot = telebot.TeleBot(TOKEN)
stripe.api_key = STRIPE_API_KEY
app = Flask(__name__)

# --- GESTIÓN DE BASE DE DATOS ---
def cargar_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: return json.load(f)
    return {}

def guardar_db(db):
    with open(DB_FILE, "w") as f: json.dump(db, f, indent=4)

# --- PASARELAS DE PAGO ---

def crear_orden_stripe(monto, moneda, uid):
    try:
        monto_centavos = int(monto * 100)
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': moneda.lower(),
                    'product_data': {'name': f'Recarga Nexus - ID {uid}'},
                    'unit_amount': monto_centavos,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url="https://t.me/TuBotNombre", 
            cancel_url="https://t.me/TuBotNombre",
        )
        return session.url
    except Exception as e:
        print(f"Error Stripe: {e}")
        return None

def crear_orden_plisio(monto, moneda, uid):
    monto_pago = monto if moneda == "USD" else (monto / TIPO_CAMBIO) 
    url = "https://api.plisio.net/api/v1/invoices/new"
    params = {
        'api_key': PLISIO_API_KEY,
        'currency': 'USDT_TRX',
        'source_currency': 'USD',
        'source_amount': f"{monto_pago:.2f}",
        'order_number': f"PAY_{uid}_{int(time.time())}",
        'order_name': 'Nexus Digital',
        'email': 'pago@nexus.com',
        'callback_url': 'https://google.com'
    }
    try:
        response = requests.get(url, params=params, timeout=15)
        data = response.json()
        if data['status'] == 'success':
            return data['data']['invoice_url']
        return None
    except: return None

# --- COMANDOS PRINCIPALES ---

@bot.message_handler(commands=['start'])
def start(message):
    db = cargar_db()
    uid = str(message.from_user.id)
    if uid not in db:
        db[uid] = {"saldo": 0, "nombre": message.from_user.first_name, "racha_derrotas": 0}
        guardar_db(db)
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("👤 Perfil", "💎 Recargar")
    markup.add("🎲 Jugar", "🏦 Retirar")
    
    bot.send_message(message.chat.id, f"👋 ¡Bienvenido {message.from_user.first_name}!\n\n💰 Saldo: `${db[uid]['saldo']} MXN`", 
                     parse_mode="Markdown", reply_markup=markup)

# --- SISTEMA DE JUEGO (DADOS) ---

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
        time.sleep(3.5)
        
        gano = False
        # Algoritmo de enganche (Si lleva 5 perdidas seguidas, gana)
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
            bot.send_message(message.chat.id, f"🎉 ¡GANASTE! Salió {valor_dado}.\nRecibes: `${monto_apuesta} MXN`")
        else:
            db[uid]['saldo'] -= monto_apuesta
            bot.send_message(message.chat.id, f"💀 PERDISTE. Salió {valor_dado}.\nSuerte a la próxima.")
        
        guardar_db(db)
    except:
        bot.reply_to(message, "❌ Uso: `/apostar 10`")

# --- SISTEMA DE RECARGA ---

@bot.message_handler(func=lambda m: m.text == "💎 Recargar")
def menu_recarga(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🇲🇽 Mercado Pago (Manual)", url=MP_LINK_MANUAL),
        types.InlineKeyboardButton("💳 Stripe (Tarjeta Global)", callback_data="metodo_stripe"),
        types.InlineKeyboardButton("🌎 Plisio (Cripto USDT)", callback_data="metodo_plisio")
    )
    bot.send_message(message.chat.id, "💎 *CENTRO DE RECARGA*\n\nSelecciona tu método:", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('metodo_'))
def seleccionar_monto(call):
    metodo = call.data.split('_')[1]
    markup = types.InlineKeyboardMarkup(row_width=2)
    montos = [100, 200, 500, 1000]
    for m in montos:
        markup.add(types.InlineKeyboardButton(f"${m} MXN", callback_data=f"pay_{metodo}_{m}"))
    bot.edit_message_text(f"💵 Elegiste {metodo.upper()}. Selecciona el monto:", 
                          call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('pay_'))
def procesar_pago(call):
    _, metodo, monto = call.data.split('_')
    monto = float(monto)
    uid = str(call.message.chat.id)
    msg_espera = bot.send_message(uid, "⏳ Generando link...")
    
    url = crear_orden_stripe(monto, "MXN", uid) if metodo == "stripe" else crear_orden_plisio(monto, "MXN", uid)
    bot.delete_message(uid, msg_espera.message_id)

    if url:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💳 PAGAR AHORA", url=url))
        bot.send_message(uid, f"✅ *Orden Lista*\nMonto: `${monto} MXN`", parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(uid, "❌ Error de conexión.")

# --- RETIROS Y PERFIL ---

@bot.message_handler(func=lambda m: m.text == "🏦 Retirar")
def retiro(message):
    db = cargar_db()
    uid = str(message.from_user.id)
    if db[uid]['saldo'] < 100:
        return bot.send_message(message.chat.id, "❌ Mínimo para retirar: $100 MXN")
    msg = bot.send_message(message.chat.id, "Escribe tu **CLABE** y **Nombre** para el SPEI:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, enviar_solicitud_retiro)

def enviar_solicitud_retiro(message):
    datos = message.text
    uid = str(message.from_user.id)
    db = cargar_db()
    monto = db[uid]['saldo']
    monto_final = monto * (1 - COMISION_RETIRO)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Marcar como PAGADO", callback_data=f"pago_{uid}_{monto}"))
    
    bot.send_message(ADMIN_ID, f"🚨 *SOLICITUD DE RETIRO*\n\nID: `{uid}`\nEnviar: `${monto_final}`\nDatos: {datos}", parse_mode="Markdown", reply_markup=markup)
    bot.send_message(message.chat.id, "⏳ Solicitud enviada al admin.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('pago_'))
def confirmar_retiro_admin(call):
    _, uid, monto = call.data.split('_')
    db = cargar_db()
    if uid in db:
        db[uid]['saldo'] = 0
        guardar_db(db)
        bot.send_message(uid, f"✅ Tu retiro de `${monto}` ha sido pagado.")
        bot.edit_message_text(f"✅ Pagado a {uid}", call.message.chat.id, call.message.message_id)

@bot.message_handler(func=lambda m: m.text == "👤 Perfil")
def perfil(message):
    db = cargar_db()
    uid = str(message.from_user.id)
    u = db.get(uid, {"saldo": 0})
    bot.send_message(message.chat.id, f"👤 *TU PERFIL*\n\n🆔 ID: `{uid}`\n💰 Saldo: `${u['saldo']} MXN`", parse_mode="Markdown")

# --- ADMIN PANEL ---

@bot.message_handler(commands=['dar'])
def dar_saldo(message):
    if str(message.from_user.id) == ADMIN_ID:
        try:
            _, tid, cant = message.text.split()
            db = cargar_db()
            db[str(tid)]['saldo'] += float(cant)
            guardar_db(db)
            bot.send_message(tid, f"✅ Se han acreditado `${cant} MXN`.")
            bot.reply_to(message, "✅ Saldo actualizado.")
        except: bot.reply_to(message, "Uso: `/dar ID MONTO`")

# --- WEBHOOK LOGIC (FLASK) ---

@app.route('/' + TOKEN, methods=['POST'])
def getMessage():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

@app.route("/")
def webhook():
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=NGROK_URL + "/" + TOKEN)
    return "<h1>Nexus Activo</h1>", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
