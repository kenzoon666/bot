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
            await update.message.reply_text("⚠️ Произошла ошибка при генерации.")
            logger.error(f"Ошибка генерации: {e}", exc_info=True)

    async def generate_image(self, prompt: str) -> str:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            logger.error("API-ключ OpenRouter не найден!")
            return None

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "prompt": prompt,
            "model": "stability-ai/sdxl",  # Модель, которую вы используете
            "width": 512,  # Пример размера изображения
            "height": 512
        }

        try:
            async with aiohttp.ClientSession() as session:
                # Изменённый URL для генерации изображений
                url = "https://openrouter.ai/api/v1/images/generate"  # Проверьте актуальность URL
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        logger.error(f"Ошибка при запросе изображения: {resp.status} - {await resp.text()}")
                        return None

                    data = await resp.json()
                    if "data" in data and data["data"]:
                        image_url = data["data"][0]["url"]
                        logger.info(f"Сгенерированный URL изображения: {image_url}")
                        return image_url
                    else:
                        logger.error(f"Ошибка генерации изображения: {data}")
                        return None
        except Exception as e:
            logger.error(f"Ошибка при запросе изображения: {e}")
            return None

    async def generate_response(self, prompt: str) -> str:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            logger.error("API-ключ OpenRouter не найден!")
            return "⚠️ Ошибка: не найден API-ключ."
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "openai/gpt-3.5-turbo",  # Модель для генерации текста
            "messages": [{"role": "user", "content": prompt}]
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        logger.error(f"Ошибка при запросе текста: {resp.status} - {await resp.text()}")
                        return "⚠️ Ошибка при генерации ответа."
                    
                    data = await resp.json()
                    if "choices" in data:
                        return data["choices"][0]["message"]["content"].strip()
                    else:
                        logger.error(f"Ошибка OpenRouter: {data}")
                        return "⚠️ Ошибка: не удалось получить ответ от AI."
        except Exception as e:
            logger.error(f"Ошибка при запросе текста: {e}")
            return "⚠️ Ошибка при обработке ответа API."

# --- FastAPI-приложение ---
web_app = FastAPI()
bot_manager = BotManager()

@web_app.on_event("startup")
async def startup_event():
    initialized = await bot_manager.initialize()
    if not initialized:
        logger.error("Не удалось инициализировать бота при запуске.")
        raise Exception("Ошибка инициализации бота.")

@web_app.post("/webhook")
async def handle_webhook(request: Request):
    if not bot_manager.initialized:
        logger.error("Бот не инициализирован!")
        return {"status": "error", "message": "Bot not initialized"}, 503

    try:
        data = await request.json()
        update = Update.de_json(data, bot_manager.app.bot)
        await bot_manager.app.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Ошибка обработки: {e}")
        return {"status": "error", "message": "Internal Server Error"}, 500

@web_app.get("/")
async def health_check():
    return {
        "status": "running",
        "bot_initialized": bot_manager.initialized
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(web_app, host="0.0.0.0", port=port)
