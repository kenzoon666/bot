import os
import logging
import aiohttp
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup
)
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
            cls._instance.user_states = {}  # Для хранения состояний пользователей
        return cls._instance

    async def initialize(self):
        if self.initialized:
            return True

        required_env = ["TELEGRAM_TOKEN", "OPENROUTER_API_KEY"]
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
                CommandHandler("cancel", self.cancel),
                CallbackQueryHandler(self.handle_callback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text),
                MessageHandler(filters.VOICE, self.handle_voice)
            ]
            
            for handler in handlers:
                self.app.add_handler(handler)

            await self.app.initialize()
            await self.app.start()

            # Настройка вебхука
            webhook_url = os.getenv("WEBHOOK_URL")
            if webhook_url:
                secret_token = os.getenv("WEBHOOK_SECRET")
                await self.app.bot.set_webhook(
                    webhook_url,
                    secret_token=secret_token,
                    drop_pending_updates=True
                )
                logger.info(f"✅ Вебхук установлен на {webhook_url}")

            self.initialized = True
            logger.info("✅ Бот успешно инициализирован")
            return True

        except Exception as e:
            logger.exception("❌ Ошибка инициализации бота")
            return False

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return

        # Основная клавиатура
        reply_keyboard = [
            ["🖼️ Сгенерировать изображение", "🎨 Генерация аватара"],
            ["🎧 Текст в голос", "🎙️ Распознать голос"],
            ["❓ Помощь", "❌ Скрыть клавиатуру"]
        ]
        markup = ReplyKeyboardMarkup(
            reply_keyboard,
            resize_keyboard=True,
            is_persistent=True
        )

        await update.message.reply_text(
            "🚀 Добро пожаловать в бота! Выберите действие:",
            reply_markup=markup
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "📌 <b>Доступные команды:</b>\n"
            "/start - Главное меню\n"
            "/menu - Альтернативное меню\n"
            "/cancel - Отменить текущее действие\n\n"
            "🖼️ <b>Генерация изображений:</b>\n"
            "Просто отправьте описание того, что хотите создать\n\n"
            "🎙️ <b>Голосовые сообщения:</b>\n"
            "Отправьте голосовое сообщение для распознавания"
        )
        await update.message.reply_text(help_text, parse_mode="HTML")

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id in self.user_states:
            del self.user_states[user_id]
        await update.message.reply_text(
            "Текущее действие отменено",
            reply_markup=ReplyKeyboardRemove()
        )
        await self.start(update, context)

    async def show_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("🖼️ Сгенерировать изображение", callback_data='generate_image')],
            [InlineKeyboardButton("🎨 Генерация аватара", callback_data='generate_avatar')],
            [InlineKeyboardButton("🎧 Текст в голос", callback_data='text_to_speech')],
            [InlineKeyboardButton("🎙️ Распознать голос", callback_data='voice_to_text')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        if data == 'generate_image':
            self.user_states[user_id] = 'waiting_for_image_prompt'
            await query.edit_message_text("📝 Введите описание изображения:")
        elif data == 'generate_avatar':
            self.user_states[user_id] = 'waiting_for_avatar_prompt'
            await query.edit_message_text("🎨 Введите описание для аватара:")
        elif data == 'text_to_speech':
            await query.edit_message_text("🔊 Отправьте текст для преобразования в голос:")
        elif data == 'voice_to_text':
            await query.edit_message_text("🎙️ Отправьте голосовое сообщение для распознавания:")

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return

        user_id = update.effective_user.id
        text = update.message.text
        state = self.user_states.get(user_id)

        # Обработка команд с клавиатуры
        if text == "❌ Скрыть клавиатуру":
            await update.message.reply_text(
                "Клавиатура скрыта. Напишите /start для её возврата.",
                reply_markup=ReplyKeyboardRemove()
            )
            return
        elif text == "❓ Помощь":
            await self.help(update, context)
            return
        elif text == "🖼️ Сгенерировать изображение":
            self.user_states[user_id] = 'waiting_for_image_prompt'
            await update.message.reply_text("📝 Введите описание изображения:")
            return
        elif text == "🎨 Генерация аватара":
            self.user_states[user_id] = 'waiting_for_avatar_prompt'
            await update.message.reply_text("🎨 Введите описание для аватара:")
            return

        # Обработка состояний
        if state == 'waiting_for_image_prompt' or state == 'waiting_for_avatar_prompt':
            await update.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
            try:
                await update.message.reply_text("⏳ Генерирую изображение...")
                
                # Определяем модель в зависимости от типа генерации
                model = "stability-ai/sdxl" if state == 'waiting_for_image_prompt' else "stability-ai/stable-diffusion-xl"
                
                image_url = await self.generate_image(text, model)
                if image_url:
                    await update.message.reply_photo(image_url)
                else:
                    await update.message.reply_text("⚠️ Не удалось сгенерировать изображение")
                
                del self.user_states[user_id]
            except Exception as e:
                logger.error(f"Ошибка генерации изображения: {e}")
                await update.message.reply_text("⚠️ Произошла ошибка при генерации")
        else:
            # Обработка обычного текста
            response = await self.generate_response(text)
            await update.message.reply_text(response, parse_mode="Markdown")

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🎙️ Голосовые сообщения пока не поддерживаются")

    async def generate_image(self, prompt: str, model: str = "stability-ai/sdxl") -> str | None:
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
            "model": model,
            "width": 1024,
            "height": 1024,
            "quality": "standard",
            "num_images": 1
        }

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
                async with session.post(
                    "https://openrouter.ai/api/v1/images/generations",
                    headers=headers,
                    json=payload
                ) as resp:
                    if resp.status != 200:
                        error = await resp.text()
                        logger.error(f"❌ Ошибка генерации: {resp.status} - {error}")
                        return None

                    data = await resp.json()
                    return data.get("data", [{}])[0].get("url")
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
            "model": "openai/gpt-4",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload
                ) as resp:
                    if resp.status != 200:
                        error = await resp.text()
                        logger.error(f"❌ Ошибка запроса: {resp.status} - {error}")
                        return "⚠️ Ошибка при обработке запроса"

                    data = await resp.json()
                    return data.get("choices", [{}])[0].get("message", {}).get("content", "⚠️ Нет ответа")
        except Exception as e:
            logger.exception("❌ Ошибка запроса к API")
            return "⚠️ Ошибка при обработке запроса"

# --- FastAPI приложение ---
web_app = FastAPI()
bot_manager = BotManager()

@web_app.on_event("startup")
async def startup_event():
    if not await bot_manager.initialize():
        raise RuntimeError("❌ Бот не инициализирован")

@web_app.post("/webhook")
async def handle_webhook(request: Request):
    # Проверка секретного токена
    if request.headers.get('X-Telegram-Bot-Api-Secret-Token') != os.getenv("WEBHOOK_SECRET"):
        return JSONResponse(
            status_code=403,
            content={"status": "error", "message": "Forbidden"}
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
        web_app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("DEBUG", "false").lower() == "true"
    )
