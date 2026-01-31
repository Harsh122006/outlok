import asyncio
from flask import Flask
from telegram_bot import create_application

app = Flask(__name__)

@app.route("/")
def health():
    return "OK", 200

async def main():
    telegram_app = create_application()
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.bot.initialize()
    await telegram_app.updater.start_polling()

    # Keep running forever
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.get_event_loop().create_task(main())
    app.run(host="0.0.0.0", port=8080)
