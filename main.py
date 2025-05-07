import os
import logging
import asyncio
from telegram import Update
import aiohttp  # для HTTP-запросов к OpenRouter или OpenAI
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from fastapi import FastAPI, Request
import uvicorn

# --- Конфигурация ---
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
            
        try:
            self.app = Application.builder() \
                .token(os.getenv("TELEGRAM_TOKEN")) \
                .updater(None) \
                .build()

            # Регистрация обработчиков
            self.app.add_handler(CommandHandler("start", self.start))
            self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
            # Добавьте другие обработчики...

            # Явная инициализация
            await self.app.initialize()
            await self.app.start()
            
            # Установка вебхука
            webhook_url = f"https://{os.getenv('RENDER_SERVICE_NAME')}.onrender.com/webhook"
            await self.app.bot.set_webhook(webhook_url)
            
            self.initialized = True
            logger.info("Бот успешно инициализирован")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка инициализации: {e}")
            return False

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text
    await update.message.chat.send_action("typing")
    
    try:
        result = await self.generate_response(prompt)
        await update.message.reply_text(result)
    except Exception as e:
        await update.message.reply_text("⚠️ Произошла ошибка при генерации ответа.")
        logger.error(f"Ошибка генерации текста: {e}", exc_info=True)
   if "картинк" in prompt.lower():
    await update.message.reply_text("⏳ Генерирую изображение...")
    url = await self.generate_image(prompt)
    await update.message.reply_photo(url)
    return
async def generate_image(self, prompt: str) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "prompt": prompt,
        "model": "openrouter/replicate/stability-ai/sdxl"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post("https://openrouter.ai/api/v1/images/generations", headers=headers, json=payload) as resp:
            data = await resp.json()
            return data["data"][0]["url"]
 async def generate_response(self, prompt: str) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY")  # или OPENAI_API_KEY
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "openrouter/openai/gpt-3.5-turbo",
        "messages": [{"role": "user", "content": prompt}]
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload) as resp:
            data = await resp.json()
            return data["choices"][0]["message"]["content"].strip()
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🚀 Бот работает корректно!")

# --- FastAPI приложение ---
web_app = FastAPI()
bot_manager = BotManager()

@web_app.on_event("startup")
async def startup_event():
    await bot_manager.initialize()

@web_app.post("/webhook")
async def handle_webhook(request: Request):
    if not bot_manager.initialized:
        logger.error("Бот не инициализирован!")
        return {"status": "error"}, 503
        
    try:
        data = await request.json()
        update = Update.de_json(data, bot_manager.app.bot)
        await bot_manager.app.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Ошибка обработки: {e}")
        return {"status": "error"}, 500

@web_app.get("/")
async def health_check():
    return {
        "status": "running",
        "bot_initialized": bot_manager.initialized
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(web_app, host="0.0.0.0", port=port)
