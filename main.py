import os
import logging
import openai
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, filters, CallbackContext

from dotenv import load_dotenv
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

async def ask_openrouter(prompt):
    try:
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
                if resp.status != 200:
                    return f"Ошибка: {data.get('error', {}).get('message', 'Неизвестная ошибка')}"
                return data["choices"][0]["message"]["content"]
    except Exception as e:
        logging.error(f"Ошибка при запросе к OpenRouter: {e}")
        return "Произошла ошибка при обработке вашего запроса."

async def resume(update: Update, context: CallbackContext):
    await update.message.reply_text("Пришли мне информацию: имя, опыт, навыки. Я составлю резюме!")

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text("Привет! Я — умный Telegram-бот. Напиши мне что-нибудь или воспользуйся командами: /resume, /donate")

async def help_command(update: Update, context: CallbackContext):
    await update.message.reply_text("Доступные команды:\n/resume — сгенерировать резюме\n/donate — поддержать проект")

async def donate(update: Update, context: CallbackContext):
    keyboard = [[InlineKeyboardButton("Поддержать на Boosty", url="https://boosty.to/")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Поддержи проект здесь:", reply_markup=reply_markup)

async def handle_message(update: Update, context: CallbackContext):
    user_input = update.message.text
    response = await ask_openrouter(user_input)
    await update.message.reply_text(response)

def main():
    # Используем Updater для старой версии библиотеки
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    # Добавляем обработчики команд и сообщений
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("resume", resume))
    dispatcher.add_handler(CommandHandler("donate", donate))
    dispatcher.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запуск бота
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
