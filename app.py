import os
import threading
from flask import Flask, jsonify
from telegram_bot import start_bot

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"status": "ok"}), 200

def run_telegram():
    start_bot()

if __name__ == "__main__":
    # Start Telegram bot in background
    threading.Thread(target=run_telegram, daemon=True).start()

    # Start Flask for Railway healthcheck
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
