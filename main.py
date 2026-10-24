import os
import time
import logging
import threading
from flask import Flask, request
import telebot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

TOKEN = os.environ["BOT_TOKEN"]  # задай в Render → Environment
WEBHOOK_URL = os.environ["RENDER_EXTERNAL_URL"].rstrip("/")

bot = telebot.TeleBot(TOKEN, parse_mode=None)
app = Flask(__name__)

# состояние мута по чатам
muted_chats: set[int] = set()        # обычные чаты/группы
muted_business: set[str] = set()     # business_connection_id


# ---------- утилиты ----------

def parse_command(text):
    if not text:
        return None, ""
    t = text.strip()
    low = t.lower()

    # /команды@botname
    if low.startswith("/"):
        cmd = low.split()[0]
        if "@" in cmd:
            cmd = cmd.split("@", 1)[0]
        if cmd in ("/mute", "/мут"):
            return "mute_on", ""
        if cmd in ("/unmute", "/размут", "/анмут"):
            return "mute_off", ""
        if cmd == "/st":
            return "sticker_spam", ""
        if cmd == "/s" and len(t.split(" ", 1)) == 2:
            return "text_spam", t.split(" ", 1)[1].strip()
        return None, ""

    # .точки
    if low == ".мут":
        return "mute_on", ""
    if low in (".размут", ".анмут"):
        return "mute_off", ""
    if low == ".ст":
        return "sticker_spam", ""
    if low.startswith(".с "):
        return "text_spam", t[3:].strip()
    return None, ""


def is_group_admin(message):
    try:
        m = bot.get_chat_member(message.chat.id, message.from_user.id)
        return m.status in ("administrator", "creator")
    except Exception as e:
        logging.warning("get_chat_member failed: %s", e)
        return False


def spam_send(fn, times=50, delay=0.5):
    """Отправка спама в фоне, чтобы не блокировать webhook."""
    def runner():
        for _ in range(times):
            try:
                fn()
                time.sleep(delay)
            except Exception as e:
                logging.warning("spam stopped: %s", e)
                return
    threading.Thread(target=runner, daemon=True).start()


def try_delete(chat_id, message_id, business_connection_id=None):
    try:
        if business_connection_id:
            bot.delete_message(
                chat_id=chat_id,
                message_id=message_id,
                business_connection_id=business_connection_id,
            )
        else:
            bot.delete_message(chat_id, message_id)
    except Exception as e:
        # частая причина: бот не админ / нет права delete_messages
        logging.warning("delete failed chat=%s msg=%s: %s", chat_id, message_id, e)


# ---------- обычные чаты и группы ----------

@bot.message_handler(
    func=lambda m: True,
    content_types=["text", "sticker", "photo", "video", "document", "voice", "audio"],
)
def handle_message(message):
    if not message.from_user or message.from_user.is_bot:
        return

    action, arg = parse_command(message.text)
    is_private = message.chat.type == "private"

    # --- .мут ---
    if action == "mute_on":
        if not is_private and not is_group_admin(message):
            bot.reply_to(message, "Только админ может включать антиспам")
            return
        muted_chats.add(message.chat.id)
        bot.reply_to(
            message,
            "Антиспам включён ✅\n\n"
            "Если сообщения не удаляются — проверь:\n"
            "1) бот админ группы с правом «Удалять сообщения»\n"
            "2) Privacy Mode в BotFather = Disable\n"
            "3) бот добавлен в группу заново после смены Privacy",
        )
        return

    # --- .размут ---
    if action == "mute_off":
        if not is_private and not is_group_admin(message):
            bot.reply_to(message, "Только админ может выключать антиспам")
            return
        muted_chats.discard(message.chat.id)
        bot.reply_to(message, "Антиспам выключен")
        return

    # --- .с текст ---
    if action == "text_spam" and arg:
        if not is_private and not is_group_admin(message):
            return
        chat_id = message.chat.id
        spam_send(lambda: bot.send_message(chat_id, arg))
        return

    # --- .ст ---
    if action == "sticker_spam":
        if not is_private and not is_group_admin(message):
            return
        if not (message.reply_to_message and message.reply_to_message.sticker):
            bot.reply_to(message, "Ответь этой командой на стикер")
            return
        chat_id = message.chat.id
        sid = message.reply_to_message.sticker.file_id
        spam_send(lambda: bot.send_sticker(chat_id, sid))
        return

    # --- удаление при муте ---
    if message.chat.id in muted_chats:
        try_delete(message.chat.id, message.message_id)


# ---------- бизнес-чаты ----------

@bot.business_message_handler(
    func=lambda m: True,
    content_types=["text", "sticker", "photo", "video", "document", "voice", "audio"],
)
def handle_business(message):
    if not message.from_user or message.from_user.is_bot:
        return

    action, arg = parse_command(message.text)
    bc = message.business_connection_id
    chat_id = message.chat.id

    def send(text):
        try:
            bot.send_message(chat_id=chat_id, text=text, business_connection_id=bc)
        except Exception as e:
            logging.warning("business send failed: %s", e)

    if action == "mute_on":
        muted_business.add(bc)
        send("Антиспам включён ✅")
        return

    if action == "mute_off":
        muted_business.discard(bc)
        send("Антиспам выключен")
        return

    if action == "text_spam" and arg:
        spam_send(lambda: bot.send_message(
            chat_id=chat_id, text=arg, business_connection_id=bc))
        return

    if action == "sticker_spam":
        if not (message.reply_to_message and message.reply_to_message.sticker):
            send("Ответь этой командой на стикер")
            return
        sid = message.reply_to_message.sticker.file_id
        spam_send(lambda: bot.send_sticker(
            chat_id=chat_id, sticker=sid, business_connection_id=bc))
        return

    if bc in muted_business:
        try_delete(chat_id, message.message_id, business_connection_id=bc)


# ---------- webhook ----------

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook_handler():
    update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
    bot.process_new_updates([update])
    return "!", 200


@app.route("/")
def health():
    return "ok", 200


if __name__ == "__main__":
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(
        url=f"{WEBHOOK_URL}/{TOKEN}",
        allowed_updates=[
            "message",
            "edited_message",
            "business_connection",
            "business_message",
            "edited_business_message",
        ],
    )
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
