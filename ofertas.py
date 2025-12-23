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

def cargar_datos_existentes():
    if os.path.exists(ARCHIVO_DATOS):
        try:
            with open(ARCHIVO_DATOS, "r") as f:
                return json.load(f)
        except: return {}
    return {}

PRODUCTOS = cargar_datos_existentes()
LAST_UPDATE_ID = 0 

def guardar_datos():
    with open(ARCHIVO_DATOS, "w") as f:
        json.dump(PRODUCTOS, f, indent=4)

def responder(texto):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": ADMIN, "text": texto, "parse_mode": "Markdown"})

def obtener_meli(item_id):
    try:
        r = requests.get(f"https://api.mercadolibre.com/items/{item_id}", timeout=5)
        item = r.json()
        return {
            "titulo": item['title'],
            "precio": item['price'],
            "imagen": item['pictures'][0]['url']
        }
    except: return None

# --- BUCLE DE ESCANEO (ENVÍO CADA MINUTO POR LINK) ---
def bucle_escaneo_precios():
    print("🛰️ Escáner de envío por minuto iniciado...")
    while True:
        if not PRODUCTOS:
            print("💤 Esperando productos en productos.json...")
            time.sleep(30)
            continue 

        items_a_revisar = list(PRODUCTOS.items())
        for item_id, info in items_a_revisar:
            datos = obtener_meli(item_id)
            if datos:
                precio_actual = datos['precio']
                link_afi = info[0]
                
                url_img = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
                txt = (f"📦 *PRODUCTO EN MONITOREO*\n\n"
                       f"{datos['titulo']}\n"
                       f"💰 *Precio Actual:* ${precio_actual}\n"
                       f"🛒 [COMPRAR AHORA]({link_afi})")
                
                requests.post(url_img, data={
                    "chat_id": CANAL, 
                    "photo": datos['imagen'], 
                    "caption": txt, 
                    "parse_mode": "Markdown"
                })
                print(f"✅ Enviado al canal: {item_id}. Esperando 1 minuto para el siguiente...")
                
                # ESPERA DE 1 MINUTO POR CADA LINK
                time.sleep(60) 
        
        print("🏁 Se recorrió toda la lista. Reiniciando ciclo de envíos...")

# --- BUCLE DE COMANDOS (RESPUESTA INMEDIATA) ---
def atender_comandos_inmediatos():
    global LAST_UPDATE_ID, PRODUCTOS
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={LAST_UPDATE_ID + 1}&timeout=5"
    try:
        res = requests.get(url).json()
        if res.get("result"):
            for update in res["result"]:
                LAST_UPDATE_ID = update["update_id"]
                m = update.get("message")
                if not m or str(m["from"]["id"]) != ADMIN: continue
                texto = m.get("text", "").strip()

                if texto == "/start":
                    responder("🚀 *Bot configurado: Envío cada 1 minuto por link.*")
                elif texto == "/lista":
                    msj = f"📋 *Productos actuales:* {len(PRODUCTOS)}"
                    responder(msj)
                elif texto.startswith("/agregar"):
                    lineas = texto.split("\n")[1:]
                    for l in lineas:
                        try:
                            p = l.split(",")
                            PRODUCTOS[p[0].strip()] = [p[1].strip(), float(p[2].replace(",","")), 0]
                        except: continue
                    guardar_datos()
                    responder("✅ Productos añadidos. Se incluirán en la rotación de 1 minuto.")
                elif texto.startswith("/borrar"):
                    mid = texto.replace("/borrar", "").strip()
                    if mid in PRODUCTOS:
                        del PRODUCTOS[mid]
                        guardar_datos()
                        responder(f"🗑️ `{mid}` eliminado.")
    except: pass

if __name__ == "__main__":
    # Iniciar monitoreo en segundo plano
    threading.Thread(target=bucle_escaneo_precios, daemon=True).start()
    print("🔥 Bot iniciado. Prioridad de comandos: ALTA. Frecuencia de envío: 1 min/link.")
    
    while True:
        atender_comandos_inmediatos()
        time.sleep(0.1)
                    
