
import os
import time
from flask import Flask, request
import telebot

TOKEN = "8782314424:AAHskWmE2RScH7PXVxiW9dLNRdrvitlKNto"
bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)
WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://eywa-chta-bot.onrender.com")

mute_enabled = False

def check_command(text):
    if not text:
        return None, ""
    cleaned = text.strip()
    lower_text = cleaned.lower()
    
    if lower_text in [".мут", "/mute"]:
        return "mute_on", ""
    elif lower_text in [".размут", ".анмут", "/unmute"]:
        return "mute_off", ""
    elif lower_text.startswith(".с "):
        arg = cleaned[3:].strip()
        return "text_spam", arg
    elif lower_text == ".ст":
        return "sticker_spam", ""
        
    return None, ""

@app.route("/" + TOKEN, methods=["POST"])
def getMessage():
    json_string = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

@app.route("/")
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL + "/" + TOKEN)
    return "Webhook set!", 200

# Обработчик для обычных чатов и групп
@bot.message_handler(func=lambda message: True)
def handle_direct_commands(message):
    global mute_enabled
    action, arg = check_command(message.text)
    
    if action == "mute_on":
        mute_enabled = True
        bot.reply_to(message, "Анти спам включён")
        return
    elif action == "mute_off":
        mute_enabled = False
        bot.reply_to(message, "Анти спам выключен")
        return
    elif action == "text_spam" and arg:
        for _ in range(100):
            try:
                bot.send_message(message.chat.id, arg)
                time.sleep(0.3)
            except Exception:
                break
        return

    if mute_enabled and not message.from_user.is_bot:
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except Exception:
            pass

# Обработчик для бизнес-чатов (личные сообщения)
@bot.business_message_handler(func=lambda message: True)
def handle_business_message(message):
    global mute_enabled
    action, arg = check_command(message.text)

    # 1. Включение антиспама
    if action == "mute_on":
        mute_enabled = True
        try:
            bot.send_message(
                chat_id=message.chat.id,
                text="Анти спам включён",
                business_connection_id=message.business_connection_id
            )
        except Exception:
            pass
        return

    # 2. Выключение антиспама (размут)
    elif action == "mute_off":
        mute_enabled = False
        try:
            bot.send_message(
                chat_id=message.chat.id,
                text="Анти спам выключен",
                business_connection_id=message.business_connection_id
            )
        except Exception:
            pass
        return

    # 3. Текстовый спам (.с текст)
    elif action == "text_spam" and arg:
        for _ in range(100):
            try:
                bot.send_message(
                    chat_id=message.chat.id,
                    text=arg,
                    business_connection_id=message.business_connection_id
                )
                time.sleep(0.3)
            except Exception:
                break
        return

    # 4. Спам стикером (.ст)
    elif action == "sticker_spam" and message.reply_to_message and message.reply_to_message.sticker:
        sticker_id = message.reply_to_message.sticker.file_id
        for _ in range(100):
            try:
                bot.send_sticker(
                    chat_id=message.chat.id,
                    sticker=sticker_id,
                    business_connection_id=message.business_connection_id
                )
                time.sleep(0.3)
            except Exception:
                break
        return

    # Удаление сообщений, если включен мут
    if mute_enabled and not message.from_user.is_bot:
        try:
            bot.delete_message(
                chat_id=message.chat.id,
                message_id=message.message_id,
                business_connection_id=message.business_connection_id
            )
        except Exception:
            pass

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL + "/" + TOKEN)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
    
