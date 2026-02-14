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

# ADMIN ID - добавьте ваш Telegram ID в переменные окружения Render!
ADMIN_ID = os.environ.get('ADMIN_ID')
if ADMIN_ID:
    ADMIN_ID = int(ADMIN_ID)
    print(f"👑 Администратор: {ADMIN_ID}")
else:
    print("⚠️ ADMIN_ID не установлен! Функции администратора недоступны")
    ADMIN_ID = None

# ====== СТРУКТУРЫ ДАННЫХ ======

# Временные данные пользователей
user_data = {}

# Счетчики для каждого продавца (для нумерации А1, Е2, Ю3...)
seller_counters = {
    'Александр': 0,
    'Евгений': 0,
    'Юлия': 0,
    'Татьяна': 0,
    'Рабочий': 0
}

# Префиксы для заказов
seller_prefixes = {
    "Александр": "А",
    "Евгений": "Е",
    "Юлия": "Ю",
    "Татьяна": "Т",
    "Рабочий": "Р"
}

# Активные заказы {order_ref: order_data} где order_ref = "А1", "Е2" и т.д.
active_orders = {}

# Завершенные заказы {order_ref: order_data}
completed_orders = {}

# Активные чаты покупателей с продавцами {buyer_id: order_ref}
active_chats = {}

# Ожидание уточнения заказа от продавца {seller_id: order_ref}
seller_waiting_for_order_update = {}

# Список точек
pickup_points = {
    "ул. Галущака 15": "Александр",
    "ул. Беловежская 4/1": "Юлия",
    "ул. Забалуева 90": "Евгений",
    "ул. Сержанта Коротаева 3": "Татьяна",
    "ул. Бетонная 14/1": "Рабочий"
}

# ====== ФУНКЦИИ ДЛЯ РАБОТЫ С ФАЙЛАМИ ======

def save_data():
    """Сохраняем все данные в файл"""
    data = {
        'seller_counters': seller_counters,
        'active_orders': active_orders,
        'completed_orders': completed_orders,
        'active_chats': active_chats,
        'seller_waiting': seller_waiting_for_order_update,
        'last_save': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Сначала сохраняем во временный файл
    temp_file = DATA_FILE + '.tmp'
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # Если успешно, заменяем основной файл
        os.replace(temp_file, DATA_FILE)
        print(f"✅ Данные сохранены: {len(active_orders)} активных заказов")
        
    except Exception as e:
        print(f"❌ Ошибка сохранения данных: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)

def load_data():
    """Загружаем все данные из файла"""
    global seller_counters, active_orders, completed_orders, active_chats
    global seller_waiting_for_order_update
    
    if not os.path.exists(DATA_FILE):
        print("📁 Файл данных не найден, начинаем с нуля")
        return
    
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        seller_counters = data.get('seller_counters', {
            'Александр': 0,
            'Евгений': 0,
            'Юлия': 0,
            'Татьяна': 0,
            'Рабочий': 0
        })
        
        active_orders = data.get('active_orders', {})
        completed_orders = data.get('completed_orders', {})
        active_chats = data.get('active_chats', {})
        seller_waiting_for_order_update = data.get('seller_waiting', {})
        
        # Конвертируем строковые ID в числа где нужно
        convert_data_types()
        
        print(f"✅ Данные загружены:")
        print(f"   - Активных заказов: {len(active_orders)}")
        print(f"   - Завершенных заказов: {len(completed_orders)}")
        
    except Exception as e:
        print(f"❌ Ошибка загрузки данных: {e}")

def convert_data_types():
    """Конвертирует строковые ID в числа"""
    # Конвертация active_chats
    new_active_chats = {}
    for key, value in active_chats.items():
        try:
            new_active_chats[int(key)] = value
        except:
            new_active_chats[key] = value
    active_chats.clear()
    active_chats.update(new_active_chats)
    
    # Конвертация seller_waiting
    new_waiting = {}
    for key, value in seller_waiting_for_order_update.items():
        try:
            new_waiting[int(key)] = value
        except:
            new_waiting[key] = value
    seller_waiting_for_order_update.clear()
    seller_waiting_for_order_update.update(new_waiting)

# Загружаем данные при старте
load_data()

# ====== ФУНКЦИИ ДЛЯ ПРОВЕРКИ ПРАВ ======

def is_admin(user_id):
    """Проверка, является ли пользователь администратором"""
    return ADMIN_ID is not None and user_id == ADMIN_ID

def is_seller(user_id):
    """Проверка, является ли пользователь продавцом"""
    return user_id in get_all_seller_ids()

def can_view_order(user_id, order_ref):
    """Проверка, может ли пользователь видеть заказ"""
    if is_admin(user_id):
        return True
    if is_seller(user_id) and order_ref in active_orders:
        return active_orders[order_ref]['seller_id'] == user_id
    return False

# ====== ФУНКЦИИ ДЛЯ ПОЛУЧЕНИЯ ID ПРОДАВЦОВ ======

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
        print(f"❌ Неизвестный продавец: {seller_name}")
        return None
    
    seller_id_str = os.environ.get(env_var_name)
    if not seller_id_str:
        print(f"⚠️ Внимание: ID продавца {seller_name} не установлен!")
        return None
    
    try:
        return int(seller_id_str)
    except ValueError:
        print(f"❌ Ошибка: ID продавца {seller_name} должен быть числом")
        return None

def get_all_seller_ids():
    """Получить список всех ID продавцов"""
    seller_ids = []
    for seller_name in pickup_points.values():
        seller_id = get_seller_id(seller_name)
        if seller_id:
            seller_ids.append(seller_id)
    return seller_ids

def get_seller_name_by_id(seller_id):
    """Получить имя продавца по его ID"""
    for seller_name in pickup_points.values():
        if get_seller_id(seller_name) == seller_id:
            return seller_name
    return None

def get_seller_active_orders(seller_id):
    """Получить все активные заказы продавца"""
    seller_orders = []
    for order_ref, order in active_orders.items():
        if order['seller_id'] == seller_id:
            seller_orders.append(order_ref)
    return seller_orders

def get_seller_prefix(seller_name):
    """Получить префикс продавца (А, Е, Ю, Т, Р)"""
    return seller_prefixes.get(seller_name, "?")

# ====== ФУНКЦИИ ДЛЯ РАБОТЫ С ЗАКАЗАМИ ======

def generate_order_ref(seller_name):
    """Генерирует ссылку на заказ вида А1, Е2 и т.д."""
    global seller_counters
    seller_counters[seller_name] = seller_counters.get(seller_name, 0) + 1
    prefix = get_seller_prefix(seller_name)
    return f"{prefix}{seller_counters[seller_name]}"

def parse_order_ref(text):
    """Парсит ссылку на заказ из сообщения"""
    if text.startswith('#'):
        parts = text[1:].split(' ', 1)
        ref = parts[0].strip()
        message_text = parts[1] if len(parts) > 1 else ""
        return ref, message_text
    return None, None

def validate_order_ref(ref, seller_id=None):
    """Проверяет корректность ссылки на заказ"""
    if not ref:
        return False, "Пустая ссылка"
    
    # Проверка формата: буква + цифра
    if len(ref) < 2 or ref[0] not in seller_prefixes.values() or not ref[1:].isdigit():
        return False, "Неверный формат"
    
    # Проверка существования заказа
    if ref not in active_orders:
        return False, "Заказ не найден"
    
    # Если указан продавец, проверяем принадлежность
    if seller_id and active_orders[ref]['seller_id'] != seller_id:
        return False, "Чужой заказ"
    
    return True, "OK"

def find_order_by_ref(ref):
    """Ищет заказ по ссылке"""
    if ref in active_orders:
        return active_orders[ref]
    if ref in completed_orders:
        return completed_orders[ref]
    return None

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
            'seller_counters': seller_counters,
            'active_orders': active_orders,
            'completed_orders': completed_orders,
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
    backups = sorted(glob.glob(f"{BACKUP_DIR}/backup_*.json"))
    if len(backups) > keep:
        for backup in backups[:-keep]:
            try:
                os.remove(backup)
                print(f"🗑 Удален старый бэкап: {backup}")
            except:
                pass

def get_backups_list():
    """Возвращает список бэкапов с информацией"""
    backups = sorted(glob.glob(f"{BACKUP_DIR}/backup_*.json"), reverse=True)
    result = []
    
    for i, backup_file in enumerate(backups[:20], 1):
        try:
            with open(backup_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            timestamp = data.get('timestamp', 'unknown')
            backup_type = data.get('type', 'unknown')
            active = len(data.get('data', {}).get('active_orders', {}))
            completed = len(data.get('data', {}).get('completed_orders', {}))
            
            result.append({
                'file': backup_file,
                'display': f"{i}. {timestamp} - {backup_type} - {active} акт, {completed} зав"
            })
        except:
            continue
    
    return result

def restore_from_backup(backup_file):
    """Восстанавливает систему из бэкапа"""
    global seller_counters, active_orders, completed_orders, active_chats
    global seller_waiting_for_order_update
    
    try:
        with open(backup_file, 'r', encoding='utf-8') as f:
            backup = json.load(f)
        
        data = backup['data']
        
        seller_counters = data.get('seller_counters', seller_counters)
        active_orders = data.get('active_orders', {})
        completed_orders = data.get('completed_orders', {})
        active_chats = data.get('active_chats', {})
        seller_waiting_for_order_update = data.get('seller_waiting', {})
        
        convert_data_types()
        save_data()
        
        return True, backup.get('timestamp', 'unknown')
        
    except Exception as e:
        return False, str(e)

# ====== КЛАВИАТУРЫ ======

def get_buyer_main_keyboard():
    """Основная клавиатура покупателя (всегда видна)"""
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row('📋 Каталог с ценами', '🏢 О нас')
    keyboard.row('👤 Связаться с админом')
    return keyboard

def get_buyer_new_order_keyboard():
    """Клавиатура для нового заказа (после завершения)"""
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row('📋 Каталог с ценами', '🏢 О нас')
    keyboard.row('👤 Связаться с админом', '🔄 Сделать новый заказ')
    return keyboard

def get_address_keyboard():
    """Клавиатура с адресами"""
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for address in pickup_points.keys():
        keyboard.add(address)
    return keyboard

def get_back_to_order_keyboard():
    """Кнопка возврата к оформлению заказа (отдельным сообщением)"""
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.add(telebot.types.InlineKeyboardButton(
        text="🔙 Вернуться к оформлению заказа",
        callback_data="back_to_order"
    ))
    return keyboard

def get_seller_order_keyboard(order_ref):
    """Кнопки для заказа (уточнить/завершить)"""
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.row(
        telebot.types.InlineKeyboardButton("✏️ Уточнить заказ", callback_data=f"seller_update_{order_ref}"),
        telebot.types.InlineKeyboardButton("✅ Завершить заказ", callback_data=f"seller_close_{order_ref}")
    )
    return keyboard

def get_seller_cancel_update_keyboard():
    """Кнопка отмены уточнения для продавца"""
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.add(telebot.types.InlineKeyboardButton(
        text="❌ Отменить уточнение",
        callback_data="seller_cancel_update"
    ))
    return keyboard

def get_seller_confirm_close_keyboard(order_ref):
    """Кнопки подтверждения завершения заказа"""
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.row(
        telebot.types.InlineKeyboardButton("✅ Да, завершить", callback_data=f"seller_confirm_close_{order_ref}"),
        telebot.types.InlineKeyboardButton("❌ Отмена", callback_data=f"seller_view_{order_ref}")
    )
    return keyboard

def get_admin_main_keyboard():
    """Основная клавиатура администратора"""
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.row(
        telebot.types.InlineKeyboardButton("📦 Активные заказы", callback_data="admin_active_orders"),
        telebot.types.InlineKeyboardButton("📜 Завершенные заказы", callback_data="admin_completed_orders")
    )
    keyboard.row(
        telebot.types.InlineKeyboardButton("💾 Бэкапы", callback_data="admin_backups")
    )
    return keyboard

def get_backups_menu_keyboard():
    """Меню бэкапов"""
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.row(
        telebot.types.InlineKeyboardButton("💾 Создать бэкап", callback_data="backup_create"),
        telebot.types.InlineKeyboardButton("📤 Восстановить", callback_data="backup_restore_menu")
    )
    keyboard.row(
        telebot.types.InlineKeyboardButton("📋 Список бэкапов", callback_data="backup_list"),
        telebot.types.InlineKeyboardButton("↩️ Назад", callback_data="admin_back")
    )
    return keyboard

def get_restore_menu_keyboard():
    """Меню восстановления"""
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.row(
        telebot.types.InlineKeyboardButton("📋 Из списка бэкапов", callback_data="backup_restore_from_list"),
        telebot.types.InlineKeyboardButton("📎 Загрузить файл", callback_data="backup_restore_upload")
    )
    keyboard.row(telebot.types.InlineKeyboardButton("↩️ Назад", callback_data="admin_backups"))
    return keyboard

def get_admin_force_close_keyboard(order_ref):
    """Кнопки подтверждения принудительного завершения заказа"""
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.row(
        telebot.types.InlineKeyboardButton("✅ Да, завершить", callback_data=f"admin_confirm_force_close_{order_ref}"),
        telebot.types.InlineKeyboardButton("❌ Отмена", callback_data=f"admin_view_order_{order_ref}")
    )
    return keyboard

# ====== ОБЩИЕ ФУНКЦИИ ======

def show_instruction(chat_id):
    """Показать инструкцию с клавиатурой"""
    bot.send_message(
        chat_id,
        "🟢 *Пошаговая инструкция:*\n\n"
        "1. Напишите, что хотите заказать\n"
        "2. Выберите откуда удобнее забрать\n"
        "3. Менеджер свяжется с вами",
        parse_mode="Markdown",
        reply_markup=get_buyer_main_keyboard()
    )

# ====== ОБРАБОТЧИКИ КОМАНД ======

@bot.message_handler(commands=['start'])
def cmd_start(message):
    """Обработчик команды /start"""
    show_instruction(message.chat.id)

@bot.message_handler(commands=['admin'])
def cmd_admin(message):
    """Панель администратора"""
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

@bot.message_handler(commands=['backup'])
def cmd_backup(message):
    """Быстрое создание бэкапа"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(user_id, "❌ У вас нет прав администратора")
        return
    
    bot.send_message(user_id, "⏳ Создание бэкапа...")
    filename = create_backup('manual')
    
    if filename:
        bot.send_message(
            user_id,
            f"✅ Бэкап успешно создан!\n\n📁 Файл: {os.path.basename(filename)}"
        )
    else:
        bot.send_message(user_id, "❌ Ошибка создания бэкапа")

# ====== ОБРАБОТЧИКИ ТЕКСТОВЫХ СООБЩЕНИЙ ======

@bot.message_handler(func=lambda message: message.text == '📋 Каталог с ценами')
def handle_catalog(message):
    """Показ каталога"""
    chat_id = message.chat.id
    
    catalog_text = (
        "📋 *Каталог с ценами*\n\n"
        "1. Грецкий орех очищенный, 500г - 400 ₽\n"
        "2. Миндаль золотой, 1000г - 950 ₽\n"
        "3. Кешью WW320, 1000г - 1000 ₽\n"
        "4. Манго сушеное, 500г - 250 ₽\n"
        "5. Клубника сушеная, 500г - 350 ₽"
    )
    
    bot.send_message(
        chat_id,
        catalog_text,
        parse_mode="Markdown",
        reply_markup=get_buyer_main_keyboard()
    )
    
    # Отдельное сообщение с кнопкой возврата
    bot.send_message(
        chat_id,
        "Нажмите кнопку ниже, чтобы вернуться к оформлению заказа",
        reply_markup=get_back_to_order_keyboard()
    )

@bot.message_handler(func=lambda message: message.text == '🏢 О нас')
def handle_about(message):
    """Информация о компании"""
    chat_id = message.chat.id
    
    about_text = (
        "🏢 *О нашей компании*\n\n"
        "*DP SBOR | Отборные орехи и сухофрукты • Новосибирск*\n"
        "Мы выбираем продукты по качеству, вкусу и внешнему виду, а не по минимальной цене\n\n"
        "Всё, начиная от выбора товара, заканчивая фасовкой и упаковкой проходит жесткий контроль\n\n"
        "Вы гарантированно получаете высшее качество по шикарным ценам\n\n"
        "📍 На данный момент есть 5 точек *в Новосибирске*, где можно забрать заказ\n\n"
        "*Наш канал: t.me/dp_sbor*"
    )
    
    bot.send_message(
        chat_id,
        about_text,
        parse_mode="Markdown",
        reply_markup=get_buyer_main_keyboard()
    )
    
    # Отдельное сообщение с кнопкой возврата
    bot.send_message(
        chat_id,
        "Нажмите кнопку ниже, чтобы вернуться к оформлению заказа",
        reply_markup=get_back_to_order_keyboard()
    )

@bot.message_handler(func=lambda message: message.text == '👤 Связаться с админом')
def handle_contact_admin(message):
    """Мгновенный переход в личный чат с администратором"""
    user_id = message.from_user.id
    
    if not ADMIN_ID:
        bot.send_message(
            user_id,
            "❌ К сожалению, администратор временно недоступен."
        )
        return
    
    # Создаем кнопку с прямой ссылкой на админа
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.add(telebot.types.InlineKeyboardButton(
        text="👤 Написать администратору",
        url=f"tg://user?id={ADMIN_ID}"
    ))
    
    bot.send_message(
        user_id,
        "Нажмите кнопку ниже, чтобы написать администратору:",
        reply_markup=keyboard
    )

@bot.message_handler(func=lambda message: message.text == '🔄 Сделать новый заказ')
def handle_new_order(message):
    """Новый заказ после завершения предыдущего"""
    show_instruction(message.chat.id)

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    """Обработка всех текстовых сообщений"""
    user_id = message.from_user.id
    text = message.text.strip()
    
    # --- АДМИНИСТРАТОР ---
    if is_admin(user_id):
        # Проверяем, не является ли это ответом на заказ
        if text.startswith('#'):
            handle_admin_reply(message)
        else:
            # Показываем панель админа
            cmd_admin(message)
        return
    
    # --- ПРОДАВЕЦ ---
    if is_seller(user_id):
        handle_seller_message(message)
        return
    
    # --- ПОКУПАТЕЛЬ ---
    handle_buyer_message(message)

# ====== ОБРАБОТЧИКИ ДЛЯ АДМИНИСТРАТОРА ======

def handle_admin_reply(message):
    """Обработка ответа администратора в формате #..."""
    user_id = message.from_user.id
    text = message.text
    
    ref, message_text = parse_order_ref(text)
    
    if not ref or not message_text:
        bot.send_message(
            user_id,
            "❌ Неверный формат.\n"
            "✅ Правильно: #А1 *текст*"
        )
        return
    
    # Проверяем, это заказ
    if ref in active_orders:
        # Ответ на заказ
        order = active_orders[ref]
        
        # Отправляем покупателю
        bot.send_message(
            order['buyer_id'],
            f"💬 *Сообщение от администратора:*\n\n{message_text}",
            parse_mode="Markdown"
        )
        
        # Уведомляем продавца
        bot.send_message(
            order['seller_id'],
            f"👑 *Вмешательство администратора*\n\n"
            f"Администратор отправил сообщение по вашему заказу {ref}\n\n"
            f"💬 {message_text}",
            parse_mode="Markdown"
        )
        
        bot.send_message(
            user_id,
            f"✅ Сообщение отправлено покупателю (Заказ {ref})"
        )
        
    else:
        bot.send_message(
            user_id,
            f"❌ Заказ {ref} не найден"
        )

def show_active_orders(chat_id):
    """Показать все активные заказы"""
    if not active_orders:
        bot.send_message(
            chat_id,
            "📦 Нет активных заказов"
        )
        return
    
    # Группируем по продавцам
    orders_by_seller = {}
    for ref, order in active_orders.items():
        seller = order['seller_name']
        if seller not in orders_by_seller:
            orders_by_seller[seller] = []
        orders_by_seller[seller].append((ref, order))
    
    text = "📦 *Активные заказы*\n\n"
    keyboard = telebot.types.InlineKeyboardMarkup()
    
    for seller, orders in orders_by_seller.items():
        text += f"👤 *{seller}* ({len(orders)}):\n"
        for ref, order in orders:
            buyer_link = f"[💬](tg://user?id={order['buyer_id']})"
            text += f"• {ref} - {order['buyer_name']} {buyer_link} - {order['order_text'][:30]}...\n"
            keyboard.add(telebot.types.InlineKeyboardButton(
                text=f"{ref} - {order['buyer_name']}",
                callback_data=f"admin_view_order_{ref}"
            ))
        text += "\n"
    
    keyboard.add(telebot.types.InlineKeyboardButton("↩️ Назад", callback_data="admin_back"))
    
    # Разбиваем на части, если слишком длинно
    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts:
            bot.send_message(chat_id, part, parse_mode="Markdown")
    else:
        bot.send_message(chat_id, text, parse_mode="Markdown")
    
    bot.send_message(
        chat_id,
        "Нажмите на заказ для просмотра деталей:",
        reply_markup=keyboard
    )

def show_completed_orders(chat_id, page=0):
    """Показать завершенные заказы (по 20)"""
    if not completed_orders:
        bot.send_message(
            chat_id,
            "📜 Нет завершенных заказов"
        )
        return
    
    # Сортируем по дате завершения (сначала новые)
    sorted_orders = sorted(
        completed_orders.items(),
        key=lambda x: x[1].get('completed_at', ''),
        reverse=True
    )
    
    start = page * 20
    end = start + 20
    page_orders = sorted_orders[start:end]
    
    if not page_orders:
        bot.send_message(chat_id, "📜 Завершенные заказы закончились")
        return
    
    text = f"📜 *Завершенные заказы* (стр. {page+1})\n\n"
    keyboard = telebot.types.InlineKeyboardMarkup()
    
    for ref, order in page_orders:
        completed_at = order.get('completed_at', 'unknown')
        buyer_link = f"[💬](tg://user?id={order['buyer_id']})"
        text += f"✅ {ref} - {completed_at} - {order['seller_name']} - {order['buyer_name']} {buyer_link}\n"
        keyboard.add(telebot.types.InlineKeyboardButton(
            text=f"{ref} - {order['buyer_name']}",
            callback_data=f"admin_view_completed_{ref}"
        ))
    
    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(telebot.types.InlineKeyboardButton(
            "⬅️ Предыдущие",
            callback_data=f"admin_completed_page_{page-1}"
        ))
    if end < len(sorted_orders):
        nav_buttons.append(telebot.types.InlineKeyboardButton(
            "Следующие ➡️",
            callback_data=f"admin_completed_page_{page+1}"
        ))
    
    if nav_buttons:
        keyboard.row(*nav_buttons)
    
    keyboard.add(telebot.types.InlineKeyboardButton("↩️ Назад", callback_data="admin_back"))
    
    bot.send_message(
        chat_id,
        text,
        parse_mode="Markdown"
    )
    
    bot.send_message(
        chat_id,
        "Нажмите на заказ для просмотра деталей:",
        reply_markup=keyboard
    )

def show_order_details(chat_id, ref, is_completed=False):
    """Показать детали заказа"""
    orders = completed_orders if is_completed else active_orders
    order = orders.get(ref)
    
    if not order:
        bot.send_message(chat_id, f"❌ Заказ {ref} не найден")
        return
    
    status = "✅ Завершен" if is_completed else "📦 Активен"
    created = order.get('timestamp', 'unknown')
    completed = order.get('completed_at', '—')
    
    text = (
        f"{status} *ЗАКАЗ {ref}*\n\n"
        f"📅 Создан: {created}\n"
        f"{f'📅 Завершен: {completed}\n' if is_completed else ''}"
        f"👤 Продавец: {order['seller_name']}\n"
        f"👤 Покупатель: {order['buyer_name']} [💬](tg://user?id={order['buyer_id']})\n"
        f"📍 Адрес: {order['address']}\n"
        f"📝 Заказ: {order['order_text']}\n"
    )
    
    bot.send_message(
        chat_id,
        text,
        parse_mode="Markdown"
    )
    
    # Показываем историю сообщений, если есть
    if 'history' in order and order['history']:
        history_text = "📜 *История переписки:*\n\n"
        for msg in order['history']:
            if msg['role'] == 'buyer':
                history_text += f"👤 [{msg['time']}] {msg['text']}\n\n"
            elif msg['role'] == 'seller':
                history_text += f"👨‍💼 [{msg['time']}] {msg['text']}\n\n"
            elif msg['role'] == 'admin':
                history_text += f"👑 [{msg['time']}] {msg['text']}\n\n"
        
        # Разбиваем на части, если слишком длинно
        if len(history_text) > 4000:
            parts = [history_text[i:i+4000] for i in range(0, len(history_text), 4000)]
            for part in parts:
                bot.send_message(chat_id, part, parse_mode="Markdown")
        else:
            bot.send_message(chat_id, history_text, parse_mode="Markdown")
    
    if not is_completed:
        # Кнопки для активного заказа
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.row(
            telebot.types.InlineKeyboardButton("✏️ Ответить", callback_data=f"admin_reply_{ref}"),
            telebot.types.InlineKeyboardButton("✅ Завершить", callback_data=f"admin_force_close_{ref}")
        )
        keyboard.add(telebot.types.InlineKeyboardButton("↩️ Назад", callback_data="admin_active_orders"))
        bot.send_message(
            chat_id,
            "Действия с заказом:",
            reply_markup=keyboard
        )

def force_close_order(chat_id, order_ref):
    """Принудительное завершение заказа администратором"""
    order = active_orders.get(order_ref)
    
    if not order:
        bot.send_message(chat_id, f"❌ Заказ {order_ref} не найден")
        return
    
    # Отправляем покупателю
    bot.send_message(
        order['buyer_id'],
        f"✅ *Заказ {order_ref} завершен администратором*\n\n"
        f"📝 *Содержание:* {order['order_text']}\n"
        f"📍 *Адрес:* {order['address']}\n\n"
        f"💬 *Если остались вопросы, свяжитесь с администратором*",
        parse_mode="Markdown",
        reply_markup=get_buyer_new_order_keyboard()
    )
    
    # Уведомляем продавца
    bot.send_message(
        order['seller_id'],
        f"👑 *Заказ {order_ref} завершен администратором*\n\n"
        f"Покупатель уведомлен о завершении заказа.",
        parse_mode="Markdown"
    )
    
    # Добавляем в завершенные
    order['completed_at'] = datetime.now().strftime("%d.%m.%Y %H:%M")
    order['status'] = 'completed'
    order['completed_by'] = 'admin'
    completed_orders[order_ref] = order
    
    # Удаляем из активных
    if order_ref in active_orders:
        del active_orders[order_ref]
    
    # Удаляем из активных чатов
    if order['buyer_id'] in active_chats:
        del active_chats[order['buyer_id']]
    
    save_data()
    
    bot.send_message(chat_id, f"✅ Заказ {order_ref} принудительно завершен")
    
    # Возвращаемся к списку активных заказов
    show_active_orders(chat_id)

# ====== ОБРАБОТЧИКИ ДЛЯ ПРОДАВЦА ======

def handle_seller_message(message):
    """Обработка сообщений от продавца"""
    seller_id = message.from_user.id
    text = message.text
    
    # Проверяем, ожидает ли продавец уточнения заказа
    if seller_id in seller_waiting_for_order_update:
        handle_seller_update_text(message)
        return
    
    # Проверяем, является ли сообщение ответом через #
    if text.startswith('#'):
        handle_seller_reply(message)
    else:
        # Показываем список активных заказов
        show_seller_orders(seller_id)

def handle_seller_reply(message):
    """Обработка ответа продавца в формате #А1 текст"""
    seller_id = message.from_user.id
    text = message.text
    
    ref, message_text = parse_order_ref(text)
    
    if not ref:
        bot.send_message(
            seller_id,
            "❌ Неверный формат.\n"
            f"✅ Правильно: #{get_seller_prefix(get_seller_name_by_id(seller_id))}1 *текст*"
        )
        return
    
    # Проверяем корректность ссылки
    is_valid, error_msg = validate_order_ref(ref, seller_id)
    
    if not is_valid:
        if error_msg == "Неверный формат":
            bot.send_message(
                seller_id,
                f"❌ Неверный формат.\n"
                f"✅ Правильно: #{get_seller_prefix(get_seller_name_by_id(seller_id))}1 *текст*"
            )
        elif error_msg == "Заказ не найден":
            bot.send_message(
                seller_id,
                f"❌ Заказ {ref} не найден\n\n"
                f"Ваши активные заказы: {', '.join(get_seller_active_orders(seller_id))}"
            )
        elif error_msg == "Чужой заказ":
            bot.send_message(
                seller_id,
                f"❌ У вас нет заказа {ref}\n\n"
                f"Ваши активные заказы: {', '.join(get_seller_active_orders(seller_id))}"
            )
        return
    
    if not message_text:
        bot.send_message(
            seller_id,
            f"❌ Не указан текст сообщения.\n"
            f"✅ Правильно: #{ref} *текст*"
        )
        return
    
    # Отправляем сообщение покупателю
    order = active_orders[ref]
    
    bot.send_message(
        order['buyer_id'],
        f"💬 *Сообщение от менеджера:*\n\n{message_text}",
        parse_mode="Markdown"
    )
    
    # Сохраняем в историю заказа
    if 'history' not in order:
        order['history'] = []
    order['history'].append({
        'time': datetime.now().strftime("%d.%m %H:%M"),
        'role': 'seller',
        'text': message_text
    })
    
    bot.send_message(
        seller_id,
        f"✅ Сообщение отправлено покупателю (Заказ {ref})"
    )
    
    # Уведомляем админа
    if ADMIN_ID:
        bot.send_message(
            ADMIN_ID,
            f"👑 *Ответ продавца*\n\n"
            f"📦 Заказ {ref}\n"
            f"👤 Продавец: {order['seller_name']}\n"
            f"💬 {message_text}",
            parse_mode="Markdown"
        )
    
    save_data()

def handle_seller_update_text(message):
    """Обработка текста уточнения заказа от продавца"""
    seller_id = message.from_user.id
    text = message.text
    
    if seller_id not in seller_waiting_for_order_update:
        return
    
    ref = seller_waiting_for_order_update[seller_id]
    order = active_orders.get(ref)
    
    if not order:
        del seller_waiting_for_order_update[seller_id]
        bot.send_message(seller_id, "❌ Заказ не найден")
        return
    
    # Сохраняем старый заказ для истории
    old_text = order['order_text']
    
    # Обновляем заказ
    order['order_text'] = text
    order['updated_at'] = datetime.now().strftime("%d.%m %H:%M")
    
    # Сохраняем в историю
    if 'history' not in order:
        order['history'] = []
    order['history'].append({
        'time': datetime.now().strftime("%d.%m %H:%M"),
        'role': 'seller',
        'text': f"✏️ Уточнил заказ: {text}"
    })
    
    save_data()
    
    # Отправляем подтверждение продавцу
    bot.send_message(
        seller_id,
        f"✅ *Заказ {ref} обновлен!*\n\n"
        f"📝 *Актуальный заказ:* {text}\n"
        f"📍 *Адрес:* {order['address']}",
        parse_mode="Markdown",
        reply_markup=get_seller_order_keyboard(ref)
    )
    
    # Отправляем покупателю
    bot.send_message(
        order['buyer_id'],
        f"📝 *Уточненный заказ:*\n\n{text}\n\n"
        f"📍 *Адрес:* {order['address']}\n\n"
        f"*Отправьте сообщение, если хотите еще что-то уточнить.*",
        parse_mode="Markdown"
    )
    
    # Уведомляем админа
    if ADMIN_ID:
        bot.send_message(
            ADMIN_ID,
            f"👑 *Заказ {ref} обновлен*\n\n"
            f"👤 Продавец: {order['seller_name']}\n"
            f"📝 Было: {old_text[:100]}\n"
            f"📝 Стало: {text[:100]}",
            parse_mode="Markdown"
        )
    
    # Очищаем ожидание
    del seller_waiting_for_order_update[seller_id]

def show_seller_orders(seller_id):
    """Показать продавцу его активные заказы"""
    orders = get_seller_active_orders(seller_id)
    
    if not orders:
        bot.send_message(
            seller_id,
            "📋 У вас нет активных заказов."
        )
        return
    
    text = "📋 *Ваши активные заказы:*\n\n"
    for ref in orders:
        order = active_orders[ref]
        text += f"• #{ref} - {order['buyer_name']} - {order['order_text'][:50]}...\n"
    
    text += "\n💬 *Чтобы ответить, начните сообщение с номера заказа:*\n"
    text += f"`#{orders[0]} ваш текст`"
    
    bot.send_message(
        seller_id,
        text,
        parse_mode="Markdown"
    )

# ====== ОБРАБОТЧИКИ ДЛЯ ПОКУПАТЕЛЯ ======

def handle_buyer_message(message):
    """Обработка сообщений от покупателя"""
    user_id = message.from_user.id
    text = message.text
    
    # Проверяем, есть ли у покупателя активный заказ (чат с продавцом)
    if user_id in active_chats:
        # Отправляем сообщение продавцу
        order_ref = active_chats[user_id]
        order = active_orders.get(order_ref)
        
        if order:
            # Сохраняем в историю
            if 'history' not in order:
                order['history'] = []
            order['history'].append({
                'time': datetime.now().strftime("%d.%m %H:%M"),
                'role': 'buyer',
                'text': text
            })
            
            # Отправляем продавцу
            bot.send_message(
                order['seller_id'],
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
                    f"👤 Покупатель: {order['buyer_name']}\n"
                    f"💬 {text}",
                    parse_mode="Markdown"
                )
            
            save_data()
        else:
            # Заказ не найден, удаляем из активных чатов
            if user_id in active_chats:
                del active_chats[user_id]
            save_data()
            # Предлагаем сделать новый заказ
            show_instruction(user_id)
        
        return
    
    # Проверяем, есть ли временные данные (начатый, но не завершенный заказ)
    if user_id in user_data:
        # Если пользователь уже начал заказ, но не выбрал адрес,
        # и сейчас пишет снова - это новый заказ, заменяем старый
        user_data[user_id] = {
            'text': text,
            'name': message.from_user.first_name or "Покупатель",
            'user_id': user_id
        }
        
        bot.send_message(
            user_id,
            "✅ Сообщение получено! Выберите удобный адрес:",
            reply_markup=get_address_keyboard()
        )
        return
    
    # Если дошли сюда - это новый заказ
    user_data[user_id] = {
        'text': text,
        'name': message.from_user.first_name or "Покупатель",
        'user_id': user_id
    }
    
    bot.send_message(
        user_id,
        "✅ Сообщение получено! Выберите удобный адрес:",
        reply_markup=get_address_keyboard()
    )

# ====== ОБРАБОТЧИКИ КОЛЛБЭКОВ ======

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    """Обработка всех нажатий на инлайн-кнопки"""
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    data = call.data
    
    # ===== ОБЩИЕ КНОПКИ =====
    if data == "back_to_order":
        bot.answer_callback_query(call.id)
        show_instruction(chat_id)
        return
    
    # ===== КНОПКИ ДЛЯ ПОКУПАТЕЛЯ (ВЫБОР АДРЕСА) =====
    if data in pickup_points:
        handle_address_selection(call)
        return
    
    # ===== КНОПКИ ДЛЯ ПРОДАВЦА =====
    if data.startswith('seller_'):
        handle_seller_callbacks(call)
        return
    
    # ===== КНОПКИ ДЛЯ АДМИНИСТРАТОРА =====
    if user_id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет прав")
        return
    
    # Главное меню админа
    if data == "admin_active_orders":
        bot.answer_callback_query(call.id)
        show_active_orders(chat_id)
    elif data == "admin_completed_orders":
        bot.answer_callback_query(call.id)
        show_completed_orders(chat_id, 0)
    elif data == "admin_backups":
        bot.answer_callback_query(call.id)
        show_backups_menu(chat_id)
    elif data == "admin_back":
        bot.answer_callback_query(call.id)
        cmd_admin(call.message)
    
    # Заказы
    elif data.startswith('admin_view_order_'):
        ref = data.replace('admin_view_order_', '')
        bot.answer_callback_query(call.id)
        show_order_details(chat_id, ref, False)
    elif data.startswith('admin_view_completed_'):
        ref = data.replace('admin_view_completed_', '')
        bot.answer_callback_query(call.id)
        show_order_details(chat_id, ref, True)
    elif data.startswith('admin_completed_page_'):
        page = int(data.replace('admin_completed_page_', ''))
        bot.answer_callback_query(call.id)
        show_completed_orders(chat_id, page)
    elif data.startswith('admin_force_close_'):
        ref = data.replace('admin_force_close_', '')
        bot.answer_callback_query(call.id)
        # Запрос подтверждения
        bot.send_message(
            chat_id,
            f"⚠️ *Принудительно завершить заказ {ref}?*\n\n"
            f"Это действие закроет чат с покупателем и завершит заказ.",
            parse_mode="Markdown",
            reply_markup=get_admin_force_close_keyboard(ref)
        )
    elif data.startswith('admin_confirm_force_close_'):
        ref = data.replace('admin_confirm_force_close_', '')
        bot.answer_callback_query(call.id)
        force_close_order(chat_id, ref)
    elif data.startswith('admin_reply_'):
        ref = data.replace('admin_reply_', '')
        bot.answer_callback_query(call.id)
        bot.send_message(
            chat_id,
            f"✏️ *Ответ в заказ {ref}*\n\n"
            f"Используйте формат: #{ref} *текст*\n\n"
            f"Пример: #{ref} Здравствуйте, чем могу помочь?",
            parse_mode="Markdown"
        )
    
    # Бэкапы
    elif data == "backup_create":
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, "⏳ Создание бэкапа...")
        filename = create_backup('manual')
        if filename:
            bot.send_message(
                chat_id,
                f"✅ Бэкап успешно создан!\n\n📁 Файл: {os.path.basename(filename)}",
                reply_markup=get_backups_menu_keyboard()
            )
        else:
            bot.send_message(chat_id, "❌ Ошибка создания бэкапа")
    elif data == "backup_restore_menu":
        bot.answer_callback_query(call.id)
        bot.send_message(
            chat_id,
            "📤 *Восстановление*\n\nВыберите способ:",
            parse_mode="Markdown",
            reply_markup=get_restore_menu_keyboard()
        )
    elif data == "backup_list":
        bot.answer_callback_query(call.id)
        show_backups_list(chat_id)
    elif data == "backup_restore_from_list":
        bot.answer_callback_query(call.id)
        show_backups_list(chat_id, for_restore=True)
    elif data == "backup_restore_upload":
        bot.answer_callback_query(call.id)
        bot.send_message(
            chat_id,
            "📎 *Загрузка бэкапа*\n\n"
            "Отправьте мне JSON-файл с бэкапом.\n\n"
            "Требования:\n"
            "• Формат: JSON\n"
            "• Создан этим ботом\n"
            "• Не поврежден",
            parse_mode="Markdown"
        )
        user_data[user_id] = {'state': 'waiting_for_backup_file'}
    elif data.startswith('backup_restore_file_'):
        backup_file = data.replace('backup_restore_file_', '')
        bot.answer_callback_query(call.id)
        confirm_restore(chat_id, backup_file)
    elif data.startswith('backup_do_restore_'):
        backup_file = data.replace('backup_do_restore_', '')
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, "⏳ Восстановление из бэкапа...")
        success, result = restore_from_backup(backup_file)
        if success:
            bot.send_message(
                chat_id,
                f"✅ *Система успешно восстановлена из бэкапа от {result}*\n\n"
                f"Восстановлено:\n"
                f"• {len(active_orders)} активных заказов\n"
                f"• {len(completed_orders)} завершенных заказов\n\n"
                f"Все данные загружены. Система работает в штатном режиме.",
                parse_mode="Markdown"
            )
        else:
            bot.send_message(
                chat_id,
                f"❌ Ошибка восстановления: {result}"
            )

def handle_seller_callbacks(call):
    """Обработчик кнопок продавца"""
    data = call.data
    seller_id = call.from_user.id
    
    if data.startswith('seller_update_'):
        order_ref = data.replace('seller_update_', '')
        order = active_orders.get(order_ref)
        
        if not order:
            bot.answer_callback_query(call.id, "❌ Заказ не найден")
            return
        
        if order['seller_id'] != seller_id:
            bot.answer_callback_query(call.id, "❌ Это не ваш заказ")
            return
        
        seller_waiting_for_order_update[seller_id] = order_ref
        bot.answer_callback_query(call.id)
        
        bot.send_message(
            seller_id,
            f"✏️ *Уточнение заказа {order_ref}*\n\n"
            f"📍 Адрес: {order['address']}\n"
            f"📝 *Текущий заказ:* {order['order_text']}\n\n"
            f"Напишите новый состав заказа.",
            parse_mode="Markdown"
        )
        
        bot.send_message(
            seller_id,
            "Нажмите кнопку ниже, чтобы отменить уточнение",
            reply_markup=get_seller_cancel_update_keyboard()
        )
        
    elif data.startswith('seller_close_'):
        order_ref = data.replace('seller_close_', '')
        order = active_orders.get(order_ref)
        
        if not order:
            bot.answer_callback_query(call.id, "❌ Заказ не найден")
            return
        
        if order['seller_id'] != seller_id:
            bot.answer_callback_query(call.id, "❌ Это не ваш заказ")
            return
        
        bot.answer_callback_query(call.id)
        
        bot.send_message(
            seller_id,
            f"⚠️ *Завершить заказ {order_ref}?*\n\n"
            f"Покупатель получит финальное сообщение с составом заказа.",
            parse_mode="Markdown",
            reply_markup=get_seller_confirm_close_keyboard(order_ref)
        )
        
    elif data == "seller_cancel_update":
        if seller_id not in seller_waiting_for_order_update:
            bot.answer_callback_query(call.id, "❌ Нет активного уточнения")
            return
        
        order_ref = seller_waiting_for_order_update[seller_id]
        order = active_orders.get(order_ref)
        
        if order:
            bot.answer_callback_query(call.id, "✅ Уточнение отменено")
            bot.send_message(
                seller_id,
                f"❌ *Уточнение заказа {order_ref} отменено*\n\n"
                f"Заказ остался без изменений.\n\n"
                f"📝 *Текущий заказ:* {order['order_text']}\n"
                f"📍 *Адрес:* {order['address']}",
                parse_mode="Markdown",
                reply_markup=get_seller_order_keyboard(order_ref)
            )
        else:
            bot.answer_callback_query(call.id, "❌ Заказ не найден")
        
        if seller_id in seller_waiting_for_order_update:
            del seller_waiting_for_order_update[seller_id]
            
    elif data.startswith('seller_confirm_close_'):
        order_ref = data.replace('seller_confirm_close_', '')
        order = active_orders.get(order_ref)
        
        if not order or order['seller_id'] != seller_id:
            bot.answer_callback_query(call.id, "❌ Ошибка")
            return
        
        # Формируем финальное сообщение для покупателя
        final_text = order['order_text']
        order_date = order.get('updated_at', order['timestamp'])
        
        # Отправляем покупателю
        bot.send_message(
            order['buyer_id'],
            f"✅ *Заказ от {order_date}*\n\n"
            f"📝 *Содержание:* {final_text}\n"
            f"📍 *Адрес:* {order['address']}\n\n"
            f"💬 *Чат с менеджером закрыт*",
            parse_mode="Markdown",
            reply_markup=get_buyer_new_order_keyboard()
        )
        
        # Добавляем в завершенные
        order['completed_at'] = datetime.now().strftime("%d.%m.%Y %H:%M")
        order['status'] = 'completed'
        completed_orders[order_ref] = order
        
        # Удаляем из активных
        if order_ref in active_orders:
            del active_orders[order_ref]
        
        # Удаляем из активных чатов
        if order['buyer_id'] in active_chats:
            del active_chats[order['buyer_id']]
        
        # Удаляем из ожиданий
        if seller_id in seller_waiting_for_order_update:
            del seller_waiting_for_order_update[seller_id]
        
        save_data()
        
        # Сообщение продавцу
        bot.edit_message_text(
            f"✅ *ЗАКАЗ {order_ref} ЗАВЕРШЕН*\n\n"
            f"👤 Покупатель: {order['buyer_name']}\n"
            f"📍 Точка: {order['address']}\n"
            f"📝 Заказ: {final_text}\n\n"
            f"📅 Создан: {order['timestamp']}\n"
            f"📅 Завершен: {order['completed_at']}",
            seller_id,
            call.message.message_id,
            parse_mode="Markdown"
        )
        
        # Показываем оставшиеся заказы
        remaining = get_seller_active_orders(seller_id)
        if remaining:
            orders_list = '\n'.join([f"• #{ref}" for ref in remaining])
            bot.send_message(
                seller_id,
                f"📋 *Осталось активных заказов: {len(remaining)}*\n\n"
                f"{orders_list}\n\n"
                f"💬 `#{remaining[0]} ваш текст`"
            )
        else:
            bot.send_message(
                seller_id,
                "✅ *Все заказы завершены!*\n\n"
                "Хорошего дня! Отдыхайте 🍃",
                parse_mode="Markdown"
            )
        
        # Уведомление админа
        if ADMIN_ID:
            bot.send_message(
                ADMIN_ID,
                f"👑 *ЗАКАЗ ЗАВЕРШЕН {order_ref}*\n\n"
                f"👤 Продавец: {order['seller_name']}\n"
                f"👤 Покупатель: {order['buyer_name']} [💬](tg://user?id={order['buyer_id']})\n"
                f"📝 {final_text}",
                parse_mode="Markdown"
            )
        
        # Создаем бэкап
        create_backup('auto')
        
        bot.answer_callback_query(call.id, "✅ Заказ завершен")
        
    elif data.startswith('seller_view_'):
        order_ref = data.replace('seller_view_', '')
        order = active_orders.get(order_ref)
        
        if order and order['seller_id'] == seller_id:
            bot.answer_callback_query(call.id)
            bot.send_message(
                seller_id,
                f"📦 *Заказ {order_ref}*\n\n"
                f"👤 Покупатель: {order['buyer_name']}\n"
                f"📍 Адрес: {order['address']}\n"
                f"📝 Заказ: {order['order_text']}",
                parse_mode="Markdown",
                reply_markup=get_seller_order_keyboard(order_ref)
            )
        else:
            bot.answer_callback_query(call.id, "❌ Заказ не найден")

def handle_address_selection(call):
    """Обработка выбора адреса покупателем"""
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    address = call.data
    
    user_info = user_data.get(user_id)
    
    if not user_info:
        bot.answer_callback_query(call.id, "❌ Ошибка: начните заказ заново")
        bot.send_message(chat_id, "Пожалуйста, напишите что хотите заказать:")
        return
    
    seller_name = pickup_points.get(address)
    seller_id = get_seller_id(seller_name)
    
    if not seller_id:
        bot.answer_callback_query(call.id, "❌ Ошибка: точка временно недоступна")
        return
    
    # Генерируем ссылку на заказ
    order_ref = generate_order_ref(seller_name)
    
    # Создаем заказ
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
        'history': [
            {
                'time': datetime.now().strftime("%d.%m %H:%M"),
                'role': 'buyer',
                'text': user_info['text']
            }
        ]
    }
    
    active_orders[order_ref] = order_data
    active_chats[user_id] = order_ref
    
    # Удаляем сообщение с кнопками адресов
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except:
        pass
    
    # Сообщение покупателю
    bot.send_message(
        chat_id,
        f"🔄 *Ваш заказ в обработке*\n\n"
        f"📍 Адрес: {address}\n"
        f"📝 Ваш заказ: {user_info['text']}\n\n"
        f"*Менеджер скоро свяжется с Вами в этом чате.*",
        parse_mode="Markdown",
        reply_markup=get_buyer_main_keyboard()
    )
    
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
    
    # Инструкция по ответу
    bot.send_message(
        seller_id,
        f"💬 *Чтобы ответить покупателю, используйте формат:*\n"
        f"`#{order_ref} ваш текст`",
        parse_mode="Markdown"
    )
    
    # Уведомление админа
    if ADMIN_ID:
        bot.send_message(
            ADMIN_ID,
            f"👑 *НОВЫЙ ЗАКАЗ {order_ref}*\n\n"
            f"👤 Продавец: {seller_name}\n"
            f"👤 Покупатель: {user_info['name']} [💬](tg://user?id={user_id})\n"
            f"📍 {address}\n"
            f"📝 {user_info['text']}",
            parse_mode="Markdown"
        )
    
    # ВАЖНО: Очищаем временные данные ПОСЛЕ создания заказа
    if user_id in user_data:
        del user_data[user_id]
    
    # Создаем бэкап
    create_backup('auto')
    
    bot.answer_callback_query(call.id, f"✅ Заказ {order_ref} отправлен менеджеру")

# ====== ФУНКЦИИ ДЛЯ БЭКАПОВ (ПРОДОЛЖЕНИЕ) ======

def show_backups_menu(chat_id):
    """Показать меню бэкапов"""
    bot.send_message(
        chat_id,
        "💾 *УПРАВЛЕНИЕ БЭКАПАМИ*\n\n"
        "Автоматические бэкапы создаются при:\n"
        "• Новом заказе\n"
        "• Завершении заказа\n"
        "• Каждые 6 часов\n\n"
        f"Последний авто-бэкап: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        parse_mode="Markdown",
        reply_markup=get_backups_menu_keyboard()
    )

def show_backups_list(chat_id, for_restore=False):
    """Показать список бэкапов"""
    backups = get_backups_list()
    
    if not backups:
        bot.send_message(
            chat_id,
            "📋 Нет доступных бэкапов"
        )
        return
    
    text = "📋 *Доступные бэкапы:*\n\n"
    keyboard = telebot.types.InlineKeyboardMarkup()
    
    for backup in backups:
        text += f"{backup['display']}\n"
        if for_restore:
            keyboard.add(telebot.types.InlineKeyboardButton(
                text=backup['display'][:50],
                callback_data=f"backup_restore_file_{backup['file']}"
            ))
    
    if for_restore:
        text += "\nНажмите на бэкап для восстановления"
        keyboard.add(telebot.types.InlineKeyboardButton("↩️ Назад", callback_data="backup_restore_menu"))
    else:
        keyboard.add(telebot.types.InlineKeyboardButton("↩️ Назад", callback_data="admin_backups"))
    
    bot.send_message(
        chat_id,
        text,
        parse_mode="Markdown"
    )
    
    if for_restore:
        bot.send_message(
            chat_id,
            "Выберите бэкап для восстановления:",
            reply_markup=keyboard
        )

def confirm_restore(chat_id, backup_file):
    """Подтверждение восстановления из бэкапа"""
    try:
        with open(backup_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        timestamp = data.get('timestamp', 'unknown')
        backup_data = data.get('data', {})
        
        active = len(backup_data.get('active_orders', {}))
        completed = len(backup_data.get('completed_orders', {}))
        
        text = (
            f"⚠️ *ВНИМАНИЕ!* Восстановление из бэкапа ЗАМЕНИТ все текущие данные:\n\n"
            f"📁 Бэкап от: {timestamp}\n\n"
            f"Текущие данные:\n"
            f"• Активных заказов: {len(active_orders)} → станет: {active}\n"
            f"• Завершенных заказов: {len(completed_orders)} → станет: {completed}\n\n"
            f"История сообщений будет ПОЛНОСТЬЮ ЗАМЕНЕНА.\n\n"
            f"Это действие необратимо без создания нового бэкапа.\n\n"
            f"Продолжить?"
        )
        
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.row(
            telebot.types.InlineKeyboardButton("✅ Да, восстановить", callback_data=f"backup_do_restore_{backup_file}"),
            telebot.types.InlineKeyboardButton("❌ Отмена", callback_data="admin_backups")
        )
        
        bot.send_message(
            chat_id,
            text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        
    except Exception as e:
        bot.send_message(
            chat_id,
            f"❌ Ошибка чтения бэкапа: {str(e)}"
        )

# ====== ОБРАБОТЧИК ФАЙЛОВ ======

@bot.message_handler(content_types=['document'])
def handle_document(message):
    """Обработка загруженных файлов (для бэкапов)"""
    user_id = message.from_user.id
    
    # Проверяем, что админ и ожидает файл
    if not is_admin(user_id) or user_data.get(user_id, {}).get('state') != 'waiting_for_backup_file':
        bot.send_message(user_id, "❌ Сейчас не ожидается загрузка файла")
        return
    
    file_info = bot.get_file(message.document.file_id)
    
    if not file_info.file_name.endswith('.json'):
        bot.send_message(user_id, "❌ Неверный формат. Ожидается JSON-файл")
        return
    
    # Скачиваем файл
    downloaded_file = bot.download_file(file_info.file_path)
    temp_file = f"{BACKUP_DIR}/uploaded_{int(time.time())}.json"
    
    try:
        with open(temp_file, 'wb') as f:
            f.write(downloaded_file)
        
        # Проверяем, что это валидный бэкап
        with open(temp_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if 'timestamp' not in data or 'data' not in data:
            bot.send_message(user_id, "❌ Файл не является корректным бэкапом бота")
            os.remove(temp_file)
            return
        
        timestamp = data.get('timestamp', 'unknown')
        backup_data = data.get('data', {})
        
        active = len(backup_data.get('active_orders', {}))
        completed = len(backup_data.get('completed_orders', {}))
        
        text = (
            f"✅ *Файл успешно загружен!*\n\n"
            f"📁 Файл: {message.document.file_name}\n"
            f"📅 Дата бэкапа: {timestamp}\n\n"
            f"Содержит:\n"
            f"• Активных заказов: {active}\n"
            f"• Завершенных заказов: {completed}\n\n"
            f"Текущие данные будут ЗАМЕНЕНЫ на данные из этого бэкапа."
        )
        
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.row(
            telebot.types.InlineKeyboardButton("✅ Восстановить", callback_data=f"backup_do_restore_{temp_file}"),
            telebot.types.InlineKeyboardButton("❌ Отмена", callback_data="admin_backups")
        )
        
        bot.send_message(
            user_id,
            text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        
        # Очищаем состояние
        if user_id in user_data:
            del user_data[user_id]
        
    except Exception as e:
        bot.send_message(
            user_id,
            f"❌ Ошибка загрузки файла: {str(e)}\n\nУбедитесь, что это корректный JSON-файл, созданный ботом."
        )
        if os.path.exists(temp_file):
            os.remove(temp_file)

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
    return '🤖 Бот для DP SBOR работает'

# ====== ЗАПУСК ======

if __name__ == '__main__':
    # Удаляем старый вебхук
    bot.remove_webhook()
    
    # Устанавливаем новый
    service_name = os.environ.get('RENDER_SERVICE_NAME', 'dp-sbor')
    webhook_url = f'https://{service_name}.onrender.com/webhook'
    
    bot.set_webhook(url=webhook_url)
    print(f"✅ Вебхук установлен: {webhook_url}")
    
    # Создаем папку для бэкапов
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        print(f"📁 Создана папка для бэкапов: {BACKUP_DIR}")
    
    # Запускаем Flask
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
