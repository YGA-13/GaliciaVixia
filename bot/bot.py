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

# Lista para gardar chat_ids
chat_ids = set()

# === SERVICIO DE TELEGRAM (SEN PYTHON-TELEGRAM-BOT) ===
def send_telegram_message(chat_id, text, parse_mode='Markdown'):
    """Envía unha mensaxe a Telegram usando a API directamente"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    try:
        response = requests.post(url, json=payload)
        return response.status_code == 200
    except:
        return False

def get_updates(offset=None):
    """Obtén as actualizacións de Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    try:
        response = requests.get(url, params=params, timeout=35)
        if response.status_code == 200:
            return response.json().get("result", [])
    except:
        pass
    return []

def process_updates():
    """Procesa as mensaxes do bot"""
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
                    text = message.get("text", "")
                    
                    # Gardar chat_id
                    chat_ids.add(chat_id)
                    
                    # Procesar comandos
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
                        zona = text.replace("/risco", "").strip().capitalize() or "Galicia"
                        send_telegram_message(chat_id,
                            f"🔍 *Risco de incendio en {zona}:*\n\n"
                            f"🟡 Nivel: MODERADO\n"
                            f"🌡️ Temperatura: 28°C\n"
                            f"💧 Humidade: 45%\n"
                            f"💨 Vento: 25 km/h\n\n"
                            f"⚠️ _Recomendación: Evita fogueiras e actividades con lume._"
                        )
                    
                    elif text == "/axuda":
                        send_telegram_message(chat_id,
                            "ℹ️ *Como usar GaliciaVixía:*\n\n"
                            "1. Escribe /risco [tua zona]\n"
                            "2. Recibe información do risco\n"
                            "3. Usa /subscribir para alertas\n\n"
                            "🔗 _Proxecto HackUDC 2026 - Grafana Labs_"
                        )
                    
                    elif text.startswith("/subscribir"):
                        zona = text.replace("/subscribir", "").strip().capitalize() or "Galicia"
                        send_telegram_message(chat_id,
                            f"✅ *Subscrito correctamente!*\n\n"
                            f"Recibirás alertas de: {zona}\n\n"
                            f"_Para desactivar: /desubscribir_"
                        )
        
        except Exception as e:
            print(f"❌ Erro procesando updates: {e}")
        
        time.sleep(1)

# === WEBHOOK PARA GRAFANA ===
app = Flask(__name__)

@app.route('/webhook/grafana', methods=['POST'])
def grafana_alert():
    """Recibe alertas de Grafana e envía a Telegram"""
    data = request.json
    alerts = data.get('alerts', [])
    
    print(f"🔔 Alerta recibida de Grafana: {len(alerts)} alertas")
    
    for alert in alerts:
        labels = alert.get('labels', {})
        zona = labels.get('zona', 'Galicia')
        severity = labels.get('severity', 'CRÍTICO')
        
        mensaje = (
            f"🔥 *ALERTA INCENDIO*\n\n"
            f"📍 Zona: {zona}\n"
            f"⚠️ Nivel: {severity}\n"
            f"📝 {alert.get('annotations', {}).get('summary', '')}\n\n"
            f"_GaliciaVixía - HackUDC 2026_"
        )
        
        # Enviar a todos os chats rexistrados
        for chat_id in chat_ids:
            if send_telegram_message(chat_id, mensaje):
                print(f"✅ Alerta enviada a {chat_id}")
            else:
                print(f"❌ Error enviando a {chat_id}")
    
    return jsonify({"status": "ok"}), 200

@app.route('/health', methods=['GET'])
def health():
    """Endpoint para comprobar que o servidor está vivo"""
    return jsonify({"status": "healthy", "chats": len(chat_ids)}), 200

# === EXECUCIÓN ===
if __name__ == '__main__':
    print("🚀 Iniciando GaliciaVixía...")
    
    # Iniciar o polling de Telegram nun fío separado
    telegram_thread = threading.Thread(target=process_updates, daemon=True)
    telegram_thread.start()
    print("🤖 Bot de Telegram iniciado...")
    
    # Iniciar Flask
    print(f"🌐 Servidor Flask iniciado no porto {FLASK_PORT}...")
    print(f"📡 Webhook endpoint: http://localhost:{FLASK_PORT}/webhook/grafana")
    app.run(host='0.0.0.0', port=FLASK_PORT, debug=False)