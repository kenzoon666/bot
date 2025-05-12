import logging
import os
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode  # Исправленный импорт
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from pydub import AudioSegment
from typing import Optional, Dict, Any
import openai

# Конфигурация
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY", "")
ELEVEN_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}" if BOT_TOKEN else "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}" if WEBHOOK_HOST else None
WEBAPP_PORT = int(os.getenv("PORT", "8000"))

# Проверка конфигурации
if not all([BOT_TOKEN, OPENROUTER_API_KEY, ELEVEN_API_KEY, WEBHOOK_HOST]):
    raise ValueError("Не все обязательные переменные окружения заданы!")

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация бота с новым синтаксисом aiogram 3.x
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())
user_states: Dict[int, Dict[str, Any]] = {}

# ... (остальной код классов AudioProcessor, OpenAIClient, ElevenLabsClient остается без изменений)

# Обработчики с новым синтаксисом aiogram 3.x
@dp.message(commands=['start', 'help'])  # Новый декоратор
async def cmd_start(message: types.Message):
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="🎤 Говори"))
    builder.add(types.KeyboardButton(text="🖼 Генерировать картинку"))
    
    await message.answer(
        "Привет! Я бот 🤖. Что хочешь сделать?",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )
    user_states[message.from_user.id] = {"waiting_for_image_prompt": False}

# ... (аналогично обновить другие обработчики с новым синтаксисом)

async def on_startup(bot: Bot):
    await bot.set_webhook(
        url=WEBHOOK_URL,
        drop_pending_updates=True
    )
    logger.info(f"Бот запущен. Вебхук: {WEBHOOK_URL}")

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    logger.info("Бот остановлен")

if __name__ == '__main__':
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
    from aiohttp import web
    
    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    
    async def on_startup_app(app):
        await on_startup(bot)
    
    app.on_startup.append(on_startup_app)
    app.on_shutdown.append(on_shutdown)
    
    web.run_app(app, host="0.0.0.0", port=WEBAPP_PORT)
