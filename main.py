import logging
import os
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
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

# Инициализация бота (упрощенная версия)
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(storage=MemoryStorage())
user_states: Dict[int, Dict[str, Any]] = {}

# Класс для обработки аудио
class AudioProcessor:
    @staticmethod
    async def convert_ogg_to_mp3(ogg_path: str, mp3_path: str) -> None:
        try:
            audio = AudioSegment.from_file(ogg_path)
            audio.export(mp3_path, format="mp3", bitrate="64k")
        except Exception as e:
            logger.error(f"Ошибка конвертации аудио: {e}")
            raise

    @staticmethod
    async def cleanup_files(*files: str) -> None:
        for file in files:
            try:
                if file and os.path.exists(file):
                    os.remove(file)
            except Exception as e:
                logger.warning(f"Не удалось удалить файл {file}: {e}")

# Обработчики команд
@dp.message(Command("start", "help"))
async def cmd_start(message: types.Message):
    buttons = [
        [types.KeyboardButton(text="🎤 Говори")],
        [types.KeyboardButton(text="🖼 Генерировать картинку")]
    ]
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True
    )
    await message.answer(
        "Привет! Я бот 🤖. Что хочешь сделать?",
        reply_markup=keyboard
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

# Остальные обработчики (текст, голос, изображения) остаются без изменений
# ...

async def on_startup():
    await bot.set_webhook(
        url=WEBHOOK_URL,
        drop_pending_updates=True
    )
    logger.info(f"Бот запущен. Вебхук: {WEBHOOK_URL}")

async def on_shutdown():
    await bot.delete_webhook()
    logger.info("Бот остановлен")

if __name__ == '__main__':
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
    from aiohttp import web
    
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    
    # Регистрация обработчика вебхука
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    
    # Настройка приложения
    setup_application(app, dp, bot=bot)
    
    # Запуск приложения
    web.run_app(app, host="0.0.0.0", port=WEBAPP_PORT)
