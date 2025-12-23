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
    if os.path.exists(ARCHIVO_DATOS):
        try:
            with open(ARCHIVO_DATOS, "r") as f:
                return json.load(f)
        except: return {}
    return {}

PRODUCTOS = cargar_datos()
db_lock = threading.Lock()

def guardar_datos():
    with db_lock:
        with open(ARCHIVO_DATOS, "w") as f:
            json.dump(PRODUCTOS, f, indent=4)

def responder_admin(texto):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": ADMIN, "text": texto, "parse_mode": "Markdown"}, timeout=5)
    except: pass

def obtener_meli(item_id):
    try:
        # 1. Obtener datos básicos (Título, Precio, Imagen)
        r = requests.get(f"https://api.mercadolibre.com/items/{item_id}", timeout=5)
        item = r.json()
        
        # 2. Obtener Descripción (API aparte)
        desc_req = requests.get(f"https://api.mercadolibre.com/items/{item_id}/description", timeout=5)
        descripcion = "Sin descripción disponible."
        if desc_req.status_code == 200:
            descripcion = desc_req.json().get('plain_text', descripcion)
        
        # Recortar descripción si es muy larga (Telegram tiene límites)
        if len(descripcion) > 400:
            descripcion = descripcion[:400] + "..."

        return {
            "titulo": item['title'],
            "precio": item['price'],
            "imagen": item['pictures'][0]['url'],
            "descripcion": descripcion
        }
    except: return None

# --- HILO 1: ESCANEO Y ENVÍO AL CANAL ---
def bucle_envio_canal():
    print("🛰️ Escáner con fotos y descripción activo.")
    while True:
        with db_lock:
            items = list(PRODUCTOS.items())
        
        if not items:
            time.sleep(10)
            continue

        for item_id, info in items:
            datos = obtener_meli(item_id)
            if datos:
                url_img = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
                
                # Diseño del mensaje con Descripción
                txt = (f"📦 *{datos['titulo']}*\n\n"
                       f"📝 *Descripción:*\n{datos['descripcion']}\n\n"
                       f"💰 *Precio Actual:* ${datos['precio']}\n"
                       f"🛒 [COMPRAR AHORA]({info[0]})")
                
                try:
                    requests.post(url_img, data={
                        "chat_id": CANAL, 
                        "photo": datos['imagen'], 
                        "caption": txt, 
                        "parse_mode": "Markdown"
                    }, timeout=10)
                    print(f"✅ Enviado: {item_id}")
                except: pass
                
                time.sleep(60) # Pausa de 1 minuto entre links
        
        time.sleep(5)

# --- HILO 2: COMANDOS ---
def bucle_comandos():
    last_update_id = 0
    while True:
        url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_update_id + 1}&timeout=10"
        try:
            res = requests.get(url, timeout=15).json()
            if res.get("result"):
                for update in res["result"]:
                    last_update_id = update["update_id"]
                    m = update.get("message")
                    if not m or str(m["from"]["id"]) != ADMIN: continue
                    texto = m.get("text", "").strip()

                    if texto == "/start":
                        responder_admin("🚀 *Bot de Ofertas con Descripción activo.*")
                    
                    elif texto == "/lista":
                        with db_lock:
                            count = len(PRODUCTOS)
                            nombres = "\n".join([f"• `{k}`" for k in PRODUCTOS.keys()])
                        responder_admin(f"📋 *Productos ({count}):*\n{nombres}" if count > 0 else "Lista vacía.")

                    elif texto.startswith("/agregar"):
                        lineas = texto.split("\n")[1:]
                        nuevos = 0
                        with db_lock:
                            for l in lineas:
                                try:
                                    p = l.split(",")
                                    # ID, LINK, PRECIO (el precio se guarda pero el bot envía todo siempre)
                                    PRODUCTOS[p[0].strip()] = [p[1].strip(), float(p[2].replace(",","")), 0]
                                    nuevos += 1
                                except: continue
                        if nuevos > 0:
                            guardar_datos()
                            responder_admin(f"✅ Se añadieron {nuevos} productos.")

                    elif texto.startswith("/borrar"):
                        mid = texto.replace("/borrar", "").strip()
                        with db_lock:
                            if mid in PRODUCTOS:
                                del PRODUCTOS[mid]
                                guardar_datos()
                                responder_admin(f"🗑️ `{mid}` eliminado.")
        except:
            time.sleep(2)

if __name__ == "__main__":
    threading.Thread(target=bucle_envio_canal, daemon=True).start()
    bucle_comandos()
