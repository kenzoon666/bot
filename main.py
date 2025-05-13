import logging
import os
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
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

# Инициализация бота
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())
user_states: Dict[int, Dict[str, Any]] = {}

# Классы AudioProcessor, OpenAIClient и ElevenLabsClient остаются без изменений
# (используйте те же реализации, что были в предыдущем коде)

# Обработчики
@dp.message(Command("start", "help"))
async def cmd_start(message: types.Message):
    builder = types.ReplyKeyboardBuilder()
    builder.button(text="🎤 Говори")
    builder.button(text="🖼 Генерировать картинку")
    await message.answer(
        "Привет! Я бот 🤖. Что хочешь сделать?",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )
    user_states[message.from_user.id] = {"waiting_for_image_prompt": False}

@dp.message(F.text == "🎤 Говори")
async def handle_voice_request(message: types.Message):
    user_states[message.from_user.id] = {"waiting_for_image_prompt": False}
    await message.reply("Отправь мне голосовое сообщение 🎙️")

@dp.message(F.text == "🖼 Генерировать картинку")
async def handle_image_request(message: types.Message):
    user_states[message.from_user.id] = {"waiting_for_image_prompt": True}
    await message.reply("Опиши изображение, которое нужно создать:")

# Остальные обработчики (для текста, голоса и изображений) адаптируйте аналогично

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
    
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    
    web.run_app(app, host="0.0.0.0", port=WEBAPP_PORT)
