import asyncio
from fastapi import FastAPI
from telegram_bot import start_bot

app = FastAPI()

@app.on_event("startup")
async def startup():
    print("🚀 App startup")
    asyncio.create_task(start_bot())  # run telegram bot in background
    print("🤖 Telegram bot started")

@app.get("/")
async def root():
    return {"status": "ok"}
