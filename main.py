import logging
import os
import aiohttp
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils.executor import start_webhook
from pydub import AudioSegment
from typing import Optional, Dict, Any
import openai

# Конфигурация (добавлены значения по умолчанию для тестирования)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY", "")
ELEVEN_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Nova
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}" if BOT_TOKEN else "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}" if WEBHOOK_HOST else None
WEBAPP_PORT = int(os.getenv("PORT", "8000"))  # Render использует PORT

# Проверка конфигурации с более информативным сообщением
required_vars = {
    "BOT_TOKEN": BOT_TOKEN,
    "OPENROUTER_API_KEY": OPENROUTER_API_KEY,
    "ELEVEN_API_KEY": ELEVEN_API_KEY,
    "WEBHOOK_HOST": WEBHOOK_HOST
}

missing_vars = [name for name, value in required_vars.items() if not value]
if missing_vars:
    raise ValueError(f"Отсутствуют обязательные переменные окружения: {', '.join(missing_vars)}")

# Логирование с более подробным форматом
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация бота с таймаутами
bot = Bot(
    token=BOT_TOKEN,
    parse_mode=ParseMode.HTML,
    timeout=30  # Увеличенный таймаут для работы с API
)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())
user_states: Dict[int, Dict[str, Any]] = {}

# ---------- Клиенты и утилиты (оптимизированные версии) ----------
class AudioProcessor:
    @staticmethod
    async def convert_ogg_to_mp3(ogg_path: str, mp3_path: str) -> None:
        try:
            audio = AudioSegment.from_file(ogg_path)
            audio.export(mp3_path, format="mp3", bitrate="64k")  # Оптимизированный битрейт
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

class OpenAIClient:
    def __init__(self):
        self.client = openai.OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1"
        )
        self.text_model = "openchat/openchat-7b"
        self.image_model = "stabilityai/stable-diffusion-xl-1024-v1-0"  # Обновленная модель
        self.whisper_model = "whisper-1"
        self.image_size = "1024x1024"  # Увеличенный размер

    async def transcribe_audio(self, path: str) -> Optional[str]:
        try:
            with open(path, "rb") as audio:
                result = self.client.audio.transcriptions.create(
                    file=audio,
                    model=self.whisper_model
                )
            return result.text
        except Exception as e:
            logger.error(f"Ошибка распознавания: {e}")
            return None

    async def generate_text_response(self, prompt: str) -> Optional[str]:
        try:
            response = self.client.chat.completions.create(
                model=self.text_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Ошибка генерации текста: {e}")
            return None

    async def generate_image(self, prompt: str) -> Optional[str]:
        try:
            response = self.client.images.generate(
                model=self.image_model,
                prompt=prompt,
                n=1,
                size=self.image_size,
                response_format="url"
            )
            return response.data[0].url
        except Exception as e:
            logger.error(f"Ошибка генерации изображения: {e}")
            return None

class ElevenLabsClient:
    def __init__(self):
        self.api_key = ELEVEN_API_KEY
        self.voice_id = ELEVEN_VOICE_ID
        self.timeout = aiohttp.ClientTimeout(total=30)  # Таймаут для запросов

    async def text_to_speech(self, text: str) -> Optional[bytes]:
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "accept": "audio/mpeg"
        }
        payload = {
            "text": text,
            "model_id": "eleven_monolingual_v2",  # Обновленная модель
            "voice_settings": {
                "stability": 0.7,
                "similarity_boost": 0.75
            }
        }
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}",
                    headers=headers,
                    json=payload
                ) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    error_text = await resp.text()
                    logger.error(f"Ошибка TTS: статус {resp.status}, текст: {error_text}")
        except Exception as e:
            logger.error(f"TTS ошибка: {e}")
        return None

# Инициализация клиентов
openai_client = OpenAIClient()
eleven_labs_client = ElevenLabsClient()

# ---------- Обработчики (с улучшенной обработкой ошибок) ----------
@dp.message_handler(commands=['start', 'help'])
async def cmd_start(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("🎤 Говори", "🖼 Генерировать картинку")
    await message.answer(
        "Привет! Я бот 🤖 с функциями:\n"
        "- Отвечаю на текстовые сообщения\n"
        "- Распознаю голосовые сообщения\n"
        "- Генерирую изображения по описанию\n\n"
        "Выбери действие:",
        reply_markup=keyboard
    )
    user_states[message.from_user.id] = {"waiting_for_image_prompt": False}

@dp.message_handler(lambda msg: msg.text and msg.text.lower() == "🎤 говори")
async def handle_voice_request(message: types.Message):
    user_states[message.from_user.id] = {"waiting_for_image_prompt": False}
    await message.reply("Отправь мне голосовое сообщение 🎙️")

@dp.message_handler(lambda msg: msg.text and msg.text.lower() == "🖼 генерировать картинку")
async def handle_image_request(message: types.Message):
    user_states[message.from_user.id] = {"waiting_for_image_prompt": True}
    await message.reply("Опиши изображение, которое нужно создать:")

@dp.message_handler(lambda msg: msg.text and user_states.get(msg.from_user.id, {}).get("waiting_for_image_prompt"))
async def handle_image_prompt(message: types.Message):
    try:
        await message.reply("⏳ Генерирую изображение...")
        url = await openai_client.generate_image(message.text)
        if url:
            await message.reply_photo(url, caption=f"Запрос: {message.text}")
        else:
            await message.reply("😞 Не удалось сгенерировать изображение. Попробуй другой запрос.")
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        await message.reply("⚠️ Произошла ошибка при генерации изображения")

@dp.message_handler(content_types=types.ContentType.TEXT)
async def handle_text(message: types.Message):
    if message.from_user.id not in user_states:
        user_states[message.from_user.id] = {"waiting_for_image_prompt": False}
    
    if user_states[message.from_user.id]["waiting_for_image_prompt"]:
        return
    
    try:
        await message.reply("⏳ Думаю над ответом...")
        response = await openai_client.generate_text_response(message.text)
        if response:
            if len(response) > 4000:  # Ограничение Telegram на длину сообщения
                response = response[:4000] + "..."
            await message.reply(response)
        else:
            await message.reply("😞 Не удалось сгенерировать ответ")
    except Exception as e:
        logger.error(f"Text processing error: {e}")
        await message.reply("⚠️ Произошла ошибка при обработке запроса")

@dp.message_handler(content_types=types.ContentType.VOICE)
async def handle_voice(message: types.Message):
    user_id = message.from_user.id
    ogg_path = f"temp_voice_{user_id}.ogg"
    mp3_path = f"temp_voice_{user_id}.mp3"
    tts_path = f"temp_reply_{user_id}.mp3"

    try:
        # Скачивание файла
        file = await bot.get_file(message.voice.file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                if resp.status != 200:
                    raise Exception(f"Ошибка скачивания: статус {resp.status}")
                with open(ogg_path, 'wb') as f:
                    f.write(await resp.read())

        # Конвертация и транскрибация
        await AudioProcessor.convert_ogg_to_mp3(ogg_path, mp3_path)
        text = await openai_client.transcribe_audio(mp3_path)
        if not text:
            raise Exception("Не удалось распознать речь")

        await message.reply(f"🎤 Вы сказали:\n\n{text}")
        
        # Генерация ответа
        response = await openai_client.generate_text_response(text)
        if not response:
            raise Exception("Не удалось сгенерировать ответ")

        # Преобразование в речь
        audio = await eleven_labs_client.text_to_speech(response)
        if audio:
            with open(tts_path, 'wb') as f:
                f.write(audio)
            with open(tts_path, 'rb') as f:
                await message.reply_voice(f, caption=response[:1000] + "..." if len(response) > 1000 else response)
        else:
            await message.reply(response[:4000] + "..." if len(response) > 4000 else response)

    except Exception as e:
        logger.error(f"Voice processing error: {e}")
        await message.reply("⚠️ Произошла ошибка при обработке голосового сообщения")
    finally:
        await AudioProcessor.cleanup_files(ogg_path, mp3_path, tts_path)

# ---------- Запуск приложения (с улучшенной обработкой) ----------
async def on_startup(dp):
    try:
        await bot.set_webhook(
            url=WEBHOOK_URL,
            drop_pending_updates=True
        )
        logger.info(f"Вебхук успешно установлен на {WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"Ошибка установки вебхука: {e}")
        raise

async def on_shutdown(dp):
    try:
        await bot.delete_webhook()
        logger.info("Вебхук удален")
    except Exception as e:
        logger.error(f"Ошибка удаления вебхука: {e}")
    await dp.storage.close()
    await dp.storage.wait_closed()

if __name__ == '__main__':
    try:
        logger.info("Запуск бота...")
        start_webhook(
            dispatcher=dp,
            webhook_path=WEBHOOK_PATH,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            skip_updates=True,
            host="0.0.0.0",
            port=WEBAPP_PORT,
            ssl_context=None,  # Render сам обрабатывает SSL
        )
    except Exception as e:
        logger.critical(f"Ошибка запуска бота: {e}")
