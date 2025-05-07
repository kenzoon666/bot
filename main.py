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
from fastapi import FastAPI, Request, status
import uvicorn

# --- Конфигурация ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Глобальные флаги ---
bot_initialized = False
bot_app = None

# --- Инициализация бота ---
async def initialize_bot():
    global bot_app, bot_initialized
    
    try:
        bot_app = Application.builder() \
            .token(os.getenv("TELEGRAM_TOKEN")) \
            .updater(None) \
            .build()

        # Добавляем обработчики
        bot_app.add_handler(CommandHandler("start", start))
        # ... другие обработчики ...

        # Установка вебхука
        webhook_url = f"https://{os.getenv('RENDER_SERVICE_NAME')}.onrender.com/webhook"
        await bot_app.bot.set_webhook(
            url=webhook_url,
            drop_pending_updates=True
        )
        logger.info(f"Вебхук установлен: {webhook_url}")

        bot_initialized = True
        return True
        
    except Exception as e:
        logger.error(f"Ошибка инициализации бота: {e}")
        return False

# --- Обработчики команд ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот работает!")

# --- Вебхук-эндпоинт ---
async def handle_webhook(request: Request):
    global bot_app
    
    if not bot_app:
        logger.error("Бот не инициализирован!")
        return {"status": "error"}, 503
        
    try:
        data = await request.json()
        update = Update.de_json(data, bot_app.bot)
        await bot_app.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}")
        return {"status": "error"}, 500

# --- FastAPI приложение ---
web_app = FastAPI()
web_app.post("/webhook")(handle_webhook)

@web_app.get("/")
async def health_check():
    return {
        "status": "running",
        "bot_initialized": bot_initialized
    }

# --- Запуск ---
async def main():
    if not await initialize_bot():
        logger.error("Не удалось инициализировать бота")
        return

    port = int(os.getenv("PORT", 10000))
    server = uvicorn.Server(
        config=uvicorn.Config(
            web_app,
            host="0.0.0.0",
            port=port,
            log_level="info"
        )
    )
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
