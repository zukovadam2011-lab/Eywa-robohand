import os
import time
import logging
import threading
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

TOKEN = os.environ["BOT_TOKEN"]
WEBHOOK_URL = os.environ["RENDER_EXTERNAL_URL"].rstrip("/")

bot = telebot.TeleBot(TOKEN, parse_mode=None)
app = Flask(__name__)

muted_chats = set() 
muted_business = set()
active_spam = {}

def parse_command(text):
    if not text:
        return None, ""
    t = text.strip()
    low = t.lower()

    if low.startswith("/"):
        cmd = low.split()[0]
        if "@" in cmd:
            cmd = cmd.split("@", 1)[0]
        if cmd in ("/mute", "/мут"):
            return "mute_on", ""
        if cmd in ("/unmute", "/размут", "/анмут"):
            return "mute_off", ""
        if cmd in ("/stop", "/стоп"):
            return "stop_spam", ""
        if cmd == "/st":
            return "sticker_spam", ""
        if cmd == "/s" and len(t.split(" ", 1)) == 2:
            return "text_spam", t.split(" ", 1)[1].strip()
        return None, ""

    if low == ".мут":
        return "mute_on", ""
    if low in (".размут", ".анмут"):
        return "mute_off", ""
    if low == ".стоп":
        return "stop_spam", ""
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

def is_business_owner(message):
    try:
        conn = bot.get_business_connection(message.business_connection_id)
        return conn.user.id == message.from_user.id
    except Exception as e:
        logging.warning("get_business_connection failed: %s", e)
        return False

def spam_send(fn, chat_key, times=100, delay=0.5):
    stop_event = threading.Event()
    active_spam[chat_key] = stop_event
    
    def runner():
        for _ in range(times):
            if stop_event.is_set():
                break
            try:
                fn()
                if stop_event.wait(delay):
                    break
            except Exception as e:
                logging.warning("spam stopped by error: %s", e)
                break
        if chat_key in active_spam:
            del active_spam[chat_key]
            
    threading.Thread(target=runner, daemon=True).start()

def try_delete(chat_id, message_id, business_connection_id=None):
    try:
        if business_connection_id:
            bot.delete_business_messages(
                business_connection_id=business_connection_id,
                message_ids=[message_id]
            )
        else:
            bot.delete_message(chat_id, message_id)
    except Exception as e:
        logging.warning("delete failed: %s", e)

# --- БЛОК: КОМАНДА /start И МЕНЮ ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.type == 'private':
        markup = InlineKeyboardMarkup()
        btn_help = InlineKeyboardButton("📖 Открыть меню и правила", callback_data="show_help")
        markup.add(btn_help)
        bot.send_message(
            message.chat.id, 
            "Привет! Я бот <b>Еува</b>. 👋\n\n"
            "Я умею защищать чаты от спама, флудить стикерами и работать как твой личный ассистент.\n\n"
            "Нажми на кнопку ниже, чтобы узнать, как меня подключить и какие у меня есть команды.", 
            parse_mode='HTML',
            reply_markup=markup
        )
    else:
        bot.reply_to(message, "Привет! Я бот Еува. Напиши мне в личку /start, чтобы увидеть меню.")

@bot.callback_query_handler(func=lambda call: call.data == "show_help")
def callback_show_help(call):
    bot.answer_callback_query(call.id)
    
    help_text = (
        "<b>🌟 ЕУВА — ТВОЙ АССИСТЕНТ</b> 🌟\n\n"
        
        "<b>⚙️ Как подключить (бесплатно):</b>\n"
        "1. Открой <b>Настройки</b> Telegram.\n"
        "2. Перейди в раздел <b>Аккаунт</b> (или Конфиденциальность).\n"
        "3. Найди пункт <b>«Автоматизация чатов»</b>.\n"
        "4. Подключи бота <b>Еува</b> к своему аккаунту.\n"
        "<i>(Это бесплатная функция, платный Telegram Premium/Business не нужен!)</i>\n\n"
        
        "<b>🛡 Управление антиспамом:</b>\n"
        "🔹 <code>.мут</code> / <code>/mute</code> — Включает антиспам (бот начнёт удалять все сообщения, включая команды спама).\n"
        "🔹 <code>.размут</code> / <code>.анмут</code> — Выключает антиспам.\n\n"
        
        "<b>💥 Спам-атака (для приколов):</b>\n"
        "🔹 <code>.с [текст]</code> — Отправить твой текст 100 раз.\n"
        "🔹 <code>.ст</code> — Отправить 100 раз стикер (нужно ответить на любой стикер этой командой).\n"
        "🔹 <code>.стоп</code> / <code>/stop</code> — Мгновенно остановить рассылку.\n\n"
        
        "<b>📜 Правила и безопасность:</b>\n"
        "<blockquote>1. Не спамьте слишком долго, Telegram может выдать бан вашему аккаунту или боту.\n"
        "2. Если используете бота в группе — сделайте его администратором с правом «Удаление сообщений».</blockquote>"
    )
    
    try:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=help_text,
            parse_mode='HTML',
            reply_markup=None 
        )
    except Exception as e:
        logging.error(f"Ошибка при редактировании сообщения: {e}")

# ------------------------------------------

# ОБЫЧНЫЙ ОБРАБОТЧИК
@bot.message_handler(
    func=lambda m: getattr(m, "business_connection_id", None) is None,
    content_types=["text", "sticker", "photo", "video", "document", "voice", "audio"],
)
def handle_message(message):
    if getattr(message, "business_connection_id", None) is not None:
        return
    if not message.from_user or message.from_user.is_bot:
        return
    if message.text and message.text.startswith('/start'):
        return

    action, arg = parse_command(message.text)
    is_private = message.chat.type == "private"
    chat_key = message.chat.id
    is_muted = chat_key in muted_chats

    # БЛОКИРОВКА: Если чат в муте, удаляем всё, кроме команд размута/стопа
    if is_muted:
        if action not in ("mute_off", "stop_spam"):
            try_delete(chat_key, message.message_id)
            return

    if action == "mute_on":
        if not is_private and not is_group_admin(message):
            bot.reply_to(message, "Только админ может включать антиспам")
            return
        muted_chats.add(chat_key)
        if chat_key in active_spam: active_spam[chat_key].set() # Останавливаем спам
        bot.reply_to(message, "Антиспам включён ✅")
        return

    if action == "mute_off":
        if not is_private and not is_group_admin(message):
            bot.reply_to(message, "Только админ может выключать антиспам")
            return
        muted_chats.discard(chat_key)
        bot.reply_to(message, "Антиспам выключен")
        return
        
    if action == "stop_spam":
        if chat_key in active_spam:
            active_spam[chat_key].set()
            bot.reply_to(message, "Спам остановлен 🛑")
        else:
            bot.reply_to(message, "Спам и так не запущен")
        return

    if action == "text_spam" and arg:
        if not is_private and not is_group_admin(message):
            return
        if not arg.strip(". "): # Защита от пустого спама (точки/пробелы)
            bot.reply_to(message, "Нельзя спамить пустотой или точками.")
            return
        spam_send(lambda: bot.send_message(chat_key, arg), chat_key=chat_key)
        return

    if action == "sticker_spam":
        if not is_private and not is_group_admin(message):
            return
        if not (message.reply_to_message and message.reply_to_message.sticker):
            bot.reply_to(message, "Ответь этой командой на стикер")
            return
        sid = message.reply_to_message.sticker.file_id
        spam_send(lambda: bot.send_sticker(chat_key, sid), chat_key=chat_key)
        return


# БИЗНЕС ОБРАБОТЧИК (Автоматизация чатов)
@bot.business_message_handler(
    func=lambda m: getattr(m, "business_connection_id", None) is not None,
    content_types=["text", "sticker", "photo", "video", "document", "voice", "audio"],
)
def handle_business(message):
    if not message.from_user or message.from_user.is_bot:
        return

    action, arg = parse_command(message.text)
    bc = message.business_connection_id
    chat_id = message.chat.id
    mute_key = (bc, chat_id)
    is_muted = mute_key in muted_business

    def send(text):
        try:
            bot.send_message(chat_id=chat_id, text=text, business_connection_id=bc)
        except Exception as e:
            logging.warning("business send failed: %s", e)

    # БЛОКИРОВКА: Если чат в муте, удаляем всё, кроме команд размута/стопа
    if is_muted:
        if action not in ("mute_off", "stop_spam"):
            try_delete(chat_id, message.message_id, business_connection_id=bc)
            return

    if action == "mute_on":
        if not is_business_owner(message):
            send("Только владелец аккаунта может включать антиспам")
            return
        muted_business.add(mute_key)
        if mute_key in active_spam: active_spam[mute_key].set() # Останавливаем спам
        send("Антиспам включён ✅")
        return

    if action == "mute_off":
        if not is_business_owner(message):
            send("Только владелец аккаунта может выключать антиспам")
            return
        muted_business.discard(mute_key)
        send("Антиспам выключен")
        return

    if action == "stop_spam":
        if mute_key in active_spam:
            active_spam[mute_key].set()
            send("Спам остановлен 🛑")
        else:
            send("Спам и так не запущен")
        return

    if action == "text_spam" and arg:
        if not is_business_owner(message):
            return
        if not arg.strip(". "): # Защита от пустого спама
            send("Нельзя спамить пустотой или точками.")
            return
        spam_send(lambda: bot.send_message(
            chat_id=chat_id, text=arg, business_connection_id=bc), chat_key=mute_key)
        return

    if action == "sticker_spam":
        if not is_business_owner(message):
            return
        if not (message.reply_to_message and message.reply_to_message.sticker):
            send("Ответь этой командой на стикер")
            return
        sid = message.reply_to_message.sticker.file_id
        spam_send(lambda: bot.send_sticker(
            chat_id=chat_id, sticker=sid, business_connection_id=bc), chat_key=mute_key)
        return


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
            "callback_query",
            "business_connection",
            "business_message",
            "edited_business_message",
        ],
    )
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
