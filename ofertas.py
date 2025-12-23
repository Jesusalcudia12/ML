import requests
import time
import json
import os
import config
import threading

# --- CONFIGURACIÓN ---
TOKEN = config.TOKEN_TELEGRAM
ADMIN = str(config.ID_ADMIN).strip()
CANAL = config.ID_CANAL
ARCHIVO_DATOS = "productos.json"

def cargar_datos():
    if not os.path.exists(ARCHIVO_DATOS):
        with open(ARCHIVO_DATOS, "w") as f: json.dump({}, f)
        return {}
    with open(ARCHIVO_DATOS, "r") as f: 
        try: return json.load(f)
        except: return {}

PRODUCTOS = cargar_datos()
LAST_UPDATE_ID = 0 

def guardar_datos():
    with open(ARCHIVO_DATOS, "w") as f:
        json.dump(PRODUCTOS, f, indent=4)

def enviar_canal(foto, texto):
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    payload = {"chat_id": CANAL, "photo": foto, "caption": texto, "parse_mode": "Markdown"}
    requests.post(url, data=payload)

def responder(texto):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": ADMIN, "text": texto, "parse_mode": "Markdown"})

def obtener_meli(item_id):
    try:
        item = requests.get(f"https://api.mercadolibre.com/items/{item_id}").json()
        return {
            "titulo": item['title'],
            "precio": item['price'],
            "imagen": item['pictures'][0]['url']
        }
    except: return None

# --- TAREA EN SEGUNDO PLANO (MONITOREO) ---
def bucle_monitoreo():
    print("🔎 Monitoreo de precios iniciado...")
    while True:
        items = list(PRODUCTOS.items())
        for item_id, info in items:
            datos = obtener_meli(item_id)
            if datos:
                link_afi, precio_meta, ultimo_precio = info[0], info[1], info[2]
                precio_actual = datos['precio']
                
                # Lógica de envío al canal
                if precio_actual <= precio_meta:
                    txt = f"🚨 *OFERTA ALCANZADA*\n\n{datos['titulo']}\n💰 *Precio:* ${precio_actual}\n🛒 [COMPRAR AQUÍ]({link_afi})"
                    enviar_canal(datos['imagen'], txt)
                    PRODUCTOS[item_id][2] = precio_actual # Evita spam
                    guardar_datos()
                
            time.sleep(5) # Pausa entre productos para evitar bloqueo de API
        time.sleep(600) # Espera 10 min tras revisar toda la lista

# --- TAREA DE COMANDOS (INSTANTÁNEO) ---
def procesar_comandos():
    global LAST_UPDATE_ID, PRODUCTOS
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={LAST_UPDATE_ID + 1}&timeout=20"
    try:
        res = requests.get(url).json()
        if res.get("result"):
            for update in res["result"]:
                LAST_UPDATE_ID = update["update_id"]
                m = update.get("message")
                if not m or str(m["from"]["id"]) != ADMIN: continue
                texto = m.get("text", "").strip()

                if texto == "/start":
                    responder("👋 Monitor activo. Canal: " + CANAL)
                elif texto == "/lista":
                    msj = f"📋 *Lista ({len(PRODUCTOS)}):*\n" + "\n".join([f"• `{k}`" for k in PRODUCTOS.keys()])
                    responder(msj if PRODUCTOS else "Vacía.")
                elif texto.startswith("/borrar"):
                    mid = texto.replace("/borrar", "").strip()
                    if mid in PRODUCTOS:
                        del PRODUCTOS[mid]
                        guardar_datos(); responder(f"🗑️ `{mid}` borrado.")
                elif texto.startswith("/agregar"):
                    for l in texto.split("\n")[1:]:
                        try:
                            p = l.split(",")
                            PRODUCTOS[p[0].strip()] = [p[1].strip(), float(p[2].replace(",","")), 0]
                        except: continue
                    guardar_datos(); responder("✅ Productos agregados.")
    except: pass

# --- INICIO ---
if __name__ == "__main__":
    # Iniciamos el monitoreo en un hilo separado
    threading.Thread(target=bucle_monitoreo, daemon=True).start()
    print(f"🔥 Bot listo para el Admin {ADMIN}")
    
    # El hilo principal se queda atendiendo comandos
    while True:
        procesar_comandos()
