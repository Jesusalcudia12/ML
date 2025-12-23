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
    """Carga la lista de URLs desde el archivo JSON."""
    if os.path.exists(ARCHIVO_DATOS):
        try:
            with open(ARCHIVO_DATOS, "r") as f:
                data = json.load(f)
                # Si el archivo era un diccionario antiguo, migra a lista de URLs
                return list(data.keys()) if isinstance(data, dict) else data
        except: return []
    return []

PRODUCTOS = cargar_datos()
db_lock = threading.Lock() # Evita que los hilos choquen al leer/escribir

def guardar_datos():
    """Guarda la lista actual de URLs en el disco."""
    with db_lock:
        with open(ARCHIVO_DATOS, "w") as f:
            json.dump(PRODUCTOS, f, indent=4)

def responder_admin(texto):
    """Envía mensajes de confirmación al administrador."""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": ADMIN, "text": texto, "parse_mode": "Markdown"}, timeout=5)
    except: pass

def extraer_id_real(url):
    """Resuelve redirecciones y extrae el ID MLM de la publicación."""
    try:
        # Los links /sec/ son acortadores que necesitan ser seguidos
        res = requests.get(url, timeout=10, allow_redirects=True)
        url_final = res.url
        # Buscamos el patrón MLM seguido de números
        match = re.search(r'MLM-?(\d+)', url_final)
        if match:
            return f"MLM{match.group(1)}"
    except Exception as e:
        print(f"⚠️ Error al resolver URL {url}: {e}")
    return None

def obtener_info_producto(url_p):
    """Consulta la API de Mercado Libre para obtener fotos y descripción."""
    id_ml = extraer_id_real(url_p)
    if not id_ml: return None
    
    try:
        # 1. Datos básicos (Título, Precio, Foto)
        r = requests.get(f"https://api.mercadolibre.com/items/{id_ml}", timeout=10).json()
        if 'title' not in r: return None

        # 2. Descripción completa
        d_req = requests.get(f"https://api.mercadolibre.com/items/{id_ml}/description", timeout=10)
        desc = d_req.json().get('plain_text', "Sin descripción.") if d_req.status_code == 200 else "Sin descripción."
        
        return {
            "titulo": r['title'],
            "precio": r['price'],
            "foto": r['pictures'][0]['url'],
            "desc": (desc[:550] + "...") if len(desc) > 550 else desc
        }
    except: return None

# --- HILO 1: ENVÍO AUTOMÁTICO AL CANAL (CADA 60 SEGUNDOS) ---
def bucle_envio():
    print(f"🛰️ Transmisión iniciada hacia {CANAL}")
    while True:
        with db_lock:
            lista_actual = list(PRODUCTOS)
        
        if not lista_actual:
            print("💤 Lista vacía. Esperando URLs...")
            time.sleep(20)
            continue

        for url_item in lista_actual:
            info = obtener_info_producto(url_item)
            if info:
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
                except: print("❌ Error de red al enviar a Telegram")
                
                # LA PAUSA: 1 minuto por cada link de la lista
                time.sleep(60)
        
        print("🏁 Ciclo completado. Reiniciando en 5 segundos...")
        time.sleep(5)

# --- HILO 2: COMANDOS DEL ADMINISTRADOR (RESPUESTA AL INSTANTE) ---
def bucle_comandos():
    last_id = 0
    print("⚡ Escucha de comandos activa (Prioridad Alta).")
    while True:
        try:
            url_api = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_id+1}&timeout=10"
            r = requests.get(url_api, timeout=15).json()
            
            if not r.get("result"): continue
            
            for up in r["result"]:
                last_id = up["update_id"]
                msg = up.get("message")
                if not msg or str(msg["from"]["id"]) != ADMIN: continue
                
                txt = msg.get("text", "").strip()

                if txt == "/start":
                    responder_admin("🚀 *Bot de Ofertas Actualizado*\n- Pega un link para agregarlo.\n- Usa /lista para ver el total.")
                
                elif txt == "/lista":
                    with db_lock:
                        cant = len(PRODUCTOS)
                    responder_admin(f"📋 Actualmente tienes {cant} links en rotación.")

                elif txt.startswith("http"):
                    with db_lock:
                        if txt not in PRODUCTOS:
                            PRODUCTOS.append(txt)
                            guardar_datos()
                            responder_admin("✅ URL guardada exitosamente.")
                        else:
                            responder_admin("ℹ️ Esta URL ya está en tu lista.")
                
                elif txt.startswith("/borrar"):
                    target = txt.replace("/borrar", "").strip()
                    with db_lock:
                        if target in PRODUCTOS:
                            PRODUCTOS.remove(target)
                            guardar_datos()
                            responder_admin("🗑️ Link eliminado de la rotación.")
                        else:
                            responder_admin("❌ No encontré ese link exacto.")
        except: 
            time.sleep(2)

if __name__ == "__main__":
    # Iniciar el envío al canal en un hilo separado (hilo secundario)
    hilo_transmision = threading.Thread(target=bucle_envio, daemon=True)
    hilo_transmision.start()
    
    # Iniciar la escucha de comandos (hilo principal)
    bucle_comandos()
