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

logging.basicConfig(level=logging.INFO)

# Проверка и загрузка переменных окружения
def check_env_vars():
    required_vars = {
        'BOT_TOKEN': os.getenv("BOT_TOKEN"),
        'OPENROUTER_API_KEY': os.getenv("OPENROUTER_API_KEY"),
        'ELEVEN_API_KEY': os.getenv("ELEVEN_API_KEY"),
        'WEBHOOK_HOST': os.getenv("WEBHOOK_HOST")
    }
    missing = [k for k, v in required_vars.items() if not v]
    if missing:
        raise ValueError(f"Отсутствуют переменные окружения: {', '.join(missing)}")
    return required_vars

try:
    env = check_env_vars()
    BOT_TOKEN = env['BOT_TOKEN']
    OPENROUTER_API_KEY = env['OPENROUTER_API_KEY']
    ELEVEN_API_KEY = env['ELEVEN_API_KEY']
    WEBHOOK_HOST = env['WEBHOOK_HOST']
except ValueError as e:
    logging.error(str(e))
    exit(1)

print("Проверка переменных окружения:")
print(f"BOT_TOKEN: {'установлен' if BOT_TOKEN else 'НЕ УСТАНОВЛЕН'}")
print(f"OPENROUTER_API_KEY: {'установлен' if OPENROUTER_API_KEY else 'НЕ УСТАНОВЛЕН'}")
print(f"ELEVEN_API_KEY: {'установлен' if ELEVEN_API_KEY else 'НЕ УСТАНОВЛЕН'}")
print(f"WEBHOOK_HOST: {'установлен' if WEBHOOK_HOST else 'НЕ УСТАНОВЛЕН'}")

ELEVEN_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_PORT = int(os.getenv("PORT", "8000"))

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(storage=MemoryStorage())
user_states: Dict[int, Dict[str, Any]] = {}

class AudioProcessor:
    @staticmethod
    async def convert_ogg_to_mp3(ogg_path: str, mp3_path: str) -> None:
        try:
            audio = AudioSegment.from_file(ogg_path)
            audio.export(mp3_path, format="mp3", bitrate="64k")
        except Exception as e:
            logging.error(f"Ошибка конвертации аудио: {e}")

    @staticmethod
    async def cleanup_files(*files: str) -> None:
        for file in files:
            try:
                if file and os.path.exists(file):
                    os.remove(file)
            except Exception as e:
                logging.warning(f"Не удалось удалить файл {file}: {e}")

@dp.message(Command("start", "help"))
async def cmd_start(message: types.Message):
    kb = types.ReplyKeyboardMarkup(keyboard=[
        [types.KeyboardButton(text="🌜 Говори")],
        [types.KeyboardButton(text="🖼 Генерировать картинку")]
    ], resize_keyboard=True)
    await message.answer("Привет! Я бот 🤖. Что хочешь сделать?", reply_markup=kb)
    user_states[message.from_user.id] = {"waiting_for_image_prompt": False}

@dp.message(F.text == "🌜 Говори")
async def handle_voice_request(message: types.Message):
    user_states[message.from_user.id] = {"waiting_for_image_prompt": False}
    await message.reply("Отправь мне голосовое сообщение 🎙️")

@dp.message(F.text == "🖼 Генерировать картинку")
async def handle_image_request(message: types.Message):
    user_states[message.from_user.id] = {"waiting_for_image_prompt": True}
    await message.reply("Опиши изображение, которое нужно создать:")

@dp.message(F.voice)
async def handle_voice(message: types.Message):
    user_id = message.from_user.id
    try:
        voice = message.voice
        file = await bot.get_file(voice.file_id)
        ogg_path = f"voice_{user_id}.ogg"
        mp3_path = f"voice_{user_id}.mp3"
        await bot.download_file(file.file_path, destination=ogg_path)
        await AudioProcessor.convert_ogg_to_mp3(ogg_path, mp3_path)

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        with open(mp3_path, "rb") as audio_file:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://openrouter.ai/api/v1/audio/transcriptions",
                    headers=headers,
                    data=audio_file
                ) as resp:
                    result = await resp.json()
                    text = result.get("text", "Не удалось распознать речь")
                    await message.reply(f"Ты сказал: {text}")

        await AudioProcessor.cleanup_files(ogg_path, mp3_path)
    except Exception as e:
        logging.error(f"Ошибка обработки голосового: {e}")
        await message.reply("Произошла ошибка при обработке голосового сообщения.")

@dp.message(F.text)
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    state = user_states.get(user_id, {})
    text = message.text.strip()

    if state.get("waiting_for_image_prompt"):
        try:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "openai/dall-e-3",
                "prompt": text,
                "n": 1,
                "size": "1024x1024"
            }
            async with aiohttp.ClientSession() as session:
                async with session.post("https://openrouter.ai/api/v1/images/generations", json=payload, headers=headers) as resp:
                    result = await resp.json()
                    if resp.status == 200 and result.get("data"):
                        image_url = result["data"][0]["url"]
                        await message.reply_photo(image_url)
                    else:
                        await message.reply("Не удалось сгенерировать изображение.")
        except Exception as e:
            logging.error(f"Ошибка генерации изображения: {e}")
            await message.reply("Произошла ошибка при генерации изображения.")
        finally:
            user_states[user_id]["waiting_for_image_prompt"] = False
    else:
        try:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "openai/gpt-4",
                "messages": [
                    {"role": "system", "content": "Ты — доброжелательный Telegram-бот."},
                    {"role": "user", "content": text}
                ]
            }
            async with aiohttp.ClientSession() as session:
                async with session.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers) as resp:
                    result = await resp.json()
                    reply = result.get("choices", [{}])[0].get("message", {}).get("content", "Не удалось получить ответ.")
                    await message.reply(reply)
        except Exception as e:
            logging.error(f"Ошибка генерации ответа: {e}")
            await message.reply("Произошла ошибка при генерации ответа.")

async def on_startup(app):
    await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    logging.info(f"Бот запущен. Вебхук: {WEBHOOK_URL}")

async def on_shutdown(app):
    await bot.delete_webhook()
    logging.info("Бот остановлен")

if __name__ == '__main__':
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
    from aiohttp import web

    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=WEBAPP_PORT)
