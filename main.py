import os
import logging
import openai
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackContext

from dotenv import load_dotenv
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я — умный Telegram-бот. Напиши мне что-нибудь или воспользуйся командами: /resume, /donate")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Доступные команды:\n/resume — сгенерировать резюме\n/donate — поддержать проект")

async def donate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Поддержать на Boosty", url="https://boosty.to/")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Поддержи проект здесь:", reply_markup=reply_markup)

async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Пришли мне информацию: имя, опыт, навыки. Я составлю резюме!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    response = await ask_openrouter(user_input)
    await update.message.reply_text(response)

async def ask_openrouter(prompt):
    import aiohttp
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://t.me/",
        "X-Title": "TelegramBot"
    }
    payload = {
        "model": "openai/gpt-3.5-turbo",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False
    }
    async with aiohttp.ClientSession() as session:
        async with session.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers) as resp:
            data = await resp.json()
            return data["choices"][0]["message"]["content"]

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("resume", resume))
    app.add_handler(CommandHandler("donate", donate))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

from fastapi import FastAPI, Request
import uvicorn

# Создаем FastAPI приложение
web_app = FastAPI()
bot_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

# Вебхук-эндпоинт для Telegram
@web_app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return {"status": "ok"}

def main():
    # Добавляем все обработчики как раньше
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("help", help_command))
    bot_app.add_handler(CommandHandler("resume", resume))
    bot_app.add_handler(CommandHandler("donate", donate))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запускаем сервер
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(web_app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
