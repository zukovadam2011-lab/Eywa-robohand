import os
import time
import logging
import threading
import random
import json
import string
import datetime
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ==========================================
# ТУТ МЕНЯЕШЬ ВЕРСИЮ ПРИ ОБНОВЛЕНИИ
CURRENT_VERSION = "2.0" 
# ==========================================

START_TIME = time.time()
TOKEN = os.environ["BOT_TOKEN"]
WEBHOOK_URL = os.environ["RENDER_EXTERNAL_URL"].rstrip("/")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

bot = telebot.TeleBot(TOKEN, parse_mode=None)
app = Flask(__name__)

VERSION_FILE = "version.json"
muted_chats = set() 
muted_business = set()
active_spam = {}
auto_replies = {}

# --- БАЗЫ ДАННЫХ ---
QUOTES = ["Всё, что нас не убивает, делает нас сильнее.", "Единственный способ сделать работу хорошо — любить её.", "Не откладывай на завтра то, что можно сделать сегодня."]
JOKES = ["— Как называется боязнь прихода Деда Мороза? — Клаустрофобия.", "Моя кровать — это сгусток магии, который не отпускает меня по утрам.", "Программист — это машина, которая превращает кофе в код."]
COMPLIMENTS = ["Ты сегодня отлично выглядишь! 😎", "С тобой так приятно общаться! 💖", "Ты очень умный(ая) и крутой(ая)! 🔥", "Твоя улыбка озаряет чат! ✨"]
TRUTHS = ["Какой твой самый большой страх?", "Что самое глупое ты делал(а) в жизни?", "Какая твоя самая странная привычка?"]
DARES = ["Отправь смешной стикер.", "Напиши комплимент следующему, кто напишет в чат.", "Напиши 'Я котик' и отправь это в чат."]
RIDDLES = ["Зимой и летом одним цветом. (Ёлка)", "Висит груша, нельзя скушать. (Лампочка)", "Кто говорит на всех языках? (Эхо)"]

def notify_owner():
    time.sleep(5) 
    last_version = ""
    if os.path.exists(VERSION_FILE):
        try:
            with open(VERSION_FILE, "r") as f: last_version = json.load(f).get("version", "")
        except: pass
    if last_version != CURRENT_VERSION:
        if OWNER_ID != 0:
            try: 
                bot.send_message(OWNER_ID, f"🚀 <b>Eywa обновлена до v{CURRENT_VERSION}!</b>\nЗагляни в /start, там теперь 30+ команд!", parse_mode='HTML')
            except: pass
        try:
            with open(VERSION_FILE, "w") as f: json.dump({"version": CURRENT_VERSION}, f)
        except: pass

def parse_command(text):
    if not text: return None, ""
    t = text.strip()
    low = t.lower()

    if low.startswith("/"):
        cmd = low.split()[0].split("@")[0]
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
    if low == ".кубик20": return "d20", ""
    if low == ".рулетка": return "roulette", ""
    if low == ".инфо": return "info", ""
    if low == ".статистика": return "stats", ""
    if low.startswith(".шар "): return "ball", t[5:].strip()
    if low.startswith(".скажи "): return "say", t[7:].strip()
    if low.startswith(".эхо "): return "say", t[5:].strip()
    
    if low == ".обнять": return "hug", ""
    if low == ".поцеловать": return "kiss", ""
    if low == ".погладить": return "pat", ""
    if low == ".ударить": return "hit", ""
    if low == ".укусить": return "bite", ""
    if low == ".подарить": return "gift", ""
    if low == ".мафия": return "mafia", ""
    
    if low == ".рандом": return "random_num", ""
    if low == ".монетка": return "coin", ""
    if low.startswith(".таймер "): return "timer", t[8:].strip()
    if low == ".кнб": return "rps", ""
    if low == ".ктоя": return "who_am_i", ""
    if low == ".факт": return "fact", ""
    if low == ".тык": return "tyk", ""
    if low == ".цитата": return "quote", ""
    if low == ".анекдот": return "joke", ""
    if low == ".комплимент": return "compliment", ""
    if low == ".правда": return "truth", ""
    if low == ".действие": return "dare", ""
    if low == ".загадка": return "riddle", ""
    if low == ".пароль": return "password", ""
    if low == ".дата": return "date", ""
    
    if low.startswith(".выбери "): return "choose", t[8:].strip()
    if low.startswith(".переверни "): return "reverse", t[11:].strip()
    if low.startswith(".верхний "): return "upper", t[9:].strip()
    if low.startswith(".нижний "): return "lower", t[8:].strip()
    if low.startswith(".длина "): return "length", t[7:].strip()
    if low.startswith(".перемешай "): return "shuffle", t[11:].strip()
    if low.startswith(".сердце "): return "heart", t[8:].strip()
    
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
        if business_connection_id: bot.delete_business_messages(business_connection_id=business_connection_id, message_ids=[message_id])
        else: bot.delete_message(chat_id, message_id)
    except: pass

def delayed_auto_reply(chat_id, bc, text):
    time.sleep(3) 
    try: 
        bot.send_message(chat_id=chat_id, text=text, business_connection_id=bc, parse_mode='HTML')
    except: pass

# --- КОМАНДА /start И МЕНЮ ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.type == 'private':
        markup = InlineKeyboardMarkup()
        btn_help = InlineKeyboardButton("Открыть меню и правила", callback_data="show_help")
        markup.add(btn_help)
        bot.send_message(message.chat.id, "Привет! Я бот <b>Еува</b>. 👋\nНажми кнопку ниже, чтобы узнать всё о моих способностях.", parse_mode='HTML', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "show_help")
def callback_show_help(call):
    bot.answer_callback_query(call.id)
    help_text = (
        f"<b>🌟 ЕУВА — МЕГА-АССИСТЕНТ (v{CURRENT_VERSION}) 🌟</b>\n\n"
        "<b>⚙️ ПОДКЛЮЧЕНИЕ:</b>\n"
        "<blockquote>Настройки -> Аккаунт -> Автоматизация чатов -> Выбрать Еува.</blockquote>\n\n"
        "<b>🛡 АНТИСПАМ:</b> <code>.мут</code> / <code>.размут</code>\n"
        "<b>💥 СПАМ:</b> <code>.с [текст]</code>, <code>.ст</code>, <code>.стоп</code>\n\n"
        "<b>🎲 ИГРЫ:</b>\n"
        "🔹 <code>.монетка</code>, <code>.кубик20</code>, <code>.загадка</code>\n"
        "🔹 <code>.правда</code> / <code>.действие</code>\n"
        "🔹 <code>.выбери [a, b, c]</code>, <code>.кнб</code>\n\n"
        "<b>🤝 ВЗАИМОДЕЙСТВИЯ (в ответ):</b>\n"
        "🔹 <code>.обнять</code>, <code>.поцеловать</code>\n"
        "🔹 <code>.погладить</code>, <code>.ударить</code>, <code>.укусить</code>, <code>.подарить</code>\n\n"
        "<b>📝 ТЕКСТ:</b>\n"
        "🔹 <code>.переверни</code>, <code>.верхний</code>, <code>.нижний</code>, <code>.длина</code>\n"
        "🔹 <code>.перемешай</code>, <code>.сердце</code>\n\n"
        "<b>🛠 УТИЛИТЫ:</b>\n"
        "🔹 <code>.пароль</code>, <code>.цитата</code>, <code>.анекдот</code>, <code>.комплимент</code>\n"
        "🔹 <code>.таймер [сек]</code>, <code>.дата</code>, <code>.статистика</code>\n"
        "🔹 <code>.рандом</code>, <code>.факт</code>, <code>.ктоя</code>, <code>.шар</code>\n\n"
        "<b>💼 БИЗНЕС:</b> <code>.авто [текст]</code> и <code>.авто стоп</code>"
    )
    try: 
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=help_text, parse_mode='HTML', reply_markup=None)
    except: pass

# --- КНОПКИ ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("act_"))
def handle_action_callback(call):
    bot.answer_callback_query(call.id)
    try:
        data = call.data.split("_")
        action_type = data[1]
        choice = data[2]
        initiator_id = data[3]
        target_id = data[4]
        
        if str(call.from_user.id) != str(target_id):
            bot.answer_callback_query(call.id, "Эта кнопка не для тебя! 😉", show_alert=True)
            return
            
        try: 
            initiator = bot.get_chat(int(initiator_id)).first_name
        except: 
            initiator = "Кто-то"
            
        target = call.from_user.first_name
        
        if choice == "yes":
            if action_type == "hug": 
                text = f"🤗 <b>{target}</b> с радостью обнял(а) <b>{initiator}</b>!"
            else: 
                text = f"😘 <b>{target}</b> поцеловал(а) <b>{initiator}</b>!"
        else:
            if action_type == "hug": 
                text = f"💔 <b>{target}</b> уклонился(ась) от объятий <b>{initiator}</b>..."
            else: 
                text = f"🚫 <b>{target}</b> дал(а) пощёчину <b>{initiator}</b>!"

        bc_id = getattr(call.message, "business_connection_id", None)
        chat_id = call.message.chat.id
        msg_id = call.message.message_id
        
        try:
            if bc_id: 
                bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, parse_mode='HTML', business_connection_id=bc_id)
            else: 
                bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, parse_mode='HTML')
        except:
            if bc_id: 
                bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML', business_connection_id=bc_id)
            else: 
                bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML')
    except: 
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("rps_"))
def handle_rps_callback(call):
    bot.answer_callback_query(call.id)
    user_choice = call.data.split("_")[1]
    bot_choice = random.choice(["rock", "scissors", "paper"])
    
    names = {"rock": "Камень", "scissors": "Ножницы", "paper": "Бумага"}
    
    if user_choice == bot_choice: 
        result = "🤝 Ничья!"
    elif (user_choice == "rock" and bot_choice == "scissors") or (user_choice == "scissors" and bot_choice == "paper") or (user_choice == "paper" and bot_choice == "rock"): 
        result = "🎉 Ты победил!"
    else: 
        result = "💻 Я победил!"
        
    text = f"Твой выбор: {names[user_choice]}\nМой выбор: {names[bot_choice]}\n\n<b>{result}</b>"
    
    bc_id = getattr(call.message, "business_connection_id", None)
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    
    try:
        if bc_id: 
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, parse_mode='HTML', business_connection_id=bc_id)
        else: 
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, parse_mode='HTML')
    except: 
        pass

# --- ОБЫЧНЫЙ ОБРАБОТЧИК ---
@bot.message_handler(func=lambda m: getattr(m, "business_connection_id", None) is None, content_types=["text", "sticker", "photo", "video", "document", "voice", "audio"])
def handle_message(message):
    if getattr(message, "business_connection_id", None) is not None or not message.from_user or message.from_user.is_bot or (message.text and message.text.startswith('/start')): return

    action, arg = parse_command(message.text)
    is_private = message.chat.type == "private"
    chat_key = message.chat.id
    if chat_key in muted_chats and action not in ("mute_off", "stop_spam"):
        try_delete(chat_key, message.message_id)
        return

    if action == "mute_on":
        if is_private or is_group_admin(message):
            muted_chats.add(chat_key)
            if chat_key in active_spam: active_spam[chat_key].set()
            bot.reply_to(message, "Антиспам включён ✅")
        return
    if action == "mute_off":
        if is_private or is_group_admin(message): 
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
        spam_send(lambda: bot.send_sticker(chat_key, message.reply_to_message.sticker.file_id), chat_key=chat_key)
        return

    if action == "ping": bot.reply_to(message, "Понг! 🏓"); return
    if action == "stats":
        uptime = int(time.time() - START_TIME)
        hours, rem = divmod(uptime, 3600)
        minutes, seconds = divmod(rem, 60)
        bot.reply_to(message, f"📊 <b>Статистика:</b>\nВерсия: {CURRENT_VERSION}\nАптайм: {hours}ч {minutes}м {seconds}с", parse_mode='HTML')
        return
    if action == "info":
        if message.reply_to_message:
            target = message.reply_to_message.from_user
            bot.reply_to(message, f"👤 Имя: {target.first_name}\n🆔 ID: <code>{target.id}</code>", parse_mode='HTML')
        elif is_private: 
            bot.reply_to(message, f"🤖 <b>Бот Еува</b>\n📦 Версия: <b>{CURRENT_VERSION}</b>", parse_mode='HTML')
        else:
            target = message.from_user
            bot.reply_to(message, f"👤 Имя: {target.first_name}\n🆔 ID: <code>{target.id}</code>", parse_mode='HTML')
        return

    if action == "dice": bot.send_dice(chat_key, emoji='🎲'); return
    if action == "d20": bot.reply_to(message, f"🎲 Выпало: <b>{random.randint(1, 20)}</b>", parse_mode='HTML'); return
    if action == "roulette": bot.send_dice(chat_key, emoji='🎰'); return
    if action == "random_num": bot.reply_to(message, f"🎲 Случайное число: <b>{random.randint(1, 100)}</b>", parse_mode='HTML'); return
    if action == "coin": bot.reply_to(message, f"🪙 {random.choice(['Орёл', 'Решка'])}"); return
    if action == "ball" and arg:
        answers = ["Да ✅", "Нет ❌", "Определенно да 💯", "Даже не думай 🤔", "Спроси позже ⏳"]
        bot.reply_to(message, f"🎱 {random.choice(answers)}")
        return
    if action == "who_am_i":
        phrases = ["гений 💡", "ленивец 🦥", "котик 🐱", "путешественник 🌍", "программист 💻", "звезда ⭐", "миллионер 💰", "шпион 🕵️"]
        bot.reply_to(message, f"👤 Сегодня ты — <b>{random.choice(phrases)}</b>!", parse_mode='HTML')
        return
    if action == "tyk": bot.reply_to(message, "Тык! 🫵"); return
    if action == "fact": bot.reply_to(message, f"💡 <b>Факт:</b> {random.choice(['У осьминога три сердца.', 'Мед никогда не портится.', 'Акулы старше деревьев.', 'У улитки 10000 зубов.'])}", parse_mode='HTML'); return
    if action == "riddle": bot.reply_to(message, f"🤔 <b>Загадка:</b>\n{random.choice(RIDDLES)}"); return
    if action == "truth": bot.reply_to(message, f"😳 <b>Правда:</b>\n{random.choice(TRUTHS)}"); return
    if action == "dare": bot.reply_to(message, f"🔥 <b>Действие:</b>\n{random.choice(DARES)}"); return
    if action == "quote": bot.reply_to(message, f"📜 <i>{random.choice(QUOTES)}</i>", parse_mode='HTML'); return
    if action == "joke": bot.reply_to(message, f"😂 {random.choice(JOKES)}"); return
    if action == "compliment": bot.reply_to(message, random.choice(COMPLIMENTS)); return

    if action == "password":
        pwd = ''.join(random.choices(string.ascii_letters + string.digits + "!@#$%^&*", k=14))
        bot.reply_to(message, f"🔐 Твой пароль:\n<code>{pwd}</code>", parse_mode='HTML')
        return
    if action == "date":
        now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        bot.reply_to(message, f"📅 Сейчас: <b>{now}</b>", parse_mode='HTML')
        return
    if action == "timer":
        try:
            secs = int(arg)
            if secs <= 0 or secs > 86400: raise ValueError
            bot.reply_to(message, f"⏱ Таймер на {secs} сек. запущен!")
            def timer_job():
                time.sleep(secs)
                try: bot.reply_to(message, f"🔔 <b>Время вышло!</b> ({secs} сек.)", parse_mode='HTML')
                except: pass
            threading.Thread(target=timer_job, daemon=True).start()
        except: bot.reply_to(message, "Укажи секунды (1-86400): <code>.таймер 60</code>", parse_mode='HTML')
        return

    if action == "say" and arg: bot.send_message(chat_key, arg); return
    if action == "choose" and arg:
        options = [o.strip() for o in arg.split(",") if o.strip()]
        if options: bot.reply_to(message, f"🤔 Я выбираю: <b>{random.choice(options)}</b>", parse_mode='HTML')
        else: bot.reply_to(message, "Напиши варианты через запятую: <code>.выбери чай, кофе</code>", parse_mode='HTML')
        return
    if action == "reverse" and arg: bot.reply_to(message, f"🔄 {arg[::-1]}"); return
    if action == "upper" and arg: bot.reply_to(message, arg.upper()); return
    if action == "lower" and arg: bot.reply_to(message, arg.lower()); return
    if action == "length" and arg: bot.reply_to(message, f"📏 Длина текста: <b>{len(arg)}</b> симв.", parse_mode='HTML'); return
    if action == "shuffle" and arg: bot.reply_to(message, f"🔀 {' '.join(random.sample(arg.split(), len(arg.split())))}"); return
    if action == "heart" and arg: bot.reply_to(message, arg.replace('а', '4').replace('о', '0').replace('е', '3') + " 💖"); return

    if action in ("hug", "kiss"):
        if not message.reply_to_message: bot.reply_to(message, "Ответь на сообщение человека."); return
        target = message.reply_to_message.from_user
        if target.id == message.from_user.id: bot.reply_to(message, "Себя нельзя!"); return
        action_ru = "обнять" if action == "hug" else "поцеловать"
        
        # БЕЗОПАСНОЕ СОЗДАНИЕ КНОПОК
        btn_yes = InlineKeyboardButton("Принять", callback_data=f"act_{action}_yes_{message.from_user.id}_{target.id}")
        btn_no = InlineKeyboardButton("Отказать", callback_data=f"act_{action}_no_{message.from_user.id}_{target.id}")
        markup = InlineKeyboardMarkup().add(btn_yes, btn_no)
        
        bot.reply_to(message, f"❤️ <b>{message.from_user.first_name}</b> хочет {action_ru} <b>{target.first_name}</b>.\n{target.first_name}, ты согласен(на)?", parse_mode='HTML', reply_markup=markup)
        return
    if action in ("pat", "hit", "bite", "gift"):
        if not message.reply_to_message: bot.reply_to(message, "Ответь на сообщение человека."); return
        t = message.reply_to_message.from_user.first_name
        u = message.from_user.first_name
        if action == "pat": bot.reply_to(messag
