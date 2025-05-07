# Основной файл бота
import logging
import os
import openai
import telebot

# === Настройки ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = "openrouter/auto"  # или другой, например, openrouter/mistral-7b

# === Проверка токенов ===
if not TELEGRAM_BOT_TOKEN or not OPENROUTER_API_KEY:
    raise Exception("Не найдены переменные окружения TELEGRAM_BOT_TOKEN или OPENROUTER_API_KEY")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
openai.api_key = OPENROUTER_API_KEY
openai.api_base = "https://openrouter.ai/api/v1"

# === Логирование ===
logging.basicConfig(level=logging.INFO)

# === Обработка команды /start ===
@bot.message_handler(commands=['start'])
def handle_start(message):
    bot.send_message(message.chat.id, "Привет! Отправь мне сообщение, и я отвечу с помощью ИИ.")

# === Обработка обычных сообщений ===
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        response = openai.ChatCompletion.create(
            model=MODEL,
            messages=[{"role": "user", "content": message.text}]
        )
        reply = response.choices[0].message.content
        bot.send_message(message.chat.id, reply)
    except Exception as e:
        logging.error(f"Ошибка при обращении к OpenRouter: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка при обращении к ИИ.")

# === Запуск бота ===
if __name__ == "__main__":
    logging.info("Бот запущен...")
    bot.infinity_polling()
