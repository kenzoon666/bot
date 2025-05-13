import logging, os, aiohttp, openai, asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from pydub import AudioSegment
from aiohttp import web
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
        logging.error(f"Отсутствуют переменные окружения: {', '.join(missing)}")
        exit(1)
    return env

env = check_env_vars()
BOT_TOKEN = env['BOT_TOKEN']
OPENROUTER_API_KEY = env['OPENROUTER_API_KEY']
ELEVEN_API_KEY = env['ELEVEN_API_KEY']
WEBHOOK_HOST = env['WEBHOOK_HOST']
ELEVEN_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
WEBHOOK_PATH = "/webhook"  # Простой путь
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_PORT = int(os.getenv("PORT", "10000"))

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(storage=MemoryStorage())
user_states: Dict[int, Dict[str, Any]] = {}

# Обработка аудио
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

    async def openrouter_chat(prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "openrouter/cinematika-7b",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers=headers
        ) as r:
            if r.status != 200:
                logger.error(f"OpenRouter error: {await r.text()}")
                return None
            res = await r.json()
            return res['choices'][0]['message']['content']
    async with aiohttp.ClientSession() as session:
    async with session.post(url, ...) as r:
        if r.status != 200:
            logger.error(f"ElevenLabs error: {await r.text()}")
            return None
        return await r.read()

async def generate_image(prompt: str) -> Optional[str]:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "openrouter/latent-consistency-v1",
        "prompt": prompt
    }
    async with aiohttp.ClientSession() as session:
        async with session.post("https://openrouter.ai/api/v1/images/generations", json=payload, headers=headers) as r:
            res = await r.json()
            return res["data"][0]["url"] if "data" in res else None

async def text_to_speech(text: str) -> Optional[bytes]:
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE_ID}"
    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {"text": text, "voice_settings": {"stability": 0.3, "similarity_boost": 0.7}}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as r:
            return await r.read() if r.status == 200 else None

async def speech_to_text(file_path: str) -> Optional[str]:
    openai.api_key = OPENROUTER_API_KEY
    with open(file_path, "rb") as f:
       transcript = await openai.Audio.atranscribe("whisper-1", f)  # Асинхронный вызов
        return transcript.get("text")

# Команды
@dp.message(Command("start", "help"))
async def cmd_start(msg: types.Message):
    if msg.from_user.id not in user_states:
        user_states[msg.from_user.id] = {"waiting_for_image_prompt": False}
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [types.KeyboardButton(text="🎤 Говори")],
        [types.KeyboardButton(text="🖼 Генерировать картинку")]
    ])
    await msg.answer("Привет! Я бот 🤖. Что хочешь сделать?", reply_markup=kb)

@dp.message(F.text == "🎤 Говори")
async def handle_voice_request(msg: types.Message):
    if msg.from_user.id not in user_states:
        user_states[msg.from_user.id] = {"waiting_for_image_prompt": False}
    await msg.reply("Отправь мне голосовое сообщение 🎙️")

@dp.message(F.text == "🖼 Генерировать картинку")
async def handle_image_request(msg: types.Message):
    if msg.from_user.id not in user_states:
        user_states[msg.from_user.id] = {"waiting_for_image_prompt": True}
    else:
        user_states[msg.from_user.id]["waiting_for_image_prompt"] = True
    await msg.reply("Опиши изображение, которое нужно создать:")

@dp.message(F.text == "🖼 Генерировать картинку")
async def handle_image_request(msg: types.Message):
    user_states[msg.from_user.id] = {"waiting_for_image_prompt": True}
    await msg.reply("Опиши изображение, которое нужно создать:")

@dp.message(F.voice)
async def handle_voice(msg: types.Message):
    try:
        user_id = msg.from_user.id
        voice = msg.voice
        file = await bot.get_file(voice.file_id)
        ogg_path, mp3_path = f"{user_id}.ogg", f"{user_id}.mp3"
        await bot.download_file(file.file_path, destination=ogg_path)
        await AudioProcessor.convert_ogg_to_mp3(ogg_path, mp3_path)
        text = await speech_to_text(mp3_path)
        reply = await openrouter_chat(text)
        audio_bytes = await text_to_speech(reply)
        if audio_bytes:
            await msg.answer_voice(
    voice=types.BufferedInputFile(
        audio_bytes, 
        filename="response.ogg"  # или .mp3
    )
)
        else:
            await msg.reply(reply)
    except Exception as e:
        logger.error(f"Ошибка в обработке voice: {e}")
        await msg.reply("Ошибка при обработке голосового сообщения.")
    finally:
        await AudioProcessor.cleanup(ogg_path, mp3_path)

@dp.message(F.text)
async def handle_text(msg: types.Message):
    try:
        user_id = msg.from_user.id
        state = user_states.get(user_id, {})
        if state.get("waiting_for_image_prompt"):
            url = await generate_image(msg.text)
            if url:
                await msg.reply_photo(photo=url)
            else:
                await msg.reply("Не удалось сгенерировать изображение.")
            state["waiting_for_image_prompt"] = False
        else:
            reply = await openrouter_chat(msg.text)
            await msg.reply(reply)
    except Exception as e:
        logger.error(f"Ошибка в обработке текста: {e}")
        await msg.reply("Произошла ошибка при обработке текста.")

# Вебхук
async def on_startup(app): await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True); logger.info(f"Бот запущен. Вебхук: {WEBHOOK_URL}")
async def on_shutdown(app): await bot.delete_webhook(); logger.info("Бот остановлен")

async def health_check(request):
    """Проверка работоспособности бота"""
    return web.Response(text="Bot is running")

if __name__ == '__main__':
    import asyncio
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
    from aiohttp import web

    async def main():
        app = web.Application()
        app.router.add_get('/', health_check)
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

    asyncio.run(main())
