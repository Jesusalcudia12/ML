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

# MODIFICADO: Solo lee el archivo existente. Si no existe, lanza un aviso en Termux.
def cargar_datos_existentes():
    if os.path.exists(ARCHIVO_DATOS):
        try:
            with open(ARCHIVO_DATOS, "r") as f:
                data = json.load(f)
                print(f"✅ Archivo {ARCHIVO_DATOS} cargado con éxito.")
                return data
        except Exception as e:
            print(f"⚠️ Error al leer el archivo: {e}")
            return {}
    else:
        print(f"⚠️ El archivo {ARCHIVO_DATOS} no se encontró en la carpeta. Se usará una lista vacía temporal.")
        return {}

# El bot inicia cargando lo que ya tienes guardado
PRODUCTOS = cargar_datos_existentes()
LAST_UPDATE_ID = 0 

def guardar_datos():
    # Esta función actualiza el archivo productos.json con la nueva información
    with open(ARCHIVO_DATOS, "w") as f:
        json.dump(PRODUCTOS, f, indent=4)
    print("💾 Archivo productos.json actualizado.")

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

def bucle_monitoreo():
    while True:
        if not PRODUCTOS:
            time.sleep(30)
            continue 

        items = list(PRODUCTOS.items())
        for item_id, info in items:
            datos = obtener_meli(item_id)
            if datos:
                link_afi, precio_meta, ultimo_precio = info[0], info[1], info[2]
                precio_actual = datos['precio']
                
                if precio_actual <= precio_meta:
                    txt = f"🚨 *OFERTA ALCANZADA*\n\n{datos['titulo']}\n💰 *Precio:* ${precio_actual}\n🛒 [COMPRAR AQUÍ]({link_afi})"
                    enviar_canal(datos['imagen'], txt)
                    PRODUCTOS[item_id][2] = precio_actual 
                    guardar_datos()
                
            time.sleep(5) 
        time.sleep(600) 

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
                    responder("👋 Bot conectado al archivo productos.json")
                
                elif texto == "/lista":
                    if not PRODUCTOS:
                        responder("📋 El archivo está vacío.")
                    else:
                        msj = f"📋 *Productos en archivo:* {len(PRODUCTOS)}\n" + "\n".join([f"• `{k}`" for k in PRODUCTOS.keys()])
                        responder(msj)

                elif texto.startswith("/agregar"):
                    lineas = texto.split("\n")[1:]
                    nuevos = 0
                    for l in lineas:
                        try:
                            p = l.split(",")
                            pid = p[0].strip()
                            # Agregamos al diccionario y luego guardamos en el archivo existente
                            PRODUCTOS[pid] = [p[1].strip(), float(p[2].replace(",","")), 0]
                            nuevos += 1
                        except: continue
                    
                    if nuevos > 0:
                        guardar_datos() # Aquí es donde se escribe en tu productos.json
                        responder(f"✅ Se añadieron {nuevos} productos al archivo existente.")
    except: pass

if __name__ == "__main__":
    t = threading.Thread(target=bucle_monitoreo, daemon=True)
    t.start()
    print(f"🔥 Bot vinculado a productos.json. Esperando comandos...")
    while True:
        procesar_comandos()
        time.sleep(0.5)
