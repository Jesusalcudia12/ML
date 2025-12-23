import stripe
import telebot
from flask import Flask, request, jsonify
import threading
import json
import os
from telebot import types

# --- CONFIGURACIÓN (REEMPLAZA CON TUS DATOS) ---
stripe.api_key = "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"  # Tu llave secreta de Stripe
bot = telebot.TeleBot("8531717834:AAExJEm2EI6Zce7ZKtyJfKb-qHPuMbCZyoE") # Tu Token de BotFather
WEBHOOK_SECRET = "whsec_CsvgZeegdGER1beChBHwHNDO8jb5z5ba" # Tu secreto de webhook de Stripe
ADMIN_ID = "6280594821" # Tu ID numérico (puedes verlo con /perfil)
DB_FILE = "usuarios.json"
BOT_USERNAME = "DARKGEN_CCBOT" # Tu alias de bot sin el @

app = Flask(__name__)

# --- GESTIÓN DE BASE DE DATOS ---
def cargar_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: return json.load(f)
    return {}

def guardar_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=4)

def actualizar_saldo(user_id, cantidad):
    db = cargar_db()
    uid = str(user_id)
    db[uid] = db.get(uid, 0) + cantidad
    guardar_db(db)
    return db[uid]

# --- COMANDOS DE USUARIO ---
@bot.message_handler(commands=['start', 'perfil'])
def ver_perfil(message):
    db = cargar_db()
    uid = str(message.from_user.id)
    saldo = db.get(uid, 0)
    
    texto = (
        f"🕹️ *PANEL DE JUGADOR*\n\n"
        f"👤 *Nombre:* {message.from_user.first_name}\n"
        f"🆔 *ID:* `{uid}`\n"
        f"💰 *Saldo Actual:* `${saldo} MXN`\n\n"
        "Usa /comprar para recargar créditos."
    )
    bot.send_message(message.chat.id, texto, parse_mode="Markdown")

@bot.message_handler(commands=['comprar'])
def menu_pagos(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    montos = [100, 200, 500, 1000, 2000, 3000, 1]
    btns = [types.InlineKeyboardButton(f"${m} MXN", callback_data=f"pago_{m}") for m in montos]
    markup.add(*btns)
    
    bot.send_message(
        message.chat.id, 
        "💎 *CENTRO DE RECARGAS*\nSelecciona el monto que deseas sumar a tu cuenta:", 
        parse_mode="Markdown", 
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('pago_'))
def crear_sesion(call):
    monto = int(call.data.split('_')[1])
    
    # --- LÍNEA 70 CORREGIDA: Protegemos la respuesta al botón ---
    try:
        bot.answer_callback_query(call.id, "Generando link seguro...")
    except Exception:
        pass # Evita que el bot se detenga si Telegram tarda en responder

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'mxn',
                    'product_data': {'name': f'Recarga de {monto} créditos'},
                    'unit_amount': monto * 100,
                },
                'quantity': 1,
            }],
            mode='payment',
            client_reference_id=str(call.from_user.id),
            success_url=f'https://t.me/{BOT_USERNAME}',
            cancel_url=f'https://t.me/{BOT_USERNAME}',
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💳 PAGAR AHORA", url=session.url))
        
        bot.send_message(
            call.message.chat.id, 
            f"✅ *Orden Generada*\nMonto: `${monto} MXN`\n\nPresiona el botón para completar el pago:", 
            parse_mode="Markdown", 
            reply_markup=markup
        )
    except Exception as e:
        print(f"Error en Stripe: {e}")
        bot.send_message(call.message.chat.id, "❌ Error al conectar con Stripe. Revisa la terminal.")

# --- COMANDOS DE ADMINISTRADOR ---
@bot.message_handler(commands=['dar'])
def dar_creditos(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        return bot.reply_to(message, "❌ No tienes permiso.")
    
    try:
        partes = message.text.split()
        target_id = partes[1]
        monto = float(partes[2])
        nuevo_total = actualizar_saldo(target_id, monto)
        bot.send_message(ADMIN_ID, f"✅ Has dado ${monto} al usuario {target_id}. Nuevo saldo: ${nuevo_total}")
        bot.send_message(target_id, f"🎁 *¡Has recibido un regalo!*\nUn administrador te ha enviado ${monto} créditos.", parse_mode="Markdown")
    except:
        bot.reply_to(message, "Uso: `/dar 12345678 500`", parse_mode="Markdown")

# --- WEBHOOK (RECEPCIÓN DE PAGOS) ---
@app.route('/webhook', methods=['POST'])
def webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
        
        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            uid = session.get('client_reference_id')
            monto_recibido = session.get('amount_total') / 100
            
            nuevo_saldo = actualizar_saldo(uid, monto_recibido)
            
            bot.send_message(
                uid, 
                f"✅ *¡PAGO CONFIRMADO!*\n\nHas recargado: `${monto_recibido} MXN`\nTu saldo total es: *${nuevo_saldo} MXN*",
                parse_mode="Markdown"
            )
            bot.send_message(ADMIN_ID, f"💰 *NUEVA VENTA:* El usuario {uid} compró ${monto_recibido} MXN.")
            
        return jsonify(success=True), 200
    except Exception as e:
        print(f"Error en Webhook: {e}")
        return jsonify(success=False), 400

# --- INICIO ---
if __name__ == "__main__":
    # Flask corre en puerto 5000 para ngrok
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False), daemon=True).start()
    print("🚀 Servidor Webhook y Bot iniciados.")
    bot.infinity_polling()
