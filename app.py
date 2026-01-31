import os
import threading
from flask import Flask, jsonify
from telegram_bot import start_bot

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"status": "ok"})

def run_bot():
    start_bot()

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
