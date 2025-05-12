import os
import logging
import aiohttp
from typing import Optional, Dict
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    TypeHandler
)
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
import uvicorn
from dataclasses import dataclass
from functools import wraps

# --- Конфигурация логов ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Конфигурация ---
@dataclass
class Config:
    TELEGRAM_TOKEN: str
    OPENROUTER_API_KEY: str
    WEBHOOK_URL: Optional[str] = None
    WEBHOOK_SECRET: Optional[str] = None
    PORT: int = 8000
    DEBUG: bool = False

    @classmethod
    def from_env(cls):
        return cls(
            TELEGRAM_TOKEN=os.getenv("TELEGRAM_TOKEN"),
            OPENROUTER_API_KEY=os.getenv("OPENROUTER_API_KEY"),
            WEBHOOK_URL=os.getenv("WEBHOOK_URL"),
            WEBHOOK_SECRET=os.getenv("WEBHOOK_SECRET"),
            PORT=int(os.getenv("PORT", 8000)),
            DEBUG=os.getenv("DEBUG", "false").lower() == "true"
        )

# --- Декораторы ---
def error_handler(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}", exc_info=True)
            if len(args) > 0 and isinstance(args[0], Update):
                update = args[0]
                await update.message.reply_text("⚠️ Произошла ошибка. Пожалуйста, попробуйте позже.")
    return wrapper

# --- Основной класс бота ---
class BotManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
            cls._instance.app = None
            cls._instance.user_states = {}
            cls._instance.config = Config.from_env()
        return cls._instance

    async def initialize(self):
        if self.initialized:
            return True

        if not all([self.config.TELEGRAM_TOKEN, self.config.OPENROUTER_API_KEY]):
            logger.error("❌ Missing required environment variables")
            return False

        try:
            self.app = (
                Application.builder()
                .token(self.config.TELEGRAM_TOKEN)
                .updater(None)
                .build()
            )

            # Регистрация обработчиков
            self._register_handlers()

            await self.app.initialize()
            await self.app.start()

            if self.config.WEBHOOK_URL:
                await self._setup_webhook()

            self.initialized = True
            logger.info("✅ Bot initialized successfully")
            return True

        except Exception as e:
            logger.exception("❌ Bot initialization failed")
            return False

    def _register_handlers(self):
        handlers = [
            CommandHandler("start", self.start),
            CommandHandler("help", self.help),
            CommandHandler("menu", self.show_menu),
            CommandHandler("cancel", self.cancel),
            CallbackQueryHandler(self.handle_callback),
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text),
            MessageHandler(filters.VOICE, self.handle_voice),
            TypeHandler(Update, self._check_rate_limit)
        ]
        
        for handler in handlers:
            self.app.add_handler(handler)

    async def _setup_webhook(self):
        try:
            await self.app.bot.set_webhook(
                self.config.WEBHOOK_URL,
                secret_token=self.config.WEBHOOK_SECRET,
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query"]
            )
            logger.info(f"✅ Webhook set to {self.config.WEBHOOK_URL}")
        except Exception as e:
            logger.error(f"❌ Failed to set webhook: {e}")

    async def _check_rate_limit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Проверка ограничения запросов"""
        user_id = update.effective_user.id
        if user_id in context.bot_data.get("rate_limit", {}):
            await update.message.reply_text("⚠️ Слишком много запросов. Подождите 1 минуту.")
            return
        context.bot_data.setdefault("rate_limit", {})[user_id] = True
        context.job_queue.run_once(
            lambda _: context.bot_data["rate_limit"].pop(user_id, None),
            when=60
        )

    @error_handler
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /start"""
        if not update.message:
            return

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

    @error_handler
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /help"""
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
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

    @error_handler
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /cancel"""
        user_id = update.effective_user.id
        self.user_states.pop(user_id, None)
        await update.message.reply_text(
            "Текущее действие отменено",
            reply_markup=ReplyKeyboardRemove()
        )
        await self.start(update, context)

    @error_handler
    async def show_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показ инлайн меню"""
        keyboard = [
            [InlineKeyboardButton("🖼️ Сгенерировать изображение", callback_data='generate_image')],
            [InlineKeyboardButton("🎨 Генерация аватара", callback_data='generate_avatar')],
            [InlineKeyboardButton("🎧 Текст в голос", callback_data='text_to_speech')],
            [InlineKeyboardButton("🎙️ Распознать голос", callback_data='voice_to_text')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)

    @error_handler
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка инлайн кнопок"""
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

    @error_handler
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текстовых сообщений"""
        if not update.message:
            return

        user_id = update.effective_user.id
        text = update.message.text.strip()
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

        # Валидация ввода
        if not text:
            await update.message.reply_text("❌ Сообщение не может быть пустым")
            return

        # Обработка состояний
        if state == 'waiting_for_image_prompt' or state == 'waiting_for_avatar_prompt':
            await self._handle_image_generation(update, text, state)
        else:
            await self._handle_regular_text(update, text)

    async def _handle_image_generation(self, update: Update, text: str, state: str):
        """Обработка генерации изображений"""
        user_id = update.effective_user.id
        await update.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
        
        try:
            await update.message.reply_text("⏳ Генерирую изображение...")
            
            model = "stability-ai/sdxl" if state == 'waiting_for_image_prompt' else "stability-ai/stable-diffusion-xl"
            image_url = await self.generate_image(text, model)
            
            if image_url:
                await update.message.reply_photo(image_url)
            else:
                await update.message.reply_text("⚠️ Не удалось сгенерировать изображение. Проверьте описание.")
            
            self.user_states.pop(user_id, None)
        except Exception as e:
            logger.error(f"Image generation error: {e}")
            await update.message.reply_text("⚠️ Произошла ошибка при генерации")
            self.user_states.pop(user_id, None)

    async def _handle_regular_text(self, update: Update, text: str):
        """Обработка обычного текста"""
        response = await self.generate_response(text)
        await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)

    @error_handler
    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка голосовых сообщений"""
        # Реальная реализация должна использовать Speech-to-Text API
        await update.message.reply_text("🎙️ Голосовые сообщения пока не поддерживаются")

    async def generate_image(self, prompt: str, model: str) -> Optional[str]:
        """Генерация изображения через OpenRouter API"""
        if not prompt.strip():
            return None

        headers = {
            "Authorization": f"Bearer {self.config.OPENROUTER_API_KEY}",
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
                        logger.error(f"Image generation failed: {resp.status} - {error}")
                        return None

                    data = await resp.json()
                    return data.get("data", [{}])[0].get("url")
        except Exception as e:
            logger.exception("Image generation request failed")
            return None

    async def generate_response(self, prompt: str) -> str:
        """Генерация текстового ответа через OpenRouter API"""
        if not prompt.strip():
            return "❌ Запрос не может быть пустым"

        headers = {
            "Authorization": f"Bearer {self.config.OPENROUTER_API_KEY}",
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
                        logger.error(f"Chat request failed: {resp.status} - {error}")
                        return "⚠️ Ошибка при обработке запроса"

                    data = await resp.json()
                    return data.get("choices", [{}])[0].get("message", {}).get("content", "⚠️ Нет ответа")
        except Exception as e:
            logger.exception("Chat request failed")
            return "⚠️ Ошибка при обработке запроса"

# --- FastAPI приложение ---
web_app = FastAPI()
bot_manager = BotManager()

@web_app.on_event("startup")
async def startup_event():
    if not await bot_manager.initialize():
        raise RuntimeError("Bot initialization failed")

@web_app.post("/webhook")
async def handle_webhook(request: Request):
    # Проверка секретного токена
    if request.headers.get('X-Telegram-Bot-Api-Secret-Token') != bot_manager.config.WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden"
        )

    try:
        data = await request.json()
        update = Update.de_json(data, bot_manager.app.bot)
        await bot_manager.app.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        logger.exception("Webhook error")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@web_app.get("/health")
async def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(
        web_app,
        host="0.0.0.0",
        port=bot_manager.config.PORT,
        reload=bot_manager.config.DEBUG
    )
