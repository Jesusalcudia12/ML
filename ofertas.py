import requests
import time
import json
import os
import config # Importa tus secretos de forma segura

# --- CONFIGURACIÓN ---
TOKEN = config.TOKEN_TELEGRAM
ADMIN = config.ID_ADMIN
CANAL = config.ID_CANAL
ARCHIVO_DATOS = "productos.json"

# FUNCION: Carga o crea automáticamente el archivo de lista
def cargar_o_crear_lista():
    if not os.path.exists(ARCHIVO_DATOS):
        with open(ARCHIVO_DATOS, "w") as f:
            json.dump({}, f)
        print(f"✨ Archivo {ARCHIVO_DATOS} creado automáticamente.")
        return {}
    else:
        with open(ARCHIVO_DATOS, "r") as f:
            return json.load(f)

# Inicializamos la memoria del bot
PRODUCTOS_AFILIADOS = cargar_o_crear_lista()

def guardar_datos():
    with open(ARCHIVO_DATOS, "w") as f:
        json.dump(PRODUCTOS_AFILIADOS, f, indent=4)

def enviar_a_canal(foto, texto):
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    payload = {"chat_id": CANAL, "photo": foto, "caption": texto, "parse_mode": "Markdown"}
    requests.post(url, data=payload)

def responder_admin(texto):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    # Convertimos ADMIN a string por seguridad en el envío
    requests.post(url, data={"chat_id": str(ADMIN), "text": texto, "parse_mode": "Markdown"})

def obtener_datos_meli(item_id):
    try:
        item = requests.get(f"https://api.mercadolibre.com/items/{item_id}").json()
        desc = requests.get(f"https://api.mercadolibre.com/items/{item_id}/description").json()
        return {
            "titulo": item['title'],
            "precio": item['price'],
            "imagen": item['pictures'][0]['url'],
            "desc": desc.get('plain_text', 'Sin descripción')[:150] + "..."
        }
    except: return None

def procesar_comandos():
    # Usamos un offset para no leer mensajes viejos infinitamente
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset=-1"
    try:
        res = requests.get(url).json()
        if res["result"]:
            m = res["result"][-1]["message"]
            # CAMBIO CLAVE: Convertimos ambos a string para asegurar coincidencia
            uid = str(m["from"]["id"])
            texto = m.get("text", "")

            if uid == str(ADMIN):
                # COMANDO /agregar
                if texto.startswith("/agregar"):
                    lineas = texto.split("\n")
                    inicio = 1 if len(lineas) > 1 else 0
                    nuevos = 0
                    
                    for i in range(inicio, len(lineas)):
                        linea = lineas[i].replace("/agregar ", "").strip()
                        if not linea: continue
                        try:
                            # Formato: ID,LINK,PRECIO_META
                            partes = linea.split(",")
                            mid = partes[0].strip()
                            link = partes[1].strip()
                            
                            # CAMBIO CLAVE: Limpiamos el precio de comas y signos
                            precio_limpio = partes[2].replace(",", "").replace("$", "").strip()
                            precio_meta = float(precio_limpio)

                            PRODUCTOS_AFILIADOS[mid] = [link, precio_meta, 0]
                            nuevos += 1
                        except Exception as e: 
                            print(f"Error procesando línea: {linea} -> {e}")
                            continue
                    
                    guardar_datos()
                    responder_admin(f"✅ ¡Lista actualizada! Se procesaron {nuevos} productos.")

                elif texto.startswith("/borrar"):
                    try:
                        mid = texto.split(" ")[1]
                        if mid in PRODUCTOS_AFILIADOS:
                            del PRODUCTOS_AFILIADOS[mid]
                            guardar_datos()
                            responder_admin(f"🗑️ Producto `{mid}` eliminado.")
                    except: pass

                elif texto == "/lista":
                    total = len(PRODUCTOS_AFILIADOS)
                    if total == 0:
                        responder_admin("📋 La lista está vacía.")
                    else:
                        msj = f"📋 *Tu lista ({total}):*\n"
                        for k, v in PRODUCTOS_AFILIADOS.items():
                            msj += f"• `{k}` → Meta: ${v[1]}\n"
                        responder_admin(msj)
    except Exception as e:
        print(f"Error en comandos: {e}")

# --- BUCLE DE TRABAJO ---
print(f"🚀 Bot en línea para el Administrador: {ADMIN}")

while True:
    procesar_comandos()
    
    # Revisión de precios
    for item_id, info in list(PRODUCTOS_AFILIADOS.items()):
        datos = obtener_datos_meli(item_id)
        if datos:
            link_afi, precio_meta, ultimo_precio = info[0], info[1], info[2]
            precio_actual = datos['precio']
            enviar_alerta = False
            tipo_alerta = ""

            if precio_actual <= precio_meta:
                tipo_alerta = "🚨 *OFERTA OBJETIVO ALCANZADA*"
                enviar_alerta = True
            elif precio_actual < ultimo_precio and ultimo_precio != 0:
                tipo_alerta = "📉 *BAJADA DE PRECIO DETECTADA*"
                enviar_alerta = True
            
            if enviar_alerta:
                caption = (f"{tipo_alerta}\n\n*{datos['titulo']}*\n"
                           f"💰 *Precio Actual:* ${precio_actual}\n"
                           f"📉 *Precio Anterior:* ${ultimo_precio if ultimo_precio != 0 else '---'}\n\n"
                           f"🛒 [COMPRAR AQUÍ]({link_afi})")
                enviar_a_canal(datos['imagen'], caption)
                
                PRODUCTOS_AFILIADOS[item_id][2] = precio_actual
                guardar_datos()
        
        time.sleep(2) 

    time.sleep(900)
