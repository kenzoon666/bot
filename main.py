import os
import logging
import asyncio
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    Defaults
)
from fastapi import FastAPI, Request, status
import uvicorn

# --- Конфигурация логов ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Инициализация приложений ---
web_app = FastAPI()
bot_app = Application.builder() \
    .token(os.getenv("TELEGRAM_TOKEN")) \
    .defaults(Defaults(block=False)) \
    .updater(None) \
    .build()

# --- Обработчики команд ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот успешно инициализирован!")

# Все обработчики должны быть добавлены ДО инициализации
handlers = [
    CommandHandler("start", start),
    # ... другие обработчики ...
]

# --- Критически важная инициализация ---
async def initialize_bot():
    """Полная инициализация бота перед запуском"""
    try:
        # 1. Добавляем обработчики
        for handler in handlers:
            bot_app.add_handler(handler)
        
        # 2. Явная инициализация
        await bot_app.initialize()
        await bot_app.start()
        
        # 3. Установка вебхука
        webhook_url = f"https://{os.getenv('RENDER_SERVICE_NAME')}.onrender.com/webhook"
        await bot_app.bot.set_webhook(
            url=webhook_url,
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        logger.info(f"🔄 Вебхук установлен: {webhook_url}")
        
        # 4. Проверка соединения
        me = await bot_app.bot.get_me()
        logger.info(f"🤖 Бот @{me.username} готов к работе")
        
        return True
    except Exception as e:
        logger.critical(f"🚨 Ошибка инициализации: {e}")
        return False

# --- Вебхук-эндпоинт ---
@web_app.post("/webhook")
async def telegram_webhook(request: Request):
    if not bot_app.initialized:
        logger.warning("⚠️ Приложение еще не инициализировано!")
        return {"status": "error", "detail": "Bot not initialized"}, 503
    
    try:
        data = await request.json()
        update = Update.de_json(data, bot_app.bot)
        await bot_app.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"❌ Ошибка обработки update: {e}")
        return {"status": "error"}, 500

# --- Health Check ---
@web_app.get("/")
async def health_check():
    return {
        "status": "running",
        "bot_initialized": bot_app.initialized,
        "bot_running": bot_app.running
    }

# --- Запуск приложения ---
async def main():
    # 1. Инициализация бота
    if not await initialize_bot():
        logger.error("❌ Не удалось инициализировать бота, завершаем работу")
        return

    # 2. Запуск сервера
    port = int(os.getenv("PORT", 10000))
    config = uvicorn.Config(
        web_app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        server_header=False
    )
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
