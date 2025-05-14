import logging
import os
import aiohttp
import openai
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
from pydub import AudioSegment
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from typing import Optional, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Проверка переменных окружения
def check_env_vars():
    env = {
        'BOT_TOKEN': os.getenv("BOT_TOKEN"),
        'OPENROUTER_API_KEY': os.getenv("OPENROUTER_API_KEY"),
        'ELEVEN_API_KEY': os.getenv("ELEVEN_API_KEY"),
        'WEBHOOK_HOST': os.getenv("WEBHOOK_HOST")
    }
    missing = [k for k, v in env.items() if not v]
    if missing:
        logger.error(f"Отсутствуют переменные окружения: {', '.join(missing)}")
        exit(1)
    return env

env = check_env_vars()
BOT_TOKEN = env['BOT_TOKEN']
OPENROUTER_API_KEY = env['OPENROUTER_API_KEY']
ELEVEN_API_KEY = env['ELEVEN_API_KEY']
WEBHOOK_HOST = env['WEBHOOK_HOST']
ELEVEN_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_PORT = int(os.getenv("PORT", "10000"))

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(storage=MemoryStorage())
user_states: Dict[int, Dict[str, Any]] = {}

# ==== Обработка аудио ====
class AudioProcessor:
    @staticmethod
    async def convert_ogg_to_mp3(ogg_path, mp3_path):
        audio = AudioSegment.from_file(ogg_path)
        audio.export(mp3_path, format="mp3", bitrate="64k")

    @staticmethod
    async def cleanup(*files):
        for f in files:
            if f and os.path.exists(f):
                os.remove(f)

# ==== Вызовы API ====
async def openrouter_chat(prompt: str) -> Optional[str]:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "openai/gpt-3.5-turbo",  # точно работает у всех
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }
    async with aiohttp.ClientSession() as session:
        async with session.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers) as r:
            if r.status != 200:
                logger.error(f"OpenRouter error: {await r.text()}")
                return None
            res = await r.json()
            return res['choices'][0]['message']['content']

REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
REPLICATE_MODEL = "stability-ai/sdxl"  # или другая доступная тебе
REPLICATE_VERSION = "a9b8a43bce0e401abbfa17b860e5ac3b21f3a3dbaedf32c89e2e43b6c35a111b"  # нужно актуальное значение!

async def replicate_image(prompt: str) -> Optional[str]:
    url = f"https://api.replicate.com/v1/predictions"
    headers = {
        "Authorization": f"Token {REPLICATE_API_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "version": REPLICATE_VERSION,
        "input": {"prompt": prompt}
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as resp:
            if resp.status != 201:
                logger.error(f"Ошибка Replicate: {await resp.text()}")
                return None
            response_data = await resp.json()
            prediction_id = response_data["id"]
    
    # Подождём, пока изображение сгенерируется
    for _ in range(10):
        await asyncio.sleep(2)
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{url}/{prediction_id}", headers=headers) as resp:
                response_data = await resp.json()
                if response_data["status"] == "succeeded":
                    return response_data["output"][0]
                elif response_data["status"] == "failed":
                    return None
    return None

async def text_to_speech(text: str) -> Optional[bytes]:
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE_ID}"
    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "text": text,
        "voice_settings": {"stability": 0.3, "similarity_boost": 0.7}
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as r:
            return await r.read() if r.status == 200 else None

async def speech_to_text(file_path: str) -> Optional[str]:
    openai.api_key = OPENROUTER_API_KEY
    with open(file_path, "rb") as f:
        transcript = await openai.Audio.atranscribe("whisper-1", f)
        return transcript.get("text")

# ==== Хендлеры ====
@dp.message(Command("start", "help"))
async def cmd_start(msg: types.Message):
    logger.info(f"Received /start from {msg.from_user.id}")
    if msg.from_user.id not in user_states:
        user_states[msg.from_user.id] = {"waiting_for_image_prompt": False}
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [types.KeyboardButton(text="🎤 Говори")],
        [types.KeyboardButton(text="🖼 Генерировать картинку")]
    ])
    await msg.answer("Привет! Я бот 🤖. Что хочешь сделать?", reply_markup=kb)

@dp.message(F.text == "🎤 Говори")
async def handle_voice_request(msg: types.Message):
    logger.info(f"Voice request from {msg.from_user.id}")
    user_states[msg.from_user.id] = {"waiting_for_image_prompt": False}
    await msg.reply("Отправь мне голосовое сообщение 🎙️")

@dp.message(F.text == "🖼 Генерировать картинку")
async def handle_image_request(msg: types.Message):
    logger.info(f"Image request from {msg.from_user.id}")
    user_states[msg.from_user.id] = {"waiting_for_image_prompt": True}
    await msg.reply("Опиши изображение, которое нужно создать:")

@dp.message(F.voice)
async def handle_voice(msg: types.Message):
    logger.info(f"Voice message from {msg.from_user.id}")
    user_id = msg.from_user.id
    try:
        file = await bot.get_file(msg.voice.file_id)
        ogg_path, mp3_path = f"{user_id}.ogg", f"{user_id}.mp3"
        await bot.download_file(file.file_path, destination=ogg_path)
        await AudioProcessor.convert_ogg_to_mp3(ogg_path, mp3_path)
        text = await speech_to_text(mp3_path)
        logger.info(f"Recognized text: {text}")
        reply = await openrouter_chat(text)
        logger.info(f"AI reply: {reply}")
        audio_bytes = await text_to_speech(reply) if reply else None
        if audio_bytes:
            await msg.answer_voice(
                voice=types.BufferedInputFile(audio_bytes, filename="response.ogg")
            )
        elif reply:
            await msg.reply(reply)
        else:
            await msg.reply("Ошибка при получении ответа от ИИ.")
    except Exception as e:
        logger.error(f"Ошибка в обработке voice: {e}")
        await msg.reply("Ошибка при обработке голосового сообщения.")
    finally:
        await AudioProcessor.cleanup(ogg_path, mp3_path)


@dp.message(F.text)
async def handle_text(msg: types.Message):
    logger.info(f"Text message from {msg.from_user.id}: {msg.text}")
    user_id = msg.from_user.id
    state = user_states.get(user_id, {})
    try:
        if state.get("waiting_for_image_prompt"):
            logger.info(f"Processing image prompt: {msg.text}")
            url = await generate_image(msg.text)
            if url:
                await msg.reply_photo(photo=url)
            else:
                await msg.reply("Не удалось сгенерировать изображение.")
            state["waiting_for_image_prompt"] = False
        else:
            reply = await openrouter_chat(msg.text)
            if reply:
                logger.info(f"AI reply: {reply}")
                await msg.reply(reply)
            else:
                await msg.reply("Ошибка при получении ответа от ИИ.")
    except Exception as e:
        logger.error(f"Ошибка в обработке текста: {e}")
        await msg.reply("Произошла ошибка при обработке текста.")


# ==== Вебхук ====
async def on_startup(app): 
    await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    logger.info(f"Бот запущен. Вебхук: {WEBHOOK_URL}")

async def on_shutdown(app): 
    await bot.delete_webhook()
    logger.info("Бот остановлен")

async def health_check(request):
    return web.Response(text="Bot is running")

if __name__ == '__main__':
    async def main():
        app = web.Application()
        app.router.add_get('/', health_check)

        # ✅ добавляем GET /webhook чтобы Telegram видел, что эндпоинт существует
        async def webhook_check(request):
            return web.Response(text="Webhook is alive")
        app.router.add_get(WEBHOOK_PATH, webhook_check)

        app.on_startup.append(on_startup)
        app.on_shutdown.append(on_shutdown)

        SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host="0.0.0.0", port=WEBAPP_PORT)
        await site.start()

        logging.info(f"Бот запущен. Вебхук: {WEBHOOK_URL}")
        while True:
            await asyncio.sleep(3600)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")

    except KeyboardInterrupt:
        logger.info("Бот остановлен")
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
