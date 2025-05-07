import os
import logging
import asyncio
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from fastapi import FastAPI
import uvicorn

# --- Конфигурация ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# --- Инициализация приложения ---
web_app = FastAPI()
bot_app = Application.builder() \
    .token(os.getenv("TELEGRAM_TOKEN")) \
    .updater(None) \
    .build()

# --- Обработчики команд ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бот работает корректно!")

# Добавляем обработчики СРАЗУ при старте
handlers = [
    CommandHandler("start", start),
    # ... другие обработчики ...
]

# --- Инициализация бота ---
async def init_bot():
    """Инициализация всех компонентов бота ДО запуска сервера"""
    for handler in handlers:
        bot_app.add_handler(handler)
    
    await bot_app.initialize()  # Критически важный вызов!
    await bot_app.start()
    
    # Установка вебхука
    webhook_url = f"https://{os.getenv('RENDER_SERVICE_NAME')}.onrender.com/webhook"
    await bot_app.bot.set_webhook(webhook_url)
    logging.info(f"Вебхук установлен: {webhook_url}")

# --- Вебхук-эндпоинт ---
@web_app.post("/webhook")
async def handle_webhook(request: Request):
    try:
        data = await request.json()
        update = Update.de_json(data, bot_app.bot)
        await bot_app.process_update(update)
    except Exception as e:
        logging.error(f"Ошибка обработки update: {e}")
    return {"status": "ok"}

# --- Health Check ---
@web_app.get("/")
async def health_check():
    return {"status": "running", "bot": "initialized"}

# --- Запуск приложения ---
if __name__ == "__main__":
    # 1. Сначала инициализируем бота
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_bot())
    
    # 2. Затем запускаем сервер
    uvicorn.run(
        web_app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 10000)),
        log_level="info"
    )
