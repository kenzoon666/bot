import os
import logging
import asyncio
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler  # <- добавлен импорт
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

        required_env = ["TELEGRAM_TOKEN", "OPENROUTER_API_KEY", "RENDER_SERVICE_NAME"]
        missing = [key for key in required_env if not os.getenv(key)]
        if missing:
            logger.error(f"❌ Отсутствуют переменные окружения: {', '.join(missing)}")
            return False

        try:
            self.app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).updater(None).build()

            self.app.add_handler(CommandHandler("start", self.start))
            self.app.add_handler(CommandHandler("help", self.help))
            self.app.add_handler(CommandHandler("menu", self.show_menu))  # ← новая команда
            self.app.add_handler(CallbackQueryHandler(self.handle_callback))  # ← обработчик кнопок
            self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
            self.app.add_handler(MessageHandler(filters.VOICE, self.handle_voice))

            await self.app.initialize()
            await self.app.start()

            base_url = os.getenv("RENDER_EXTERNAL_URL") or f"https://{os.getenv('RENDER_SERVICE_NAME')}.onrender.com"
            webhook_url = f"{base_url}/webhook"
            await self.app.bot.set_webhook(webhook_url)

            self.initialized = True
            logger.info("✅ Бот успешно инициализирован")
            return True

        except Exception as e:
            logger.exception("❌ Ошибка инициализации бота")
            return False

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message:
            keyboard = [
                [KeyboardButton("🎨 Генерация аватара по описанию")],
                [KeyboardButton("🖼️ Сгенерировать изображение")],
                [KeyboardButton("🎧 Преобразовать текст в голос")],
                [KeyboardButton("🎙️ Распознать голосовое сообщение")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text("🚀 Бот работает корректно! Выберите опцию:", reply_markup=reply_markup)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message:
            await update.message.reply_text(
                "Я могу генерировать текст и изображения по вашему запросу, а также работать с голосом.\n"
                "Выберите опцию с клавиатуры или введите сообщение.\n\n"
                "Примеры:\n- Сгенерируй картинку кота\n- Преобразуй этот текст в речь\n- Распознай голосовое сообщение"
            )

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return

        prompt = update.message.text
        await update.message.chat.send_action(ChatAction.TYPING)

        try:
            if "картинк" in prompt.lower() or "аватар" in prompt.lower() or "🖼️" in prompt or "🎨" in prompt:
                await update.message.reply_text("⏳ Генерирую изображение...")
                url = await self.generate_image(prompt)
                if url:
                    await update.message.reply_photo(url)
                else:
                    await update.message.reply_text("⚠️ Ошибка при генерации изображения.")
            elif "🎧" in prompt:
                await update.message.reply_text("🔊 Пока функция преобразования текста в голос в разработке.")
            elif "🎙️" in prompt:
                await update.message.reply_text("🎙️ Отправьте голосовое сообщение, и я его распознаю.")
            else:
                result = await self.generate_response(prompt)
                await update.message.reply_text(result, parse_mode="Markdown")
        except Exception as e:
            logger.exception("Ошибка при обработке текста/изображения")
            await update.message.reply_text("⚠️ Произошла ошибка при генерации.")

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.voice:
            return

        await update.message.reply_text("🎙️ Пока функция распознавания голосовых в разработке.")

    async def generate_image(self, prompt: str) -> str | None:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            logger.error("❌ API-ключ OpenRouter не найден!")
            return None

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "prompt": prompt,
            "model": "stability-ai/sdxl",
            "width": 512,
            "height": 512
        }

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.post("https://openrouter.ai/api/v1/images/generate", headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        logger.error(f"❌ Ошибка генерации изображения: {resp.status} - {await resp.text()}")
                        return None

                    data = await resp.json()
                    image_url = data.get("data", [{}])[0].get("url")
                    logger.info(f"✅ Сгенерировано изображение: {image_url}")
                    return image_url
        except Exception as e:
            logger.exception("❌ Ошибка запроса генерации изображения")
            return None

    async def generate_response(self, prompt: str) -> str:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            return "⚠️ Ошибка: отсутствует API-ключ."

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "openai/gpt-3.5-turbo",
            "messages": [{"role": "user", "content": prompt}]
        }

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        logger.error(f"❌ Ошибка генерации текста: {resp.status} - {await resp.text()}")
                        return "⚠️ Сейчас сервер перегружен. Повторите позже."

                    data = await resp.json()
                    return data.get("choices", [{}])[0].get("message", {}).get("content", "⚠️ Нет ответа от модели.")
        except Exception as e:
            logger.exception("❌ Ошибка запроса к OpenRouter")
            return "⚠️ Ошибка при обработке ответа API."

# --- FastAPI-приложение ---
web_app = FastAPI()
bot_manager = BotManager()

@web_app.on_event("startup")
async def startup_event():
    if not await bot_manager.initialize():
        raise RuntimeError("❌ Бот не инициализирован.")
    async def show_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("🎨 Генерация аватара по описанию", callback_data='generate_avatar')],
            [InlineKeyboardButton("🖼️ Сгенерировать изображение", callback_data='generate_image')],
            [InlineKeyboardButton("🎧 Преобразовать текст в голос", callback_data='text_to_speech')],
            [InlineKeyboardButton("🎙️ Распознать голосовое сообщение", callback_data='voice_to_text')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.message:
            await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        if data == 'generate_avatar':
            await query.edit_message_text("Введите описание для генерации аватара 🎨")
        elif data == 'generate_image':
            await query.edit_message_text("Отправьте описание изображения 🖼️")
        elif data == 'text_to_speech':
            await query.edit_message_text("Отправьте текст для озвучки 🎧")
        elif data == 'voice_to_text':
            await query.edit_message_text("Отправьте голосовое сообщение 🎙️")
        else:
            await query.edit_message_text("Неизвестная команда.")

@web_app.post("/webhook")
async def handle_webhook(request: Request):
    if not bot_manager.initialized:
        return JSONResponse(status_code=503, content={"status": "error", "message": "Bot not initialized"})

    try:
        data = await request.json()
        update = Update.de_json(data, bot_manager.app.bot)
        await bot_manager.app.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        logger.exception("❌ Ошибка обработки webhook")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Internal Server Error"})

@web_app.get("/")
async def health_check():
    return {
        "status": "running",
        "bot_initialized": bot_manager.initialized
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(web_app, host="0.0.0.0", port=port)
