from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext

# Функция для команды start
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text("Привет, я твой Telegram-бот!")

# Функция для команды help
async def help_command(update: Update, context: CallbackContext):
    await update.message.reply_text("Доступные команды:\n/start - Приветствие\n/help - Справка")

# Функция для эхо сообщений
async def echo(update: Update, context: CallbackContext):
    await update.message.reply_text(update.message.text)

async def main():
    TELEGRAM_TOKEN = 'your-telegram-bot-token'  # Замените на свой токен

    # Создаём приложение с токеном
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Добавляем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    # Добавляем обработчик для всех текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Запускаем бота
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
