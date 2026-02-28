import os
import requests
import threading
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import time

# Cargar variables de entorno
load_dotenv()

# === CONFIGURACIÓN ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
FLASK_PORT = 5000
CACHE_TTL = 3600  # Datos válidos por 1 hora

# 🗄️ CACHE GLOBAL: {zona: {datos, timestamp, expires}}
risk_cache = {}
cache_lock = threading.Lock()

# Lista para gardar chat_ids
chat_ids = set()


# === UTILIDADES DE CACHÉ ===
def get_cached_risk(zona):
    """Obtén datos da caché se están válidos"""
    with cache_lock:
        entry = risk_cache.get(zona) or risk_cache.get("Galicia")
        if entry and time.time() < entry["expires"]:
            return entry["data"]
    return None


def update_cache(zona, data):
    """Actualiza a caché con novos datos"""
    with cache_lock:
        risk_cache[zona] = {
            "data": data,
            "timestamp": time.strftime("%H:%M"),
            "expires": time.time() + CACHE_TTL
        }
        print(f"💾 Caché actualizada: {zona}")


# === SERVICIO DE TELEGRAM ===
def send_telegram_message(chat_id, text, parse_mode='Markdown'):
    """Envía unha mensaxe a Telegram"""
    # ✅ CORRECCIÓN: URL sen espazos extra
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Error Telegram: {e}")
        return False


def get_updates(offset=None):
    """Obtén as actualizacións de Telegram"""
    # ✅ CORRECCIÓN: URL sen espazos extra
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    try:
        response = requests.get(url, params=params, timeout=35)
        if response.status_code == 200:
            return response.json().get("result", [])
    except Exception as e:
        print(f"❌ Error getUpdates: {e}")
    return []


def _get_recommendation(severity):
    """Devolve recomendación según nivel"""
    severity_upper = str(severity).upper()
    if "CRÍTICO" in severity_upper or "ALTO" in severity_upper or "HIGH" in severity_upper:
        return "🚫 Prohibido calquera uso de lume. Evacúa se é necesario."
    elif "MODERADO" in severity_upper or "MEDIO" in severity_upper or "MEDIUM" in severity_upper:
        return "⚠️ Evita fogueiras, queimas e actividades con lume."
    else:
        return "✅ Condiciones favorables, pero mantén precaución."


def process_updates():
    """Procesa as mensaxes do bot (polling de Telegram)"""
    last_update_id = 0
    
    while True:
        try:
            updates = get_updates(last_update_id + 1)
            
            for update in updates:
                update_id = update["update_id"]
                last_update_id = max(last_update_id, update_id)
                
                if "message" in update:
                    message = update["message"]
                    chat_id = message["chat"]["id"]
                    text = message.get("text", "").strip()
                    
                    chat_ids.add(chat_id)
                    
                    # === COMANDOS ===
                    if text == "/start":
                        send_telegram_message(chat_id,
                            "👋 *Benvido a GaliciaVixía!*\n\n"
                            "🔥 Sistema de alerta de incendios forestais\n\n"
                            "*Comandos dispoñibles:*\n"
                            "/risco [zona] - Consultar risco actual\n"
                            "/axuda - Ver axuda\n"
                            "/subscribir [zona] - Recibir alertas da túa zona\n\n"
                            "_Exemplo: /risco Ourense_"
                        )
                    
                    elif text.startswith("/risco"):
                        try:
                            zona = text.replace("/risco", "").strip().capitalize() or "Galicia"
                            datos = get_cached_risk(zona)
                            
                            if datos:
                                mensaje = (
                                    f"🔍 *Risco de incendio en {zona}:*\n\n"
                                    f"⚠️ Nivel: {datos.get('nivel', 'DESCONOCIDO')}\n"
                                    f"📝 {datos.get('summary', 'Sen detalles')}\n"
                                    f"🕒 Actualizado: {datos.get('timestamp', 'N/A')} ⚡ Da última alerta\n\n"
                                    f"_{datos.get('recomendacion', 'Mantén precaución.')}_\n\n"
                                    f"_GaliciaVixía - HackUDC 2026_"
                                )
                            else:
                                mensaje = (
                                    f"⚪ *Sen datos recentes para {zona}*\n\n"
                                    f"Aínda non se recibiron alertas para esta zona.\n\n"
                                    f"✅ Usa /subscribir {zona.lower()} para recibir notificacións automáticas."
                                )
                            
                            send_telegram_message(chat_id, mensaje, parse_mode='Markdown')
                            
                        except Exception as e:
                            print(f"❌ Error en /risco: {e}")
                            send_telegram_message(chat_id, "⚠️ Error procesando a consulta. Intenta de novo.", parse_mode='Markdown')
                    
                    elif text == "/axuda":
                        send_telegram_message(chat_id,
                            "ℹ️ *Como usar GaliciaVixía:*\n\n"
                            "1. Escribe /risco [tua zona]\n"
                            "2. O bot mostra os últimos datos recibidos de Grafana\n"
                            "3. Usa /subscribir para alertas push\n\n"
                            "🔔 *Nota:* Os datos actualízanse cando Grafana detecta cambios.\n\n"
                            "🔗 _Proxecto HackUDC 2026 - Grafana Labs_"
                        )
                    
                    elif text.startswith("/subscribir"):
                        zona = text.replace("/subscribir", "").strip().capitalize() or "Galicia"
                        send_telegram_message(chat_id,
                            f"✅ *Subscrito correctamente!*\n\n"
                            f"Recibirás alertas push de: {zona}\n\n"
                            f"_Para desactivar: /desubscribir_"
                        )
                    
                    elif text == "/desubscribir":
                        send_telegram_message(chat_id, "🔕 *Desubscrito correctamente!*")
        
        except Exception as e:
            print(f"❌ Erro procesando updates: {e}")
        
        time.sleep(1)


# === WEBHOOK PARA GRAFANA (CORAZÓN DO SISTEMA) ===
app = Flask(__name__)

@app.route('/webhook/grafana', methods=['POST'])
def grafana_alert():
    """
    🔥 RECEBE ALERTAS DE GRAFANA E ACTUALIZA A CACHÉ 🔥
    Este é o único punto onde se "leen" datos de Grafana.
    """
    try:
        data = request.get_json(force=True)
        alerts = data.get('alerts', [])
        
        print(f"🔔 Webhook recibido: {len(alerts)} alertas")
        
        for alert in alerts:
            labels = alert.get('labels', {})
            zona = labels.get('zona', 'Galicia')
            severity = labels.get('severity', 'MODERADO')
            value = alert.get('value', 'N/A')
            
            # ✅ CONSTRUIR DATOS COMPLETOS (inclúe timestamp)
            risk_data = {
                "valor": value,
                "nivel": severity,
                "summary": alert.get('annotations', {}).get('summary', '') or 'Alerta de risco detectada',
                "recomendacion": _get_recommendation(severity),
                "timestamp": time.strftime("%H:%M")  # 👈 CLAVE PARA EVITAR KeyError
            }
            
            # 👇 ACTUALIZAR CACHÉ
            update_cache(zona, risk_data)
            
            # Construír mensaxe de alerta push
            mensaje = (
                f"🔥 *ALERTA INCENDIO*\n\n"
                f"📍 Zona: {zona}\n"
                f"⚠️ Nivel: {severity}\n"
                f"📝 {risk_data['summary']}\n\n"
                f"_{risk_data['recomendacion']}_\n\n"
                f"_GaliciaVixía - HackUDC 2026_"
            )
            
            # Enviar a todos os chats subscritos
            for chat_id in list(chat_ids):
                if send_telegram_message(chat_id, mensaje):
                    print(f"✅ Alerta enviada a {chat_id}")
                else:
                    print(f"❌ Fallou envío a {chat_id}")
        
        return jsonify({"status": "ok", "processed": len(alerts)}), 200
        
    except Exception as e:
        print(f"❌ Error procesando webhook: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Endpoint para comprobar estado do servidor"""
    now = time.time()
    active_cache = {
        zona: f"{int(entry['expires'] - now)}s" 
        for zona, entry in risk_cache.items() 
        if entry['expires'] > now
    }
    
    return jsonify({
        "status": "healthy",
        "chats_subscritos": len(chat_ids),
        "zonas_en_cache": list(active_cache.keys()),
        "cache_ttl": f"{CACHE_TTL}s",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }), 200


@app.route('/debug/cache', methods=['GET'])
def debug_cache():
    """Ver estado da caché (só para debugging)"""
    now = time.time()
    cleaned = {}
    for zona, entry in risk_cache.items():
        if entry['expires'] > now:
            cleaned[zona] = {
                "nivel": entry["data"].get("nivel"),
                "valor": entry["data"].get("valor"),
                "actualizado": entry["timestamp"],
                "expira_en": f"{int(entry['expires'] - now)}s"
            }
    return jsonify(cleaned or {"message": "Caché vacía"}), 200


# === EXECUCIÓN ===
if __name__ == '__main__':
    print("🚀 Iniciando GaliciaVixía (Webhook Push)...")
    print(f"🤖 Telegram: {'✅ Token OK' if TELEGRAM_TOKEN else '❌ Sen token'}")
    print(f"⏱️ Cache TTL: {CACHE_TTL}s (1 hora)")
    print(f"📡 Webhook: http://localhost:{FLASK_PORT}/webhook/grafana")
    print(f"🩺 Health: http://localhost:{FLASK_PORT}/health")
    print(f"🐛 Debug: http://localhost:{FLASK_PORT}/debug/cache")
    print("\n💡 Os datos actualízanse SOLO cando Grafana envía alertas.")
    
    # Iniciar polling de Telegram en fío separado
    telegram_thread = threading.Thread(target=process_updates, daemon=True)
    telegram_thread.start()
    
    # Iniciar servidor Flask
    app.run(host='0.0.0.0', port=FLASK_PORT, debug=False)