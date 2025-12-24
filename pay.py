import stripe
import telebot
import json
import os
import threading
import time
import random
from flask import Flask, request, jsonify
from telebot import types
from datetime import datetime

# --- CONFIGURACIÓN (REEMPLAZA CON TUS DATOS REALES) ---
stripe.api_key = "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"
bot = telebot.TeleBot("8531717834:AAExJEm2EI6Zce7ZKtyJfKb-qHPuMbCZyoE")
WEBHOOK_SECRET = "whsec_CsvgZeegdGER1beChBHwHNDO8jb5z5ba" 
ADMIN_ID = "6280594821" 
DB_FILE = "database_final.json"
PENDING_FILE = "cola_retiros.json"
BOT_USERNAME = "DARKGEN_CCBOT" # Sin el @
COMISION_RETIRO = 0.15 # 15%

app = Flask(__name__)

# --- GESTIÓN DE DATOS ---
def cargar_datos(archivo):
    if os.path.exists(archivo):
        with open(archivo, "r") as f: return json.load(f)
    return {}

def guardar_datos(datos, archivo):
    with open(archivo, "w") as f: json.dump(datos, f, indent=4)

def registrar_evento(uid, tipo, monto, estado):
    db = cargar_datos(DB_FILE)
    uid = str(uid)
    if "historial" not in db[uid]: db[uid]["historial"] = []
    evento = {
        "fecha": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "tipo": tipo,
        "monto": monto,
        "estado": estado
    }
    db[uid]["historial"].append(evento)
    guardar_datos(db, DB_FILE)

# --- PROCESADOR AUTOMÁTICO DE RETIROS (SEGUNDO PLANO) ---
def procesador_retiros():
    while True:
        pendientes = cargar_datos(PENDING_FILE)
        if pendientes:
            try:
                balance = stripe.Balance.retrieve()
                disponible = balance.available[0].amount / 100
                for uid, info in list(pendientes.items()):
                    if disponible >= info['monto_final']:
                        stripe.Transfer.create(
                            amount=int(info['monto_final'] * 100),
                            currency="mxn",
                            destination=info['stripe_connect_id']
                        )
                        registrar_evento(uid, "Retiro", info['monto_bruto'], "✅ Completado")
                        bot.send_message(uid, f"✅ *¡Retiro Liberado!* Tu pago de `${info['monto_bruto']}` ha sido enviado.")
                        del pendientes[uid]
                guardar_datos(pendientes, PENDING_FILE)
            except Exception as e: print(f"Error procesador: {e}")
        time.sleep(3600) # Revisa cada hora

# --- COMANDOS PRINCIPALES ---
@bot.message_handler(commands=['start'])
def start(message):
    db = cargar_datos(DB_FILE)
    uid = str(message.from_user.id)
    if uid not in db:
        db[uid] = {"nombre": message.from_user.first_name, "saldo": 0, "racha_derrotas": 0, "stripe_connect_id": None, "historial": []}
        guardar_datos(db, DB_FILE)
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("👤 Perfil", "💳 Recargar")
    markup.add("🎲 Jugar Dados", "🏦 Retirar")
    markup.add("📜 Historial")
    
    msg = (f"👋 ¡Hola {message.from_user.first_name}!\n\n"
           f"💰 Saldo: `${db[uid]['saldo']} MXN`\n"
           f"⚠️ *Nota:* Retiros tienen 15% de comisión.\n"
           f"🎲 Cada Coin equivale a $1.00 MXN.")
    bot.send_message(message.chat.id, msg, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "👤 Perfil")
def perfil(message):
    db = cargar_datos(DB_FILE)
    user = db.get(str(message.from_user.id))
    bot.send_message(message.chat.id, f"👤 *PERFIL*\n💰 Saldo: `${user['saldo']} MXN`", parse_mode="Markdown")

# --- LÓGICA DEL JUEGO (CASA SIEMPRE GANA + ENGANCHE) ---
@bot.message_handler(func=lambda m: m.text == "🎲 Jugar Dados")
def menu_juego(message):
    bot.send_message(message.chat.id, "🎰 *CASINO COINS*\nUsa `/apostar [monto]`\n(Ganas si sale 6)")

@bot.message_handler(commands=['apostar'])
def apostar(message):
    db = cargar_datos(DB_FILE)
    uid = str(message.from_user.id)
    user = db[uid]
    try:
        monto = float(message.text.split()[1])
        if monto > user['saldo'] or monto <= 0: return bot.reply_to(message, "❌ Saldo insuficiente o monto inválido.")

        msg_dado = bot.send_dice(message.chat.id, emoji='🎲')
        valor = msg_dado.dice.value
        time.sleep(3)

        ganó = False
        if user.get("racha_derrotas", 0) >= 5: # Sistema de enganche
            ganó = True
            user["racha_derrotas"] = 0
        elif valor == 6:
            ganó = True
            user["racha_derrotas"] = 0
        else:
            user["racha_derrotas"] = user.get("racha_derrotas", 0) + 1

        if ganó:
            db[uid]['saldo'] += monto
            registrar_evento(uid, "Juego", monto, "🟢 Ganó")
            bot.send_message(message.chat.id, f"🎉 ¡Ganaste! Salió {valor}. Saldo actualizado.")
        else:
            db[uid]['saldo'] -= monto
            db["ADMIN_PROFIT"] = db.get("ADMIN_PROFIT", 0) + monto
            registrar_evento(uid, "Juego", monto, "🔴 Perdió")
            bot.send_message(message.chat.id, f"💀 Perdiste. Salió {valor}. Suerte a la próxima.")
        guardar_datos(db, DB_FILE)
    except: bot.reply_to(message, "Usa: `/apostar 10`")

# --- SISTEMA DE RECARGA ---
@bot.message_handler(func=lambda m: m.text == "💳 Recargar")
def recargar(message):
    msg = bot.send_message(message.chat.id, "¿Cuánto quieres recargar? (Monto mínimo $20)")
    bot.register_next_step_handler(msg, crear_checkout)

def crear_checkout(message):
    try:
        monto = int(message.text)
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{'price_data': {'currency': 'mxn', 'product_data': {'name': 'Coins'}, 'unit_amount': monto*100}, 'quantity': 1}],
            mode='payment',
            client_reference_id=str(message.from_user.id),
            success_url=f"https://t.me/{BOT_USERNAME}",
            cancel_url=f"https://t.me/{BOT_USERNAME}"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💳 Pagar con Tarjeta", url=session.url))
        bot.send_message(message.chat.id, f"Link de pago por ${monto} MXN:", reply_markup=markup)
    except: bot.send_message(message.chat.id, "❌ Error.")

# --- SISTEMA DE RETIRO ---
@bot.message_handler(func=lambda m: m.text == "🏦 Retirar")
def retiro(message):
    db = cargar_datos(DB_FILE)
    uid = str(message.from_user.id)
    user = db[uid]
    if user['saldo'] <= 0: return bot.send_message(message.chat.id, "❌ Sin saldo.")
    
    if not user.get("stripe_connect_id"):
        acc = stripe.Account.create(type="express", country="MX")
        db[uid]["stripe_connect_id"] = acc.id
        guardar_datos(db, DB_FILE)
        link = stripe.AccountLink.create(account=acc.id, refresh_url=f"https://t.me/{BOT_USERNAME}", return_url=f"https://t.me/{BOT_USERNAME}", type="account_onboarding")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🏦 Vincular Banco", url=link.url))
        return bot.send_message(message.chat.id, "Vincula tu cuenta para recibir pagos:", reply_markup=markup)
    
    msg = bot.send_message(message.chat.id, "¿Cuánto deseas retirar?")
    bot.register_next_step_handler(msg, procesar_retiro)

def procesar_retiro(message):
    try:
        monto = float(message.text)
        db = cargar_datos(DB_FILE)
        uid = str(message.from_user.id)
        if monto > db[uid]['saldo']: return bot.send_message(message.chat.id, "❌ Saldo insuficiente.")
        
        m_final = monto * (1 - COMISION_RETIRO)
        balance = stripe.Balance.retrieve()
        disponible = balance.available[0].amount / 100

        db[uid]['saldo'] -= monto
        if disponible < m_final:
            pendientes = cargar_datos(PENDING_FILE)
            pendientes[uid] = {"monto_bruto": monto, "monto_final": m_final, "stripe_connect_id": db[uid]["stripe_connect_id"]}
            guardar_datos(pendientes, PENDING_FILE)
            registrar_evento(uid, "Retiro", monto, "⏳ Pendiente")
            bot.send_message(message.chat.id, "⏳ Retiro en cola. Stripe liberará los fondos en 3-5 días.")
        else:
            stripe.Transfer.create(amount=int(m_final*100), currency="mxn", destination=db[uid]["stripe_connect_id"])
            registrar_evento(uid, "Retiro", monto, "✅ Completado")
            bot.send_message(message.chat.id, "✅ Retiro enviado.")
        guardar_datos(db, DB_FILE)
    except: bot.send_message(message.chat.id, "❌ Error.")

@bot.message_handler(func=lambda m: m.text == "📜 Historial")
def historial(message):
    db = cargar_datos(DB_FILE)
    h = db.get(str(message.from_user.id), {}).get("historial", [])
    if not h: return bot.send_message(message.chat.id, "Vacío.")
    res = "📜 *MOVIMIENTOS*\n"
    for e in h[-5:]: res += f"• {e['fecha']} | {e['tipo']} ${e['monto']} | {e['estado']}\n"
    bot.send_message(message.chat.id, res, parse_mode="Markdown")

@app.route('/webhook', methods=['POST'])
def webhook():
    payload = request.data
    sig = request.headers.get('Stripe-Signature')
    try:
        event = stripe.Webhook.construct_event(payload, sig, WEBHOOK_SECRET)
        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            uid = session.get('client_reference_id')
            monto = session.get('amount_total') / 100
            db = cargar_datos(DB_FILE)
            db[str(uid)]['saldo'] += monto
            guardar_datos(db, DB_FILE)
            registrar_evento(uid, "Recarga", monto, "✅ Éxito")
            bot.send_message(uid, f"✅ Recarga de `${monto}` exitosa.")
        return jsonify(success=True), 200
    except: return jsonify(success=False), 400

if __name__ == "__main__":
    threading.Thread(target=procesador_retiros, daemon=True).start()
    threading.Thread(target=lambda: app.run(port=5000, debug=False, use_reloader=False)).start()
    bot.infinity_polling()
