import os
import logging
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler
)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

# --- Конфигурация логов ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class BotManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
            cls._instance.app = None
        return cls._instance

    async def initialize(self):
        if self.initialized:
            return True

        required_env = ["TELEGRAM_TOKEN", "OPENROUTER_API_KEY", "RENDER_SERVICE_NAME"]
        missing = [key for key in required_env if not os.getenv(key)]
        if missing:
            logger.error(f"❌ Отсутствуют переменные окружения: {', '.join(missing)}")
            return False

        try:
            self.app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).updater(None).build()

            # Регистрация обработчиков
            handlers = [
                CommandHandler("start", self.start),
                CommandHandler("help", self.help),
                CommandHandler("menu", self.show_menu),
                CallbackQueryHandler(self.handle_callback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text),
                MessageHandler(filters.VOICE, self.handle_voice)
            ]
            
            for handler in handlers:
                self.app.add_handler(handler)

            await self.app.initialize()
            await self.app.start()

            base_url = os.getenv("RENDER_EXTERNAL_URL") or f"https://{os.getenv('RENDER_SERVICE_NAME')}.onrender.com"
            webhook_url = f"{base_url}/webhook"
            
            # Установка вебхука с секретным токеном
            secret_token = os.getenv("WEBHOOK_SECRET")
            await self.app.bot.set_webhook(
                webhook_url,
                secret_token=secret_token,
                drop_pending_updates=True
            )

            self.initialized = True
            logger.info("✅ Бот успешно инициализирован")
            return True

        except Exception as e:
            logger.exception("❌ Ошибка инициализации бота")
            return False

    # ... (остальные методы класса остаются без изменений) ...

# --- FastAPI-приложение ---
web_app = FastAPI()
bot_manager = BotManager()

@web_app.on_event("startup")
async def startup_event():
    if not await bot_manager.initialize():
        raise RuntimeError("❌ Бот не инициализирован.")

@web_app.post("/webhook")
async def handle_webhook(request: Request):
    # Проверка секретного токена
    if request.headers.get('X-Telegram-Bot-Api-Secret-Token') != os.getenv("WEBHOOK_SECRET"):
        return JSONResponse(
            status_code=403,
            content={"status": "error", "message": "Forbidden"}
        )

    if not bot_manager.initialized:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Bot not initialized"}
        )

    try:
        data = await request.json()
        update = Update.de_json(data, bot_manager.app.bot)
        await bot_manager.app.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        logger.exception("❌ Ошибка в webhook")
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(e)}
        )

if __name__ == "__main__":
    uvicorn.run(
        "main:web_app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("DEBUG", False)
