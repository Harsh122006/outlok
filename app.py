import asyncio
from fastapi import FastAPI
from bot import start_bot

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    print("🚀 FastAPI startup")
    asyncio.create_task(start_bot())
    print("🤖 Telegram bot task started")

@app.get("/")
async def root():
    return {"status": "ok"}
