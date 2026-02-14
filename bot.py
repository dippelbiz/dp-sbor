import os
import telebot
from flask import Flask, request
from datetime import datetime
import json
import time
import glob
import shutil

# ====== НАСТРОЙКИ ======
TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не установлен!")
    exit(1)

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Имя файла для хранения данных
DATA_FILE = 'bot_data.json'
BACKUP_DIR = 'backups'

# ADMIN ID
ADMIN_ID = os.environ.get('ADMIN_ID')
if ADMIN_ID:
    ADMIN_ID = int(ADMIN_ID)
    print(f"👑 Администратор: {ADMIN_ID}")
else:
    print("⚠️ ADMIN_ID не установлен!")
    ADMIN_ID = None

# Хранилища данных
user_data = {}
active_orders = {}
active_chats = {}
seller_waiting_for_order_update = {}

# Счетчики для продавцов (А1, Е2...)
seller_counters = {
    'Александр': 0,
    'Евгений': 0,
    'Юлия': 0,
    'Татьяна': 0,
    'Рабочий': 0
}

seller_prefixes = {
    "Александр": "А",
    "Евгений": "Е",
    "Юлия": "Ю",
    "Татьяна": "Т",
    "Рабочий": "Р"
}

# Список точек
pickup_points = {
    "ул. Галущака 15": "Александр",
    "ул. Беловежская 4/1": "Юлия", 
    "ул. Забалуева 90": "Евгений",
    "ул. Сержанта Коротаева 3": "Татьяна",
    "ул. Бетонная 14/1": "Рабочий"
}

# ====== ФУНКЦИИ ДЛЯ РАБОТЫ С ЗАКАЗАМИ ======
def generate_order_ref(seller_name):
    """Генерирует номер заказа вида А1, Е2 и т.д."""
    global seller_counters
    seller_counters[seller_name] = seller_counters.get(seller_name, 0) + 1
    return f"{seller_prefixes[seller_name]}{seller_counters[seller_name]}"

def parse_seller_ref(text):
    """Парсит ответ продавца в формате #А1 текст"""
    if text.startswith('#'):
        parts = text[1:].split(' ', 1)
        ref = parts[0].strip()
        message_text = parts[1] if len(parts) > 1 else ""
        
        # Проверка формата: буква + цифра
        if ref and ref[0] in seller_prefixes.values() and ref[1:].isdigit():
            return ref, message_text
    return None, None

# ====== ФУНКЦИИ ДЛЯ РАБОТЫ С ФАЙЛАМИ ======
def save_data():
    """Сохраняем данные в файл"""
    data = {
        'seller_counters': seller_counters,
        'active_orders': active_orders,
        'active_chats': active_chats,
        'seller_waiting': seller_waiting_for_order_update
    }
    
    temp_file = DATA_FILE + '.tmp'
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp_file, DATA_FILE)
        print(f"✅ Данные сохранены: {len(active_orders)} заказов")
    except Exception as e:
        print(f"❌ Ошибка сохранения: {e}")

def load_data():
    """Загружаем данные из файла"""
    global seller_counters, active_orders, active_chats, seller_waiting_for_order_update
    
    if not os.path.exists(DATA_FILE):
        print("📁 Новый файл данных")
        return
    
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        seller_counters = data.get('seller_counters', seller_counters)
        active_orders = data.get('active_orders', {})
        active_chats = data.get('active_chats', {})
        seller_waiting_for_order_update = data.get('seller_waiting', {})
        
        # Конвертируем ID в числа
        new_chats = {}
        for k, v in active_chats.items():
            try:
                new_chats[int(k)] = v
            except:
                new_chats[k] = v
        active_chats = new_chats
        
        print(f"✅ Загружено: {len(active_orders)} заказов")
    except Exception as e:
        print(f"❌ Ошибка загрузки: {e}")

# ====== ФУНКЦИИ ДЛЯ БЭКАПОВ ======
def create_backup(backup_type='auto'):
    """Создает бэкап"""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{BACKUP_DIR}/backup_{timestamp}.json"
    
    backup = {
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'type': backup_type,
        'data': {
            'seller_counters': seller_counters,
            'active_orders': active_orders,
            'active_chats': active_chats,
            'seller_waiting': seller_waiting_for_order_update
        }
    }
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(backup, f, ensure_ascii=False, indent=2)
        
        # Удаляем старые бэкапы (оставляем 20)
        backups = sorted(glob.glob(f"{BACKUP_DIR}/backup_*.json"))
        if len(backups) > 20:
            for old in backups[:-20]:
                os.remove(old)
        
        print(f"✅ Бэкап создан: {filename}")
        return filename
    except Exception as e:
        print(f"❌ Ошибка бэкапа: {e}")
        return None

def restore_from_backup(backup_file):
    """Восстанавливает из бэкапа"""
    global seller_counters, active_orders, active_chats, seller_waiting_for_order_update
    
    try:
        with open(backup_file, 'r', encoding='utf-8') as f:
            backup = json.load(f)
        
        data = backup['data']
        seller_counters = data.get('seller_counters', seller_counters)
        active_orders = data.get('active_orders', {})
        active_chats = data.get('active_chats', {})
        seller_waiting_for_order_update = data.get('seller_waiting', {})
        
        save_data()
        return True, backup.get('timestamp')
    except Exception as e:
        return False, str(e)

def get_backups_list():
    """Список бэкапов"""
    backups = sorted(glob.glob(f"{BACKUP_DIR}/backup_*.json"), reverse=True)
    result = []
    
    for i, file in enumerate(backups[:20], 1):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            result.append({
                'file': file,
                'display': f"{i}. {data.get('timestamp')} - {data.get('type')}"
            })
        except:
            continue
    return result

# Загружаем данные
load_data()

# ====== ФУНКЦИИ ДЛЯ ПРОВЕРКИ ПРАВ ======
def is_admin(user_id):
    return ADMIN_ID is not None and user_id == ADMIN_ID

def is_seller(user_id):
    return user_id in get_all_seller_ids()

def get_seller_id(seller_name):
    env_vars = {
        "Александр": "Seller_Aleksandr",
        "Юлия": "Seller_Yulia",
        "Евгений": "Seller_Evgeniy",
        "Татьяна": "Seller_Tatiana",
        "Рабочий": "Seller_Rabochiy"
    }
    
    seller_id = os.environ.get(env_vars.get(seller_name))
    return int(seller_id) if seller_id else None

def get_all_seller_ids():
    ids = []
    for seller in pickup_points.values():
        sid = get_seller_id(seller)
        if sid:
            ids.append(sid)
    return ids

def get_seller_active_orders(seller_id):
    return [ref for ref, o in active_orders.items() if o['seller_id'] == seller_id]

def get_seller_name_by_id(seller_id):
    for seller in pickup_points.values():
        if get_seller_id(seller) == seller_id:
            return seller
    return None

# ====== КЛАВИАТУРЫ ======
def get_main_keyboard():
    kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add('📋 Каталог с ценами')
    kb.add('🏢 О нас')
    kb.add('👤 Связаться с админом')
    return kb

def get_address_keyboard():
    kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for address in pickup_points.keys():
        kb.add(address)
    return kb

def get_back_to_order_keyboard():
    kb = telebot.types.InlineKeyboardMarkup()
    kb.add(telebot.types.InlineKeyboardButton(
        "🔙 Вернуться к оформлению",
        callback_data="back_to_order"
    ))
    return kb

def get_seller_order_keyboard(order_ref):
    kb = telebot.types.InlineKeyboardMarkup()
    kb.row(
        telebot.types.InlineKeyboardButton("✏️ Уточнить", callback_data=f"update_{order_ref}"),
        telebot.types.InlineKeyboardButton("✅ Завершить", callback_data=f"close_{order_ref}")
    )
    return kb

def get_seller_cancel_keyboard():
    kb = telebot.types.InlineKeyboardMarkup()
    kb.add(telebot.types.InlineKeyboardButton("❌ Отменить", callback_data="cancel_update"))
    return kb

def get_admin_keyboard():
    kb = telebot.types.InlineKeyboardMarkup()
    kb.row(
        telebot.types.InlineKeyboardButton("📦 Активные", callback_data="admin_active"),
        telebot.types.InlineKeyboardButton("💾 Бэкапы", callback_data="admin_backups")
    )
    return kb

def get_backups_menu_keyboard():
    kb = telebot.types.InlineKeyboardMarkup()
    kb.row(
        telebot.types.InlineKeyboardButton("💾 Создать", callback_data="backup_create"),
        telebot.types.InlineKeyboardButton("📤 Восстановить", callback_data="backup_restore")
    )
    kb.row(
        telebot.types.InlineKeyboardButton("📋 Список", callback_data="backup_list"),
        telebot.types.InlineKeyboardButton("↩️ Назад", callback_data="admin_back")
    )
    return kb

# ====== ОБРАБОТЧИКИ ======
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "🟢 *Пошаговая инструкция:*\n\n1. Напишите, что хотите заказать\n2. Выберите адрес\n3. Менеджер свяжется",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if not is_admin(message.from_user.id):
        return
    
    text = "👑 *Панель администратора*\n\n"
    text += f"📦 Активных заказов: {len(active_orders)}\n"
    
    bot.send_message(
        message.chat.id,
        text,
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard()
    )

@bot.message_handler(func=lambda m: m.text == '📋 Каталог с ценами')
def catalog(message):
    text = (
        "📋 *Каталог*\n\n"
        "1. Грецкий орех, 500г - 400 ₽\n"
        "2. Миндаль, 1000г - 950 ₽\n"
        "3. Кешью, 1000г - 1000 ₽\n"
        "4. Манго, 500г - 250 ₽\n"
        "5. Клубника, 500г - 350 ₽"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")
    bot.send_message(
        message.chat.id,
        "⬆️ Вернуться",
        reply_markup=get_back_to_order_keyboard()
    )

@bot.message_handler(func=lambda m: m.text == '🏢 О нас')
def about(message):
    text = "🏢 *DP SBOR*\nОтборные орехи и сухофрукты • Новосибирск"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")
    bot.send_message(
        message.chat.id,
        "⬆️ Вернуться",
        reply_markup=get_back_to_order_keyboard()
    )

@bot.message_handler(func=lambda m: m.text == '👤 Связаться с админом')
def contact_admin(message):
    if ADMIN_ID:
        kb = telebot.types.InlineKeyboardMarkup()
        kb.add(telebot.types.InlineKeyboardButton(
            "📱 Написать админу",
            url=f"tg://user?id={ADMIN_ID}"
        ))
        bot.send_message(
            message.chat.id,
            "Нажмите кнопку для связи:",
            reply_markup=kb
        )

@bot.callback_query_handler(func=lambda call: call.data == "back_to_order")
def back_to_order(call):
    bot.answer_callback_query(call.id)
    start(call.message)

@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_text(message):
    user_id = message.from_user.id
    text = message.text
    
    # Администратор
    if is_admin(user_id) and text.startswith('#'):
        ref, msg = parse_seller_ref(text)
        if ref and ref in active_orders:
            order = active_orders[ref]
            bot.send_message(order['buyer_id'], f"👑 *Админ:* {msg}", parse_mode="Markdown")
            bot.send_message(order['seller_id'], f"👑 *Админ в заказе {ref}:* {msg}", parse_mode="Markdown")
            bot.send_message(user_id, f"✅ Отправлено в {ref}")
        return
    
    # Продавец
    if is_seller(user_id):
        if user_id in seller_waiting_for_order_update:
            ref = seller_waiting_for_order_update[user_id]
            if ref in active_orders:
                old = active_orders[ref]['order_text']
                active_orders[ref]['order_text'] = text
                active_orders[ref]['updated_at'] = datetime.now().strftime("%d.%m.%Y %H:%M")
                
                bot.send_message(
                    active_orders[ref]['buyer_id'],
                    f"📝 *Уточненный заказ {ref}:*\n\n{text}",
                    parse_mode="Markdown"
                )
                
                bot.send_message(
                    user_id,
                    f"✅ Заказ {ref} обновлен",
                    reply_markup=get_seller_order_keyboard(ref)
                )
                
                del seller_waiting_for_order_update[user_id]
                save_data()
                create_backup('auto')
            return
        
        ref, msg = parse_seller_ref(text)
        if ref:
            if ref in active_orders:
                order = active_orders[ref]
                if order['seller_id'] == user_id:
                    bot.send_message(order['buyer_id'], f"💬 *Менеджер:* {msg}", parse_mode="Markdown")
                    bot.send_message(user_id, f"✅ Отправлено в {ref}")
                else:
                    bot.send_message(user_id, f"❌ Заказ {ref} не ваш")
            else:
                bot.send_message(user_id, f"❌ Заказ {ref} не найден")
        else:
            orders = get_seller_active_orders(user_id)
            if orders:
                text = "📋 *Ваши заказы:*\n" + "\n".join([f"• #{ref}" for ref in orders])
                text += "\n\n💬 Чтобы ответить: #А1 текст"
                bot.send_message(user_id, text, parse_mode="Markdown")
        return
    
    # Покупатель с активным заказом
    if user_id in active_chats:
        ref = active_chats[user_id]
        if ref in active_orders:
            order = active_orders[ref]
            bot.send_message(
                order['seller_id'],
                f"📩 *От {order['buyer_name']} ({ref}):*\n\n{text}",
                parse_mode="Markdown",
                reply_markup=get_seller_order_keyboard(ref)
            )
            bot.send_message(user_id, "✅ Отправлено менеджеру")
        return
    
    # Новый заказ
    user_data[user_id] = {
        'text': text,
        'name': message.from_user.first_name or "Покупатель"
    }
    
    bot.send_message(
        user_id,
        "✅ Выберите адрес:",
        reply_markup=get_address_keyboard()
    )

@bot.message_handler(func=lambda m: m.text in pickup_points.keys())
def address_selected(message):
    user_id = message.from_user.id
    address = message.text
    
    if user_id not in user_data:
        bot.send_message(user_id, "Сначала напишите заказ")
        return
    
    seller_name = pickup_points[address]
    seller_id = get_seller_id(seller_name)
    
    if not seller_id:
        bot.send_message(user_id, "Ошибка, попробуйте позже")
        return
    
    order_ref = generate_order_ref(seller_name)
    
    order_data = {
        'order_ref': order_ref,
        'buyer_id': user_id,
        'buyer_name': user_data[user_id]['name'],
        'seller_id': seller_id,
        'seller_name': seller_name,
        'address': address,
        'order_text': user_data[user_id]['text'],
        'timestamp': datetime.now().strftime("%d.%m.%Y %H:%M"),
        'updated_at': None
    }
    
    active_orders[order_ref] = order_data
    active_chats[user_id] = order_ref
    
    bot.send_message(
        user_id,
        f"🔄 *Заказ {order_ref} в обработке*\n\n📍 {address}\n📝 {user_data[user_id]['text']}",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )
    
    bot.send_message(
        seller_id,
        f"📦 *НОВЫЙ ЗАКАЗ {order_ref}*\n\n👤 {user_data[user_id]['name']}\n📍 {address}\n📝 {user_data[user_id]['text']}",
        parse_mode="Markdown",
        reply_markup=get_seller_order_keyboard(order_ref)
    )
    
    bot.send_message(
        seller_id,
        f"💬 Для ответа: #{order_ref} текст"
    )
    
    if ADMIN_ID:
        bot.send_message(
            ADMIN_ID,
            f"👑 *Новый заказ {order_ref}*\n\n👤 {user_data[user_id]['name']} [💬](tg://user?id={user_id})\n📍 {address}",
            parse_mode="Markdown"
        )
    
    del user_data[user_id]
    save_data()
    create_backup('auto')

# ====== КОЛЛБЭКИ ======
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    
    # Кнопки продавца
    if data.startswith('update_'):
        ref = data[7:]
        if ref in active_orders and active_orders[ref]['seller_id'] == user_id:
            seller_waiting_for_order_update[user_id] = ref
            bot.answer_callback_query(call.id)
            bot.send_message(user_id, f"✏️ Напишите новый состав для {ref}:")
            bot.send_message(user_id, "❌ Отменить", reply_markup=get_seller_cancel_keyboard())
        return
    
    if data == "cancel_update":
        if user_id in seller_waiting_for_order_update:
            del seller_waiting_for_order_update[user_id]
            bot.answer_callback_query(call.id, "✅ Отменено")
        return
    
    if data.startswith('close_'):
        ref = data[6:]
        if ref in active_orders and active_orders[ref]['seller_id'] == user_id:
            order = active_orders[ref]
            
            bot.send_message(
                order['buyer_id'],
                f"✅ *Заказ {ref} завершен*\n\n📝 {order['order_text']}\n📍 {order['address']}",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard()
            )
            
            if order['buyer_id'] in active_chats:
                del active_chats[order['buyer_id']]
            
            del active_orders[ref]
            save_data()
            create_backup('auto')
            
            bot.answer_callback_query(call.id, "✅ Завершен")
            bot.edit_message_text(
                f"✅ Заказ {ref} завершен",
                user_id,
                call.message.message_id
            )
        return
    
    # Админ кнопки
    if user_id != ADMIN_ID:
        return
    
    if data == "admin_active":
        text = "📦 *Активные заказы:*\n"
        for ref, order in active_orders.items():
            text += f"\n• {ref} - {order['buyer_name']} [💬](tg://user?id={order['buyer_id']})\n  📝 {order['order_text'][:50]}..."
        bot.send_message(user_id, text, parse_mode="Markdown")
    
    elif data == "admin_backups":
        bot.send_message(
            user_id,
            "💾 *Управление бэкапами*",
            parse_mode="Markdown",
            reply_markup=get_backups_menu_keyboard()
        )
    
    elif data == "backup_create":
        bot.answer_callback_query(call.id)
        bot.send_message(user_id, "⏳ Создание бэкапа...")
        file = create_backup('manual')
        if file:
            bot.send_message(user_id, f"✅ Бэкап создан: {os.path.basename(file)}")
    
    elif data == "backup_list":
        backups = get_backups_list()
        if not backups:
            bot.send_message(user_id, "📋 Нет бэкапов")
            return
        
        text = "📋 *Бэкапы:*\n"
        kb = telebot.types.InlineKeyboardMarkup()
        for b in backups[:10]:
            text += f"\n{b['display']}"
            kb.add(telebot.types.InlineKeyboardButton(
                b['display'][:30],
                callback_data=f"restore_{b['file']}"
            ))
        kb.add(telebot.types.InlineKeyboardButton("↩️ Назад", callback_data="admin_backups"))
        bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=kb)
    
    elif data.startswith('restore_'):
        file = data[8:]
        kb = telebot.types.InlineKeyboardMarkup()
        kb.row(
            telebot.types.InlineKeyboardButton("✅ Да", callback_data=f"confirm_{file}"),
            telebot.types.InlineKeyboardButton("❌ Нет", callback_data="admin_backups")
        )
        bot.send_message(user_id, "⚠️ Восстановить данные из бэкапа?", reply_markup=kb)
    
    elif data.startswith('confirm_'):
        file = data[8:]
        success, ts = restore_from_backup(file)
        if success:
            bot.send_message(user_id, f"✅ Восстановлено из бэкапа {ts}")
        else:
            bot.send_message(user_id, f"❌ Ошибка: {ts}")
    
    elif data == "admin_back":
        bot.answer_callback_query(call.id)
        admin_panel(call.message)

# ====== WEBHOOK ======
@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
        bot.process_new_updates([update])
        return ''
    return 'Bad Request', 400

@app.route('/')
def index():
    return '🤖 Бот работает'

# ====== ЗАПУСК ======
if __name__ == '__main__':
    # Создаем папку для бэкапов
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    
    bot.remove_webhook()
    service_name = os.environ.get('RENDER_SERVICE_NAME', 'dp-sbor')
    bot.set_webhook(url=f'https://{service_name}.onrender.com/webhook')
    print(f"✅ Вебхук: {service_name}.onrender.com/webhook")
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
