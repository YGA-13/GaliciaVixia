import os
import requests
import threading
import json
import time
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from collections import deque

# =====================================================
# CONFIG
# =====================================================

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

FLASK_PORT = 5000
SUBS_FILE = "subscriptions.json"

# =====================================================
# GLOBAL STATE
# =====================================================

subscriptions = {}
subs_lock = threading.Lock()

alert_history = deque(maxlen=100)

# =====================================================
# TELEGRAM SENDER
# =====================================================

def send_telegram_message(chat_id, text):

    if not TELEGRAM_TOKEN:
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }

    try:
        r = requests.post(url, json=payload, timeout=10)

        if r.status_code != 200:
            print("Telegram error:", r.text)
            return False

        return True

    except Exception as e:
        print("Telegram exception:", e)
        return False

# =====================================================
# STORAGE
# =====================================================

def load_subscriptions():

    global subscriptions

    if os.path.exists(SUBS_FILE):

        try:
            with open(SUBS_FILE,"r",encoding="utf-8") as f:
                data=json.load(f)

                for cid in data:
                    data[cid]["zonas"]=set(data[cid]["zonas"])

                subscriptions=data

            print(f"📂 Subscricións cargadas: {len(subscriptions)}")

        except Exception as e:
            print("Load subs error:",e)
            subscriptions={}

    else:
        subscriptions={}

def save_subscriptions():

    with subs_lock:

        data={
            cid:{
                "zonas":list(p["zonas"]),
                "activo":p.get("activo",True)
            }
            for cid,p in subscriptions.items()
        }

        with open(SUBS_FILE,"w",encoding="utf-8") as f:
            json.dump(data,f,indent=2,ensure_ascii=False)

# =====================================================
# COMMAND PROCESSOR
# =====================================================

def process_command(chat_id, text):

    text=text.strip()

    # ---------- START ----------
    if text=="/start":

        send_telegram_message(
            chat_id,
            "👋 Benvido a GaliciaVixía\n\n"
            "🔥 Sistema de alertas forestais\n\n"
            "📌 Comandos:\n"
            "/subscribir zona\n"
            "/desubscribir zona\n"
            "/miszonas\n"
            "/axuda\n"
        )
        return

    # ---------- AXUDA ----------
    if text=="/axuda":

        send_telegram_message(
            chat_id,
            "ℹ️ *GaliciaVixía*\n\n"
            "👉 /subscribir [zona]\n"
            "👉 /desubscribir [zona]\n"
            "👉 /miszonas\n"
        )
        return

    # ---------- SUBSCRIBIR ----------
    if text.startswith("/subscribir"):

        raw=text.replace("/subscribir","").strip()

        zonas=[
            z.strip().capitalize()
            for z in raw.replace(",", " ").split()
            if z.strip()
        ]

        if not zonas:
            zonas=["Galicia"]

        with subs_lock:

            if chat_id not in subscriptions:
                subscriptions[chat_id]={
                    "zonas":set(),
                    "activo":True
                }

            for zona in zonas:
                subscriptions[chat_id]["zonas"].add(zona)

        save_subscriptions()

        zonas_list=", ".join(sorted(subscriptions[chat_id]["zonas"]))

        send_telegram_message(
            chat_id,
            f"✅ Subscrito\n📋 Zonas activas:\n{zonas_list}"
        )

        return

    # ---------- DESUBSCRIBIR ----------
    if text.startswith("/desubscribir"):

        raw=text.replace("/desubscribir","").strip()

        zonas_lista=[
            z.strip().capitalize()
            for z in raw.replace(",", " ").split()
            if z.strip()
        ]

        if not zonas_lista:
            send_telegram_message(chat_id,"⚠️ Especifica zona(s)")
            return

        with subs_lock:

            if chat_id in subscriptions:

                for zona in zonas_lista:
                    subscriptions[chat_id]["zonas"].discard(zona)

                if not subscriptions[chat_id]["zonas"]:
                    del subscriptions[chat_id]

        save_subscriptions()

        send_telegram_message(
            chat_id,
            "🔕 Desubscrito de:\n" +
            "\n".join(f"• {z}" for z in zonas_lista)
        )

        return

    # ---------- MIS ZONAS ----------
    if text=="/miszonas":

        with subs_lock:

            if chat_id in subscriptions and subscriptions[chat_id]["zonas"]:

                zonas="\n".join(
                    f"• {z}" for z in sorted(subscriptions[chat_id]["zonas"])
                )

                msg="📋 *As túas zonas*\n\n"+zonas

            else:
                msg="⚪ Non tes zonas subscritas."

        send_telegram_message(chat_id,msg)
        return

# =====================================================
# TELEGRAM POLLING WORKER
# =====================================================

def process_updates():

    print("🤖 Polling Telegram iniciado")

    last_update_id=0

    while True:

        try:

            url=f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"

            r=requests.get(
                url,
                params={"timeout":30,"offset":last_update_id+1},
                timeout=35
            )

            if r.status_code==200:

                updates=r.json().get("result",[])

                for update in updates:

                    last_update_id=max(
                        last_update_id,
                        update["update_id"]
                    )

                    if "message" not in update:
                        continue

                    msg=update["message"]

                    chat_id=str(msg["chat"]["id"])
                    text=msg.get("text","")

                    process_command(chat_id,text)

        except Exception as e:
            print("Polling error:",e)

        time.sleep(1)

# =====================================================
# WEBHOOK GRAFANA
# =====================================================

app=Flask(__name__)

@app.route("/webhook/grafana",methods=["POST"])
def grafana_alert():

    try:

        data=request.get_json(silent=True)

        if not data:
            return jsonify({"error":"bad json"}),400

        alerts=data.get("alerts",[])

        notified=0

        for alert in alerts:

            labels=alert.get("labels",{})

            zona=labels.get("zona","Galicia")
            severity=labels.get("severity","MODERADO")

            summary=alert.get("annotations",{}).get("summary","")

            mensaje=f"""
🔥 ALERTA INCENDIO

📍 Zona: {zona}
⚠️ Nivel: {severity}
📝 {summary}
"""

            with subs_lock:

                for chat_id,prefs in subscriptions.items():

                    if not prefs.get("activo",True):
                        continue

                    zonas_usuario=prefs["zonas"]

                    if zona in zonas_usuario or "Galicia" in zonas_usuario:

                        send_telegram_message(chat_id,mensaje)
                        notified+=1

        return jsonify({
            "status":"ok",
            "notified_users":notified
        })

    except Exception as e:
        print("Webhook error:",e)
        return jsonify({"error":"internal"}),500

# =====================================================
# MAIN
# =====================================================

if __name__=="__main__":

    print("🚀 GaliciaVixía FINAL STABLE VERSION")

    load_subscriptions()

    threading.Thread(
        target=process_updates,
        daemon=True
    ).start()

    app.run(
        host="0.0.0.0",
        port=FLASK_PORT,
        threaded=True,
        debug=False
    )