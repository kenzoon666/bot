import logging
import os
import openai
import aiohttp
from aiogram import Bot, Dispatcher, executor, types
from pydub import AudioSegment
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY")

if not BOT_TOKEN or not OPENROUTER_API_KEY or not ELEVEN_API_KEY:
    raise ValueError("BOT_TOKEN, OPENROUTER_API_KEY или ELEVEN_API_KEY не заданы!")

openai.api_key = OPENROUTER_API_KEY
openai.api_base = "https://openrouter.ai/api/v1"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
user_states = {}

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("🎤 Говори", "🖼 Генерировать картинку")
    await message.answer("Привет! Я бот 🤖. Что хочешь сделать?", reply_markup=keyboard)
    user_states[message.from_user.id] = {"waiting_for_image_prompt": False}

@dp.message_handler(lambda message: message.text and message.text != '')
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    user_states.setdefault(user_id, {"waiting_for_image_prompt": False})

    if message.text == "🎤 Говори":
        await message.reply("Жду голосовое сообщение.")
        user_states[user_id]["waiting_for_image_prompt"] = False

    elif message.text == "🖼 Генерировать картинку":
        await message.reply("Напиши описание картинки 🖌")
        user_states[user_id]["waiting_for_image_prompt"] = True

    elif user_states[user_id].get("waiting_for_image_prompt"):
        await message.reply("Генерирую изображение... ⏳")
        image_url = await generate_image(message.text)
        if image_url:
            await message.reply_photo(image_url, caption="Вот твоя картинка!")
        else:
            await message.reply("Не удалось сгенерировать изображение 😔")
        user_states[user_id]["waiting_for_image_prompt"] = False

    else:
        response = await gpt_response(message.text)
        await message.reply(response)

@dp.message_handler(content_types=types.ContentType.VOICE)
async def handle_voice(message: types.Message):
    file_info = await bot.get_file(message.voice.file_id)
    file_path = file_info.file_path
    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

    ogg_file = f"voice_{message.from_user.id}.ogg"
    mp3_file = f"voice_{message.from_user.id}.mp3"
    tts_file = f"response_{message.from_user.id}.mp3"

    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as resp:
            with open(ogg_file, 'wb') as f:
                f.write(await resp.read())

    audio = AudioSegment.from_file(ogg_file)
    audio.export(mp3_file, format="mp3")

    with open(mp3_file, "rb") as audio_file:
        transcript = openai.Audio.transcribe("whisper-1", audio_file)

    user_text = transcript["text"]
    await message.reply(f"Вы сказали: {user_text}")

    reply_text = await gpt_response(user_text)

    # Озвучка через ElevenLabs
    voice_id = "21m00Tcm4TlvDq8ikWAM"  # голос Nova, можно заменить
    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "text": reply_text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {"stability": 0.7, "similarity_boost": 0.75}
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers=headers, json=payload
        ) as resp:
            if resp.status == 200:
                with open(tts_file, "wb") as f:
                    f.write(await resp.read())
            else:
                await message.reply("Ошибка при генерации озвучки.")
                tts_file = None

    if tts_file and os.path.exists(tts_file):
        with open(tts_file, "rb") as f:
            await message.reply_voice(f, caption=reply_text)

    for file in [ogg_file, mp3_file, tts_file]:
        if file and os.path.exists(file):
            os.remove(file)

async def gpt_response(prompt):
    response = openai.ChatCompletion.create(
        model="openchat/openchat-7b",
        messages=[{"role": "user", "content": prompt}]
    )
    return response['choices'][0]['message']['content']

async def generate_image(prompt: str):
    try:
        response = openai.Image.create(
            model="stabilityai/stable-diffusion",
            prompt=prompt,
            n=1,
            size="512x512"
        )
        return response['data'][0]['url']
    except Exception as e:
        print(f"Image generation error: {e}")
        return None

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
