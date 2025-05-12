import logging
import os
import aiohttp
import asyncio
import openai
from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils.executor import start_webhook
from pydub import AudioSegment
from typing import Optional, Dict, Any

# Конфигурация
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY")
ELEVEN_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Nova
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # например: https://yourdomain.com
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_PORT = int(os.getenv("PORT", 8000))

if not all([BOT_TOKEN, OPENROUTER_API_KEY, ELEVEN_API_KEY, WEBHOOK_HOST]):
    raise ValueError("Не все обязательные переменные окружения заданы!")

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())
user_states: Dict[int, Dict[str, Any]] = {}

# ---------- Клиенты и утилиты ----------
class AudioProcessor:
    @staticmethod
    async def convert_ogg_to_mp3(ogg_path: str, mp3_path: str) -> None:
        audio = AudioSegment.from_file(ogg_path)
        audio.export(mp3_path, format="mp3")

    @staticmethod
    async def cleanup_files(*files: str) -> None:
        for file in files:
            if file and os.path.exists(file):
                try:
                    os.remove(file)
                except Exception as e:
                    logger.error(f"Ошибка удаления {file}: {e}")

class OpenAIClient:
    def __init__(self):
        openai.api_key = OPENROUTER_API_KEY
        openai.api_base = "https://openrouter.ai/api/v1"
        self.text_model = "openchat/openchat-7b"
        self.image_model = "stabilityai/stable-diffusion"
        self.whisper_model = "whisper-1"
        self.image_size = "512x512"

    async def transcribe_audio(self, path: str) -> Optional[str]:
        try:
            with open(path, "rb") as audio:
                result = openai.Audio.transcribe(self.whisper_model, audio)
            return result["text"]
        except Exception as e:
            logger.error(f"Ошибка распознавания: {e}")
            return None

    async def generate_text_response(self, prompt: str) -> Optional[str]:
        try:
            response = openai.ChatCompletion.create(
                model=self.text_model,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Ошибка генерации текста: {e}")
            return None

    async def generate_image(self, prompt: str) -> Optional[str]:
        try:
            response = openai.Image.create(
                model=self.image_model,
                prompt=prompt,
                n=1,
                size=self.image_size
            )
            return response["data"][0]["url"]
        except Exception as e:
            logger.error(f"Ошибка генерации изображения: {e}")
            return None

class ElevenLabsClient:
    def __init__(self):
        self.api_key = ELEVEN_API_KEY
        self.voice_id = ELEVEN_VOICE_ID

    async def text_to_speech(self, text: str) -> Optional[bytes]:
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.7,
                "similarity_boost": 0.75
            }
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}",
                    headers=headers,
                    json=payload
                ) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    logger.error(f"Ошибка TTS: статус {resp.status}")
        except Exception as e:
            logger.error(f"TTS ошибка: {e}")
        return None

# Инициализация клиентов
openai_client = OpenAIClient()
eleven_labs_client = ElevenLabsClient()

# ---------- Обработчики ----------
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("🎤 Говори", "🖼 Генерировать картинку")
    await message.answer("Привет! Я бот 🤖. Что хочешь сделать?", reply_markup=keyboard)
    user_states[message.from_user.id] = {"waiting_for_image_prompt": False}

@dp.message_handler(lambda msg: msg.text)
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    state = user_states.setdefault(user_id, {"waiting_for_image_prompt": False})

    if message.text == "🎤 Говори":
        state["waiting_for_image_prompt"] = False
        return await message.reply("Жду голосовое сообщение 🎙")

    if message.text == "🖼 Генерировать картинку":
        state["waiting_for_image_prompt"] = True
        return await message.reply("Опиши изображение, которое нужно создать:")

    if state["waiting_for_image_prompt"]:
        await message.reply("Генерирую изображение...")
        url = await openai_client.generate_image(message.text)
        return await message.reply_photo(url) if url else await message.reply("Ошибка генерации 😞")

    response = await openai_client.generate_text_response(message.text)
    await message.reply(response or "Ошибка генерации ответа 😞")

@dp.message_handler(content_types=types.ContentType.VOICE)
async def handle_voice(message: types.Message):
    user_id = message.from_user.id
    ogg_path = f"voice_{user_id}.ogg"
    mp3_path = f"voice_{user_id}.mp3"
    tts_path = f"reply_{user_id}.mp3"

    try:
        file = await bot.get_file(message.voice.file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"

        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                with open(ogg_path, 'wb') as f:
                    f.write(await resp.read())

        await AudioProcessor.convert_ogg_to_mp3(ogg_path, mp3_path)
        text = await openai_client.transcribe_audio(mp3_path)

        if not text:
            return await message.reply("Не удалось распознать сообщение 😞")

        await message.reply(f"Вы сказали: {text}")
        response = await openai_client.generate_text_response(text)

        if not response:
            return await message.reply("Ошибка генерации ответа 😞")

        audio = await eleven_labs_client.text_to_speech(response)
        if audio:
            with open(tts_path, 'wb') as f:
                f.write(audio)
            with open(tts_path, 'rb') as f:
                await message.reply_voice(f, caption=response)
        else:
            await message.reply(response)

    except Exception as e:
        logger.error(f"Ошибка обработки голоса: {e}")
        await message.reply("Произошла ошибка при обработке голосового сообщения 😞")
    finally:
        await AudioProcessor.cleanup_files(ogg_path, mp3_path, tts_path)

# ---------- Запуск приложения ----------
async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)
    logger.info("Бот запущен и слушает вебхук.")

async def on_shutdown(dp):
    await bot.delete_webhook()
    logger.info("Бот остановлен.")

if __name__ == '__main__':
    from aiogram import executor
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host="0.0.0.0",
        port=WEBAPP_PORT,
    )
