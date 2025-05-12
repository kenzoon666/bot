import logging
import os
import openai
import aiohttp
from aiogram import Bot, Dispatcher, executor, types
from pydub import AudioSegment
from dotenv import load_dotenv

load_dotenv()

# Настройки
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
openai.api_key = OPENROUTER_API_KEY
openai.api_base = "https://openrouter.ai/api/v1"

# Логирование
logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Команды
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("🎤 Говори", "🖼 Генерировать картинку")
    await message.answer("Привет! Я бот 🤖. Что хочешь сделать?", reply_markup=keyboard)

# Обработка текста
@dp.message_handler(lambda message: message.text and message.text != '')
async def handle_text(message: types.Message):
    if message.text == "🎤 Говори":
        await message.reply("Жду голосовое сообщение.")
    elif message.text == "🖼 Генерировать картинку":
        await message.reply("Напиши описание картинки.")
    else:
        response = await gpt_response(message.text)
        await message.reply(response)

# Обработка голосовых
@dp.message_handler(content_types=types.ContentType.VOICE)
async def handle_voice(message: types.Message):
    file_info = await bot.get_file(message.voice.file_id)
    file_path = file_info.file_path
    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

    ogg_file = f"voice_{message.from_user.id}.ogg"
    mp3_file = f"voice_{message.from_user.id}.mp3"

    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as resp:
            with open(ogg_file, 'wb') as f:
                f.write(await resp.read())

    # Конвертация OGG → MP3
    audio = AudioSegment.from_file(ogg_file)
    audio.export(mp3_file, format="mp3")

    # Speech-to-Text
    with open(mp3_file, "rb") as audio_file:
        transcript = openai.Audio.transcribe("whisper-1", audio_file)

    user_text = transcript["text"]
    await message.reply(f"Вы сказали: {user_text}")

    # GPT-ответ
    reply_text = await gpt_response(user_text)

    # Text-to-Speech
    audio_response = openai.Audio.speech.create(
        model="elevenlabs-tts",
        voice="nova",
        input=reply_text
    )

    out_file = f"response_{message.from_user.id}.mp3"
    with open(out_file, "wb") as f:
        f.write(audio_response.content)

    # Отправка голосом
    with open(out_file, "rb") as f:
        await message.reply_voice(f, caption=reply_text)

    # Удаление временных файлов
    for file in [ogg_file, mp3_file, out_file]:
        if os.path.exists(file):
            os.remove(file)

# GPT функция
async def gpt_response(prompt):
    response = openai.ChatCompletion.create(
        model="openchat/openchat-7b",
        messages=[{"role": "user", "content": prompt}]
    )
    return response['choices'][0]['message']['content']

# Запуск
if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
