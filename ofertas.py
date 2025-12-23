import requests
import time
import json
import os
import config
import threading
import re

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
    try: requests.post(url, data={"chat_id": ADMIN, "text": texto, "parse_mode": "Markdown"}, timeout=5)
    except: pass

# --- NUEVA FUNCIÓN: LIMPIAR Y CORREGIR IDS ---
def corregir_id(texto):
    # Si es un link de "sec" o "social", intentamos extraer el ID real
    if "mercadolibre.com" in texto:
        try:
            r = requests.get(texto, timeout=5, allow_redirects=True)
            url_final = r.url
            match = re.search(r'MLM-?(\d+)', url_final)
            if match: return f"MLM{match.group(1)}"
        except: pass
    
    # Si el ID ya es tipo MLM123456, lo dejamos igual
    if texto.startswith("MLM"):
        return texto.replace("-", "")
    
    return texto # Si no se puede corregir, devolvemos el original

def obtener_meli(item_id):
    # Intentamos corregir el ID antes de consultar la API
    id_limpio = corregir_id(item_id)
    
    try:
        r = requests.get(f"https://api.mercadolibre.com/items/{id_limpio}", timeout=5)
        item = r.json()
        
        if 'title' not in item:
            print(f"❌ No se pudo encontrar el producto con ID: {item_id}")
            return None
        
        desc_req = requests.get(f"https://api.mercadolibre.com/items/{id_limpio}/description", timeout=5)
        descripcion = "Sin descripción disponible."
        if desc_req.status_code == 200:
            descripcion = desc_req.json().get('plain_text', descripcion)
        
        if len(descripcion) > 500: descripcion = descripcion[:500] + "..."

        return {
            "titulo": item['title'],
            "precio": item['price'],
            "imagen": item['pictures'][0]['url'],
            "descripcion": descripcion
        }
    except: return None

# --- HILO 1: ENVÍO AL CANAL (1 MIN POR LINK) ---
def bucle_envio_canal():
    print(f"🛰️ Transmisión activa hacia {CANAL}")
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
                txt = (f"📦 *{datos['titulo']}*\n\n"
                       f"📝 *Descripción:*\n_{datos['descripcion']}_\n\n"
                       f"💰 *Precio:* ${datos['precio']}\n"
                       f"🛒 [VER EN MERCADO LIBRE]({info[0]})")
                
                try:
                    requests.post(url_img, data={
                        "chat_id": CANAL, "photo": datos['imagen'], 
                        "caption": txt, "parse_mode": "Markdown"
                    }, timeout=15)
                    print(f"✅ Publicado: {item_id}")
                except: pass
                
                time.sleep(60) # Pausa de 1 minuto por cada link
        time.sleep(5)

# --- HILO 2: COMANDOS ---
def bucle_comandos():
    last_update_id = 0
    while True:
        url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_update_id + 1}&timeout=10"
        try:
            res = requests.get(url).json()
            if res.get("result"):
                for update in res["result"]:
                    last_update_id = update["update_id"]
                    m = update.get("message")
                    if not m or str(m["from"]["id"]) != ADMIN: continue
                    texto = m.get("text", "").strip()

                    if texto == "/start":
                        responder_admin("🚀 Bot listo. Ahora intento corregir IDs de cupones automáticamente.")
                    
                    elif texto == "/lista":
                        with db_lock:
                            count = len(PRODUCTOS)
                            resumen = "\n".join([f"• `{k}`" for k in PRODUCTOS.keys()])
                        responder_admin(f"📋 *En lista ({count}):*\n{resumen}")

                    elif texto.startswith("/agregar"):
                        lineas = texto.split("\n")[1:]
                        nuevos = 0
                        with db_lock:
                            for l in lineas:
                                try:
                                    p = l.split(",")
                                    # Guardamos el ID tal cual, la corrección se hace al momento de enviar
                                    PRODUCTOS[p[0].strip()] = [p[1].strip(), float(p[2].replace(",","")), 0]
                                    nuevos += 1
                                except: continue
                        guardar_datos()
                        responder_admin(f"✅ Añadidos {nuevos} productos.")
                    
                    elif texto.startswith("/borrar"):
                        mid = texto.replace("/borrar", "").strip()
                        with db_lock:
                            if mid in PRODUCTOS:
                                del PRODUCTOS[mid]
                                guardar_datos()
                                responder_admin(f"🗑️ `{mid}` borrado.")
        except: time.sleep(2)

if __name__ == "__main__":
    threading.Thread(target=bucle_envio_canal, daemon=True).start()
    bucle_comandos()
