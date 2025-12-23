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
                data = json.load(f)
                # Si el archivo era un diccionario antiguo, lo convertimos a lista
                return list(data.keys()) if isinstance(data, dict) else data
        except: return []
    return []

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

def extraer_id_real(url):
    try:
        # Resolver redirecciones de links cortos (amzn.to, mercadolibre.com/sec, etc)
        res = requests.get(url, timeout=10, allow_redirects=True)
        url_final = res.url
        # Buscar el ID de Mercado Libre (MLM12345)
        match = re.search(r'MLM-?(\d+)', url_final)
        if match:
            return f"MLM{match.group(1)}"
    except: pass
    return None

def obtener_info_producto(url_p):
    id_ml = extraer_id_real(url_p)
    if not id_ml: return None
    
    try:
        # 1. Obtener Título, Precio y Foto
        r = requests.get(f"https://api.mercadolibre.com/items/{id_ml}", timeout=10)
        item = r.json()
        if 'title' not in item: return None

        # 2. Obtener Descripción
        d = requests.get(f"https://api.mercadolibre.com/items/{id_ml}/description", timeout=10)
        desc = d.json().get('plain_text', "Sin descripción.") if d.status_code == 200 else "Sin descripción."
        
        return {
            "titulo": item['title'],
            "precio": item['price'],
            "foto": item['pictures'][0]['url'],
            "desc": (desc[:500] + "...") if len(desc) > 500 else desc
        }
    except: return None

# --- PROCESO DE ENVÍO (CADA 1 MINUTO) ---
def bucle_envio():
    print(f"🚀 Bot iniciado. Publicando en {CANAL} cada 60 segundos.")
    while True:
        with db_lock:
            lista_actual = list(PRODUCTOS)
        
        if not lista_actual:
            time.sleep(10)
            continue

        for url_item in lista_actual:
            info = obtener_info_producto(url_item)
            if info:
                # Construir el mensaje
                mensaje = (f"📦 *{info['titulo']}*\n\n"
                           f"📝 *Descripción:*\n_{info['desc']}_\n\n"
                           f"💰 *Precio:* ${info['precio']}\n"
                           f"🛒 [VER PRODUCTO AQUÍ]({url_item})")
                
                try:
                    payload = {
                        "chat_id": CANAL,
                        "photo": info['foto'],
                        "caption": mensaje,
                        "parse_mode": "Markdown"
                    }
                    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendPhoto", data=payload, timeout=20)
                    print(f"✅ Publicado OK: {info['titulo'][:30]}")
                except: print("❌ Error enviando a Telegram")
                
                time.sleep(60) # ESPERA DE 1 MINUTO
        time.sleep(5)

# --- PROCESO DE COMANDOS (INSTANTÁNEO) ---
def bucle_comandos():
    last_id = 0
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_id+1}&timeout=10", timeout=15).json()
            if not r.get("result"): continue
            
            for up in r["result"]:
                last_id = up["update_id"]
                msg = up.get("message")
                if not msg or str(msg["from"]["id"]) != ADMIN: continue
                
                txt = msg.get("text", "").strip()

                if txt == "/start":
                    responder_admin("👋 *¡Hola!* Solo pégame el link de Mercado Libre para agregarlo.")
                
                elif txt == "/lista":
                    responder_admin(f"📋 Tienes {len(PRODUCTOS)} links en rotación.")

                elif txt.startswith("http"):
                    with db_lock:
                        if txt not in PRODUCTOS:
                            PRODUCTOS.append(txt)
                            guardar_datos()
                            responder_admin("✅ Link guardado. Se publicará en su turno.")
                        else:
                            responder_admin("⚠️ Ese link ya existe.")
                
                elif txt.startswith("/borrar"):
                    target = txt.replace("/borrar", "").strip()
                    with db_lock:
                        if target in PRODUCTOS:
                            PRODUCTOS.remove(target)
                            guardar_datos()
                            responder_admin("🗑️ Link eliminado.")
        except: time.sleep(2)

if __name__ == "__main__":
    threading.Thread(target=bucle_envio, daemon=True).start()
    bucle_comandos()
