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

from fastapi import FastAPI, Request, status
import uvicorn

# Инициализация
web_app = FastAPI()
bot_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

# Health check для Render
@web_app.get("/", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "ok", "bot": "running"}

# Вебхук-эндпоинт
@web_app.post("/webhook")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        update = Update.de_json(data, bot_app.bot)
        await bot_app.process_update(update)
    except Exception as e:
        print(f"Webhook error: {e}")
    return {"status": "ok"}

async def setup_webhook():
    webhook_url = f"https://{os.environ['RENDER_SERVICE_NAME']}.onrender.com/webhook"
    await bot_app.bot.set_webhook(
        url=webhook_url,
        drop_pending_updates=True
    )
    print(f"Webhook configured: {webhook_url}")

def main():
    # Регистрация обработчиков
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("help", help_command))
    bot_app.add_handler(CommandHandler("resume", resume))
    bot_app.add_handler(CommandHandler("donate", donate))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Настройка и запуск
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        web_app,
        host="0.0.0.0",
        port=port,
        server_header=False
    )

if __name__ == "__main__":
    import asyncio
    asyncio.run(setup_webhook())
    main()
