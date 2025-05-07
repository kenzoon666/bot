from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# Функция для команды start
def start(update: Update, context: CallbackContext):
    update.message.reply_text("Привет, я твой Telegram-бот!")

# Функция для команды help
def help_command(update: Update, context: CallbackContext):
    update.message.reply_text("Доступные команды:\n/start - Приветствие\n/help - Справка")

# Функция для эхо сообщений
def echo(update: Update, context: CallbackContext):
    update.message.reply_text(update.message.text)

def main():
    TELEGRAM_TOKEN = 'your-telegram-bot-token'  # Замените на свой токен

    # Создаём updater с токеном
    updater = Updater(TELEGRAM_TOKEN, use_context=True)

    # Получаем диспетчера для добавления обработчиков
    dp = updater.dispatcher

    # Добавляем обработчики команд
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))

    # Добавляем обработчик для всех текстовых сообщений
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))

    # Запускаем бота
    updater.start_polling()

    # Ожидаем завершения работы
    updater.idle()

if __name__ == "__main__":
    main()
