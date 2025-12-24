import stripe
import paypalrestsdk
import telebot
import json
import os
import random
import time
from telebot import types
from datetime import datetime

# --- CONFIGURACIÓN ---
stripe.api_key = "TU_STRIPE_KEY"
paypalrestsdk.configure({
    "mode": "live", # "sandbox" para pruebas
    "client_id": "TU_PAYPAL_CLIENT_ID",
    "client_secret": "TU_PAYPAL_CLIENT_SECRET"
})

bot = telebot.TeleBot("TU_TOKEN_TELEGRAM")
DB_FILE = "database_segura.json"
ADMIN_ID = "6280594821" 
COMISION_RETIRO = 0.15 # 15%

# Concepto legal para evitar reclamos bancarios
CONCEPTO_COBRO = "Donación voluntaria para soporte de proyecto digital"

# --- GESTIÓN DE BASE DE DATOS ---
def cargar_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: return json.load(f)
    return {}

def guardar_db(db):
    with open(DB_FILE, "w") as f: json.dump(db, f, indent=4)

def registrar_evento(uid, tipo, monto, estado):
    db = cargar_db()
    uid = str(uid)
    if "historial" not in db[uid]: db[uid]["historial"] = []
    evento = {
        "fecha": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "tipo": tipo,
        "monto": monto,
        "estado": estado
    }
    db[uid]["historial"].append(evento)
    guardar_db(db)

# --- INICIO Y REGISTRO ---
@bot.message_handler(commands=['start'])
def start_seguro(message):
    db = cargar_db()
    uid = str(message.from_user.id)
    if uid not in db:
        db[uid] = {
            "saldo": 0, 
            "nombre": message.from_user.first_name,
            "racha_derrotas": 0,
            "historial": []
        }
        guardar_db(db)

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("👤 Perfil", "💳 Recargar")
    markup.add("🎲 Jugar", "🏦 Retirar")
    markup.add("📜 Historial")
    
    bot.send_message(message.chat.id, 
        f"👋 ¡Bienvenido, {message.from_user.first_name}!\n\n"
        f"⚠️ *AVISO LEGAL:* Al usar este bot, usted acepta que toda recarga es una **{CONCEPTO_COBRO}** no reembolsable.\n\n"
        f"💰 Tu saldo: `${db[uid]['saldo']} MXN`", 
        parse_mode="Markdown", reply_markup=markup)

# --- SISTEMA DE JUEGO (CASA GANA + ENGANCHE) ---
@bot.message_handler(func=lambda m: m.text == "🎲 Jugar")
def menu_juego(message):
    bot.send_message(message.chat.id, "🎰 *DADOS CASINO*\n\nGanas si sale **6**.\nUsa `/apostar [monto]` para jugar.\nEjemplo: `/apostar 10`", parse_mode="Markdown")

@bot.message_handler(commands=['apostar'])
def apostar_coins(message):
    db = cargar_db()
    uid = str(message.from_user.id)
    user = db.get(uid)

    try:
        monto_apuesta = float(message.text.split()[1])
        if monto_apuesta > user['saldo'] or monto_apuesta <= 0:
            return bot.reply_to(message, "❌ Saldo insuficiente o monto inválido.")

        msg_dado = bot.send_dice(message.chat.id, emoji='🎲')
        valor_dado = msg_dado.dice.value
        time.sleep(3)

        gano = False
        # Sistema de Enganche: Si lleva 5 pérdidas, la 6ta gana forzado
        if user.get("racha_derrotas", 0) >= 5:
            gano = True
            user["racha_derrotas"] = 0
        elif valor_dado == 6: # Probabilidad normal (1 de 6)
            gano = True
            user["racha_derrotas"] = 0
        else:
            gano = False
            user["racha_derrotas"] = user.get("racha_derrotas", 0) + 1

        if gano:
            db[uid]['saldo'] += monto_apuesta
            registrar_evento(uid, "Juego (Gane)", monto_apuesta, "🟢 + Saldo")
            bot.send_message(message.chat.id, f"🎉 ¡Ganaste! Salió {valor_dado}. Has ganado `${monto_apuesta}`.")
        else:
            db[uid]['saldo'] -= monto_apuesta
            registrar_evento(uid, "Juego (Perdió)", monto_apuesta, "🔴 - Saldo")
            bot.send_message(message.chat.id, f"💀 Perdiste. Salió {valor_dado}. Intenta de nuevo.")
        
        guardar_db(db)
    except:
        bot.reply_to(message, "❌ Uso correcto: `/apostar 50`")

# --- MENÚ DE RECARGA (DONACIÓN) ---
@bot.message_handler(func=lambda m: m.text == "💳 Recargar")
def menu_pagos(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 Tarjeta (Stripe)", callback_data="pay_stripe"))
    markup.add(types.InlineKeyboardButton("🔵 PayPal", callback_data="pay_paypal"))
    
    bot.send_message(message.chat.id, 
        f"💎 *CENTRO DE DONACIONES*\n\n"
        f"Concepto: {CONCEPTO_COBRO}\n\n"
        f"Seleccione su método:", 
        parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["pay_stripe", "pay_paypal"])
def prep_pago(call):
    metodo = "Stripe" if call.data == "pay_stripe" else "PayPal"
    msg = bot.send_message(call.message.chat.id, f"¿Monto de la donación vía {metodo}? (MXN)")
    if call.data == "pay_stripe":
        bot.register_next_step_handler(msg, checkout_stripe)
    else:
        bot.register_next_step_handler(msg, checkout_paypal)

# (Lógicas de checkout_stripe y checkout_paypal integradas con CONCEPTO_COBRO)
def checkout_stripe(message):
    try:
        monto = int(message.text)
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{'price_data': {'currency': 'mxn', 'product_data': {'name': CONCEPTO_COBRO}, 'unit_amount': monto * 100}, 'quantity': 1}],
            mode='payment',
            client_reference_id=str(message.from_user.id),
            success_url="https://t.me/TuBot",
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Realizar Donación", url=session.url))
        bot.send_message(message.chat.id, f"Link de Stripe generado (${monto}):", reply_markup=markup)
    except: bot.send_message(message.chat.id, "❌ Error.")

def checkout_paypal(message):
    try:
        monto = float(message.text)
        payment = paypalrestsdk.Payment({
            "intent": "sale",
            "payer": {"payment_method": "paypal"},
            "redirect_urls": {"return_url": "https://t.me/TuBot", "cancel_url": "https://t.me/TuBot"},
            "transactions": [{"item_list": {"items": [{"name": CONCEPTO_COBRO, "price": str(monto), "currency": "MXN", "quantity": 1}]}, "amount": {"total": str(monto), "currency": "MXN"}, "description": CONCEPTO_COBRO}]
        })
        if payment.create():
            for link in payment.links:
                if link.rel == "approval_url":
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("🔵 Donar vía PayPal", url=link.href))
                    bot.send_message(message.chat.id, f"Link de PayPal generado (${monto}):", reply_markup=markup)
        else: bot.send_message(message.chat.id, "❌ Error en PayPal.")
    except: bot.send_message(message.chat.id, "❌ Error.")

# --- RETIRO MANUAL (MÁS SEGURO) ---
@bot.message_handler(func=lambda m: m.text == "🏦 Retirar")
def retirar(message):
    db = cargar_db()
    uid = str(message.from_user.id)
    if db[uid]['saldo'] <= 0: return bot.send_message(message.chat.id, "❌ Sin saldo.")
    
    msg = bot.send_message(message.chat.id, "Escribe tu **CLABE Interbancaria** y **Nombre del Titular**:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, step_monto_retiro)

def step_monto_retiro(message):
    datos = message.text
    msg = bot.send_message(message.chat.id, "¿Cuánto deseas retirar?")
    bot.register_next_step_handler(msg, finalizar_retiro, datos)

def finalizar_retiro(message, datos):
    try:
        monto = float(message.text)
        db = cargar_db()
        uid = str(message.from_user.id)
        if monto > db[uid]['saldo']: return bot.send_message(message.chat.id, "❌ Saldo insuficiente.")

        monto_final = monto * (1 - COMISION_RETIRO)
        db[uid]['saldo'] -= monto
        guardar_db(db)
        registrar_evento(uid, "Retiro", monto, "⏳ Pendiente")

        # Notificar al Admin
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Confirmar Pago ✅", callback_data=f"pagado_{uid}_{monto}"))
        bot.send_message(ADMIN_ID, f"🚨 *SOLICITUD DE RETIRO*\n\nUsuario: `{uid}`\nCagar: `${monto_final}`\nDatos: `{datos}`", parse_mode="Markdown", reply_markup=markup)
        bot.send_message(message.chat.id, "✅ Solicitud enviada. Se te transferirá en un lapso de 24h.")
    except: bot.send_message(message.chat.id, "❌ Error.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('pagado_'))
def admin_confirma(call):
    _, uid, monto = call.data.split('_')
    bot.send_message(uid, f"✅ Tu retiro de `${monto} MXN` ha sido enviado a tu banco.")
    bot.edit_message_text(f"✅ Pago de {monto} realizado a {uid}", ADMIN_ID, call.message.message_id)

# --- HISTORIAL Y PERFIL ---
@bot.message_handler(func=lambda m: m.text == "📜 Historial")
def ver_historial(message):
    db = cargar_db()
    h = db.get(str(message.from_user.id), {}).get("historial", [])
    if not h: return bot.send_message(message.chat.id, "📭 Sin movimientos.")
    res = "📜 *ÚLTIMOS MOVIMIENTOS*\n\n"
    for e in h[-10:]: res += f"• {e['fecha']} | {e['tipo']} ${e['monto']} | {e['estado']}\n"
    bot.send_message(message.chat.id, res, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "👤 Perfil")
def perfil(message):
    db = cargar_db()
    u = db[str(message.from_user.id)]
    bot.send_message(message.chat.id, f"👤 *PERFIL*\n💰 Saldo: `${u['saldo']} MXN`", parse_mode="Markdown")

bot.infinity_polling()
