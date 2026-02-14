import os
import telebot
from flask import Flask, request
from datetime import datetime, timedelta, timezone
import json
import time
import threading
import shutil

# ====== НАСТРОЙКИ ЧАСОВОГО ПОЯСА ======
NOVOSIBIRSK_OFFSET = 7

def get_novosibirsk_time():
    utc_time = datetime.now(timezone.utc)
    return utc_time + timedelta(hours=NOVOSIBIRSK_OFFSET)

def format_time(dt=None):
    if dt is None:
        dt = get_novosibirsk_time()
    if isinstance(dt, str):
        return dt
    return dt.strftime("%d.%m.%Y %H:%M:%S")

def format_date(dt=None):
    if dt is None:
        dt = get_novosibirsk_time()
    return dt.strftime("%d.%m.%Y")

def format_time_only(dt=None):
    if dt is None:
        dt = get_novosibirsk_time()
    return dt.strftime("%H:%M")

# ====== НАСТРОЙКИ ======
TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не установлен!")
    exit(1)

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

DATA_FILE = 'bot_data.json'

ADMIN_ID = os.environ.get('ADMIN_ID')
if ADMIN_ID:
    ADMIN_ID = int(ADMIN_ID)
    print(f"👑 Администратор: {ADMIN_ID}")
else:
    print("⚠️ ADMIN_ID не установлен!")
    ADMIN_ID = None

SELLER_CODES = {
    "Александр": "А",
    "Юлия": "Ю",
    "Евгений": "Е",
    "Татьяна": "Т",
    "Рабочий": "Р"
}

CODE_TO_SELLER = {v: k for k, v in SELLER_CODES.items()}

pickup_points = {
    "ул. Галущака 15": "Александр",
    "ул. Беловежская 4/1": "Юлия", 
    "ул. Забалуева 90": "Евгений",
    "ул. Сержанта Коротаева 3": "Татьяна",
    "ул. Бетонная 14/1": "Рабочий"
}

user_data = {}
seller_counters = {}
active_orders = {}
completed_orders = {}
active_chats = {}
admin_chats = {}
admin_chat_counter = 0

# ====== ФУНКЦИИ ======
def generate_order_id(seller_name):
    code = SELLER_CODES[seller_name]
    if seller_name not in seller_counters:
        seller_counters[seller_name] = 0
    seller_counters[seller_name] += 1
    return f"{code}{seller_counters[seller_name]}"

def parse_order_id(order_id):
    if not order_id or len(order_id) < 2:
        return None, None
    code = order_id[0]
    try:
        number = int(order_id[1:])
        seller_name = CODE_TO_SELLER.get(code)
        return seller_name, number
    except:
        return None, None

def save_data():
    data = {
        'seller_counters': seller_counters,
        'active_orders': active_orders,
        'completed_orders': completed_orders,
        'admin_chats': admin_chats,
        'admin_chat_counter': admin_chat_counter
    }
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ Данные сохранены")
    except Exception as e:
        print(f"❌ Ошибка сохранения: {e}")

def load_data():
    global seller_counters, active_orders, completed_orders, active_chats, admin_chats, admin_chat_counter
    if not os.path.exists(DATA_FILE):
        print("📁 Новый файл данных")
        return
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        seller_counters = data.get('seller_counters', {})
        active_orders = data.get('active_orders', {})
        completed_orders = data.get('completed_orders', {})
        admin_chats = data.get('admin_chats', {})
        admin_chat_counter = data.get('admin_chat_counter', 0)
        active_chats = {}
        for order_id, order in active_orders.items():
            if 'buyer_id' in order:
                active_chats[order['buyer_id']] = order_id
        print(f"✅ Загружено: {len(active_orders)} активных, {len(completed_orders)} завершенных")
    except Exception as e:
        print(f"❌ Ошибка загрузки: {e}")

load_data()

def is_admin(user_id):
    return ADMIN_ID is not None and user_id == ADMIN_ID

def get_seller_id(seller_name):
    env_vars = {
        "Александр": "Seller_Aleksandr",
        "Юлия": "Seller_Yulia",
        "Евгений": "Seller_Evgeniy",
        "Татьяна": "Seller_Tatiana",
        "Рабочий": "Seller_Rabochiy"
    }
    env_var_name = env_vars.get(seller_name)
    if not env_var_name:
        return None
    seller_id_str = os.environ.get(env_var_name)
    if not seller_id_str:
        return None
    try:
        return int(seller_id_str)
    except:
        return None

def get_all_seller_ids():
    seller_ids = []
    for seller_name in pickup_points.values():
        seller_id = get_seller_id(seller_name)
        if seller_id:
            seller_ids.append(seller_id)
    return seller_ids

def get_seller_name_by_id(seller_id):
    for seller_name in pickup_points.values():
        if get_seller_id(seller_name) == seller_id:
            return seller_name
    return None

def is_seller(user_id):
    return user_id in get_all_seller_ids()

def get_buyer_link(buyer_id):
    return f"tg://user?id={buyer_id}"

def create_backup(reason=""):
    if not ADMIN_ID:
        return
    try:
        timestamp = get_novosibirsk_time().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{timestamp}.json"
        shutil.copy2(DATA_FILE, backup_name)
        with open(backup_name, 'rb') as f:
            bot.send_document(
                ADMIN_ID,
                f,
                caption=f"💾 Бэкап {format_time()}\n{reason}"
            )
        os.remove(backup_name)
    except Exception as e:
        print(f"❌ Ошибка бэкапа: {e}")

# ====== ФУНКЦИИ ИНТЕРФЕЙСА ======
def show_instruction(chat_id):
    """Показывает пошаговую инструкцию"""
    text = (
        "🟢 *Пошаговая инструкция:*\n\n"
        "1️⃣ Напишите, что хотите заказать\n"
        "2️⃣ Выберите точку самовывоза\n"
        "3️⃣ Менеджер свяжется с вами\n\n"
        "После оформления заказа вы сможете общаться с менеджером прямо в этом чате."
    )
    
    # Основная клавиатура
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    
    if is_seller(chat_id):
        keyboard.row('📋 Мои заказы')
        keyboard.row('📋 Каталог', 'ℹ️ О нас')
    elif is_admin(chat_id):
        keyboard.row('📋 Активные заказы', '📦 Завершенные')
        keyboard.row('📬 Сообщения', '💾 Бэкап')
        keyboard.row('📋 Каталог', 'ℹ️ О нас')
    else:
        keyboard.row('📋 Каталог', 'ℹ️ О нас')
        keyboard.row('👤 Связаться с админом')
    
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=keyboard)

def add_back_button(chat_id, text):
    """Добавляет кнопку возврата к инструкции"""
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row('🔙 Вернуться к оформлению заказа')
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=keyboard)

# ====== ОБРАБОТЧИКИ ======
@bot.message_handler(commands=['start'])
def start(message):
    show_instruction(message.chat.id)

@bot.message_handler(func=lambda m: m.text == '🔙 Вернуться к оформлению заказа')
def back_to_instruction(message):
    show_instruction(message.chat.id)

@bot.message_handler(func=lambda m: m.text == '📋 Каталог')
def catalog(message):
    text = (
        "📋 *Каталог*\n\n"
        "1. Грецкий орех 500г - 400₽\n"
        "2. Миндаль 1000г - 950₽\n"
        "3. Кешью 1000г - 1000₽\n"
        "4. Манго сушеное 500г - 250₽\n"
        "5. Клубника сушеная 500г - 350₽\n"
        "6. Фисташки 500г - 600₽"
    )
    add_back_button(message.chat.id, text)

@bot.message_handler(func=lambda m: m.text == 'ℹ️ О нас')
def about(message):
    text = (
        "🏢 *DP SBOR*\n"
        "Отборные орехи и сухофрукты\n"
        "📍 Новосибирск\n\n"
        "Канал: @dp_sbor"
    )
    add_back_button(message.chat.id, text)

@bot.message_handler(func=lambda m: m.text == '👤 Связаться с админом')
def contact_admin_start(message):
    add_back_button(
        message.chat.id,
        "👤 Напишите сообщение администратору:"
    )
    bot.register_next_step_handler(message, contact_admin_send)

def contact_admin_send(message):
    if message.text == '🔙 Вернуться к оформлению заказа':
        show_instruction(message.chat.id)
        return
    
    user_id = message.from_user.id
    text = message.text
    
    global admin_chat_counter
    if user_id not in admin_chats:
        admin_chat_counter += 1
        admin_chats[user_id] = {
            'id': admin_chat_counter,
            'name': message.from_user.first_name or "Покупатель",
            'messages': []
        }
    
    admin_chats[user_id]['messages'].append({
        'time': format_time(),
        'from': 'user',
        'text': text
    })
    save_data()
    
    add_back_button(user_id, "✅ Сообщение отправлено администратору!")
    
    if ADMIN_ID:
        link = get_buyer_link(user_id)
        admin_text = (
            f"📩 *Новое сообщение #{admin_chats[user_id]['id']}*\n"
            f"👤 {admin_chats[user_id]['name']}\n"
            f"💬 [Связаться]({link})\n"
            f"🕐 {format_time()}\n\n"
            f"{text}"
        )
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.row(
            telebot.types.InlineKeyboardButton("👀 Посмотреть", callback_data=f"chat_{user_id}"),
            telebot.types.InlineKeyboardButton("✅ Закрыть", callback_data=f"close_{user_id}")
        )
        bot.send_message(ADMIN_ID, admin_text, parse_mode="Markdown", reply_markup=keyboard)

@bot.message_handler(func=lambda m: m.text == '📋 Мои заказы')
def seller_orders_list(message):
    user_id = message.from_user.id
    if not is_seller(user_id):
        return
    
    seller_name = get_seller_name_by_id(user_id)
    my_orders = []
    for oid, order in active_orders.items():
        if order['seller_name'] == seller_name:
            my_orders.append((oid, order))
    
    if not my_orders:
        add_back_button(user_id, "📭 Нет активных заказов")
        return
    
    for oid, order in my_orders:
        text = (
            f"📦 *Заказ {oid}*\n"
            f"👤 {order['buyer_name']}\n"
            f"📝 {order['order_text']}\n"
            f"🕐 {order['time']}"
        )
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.row(
            telebot.types.InlineKeyboardButton("✏️ Уточнить", callback_data=f"update_{oid}"),
            telebot.types.InlineKeyboardButton("✅ Завершить", callback_data=f"close_{oid}")
        )
        bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=keyboard)
    
    # Добавляем кнопку возврата
    add_back_button(user_id, "🔙 Вернуться в меню")

@bot.message_handler(func=lambda m: m.text == '📋 Активные заказы')
def admin_active_orders(message):
    if not is_admin(message.from_user.id):
        return
    
    if not active_orders:
        add_back_button(message.from_user.id, "📭 Нет активных заказов")
        return
    
    for oid, order in active_orders.items():
        link = get_buyer_link(order['buyer_id'])
        text = (
            f"📦 *Заказ {oid}*\n"
            f"👤 Продавец: {order['seller_name']}\n"
            f"👤 Покупатель: {order['buyer_name']} 💬 [Связаться]({link})\n"
            f"📍 {order['address']}\n"
            f"📝 {order['order_text']}\n"
            f"🕐 {order['time']}"
        )
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.row(
            telebot.types.InlineKeyboardButton("👀 История", callback_data=f"history_{oid}"),
            telebot.types.InlineKeyboardButton("✅ Завершить", callback_data=f"admin_close_{oid}")
        )
        bot.send_message(message.from_user.id, text, parse_mode="Markdown", reply_markup=keyboard)
    
    add_back_button(message.from_user.id, "🔙 Вернуться в меню")

@bot.message_handler(func=lambda m: m.text == '📦 Завершенные')
def admin_completed_orders(message):
    if not is_admin(message.from_user.id):
        return
    
    if not completed_orders:
        add_back_button(message.from_user.id, "📭 Нет завершенных заказов")
        return
    
    for oid, order in list(completed_orders.items())[-10:]:
        link = get_buyer_link(order['buyer_id'])
        text = (
            f"✅ *Заказ {oid}*\n"
            f"👤 Продавец: {order['seller_name']}\n"
            f"👤 Покупатель: {order['buyer_name']} 💬 [Связаться]({link})\n"
            f"📍 {order['address']}\n"
            f"📝 {order['order_text']}\n"
            f"📅 Создан: {order['time']}\n"
            f"✅ Завершен: {order.get('completed_time', '')}"
        )
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.row(telebot.types.InlineKeyboardButton("👀 История", callback_data=f"history_{oid}"))
        bot.send_message(message.from_user.id, text, parse_mode="Markdown", reply_markup=keyboard)
    
    add_back_button(message.from_user.id, "🔙 Вернуться в меню")

@bot.message_handler(func=lambda m: m.text == '📬 Сообщения')
def admin_chats_list(message):
    if not is_admin(message.from_user.id):
        return
    
    active = []
    for uid, chat in admin_chats.items():
        if not chat.get('closed', False):
            active.append((uid, chat))
    
    if not active:
        add_back_button(message.from_user.id, "📭 Нет новых сообщений")
        return
    
    for uid, chat in active:
        last = chat['messages'][-1] if chat['messages'] else {'text': '', 'time': ''}
        text = (
            f"📩 *#{chat['id']} {chat['name']}*\n"
            f"🕐 {last['time']}\n"
            f"📝 {last['text'][:50]}..."
        )
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.row(
            telebot.types.InlineKeyboardButton("👀 Открыть", callback_data=f"chat_{uid}"),
            telebot.types.InlineKeyboardButton("✅ Закрыть", callback_data=f"close_{uid}")
        )
        bot.send_message(message.from_user.id, text, parse_mode="Markdown", reply_markup=keyboard)
    
    add_back_button(message.from_user.id, "🔙 Вернуться в меню")

@bot.message_handler(func=lambda m: m.text == '💾 Бэкап')
def admin_backup(message):
    if not is_admin(message.from_user.id):
        return
    bot.send_message(message.from_user.id, "⏳ Создаю бэкап...")
    create_backup("Ручной бэкап")
    add_back_button(message.from_user.id, "✅ Бэкап создан!")

@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_text(message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Обработка возврата
    if text == '🔙 Вернуться к оформлению заказа':
        show_instruction(user_id)
        return
    
    # Продавец: ответ на заказ
    if is_seller(user_id) and text.startswith('#'):
        parts = text[1:].split(' ', 1)
        order_id = parts[0].strip().upper()
        msg_text = parts[1] if len(parts) > 1 else ""
        
        if not msg_text:
            bot.send_message(user_id, "❌ Напишите текст после #А1")
            return
        
        if order_id not in active_orders:
            bot.send_message(user_id, f"❌ Заказ {order_id} не найден")
            return
        
        order = active_orders[order_id]
        if order['seller_name'] != get_seller_name_by_id(user_id):
            bot.send_message(user_id, f"❌ Это не ваш заказ")
            return
        
        try:
            bot.send_message(
                order['buyer_id'],
                f"💬 *Сообщение от менеджера:*\n\n{msg_text}"
            )
            bot.send_message(user_id, f"✅ Отправлено для {order_id}")
            
            if 'messages' not in order:
                order['messages'] = []
            order['messages'].append({
                'time': format_time(),
                'from': 'seller',
                'text': msg_text
            })
            save_data()
            
        except Exception as e:
            bot.send_message(user_id, f"❌ Ошибка: {str(e)[:100]}")
        return
    
    # Покупатель: новый заказ
    if user_id in active_chats:
        bot.send_message(user_id, "⚠️ У вас уже есть активный заказ")
        return
    
    user_data[user_id] = {
        'text': text,
        'name': message.from_user.first_name or "Покупатель"
    }
    
    keyboard = telebot.types.InlineKeyboardMarkup()
    for addr in pickup_points.keys():
        keyboard.add(telebot.types.InlineKeyboardButton(addr, callback_data=f"addr_{addr}"))
    
    bot.send_message(user_id, "📍 Выберите точку:", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    data = call.data
    
    if data.startswith('addr_'):
        address = data[5:]
        seller_name = pickup_points[address]
        seller_id = get_seller_id(seller_name)
        
        if not seller_id:
            bot.answer_callback_query(call.id, "❌ Ошибка")
            return
        
        order_id = generate_order_id(seller_name)
        buyer_data = user_data.get(user_id, {})
        
        order = {
            'order_id': order_id,
            'buyer_id': user_id,
            'buyer_name': buyer_data.get('name', 'Покупатель'),
            'seller_id': seller_id,
            'seller_name': seller_name,
            'address': address,
            'order_text': buyer_data.get('text', ''),
            'time': format_time(),
            'status': 'active',
            'messages': []
        }
        
        active_orders[order_id] = order
        active_chats[user_id] = order_id
        save_data()
        
        try:
            seller_text = (
                f"📦 *Новый заказ {order_id}*\n"
                f"👤 {order['buyer_name']}\n"
                f"📍 {address}\n"
                f"📝 {order['order_text']}\n"
                f"🕐 {order['time']}"
            )
            keyboard = telebot.types.InlineKeyboardMarkup()
            keyboard.row(
                telebot.types.InlineKeyboardButton("✏️ Уточнить", callback_data=f"update_{order_id}"),
                telebot.types.InlineKeyboardButton("✅ Завершить", callback_data=f"close_{order_id}")
            )
            bot.send_message(seller_id, seller_text, parse_mode="Markdown", reply_markup=keyboard)
            order['delivered'] = True
        except Exception as e:
            order['delivered'] = False
            order['delivery_error'] = str(e)[:100]
        
        save_data()
        
        if ADMIN_ID:
            link = get_buyer_link(user_id)
            admin_text = (
                f"👑 *Новый заказ {order_id}*\n"
                f"👤 Продавец: {seller_name}\n"
                f"👤 Покупатель: {order['buyer_name']} 💬 [Связаться]({link})\n"
                f"📍 {address}\n"
                f"📝 {order['order_text']}"
            )
            bot.send_message(ADMIN_ID, admin_text, parse_mode="Markdown")
        
        bot.edit_message_text(
            f"✅ Заказ {order_id} принят!\n📍 {address}\nМенеджер скоро свяжется",
            user_id,
            call.message.message_id
        )
        
        create_backup(f"Новый заказ {order_id}")
        bot.answer_callback_query(call.id)
    
    elif data.startswith('update_'):
        order_id = data[7:]
        if order_id not in active_orders:
            bot.answer_callback_query(call.id, "❌ Заказ не найден")
            return
        
        bot.edit_message_text(
            f"✏️ Напишите новый состав для {order_id}:\n(начните с #{order_id})",
            user_id,
            call.message.message_id
        )
        bot.answer_callback_query(call.id)
    
    elif data.startswith('close_') or data.startswith('admin_close_'):
        is_admin_close = data.startswith('admin_close_')
        order_id = data[12:] if is_admin_close else data[6:]
        
        if order_id not in active_orders:
            bot.answer_callback_query(call.id, "❌ Заказ не найден")
            return
        
        order = active_orders.pop(order_id)
        order['completed_time'] = format_time()
        order['completed_by'] = 'admin' if is_admin_close else 'seller'
        
        completed_orders[order_id] = order
        
        if order['buyer_id'] in active_chats:
            del active_chats[order['buyer_id']]
        
        save_data()
        
        buyer_text = (
            f"✅ *Заказ {order_id} завершен*\n"
            f"📍 {order['address']}\n"
            f"📝 {order['order_text']}\n"
            f"Спасибо за покупку!"
        )
        bot.send_message(order['buyer_id'], buyer_text, parse_mode="Markdown")
        
        if not is_admin_close and ADMIN_ID:
            link = get_buyer_link(order['buyer_id'])
            admin_text = (
                f"👑 *Заказ {order_id} завершен*\n"
                f"👤 Продавец: {order['seller_name']}\n"
                f"👤 Покупатель: {order['buyer_name']} 💬 [Связаться]({link})"
            )
            bot.send_message(ADMIN_ID, admin_text, parse_mode="Markdown")
        
        bot.edit_message_text(
            f"✅ Заказ {order_id} завершен",
            user_id,
            call.message.message_id
        )
        
        create_backup(f"Заказ {order_id} завершен")
        bot.answer_callback_query(call.id)
    
    elif data.startswith('history_'):
        order_id = data[8:]
        order = active_orders.get(order_id) or completed_orders.get(order_id)
        
        if not order:
            bot.answer_callback_query(call.id, "❌ Заказ не найден")
            return
        
        link = get_buyer_link(order['buyer_id'])
        text = (
            f"📜 *История заказа {order_id}*\n"
            f"👤 Продавец: {order['seller_name']}\n"
            f"👤 Покупатель: {order['buyer_name']} 💬 [Связаться]({link})\n"
            f"📍 {order['address']}\n"
            f"📝 {order['order_text']}\n"
            f"🕐 Создан: {order['time']}\n"
        )
        
        if 'completed_time' in order:
            text += f"✅ Завершен: {order['completed_time']}\n"
        
        text += "\n💬 *Сообщения:*\n"
        for msg in order.get('messages', []):
            from_who = "👤 Продавец" if msg['from'] == 'seller' else "👤 Покупатель"
            text += f"{from_who} ({msg['time']}): {msg['text']}\n"
        
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.row(
            telebot.types.InlineKeyboardButton(
                "💬 Связаться с покупателем",
                callback_data=f"contact_buyer_{order['buyer_id']}"
            )
        )
        
        bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=keyboard)
        bot.answer_callback_query(call.id)
    
    elif data.startswith('contact_buyer_'):
        buyer_id = int(data[14:])
        bot.send_message(
            user_id,
            f"✏️ Напишите сообщение покупателю:"
        )
        bot.register_next_step_handler_by_chat_id(user_id, send_to_buyer, buyer_id)
        bot.answer_callback_query(call.id)
    
    elif data.startswith('chat_'):
        buyer_id = int(data[5:])
        if buyer_id not in admin_chats:
            bot.answer_callback_query(call.id, "❌ Чат не найден")
            return
        
        chat = admin_chats[buyer_id]
        text = f"📩 *Чат #{chat['id']} с {chat['name']}*\n\n"
        for msg in chat['messages']:
            who = "👤 Покупатель" if msg['from'] == 'user' else "👨‍💼 Вы"
            text += f"{who} ({msg['time']}): {msg['text']}\n"
        
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.row(
            telebot.types.InlineKeyboardButton("✏️ Ответить", callback_data=f"reply_{buyer_id}"),
            telebot.types.InlineKeyboardButton("✅ Закрыть", callback_data=f"close_{buyer_id}")
        )
        
        bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=keyboard)
        bot.answer_callback_query(call.id)
    
    elif data.startswith('reply_'):
        buyer_id = int(data[6:])
        bot.send_message(
            user_id,
            f"✏️ Напишите ответ:"
        )
        bot.register_next_step_handler_by_chat_id(user_id, reply_to_buyer, buyer_id)
        bot.answer_callback_query(call.id)
    
    elif data.startswith('close_') and len(data) > 6 and data[6:].isdigit():
        buyer_id = int(data[6:])
        if buyer_id in admin_chats:
            admin_chats[buyer_id]['closed'] = True
            save_data()
            bot.edit_message_text("✅ Чат закрыт", user_id, call.message.message_id)
        bot.answer_callback_query(call.id)

def send_to_buyer(message, buyer_id):
    if message.text == '🔙 Вернуться к оформлению заказа':
        show_instruction(message.chat.id)
        return
    
    text = message.text
    try:
        bot.send_message(
            buyer_id,
            f"👑 *Сообщение от администратора:*\n\n{text}",
            parse_mode="Markdown"
        )
        add_back_button(message.chat.id, "✅ Отправлено!")
    except Exception as e:
        add_back_button(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")

def reply_to_buyer(message, buyer_id):
    if message.text == '🔙 Вернуться к оформлению заказа':
        show_instruction(message.chat.id)
        return
    
    text = message.text
    if buyer_id in admin_chats:
        admin_chats[buyer_id]['messages'].append({
            'time': format_time(),
            'from': 'admin',
            'text': text
        })
        save_data()
        
        bot.send_message(
            buyer_id,
            f"💬 *Ответ от администратора:*\n\n{text}",
            parse_mode="Markdown"
        )
        add_back_button(message.chat.id, "✅ Отправлено!")

# ====== WEBHOOK ======
@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    return 'Bad Request', 400

@app.route('/')
def index():
    return '🤖 Бот работает'

# ====== ЗАПУСК ======
if __name__ == '__main__':
    bot.remove_webhook()
    service_name = os.environ.get('RENDER_SERVICE_NAME', 'dp-sbor')
    webhook_url = f'https://{service_name}.onrender.com/webhook'
    bot.set_webhook(url=webhook_url)
    print(f"✅ Вебхук: {webhook_url}")
    print(f"🕐 Новосибирск: {format_time()}")
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
