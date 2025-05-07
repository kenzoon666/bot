import os
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from fastapi import FastAPI, Request
import uvicorn

# --- Инициализация ---
web_app = FastAPI()
bot_app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).updater(None).build()

# --- Обработчики команд ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я работаю!")

# Добавляем все обработчики
handlers = [
    CommandHandler("start", start),
    # ... другие обработчики ...
]

# --- Вебхук-эндпоинт ---
@web_app.on_event("startup")
async def on_startup():
    try:
        await bot_app.bot.get_me()
        logging.info("Бот успешно подключен к Telegram")
    except Exception as e:
        logging.critical(f"Ошибка подключения: {e}")
        @web_app.post("/webhook")
async def handle_webhook(request: Request):
    try:
        # Важно: инициализация при первом запросе
        if not bot_app.initialized:
            for handler in handlers:
                bot_app.add_handler(handler)
            await bot_app.initialize()  # Явная инициализация
            
        data = await request.json()
        update = Update.de_json(data, bot_app.bot)
        await bot_app.process_update(update)
    except Exception as e:
        logging.error(f"Ошибка: {str(e)}")
    return {"status": "ok"}

# --- Health Check ---
@web_app.get("/")
async def health_check():
    return {"status": "ok"}

# --- Запуск ---
async def setup():
    """Настройка при запуске"""
    await bot_app.bot.set_webhook(
        f"https://{os.getenv('RENDER_SERVICE_NAME')}.onrender.com/webhook"
    )
    logging.info("Вебхук установлен")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(web_app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
