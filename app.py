import asyncio
import os

from fastapi import FastAPI
from auth import router as auth_router
from health import router as health_router
from telegram_bot import start_bot

app = FastAPI()

# Routers
app.include_router(auth_router)
app.include_router(health_router)


@app.on_event("startup")
async def startup_event():
    """
    Start Telegram bot when app starts
    """
    asyncio.create_task(start_bot())


@app.get("/")
async def root():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=False
    )
