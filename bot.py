import os
import telebot
from flask import Flask, request
from datetime import datetime, timedelta, timezone
import json
import time
import threading
from collections import defaultdict
import shutil

# ====== НАСТРОЙКИ ЧАСОВОГО ПОЯСА ======
# МСК время (UTC+3) -> Новосибирск (UTC+7)
MSK_OFFSET = 3
NOVOSIBIRSK_OFFSET = 7
TOTAL_OFFSET = NOVOSIBIRSK_OFFSET - MSK_OFFSET  # +4 часа к серверному времени

def get_novosibirsk_time():
    """Возвращает текущее время в Новосибирске (UTC+7)"""
    utc_time = datetime.now(timezone.utc)
    novosibirsk_time = utc_time + timedelta(hours=NOVOSIBIRSK_OFFSET)
    return novosibirsk_time

def format_time(dt=None):
    """Форматирует время в локальный формат"""
    if dt is None:
        dt = get_novosibirsk_time()
    if isinstance(dt, str):
        return dt
    return dt.strftime("%d.%m.%Y %H:%M")

def format_date(dt=None):
    """Форматирует только дату"""
    if dt is None:
        dt = get_novosibirsk_time()
    if isinstance(dt, str):
        return dt
    return dt.strftime("%d.%m.%Y")

def format_time_only(dt=None):
    """Форматирует только время"""
    if dt is None:
        dt = get_novosibirsk_time()
    if isinstance(dt, str):
        return dt
    return dt.strftime("%H:%M")

# ====== НАСТРОЙКИ ======
TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не установлен!")
    exit(1)

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Имя файла для хранения данных
DATA_FILE = 'bot_data.json'

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
seller_counters = {}  # Счетчики заказов для каждого продавца {seller_name: counter}
active_orders = {}  # Активные заказы {seller_name: {order_number: order_data}}
completed_orders = {}  # Завершенные заказы {seller_name: {order_number: order_data}}
active_chats = {}   # Активные чаты {buyer_id: (seller_name, order_number)}
seller_waiting_for_order_update = {}  # Ожидание уточнения заказа {seller_id: (seller_name, order_number)}
admin_blocked_orders = {}  # Заказы, заблокированные админом {seller_name: {order_number: True}}
admin_chats = {}  # Чаты с админом {buyer_id: admin_chat_data}
admin_chat_counter = 0  # Счетчик сообщений админу
seller_ratings = {}  # Рейтинги продавцов {seller_name: {'total': 0, 'count': 0, 'avg': 0}}

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
        'seller_ratings': seller_ratings,
        'admin_chat_counter': admin_chat_counter
    }
    
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ Данные сохранены")
    except Exception as e:
        print(f"❌ Ошибка сохранения данных: {e}")

def load_data():
    """Загружаем данные из файла"""
    global seller_counters, active_orders, completed_orders, active_chats, admin_chat_counter, seller_ratings
    
    if not os.path.exists(DATA_FILE):
        print("📁 Файл данных не найден, начинаем с нуля")
        # Инициализируем счетчики для всех продавцов
        for seller_name in pickup_points.values():
            seller_counters[seller_name] = 0
            active_orders[seller_name] = {}
            completed_orders[seller_name] = {}
        return
    
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        seller_counters = data.get('seller_counters', {})
        active_orders = data.get('active_orders', {})
        completed_orders = data.get('completed_orders', {})
        seller_ratings = data.get('seller_ratings', {})
        admin_chat_counter = data.get('admin_chat_counter', 0)
        
        # Восстанавливаем активные чаты
        active_chats = {}
        for seller_name, orders in active_orders.items():
            for order_num, order in orders.items():
                if 'buyer_id' in order:
                    buyer_id = int(order['buyer_id']) if isinstance(order['buyer_id'], str) else order['buyer_id']
                    active_chats[buyer_id] = (seller_name, order_num)
        
        print(f"✅ Данные загружены")
        print(f"📊 Счетчики продавцов: {seller_counters}")
        
    except Exception as e:
        print(f"❌ Ошибка загрузки данных: {e}")
        # Инициализируем счетчики для всех продавцов
        for seller_name in pickup_points.values():
            seller_counters[seller_name] = 0
            active_orders[seller_name] = {}
            completed_orders[seller_name] = {}

# Загружаем данные при старте
load_data()

# ====== ФУНКЦИИ ДЛЯ РАБОТЫ С ЗАКАЗАМИ ======
def generate_order_number(seller_name):
    """Генерирует новый номер заказа для продавца"""
    global seller_counters
    if seller_name not in seller_counters:
        seller_counters[seller_name] = 0
    seller_counters[seller_name] += 1
    return seller_counters[seller_name]

def get_order_full_id(seller_name, order_number):
    """Возвращает строковое представление заказа"""
    return f"{seller_name}_{order_number}"

def parse_order_full_id(full_id):
    """Парсит строку вида 'Александр_3' в (seller_name, order_number)"""
    try:
        parts = full_id.split('_')
        seller_name = parts[0]
        order_number = int(parts[1])
        return seller_name, order_number
    except:
        return None, None

def add_active_order(seller_name, order_data):
    """Добавляет заказ в активные"""
    if seller_name not in active_orders:
        active_orders[seller_name] = {}
    order_number = order_data['order_number']
    active_orders[seller_name][order_number] = order_data
    active_chats[order_data['buyer_id']] = (seller_name, order_number)

def move_to_completed(seller_name, order_number):
    """Перемещает заказ из активных в завершенные"""
    if seller_name in active_orders and order_number in active_orders[seller_name]:
        order = active_orders[seller_name].pop(order_number)
        order['completed_at'] = format_time()
        
        if seller_name not in completed_orders:
            completed_orders[seller_name] = {}
        completed_orders[seller_name][order_number] = order
        
        # Удаляем из активных чатов
        if order['buyer_id'] in active_chats:
            del active_chats[order['buyer_id']]
        
        return order
    return None

def is_order_blocked(seller_name, order_number):
    """Проверяет, заблокирован ли заказ админом"""
    return (seller_name in admin_blocked_orders and 
            order_number in admin_blocked_orders[seller_name])

def block_order(seller_name, order_number):
    """Блокирует заказ для продавца"""
    if seller_name not in admin_blocked_orders:
        admin_blocked_orders[seller_name] = {}
    admin_blocked_orders[seller_name][order_number] = True

def unblock_order(seller_name, order_number):
    """Разблокирует заказ для продавца"""
    if seller_name in admin_blocked_orders and order_number in admin_blocked_orders[seller_name]:
        del admin_blocked_orders[seller_name][order_number]
        if not admin_blocked_orders[seller_name]:
            del admin_blocked_orders[seller_name]

# ====== ФУНКЦИИ БЭКАПА ======
def create_backup(backup_type="Авто"):
    """Создает бэкап данных и отправляет админу"""
    if not ADMIN_ID:
        return
    
    try:
        if os.path.exists(DATA_FILE):
            timestamp = get_novosibirsk_time().strftime("%Y%m%d_%H%M%S")
            backup_name = f"backup_{timestamp}.json"
            
            # Копируем файл
            shutil.copy2(DATA_FILE, backup_name)
            
            with open(backup_name, 'rb') as f:
                bot.send_document(
                    ADMIN_ID,
                    f,
                    caption=f"💾 {backup_type} бэкап {format_time()}"
                )
            
            # Удаляем временную копию
            os.remove(backup_name)
            print(f"✅ {backup_type} бэкап создан и отправлен")
    except Exception as e:
        print(f"❌ Ошибка создания бэкапа: {e}")

# ====== ФУНКЦИИ ДЛЯ ПРОВЕРКИ ПРАВ ======
def is_admin(user_id):
    return ADMIN_ID is not None and user_id == ADMIN_ID

def is_seller(user_id):
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

def get_seller_active_orders(seller_id):
    seller_name = get_seller_name_by_id(seller_id)
    if seller_name and seller_name in active_orders:
        return list(active_orders[seller_name].keys())
    return []

def get_buyer_link(buyer_id, buyer_name):
    return f"tg://user?id={buyer_id}"

# ====== ФУНКЦИИ ДЛЯ ИНТЕРФЕЙСА ======
def show_instruction_with_keyboard(chat_id):
    """Показать инструкцию с клавиатурой"""
    user_id = chat_id
    
    main_keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    main_keyboard.row('📋 Каталог с ценами', 'ℹ️ О нас')
    
    if is_seller(user_id):
        main_keyboard.row('📋 Мои заказы')
    else:
        # Для покупателей добавляем дополнительные кнопки
        main_keyboard.row('📋 Мои заказы', '👤 Связаться с админом')
    
    instruction_text = (
        "🟢 *Пошаговая инструкция:*\n\n"
        "1. Напишите, что хотите заказать\n"
        "2. Выберите откуда удобнее забрать\n"
        "3. Менеджер свяжется с вами"
    )
    
    bot.send_message(
        chat_id,
        instruction_text,
        parse_mode="Markdown",
        reply_markup=main_keyboard
    )

def show_admin_panel(chat_id):
    """Показать панель администратора"""
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row('📋 Активные заказы', '❌ Проблемные заказы')
    keyboard.row('📦 Завершенные заказы', '📊 Статистика')
    keyboard.row('💾 Создать бэкап', '📤 Восстановить из бэкапа')
    keyboard.row('📬 Новые сообщения', '🏠 Главное меню')
    
    bot.send_message(
        chat_id,
        "👑 *Панель администратора*\n\n"
        "Выберите действие:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# ====== ОБРАБОТЧИКИ КОМАНД ======
@bot.message_handler(commands=['start'])
def send_welcome(message):
    show_instruction_with_keyboard(message.chat.id)

@bot.message_handler(commands=['admin'])
def admin_command(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.from_user.id, "❌ У вас нет прав администратора")
        return
    show_admin_panel(message.from_user.id)

# ====== ОБРАБОТЧИКИ ТЕКСТА ======
@bot.message_handler(func=lambda message: message.text == '📋 Каталог с ценами')
def send_catalog(message):
    catalog_text = (
        "📋 *Каталог с ценами*\n\n"
        "1. *Грецкий орех очищенный*, 500г - 400 ₽\n"
        "2. *Миндаль золотой*, 1000г - 950 ₽\n"
        "3. *Кешью WW320*, 1000г - 1000 ₽\n"
        "4. *Манго сушеное*, 500г - 250 ₽\n"
        "5. *Клубника сушеная*, 500г - 350 ₽\n"
        "6. *Фисташки иранские*, 500г - 600 ₽\n\n"
        "*Для заказа напишите что Вам нужно*"
    )
    bot.send_message(message.chat.id, catalog_text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == 'ℹ️ О нас')
def send_about(message):
    about_text = (
        "🏢 *О нашей компании*\n\n"
        "*DP SBOR | Отборные орехи и сухофрукты • Новосибирск*\n"
        "Мы выбираем продукты по качеству, вкусу и внешнему виду, а не по минимальной цене\n\n"
        "Всё, начиная от выбора товара, заканчивая фасовкой и упаковкой проходит жесткий контроль\n\n"
        "*Вы гарантированно получаете высшее качество по шикарным ценам*\n\n"
        "📍 На данный момент есть 5 точек *в Новосибирске*, где можно забрать заказ\n\n"
        "*Наш канал: t.me/dp_sbor*"
    )
    bot.send_message(message.chat.id, about_text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == '📋 Мои заказы')
def my_orders(message):
    user_id = message.from_user.id
    
    if is_seller(user_id):
        # Для продавца - его активные заказы
        seller_name = get_seller_name_by_id(user_id)
        if seller_name and seller_name in active_orders and active_orders[seller_name]:
            keyboard = telebot.types.InlineKeyboardMarkup()
            for order_num in sorted(active_orders[seller_name].keys()):
                order = active_orders[seller_name][order_num]
                keyboard.row(
                    telebot.types.InlineKeyboardButton(
                        f"Заказ {seller_name}_{order_num} - {order['buyer_name']}",
                        callback_data=f"view_order_{seller_name}_{order_num}"
                    )
                )
            bot.send_message(
                user_id,
                "📋 *Ваши активные заказы*",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        else:
            bot.send_message(user_id, "📭 У вас нет активных заказов")
    
    else:
        # Для покупателя - история его заказов (шаблоны)
        buyer_orders = []
        for seller_name, orders in completed_orders.items():
            for order_num, order in orders.items():
                if order.get('buyer_id') == user_id:
                    buyer_orders.append(order)
        
        # Также добавляем активные заказы
        if user_id in active_chats:
            seller_name, order_num = active_chats[user_id]
            if seller_name in active_orders and order_num in active_orders[seller_name]:
                buyer_orders.append(active_orders[seller_name][order_num])
        
        if buyer_orders:
            # Сортируем по дате (последние сверху)
            buyer_orders.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            keyboard = telebot.types.InlineKeyboardMarkup()
            for order in buyer_orders[:5]:  # Последние 5
                order_text = order['order_text'][:30] + "..." if len(order['order_text']) > 30 else order['order_text']
                keyboard.row(
                    telebot.types.InlineKeyboardButton(
                        f"🔄 {order['timestamp']}: {order_text}",
                        callback_data=f"repeat_order_{order['seller_name']}_{order['order_number']}"
                    )
                )
            
            bot.send_message(
                user_id,
                "📋 *Ваши последние заказы*\n\nНажмите на заказ, чтобы повторить",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        else:
            bot.send_message(user_id, "📭 У вас пока нет заказов")

@bot.message_handler(func=lambda message: message.text == '👤 Связаться с админом')
def contact_admin(message):
    user_id = message.from_user.id
    
    # Проверяем, есть ли незавершенный диалог
    if user_id in admin_chats and not admin_chats[user_id].get('completed', False):
        chat_data = admin_chats[user_id]
        
        # Показываем историю диалога
        history = "👤 *ВАШ ДИАЛОГ С АДМИНИСТРАТОРОМ*\n"
        history += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for msg in chat_data.get('messages', []):
            sender = "👤 Вы" if msg['sender'] == 'user' else "👨‍💼 Администратор"
            history += f"{sender} ({msg['time']}):\n{msg['text']}\n\n"
        
        bot.send_message(user_id, history, parse_mode="Markdown")
    
    # Показываем поле для ввода
    msg_text = (
        "👤 *СВЯЗЬ С АДМИНИСТРАТОРОМ*\n\n"
        "Вы можете сообщить о проблемах, ошибках или задать вопросы по работе сервиса.\n\n"
        "Напишите ваше сообщение:"
    )
    
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row('🔄 Вернуться к оформлению заказа')
    
    bot.send_message(
        user_id,
        msg_text,
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    # Регистрируем следующий шаг
    bot.register_next_step_handler(message, process_admin_message)

def process_admin_message(message):
    """Обработка сообщения для админа"""
    user_id = message.from_user.id
    
    if message.text == '🔄 Вернуться к оформлению заказа':
        show_instruction_with_keyboard(user_id)
        return
    
    # Создаем или обновляем чат
    if user_id not in admin_chats:
        global admin_chat_counter
        admin_chat_counter += 1
        admin_chats[user_id] = {
            'chat_id': admin_chat_counter,
            'user_name': message.from_user.first_name or "Покупатель",
            'messages': [],
            'completed': False,
            'created_at': format_time()
        }
    
    # Добавляем сообщение
    admin_chats[user_id]['messages'].append({
        'sender': 'user',
        'text': message.text,
        'time': format_time_only()
    })
    admin_chats[user_id]['completed'] = False
    
    # Сохраняем данные
    save_data()
    
    # Удаляем предыдущее служебное сообщение, если есть
    try:
        bot.delete_message(user_id, message.message_id - 1)
    except:
        pass
    
    # Отправляем подтверждение с обновленным дизайном
    confirm_text = (
        "✅ Сообщение отправлено администратору!\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Вы в любой момент можете вернуться к диалогу.\n"
        "Просто нажмите в меню кнопку \"👤 Связь с админом\"\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row('📝 Написать сообщение администратору')
    keyboard.row('🔄 Вернуться к оформлению заказа (меню)')
    
    sent_msg = bot.send_message(
        user_id,
        confirm_text,
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    # Уведомляем админа
    if ADMIN_ID:
        buyer_link = get_buyer_link(user_id, admin_chats[user_id]['user_name'])
        admin_msg = (
            f"📩 *НОВОЕ СООБЩЕНИЕ #{admin_chats[user_id]['chat_id']}*\n"
            f"👤 {admin_chats[user_id]['user_name']}\n"
            f"💬 [Связаться с покупателем]({buyer_link})\n"
            f"📅 {format_time()}\n\n"
            f"*Текст:*\n{message.text}"
        )
        
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.row(
            telebot.types.InlineKeyboardButton("👀 Посмотреть", callback_data=f"view_admin_chat_{user_id}"),
            telebot.types.InlineKeyboardButton("✅ Завершить", callback_data=f"complete_admin_chat_{user_id}")
        )
        
        bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown", reply_markup=keyboard)
        
        # Создаем бэкап при новом сообщении
        create_backup("По сообщению")

@bot.message_handler(func=lambda message: message.text == '📝 Написать сообщение администратору')
def write_to_admin(message):
    user_id = message.from_user.id
    contact_admin(message)

@bot.message_handler(func=lambda message: message.text == '🔄 Вернуться к оформлению заказа (меню)')
def back_to_order_menu(message):
    show_instruction_with_keyboard(message.chat.id)

@bot.message_handler(func=lambda message: message.text == '🔄 Вернуться к оформлению заказа')
def back_to_order(message):
    show_instruction_with_keyboard(message.chat.id)

# ====== АДМИН-ПАНЕЛЬ ======
@bot.message_handler(func=lambda message: message.text == '📋 Активные заказы')
def admin_active_orders(message):
    if not is_admin(message.from_user.id):
        return
    
    has_orders = False
    for seller_name, orders in active_orders.items():
        if orders:
            has_orders = True
            for order_num, order in sorted(orders.items()):
                buyer_link = get_buyer_link(order['buyer_id'], order['buyer_name'])
                order_info = (
                    f"📦 *Заказ {seller_name}_{order_num}*\n"
                    f"📅 {order['timestamp']}\n"
                    f"👤 Покупатель: {order['buyer_name']}\n"
                    f"💬 [Связаться]({buyer_link})\n"
                    f"📍 {order['address']}\n"
                    f"📝 {order['order_text']}"
                )
                
                keyboard = telebot.types.InlineKeyboardMarkup()
                keyboard.row(
                    telebot.types.InlineKeyboardButton(
                        "👀 Посмотреть чат", 
                        callback_data=f"view_order_{seller_name}_{order_num}"
                    )
                )
                
                bot.send_message(
                    message.from_user.id,
                    order_info,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
    
    if not has_orders:
        bot.send_message(message.from_user.id, "📭 Нет активных заказов")

@bot.message_handler(func=lambda message: message.text == '❌ Проблемные заказы')
def admin_problem_orders(message):
    if not is_admin(message.from_user.id):
        return
    
    problem_orders = []
    for seller_name, orders in active_orders.items():
        for order_num, order in orders.items():
            if not order.get('delivered_to_seller', True):
                problem_orders.append((seller_name, order_num, order, 'seller'))
            if not order.get('delivered_to_admin', True):
                problem_orders.append((seller_name, order_num, order, 'admin'))
    
    if not problem_orders:
        bot.send_message(message.from_user.id, "✅ Проблемных заказов нет")
        return
    
    bot.send_message(
        message.from_user.id,
        f"❌ *ПРОБЛЕМНЫЕ ЗАКАЗЫ ({len(problem_orders)})*",
        parse_mode="Markdown"
    )
    
    for seller_name, order_num, order, target in problem_orders:
        buyer_link = get_buyer_link(order['buyer_id'], order['buyer_name'])
        problem_info = (
            f"⚠️ *{seller_name}_{order_num}*\n"
            f"👤 {order['buyer_name']} 💬 [Связаться]({buyer_link})\n"
            f"📝 {order['order_text'][:50]}...\n"
            f"❌ Не доставлен: {'продавцу' if target == 'seller' else 'админу'}\n"
            f"🔄 Попыток: {order.get('delivery_attempts', 0)}"
        )
        
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.row(
            telebot.types.InlineKeyboardButton(
                f"🔄 Переотправить {'продавцу' if target == 'seller' else 'админу'}",
                callback_data=f"retry_delivery_{seller_name}_{order_num}_{target}"
            )
        )
        
        bot.send_message(
            message.from_user.id,
            problem_info,
            parse_mode="Markdown",
            reply_markup=keyboard
        )

@bot.message_handler(func=lambda message: message.text == '📦 Завершенные заказы')
def admin_completed_orders(message):
    if not is_admin(message.from_user.id):
        return
    
    has_completed = False
    keyboard = telebot.types.InlineKeyboardMarkup()
    
    for seller_name, orders in completed_orders.items():
        for order_num in sorted(orders.keys(), reverse=True)[:5]:  # Последние 5
            order = orders[order_num]
            has_completed = True
            keyboard.row(
                telebot.types.InlineKeyboardButton(
                    f"✅ {seller_name}_{order_num} - {order['buyer_name']} - {order['timestamp']}",
                    callback_data=f"view_completed_{seller_name}_{order_num}"
                )
            )
    
    if has_completed:
        bot.send_message(
            message.from_user.id,
            "📦 *Завершенные заказы (последние)*\n\nВыберите для просмотра:",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    else:
        bot.send_message(message.from_user.id, "📭 Нет завершенных заказов")

@bot.message_handler(func=lambda message: message.text == '📊 Статистика')
def admin_statistics(message):
    if not is_admin(message.from_user.id):
        return
    
    # Общая статистика
    total_active = sum(len(orders) for orders in active_orders.values())
    total_completed = sum(len(orders) for orders in completed_orders.values())
    
    # Проблемные заказы
    problem_count = 0
    for seller_name, orders in active_orders.items():
        for order in orders.values():
            if not order.get('delivered_to_seller', True):
                problem_count += 1
    
    # Статистика по продавцам
    seller_stats = []
    for seller_name in pickup_points.values():
        active = len(active_orders.get(seller_name, {}))
        completed = len(completed_orders.get(seller_name, {}))
        problematic = 0
        for order in active_orders.get(seller_name, {}).values():
            if not order.get('delivered_to_seller', True):
                problematic += 1
        
        rating = seller_ratings.get(seller_name, {}).get('avg', 0)
        
        seller_stats.append({
            'name': seller_name,
            'active': active,
            'problematic': problematic,
            'completed': completed,
            'rating': rating
        })
    
    # Формируем отчет
    report = "📊 *СТАТИСТИКА*\n"
    report += "━━━━━━━━━━━━━\n\n"
    report += f"🔥 *ОБЩЕЕ:*\n"
    report += f"✅ Активных заказов: {total_active}\n"
    report += f"⚠️ Проблемных заказов: {problem_count}\n"
    report += f"📦 Завершено всего: {total_completed}\n\n"
    
    report += "👥 *ПО ПРОДАВЦАМ:*\n"
    for stat in seller_stats:
        report += f"• {stat['name']}: {stat['active']} актив, {stat['problematic']} проблем, {stat['completed']} заверш"
        if stat['rating'] > 0:
            report += f", ⭐ {stat['rating']:.1f}"
        report += "\n"
    
    # Динамика за последние 7 дней
    report += "\n📈 *ДИНАМИКА ЗА НЕДЕЛЮ:*\n"
    today = get_novosibirsk_time()
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        date_str = date.strftime("%d.%m")
        # Здесь можно добавить реальную статистику по дням
        report += f"• {date_str}: Данные собираются...\n"
    
    # Популярные товары
    report += "\n🔥 *ПОПУЛЯРНЫЕ ТОВАРЫ:*\n"
    report += "1. Клубника сушеная - данные собираются\n"
    report += "2. Миндаль золотой - данные собираются\n"
    report += "3. Грецкий орех - данные собираются\n"
    
    bot.send_message(message.from_user.id, report, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == '💾 Создать бэкап')
def admin_create_backup(message):
    if not is_admin(message.from_user.id):
        return
    
    bot.send_message(message.from_user.id, "⏳ Создаю бэкап...")
    create_backup("Ручной")
    bot.send_message(message.from_user.id, "✅ Бэкап создан и отправлен")

@bot.message_handler(func=lambda message: message.text == '📤 Восстановить из бэкапа')
def admin_restore_prompt(message):
    if not is_admin(message.from_user.id):
        return
    
    bot.send_message(
        message.from_user.id,
        "📤 Отправьте файл бэкапа (backup_*.json) для восстановления"
    )
    bot.register_next_step_handler(message, process_restore)

def process_restore(message):
    if not message.document:
        bot.send_message(message.chat.id, "❌ Это не файл")
        return
    
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Сохраняем временный файл
        temp_file = 'temp_restore.json'
        with open(temp_file, 'wb') as f:
            f.write(downloaded_file)
        
        # Проверяем, что это валидный JSON
        with open(temp_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Восстанавливаем данные
        global seller_counters, active_orders, completed_orders, active_chats, admin_chat_counter, seller_ratings
        
        seller_counters = data.get('seller_counters', {})
        active_orders = data.get('active_orders', {})
        completed_orders = data.get('completed_orders', {})
        seller_ratings = data.get('seller_ratings', {})
        admin_chat_counter = data.get('admin_chat_counter', 0)
        
        # Восстанавливаем активные чаты
        active_chats = {}
        for seller_name, orders in active_orders.items():
            for order_num, order in orders.items():
                if 'buyer_id' in order:
                    buyer_id = int(order['buyer_id']) if isinstance(order['buyer_id'], str) else order['buyer_id']
                    active_chats[buyer_id] = (seller_name, order_num)
        
        # Сохраняем восстановленные данные
        os.remove(temp_file)
        save_data()
        
        bot.send_message(
            message.chat.id,
            f"✅ Данные восстановлены!\n"
            f"📦 Активных заказов: {sum(len(o) for o in active_orders.values())}\n"
            f"📦 Завершенных заказов: {sum(len(o) for o in completed_orders.values())}"
        )
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка восстановления: {e}")

@bot.message_handler(func=lambda message: message.text == '📬 Новые сообщения')
def admin_new_messages(message):
    if not is_admin(message.from_user.id):
        return
    
    active_chats_list = []
    for user_id, chat_data in admin_chats.items():
        if not chat_data.get('completed', False):
            active_chats_list.append((user_id, chat_data))
    
    if not active_chats_list:
        bot.send_message(message.from_user.id, "📭 Нет новых сообщений")
        return
    
    bot.send_message(
        message.from_user.id,
        f"📬 *НОВЫЕ СООБЩЕНИЯ ({len(active_chats_list)})*",
        parse_mode="Markdown"
    )
    
    for user_id, chat_data in active_chats_list:
        buyer_link = get_buyer_link(user_id, chat_data['user_name'])
        last_msg = chat_data['messages'][-1] if chat_data['messages'] else {'text': '', 'time': ''}
        
        msg_info = (
            f"📩 *#{chat_data['chat_id']} {chat_data['user_name']}*\n"
            f"💬 [Связаться]({buyer_link})\n"
            f"🕐 {last_msg['time']}\n"
            f"📝 {last_msg['text'][:50]}...\n"
        )
        
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.row(
            telebot.types.InlineKeyboardButton("👀 Посмотреть", callback_data=f"view_admin_chat_{user_id}"),
            telebot.types.InlineKeyboardButton("✅ Завершить", callback_data=f"complete_admin_chat_{user_id}")
        )
        
        bot.send_message(
            message.from_user.id,
            msg_info,
            parse_mode="Markdown",
            reply_markup=keyboard
        )

@bot.message_handler(func=lambda message: message.text == '🏠 Главное меню')
def back_to_main_menu(message):
    show_instruction_with_keyboard(message.chat.id)

# ====== ОБРАБОТЧИКИ СООБЩЕНИЙ ======
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Пропускаем команды меню
    menu_commands = [
        '📋 Каталог с ценами', 'ℹ️ О нас', '📋 Мои заказы', '👤 Связаться с админом',
        '🔄 Вернуться к оформлению заказа', '📋 Активные заказы', '❌ Проблемные заказы',
        '📦 Завершенные заказы', '📊 Статистика', '💾 Создать бэкап', '📤 Восстановить из бэкапа',
        '📬 Новые сообщения', '🏠 Главное меню', '📝 Написать сообщение администратору',
        '🔄 Вернуться к оформлению заказа (меню)'
    ]
    if text in menu_commands:
        return
    
    # --- АДМИНИСТРАТОР ---
    if is_admin(user_id):
        # Админ может отвечать на любой заказ через seller_name_number
        if '_' in text and text.split('_')[0] in pickup_points.values():
            try:
                seller_name, rest = text.split('_', 1)
                parts = rest.split(' ', 1)
                order_num = int(parts[0])
                message_text = parts[1] if len(parts) > 1 else ""
                
                if not message_text:
                    bot.send_message(user_id, "❌ Не указан текст сообщения")
                    return
                
                if (seller_name in active_orders and 
                    order_num in active_orders[seller_name]):
                    
                    order = active_orders[seller_name][order_num]
                    
                    # Отправляем сообщение покупателю (инкогнито)
                    bot.send_message(
                        order['buyer_id'],
                        f"💬 *Сообщение от менеджера:*\n\n{message_text}",
                        parse_mode="Markdown"
                    )
                    
                    bot.send_message(
                        user_id,
                        f"✅ Сообщение отправлено покупателю ({seller_name}_{order_num})"
                    )
                    
                    # Если админ подключен к заказу, уведомляем
                    if is_order_blocked(seller_name, order_num):
                        bot.send_message(
                            get_seller_id(seller_name),
                            f"👑 Администратор отправил сообщение по заказу {seller_name}_{order_num}"
                        )
                else:
                    bot.send_message(user_id, f"❌ Заказ {seller_name}_{order_num} не найден")
                    
            except Exception as e:
                bot.send_message(user_id, f"❌ Ошибка: {str(e)[:100]}")
        else:
            show_admin_panel(user_id)
        return
    
    # --- ПРОДАВЕЦ ---
    if is_seller(user_id):
        seller_name = get_seller_name_by_id(user_id)
        
        # Проверяем, ожидаем ли мы уточнение заказа
        if user_id in seller_waiting_for_order_update:
            seller_name_wait, order_num = seller_waiting_for_order_update[user_id]
            if seller_name_wait in active_orders and order_num in active_orders[seller_name_wait]:
                
                # Проверяем, не заблокирован ли заказ админом
                if is_order_blocked(seller_name_wait, order_num):
                    bot.send_message(
                        user_id,
                        f"❌ Заказ {seller_name_wait}_{order_num} заблокирован администратором"
                    )
                    del seller_waiting_for_order_update[user_id]
                    return
                
                order = active_orders[seller_name_wait][order_num]
                old_text = order['order_text']
                order['order_text'] = text
                order['updated_at'] = format_date()
                order['delivered_to_seller'] = True
                
                save_data()
                
                # Отправляем подтверждение продавцу
                seller_keyboard = telebot.types.InlineKeyboardMarkup()
                seller_keyboard.row(
                    telebot.types.InlineKeyboardButton("✏️ Уточнить заказ", callback_data=f"seller_update_{seller_name_wait}_{order_num}"),
                    telebot.types.InlineKeyboardButton("✅ Завершить заказ", callback_data=f"seller_close_{seller_name_wait}_{order_num}")
                )
                
                bot.send_message(
                    user_id,
                    f"✅ *Заказ {seller_name_wait}_{order_num} обновлен!*\n\n"
                    f"📝 *Актуальный заказ:* {text}",
                    parse_mode="Markdown",
                    reply_markup=seller_keyboard
                )
                
                # Уведомляем покупателя
                bot.send_message(
                    order['buyer_id'],
                    f"📝 *Уточненный заказ:*\n\n{text}",
                    parse_mode="Markdown"
                )
                
                # Уведомляем админа
                if ADMIN_ID:
                    buyer_link = get_buyer_link(order['buyer_id'], order['buyer_name'])
                    bot.send_message(
                        ADMIN_ID,
                        f"👑 *Заказ {seller_name_wait}_{order_num} обновлен*\n\n"
                        f"👤 Продавец: {seller_name_wait}\n"
                        f"👤 Покупатель: {order['buyer_name']} 💬 [Связаться]({buyer_link})\n"
                        f"📝 Было: {old_text[:50]}...\n"
                        f"📝 Стало: {text[:50]}...",
                        parse_mode="Markdown"
                    )
                
                del seller_waiting_for_order_update[user_id]
                return
        
        # Обработка ответов на заказы
        if '_' in text:
            try:
                parts = text.split(' ', 1)
                full_id = parts[0]
                message_text = parts[1] if len(parts) > 1 else ""
                
                s_name, order_num = parse_order_full_id(full_id)
                
                if not s_name or not order_num:
                    bot.send_message(user_id, "❌ Неверный формат. Используйте: Продавец_Номер текст")
                    return
                
                if s_name != seller_name:
                    bot.send_message(user_id, f"❌ Это не ваш заказ")
                    return
                
                if (s_name in active_orders and 
                    order_num in active_orders[s_name]):
                    
                    # Проверяем блокировку
                    if is_order_blocked(s_name, order_num):
                        bot.send_message(
                            user_id,
                            f"❌ Заказ {full_id} заблокирован администратором"
                        )
                        return
                    
                    order = active_orders[s_name][order_num]
                    
                    # Отправляем сообщение покупателю
                    bot.send_message(
                        order['buyer_id'],
                        f"💬 *Сообщение от менеджера:*\n\n{message_text}",
                        parse_mode="Markdown"
                    )
                    
                    bot.send_message(user_id, f"✅ Сообщение отправлено")
                    
                    # Копируем админу
                    if ADMIN_ID:
                        buyer_link = get_buyer_link(order['buyer_id'], order['buyer_name'])
                        bot.send_message(
                            ADMIN_ID,
                            f"👑 *Сообщение от продавца*\n\n"
                            f"📦 Заказ {full_id}\n"
                            f"👤 Покупатель: {order['buyer_name']} 💬 [Связаться]({buyer_link})\n"
                            f"💬 {message_text}",
                            parse_mode="Markdown"
                        )
                else:
                    bot.send_message(user_id, f"❌ Заказ {full_id} не найден")
                    
            except Exception as e:
                bot.send_message(user_id, f"❌ Ошибка: {str(e)[:100]}")
        else:
            # Показываем активные заказы
            if seller_name in active_orders and active_orders[seller_name]:
                orders_list = '\n'.join([f"• {seller_name}_{oid}" for oid in active_orders[seller_name].keys()])
                bot.send_message(
                    user_id,
                    f"📋 *Ваши активные заказы:*\n\n{orders_list}\n\n"
                    f"💬 Чтобы ответить, напишите: `{seller_name}_номер текст`\n"
                    f"Пример: `{seller_name}_1 Здравствуйте!`"
                )
            else:
                bot.send_message(user_id, "📭 У вас нет активных заказов")
        return
    
    # --- ПОКУПАТЕЛЬ ---
    # Проверяем, есть ли активный чат
    if user_id in active_chats:
        seller_name, order_num = active_chats[user_id]
        
        if seller_name in active_orders and order_num in active_orders[seller_name]:
            order = active_orders[seller_name][order_num]
            
            # Проверяем блокировку
            if is_order_blocked(seller_name, order_num):
                bot.send_message(
                    user_id,
                    "⏳ Ваш заказ временно обрабатывается администратором. Скоро продолжим."
                )
                return
            
            # Отправляем сообщение продавцу
            seller_id = get_seller_id(seller_name)
            if seller_id:
                seller_keyboard = telebot.types.InlineKeyboardMarkup()
                seller_keyboard.row(
                    telebot.types.InlineKeyboardButton("✏️ Уточнить заказ", callback_data=f"seller_update_{seller_name}_{order_num}"),
                    telebot.types.InlineKeyboardButton("✅ Завершить заказ", callback_data=f"seller_close_{seller_name}_{order_num}")
                )
                
                bot.send_message(
                    seller_id,
                    f"📩 *Сообщение от покупателя ({seller_name}_{order_num}):*\n\n"
                    f"👤 {order['buyer_name']}\n"
                    f"💬 {text}",
                    parse_mode="Markdown",
                    reply_markup=seller_keyboard
                )
                
                bot.send_message(user_id, "✅ Сообщение отправлено менеджеру")
                
                # Копируем админу
                if ADMIN_ID:
                    buyer_link = get_buyer_link(user_id, order['buyer_name'])
                    bot.send_message(
                        ADMIN_ID,
                        f"👑 *Сообщение от покупателя*\n\n"
                        f"📦 Заказ {seller_name}_{order_num}\n"
                        f"👤 Покупатель: {order['buyer_name']} 💬 [Связаться]({buyer_link})\n"
                        f"💬 {text}",
                        parse_mode="Markdown"
                    )
            return
        else:
            # Чат недействителен
            if user_id in active_chats:
                del active_chats[user_id]
    
    # --- НОВЫЙ ЗАКАЗ ---
    # Сохраняем данные
    user_data[user_id] = {
        'text': text,
        'name': message.from_user.first_name or "Покупатель",
        'user_id': user_id
    }
    
    # Кнопки выбора адреса
    keyboard = telebot.types.InlineKeyboardMarkup()
    for address in pickup_points.keys():
        keyboard.add(telebot.types.InlineKeyboardButton(text=address, callback_data=address))
    
    bot.send_message(
        user_id,
        "✅ Сообщение получено! Выберите удобный адрес:",
        reply_markup=keyboard
    )

# ====== ОБРАБОТЧИКИ КОЛЛБЭКОВ ======
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    data = call.data
    
    # Просмотр заказа
    if data.startswith('view_order_'):
        parts = data.split('_')
        seller_name = parts[2]
        order_num = int(parts[3])
        
        if seller_name in active_orders and order_num in active_orders[seller_name]:
            order = active_orders[seller_name][order_num]
            
            # Формируем информацию
            buyer_link = get_buyer_link(order['buyer_id'], order['buyer_name'])
            order_info = (
                f"📦 *ЗАКАЗ {seller_name}_{order_num}*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 Покупатель: {order['buyer_name']}\n"
                f"💬 [Связаться]({buyer_link})\n"
                f"📍 {order['address']}\n"
                f"📝 {order['order_text']}\n"
                f"📅 Создан: {order['timestamp']}\n"
            )
            
            if 'updated_at' in order and order['updated_at']:
                order_info += f"🔄 Обновлен: {order['updated_at']}\n"
            
            # История сообщений (упрощенно)
            order_info += "\n📜 *ИСТОРИЯ ЧАТА:*\n"
            order_info += "Здесь будет история сообщений..."
            
            keyboard = telebot.types.InlineKeyboardMarkup()
            if is_admin(user_id):
                if is_order_blocked(seller_name, order_num):
                    keyboard.row(
                        telebot.types.InlineKeyboardButton(
                            "🔌 Отключиться от заказа",
                            callback_data=f"admin_unblock_{seller_name}_{order_num}"
                        )
                    )
                else:
                    keyboard.row(
                        telebot.types.InlineKeyboardButton(
                            "👑 Подключиться к заказу",
                            callback_data=f"admin_block_{seller_name}_{order_num}"
                        )
                    )
            
            bot.send_message(
                user_id,
                order_info,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
    
    # Просмотр завершенного заказа
    elif data.startswith('view_completed_'):
        parts = data.split('_')
        seller_name = parts[2]
        order_num = int(parts[3])
        
        if seller_name in completed_orders and order_num in completed_orders[seller_name]:
            order = completed_orders[seller_name][order_num]
            
            buyer_link = get_buyer_link(order['buyer_id'], order['buyer_name'])
            order_info = (
                f"✅ *ЗАВЕРШЕННЫЙ ЗАКАЗ {seller_name}_{order_num}*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 Покупатель: {order['buyer_name']}\n"
                f"💬 [Связаться]({buyer_link})\n"
                f"📍 {order['address']}\n"
                f"📝 {order['order_text']}\n"
                f"📅 Создан: {order['timestamp']}\n"
                f"✅ Завершен: {order.get('completed_at', 'неизвестно')}\n"
            )
            
            bot.send_message(user_id, order_info, parse_mode="Markdown")
    
    # Повтор заказа
    elif data.startswith('repeat_order_'):
        parts = data.split('_')
        seller_name = parts[2]
        order_num = int(parts[3])
        
        if seller_name in completed_orders and order_num in completed_orders[seller_name]:
            order = completed_orders[seller_name][order_num]
            
            keyboard = telebot.types.InlineKeyboardMarkup()
            keyboard.row(
                telebot.types.InlineKeyboardButton(
                    "✅ Подтвердить",
                    callback_data=f"confirm_repeat_{seller_name}_{order_num}"
                ),
                telebot.types.InlineKeyboardButton(
                    "✏️ Изменить",
                    callback_data=f"edit_repeat_{seller_name}_{order_num}"
                )
            )
            keyboard.row(
                telebot.types.InlineKeyboardButton(
                    "❌ Отмена",
                    callback_data="cancel_repeat"
                )
            )
            
            bot.send_message(
                user_id,
                f"🔄 *Повторить заказ от {order['timestamp']}*\n\n"
                f"📝 {order['order_text']}\n"
                f"📍 Точка: {order['address']}\n\n"
                f"Подтвердите или измените заказ:",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
    
    elif data.startswith('confirm_repeat_'):
        parts = data.split('_')
        seller_name = parts[2]
        order_num = int(parts[3])
        
        if seller_name in completed_orders and order_num in completed_orders[seller_name]:
            old_order = completed_orders[seller_name][order_num]
            
            # Создаем новый заказ
            new_order_num = generate_order_number(seller_name)
            seller_id = get_seller_id(seller_name)
            
            new_order = {
                'order_number': new_order_num,
                'buyer_id': user_id,
                'buyer_name': old_order['buyer_name'],
                'seller_id': seller_id,
                'seller_name': seller_name,
                'address': old_order['address'],
                'order_text': old_order['order_text'],
                'timestamp': format_date(),
                'updated_at': None,
                'status': 'active',
                'delivered_to_seller': False,
                'delivered_to_admin': False,
                'delivery_attempts': 0
            }
            
            add_active_order(seller_name, new_order)
            save_data()
            
            # Уведомляем продавца
            if seller_id:
                seller_message = (
                    f"📦 *НОВЫЙ ЗАКАЗ {seller_name}_{new_order_num}*\n"
                    f"📅 {new_order['timestamp']}\n\n"
                    f"👤 *Покупатель:* {old_order['buyer_name']}\n"
                    f"📍 *Точка:* {old_order['address']}\n"
                    f"📝 *Заказ:* {old_order['order_text']}"
                )
                
                seller_keyboard = telebot.types.InlineKeyboardMarkup()
                seller_keyboard.row(
                    telebot.types.InlineKeyboardButton("✏️ Уточнить заказ", callback_data=f"seller_update_{seller_name}_{new_order_num}"),
                    telebot.types.InlineKeyboardButton("✅ Завершить заказ", callback_data=f"seller_close_{seller_name}_{new_order_num}")
                )
                
                try:
                    bot.send_message(seller_id, seller_message, parse_mode="Markdown", reply_markup=seller_keyboard)
                    new_order['delivered_to_seller'] = True
                except:
                    new_order['delivered_to_seller'] = False
                
                save_data()
            
            # Уведомляем покупателя с обновленным дизайном
            buyer_msg = (
                f"✅ *Заказ повторен!*\n\n"
                f"📍 Адрес: {old_order['address']}\n"
                f"📝 Ваш заказ: {old_order['order_text']}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Вы в любой момент можете вернуться к диалогу.\n"
                f"Просто нажмите в меню кнопку \"👤 Связь с админом\"\n"
                f"━━━━━━━━━━━━━━━━━━━━━━"
            )
            
            buyer_keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
            buyer_keyboard.row('📝 Написать сообщение администратору')
            buyer_keyboard.row('🔄 Вернуться к оформлению заказа (меню)')
            
            bot.send_message(
                user_id,
                buyer_msg,
                parse_mode="Markdown",
                reply_markup=buyer_keyboard
            )
            
            # Создаем бэкап
            create_backup("Новый заказ (повтор)")
    
    elif data == "cancel_repeat":
        bot.edit_message_text(
            "❌ Повтор заказа отменен",
            user_id,
            call.message.message_id
        )
    
    elif data.startswith('edit_repeat_'):
        parts = data.split('_')
        seller_name = parts[2]
        order_num = int(parts[3])
        
        bot.edit_message_text(
            "✏️ Напишите новый текст заказа:",
            user_id,
            call.message.message_id
        )
        # Здесь можно добавить логику редактирования
    
    # Админ: блокировка заказа
    elif data.startswith('admin_block_'):
        parts = data.split('_')
        seller_name = parts[2]
        order_num = int(parts[3])
        
        if seller_name in active_orders and order_num in active_orders[seller_name]:
            block_order(seller_name, order_num)
            
            # Уведомляем продавца
            seller_id = get_seller_id(seller_name)
            if seller_id:
                bot.send_message(
                    seller_id,
                    f"👑 *ВНИМАНИЕ!*\nАдминистратор подключился к заказу {seller_name}_{order_num}\n"
                    f"Вы не можете работать с этим заказом до отключения администратора."
                )
            
            bot.answer_callback_query(call.id, f"✅ Вы подключились к заказу {seller_name}_{order_num}")
            
            # Обновляем сообщение
            keyboard = telebot.types.InlineKeyboardMarkup()
            keyboard.row(
                telebot.types.InlineKeyboardButton("🔌 Отключиться", callback_data=f"admin_unblock_{seller_name}_{order_num}")
            )
            
            bot.edit_message_reply_markup(user_id, call.message.message_id, reply_markup=keyboard)
    
    # Админ: разблокировка заказа
    elif data.startswith('admin_unblock_'):
        parts = data.split('_')
        seller_name = parts[2]
        order_num = int(parts[3])
        
        unblock_order(seller_name, order_num)
        
        # Уведомляем продавца
        seller_id = get_seller_id(seller_name)
        if seller_id:
            bot.send_message(
                seller_id,
                f"👑 Администратор отключился от заказа {seller_name}_{order_num}\n"
                f"Вы можете продолжить работу с заказом."
            )
        
        bot.answer_callback_query(call.id, f"✅ Вы отключились от заказа {seller_name}_{order_num}")
        
        # Обновляем сообщение
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.row(
            telebot.types.InlineKeyboardButton(
                "👑 Подключиться к заказу",
                callback_data=f"admin_block_{seller_name}_{order_num}"
            )
        )
        
        bot.edit_message_reply_markup(user_id, call.message.message_id, reply_markup=keyboard)
    
    # Админ: просмотр чата с покупателем
    elif data.startswith('view_admin_chat_'):
        buyer_id = int(data.split('_')[3])
        
        if buyer_id in admin_chats:
            chat_data = admin_chats[buyer_id]
            buyer_link = get_buyer_link(buyer_id, chat_data['user_name'])
            
            history = f"📩 *ЧАТ #{chat_data['chat_id']} с {chat_data['user_name']}*\n"
            history += f"💬 [Связаться]({buyer_link})\n"
            history += "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            for msg in chat_data['messages']:
                sender = "👤 Покупатель" if msg['sender'] == 'user' else "👨‍💼 Вы"
                history += f"{sender} ({msg['time']}):\n{msg['text']}\n\n"
            
            keyboard = telebot.types.InlineKeyboardMarkup()
            keyboard.row(
                telebot.types.InlineKeyboardButton("✏️ Ответить", callback_data=f"reply_admin_chat_{buyer_id}"),
                telebot.types.InlineKeyboardButton("✅ Завершить", callback_data=f"complete_admin_chat_{buyer_id}")
            )
            
            bot.send_message(
                user_id,
                history,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
    
    # Админ: ответ в чат
    elif data.startswith('reply_admin_chat_'):
        buyer_id = int(data.split('_')[3])
        
        bot.send_message(
            user_id,
            f"✏️ Введите ответ для покупателя:"
        )
        bot.register_next_step_handler_by_chat_id(
            user_id,
            process_admin_reply,
            buyer_id
        )
    
    # Админ: завершить чат
    elif data.startswith('complete_admin_chat_'):
        buyer_id = int(data.split('_')[3])
        
        if buyer_id in admin_chats:
            admin_chats[buyer_id]['completed'] = True
            save_data()
            
            bot.answer_callback_query(call.id, "✅ Чат завершен")
            
            try:
                bot.edit_message_reply_markup(user_id, call.message.message_id, reply_markup=None)
            except:
                pass
    
    # Админ: переотправка проблемного заказа
    elif data.startswith('retry_delivery_'):
        parts = data.split('_')
        seller_name = parts[3]
        order_num = int(parts[4])
        target = parts[5]
        
        if seller_name in active_orders and order_num in active_orders[seller_name]:
            order = active_orders[seller_name][order_num]
            
            if target == 'seller':
                seller_id = get_seller_id(seller_name)
                if seller_id:
                    seller_message = (
                        f"📦 *ПОВТОРНАЯ ОТПРАВКА ЗАКАЗА {seller_name}_{order_num}*\n"
                        f"📅 {order['timestamp']}\n\n"
                        f"👤 *Покупатель:* {order['buyer_name']}\n"
                        f"📍 *Точка:* {order['address']}\n"
                        f"📝 *Заказ:* {order['order_text']}"
                    )
                    
                    seller_keyboard = telebot.types.InlineKeyboardMarkup()
                    seller_keyboard.row(
                        telebot.types.InlineKeyboardButton("✏️ Уточнить заказ", callback_data=f"seller_update_{seller_name}_{order_num}"),
                        telebot.types.InlineKeyboardButton("✅ Завершить заказ", callback_data=f"seller_close_{seller_name}_{order_num}")
                    )
                    
                    try:
                        bot.send_message(seller_id, seller_message, parse_mode="Markdown", reply_markup=seller_keyboard)
                        order['delivered_to_seller'] = True
                        bot.answer_callback_query(call.id, "✅ Заказ переотправлен продавцу")
                    except Exception as e:
                        order['delivered_to_seller'] = False
                        order['last_error'] = str(e)[:100]
                        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)[:50]}")
                    
                    order['delivery_attempts'] = order.get('delivery_attempts', 0) + 1
                    save_data()
            
            elif target == 'admin' and ADMIN_ID:
                buyer_link = get_buyer_link(order['buyer_id'], order['buyer_name'])
                admin_msg = (
                    f"👑 *ПОВТОРНАЯ ОТПРАВКА ЗАКАЗА {seller_name}_{order_num}*\n"
                    f"📅 {order['timestamp']}\n\n"
                    f"👤 Продавец: {seller_name}\n"
                    f"👤 Покупатель: {order['buyer_name']} 💬 [Связаться]({buyer_link})\n"
                    f"📍 {order['address']}\n"
                    f"📝 {order['order_text']}"
                )
                
                try:
                    bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown")
                    order['delivered_to_admin'] = True
                    bot.answer_callback_query(call.id, "✅ Уведомление переотправлено админу")
                except Exception as e:
                    order['delivered_to_admin'] = False
                    bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)[:50]}")
                
                save_data()
    
    # Продавец: уточнить заказ
    elif data.startswith('seller_update_'):
        parts = data.split('_')
        seller_name = parts[2]
        order_num = int(parts[3])
        
        seller_id = user_id
        
        if seller_name in active_orders and order_num in active_orders[seller_name]:
            
            # Проверяем блокировку
            if is_order_blocked(seller_name, order_num):
                bot.answer_callback_query(call.id, f"❌ Заказ заблокирован администратором")
                return
            
            seller_waiting_for_order_update[seller_id] = (seller_name, order_num)
            bot.answer_callback_query(call.id)
            
            bot.send_message(
                seller_id,
                f"✏️ *Уточнение заказа {seller_name}_{order_num}*\n\n"
                f"📍 Адрес: {active_orders[seller_name][order_num]['address']}\n"
                f"📝 *Текущий заказ:* {active_orders[seller_name][order_num]['order_text']}\n\n"
                f"*Напишите новый состав заказа:*"
            )
    
    # Продавец: завершить заказ
    elif data.startswith('seller_close_'):
        parts = data.split('_')
        seller_name = parts[2]
        order_num = int(parts[3])
        
        seller_id = user_id
        
        if seller_name in active_orders and order_num in active_orders[seller_name]:
            
            # Проверяем блокировку
            if is_order_blocked(seller_name, order_num):
                bot.answer_callback_query(call.id, f"❌ Заказ заблокирован администратором")
                return
            
            order = active_orders[seller_name][order_num]
            
            # Финальное сообщение покупателю с обновленным дизайном
            final_message = (
                f"✅ *Заказ от {order['timestamp']}*\n\n"
                f"📝 *Содержание:* {order['order_text']}\n"
                f"📍 *Адрес:* {order['address']}\n\n"
                f"💬 *Чат с менеджером закрыт*\n\n"
                f"✨ Оцените работу продавца:"
            )
            
            rating_keyboard = telebot.types.InlineKeyboardMarkup()
            rating_keyboard.row(
                telebot.types.InlineKeyboardButton("⭐", callback_data=f"rate_1_{seller_name}_{order_num}"),
                telebot.types.InlineKeyboardButton("⭐⭐", callback_data=f"rate_2_{seller_name}_{order_num}"),
                telebot.types.InlineKeyboardButton("⭐⭐⭐", callback_data=f"rate_3_{seller_name}_{order_num}"),
                telebot.types.InlineKeyboardButton("⭐⭐⭐⭐", callback_data=f"rate_4_{seller_name}_{order_num}"),
                telebot.types.InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data=f"rate_5_{seller_name}_{order_num}")
            )
            
            bot.send_message(
                order['buyer_id'],
                final_message,
                parse_mode="Markdown",
                reply_markup=rating_keyboard
            )
            
            # Перемещаем в завершенные
            completed_order = move_to_completed(seller_name, order_num)
            
            # Очищаем ожидание
            if seller_id in seller_waiting_for_order_update:
                del seller_waiting_for_order_update[seller_id]
            
            save_data()
            
            bot.answer_callback_query(call.id, "✅ Заказ завершен")
            
            # Обновляем сообщение у продавца
            try:
                bot.edit_message_text(
                    f"✅ *ЗАКАЗ ЗАВЕРШЕН {seller_name}_{order_num}*",
                    seller_id,
                    call.message.message_id
                )
            except:
                pass
            
            # Уведомляем админа
            if ADMIN_ID:
                buyer_link = get_buyer_link(order['buyer_id'], order['buyer_name'])
                bot.send_message(
                    ADMIN_ID,
                    f"👑 *ЗАКАЗ ЗАВЕРШЕН*\n\n"
                    f"📦 {seller_name}_{order_num}\n"
                    f"👤 Покупатель: {order['buyer_name']} 💬 [Связаться]({buyer_link})\n"
                    f"📝 {order['order_text']}",
                    parse_mode="Markdown"
                )
            
            # Создаем бэкап
            create_backup("Заказ завершен")
    
    # Оценка продавца
    elif data.startswith('rate_'):
        parts = data.split('_')
        rating = int(parts[1])
        seller_name = parts[2]
        order_num = int(parts[3])
        
        if seller_name not in seller_ratings:
            seller_ratings[seller_name] = {'total': 0, 'count': 0, 'avg': 0}
        
        seller_ratings[seller_name]['total'] += rating
        seller_ratings[seller_name]['count'] += 1
        seller_ratings[seller_name]['avg'] = seller_ratings[seller_name]['total'] / seller_ratings[seller_name]['count']
        
        save_data()
        
        bot.answer_callback_query(call.id, "✅ Спасибо за оценку!")
        
        try:
            bot.edit_message_reply_markup(user_id, call.message.message_id, reply_markup=None)
        except:
            pass
        
        # Уведомляем продавца
        seller_id = get_seller_id(seller_name)
        if seller_id:
            bot.send_message(
                seller_id,
                f"⭐ Новая оценка! Средний рейтинг: {seller_ratings[seller_name]['avg']:.1f}"
            )
    
    # Обработка выбора адреса (новый заказ)
    elif call.data in pickup_points:
        address = call.data
        user_info = user_data.get(user_id)
        
        if not user_info:
            bot.answer_callback_query(call.id, "❌ Ошибка: начните заказ заново")
            return
        
        seller_name = pickup_points[address]
        seller_id = get_seller_id(seller_name)
        
        if seller_id:
            # Генерируем номер заказа
            order_number = generate_order_number(seller_name)
            
            # Создаем заказ
            order_data = {
                'order_number': order_number,
                'buyer_id': user_id,
                'buyer_name': user_info['name'],
                'seller_id': seller_id,
                'seller_name': seller_name,
                'address': address,
                'order_text': user_info['text'],
                'timestamp': format_date(),
                'updated_at': None,
                'status': 'active',
                'delivered_to_seller': False,
                'delivered_to_admin': False,
                'delivery_attempts': 0
            }
            
            add_active_order(seller_name, order_data)
            save_data()
            
            # Отправляем продавцу
            seller_message = (
                f"📦 *НОВЫЙ ЗАКАЗ {seller_name}_{order_number}*\n"
                f"📅 {order_data['timestamp']}\n\n"
                f"👤 *Покупатель:* {user_info['name']}\n"
                f"📍 *Точка:* {address}\n"
                f"📝 *Заказ:* {user_info['text']}"
            )
            
            seller_keyboard = telebot.types.InlineKeyboardMarkup()
            seller_keyboard.row(
                telebot.types.InlineKeyboardButton("✏️ Уточнить заказ", callback_data=f"seller_update_{seller_name}_{order_number}"),
                telebot.types.InlineKeyboardButton("✅ Завершить заказ", callback_data=f"seller_close_{seller_name}_{order_number}")
            )
            
            try:
                bot.send_message(seller_id, seller_message, parse_mode="Markdown", reply_markup=seller_keyboard)
                order_data['delivered_to_seller'] = True
            except Exception as e:
                order_data['delivered_to_seller'] = False
                order_data['last_error'] = str(e)[:100]
            
            # Уведомляем админа
            if ADMIN_ID:
                buyer_link = get_buyer_link(user_id, user_info['name'])
                admin_msg = (
                    f"👑 *НОВЫЙ ЗАКАЗ {seller_name}_{order_number}*\n\n"
                    f"👤 Продавец: {seller_name}\n"
                    f"👤 Покупатель: {user_info['name']} 💬 [Связаться]({buyer_link})\n"
                    f"📍 {address}\n"
                    f"📝 {user_info['text']}"
                )
                
                try:
                    bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown")
                    order_data['delivered_to_admin'] = True
                except:
                    order_data['delivered_to_admin'] = False
            
            save_data()
            
            # Удаляем сообщение с кнопками
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            
            # Сообщение покупателю с обновленным дизайном
            buyer_msg = (
                f"🔄 *Ваш заказ в обработке*\n\n"
                f"📍 Адрес: {address}\n"
                f"📝 Ваш заказ: {user_info['text']}\n\n"
                f"*Менеджер скоро свяжется с Вами в этом чате.*\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Вы в любой момент можете вернуться к диалогу.\n"
                f"Просто нажмите в меню кнопку \"👤 Связь с админом\"\n"
                f"━━━━━━━━━━━━━━━━━━━━━━"
            )
            
            buyer_keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
            buyer_keyboard.row('📝 Написать сообщение администратору')
            buyer_keyboard.row('🔄 Вернуться к оформлению заказа (меню)')
            
            bot.send_message(
                user_id,
                buyer_msg,
                parse_mode="Markdown",
                reply_markup=buyer_keyboard
            )
            
            bot.answer_callback_query(call.id, f"✅ Заказ {seller_name}_{order_number} создан")
            
            # Создаем бэкап
            create_backup("Новый заказ")
    
    # Кнопка нового заказа
    elif call.data == "NEW_ORDER":
        bot.answer_callback_query(call.id)
        show_instruction_with_keyboard(call.message.chat.id)

def process_admin_reply(message, buyer_id):
    """Обработка ответа админа покупателю"""
    if buyer_id in admin_chats:
        # Добавляем ответ в историю
        admin_chats[buyer_id]['messages'].append({
            'sender': 'admin',
            'text': message.text,
            'time': format_time_only()
        })
        
        # Отправляем покупателю с обновленным дизайном
        buyer_msg = (
            f"💬 *Ответ от Администратора:*\n\n"
            f"{message.text}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Вы в любой момент можете вернуться к диалогу.\n"
            f"Просто нажмите в меню кнопку \"👤 Связь с админом\"\n"
            f"━━━━━━━━━━━━━━━━━━━━━━"
        )
        
        keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.row('📝 Написать сообщение администратору')
        keyboard.row('🔄 Вернуться к оформлению заказа (меню)')
        
        bot.send_message(
            buyer_id,
            buyer_msg,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        
        # Удаляем предыдущее служебное сообщение у покупателя
        try:
            bot.delete_message(buyer_id, message.message_id - 1)
        except:
            pass
        
        bot.send_message(
            message.chat.id,
            "✅ Ответ отправлен покупателю"
        )
        
        save_data()

# ====== ЕЖЕДНЕВНАЯ СВОДКА ======
def send_daily_summary():
    """Отправляет ежедневную сводку продавцам"""
    while True:
        now = get_novosibirsk_time()
        # Отправляем в 9:00 каждый день по Новосибирску
        target_time = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if now > target_time:
            target_time += timedelta(days=1)
        
        sleep_seconds = (target_time - now).total_seconds()
        time.sleep(sleep_seconds)
        
        for seller_name in pickup_points.values():
            seller_id = get_seller_id(seller_name)
            if seller_id:
                # Собираем статистику
                active = len(active_orders.get(seller_name, {}))
                completed_yesterday = 0
                
                # Считаем завершенные за вчера
                yesterday = (get_novosibirsk_time() - timedelta(days=1)).strftime("%d.%m.%Y")
                for order in completed_orders.get(seller_name, {}).values():
                    if order.get('timestamp') == yesterday:
                        completed_yesterday += 1
                
                summary = (
                    f"📊 *ДОБРОЕ УТРО, {seller_name}!*\n\n"
                    f"Ваши заказы на сегодня:\n"
                    f"✅ Активных: {active}\n"
                    f"📦 Завершено вчера: {completed_yesterday}\n\n"
                    f"Хорошего дня! ☀️"
                )
                
                try:
                    bot.send_message(seller_id, summary, parse_mode="Markdown")
                except:
                    pass

# Запускаем поток для ежедневной сводки
summary_thread = threading.Thread(target=send_daily_summary, daemon=True)
summary_thread.start()

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
    print(f"✅ Вебхук установлен: {webhook_url}")
    print(f"🕐 Часовой пояс: Новосибирск (UTC+7)")
    print(f"🕐 Текущее время: {format_time()}")
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
