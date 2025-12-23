import requests
import time
import json
import os
import config

# --- CONFIGURACIÓN ---
TOKEN = config.TOKEN_TELEGRAM
ADMIN = str(config.ID_ADMIN).strip() # Forzamos a texto y limpiamos espacios
CANAL = config.ID_CANAL
ARCHIVO_DATOS = "productos.json"

def cargar_o_crear_lista():
    if not os.path.exists(ARCHIVO_DATOS):
        with open(ARCHIVO_DATOS, "w") as f:
            json.dump({}, f)
        return {}
    with open(ARCHIVO_DATOS, "r") as f:
        return json.load(f)

PRODUCTOS_AFILIADOS = cargar_o_crear_lista()

def guardar_datos():
    with open(ARCHIVO_DATOS, "w") as f:
        json.dump(PRODUCTOS_AFILIADOS, f, indent=4)

def responder_admin(texto):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": ADMIN, "text": texto, "parse_mode": "Markdown"}
    r = requests.post(url, data=payload)
    print(f"DEBUG: Respuesta enviada al Admin. Status: {r.status_code}")

def procesar_comandos():
    # El parámetro timeout ayuda a que el bot responda más rápido
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset=-1&timeout=10"
    try:
        res = requests.get(url).json()
        if res.get("result"):
            m = res["result"][-1].get("message")
            if not m: return
            
            uid = str(m["from"]["id"]).strip()
            texto = m.get("text", "")
            
            # ESTO APARECERÁ EN TERMUX SIEMPRE QUE ALGUIEN ESCRIBA
            print(f"📩 Mensaje recibido de ID: {uid} | Contenido: {texto}")

            if uid == ADMIN:
                if texto == "/start":
                    responder_admin("👋 ¡Hola! Soy tu bot de ofertas. Ya te reconozco como Administrador.")
                
                elif texto == "/lista":
                    total = len(PRODUCTOS_AFILIADOS)
                    if total == 0:
                        responder_admin("📋 La lista está vacía actualmente.")
                    else:
                        msj = f"📋 *Tu lista ({total}):*\n"
                        for k, v in PRODUCTOS_AFILIADOS.items():
                            msj += f"• `{k}` → ${v[1]}\n"
                        responder_admin(msj)

                elif texto.startswith("/agregar"):
                    lineas = texto.split("\n")
                    nuevos = 0
                    for i in range(1, len(lineas)):
                        try:
                            mid, link, precio = lineas[i].split(",")
                            precio_limpio = precio.replace(",", "").replace("$", "").strip()
                            PRODUCTOS_AFILIADOS[mid.strip()] = [link.strip(), float(precio_limpio), 0]
                            nuevos += 1
                        except: continue
                    guardar_datos()
                    responder_admin(f"✅ Se agregaron {nuevos} productos.")
            else:
                print(f"🚫 Acceso denegado para el ID: {uid}. El ADMIN configurado es: {ADMIN}")
    except Exception as e:
        print(f"❌ Error de conexión: {e}")

print(f"🚀 Bot en línea. Esperando mensajes del Admin ID: {ADMIN}...")

while True:
    procesar_comandos()
    time.sleep(1) # Revisa comandos cada segundo
