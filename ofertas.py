import requests
import time
import json
import os
import config
import threading

# --- CONFIGURACIÓN DESDE CONFIG.PY ---
TOKEN = config.TOKEN_TELEGRAM
ADMIN = str(config.ID_ADMIN).strip()
CANAL = config.ID_CANAL  # Asegúrate de que sea "@Ofertas_MercadoLibreMx"
ARCHIVO_DATOS = "productos.json"

# --- GESTIÓN DE DATOS (PERSISTENCIA) ---
def cargar_datos():
    if os.path.exists(ARCHIVO_DATOS):
        try:
            with open(ARCHIVO_DATOS, "r") as f:
                data = json.load(f)
                print(f"✅ Archivo cargado: {len(data)} productos encontrados.")
                return data
        except:
            print("⚠️ Error leyendo productos.json, iniciando vacío.")
            return {}
    return {}

PRODUCTOS = cargar_datos()
db_lock = threading.Lock() # Evita errores al escribir y leer al mismo tiempo

def guardar_datos():
    with db_lock:
        with open(ARCHIVO_DATOS, "w") as f:
            json.dump(PRODUCTOS, f, indent=4)

# --- COMUNICACIÓN ---
def responder_admin(texto):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": ADMIN, "text": texto, "parse_mode": "Markdown"}, timeout=5)
    except: pass

def obtener_meli(item_id):
    try:
        # 1. Datos básicos
        r = requests.get(f"https://api.mercadolibre.com/items/{item_id}", timeout=5)
        item = r.json()
        
        # 2. Descripción completa
        desc_req = requests.get(f"https://api.mercadolibre.com/items/{item_id}/description", timeout=5)
        descripcion = "Sin descripción."
        if desc_req.status_code == 200:
            descripcion = desc_req.json().get('plain_text', descripcion)
        
        # Acortar descripción para Telegram (límite de 1024 total con foto)
        if len(descripcion) > 500:
            descripcion = descripcion[:500] + "..."

        return {
            "titulo": item['title'],
            "precio": item['price'],
            "imagen": item['pictures'][0]['url'],
            "descripcion": descripcion
        }
    except Exception as e:
        print(f"❌ Error API MeLi ({item_id}): {e}")
        return None

# --- HILO 1: ENVÍO AUTOMÁTICO AL CANAL (1 MIN POR LINK) ---
def bucle_envio_canal():
    print(f"🛰️ Transmisión iniciada hacia {CANAL}...")
    while True:
        with db_lock:
            items = list(PRODUCTOS.items())
        
        if not items:
            print("💤 Lista vacía en productos.json. Esperando...")
            time.sleep(30)
            continue

        for item_id, info in items:
            datos = obtener_meli(item_id)
            if datos:
                url_img = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
                
                # Formato del mensaje
                txt = (f"📦 *{datos['titulo']}*\n\n"
                       f"📝 *Descripción:*\n_{datos['descripcion']}_\n\n"
                       f"💰 *Precio:* ${datos['precio']}\n"
                       f"🛒 [VER EN MERCADO LIBRE]({info[0]})")
                
                try:
                    res = requests.post(url_img, data={
                        "chat_id": CANAL, 
                        "photo": datos['imagen'], 
                        "caption": txt, 
                        "parse_mode": "Markdown"
                    }, timeout=15)
                    
                    if res.status_code == 200:
                        print(f"✅ Publicado: {item_id}")
                    else:
                        print(f"❌ Error Telegram ({res.status_code}): {res.text}")
                except Exception as e:
                    print(f"⚠️ Error de red al enviar: {e}")
                
                # LA PAUSA QUE PEDISTE: 1 minuto entre cada link
                time.sleep(60) 
        
        print("🏁 Fin de lista. Reiniciando ciclo...")
        time.sleep(5)

# --- HILO 2: COMANDOS (RESPUESTA INSTANTÁNEA) ---
def bucle_comandos():
    last_update_id = 0
    print("⚡ Servidor de comandos activo (Prioridad Alta).")
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
                        responder_admin("🚀 *Bot Totalmente Actualizado*\n- Envío: 1 min/link\n- Fotos y Descripción: Sí\n- Modo: Multihilo")
                    
                    elif texto == "/lista":
                        with db_lock:
                            nombres = "\n".join([f"• `{k}`" for k in PRODUCTOS.keys()])
                            count = len(PRODUCTOS)
                        responder_admin(f"📋 *Productos en rotación ({count}):*\n{nombres}" if count > 0 else "Lista vacía.")

                    elif texto.startswith("/agregar"):
                        lineas = texto.split("\n")[1:]
                        nuevos = 0
                        with db_lock:
                            for l in lineas:
                                try:
                                    p = l.split(",")
                                    # Formato: ID, LINK, PRECIO
                                    PRODUCTOS[p[0].strip()] = [p[1].strip(), float(p[2].replace(",","")), 0]
                                    nuevos += 1
                                except: continue
                        if nuevos > 0:
                            guardar_datos()
                            responder_admin(f"✅ Añadidos {nuevos} productos. Los anteriores se mantienen.")

                    elif texto.startswith("/borrar"):
                        mid = texto.replace("/borrar", "").strip()
                        with db_lock:
                            if mid in PRODUCTOS:
                                del PRODUCTOS[mid]
                                guardar_datos()
                                responder_admin(f"🗑️ `{mid}` eliminado.")
                            else:
                                responder_admin("❌ No encontré ese ID.")
        except:
            time.sleep(2)

# --- LANZAMIENTO DEL SISTEMA ---
if __name__ == "__main__":
    # 1. Hilo secundario para el canal (No bloquea los comandos)
    t_canal = threading.Thread(target=bucle_envio_canal, daemon=True)
    t_canal.start()
    
    # 2. Hilo principal para recibir tus órdenes
    bucle_comandos()
