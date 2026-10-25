import os
import time
import logging
import threading
import random
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

TOKEN = os.environ["BOT_TOKEN"]
WEBHOOK_URL = os.environ["RENDER_EXTERNAL_URL"].rstrip("/")

bot = telebot.TeleBot(TOKEN, parse_mode=None)
app = Flask(__name__)

# Хранилища данных
muted_chats = set() 
muted_business = set()
active_spam = {}
auto_replies = {}

def parse_command(text):
    if not text: return None, ""
    t = text.strip()
    low = t.lower()

    if low.startswith("/"):
        cmd = low.split()[0]
        if "@" in cmd: cmd = cmd.split("@", 1)[0]
        if cmd in ("/mute", "/мут"): return "mute_on", ""
        if cmd in ("/unmute", "/размут", "/анмут"): return "mute_off", ""
        if cmd in ("/stop", "/стоп"): return "stop_spam", ""
        if cmd == "/st": return "sticker_spam", ""
        if cmd == "/s" and len(t.split(" ", 1)) == 2: return "text_spam", t.split(" ", 1)[1].strip()
        if cmd == "/ping": return "ping", ""
        return None, ""

    if low == ".мут": return "mute_on", ""
    if low in (".размут", ".анмут"): return "mute_off", ""
    if low == ".стоп": return "stop_spam", ""
    if low == ".ст": return "sticker_spam", ""
    if low.startswith(".с "): return "text_spam", t[3:].strip()
    
    if low == ".пинг": return "ping", ""
    if low == ".кубик": return "dice", ""
    if low == ".рулетка": return "roulette", ""
    if low == ".инфо": return "info", ""
    if low.startswith(".шар "): return "ball", t[5:].strip()
    if low.startswith(".скажи "): return "say", t[7:].strip()
    
    if low == ".обнять": return "hug", ""
    if low == ".поцеловать": return "kiss", ""
    if low == ".мафия": return "mafia", ""
    
    if low.startswith(".авто "): return "auto_on", t[6:].strip()
    if low == ".авто стоп": return "auto_off", ""

    return None, ""

def is_group_admin(message):
    try:
        m = bot.get_chat_member(message.chat.id, message.from_user.id)
        return m.status in ("administrator", "creator")
    except: return False

def is_business_owner(message):
    try:
        conn = bot.get_business_connection(message.business_connection_id)
        return conn.user.id == message.from_user.id
    except: return False

def spam_send(fn, chat_key, times=100, delay=0.5):
    stop_event = threading.Event()
    active_spam[chat_key] = stop_event
    def runner():
        for _ in range(times):
            if stop_event.is_set(): break
            try:
                fn()
                if stop_event.wait(delay): break
            except: break
        if chat_key in active_spam: del active_spam[chat_key]
    threading.Thread(target=runner, daemon=True).start()

def try_delete(chat_id, message_id, business_connection_id=None):
    try:
        if business_connection_id:
            bot.delete_business_messages(business_connection_id=business_connection_id, message_ids=[message_id])
        else:
            bot.delete_message(chat_id, message_id)
    except: pass

def delayed_auto_reply(chat_id, bc, text):
    time.sleep(3) # Задержка 3 секунды
    try: bot.send_message(chat_id=chat_id, text=text, business_connection_id=bc, parse_mode='HTML')
    except: pass

# --- КОМАНДА /start И МЕНЮ ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.type == 'private':
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("📖 Открыть меню и правила", callback_data="show_help"))
        bot.send_message(message.chat.id, "Привет! Я бот <b>Еува</b>. 👋\nНажми кнопку ниже, чтобы узнать всё о моих способностях.", parse_mode='HTML', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "show_help")
def callback_show_help(call):
    bot.answer_callback_query(call.id)
    help_text = (
        "<b>🌟 ЕУВА — ТВОЙ ЛИЧНЫЙ АССИСТЕНТ</b> 🌟\n\n"
        
        "<b>⚙️ КАК ПОДКЛЮЧИТЬ:</b>\n"
        "<blockquote>Открой <b>Настройки</b> Telegram -> <b>Аккаунт</b> -> <b>Автоматизация чатов</b> -> Выбери бота <b>Еува</b>.\n"
        "<i>(Это полностью бесплатно, Telegram Premium/Business не нужен!)</i></blockquote>\n\n"
        
        "<b>🛡 УПРАВЛЕНИЕ АНТИСПАМОМ:</b>\n"
        "🔹 <code>.мут</code> / <code>/mute</code> — Включает антиспам (удаляет всё подряд).\n"
        "🔹 <code>.размут</code> — Выключает антиспам.\n\n"
        
        "<b>💥 СПАМ-АТАКА (для приколов):</b>\n"
        "🔹 <code>.с [текст]</code> — Отправить текст 100 раз.\n"
        "🔹 <code>.ст</code> — Отправить стикер 100 раз (в ответ на стикер).\n"
        "🔹 <code>.стоп</code> — Мгновенно остановить спам.\n\n"
        
        "<b>🎲 РАЗВЛЕЧЕНИЯ И ИГРЫ:</b>\n"
        "🔹 <code>.обнять</code> / <code>.поцеловать</code> — (в ответ на сообщение) с кнопками «Принять/Отказать».\n"
        "🔹 <code>.мафия</code> — Раздать роли в игре (напиши в ЛС бота).\n"
        "🔹 <code>.кубик</code> / <code>.рулетка</code> — Анимированные эмодзи.\n"
        "🔹 <code>.шар [вопрос]</code> — Магический шар (Да/Нет).\n"
        "🔹 <code>.скажи [текст]</code> — Бот повторит твой текст.\n"
        "🔹 <code>.пинг</code> — Проверка работы.\n"
        "🔹 <code>.инфо</code> — (в ответ на сообщение) узнать ID человека.\n\n"
        
        "<b>💼 ДЛЯ АВТОМАТИЗАЦИИ ЧАТОВ:</b>\n"
        "🔹 <code>.авто [текст]</code> — Включить умный автоответчик (бот ответит через 3 секунды, как живой человек).\n"
        "🔹 <code>.авто стоп</code> — Выключить автоответчик."
    )
    try: bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=help_text, parse_mode='HTML', reply_markup=None)
    except: pass

# --- ОБРАБОТЧИКИ КНОПОК ОБНИМАШЕК ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("act_"))
def handle_action_callback(call):
    data = call.data.split("_")
    action_type, choice, initiator_id, target_id = data[1], data[2], data[3], data[4]
    
    if str(call.from_user.id) != str(target_id):
        bot.answer_callback_query(call.id, "Эта кнопка не для тебя! 😉", show_alert=True)
        return

    try: initiator = bot.get_chat(int(initiator_id)).first_name
    except: initiator = "Кто-то"
    target = call.from_user.first_name
    
    if choice == "yes":
        if action_type == "hug": text = f"🤗 <b>{target}</b> с радостью обнял(а) <b>{initiator}</b>!"
        else: text = f"😘 <b>{target}</b> поцеловал(а) <b>{initiator}</b>! Какая милота!"
        bot.answer_callback_query(call.id, "Принято!")
    else:
        if action_type == "hug": text = f"💔 <b>{target}</b> уклонился(ась) от объятий <b>{initiator}</b>..."
        else: text = f"🚫 <b>{target}</b> дал(а) пощёчину <b>{initiator}</b> за попытку поцелуя!"
        bot.answer_callback_query(call.id, "Отклонено!")

    try: bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=text, parse_mode='HTML')
    except: pass

# --- ОБЫЧНЫЙ ОБРАБОТЧИК ---
@bot.message_handler(func=lambda m: getattr(m, "business_connection_id", None) is None, content_types=["text", "sticker", "photo", "video", "document", "voice", "audio"])
def handle_message(message):
    if getattr(message, "business_connection_id", None) is not None: return
    if not message.from_user or message.from_user.is_bot: return
    if message.text and message.text.startswith('/start'): return

    action, arg = parse_command(message.text)
    is_private = message.chat.type == "private"
    chat_key = message.chat.id
    is_muted = chat_key in muted_chats

    if is_muted and action not in ("mute_off", "stop_spam"):
        try_delete(chat_key, message.message_id)
        return

    if action == "mute_on":
        if not is_private and not is_group_admin(message): return
        muted_chats.add(chat_key)
        if chat_key in active_spam: active_spam[chat_key].set()
        bot.reply_to(message, "Антиспам включён ✅")
        return
    if action == "mute_off":
        if not is_private and not is_group_admin(message): return
        muted_chats.discard(chat_key)
        bot.reply_to(message, "Антиспам выключен")
        return
    if action == "stop_spam":
        if chat_key in active_spam: active_spam[chat_key].set(); bot.reply_to(message, "Спам остановлен 🛑")
        else: bot.reply_to(message, "Спам и так не запущен")
        return
    if action == "text_spam" and arg:
        if not is_private and not is_group_admin(message): return
        if not arg.strip(". "): bot.reply_to(message, "Нельзя спамить пустотой."); return
        spam_send(lambda: bot.send_message(chat_key, arg), chat_key=chat_key)
        return
    if action == "sticker_spam":
        if not is_private and not is_group_admin(message): return
        if not (message.reply_to_message and message.reply_to_message.sticker): return
        sid = message.reply_to_message.sticker.file_id
        spam_send(lambda: bot.send_sticker(chat_key, sid), chat_key=chat_key)
        return

    if action == "ping": bot.reply_to(message, "Понг! 🏓"); return
    if action == "dice": bot.send_dice(chat_key, emoji='🎲'); return
    if action == "roulette": bot.send_dice(chat_key, emoji='🎰'); return
    if action == "info":
        target = message.reply_to_message.from_user if message.reply_to_message else message.from_user
        bot.reply_to(message, f"👤 Имя: {target.first_name}\n🆔 ID: <code>{target.id}</code>", parse_mode='HTML'); return
    if action == "ball" and arg:
        answers = ["Да ✅", "Нет ❌", "Определенно да 💯", "Даже не думай 🤔", "Спроси позже ⏳", "Вероятно 📈"]
        bot.reply_to(message, f"🎱 {random.choice(answers)}"); return
    if action == "say" and arg: bot.send_message(chat_key, arg); return
    
    if action in ("hug", "kiss"):
        if not message.reply_to_message: bot.reply_to(message, "Ответь на сообщение человека, чтобы применить действие."); return
        target = message.reply_to_message.from_user
        if target.id == message.from_user.id: bot.reply_to(message, "Себя нельзя! Выбери другого человека."); return
        
        action_ru = "обнять" if action == "hug" else "поцеловать"
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✅ Принять", callback_data=f"act_{action}_yes_{message.from_user.id}_{target.id}"),
            InlineKeyboardButton("❌ Отказать", callback_data=f"act_{action}_no_{message.from_user.id}_{target.id}")
        )
        bot.reply_to(message, f"❤️ <b>{message.from_user.first_name}</b> хочет {action_ru} <b>{target.first_name}</b>.\n{target.first_name}, ты согласен(на)?", parse_mode='HTML', reply_markup=markup)
        return

    if action == "mafia":
        roles = ["🔪 Мафия", "🕵️‍♂️ Комиссар", "💉 Доктор", "👨‍🌾 Мирный житель", "👨‍🌾 Мирный житель"]
        if is_private: bot.reply_to(message, f"Твоя роль в игре: {random.choice(roles)}")
        else: bot.reply_to(message, "Игра «Мафия»! Напиши мне в личные сообщения команду <code>.мафия</code>, чтобы получить свою роль в тайне от других.", parse_mode='HTML')
        return

# --- БИЗНЕС ОБРАБОТЧИК (Автоматизация) ---
@bot.business_message_handler(func=lambda m: getattr(m, "business_connection_id", None) is not None, content_types=["text", "sticker", "photo", "video", "document", "voice", "audio"])
def handle_business(message):
    if not message.from_user or message.from_user.is_bot: return

    action, arg = parse_command(message.text)
    bc = message.business_connection_id
    chat_id = message.chat.id
    mute_key = (bc, chat_id)
    is_muted = mute_key in muted_business
    is_owner = is_business_owner(message)

    def send(text, reply_markup=None):
        try: bot.send_message(chat_id=chat_id, text=text, business_connection_id=bc, parse_mode='HTML', reply_markup=reply_markup)
        except: pass

    if is_muted and action not in ("mute_off", "stop_spam"):
        try_delete(chat_id, message.message_id, business_connection_id=bc)
        return

    # АВТООТВЕТЧИК
    if chat_id in auto_replies and not is_owner:
        threading.Thread(target=delayed_auto_reply, args=(chat_id, bc, auto_replies[chat_id]), daemon=True).start()
        return

    if action == "mute_on":
        if not is_owner: send("Только владелец может включать антиспам"); return
        muted_business.add(mute_key); send("Антиспам включён ✅"); return
    if action == "mute_off":
        if not is_owner: send("Только владелец может выключать антиспам"); return
        muted_business.discard(mute_key); send("Антиспам выключен"); return
    if action == "stop_spam":
        if mute_key in active_spam: active_spam[mute_key].set(); send("Спам остановлен 🛑")
        else: send("Спам и так не запущен")
        return
    if action == "text_spam" and arg:
        if not is_owner: return
        if not arg.strip(". "): send("Нельзя спамить пустотой."); return
        spam_send(lambda: bot.send_message(chat_id=chat_id, text=arg, business_connection_id=bc), chat_key=mute_key)
        return
    if action == "sticker_spam":
        if not is_owner: return
        if not (message.reply_to_message and message.reply_to_message.sticker): send("Ответь на стикер"); return
        sid = message.reply_to_message.sticker.file_id
        spam_send(lambda: bot.send_sticker(chat_id=chat_id, sticker=sid, business_connection_id=bc), chat_key=mute_key)
        return

    if action == "ping" and is_owner: send("Понг! 🏓"); return
    if action == "dice" and is_owner: bot.send_dice(chat_id, emoji='🎲', business_connection_id=bc); return
    if action == "roulette" and is_owner: bot.send_dice(chat_id, emoji='🎰', business_connection_id=bc); return
    if action == "info" and is_owner:
        target = message.reply_to_message.from_user if message.reply_to_message else message.from_user
        send(f"👤 Имя: {target.first_name}\n🆔 ID: <code>{target.id}</code>")
        return
    if action == "ball" and arg and is_owner:
        answers = ["Да ✅", "Нет ❌", "Определенно да 💯", "Даже не думай 🤔", "Спроси позже ⏳"]
        send(f"🎱 {random.choice(answers)}"); return
    if action == "say" and arg and is_owner:
        bot.send_message(chat_id=chat_id, text=arg, business_connection_id=bc); return
    
    if action in ("hug", "kiss"):
        if not message.reply_to_message: send("Ответь на сообщение человека."); return
        target = message.reply_to_message.from_user
        if target.id == message.from_user.id: send("Себя нельзя!"); return
        
        action_ru = "обнять" if action == "hug" else "поцеловать"
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✅ Принять", callback_data=f"act_{action}_yes_{message.from_user.id}_{target.id}"),
            InlineKeyboardButton("❌ Отказать", callback_data=f"act_{action}_no_{message.from_user.id}_{target.id}")
        )
        send(f"❤️ <b>{message.from_user.first_name}</b> хочет {action_ru} <b>{target.first_name}</b>.\n{target.first_name}, ты согласен(на)?", reply_markup=markup)
        return

    if action == "mafia":
        send("Чтобы получить роль, напиши мне в личные сообщения команду <code>.мафия</code>")
        return

    if action == "auto_on":
        if not is_owner: return
        if not arg: send("Напиши текст: .авто Я сейчас занят, отвечу позже"); return
        auto_replies[chat_id] = arg
        send(f"🤖 Автоответчик включен!\nБот будет отвечать через 3 секунды этим текстом:\n\n<blockquote>{arg}</blockquote>")
        return
    if action == "auto_off":
        if not is_owner: return
        if chat_id in auto_replies:
            del auto_replies[chat_id]
            send("🤖 Автоответчик выключен.")
        else:
            send("Автоответчик и так не работает.")
        return

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook_handler():
    update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
    bot.process_new_updates([update])
    return "!", 200

@app.route("/")
def health(): return "ok", 200

if __name__ == "__main__":
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(
        url=f"{WEBHOOK_URL}/{TOKEN}",
        allowed_updates=["message", "edited_message", "callback_query", "business_connection", "business_message", "edited_business_message"],
    )
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
