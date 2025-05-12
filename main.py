import logging
import os
import aiohttp
import asyncio
from aiogram import Bot, Dispatcher, executor, types
from pydub import AudioSegment
from typing import Optional, Dict, Any

# Конфигурация
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY")
ELEVEN_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Голос Nova

# Проверка переменных окружения
if not all([BOT_TOKEN, OPENROUTER_API_KEY, ELEVEN_API_KEY]):
    raise ValueError("Не все обязательные переменные окружения заданы!")

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
user_states: Dict[int, Dict[str, Any]] = {}

# Константы
IMAGE_MODEL = "stabilityai/stable-diffusion"
TEXT_MODEL = "openchat/openchat-7b"
WHISPER_MODEL = "whisper-1"
IMAGE_SIZE = "512x512"

class AudioProcessor:
    @staticmethod
    async def convert_ogg_to_mp3(ogg_path: str, mp3_path: str) -> None:
        """Конвертирует OGG в MP3"""
        audio = AudioSegment.from_file(ogg_path)
        audio.export(mp3_path, format="mp3")

    @staticmethod
    async def cleanup_files(*files: str) -> None:
        """Удаляет временные файлы"""
        for file in files:
            if file and os.path.exists(file):
                try:
                    os.remove(file)
                except Exception as e:
                    logger.error(f"Ошибка при удалении файла {file}: {e}")

class OpenAIClient:
    def __init__(self):
        self.api_key = OPENROUTER_API_KEY
        self.api_base = "https://openrouter.ai/api/v1"

    async def transcribe_audio(self, audio_path: str) -> Optional[str]:
        """Транскрибирует аудио в текст"""
        try:
            with open(audio_path, "rb") as audio_file:
                transcript = openai.Audio.transcribe(WHISPER_MODEL, audio_file)
                return transcript["text"]
        except Exception as e:
            logger.error(f"Ошибка транскрибации: {e}")
            return None

    async def generate_text_response(self, prompt: str) -> Optional[str]:
        """Генерирует текстовый ответ"""
        try:
            response = openai.ChatCompletion.create(
                model=TEXT_MODEL,
                messages=[{"role": "user", "content": prompt}]
            )
            return response['choices'][0]['message']['content']
        except Exception as e:
            logger.error(f"Ошибка генерации текста: {e}")
            return None

    async def generate_image(self, prompt: str) -> Optional[str]:
        """Генерирует изображение по промпту"""
        try:
            response = openai.Image.create(
                model=IMAGE_MODEL,
                prompt=prompt,
                n=1,
                size=IMAGE_SIZE
            )
            return response['data'][0]['url']
        except Exception as e:
            logger.error(f"Ошибка генерации изображения: {e}")
            return None

class ElevenLabsClient:
    def __init__(self):
        self.api_key = ELEVEN_API_KEY
        self.voice_id = ELEVEN_VOICE_ID

    async def text_to_speech(self, text: str) -> Optional[bytes]:
        """Преобразует текст в речь"""
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
                    logger.error(f"Ошибка ElevenLabs API: {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"Ошибка запроса к ElevenLabs: {e}")
            return None

# Инициализация клиентов
openai_client = OpenAIClient()
eleven_labs_client = ElevenLabsClient()

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    """Обработчик команды /start"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("🎤 Говори", "🖼 Генерировать картинку")
    await message.answer("Привет! Я бот 🤖. Что хочешь сделать?", reply_markup=keyboard)
    user_states[message.from_user.id] = {"waiting_for_image_prompt": False}

@dp.message_handler(lambda message: message.text and message.text != '')
async def handle_text(message: types.Message):
    """Обработчик текстовых сообщений"""
    user_id = message.from_user.id
    user_state = user_states.setdefault(user_id, {"waiting_for_image_prompt": False})

    if message.text == "🎤 Говори":
        await message.reply("Жду голосовое сообщение.")
        user_state["waiting_for_image_prompt"] = False
        return

    if message.text == "🖼 Генерировать картинку":
        await message.reply("Напиши описание картинки 🖌")
        user_state["waiting_for_image_prompt"] = True
        return

    if user_state.get("waiting_for_image_prompt"):
        await message.reply("Генерирую изображение... ⏳")
        image_url = await openai_client.generate_image(message.text)
        if image_url:
            await message.reply_photo(image_url, caption="Вот твоя картинка!")
        else:
            await message.reply("Не удалось сгенерировать изображение 😔")
        user_state["waiting_for_image_prompt"] = False
        return

    response = await openai_client.generate_text_response(message.text)
    if response:
        await message.reply(response)
    else:
        await message.reply("Произошла ошибка при обработке запроса 😔")

@dp.message_handler(content_types=types.ContentType.VOICE)
async def handle_voice(message: types.Message):
    """Обработчик голосовых сообщений"""
    user_id = message.from_user.id
    file_prefix = f"voice_{user_id}"
    
    try:
        # Скачивание голосового сообщения
        file_info = await bot.get_file(message.voice.file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        
        ogg_file = f"{file_prefix}.ogg"
        mp3_file = f"{file_prefix}.mp3"
        tts_file = f"response_{user_id}.mp3"

        # Скачивание и конвертация аудио
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                with open(ogg_file, 'wb') as f:
                    f.write(await resp.read())

        await AudioProcessor.convert_ogg_to_mp3(ogg_file, mp3_file)

        # Транскрибация аудио
        user_text = await openai_client.transcribe_audio(mp3_file)
        if not user_text:
            await message.reply("Не удалось распознать голосовое сообщение 😔")
            return

        await message.reply(f"Вы сказали: {user_text}")

        # Генерация текстового ответа
        reply_text = await openai_client.generate_text_response(user_text)
        if not reply_text:
            await message.reply("Не удалось сгенерировать ответ 😔")
            return

        # Озвучка ответа
        audio_data = await eleven_labs_client.text_to_speech(reply_text)
        if audio_data:
            with open(tts_file, "wb") as f:
                f.write(audio_data)
            with open(tts_file, "rb") as f:
                await message.reply_voice(f, caption=reply_text)
        else:
            await message.reply(reply_text)

    except Exception as e:
        logger.error(f"Ошибка обработки голосового сообщения: {e}")
        await message.reply("Произошла ошибка при обработке голосового сообщения 😔")
    finally:
        # Очистка временных файлов
        await AudioProcessor.cleanup_files(ogg_file, mp3_file, tts_file)

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
