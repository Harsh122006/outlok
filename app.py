import asyncio
import threading
from flask import Flask
from telegram_bot import build_bot

app = Flask(__name__)

@app.route("/")
def health():
    return "OK", 200

def run_bot():
    bot = build_bot()
    asyncio.run(bot.run_polling())

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    app.run(host="0.0.0.0", port=8080)
