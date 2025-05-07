import os
import logging
import asyncio
import aiohttp
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

# --- Конфигурация логов ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Класс бота ---
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

        try:
            self.app = Application.builder() \
                .token(os.getenv("TELEGRAM_TOKEN")) \
                .updater(None) \
                .build()

            self.app.add_handler(CommandHandler("start", self.start))
            self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))

            await self.app.initialize()
            await self.app.start()

            webhook_url = f"https://{os.getenv('RENDER_SERVICE_NAME')}.onrender.com/webhook"
            await self.app.bot.set_webhook(webhook_url)

            self.initialized = True
            logger.info("Бот успешно инициализирован")
            return True

        except Exception as e:
            logger.error(f"Ошибка инициализации: {e}")
            return False

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🚀 Бот работает корректно!")

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        prompt = update.message.text
        await update.message.chat.send_action("typing")

        try:
            if "картинк" in prompt.lower():
                await update.message.reply_text("⏳ Генерирую изображение...")
                url = await self.generate_image(prompt)
                if url:
                    await update.message.reply_photo(url)
                else:
                    await update.message.reply_text("⚠️ Ошибка при генерации изображения.")
            else:
                result = await self.generate_response(prompt)
                await update.message.reply_text(result)
        except Exception as e:
            await update.message.reply_text("⚠_
