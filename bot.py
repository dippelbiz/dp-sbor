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
    print("⚠️ ADMIN_ID не установлен! Функции администратора недоступны")
    ADMIN_ID = None

# Хранилища данных
user_data = {}  # Для временных данных пользователей
active_orders = {}  # Активные заказы {'А1': order_data}
completed_orders = {}  # Завершенные заказы {'А1': order_data}
active_chats = {}  # Активные чаты {buyer_id: order_id}
seller_waiting_for_order_update = {}  # Ожидание уточнения заказа {seller_id: order_id}
admin_chats = {}  # Чаты с администратором {'Admin1': chat_data}
admin_counter = 0  # Счетчик для админ-чатов
seller_counters = {}  # Счетчики продавцов {'Александр': 5, ...}

# Список точек и продавцов
pickup_points = {
    "ул. Галущака 15": "Александр",
    "ул. Беловежская 4/1": "Юлия",
    "ул. Забалуева 90": "Евгений",
    "ул. Сержанта Коротаева 3": "Татьяна",
    "ул. Бетонная 14/1": "Рабочий"
}

# Префиксы для номеров заказов
seller_prefixes = {
    "Александр": "А",
    "Евгений": "Е",
    "Юлия": "Ю",
    "Татьяна": "Т",
    "Рабочий": "Р"
}

# ====== ФУНКЦИИ ДЛЯ РАБОТЫ С ФАЙЛАМИ ======

def save_data():
    """Сохраняем все данные в файл"""
    data = {
        'active_orders': active_orders,
        'completed_orders': completed_orders,
        'seller_counters': seller_counters,
        'admin_chats': admin_chats,
        'admin_counter': admin_counter,
        'active_chats': active_chats,
        'seller_waiting': seller_waiting_for_order_update,
        'last_save': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'version': '2.0'
    }
    
    temp_file = DATA_FILE + '.tmp'
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        if os.path.exists(DATA_FILE):
            os.replace(temp_file, DATA_FILE)
        else:
            os.rename(temp_file, DATA_FILE)
            
        print(f"✅ Данные сохранены: {len(active_orders)} заказов, {len(admin_chats)} админ-чатов")
        
    except Exception as e:
        print(f"❌ Ошибка сохранения данных: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)

def load_data():
    """Загружаем все данные из файла"""
    global active_orders, completed_orders, seller_counters
    global admin_chats, admin_counter, active_chats
    global seller_waiting_for_order_update
    
    if not os.path.exists(DATA_FILE):
        print("📁 Файл данных не найден, инициализация...")
        initialize_default_data()
        return
    
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        active_orders = data.get('active_orders', {})
        completed_orders = data.get('completed_orders', {})
        seller_counters = data.get('seller_counters', {})
        admin_chats = data.get('admin_chats', {})
        admin_counter = data.get('admin_counter', 0)
        active_chats = data.get('active_chats', {})
        seller_waiting_for_order_update = data.get('seller_waiting', {})
        
        # Конвертируем ключи в числа где нужно
        convert_data_types()
        
        print(f"✅ Данные загружены:")
        print(f"   - Активных заказов: {len(active_orders)}")
        print(f"   - Завершенных заказов: {len(completed_orders)}")
        print(f"   - Админ-чатов: {len(admin_chats)}")
        print(f"   - Активных чатов: {len(active_chats)}")
        
    except Exception as e:
        print(f"❌ Ошибка загрузки данных: {e}")
        initialize_default_data()

def initialize_default_data():
    """Инициализация данных по умолчанию"""
    global active_orders, completed_orders, seller_counters
    global admin_chats, admin_counter, active_chats
    global seller_waiting_for_order_update
    
    active_orders = {}
    completed_orders = {}
    seller_counters = {seller: 0 for seller in seller_prefixes.keys()}
    admin_chats = {}
    admin_counter = 0
    active_chats = {}
    seller_waiting_for_order_update = {}
    
    print("📁 Созданы пустые структуры данных")

def convert_data_types():
    """Конвертирует строковые ключи в числа где нужно"""
    global active_chats
    
    # Конвертируем ключи active_chats в int
    new_active_chats = {}
    for key, value in active_chats.items():
        try:
            new_active_chats[int(key)] = value
        except (ValueError, TypeError):
            new_active_chats[key] = value
    active_chats = new_active_chats

# ====== ФУНКЦИИ ДЛЯ БЭКАПОВ ======

def create_backup(backup_type='auto'):
    """Создает полный бэкап системы"""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{BACKUP_DIR}/backup_{timestamp}.json"
    
    backup = {
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'type': backup_type,
        'data': {
            'active_orders': active_orders,
            'completed_orders': completed_orders,
            'seller_counters': seller_counters,
            'admin_chats': admin_chats,
            'admin_counter': admin_counter,
            'active_chats': active_chats,
            'seller_waiting': seller_waiting_for_order_update
        }
    }
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(backup, f, ensure_ascii=False, indent=2)
        
        # Оставляем только последние 20 бэкапов
        clean_old_backups(20)
        
        print(f"✅ Бэкап создан: {filename}")
        return filename
        
    except Exception as e:
        print(f"❌ Ошибка создания бэкапа: {e}")
        return None

def clean_old_backups(keep=20):
    """Оставляет только последние keep бэкапов"""
    try:
        backups = sorted(glob.glob(f"{BACKUP_DIR}/backup_*.json"))
        if len(backups) > keep:
            for backup in backups[:-keep]:
                os.remove(backup)
                print(f"🗑 Удален старый бэкап: {backup}")
    except Exception as e:
        print(f"❌ Ошибка при очистке бэкапов: {e}")

def list_backups():
    """Возвращает список бэкапов с информацией"""
    backups = sorted(glob.glob(f"{BACKUP_DIR}/backup_*.json"), reverse=True)
    result = []
    
    for i, backup_file in enumerate(backups[:20], 1):
        try:
            with open(backup_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            backup_data = data.get('data', {})
            result.append({
                'number': i,
                'file': backup_file,
                'timestamp': data.get('timestamp', 'Unknown'),
                'type': data.get('type', 'unknown'),
                'active_count': len(backup_data.get('active_orders', {})),
                'completed_count': len(backup_data.get('completed_orders', {})),
                'chats_count': len(backup_data.get('admin_chats', {}))
            })
        except:
            continue
    
    return result

def restore_from_backup(backup_file):
    """Восстанавливает систему из бэкапа"""
    global active_orders, completed_orders, seller_counters
    global admin_chats, admin_counter, active_chats
    global seller_waiting_for_order_update
    
    try:
        with open(backup_file, 'r', encoding='utf-8') as f:
            backup = json.load(f)
        
        data = backup['data']
        
        active_orders = data.get('active_orders', {})
        completed_orders = data.get('completed_orders', {})
        seller_counters = data.get('seller_counters', {})
        admin_chats = data.get('admin_chats', {})
        admin_counter = data.get('admin_counter', 0)
        active_chats = data.get('active_chats', {})
        seller_waiting_for_order_update = data.get('seller_waiting', {})
        
        convert_data_types()
        save_data()
        
        return True, backup.get('timestamp', 'Unknown')
        
    except Exception as e:
        return False, str(e)

# ====== ФУНКЦИИ ДЛЯ ПРОВЕРКИ ПРАВ ======

def is_admin(user_id):
    """Проверка, является ли пользователь администратором"""
    return ADMIN_ID is not None and user_id == ADMIN_ID

def is_seller(user_id):
    """Проверка, является ли пользователь продавцом"""
    return user_id in get_all_seller_ids()

def get_seller_id(seller_name):
    """Получение ID продавца из переменных окружения"""
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
    except ValueError:
        return None

def get_all_seller_ids():
    """Получить список всех ID продавцов"""
    seller_ids = []
    for seller_name in pickup_points.values():
        seller_id = get_seller_id(seller_name)
        if seller_id:
            seller_ids.append(seller_id)
    return seller_ids

def get_seller_active_orders(seller_id):
    """Получить все активные заказы продавца"""
    seller_orders = []
    for order_id, order in active_orders.items():
        if order['seller_id'] == seller_id:
            seller_orders.append(order_id)
    return seller_orders

def get_seller_name_by_id(seller_id):
    """Получить имя продавца по ID"""
    for seller_name in pickup_points.values():
        if get_seller_id(seller_name) == seller_id:
            return seller_name
    return None

def get_seller_prefix(seller_name):
    """Получить префикс для номера заказа"""
    return seller_prefixes.get(seller_name, "?")

# ====== ФУНКЦИИ ДЛЯ РАБОТЫ С ЗАКАЗАМИ ======

def generate_order_id(seller_name):
    """Генерирует новый номер заказа для продавца"""
    global seller_counters
    
    if seller_name not in seller_counters:
        seller_counters[seller_name] = 0
    
    seller_counters[seller_name] += 1
    counter = seller_counters[seller_name]
    prefix = get_seller_prefix(seller_name)
    
    return f"{prefix}{counter}"

def parse_order_ref(text):
    """Парсит ссылку на заказ из сообщения"""
    if text.startswith('#'):
        parts = text[1:].split(' ', 1)
        ref = parts[0].strip()
        message = parts[1] if len(parts) > 1 else ""
        
        # Проверка формата: буква + цифра
        if ref and ref[0] in seller_prefixes.values() and ref[1:].isdigit():
            return ref, message
    
    return None, None

def find_order_by_ref(ref):
    """Ищет заказ по ссылке"""
    if ref in active_orders:
        return ref, active_orders[ref]
    if ref in completed_orders:
        return ref, completed_orders[ref]
    return None, None

def add_message_to_order(order_ref, sender_type, text):
    """Добавляет сообщение в историю заказа"""
    if order_ref in active_orders:
        if 'messages' not in active_orders[order_ref]:
            active_orders[order_ref]['messages'] = []
        
        active_orders[order_ref]['messages'].append({
            'time': datetime.now().strftime("%d.%m %H:%M"),
            'from': sender_type,
            'text': text
        })
        
        # Ограничиваем историю
        if len(active_orders[order_ref]['messages']) > 50:
            active_orders[order_ref]['messages'] = active_orders[order_ref]['messages'][-50:]

# ====== ФУНКЦИИ ДЛЯ РАБОТЫ С АДМИН-ЧАТАМИ ======

def create_admin_chat(user_id, user_name, first_message):
    """Создает новый админ-чат"""
    global admin_counter
    
    admin_counter += 1
    chat_id = f"Admin{admin_counter}"
    
    admin_chats[chat_id] = {
        'user_id': user_id,
        'user_name': user_name,
        'status': 'active',
        'history': [{
            'time': datetime.now().strftime("%d.%m %H:%M"),
            'role': 'user',
            'text': first_message
        }],
        'last_message_time': datetime.now().strftime("%d.%m %H:%M"),
        'last_message_text': first_message,
        'created': datetime.now().strftime("%d.%m %H:%M"),
        'completed': None
    }
    
    save_data()
    create_backup('auto')
    
    return chat_id

def add_message_to_admin_chat(chat_id, role, text):
    """Добавляет сообщение в админ-чат"""
    if chat_id in admin_chats:
        admin_chats[chat_id]['history'].append({
            'time': datetime.now().strftime("%d.%m %H:%M"),
            'role': role,
            'text': text
        })
        admin_chats[chat_id]['last_message_time'] = datetime.now().strftime("%d.%m %H:%M")
        admin_chats[chat_id]['last_message_text'] = text
        
        save_data()
        create_backup('auto')

def get_unresolved_chats():
    """Возвращает список активных админ-чатов"""
    unresolved = []
    for chat_id, chat in admin_chats.items():
        if chat['status'] == 'active':
            unresolved.append({
                'id': chat_id,
                'user_name': chat['user_name'],
                'last_time': chat['last_message_time'],
                'last_text': chat['last_message_text'][:30] + '...' if len(chat['last_message_text']) > 30 else chat['last_message_text']
            })
    return sorted(unresolved, key=lambda x: x['last_time'], reverse=True)

def format_chat_history(chat_id):
    """Форматирует историю чата для показа"""
    if chat_id not in admin_chats:
        return "Чат не найден"
    
    chat = admin_chats[chat_id]
    history = f"📜 История чата {chat_id} с {chat['user_name']}\n\n"
    
    for msg in chat['history']:
        if msg['role'] == 'user':
            history += f"👤 [{msg['time']}] {msg['text']}\n\n"
        elif msg['role'] == 'admin':
            history += f"👑 [{msg['time']}] {msg['text']}\n\n"
        else:
            history += f"🤖 [{msg['time']}] {msg['text']}\n\n"
    
    return history

# ====== КЛАВИАТУРЫ ======

def get_buyer_main_keyboard():
    """Основная клавиатура для покупателя"""
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row('📋 Каталог с ценами', 'ℹ️ О нас')
    keyboard.row('👤 Связаться с админом')
    return keyboard

def get_buyer_keyboard_with_new_order():
    """Клавиатура для покупателя с кнопкой нового заказа"""
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row('📋 Каталог с ценами', 'ℹ️ О нас')
    keyboard.row('👤 Связаться с админом', '🔄 Сделать новый заказ')
    return keyboard

def get_cancel_keyboard():
    """Клавиатура с кнопкой отмены"""
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row('❌ Отмена')
    return keyboard

def get_seller_order_keyboard(order_ref):
    """Клавиатура для работы с заказом (продавец)"""
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.row(
        telebot.types.InlineKeyboardButton("✏️ Уточнить заказ", callback_data=f"seller_update_{order_ref}"),
        telebot.types.InlineKeyboardButton("✅ Завершить заказ", callback_data=f"seller_close_{order_ref}")
    )
    return keyboard

def get_return_keyboard():
    """Кнопка возврата отдельным сообщением"""
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.row(telebot.types.InlineKeyboardButton("🔙 Вернуться к оформлению заказа", callback_data="return_to_order"))
    return keyboard

def get_admin_main_keyboard():
    """Основная клавиатура для админа"""
    keyboard = telebot.types.InlineKeyboardMarkup(row_width=2)
    keyboard.row(
        telebot.types.InlineKeyboardButton("📋 Нерешенные вопросы", callback_data="admin_unresolved"),
        telebot.types.InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")
    )
    keyboard.row(
        telebot.types.InlineKeyboardButton("📦 Активные заказы", callback_data="admin_active_orders"),
        telebot.types.InlineKeyboardButton("📜 Завершенные заказы", callback_data="admin_completed_orders")
    )
    keyboard.row(
        telebot.types.InlineKeyboardButton("💾 Бэкапы", callback_data="admin_backups"),
        telebot.types.InlineKeyboardButton("🔍 Поиск", callback_data="admin_search")
    )
    return keyboard

def get_admin_backup_keyboard():
    """Клавиатура для раздела бэкапов"""
    keyboard = telebot.types.InlineKeyboardMarkup(row_width=2)
    keyboard.row(
        telebot.types.InlineKeyboardButton("💾 Создать бэкап", callback_data="admin_backup_create"),
        telebot.types.InlineKeyboardButton("📤 Восстановить", callback_data="admin_backup_restore_menu")
    )
    keyboard.row(
        telebot.types.InlineKeyboardButton("📋 Список бэкапов", callback_data="admin_backup_list"),
        telebot.types.InlineKeyboardButton("↩️ Назад", callback_data="admin_back")
    )
    return keyboard

def get_admin_restore_menu_keyboard():
    """Клавиатура для меню восстановления"""
    keyboard = telebot.types.InlineKeyboardMarkup(row_width=2)
    keyboard.row(
        telebot.types.InlineKeyboardButton("📋 Из списка бэкапов", callback_data="admin_backup_restore_list"),
        telebot.types.InlineKeyboardButton("📎 Загрузить файл", callback_data="admin_backup_upload")
    )
    keyboard.row(telebot.types.InlineKeyboardButton("↩️ Назад", callback_data="admin_backups"))
    return keyboard

def get_chat_action_keyboard(chat_id):
    """Клавиатура для действий с админ-чатом"""
    keyboard = telebot.types.InlineKeyboardMarkup(row_width=3)
    keyboard.row(
        telebot.types.InlineKeyboardButton("✏️ Ответить", callback_data=f"chat_reply_{chat_id}"),
        telebot.types.InlineKeyboardButton("✅ Завершить вопрос", callback_data=f"chat_complete_{chat_id}"),
        telebot.types.InlineKeyboardButton("↩️ Назад", callback_data="admin_unresolved")
    )
    return keyboard

# ====== ОБРАБОТЧИКИ КОМАНД ======

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    
    if is_admin(user_id):
        bot.send_message(user_id, "👑 Вы администратор. Используйте /admin для входа в панель")
    elif is_seller(user_id):
        bot.send_message(user_id, "👨‍💼 Вы продавец. Новые заказы будут приходить сюда")
    else:
        # Покупатель
        bot.send_message(
            user_id,
            "🟢 Пошаговая инструкция:\n\n"
            "1. Напишите, что хотите заказать\n"
            "2. Выберите откуда удобнее забрать\n"
            "3. Менеджер свяжется с вами",
            reply_markup=get_buyer_main_keyboard()
        )

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(user_id, "❌ У вас нет прав администратора")
        return
    
    bot.send_message(
        user_id,
        "👑 *Панель администратора*\n\nВыберите действие:",
        parse_mode="Markdown",
        reply_markup=get_admin_main_keyboard()
    )

@bot.message_handler(commands=['cancel'])
def cancel_action(message):
    user_id = message.from_user.id
    
    # Проверяем, есть ли активное действие
    if user_id in seller_waiting_for_order_update:
        order_ref = seller_waiting_for_order_update[user_id]
        del seller_waiting_for_order_update[user_id]
        
        if order_ref in active_orders:
            order = active_orders[order_ref]
            bot.send_message(
                user_id,
                f"❌ Уточнение заказа {order_ref} отменено\n\n"
                f"Текущий заказ: {order['order_text']}\n"
                f"📍 Адрес: {order['address']}",
                reply_markup=get_seller_order_keyboard(order_ref)
            )
        else:
            bot.send_message(user_id, "❌ Заказ не найден")
    else:
        bot.send_message(user_id, "❌ Нет активных действий для отмены")

# ====== ОБРАБОТЧИКИ ТЕКСТА ======

@bot.message_handler(func=lambda message: message.text == '📋 Каталог с ценами')
def send_catalog(message):
    user_id = message.from_user.id
    
    catalog_text = (
        "📋 *Каталог с ценами*\n\n"
        "1. *Грецкий орех очищенный*, 500г - 400 ₽\n"
        "2. *Миндаль золотой*, 1000г - 950 ₽\n"
        "3. *Кешью WW320*, 1000г - 1000 ₽\n"
        "4. *Манго сушеное*, 500г - 250 ₽\n"
        "5. *Клубника сушеная*, 500г - 350 ₽"
    )
    
    bot.send_message(user_id, catalog_text, parse_mode="Markdown")
    bot.send_message(user_id, "⬆️", reply_markup=get_return_keyboard())

@bot.message_handler(func=lambda message: message.text == 'ℹ️ О нас')
def send_about(message):
    user_id = message.from_user.id
    
    about_text = (
        "🏢 *О нашей компании*\n\n"
        "*DP SBOR | Отборные орехи и сухофрукты • Новосибирск*\n"
        "Мы выбираем продукты по качеству, вкусу и внешнему виду, а не по минимальной цене\n\n"
        "Всё, начиная от выбора товара, заканчивая фасовкой и упаковкой проходит жесткий контроль\n\n"
        "Вы гарантированно получаете высшее качество по шикарным ценам\n\n"
        "📍 На данный момент есть 5 точек *в Новосибирске*, где можно забрать заказ\n\n"
        "*Наш канал: t.me/dp_sbor*"
    )
    
    bot.send_message(user_id, about_text, parse_mode="Markdown")
    bot.send_message(user_id, "⬆️", reply_markup=get_return_keyboard())

@bot.message_handler(func=lambda message: message.text == '👤 Связаться с админом')
def contact_admin(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "Покупатель"
    
    # Проверяем, есть ли уже активный чат
    for chat_id, chat in admin_chats.items():
        if chat['user_id'] == user_id and chat['status'] == 'active':
            # Показываем существующий чат
            history = format_chat_history(chat_id)
            bot.send_message(user_id, history)
            bot.send_message(
                user_id,
                "📬 *Продолжение диалога с администратором*\n\n"
                "Напишите ваше сообщение. Для выхода нажмите кнопку ниже.",
                parse_mode="Markdown",
                reply_markup=get_cancel_keyboard()
            )
            return
    
    # Новый чат
    bot.send_message(
        user_id,
        "📬 *Режим связи с администратором*\n\n"
        "Напишите ваше сообщение. Администратор ответит вам в этом чате.\n"
        "Для выхода нажмите кнопку ниже.",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )

@bot.message_handler(func=lambda message: message.text == '🔄 Сделать новый заказ')
def new_order(message):
    user_id = message.from_user.id
    
    bot.send_message(
        user_id,
        "🟢 *Пошаговая инструкция:*\n\n"
        "1. Напишите, что хотите заказать\n"
        "2. Выберите откуда удобнее забрать\n"
        "3. Менеджер свяжется с вами",
        parse_mode="Markdown",
        reply_markup=get_buyer_main_keyboard()
    )

@bot.message_handler(func=lambda message: message.text == '❌ Отмена')
def cancel_button(message):
    user_id = message.from_user.id
    
    # Возвращаем основную клавиатуру
    bot.send_message(
        user_id,
        "✅ Действие отменено",
        reply_markup=get_buyer_main_keyboard()
    )

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Пропускаем команды, которые уже обработаны
    if text in ['📋 Каталог с ценами', 'ℹ️ О нас', '👤 Связаться с админом', '🔄 Сделать новый заказ', '❌ Отмена']:
        return
    
    # --- АДМИНИСТРАТОР ---
    if is_admin(user_id):
        # Проверяем формат #AdminX
        if text.startswith('#Admin') or text.startswith('#admin'):
            parts = text.split(' ', 1)
            chat_ref = parts[0][1:]  # Admin1
            message_text = parts[1] if len(parts) > 1 else ""
            
            if not message_text:
                bot.send_message(
                    user_id,
                    f"❌ Неверный формат.\n✅ Правильно: #{chat_ref} *текст сообщения*"
                )
                return
            
            if chat_ref in admin_chats:
                chat = admin_chats[chat_ref]
                
                # Отправляем сообщение покупателю
                bot.send_message(
                    chat['user_id'],
                    f"💬 *Сообщение от администратора:*\n\n{message_text}",
                    parse_mode="Markdown"
                )
                
                # Сохраняем в историю
                add_message_to_admin_chat(chat_ref, 'admin', message_text)
                
                bot.send_message(
                    user_id,
                    f"✅ Сообщение отправлено покупателю (Чат {chat_ref})"
                )
            else:
                bot.send_message(user_id, f"❌ Чат {chat_ref} не найден")
        return
    
    # --- ПРОДАВЕЦ ---
    if is_seller(user_id):
        # Проверяем, ожидаем ли мы уточнение заказа
        if user_id in seller_waiting_for_order_update:
            order_ref = seller_waiting_for_order_update[user_id]
            
            if order_ref in active_orders:
                order = active_orders[order_ref]
                
                # Обновляем заказ
                old_text = order['order_text']
                order['order_text'] = text
                order['updated_at'] = datetime.now().strftime("%d.%m.%Y %H:%M")
                
                # Сохраняем в историю
                add_message_to_order(order_ref, 'seller_update', text)
                
                save_data()
                create_backup('auto')
                
                # Отправляем подтверждение продавцу
                bot.send_message(
                    user_id,
                    f"✅ *Заказ {order_ref} обновлен!*\n\n"
                    f"📝 *Актуальный заказ:* {text}\n"
                    f"📍 *Адрес:* {order['address']}",
                    parse_mode="Markdown",
                    reply_markup=get_seller_order_keyboard(order_ref)
                )
                
                # Отправляем уведомление покупателю
                bot.send_message(
                    order['buyer_id'],
                    f"📝 *Уточненный заказ:*\n\n{text}\n\n"
                    f"📍 *Адрес:* {order['address']}\n\n"
                    f"Отправьте сообщение, если хотите еще что-то уточнить.",
                    parse_mode="Markdown"
                )
                
                # Уведомляем админа
                if ADMIN_ID:
                    bot.send_message(
                        ADMIN_ID,
                        f"👑 *Заказ {order_ref} обновлен*\n\n"
                        f"👤 Продавец: {order['seller_name']}\n"
                        f"📝 Было: {old_text[:100]}\n"
                        f"📝 Стало: {text[:100]}",
                        parse_mode="Markdown"
                    )
                
                # Очищаем ожидание
                del seller_waiting_for_order_update[user_id]
                return
            else:
                del seller_waiting_for_order_update[user_id]
                bot.send_message(user_id, "❌ Заказ не найден")
                return
        
        # Проверяем формат #А1
        order_ref, message_text = parse_order_ref(text)
        
        if order_ref:
            if not message_text:
                seller_prefix = get_seller_prefix(get_seller_name_by_id(user_id))
                bot.send_message(
                    user_id,
                    f"❌ Неверный формат.\n✅ Правильно: #{seller_prefix}1 *текст сообщения*"
                )
                return
            
            found_ref, order = find_order_by_ref(order_ref)
            
            if found_ref:
                if order['seller_id'] == user_id:
                    # Отправляем сообщение покупателю
                    bot.send_message(
                        order['buyer_id'],
                        f"💬 *Сообщение от менеджера:*\n\n{message_text}",
                        parse_mode="Markdown"
                    )
                    
                    # Сохраняем в историю
                    add_message_to_order(order_ref, 'seller', message_text)
                    
                    bot.send_message(
                        user_id,
                        f"✅ Сообщение отправлено покупателю (Заказ {order_ref})"
                    )
                    
                    # Уведомляем админа
                    if ADMIN_ID:
                        bot.send_message(
                            ADMIN_ID,
                            f"👑 *Сообщение от менеджера*\n\n"
                            f"📦 Заказ {order_ref}\n"
                            f"👤 Продавец: {order['seller_name']}\n"
                            f"👤 Покупатель: {order['buyer_name']}\n"
                            f"💬 {message_text}",
                            parse_mode="Markdown"
                        )
                else:
                    bot.send_message(user_id, f"❌ У вас нет заказа {order_ref}")
            else:
                bot.send_message(user_id, f"❌ Заказ {order_ref} не найден")
        else:
            # Если продавец пишет без #
            seller_active = get_seller_active_orders(user_id)
            if seller_active:
                orders_list = '\n'.join([f"• Заказ {oid}" for oid in seller_active])
                bot.send_message(
                    user_id,
                    f"📋 *У вас {len(seller_active)} активных заказов:*\n\n"
                    f"{orders_list}\n\n"
                    f"💬 *Чтобы ответить, начните сообщение с номера заказа:*\n"
                    f"Пример: `#А1 Здравствуйте!`"
                )
            else:
                bot.send_message(user_id, "❌ У вас нет активных заказов.")
        return
    
    # --- ПОКУПАТЕЛЬ ---
    
    # Проверяем, в режиме ли чата с админом
    for chat_id, chat in admin_chats.items():
        if chat['user_id'] == user_id and chat['status'] == 'active':
            # Отправляем сообщение админу
            add_message_to_admin_chat(chat_id, 'user', text)
            
            # Уведомление админу
            if ADMIN_ID:
                bot.send_message(
                    ADMIN_ID,
                    f"📩 *Новое сообщение в чате {chat_id}*\n\n"
                    f"👤 {chat['user_name']}\n"
                    f"💬 {text}\n\n"
                    f"💬 [Связаться](tg://user?id={user_id})",
                    parse_mode="Markdown"
                )
            
            bot.send_message(
                user_id,
                "✅ Сообщение отправлено администратору\n\n"
                "Напишите новое сообщение или нажмите кнопку ниже.",
                reply_markup=get_cancel_keyboard()
            )
            return
    
    # Проверяем, есть ли активный заказ
    if user_id in active_chats:
        order_ref = active_chats[user_id]
        order = active_orders.get(order_ref)
        
        if order:
            # Отправляем сообщение продавцу
            seller_id = order['seller_id']
            
            # Сохраняем в историю
            add_message_to_order(order_ref, 'buyer', text)
            
            bot.send_message(
                seller_id,
                f"📩 *Сообщение от покупателя (Заказ {order_ref}):*\n\n"
                f"👤 {order['buyer_name']}\n"
                f"📍 Точка: {order['address']}\n"
                f"📝 *Текущий заказ:* {order['order_text']}\n\n"
                f"💬 {text}",
                parse_mode="Markdown",
                reply_markup=get_seller_order_keyboard(order_ref)
            )
            
            bot.send_message(
                user_id,
                "✅ Сообщение отправлено менеджеру"
            )
            
            # Уведомляем админа
            if ADMIN_ID:
                bot.send_message(
                    ADMIN_ID,
                    f"👑 *Сообщение от покупателя*\n\n"
                    f"📦 Заказ {order_ref}\n"
                    f"👤 Продавец: {order['seller_name']}\n"
                    f"👤 Покупатель: {order['buyer_name']}\n"
                    f"💬 {text}",
                    parse_mode="Markdown"
                )
            return
        else:
            # Если заказ не найден, удаляем из активных чатов
            if user_id in active_chats:
                del active_chats[user_id]
                save_data()
    
    # --- НОВЫЙ ЗАКАЗ ---
    if user_id in active_chats:
        bot.send_message(
            user_id,
            "⚠️ У вас уже есть активный заказ. Дождитесь завершения текущего заказа.",
            reply_markup=get_buyer_main_keyboard()
        )
        return
    
    # Сохраняем данные для нового заказа
    user_data[user_id] = {
        'text': text,
        'name': message.from_user.first_name or "Покупатель",
        'user_id': user_id
    }
    
    # Кнопки с адресами
    keyboard = telebot.types.InlineKeyboardMarkup()
    for address in pickup_points.keys():
        keyboard.add(telebot.types.InlineKeyboardButton(text=address, callback_data=f"address_{address}"))
    
    bot.send_message(
        user_id,
        "✅ Сообщение получено! Выберите удобный адрес:",
        reply_markup=keyboard
    )

# ====== ОБРАБОТЧИКИ КОЛЛБЭКОВ ======

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    
    # ===== ВОЗВРАТ К ОФОРМЛЕНИЮ =====
    if call.data == "return_to_order":
        bot.answer_callback_query(call.id)
        bot.delete_message(chat_id, call.message.message_id)
        bot.send_message(
            user_id,
            "🟢 *Пошаговая инструкция:*\n\n"
            "1. Напишите, что хотите заказать\n"
            "2. Выберите откуда удобнее забрать\n"
            "3. Менеджер свяжется с вами",
            parse_mode="Markdown",
            reply_markup=get_buyer_main_keyboard()
        )
        return
    
    # ===== ВЫБОР АДРЕСА =====
    if call.data.startswith('address_'):
        address = call.data[8:]  # убираем 'address_'
        user_info = user_data.get(user_id)
        
        if not user_info:
            bot.answer_callback_query(call.id, "❌ Ошибка: начните заказ заново")
            bot.send_message(chat_id, "Пожалуйста, напишите что хотите заказать:")
            return
        
        seller_name = pickup_points.get(address)
        seller_id = get_seller_id(seller_name)
        
        if seller_id:
            # Генерируем номер заказа
            order_ref = generate_order_id(seller_name)
            
            # Сохраняем заказ
            order_data = {
                'order_ref': order_ref,
                'buyer_id': user_id,
                'buyer_name': user_info['name'],
                'seller_id': seller_id,
                'seller_name': seller_name,
                'address': address,
                'order_text': user_info['text'],
                'timestamp': datetime.now().strftime("%d.%m.%Y %H:%M"),
                'updated_at': None,
                'status': 'active',
                'messages': []
            }
            
            active_orders[order_ref] = order_data
            active_chats[user_id] = order_ref
            
            save_data()
            create_backup('auto')
            
            # Удаляем сообщение с кнопками
            try:
                bot.delete_message(chat_id, call.message.message_id)
            except:
                pass
            
            # Сообщение продавцу
            seller_message = (
                f"📦 *НОВЫЙ ЗАКАЗ {order_ref}*\n\n"
                f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                f"👤 *Покупатель:* {user_info['name']}\n"
                f"📍 *Точка:* {address}\n"
                f"📝 *Заказ:* {user_info['text']}"
            )
            
            bot.send_message(
                seller_id,
                seller_message,
                parse_mode="Markdown",
                reply_markup=get_seller_order_keyboard(order_ref)
            )
            
            bot.send_message(
                seller_id,
                f"💬 *Чтобы ответить:* `#{order_ref} ваш_текст`",
                parse_mode="Markdown"
            )
            
            # Сообщение покупателю
            buyer_message = (
                f"🔄 *Ваш заказ в обработке*\n\n"
                f"📍 Адрес: {address}\n"
                f"📝 Ваш заказ: {user_info['text']}\n\n"
                f"*Менеджер скоро свяжется с Вами в этом чате.*"
            )
            
            bot.send_message(
                user_id,
                buyer_message,
                parse_mode="Markdown",
                reply_markup=get_buyer_main_keyboard()
            )
            
            # Уведомление админу
            if ADMIN_ID:
                bot.send_message(
                    ADMIN_ID,
                    f"👑 *НОВЫЙ ЗАКАЗ {order_ref}*\n\n"
                    f"👤 Продавец: {seller_name}\n"
                    f"👤 Покупатель: {user_info['name']}\n"
                    f"📍 {address}\n"
                    f"📝 {user_info['text']}",
                    parse_mode="Markdown"
                )
            
            bot.answer_callback_query(call.id, f"✅ Заказ {order_ref} отправлен")
        else:
            bot.answer_callback_query(call.id, "❌ Ошибка: точка временно недоступна")
        
        return
    
    # ===== ПРОДАВЕЦ: УТОЧНИТЬ ЗАКАЗ =====
    if call.data.startswith('seller_update_'):
        order_ref = call.data[14:]  # убираем 'seller_update_'
        
        if order_ref not in active_orders:
            bot.answer_callback_query(call.id, "❌ Заказ не найден")
            return
        
        order = active_orders[order_ref]
        
        if order['seller_id'] != user_id:
            bot.answer_callback_query(call.id, "❌ Это не ваш заказ")
            return
        
        seller_waiting_for_order_update[user_id] = order_ref
        bot.answer_callback_query(call.id)
        
        # Отдельное сообщение с информацией
        bot.send_message(
            user_id,
            f"✏️ *Уточнение заказа {order_ref}*\n\n"
            f"📍 Адрес: {order['address']}\n"
            f"📝 *Текущий заказ:* {order['order_text']}\n\n"
            f"Напишите новый состав заказа.",
            parse_mode="Markdown"
        )
        
        # Отдельное сообщение с кнопкой отмены
        cancel_keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        cancel_keyboard.row('❌ Отменить уточнение')
        
        bot.send_message(
            user_id,
            "⬆️",
            reply_markup=cancel_keyboard
        )
        
        return
    
    # ===== ПРОДАВЕЦ: ЗАВЕРШИТЬ ЗАКАЗ =====
    if call.data.startswith('seller_close_'):
        order_ref = call.data[13:]  # убираем 'seller_close_'
        
        if order_ref not in active_orders:
            bot.answer_callback_query(call.id, "❌ Заказ не найден")
            return
        
        order = active_orders[order_ref]
        
        if order['seller_id'] != user_id:
            bot.answer_callback_query(call.id, "❌ Это не ваш заказ")
            return
        
        bot.answer_callback_query(call.id)
        
        # Подтверждение
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.row(
            telebot.types.InlineKeyboardButton("✅ Да, завершить", callback_data=f"seller_confirm_close_{order_ref}"),
            telebot.types.InlineKeyboardButton("❌ Отмена", callback_data=f"seller_cancel_close_{order_ref}")
        )
        
        bot.send_message(
            user_id,
            f"⚠️ *Завершить заказ {order_ref}?*\n\n"
            f"Покупатель получит финальное сообщение с составом заказа.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        
        return
    
    # ===== ПРОДАВЕЦ: ПОДТВЕРЖДЕНИЕ ЗАВЕРШЕНИЯ =====
    if call.data.startswith('seller_confirm_close_'):
        order_ref = call.data[20:]  # убираем 'seller_confirm_close_'
        
        if order_ref not in active_orders:
            bot.answer_callback_query(call.id, "❌ Заказ не найден")
            return
        
        order = active_orders[order_ref]
        
        if order['seller_id'] != user_id:
            bot.answer_callback_query(call.id, "❌ Это не ваш заказ")
            return
        
        # Завершаем заказ
        final_text = order['order_text']
        order_date = order['updated_at'] if order['updated_at'] else order['timestamp']
        
        # Финальное сообщение покупателю
        final_message = (
            f"✅ *Заказ от {order_date}*\n\n"
            f"📝 *Содержание:* {final_text}\n"
            f"📍 *Адрес:* {order['address']}\n\n"
            f"💬 *Чат с менеджером закрыт*"
        )
        
        bot.send_message(
            order['buyer_id'],
            final_message,
            parse_mode="Markdown",
            reply_markup=get_buyer_keyboard_with_new_order()
        )
        
        # Уведомление админу
        if ADMIN_ID:
            bot.send_message(
                ADMIN_ID,
                f"👑 *ЗАКАЗ ЗАВЕРШЕН {order_ref}*\n\n"
                f"👤 Продавец: {order['seller_name']}\n"
                f"👤 Покупатель: {order['buyer_name']}\n"
                f"📝 {final_text}",
                parse_mode="Markdown"
            )
        
        # Переносим в завершенные
        order['completed_at'] = datetime.now().strftime("%d.%m.%Y %H:%M")
        order['status'] = 'completed'
        completed_orders[order_ref] = order
        
        # Удаляем из активных
        if order['buyer_id'] in active_chats:
            del active_chats[order['buyer_id']]
        
        del active_orders[order_ref]
        
        if user_id in seller_waiting_for_order_update:
            del seller_waiting_for_order_update[user_id]
        
        save_data()
        create_backup('auto')
        
        # Обновляем сообщение у продавца
        try:
            bot.edit_message_text(
                f"✅ *ЗАКАЗ ЗАВЕРШЕН {order_ref}*\n\n"
                f"👤 Покупатель: {order['buyer_name']}\n"
                f"📍 Точка: {order['address']}\n"
                f"📝 Заказ: {final_text}\n\n"
                f"📅 Создан: {order['timestamp']}\n"
                f"📅 Завершен: {order['completed_at']}",
                user_id,
                call.message.message_id,
                parse_mode="Markdown"
            )
        except:
            pass
        
        # Показываем оставшиеся заказы
        seller_active = get_seller_active_orders(user_id)
        if seller_active:
            orders_list = '\n'.join([f"• Заказ {oid}" for oid in seller_active])
            bot.send_message(
                user_id,
                f"📋 *Осталось активных заказов: {len(seller_active)}*\n\n"
                f"{orders_list}\n\n"
                f"💬 `#номер_заказа ваш_текст`"
            )
        else:
            bot.send_message(
                user_id,
                "✅ Все заказы завершены! Хорошего дня! 🍃"
            )
        
        bot.answer_callback_query(call.id, "✅ Заказ завершен")
        
        return
    
    # ===== ПРОДАВЕЦ: ОТМЕНА ЗАВЕРШЕНИЯ =====
    if call.data.startswith('seller_cancel_close_'):
        order_ref = call.data[19:]  # убираем 'seller_cancel_close_'
        
        bot.answer_callback_query(call.id, "❌ Завершение отменено")
        
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass
        
        return
    
    # ===== АДМИН: ПАНЕЛЬ =====
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "❌ Нет прав")
        return
    
    # ===== АДМИН: НЕРЕШЕННЫЕ ВОПРОСЫ =====
    if call.data == "admin_unresolved":
        unresolved = get_unresolved_chats()
        
        if not unresolved:
            bot.send_message(user_id, "📭 Нет нерешенных вопросов")
            bot.answer_callback_query(call.id)
            return
        
        text = "📋 *Нерешенные вопросы:*\n\n"
        keyboard = telebot.types.InlineKeyboardMarkup()
        
        for chat in unresolved:
            text += f"• {chat['id']} - {chat['user_name']} - {chat['last_time']}\n"
            keyboard.add(telebot.types.InlineKeyboardButton(
                chat['id'], callback_data=f"admin_chat_{chat['id']}"
            ))
        
        bot.send_message(user_id, text, parse_mode="Markdown")
        bot.send_message(user_id, "Нажмите на номер чата для просмотра:", reply_markup=keyboard)
        bot.answer_callback_query(call.id)
        
        return
    
    # ===== АДМИН: ПРОСМОТР ЧАТА =====
    if call.data.startswith('admin_chat_'):
        chat_id = call.data[11:]  # убираем 'admin_chat_'
        
        if chat_id not in admin_chats:
            bot.answer_callback_query(call.id, "❌ Чат не найден")
            return
        
        history = format_chat_history(chat_id)
        bot.send_message(user_id, history, parse_mode="Markdown")
        bot.send_message(
            user_id,
            "Выберите действие:",
            reply_markup=get_chat_action_keyboard(chat_id)
        )
        
        bot.answer_callback_query(call.id)
        
        return
    
    # ===== АДМИН: ОТВЕТИТЬ В ЧАТЕ =====
    if call.data.startswith('chat_reply_'):
        chat_id = call.data[11:]  # убираем 'chat_reply_'
        
        bot.send_message(
            user_id,
            f"✏️ *Ответ в чат {chat_id}*\n\n"
            f"Используйте формат: #{chat_id} *текст сообщения*\n\n"
            f"Пример: #{chat_id} Здравствуйте! Чем могу помочь?",
            parse_mode="Markdown"
        )
        
        bot.answer_callback_query(call.id)
        
        return
    
    # ===== АДМИН: ЗАВЕРШИТЬ ЧАТ =====
    if call.data.startswith('chat_complete_'):
        chat_id = call.data[14:]  # убираем 'chat_complete_'
        
        if chat_id not in admin_chats:
            bot.answer_callback_query(call.id, "❌ Чат не найден")
            return
        
        chat = admin_chats[chat_id]
        chat['status'] = 'completed'
        chat['completed'] = datetime.now().strftime("%d.%m.%Y %H:%M")
        
        save_data()
        create_backup('auto')
        
        # Уведомляем покупателя
        bot.send_message(
            chat['user_id'],
            "✅ *Администратор завершил вопрос. Если будут новые, обязательно пишите.*",
            parse_mode="Markdown",
            reply_markup=get_buyer_main_keyboard()
        )
        
        bot.send_message(
            user_id,
            f"✅ Вопрос {chat_id} завершен"
        )
        
        bot.answer_callback_query(call.id)
        
        return
    
    # ===== АДМИН: СТАТИСТИКА =====
    if call.data == "admin_stats":
        active_count = len(active_orders)
        completed_count = len(completed_orders)
        chats_count = len([c for c in admin_chats.values() if c['status'] == 'active'])
        
        # Статистика по продавцам
        seller_stats = {}
        for order in active_orders.values():
            seller = order['seller_name']
            seller_stats[seller] = seller_stats.get(seller, 0) + 1
        
        stats_text = (
            f"📊 *ОБЩАЯ СТАТИСТИКА*\n\n"
            f"📦 *Заказы:*\n"
            f"• Активных: {active_count}\n"
            f"• Завершенных: {completed_count}\n\n"
            f"👥 *Продавцы:*\n"
        )
        
        for seller, count in seller_stats.items():
            stats_text += f"• {seller}: {count} активных\n"
        
        stats_text += f"\n💬 *Админ-чаты:*\n• Нерешенных: {chats_count}"
        
        bot.send_message(user_id, stats_text, parse_mode="Markdown")
        bot.answer_callback_query(call.id)
        
        return
    
    # ===== АДМИН: АКТИВНЫЕ ЗАКАЗЫ =====
    if call.data == "admin_active_orders":
        if not active_orders:
            bot.send_message(user_id, "📭 Нет активных заказов")
            bot.answer_callback_query(call.id)
            return
        
        # Группируем по продавцам
        by_seller = {}
        for ref, order in active_orders.items():
            seller = order['seller_name']
            if seller not in by_seller:
                by_seller[seller] = []
            by_seller[seller].append((ref, order))
        
        text = "📦 *АКТИВНЫЕ ЗАКАЗЫ*\n\n"
        keyboard = telebot.types.InlineKeyboardMarkup()
        
        for seller, orders in by_seller.items():
            text += f"👤 *{seller}* ({len(orders)}):\n"
            for ref, order in orders:
                text += f"• {ref} - {order['buyer_name']} - {order['order_text'][:30]}... "
                text += f"[💬](tg://user?id={order['buyer_id']})\n"
                keyboard.add(telebot.types.InlineKeyboardButton(
                    ref, callback_data=f"admin_view_order_{ref}"
                ))
            text += "\n"
        
        bot.send_message(user_id, text, parse_mode="Markdown", disable_web_page_preview=True)
        bot.send_message(user_id, "Нажмите на номер заказа для просмотра:", reply_markup=keyboard)
        bot.answer_callback_query(call.id)
        
        return
    
    # ===== АДМИН: ПРОСМОТР ЗАКАЗА =====
    if call.data.startswith('admin_view_order_'):
        order_ref = call.data[16:]  # убираем 'admin_view_order_'
        
        found_ref, order = find_order_by_ref(order_ref)
        
        if not order:
            bot.send_message(user_id, f"❌ Заказ {order_ref} не найден")
            bot.answer_callback_query(call.id)
            return
        
        status = "✅ Завершен" if order['status'] == 'completed' else "📦 Активен"
        
        text = (
            f"{'📦' if order['status'] == 'active' else '📜'} *ЗАКАЗ {order_ref}*\n\n"
            f"📅 Создан: {order['timestamp']}\n"
            f"👤 Продавец: {order['seller_name']}\n"
            f"👤 Покупатель: {order['buyer_name']} [💬](tg://user?id={order['buyer_id']})\n"
            f"📍 Адрес: {order['address']}\n"
            f"📝 Заказ: {order['order_text']}\n"
            f"📌 Статус: {status}\n"
        )
        
        if order.get('updated_at'):
            text += f"🔄 Обновлен: {order['updated_at']}\n"
        
        if order.get('completed_at'):
            text += f"🏁 Завершен: {order['completed_at']}\n"
        
        bot.send_message(user_id, text, parse_mode="Markdown", disable_web_page_preview=True)
        
        # Показываем историю сообщений
        if 'messages' in order and order['messages']:
            history = "📜 *История переписки:*\n\n"
            for msg in order['messages'][-10:]:  # последние 10
                if msg['from'] == 'buyer':
                    history += f"👤 [{msg['time']}] {msg['text']}\n\n"
                elif msg['from'] == 'seller':
                    history += f"👨‍💼 [{msg['time']}] {msg['text']}\n\n"
                elif msg['from'] == 'seller_update':
                    history += f"✏️ [{msg['time']}] {msg['text']}\n\n"
            
            bot.send_message(user_id, history, parse_mode="Markdown")
        
        bot.answer_callback_query(call.id)
        
        return
    
    # ===== АДМИН: ЗАВЕРШЕННЫЕ ЗАКАЗЫ =====
    if call.data == "admin_completed_orders":
        if not completed_orders:
            bot.send_message(user_id, "📭 Нет завершенных заказов")
            bot.answer_callback_query(call.id)
            return
        
        # Последние 20
        sorted_orders = sorted(
            completed_orders.items(),
            key=lambda x: x[1].get('completed_at', x[1]['timestamp']),
            reverse=True
        )[:20]
        
        text = "📜 *ПОСЛЕДНИЕ ЗАВЕРШЕННЫЕ ЗАКАЗЫ*\n\n"
        keyboard = telebot.types.InlineKeyboardMarkup()
        
        for ref, order in sorted_orders:
            date = order.get('completed_at', order['timestamp']).split()[0]
            text += f"✅ {ref} - {date} - {order['seller_name']} - {order['buyer_name']} "
            text += f"[💬](tg://user?id={order['buyer_id']})\n"
            keyboard.add(telebot.types.InlineKeyboardButton(
                ref, callback_data=f"admin_view_order_{ref}"
            ))
        
        bot.send_message(user_id, text, parse_mode="Markdown", disable_web_page_preview=True)
        bot.send_message(user_id, "Нажмите на номер заказа для просмотра:", reply_markup=keyboard)
        bot.answer_callback_query(call.id)
        
        return
    
    # ===== АДМИН: БЭКАПЫ =====
    if call.data == "admin_backups":
        last_backup = "никогда"
        backups = list_backups()
        if backups:
            last_backup = backups[0]['timestamp']
        
        text = (
            f"💾 *УПРАВЛЕНИЕ БЭКАПАМИ*\n\n"
            f"Автоматические бэкапы создаются при:\n"
            f"• Новом заказе\n"
            f"• Завершении заказа\n"
            f"• Каждом действии в чате админа и покупателя\n"
            f"• Каждые 6 часов\n\n"
            f"Последний авто-бэкап: {last_backup}"
        )
        
        bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=get_admin_backup_keyboard())
        bot.answer_callback_query(call.id)
        
        return
    
    # ===== АДМИН: СОЗДАТЬ БЭКАП =====
    if call.data == "admin_backup_create":
        bot.send_message(user_id, "⏳ Создание бэкапа...")
        
        filename = create_backup('manual')
        
        if filename:
            bot.send_message(
                user_id,
                f"✅ *Бэкап успешно создан!*\n\n"
                f"📁 Файл: {os.path.basename(filename)}\n"
                f"📦 Данные:\n"
                f"   • Активных заказов: {len(active_orders)}\n"
                f"   • Завершенных заказов: {len(completed_orders)}\n"
                f"   • Админ-чатов: {len(admin_chats)}\n"
                f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
                parse_mode="Markdown"
            )
        else:
            bot.send_message(user_id, "❌ Ошибка при создании бэкапа")
        
        bot.answer_callback_query(call.id)
        
        return
    
    # ===== АДМИН: МЕНЮ ВОССТАНОВЛЕНИЯ =====
    if call.data == "admin_backup_restore_menu":
        bot.send_message(
            user_id,
            "📤 *ВОССТАНОВЛЕНИЕ*\n\nВыберите способ:",
            parse_mode="Markdown",
            reply_markup=get_admin_restore_menu_keyboard()
        )
        bot.answer_callback_query(call.id)
        
        return
    
    # ===== АДМИН: СПИСОК БЭКАПОВ =====
    if call.data == "admin_backup_list":
        backups = list_backups()
        
        if not backups:
            bot.send_message(user_id, "📭 Нет доступных бэкапов")
            bot.answer_callback_query(call.id)
            return
        
        text = "📋 *ДОСТУПНЫЕ БЭКАПЫ*\n\n"
        keyboard = telebot.types.InlineKeyboardMarkup()
        
        for b in backups:
            text += f"{b['number']}. {b['timestamp']} - {b['type']} - {b['active_count']} акт, {b['completed_count']} зав, {b['chats_count']} чатов\n"
            keyboard.add(telebot.types.InlineKeyboardButton(
                f"{b['number']}. {b['timestamp']}",
                callback_data=f"admin_backup_info_{b['file']}"
            ))
        
        keyboard.row(telebot.types.InlineKeyboardButton("↩️ Назад", callback_data="admin_backups"))
        
        bot.send_message(user_id, text, parse_mode="Markdown")
        bot.send_message(user_id, "Нажмите на бэкап для просмотра:", reply_markup=keyboard)
        bot.answer_callback_query(call.id)
        
        return
    
    # ===== АДМИН: ИНФО О БЭКАПЕ =====
    if call.data.startswith('admin_backup_info_'):
        backup_file = call.data[18:]  # убираем 'admin_backup_info_'
        
        try:
            with open(backup_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            backup_data = data.get('data', {})
            
            text = (
                f"📁 *БЭКАП {os.path.basename(backup_file)}*\n\n"
                f"📅 Дата: {data.get('timestamp', 'Unknown')}\n"
                f"📌 Тип: {data.get('type', 'unknown')}\n"
                f"📦 Содержит:\n"
                f"   • Активные заказы: {len(backup_data.get('active_orders', {}))}\n"
                f"   • Завершенные заказы: {len(backup_data.get('completed_orders', {}))}\n"
                f"   • Админ-чаты: {len(backup_data.get('admin_chats', {}))}\n"
                f"📁 Размер: {os.path.getsize(backup_file) // 1024} KB"
            )
            
            keyboard = telebot.types.InlineKeyboardMarkup()
            keyboard.row(
                telebot.types.InlineKeyboardButton("📤 Восстановить", callback_data=f"admin_backup_restore_{backup_file}"),
                telebot.types.InlineKeyboardButton("❌ Удалить", callback_data=f"admin_backup_delete_{backup_file}")
            )
            keyboard.row(telebot.types.InlineKeyboardButton("↩️ Назад", callback_data="admin_backup_list"))
            
            bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=keyboard)
            
        except Exception as e:
            bot.send_message(user_id, f"❌ Ошибка при чтении бэкапа: {e}")
        
        bot.answer_callback_query(call.id)
        
        return
    
    # ===== АДМИН: ВОССТАНОВИТЬ ИЗ БЭКАПА =====
    if call.data.startswith('admin_backup_restore_'):
        backup_file = call.data[21:]  # убираем 'admin_backup_restore_'
        
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.row(
            telebot.types.InlineKeyboardButton("✅ Да, восстановить", callback_data=f"admin_confirm_restore_{backup_file}"),
            telebot.types.InlineKeyboardButton("❌ Отмена", callback_data="admin_backups")
        )
        
        bot.send_message(
            user_id,
            f"⚠️ *ВНИМАНИЕ!*\n\n"
            f"Восстановление из бэкапа ЗАМЕНИТ все текущие данные:\n\n"
            f"Текущие данные:\n"
            f"   • Активные заказы: {len(active_orders)}\n"
            f"   • Завершенные заказы: {len(completed_orders)}\n"
            f"   • Админ-чаты: {len(admin_chats)}\n\n"
            f"Это действие необратимо без создания нового бэкапа.\n\n"
            f"Продолжить?",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        
        bot.answer_callback_query(call.id)
        
        return
    
    # ===== АДМИН: ПОДТВЕРЖДЕНИЕ ВОССТАНОВЛЕНИЯ =====
    if call.data.startswith('admin_confirm_restore_'):
        backup_file = call.data[21:]  # убираем 'admin_confirm_restore_'
        
        bot.send_message(user_id, "⏳ Восстановление из бэкапа...")
        
        success, result = restore_from_backup(backup_file)
        
        if success:
            bot.send_message(
                user_id,
                f"✅ *Система успешно восстановлена из бэкапа от {result}*\n\n"
                f"Восстановлено:\n"
                f"   • {len(active_orders)} активных заказов\n"
                f"   • {len(completed_orders)} завершенных заказов\n"
                f"   • {len(admin_chats)} админ-чатов с полной историей\n\n"
                f"Все данные загружены. Система работает в штатном режиме.",
                parse_mode="Markdown"
            )
        else:
            bot.send_message(
                user_id,
                f"❌ Ошибка восстановления: {result}"
            )
        
        bot.answer_callback_query(call.id)
        
        return
    
    # ===== АДМИН: УДАЛИТЬ БЭКАП =====
    if call.data.startswith('admin_backup_delete_'):
        backup_file = call.data[19:]  # убираем 'admin_backup_delete_'
        
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.row(
            telebot.types.InlineKeyboardButton("✅ Да, удалить", callback_data=f"admin_confirm_delete_{backup_file}"),
            telebot.types.InlineKeyboardButton("❌ Отмена", callback_data="admin_backup_list")
        )
        
        bot.send_message(
            user_id,
            f"⚠️ Удалить бэкап {os.path.basename(backup_file)}?\n\nЭто действие нельзя отменить.",
            reply_markup=keyboard
        )
        
        bot.answer_callback_query(call.id)
        
        return
    
    # ===== АДМИН: ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ =====
    if call.data.startswith('admin_confirm_delete_'):
        backup_file = call.data[20:]  # убираем 'admin_confirm_delete_'
        
        try:
            os.remove(backup_file)
            bot.send_message(user_id, f"✅ Бэкап удален")
        except Exception as e:
            bot.send_message(user_id, f"❌ Ошибка при удалении: {e}")
        
        bot.answer_callback_query(call.id)
        
        return
    
    # ===== АДМИН: ПОИСК =====
    if call.data == "admin_search":
        bot.send_message(
            user_id,
            "🔍 *ПОИСК*\n\n"
            "Введите номер заказа:\n\n"
            "Форматы:\n"
            "• #А1 - заказ Александра\n"
            "• #Е2 - заказ Евгения\n"
            "• #Ю3 - заказ Юлии\n"
            "• #Т4 - заказ Татьяны\n"
            "• #Р5 - заказ Рабочего",
            parse_mode="Markdown"
        )
        bot.answer_callback_query(call.id)
        
        return
    
    # ===== АДМИН: НАЗАД =====
    if call.data == "admin_back":
        bot.send_message(
            user_id,
            "👑 *Панель администратора*\n\nВыберите действие:",
            parse_mode="Markdown",
            reply_markup=get_admin_main_keyboard()
        )
        bot.answer_callback_query(call.id)
        
        return

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
    # Загружаем данные
    load_data()
    
    # Создаем директорию для бэкапов если нет
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    
    # Устанавливаем вебхук
    bot.remove_webhook()
    
    service_name = os.environ.get('RENDER_SERVICE_NAME', 'dp-sbor')
    webhook_url = f'https://{service_name}.onrender.com/webhook'
    
    bot.set_webhook(url=webhook_url)
    print(f"✅ Вебхук установлен: {webhook_url}")
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
