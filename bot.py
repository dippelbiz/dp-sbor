import os
import telebot
from flask import Flask, request
from datetime import datetime
import json
import time
import shutil
from pathlib import Path

# ====== НАСТРОЙКИ ======
TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не установлен!")
    exit(1)

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Имя файла для хранения данных
DATA_FILE = 'bot_data.json'
ARCHIVE_FILE = 'orders_archive.json'
BACKUP_DIR = 'backups'  # Папка для бэкапов

# ADMIN ID - добавьте ваш Telegram ID в переменные окружения Render!
ADMIN_ID = os.environ.get('ADMIN_ID')
if ADMIN_ID:
    ADMIN_ID = int(ADMIN_ID)
    print(f"👑 Администратор: {ADMIN_ID}")
else:
    print("⚠️ ADMIN_ID не установлен! Функции администратора недоступны")
    ADMIN_ID = None

# Хранилища данных
user_data = {}  # Для временных данных пользователей
# Счетчики заказов для каждого продавца {seller_name: counter}
seller_counters = {
    "Александр": 0,
    "Юлия": 0,
    "Евгений": 0,
    "Татьяна": 0,
    "Рабочий": 0
}
active_orders = {}  # Активные заказы {order_id: order_data}
archive_orders = {}  # Архив завершенных заказов {order_id: order_data}
active_chats = {}   # Активные чаты {buyer_id: order_id}
chat_history = {}   # История сообщений {order_id: [messages]}
seller_waiting_for_order_update = {}  # Ожидание уточнения заказа {seller_id: order_id}
waiting_for_backup_upload = set()  # Ожидание загрузки файла бэкапа

# Список точек
pickup_points = {
    "ул. Галущака 15": "Александр",
    "ул. Беловежская 4/1": "Юлия", 
    "ул. Забалуева 90": "Евгений",
    "ул. Сержанта Коротаева 3": "Татьяна",
    "ул. Бетонная 14/1": "Рабочий"
}

# Соответствие букв продавцам
seller_letters = {
    "Александр": "А",
    "Юлия": "Ю",
    "Евгений": "Е",
    "Татьяна": "Т",
    "Рабочий": "Р"
}

# ====== ФУНКЦИИ ДЛЯ БЭКАПОВ ======
def create_backup_dir():
    """Создание папки для бэкапов если её нет"""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        print(f"📁 Создана папка для бэкапов: {BACKUP_DIR}")

def get_backup_filename():
    """Генерация имени файла бэкапа"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{BACKUP_DIR}/backup_{timestamp}.json"

def create_backup():
    """Создание полного бэкапа всех данных"""
    create_backup_dir()
    
    backup_data = {
        'timestamp': datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        'seller_counters': seller_counters,
        'active_orders': active_orders,
        'archive_orders': archive_orders,
        'chat_history': chat_history,
        'active_chats': active_chats
    }
    
    backup_file = get_backup_filename()
    
    try:
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
        print(f"💾 Бэкап создан: {backup_file}")
        return backup_file
    except Exception as e:
        print(f"❌ Ошибка создания бэкапа: {e}")
        return None

def restore_from_backup(backup_file):
    """Восстановление данных из бэкапа"""
    global seller_counters, active_orders, archive_orders, chat_history, active_chats
    
    try:
        with open(backup_file, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)
        
        # Восстанавливаем данные
        seller_counters = backup_data.get('seller_counters', seller_counters)
        active_orders = backup_data.get('active_orders', {})
        archive_orders = backup_data.get('archive_orders', {})
        chat_history = backup_data.get('chat_history', {})
        active_chats = backup_data.get('active_chats', {})
        
        # Преобразуем ID в числа где нужно
        for order_id, order in active_orders.items():
            if 'buyer_id' in order:
                order['buyer_id'] = int(order['buyer_id'])
            if 'seller_id' in order:
                order['seller_id'] = int(order['seller_id'])
        
        for order_id, order in archive_orders.items():
            if 'buyer_id' in order:
                order['buyer_id'] = int(order['buyer_id'])
            if 'seller_id' in order:
                order['seller_id'] = int(order['seller_id'])
        
        # Сохраняем восстановленные данные
        save_data()
        save_archive()
        
        print(f"✅ Данные восстановлены из бэкапа: {backup_file}")
        return True
    except Exception as e:
        print(f"❌ Ошибка восстановления из бэкапа: {e}")
        return False

def restore_from_uploaded_file(file_path):
    """Восстановление из загруженного файла"""
    try:
        # Копируем загруженный файл в папку бэкапов
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{BACKUP_DIR}/uploaded_backup_{timestamp}.json"
        shutil.copy2(file_path, backup_filename)
        
        # Восстанавливаем данные
        success = restore_from_backup(backup_filename)
        
        if success:
            # Удаляем временный файл
            os.remove(file_path)
            return True, backup_filename
        else:
            return False, None
    except Exception as e:
        print(f"❌ Ошибка при обработке загруженного файла: {e}")
        return False, None

def list_backups():
    """Получение списка доступных бэкапов"""
    if not os.path.exists(BACKUP_DIR):
        return []
    
    backups = []
    for file in os.listdir(BACKUP_DIR):
        if file.startswith('backup_') and file.endswith('.json'):
            filepath = os.path.join(BACKUP_DIR, file)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    timestamp = data.get('timestamp', 'неизвестно')
                backups.append({
                    'filename': file,
                    'path': filepath,
                    'timestamp': timestamp,
                    'size': os.path.getsize(filepath)
                })
            except:
                backups.append({
                    'filename': file,
                    'path': filepath,
                    'timestamp': 'поврежден',
                    'size': os.path.getsize(filepath)
                })
    
    # Сортируем по дате создания (новые сверху)
    backups.sort(key=lambda x: x['filename'], reverse=True)
    return backups

def cleanup_old_backups(keep_last=20):
    """Очистка старых бэкапов, оставляем только последние keep_last"""
    backups = list_backups()
    if len(backups) <= keep_last:
        return
    
    # Удаляем самые старые бэкапы
    to_delete = backups[keep_last:]
    for backup in to_delete:
        try:
            os.remove(backup['path'])
            print(f"🗑 Удален старый бэкап: {backup['filename']}")
        except Exception as e:
            print(f"❌ Ошибка удаления бэкапа {backup['filename']}: {e}")

# ====== ФУНКЦИИ ДЛЯ РАБОТЫ С ФАЙЛАМИ ======
def save_data():
    """Сохраняем активные заказы, счетчики и историю чатов в файл"""
    data = {
        'seller_counters': seller_counters,
        'active_orders': {},
        'chat_history': {}
    }
    
    # Преобразуем активные заказы в сохраняемый формат
    for order_id, order in active_orders.items():
        data['active_orders'][str(order_id)] = order
    
    # Сохраняем историю чатов
    for order_id, messages in chat_history.items():
        data['chat_history'][str(order_id)] = messages
    
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ Данные сохранены: {len(active_orders)} активных заказов")
    except Exception as e:
        print(f"❌ Ошибка сохранения данных: {e}")

def load_data():
    """Загружаем активные заказы, счетчики и историю чатов из файла"""
    global seller_counters, active_orders, active_chats, chat_history
    
    if not os.path.exists(DATA_FILE):
        print("📁 Файл данных не найден, начинаем с нуля")
        return
    
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Загружаем счетчики продавцов
        if 'seller_counters' in data:
            seller_counters.update(data['seller_counters'])
        
        active_orders = {}
        active_chats = {}
        
        # Восстанавливаем активные заказы
        loaded_orders = 0
        for order_id_str, order in data.get('active_orders', {}).items():
            order_id = str(order_id_str)
            
            # ПРЕОБРАЗУЕМ ВСЕ ID ИЗ СТРОК В ЧИСЛА
            if 'buyer_id' in order:
                order['buyer_id'] = int(order['buyer_id'])
            if 'seller_id' in order:
                order['seller_id'] = int(order['seller_id'])
            
            active_orders[order_id] = order
            loaded_orders += 1
            
            # Восстанавливаем активные чаты
            if 'buyer_id' in order and order['buyer_id']:
                active_chats[order['buyer_id']] = order_id
                print(f"🔄 Восстановлен чат: покупатель {order['buyer_id']} -> заказ #{order_id}")
        
        # Восстанавливаем историю чатов
        if 'chat_history' in data:
            chat_history = data['chat_history']
            print(f"📜 Загружена история для {len(chat_history)} чатов")
        
        print(f"✅ Данные загружены: {loaded_orders} активных заказов")
        print(f"📊 Текущие счетчики заказов: {seller_counters}")
        print(f"💬 Активных чатов восстановлено: {len(active_chats)}")
        
        # Выводим список восстановленных заказов
        if loaded_orders > 0:
            print("📋 Активные заказы:")
            for oid, ord in active_orders.items():
                print(f"   #{oid}: {ord['buyer_name']} - {ord['order_text'][:30]}...")
        
    except Exception as e:
        print(f"❌ Ошибка загрузки данных: {e}")

def save_archive():
    """Сохраняем архив завершенных заказов"""
    try:
        with open(ARCHIVE_FILE, 'w', encoding='utf-8') as f:
            json.dump(archive_orders, f, ensure_ascii=False, indent=2)
        print(f"✅ Архив сохранен: {len(archive_orders)} завершенных заказов")
    except Exception as e:
        print(f"❌ Ошибка сохранения архива: {e}")

def load_archive():
    """Загружаем архив завершенных заказов"""
    global archive_orders
    
    if not os.path.exists(ARCHIVE_FILE):
        print("📁 Файл архива не найден, начинаем с нуля")
        return
    
    try:
        with open(ARCHIVE_FILE, 'r', encoding='utf-8') as f:
            archive_orders = json.load(f)
        
        # Преобразуем ID в числа где нужно
        for order_id, order in archive_orders.items():
            if 'buyer_id' in order:
                order['buyer_id'] = int(order['buyer_id'])
            if 'seller_id' in order:
                order['seller_id'] = int(order['seller_id'])
        
        print(f"✅ Архив загружен: {len(archive_orders)} завершенных заказов")
    except Exception as e:
        print(f"❌ Ошибка загрузки архива: {e}")

# Загружаем данные и архив при старте
load_data()
load_archive()

# ПРОВЕРКА: Если есть активные заказы, покажем их в логах
if active_orders:
    print(f"\n🚀 БОТ ЗАПУЩЕН С {len(active_orders)} АКТИВНЫМИ ЗАКАЗАМИ:")
    for order_id, order in active_orders.items():
        print(f"   #{order_id}: {order['buyer_name']} - {order['order_text'][:50]}...")
    print(f"💬 Активных чатов: {len(active_chats)}\n")
else:
    print("\n📭 Нет активных заказов\n")

# ====== ФУНКЦИИ ДЛЯ ПРОВЕРКИ ПРАВ ======
def is_admin(user_id):
    """Проверка, является ли пользователь администратором"""
    return ADMIN_ID is not None and user_id == ADMIN_ID

def is_seller(user_id):
    """Проверка, является ли пользователь продавцом"""
    return user_id in get_all_seller_ids()

def can_view_order(user_id, order):
    """Проверка, может ли пользователь видеть заказ"""
    return is_admin(user_id) or (is_seller(user_id) and order['seller_id'] == user_id)

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
        print(f"   Установите переменную {env_var_name} в настройках Render")
        return None
    
    try:
        return int(seller_id_str)
    except ValueError:
        print(f"❌ Ошибка: ID продавца {seller_name} должен быть числом, а не '{seller_id_str}'")
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

def get_all_active_orders():
    """Получить ВСЕ активные заказы (для админа)"""
    return list(active_orders.keys())

def log_message(order_id, sender_id, sender_name, sender_role, message_text):
    """Логирование сообщения в историю чата"""
    if order_id not in chat_history:
        chat_history[order_id] = []
    
    chat_history[order_id].append({
        'timestamp': datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        'sender_id': sender_id,
        'sender_name': sender_name,
        'sender_role': sender_role,
        'message': message_text
    })
    
    # Ограничим историю последними 100 сообщениями
    if len(chat_history[order_id]) > 100:
        chat_history[order_id] = chat_history[order_id][-100:]
    
    save_data()

def get_chat_history_text(order_id):
    """Получить форматированную историю чата"""
    if order_id not in chat_history or not chat_history[order_id]:
        return "📭 История сообщений пуста"
    
    history_text = f"📜 *История чата по заказу #{order_id}*\n\n"
    
    for msg in chat_history[order_id]:
        role_emoji = {
            'покупатель': '👤',
            'продавец': '👨‍💼',
            'админ': '👑'
        }.get(msg['sender_role'], '💬')
        
        history_text += f"{role_emoji} *{msg['sender_name']}* ({msg['sender_role']})\n"
        history_text += f"🕐 {msg['timestamp']}\n"
        history_text += f"💬 {msg['message']}\n\n"
    
    return history_text

def show_instruction_with_keyboard(chat_id):
    """Показать инструкцию с клавиатурой"""
    main_keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    main_keyboard.add('Каталог с ценами')
    main_keyboard.add('О нас')
    main_keyboard.add('Связь с Админом')
    
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

# ====== КОМАНДЫ ДЛЯ АДМИНИСТРАТОРА ======
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    """Панель администратора"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(user_id, "❌ У вас нет прав администратора")
        return
    
    keyboard = telebot.types.InlineKeyboardMarkup(row_width=2)
    keyboard.row(
        telebot.types.InlineKeyboardButton("📋 Активные заказы", callback_data="admin_all_orders"),
        telebot.types.InlineKeyboardButton("📚 Архив заказов", callback_data="admin_archive")
    )
    keyboard.row(
        telebot.types.InlineKeyboardButton("👥 Статистика", callback_data="admin_stats"),
        telebot.types.InlineKeyboardButton("🔍 Поиск", callback_data="admin_search")
    )
    keyboard.row(
        telebot.types.InlineKeyboardButton("📊 Отчет по продавцам", callback_data="admin_sellers")
    )
    keyboard.row(
        telebot.types.InlineKeyboardButton("💾 Управление бэкапами", callback_data="admin_backup_menu")
    )
    
    bot.send_message(
        user_id,
        "👑 *Панель администратора*\n\n"
        "Выберите действие:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

@bot.message_handler(commands=['stats'])
def admin_stats_command(message):
    """Быстрая статистика"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(user_id, "❌ У вас нет прав администратора")
        return
    
    show_admin_stats(user_id)

def show_admin_stats(chat_id):
    """Показать статистику"""
    total_orders = len(active_orders)
    total_archive = len(archive_orders)
    total_chats = len(active_chats)
    
    # Статистика по продавцам
    seller_stats = {}
    for order_id, order in active_orders.items():
        seller_name = order['seller_name']
        if seller_name not in seller_stats:
            seller_stats[seller_name] = 0
        seller_stats[seller_name] += 1
    
    stats_text = "📊 *Статистика системы*\n\n"
    stats_text += f"📦 Активных заказов: {total_orders}\n"
    stats_text += f"📚 Завершенных заказов: {total_archive}\n"
    stats_text += f"💬 Активных чатов: {total_chats}\n\n"
    stats_text += "*По продавцам (активные):*\n"
    
    for seller, count in seller_stats.items():
        stats_text += f"• {seller}: {count} заказов\n"
    
    bot.send_message(chat_id, stats_text, parse_mode="Markdown")

def force_complete_order(admin_id, order_id):
    """Принудительное завершение заказа администратором"""
    order = active_orders.get(order_id)
    
    if not order:
        bot.send_message(admin_id, f"❌ Заказ #{order_id} не найден")
        return False
    
    try:
        final_order_text = order['order_text']
        order_date = order['updated_at'] if order['updated_at'] else order['timestamp']
        
        # Финальное сообщение покупателю
        final_message = (
            f"✅ *Заказ от {order_date}*\n\n"
            f"📝 *Содержание:* {final_order_text}\n"
            f"📍 *Адрес:* {order['address']}\n\n"
            f"💬 *Чат закрыт администратором*"
        )
        
        user_keyboard = telebot.types.InlineKeyboardMarkup()
        user_keyboard.row(
            telebot.types.InlineKeyboardButton("🔄 Сделать новый заказ", callback_data="NEW_ORDER")
        )
        
        bot.send_message(
            order['buyer_id'],
            final_message,
            parse_mode="Markdown",
            reply_markup=user_keyboard
        )
        
        # Уведомляем продавца о принудительном завершении
        bot.send_message(
            order['seller_id'],
            f"👑 *Заказ #{order_id} завершен администратором*\n\n"
            f"👤 Покупатель: {order['buyer_name']}\n"
            f"📍 Точка: {order['address']}\n"
            f"📝 Заказ: {final_order_text}",
            parse_mode="Markdown"
        )
        
        # Добавляем информацию о завершении в историю
        log_message(
            order_id,
            admin_id,
            "Администратор",
            "админ",
            f"✅ Заказ принудительно завершен"
        )
        
        # Сохраняем в архив
        order['completed_at'] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        order['completed_by'] = "admin"
        archive_orders[order_id] = order
        
        # Удаляем из активных
        if order['buyer_id'] in active_chats:
            del active_chats[order['buyer_id']]
        
        del active_orders[order_id]
        
        if order['seller_id'] in seller_waiting_for_order_update:
            del seller_waiting_for_order_update[order['seller_id']]
        
        save_data()
        save_archive()
        
        # Создаем бэкап при завершении заказа
        create_backup()
        cleanup_old_backups()
        
        bot.send_message(admin_id, f"✅ Заказ #{order_id} принудительно завершен")
        return True
        
    except Exception as e:
        bot.send_message(admin_id, f"❌ Ошибка при завершении заказа: {str(e)[:100]}")
        return False

# ====== ОБРАБОТЧИКИ ======
@bot.message_handler(commands=['start'])
def send_welcome(message):
    show_instruction_with_keyboard(message.chat.id)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    """Обработка загруженных файлов (бэкапов)"""
    user_id = message.from_user.id
    
    # Проверяем, что это админ и он ожидает загрузку бэкапа
    if not is_admin(user_id) or user_id not in waiting_for_backup_upload:
        bot.send_message(user_id, "❌ Сейчас не ожидается загрузка файлов")
        return
    
    try:
        # Получаем информацию о файле
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Сохраняем временный файл
        temp_file = f"temp_backup_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(temp_file, 'wb') as f:
            f.write(downloaded_file)
        
        # Пытаемся восстановить из файла
        success, backup_path = restore_from_uploaded_file(temp_file)
        
        if success:
            bot.send_message(
                user_id,
                f"✅ *Данные успешно восстановлены из загруженного файла!*\n\n"
                f"📦 Активных заказов: {len(active_orders)}\n"
                f"📚 Завершенных заказов: {len(archive_orders)}\n"
                f"💬 Чатов в истории: {len(chat_history)}\n\n"
                f"Файл сохранен как: `{os.path.basename(backup_path)}`",
                parse_mode="Markdown"
            )
        else:
            bot.send_message(
                user_id,
                "❌ *Ошибка при восстановлении из файла*\n\n"
                "Убедитесь, что файл является корректным бэкапом.",
                parse_mode="Markdown"
            )
        
        # Убираем пользователя из ожидания
        waiting_for_backup_upload.remove(user_id)
        
    except Exception as e:
        bot.send_message(
            user_id,
            f"❌ Ошибка при обработке файла: {str(e)[:100]}"
        )
        if user_id in waiting_for_backup_upload:
            waiting_for_backup_upload.remove(user_id)

@bot.message_handler(func=lambda message: message.text == 'Каталог с ценами')
def send_catalog(message):
    catalog_text = (
        "📋 *Каталог с ценами*\n\n"
        "1. *Грецкий орех очищенный*, 500г - 400 ₽\n"
        "2. *Миндаль золотой*, 1000г - 950 ₽\n"
        "3. *Кешью WW320*, 1000г - 1000 ₽\n"
        "4. *Манго сушеное*, 500г - 250 ₽\n"
        "5. *Клубника сушеная*, 500г- 350 ₽\n\n"
        "*Для заказа напишите что Вам нужно*"
    )
    bot.send_message(message.chat.id, catalog_text, parse_mode="Markdown")
    show_instruction_with_keyboard(message.chat.id)

@bot.message_handler(func=lambda message: message.text == 'О нас')
def send_about(message):
    about_text = (
        "🏢 *О нашей компании*\n\n"
        "*DP SBOR | Отборные орехи и сухофрукты • Новосибирск*\n"
        "Мы выбираем продукты по качеству, вкусу и внешнему виду, а не по минимальной цене\n\n"
        "Всё, начиная от выбора товара, заканчивая фасовкой и упаковкой проходит жесткий контроль\n\n"
        "*Вы гарантированно получаете высшее качество по шикарным ценам*\n\n"
        "📍 На данный момент есть 5 точек *в Новосибирске*, где можно забрать заказ\n\n"
        "*Наш канал: t.me/dp_sbor *"
    )
    bot.send_message(message.chat.id, about_text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == 'Связь с Админом')
def contact_admin(message):
    """Обработка кнопки связи с админом"""
    admin_contact_text = (
        "👑 *Связь с администратором*\n\n"
        "Для связи с администратором нажмите кнопку ниже:"
    )
    
    # Создаем кнопку для перехода в личные сообщения с админом
    keyboard = telebot.types.InlineKeyboardMarkup()
    if ADMIN_ID:
        admin_link = f"tg://user?id={ADMIN_ID}"
        keyboard.add(telebot.types.InlineKeyboardButton(
            text="📩 Написать администратору", 
            url=admin_link
        ))
    else:
        keyboard.add(telebot.types.InlineKeyboardButton(
            text="❌ Администратор не доступен", 
            callback_data="admin_unavailable"
        ))
    
    bot.send_message(
        message.chat.id,
        admin_contact_text,
        parse_mode="Markdown",
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    # ===== АДМИН КНОПКИ =====
    if call.data == "admin_all_orders":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Нет прав")
            return
        
        if not active_orders:
            bot.send_message(user_id, "📭 Нет активных заказов")
            bot.answer_callback_query(call.id)
            return
        
        for order_id, order in active_orders.items():
            order_info = (
                f"📦 *Заказ #{order_id}*\n"
                f"📅 {order['timestamp']}\n"
                f"👤 Продавец: {order['seller_name']}\n"
                f"👤 Покупатель: {order['buyer_name']}\n"
                f"📍 {order['address']}\n"
                f"📝 {order['order_text'][:50]}...\n\n"
                f"💬 Сообщений в чате: {len(chat_history.get(order_id, []))}"
            )
            
            keyboard = telebot.types.InlineKeyboardMarkup(row_width=2)
            keyboard.row(
                telebot.types.InlineKeyboardButton("📜 История чата", callback_data=f"admin_chat_{order_id}"),
                telebot.types.InlineKeyboardButton("⚠️ Завершить", callback_data=f"admin_force_close_{order_id}")
            )
            
            bot.send_message(user_id, order_info, parse_mode="Markdown", reply_markup=keyboard)
        
        bot.answer_callback_query(call.id)
        return
    
    elif call.data == "admin_archive":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Нет прав")
            return
        
        if not archive_orders:
            bot.send_message(user_id, "📭 Архив пуст")
            bot.answer_callback_query(call.id)
            return
        
        # Показываем последние 10 завершенных заказов
        archive_list = list(archive_orders.items())[-10:]
        
        for order_id, order in archive_list:
            order_info = (
                f"📚 *Заказ #{order_id} (завершен)*\n"
                f"📅 Создан: {order['timestamp']}\n"
                f"🏁 Завершен: {order.get('completed_at', 'неизвестно')}\n"
                f"👤 Продавец: {order['seller_name']}\n"
                f"👤 Покупатель: {order['buyer_name']}\n"
                f"📍 {order['address']}\n"
                f"📝 {order['order_text'][:50]}..."
            )
            
            keyboard = telebot.types.InlineKeyboardMarkup()
            keyboard.row(
                telebot.types.InlineKeyboardButton("📜 История чата", callback_data=f"admin_archive_chat_{order_id}")
            )
            
            bot.send_message(user_id, order_info, parse_mode="Markdown", reply_markup=keyboard)
        
        bot.send_message(user_id, f"📚 Всего в архиве: {len(archive_orders)} заказов")
        bot.answer_callback_query(call.id)
        return
    
    elif call.data == "admin_stats":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Нет прав")
            return
        show_admin_stats(user_id)
        bot.answer_callback_query(call.id)
        return
    
    elif call.data == "admin_sellers":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Нет прав")
            return
        
        sellers_info = "👥 *Статистика по продавцам*\n\n"
        for seller_name in pickup_points.values():
            seller_id = get_seller_id(seller_name)
            if seller_id:
                active_count = len(get_seller_active_orders(seller_id))
                # Считаем завершенные заказы
                completed_count = sum(1 for o in archive_orders.values() if o['seller_name'] == seller_name)
                sellers_info += f"• {seller_name}:\n"
                sellers_info += f"  📦 Активных: {active_count}\n"
                sellers_info += f"  📚 Завершено: {completed_count}\n\n"
        
        bot.send_message(user_id, sellers_info, parse_mode="Markdown")
        bot.answer_callback_query(call.id)
        return
    
    elif call.data == "admin_search":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Нет прав")
            return
        bot.send_message(user_id, "🔍 Введите номер заказа в формате: /search А1")
        bot.answer_callback_query(call.id)
        return
    
    elif call.data == "admin_backup_menu":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Нет прав")
            return
        
        keyboard = telebot.types.InlineKeyboardMarkup(row_width=2)
        keyboard.row(
            telebot.types.InlineKeyboardButton("💾 Создать бэкап", callback_data="admin_backup_create"),
            telebot.types.InlineKeyboardButton("📋 Список бэкапов", callback_data="admin_backup_list")
        )
        keyboard.row(
            telebot.types.InlineKeyboardButton("📤 Загрузить бэкап", callback_data="admin_backup_upload"),
            telebot.types.InlineKeyboardButton("📥 Скачать бэкап", callback_data="admin_backup_download_menu")
        )
        keyboard.row(
            telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_back")
        )
        
        bot.edit_message_text(
            "💾 *Управление бэкапами*\n\n"
            "Выберите действие:",
            user_id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        bot.answer_callback_query(call.id)
        return
    
    elif call.data == "admin_backup_create":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Нет прав")
            return
        
        bot.edit_message_text(
            "⏳ Создаю бэкап...",
            user_id,
            call.message.message_id,
            parse_mode="Markdown"
        )
        
        backup_file = create_backup()
        cleanup_old_backups()
        
        if backup_file:
            bot.edit_message_text(
                f"✅ Бэкап успешно создан!\n\n"
                f"📁 Файл: {backup_file}\n"
                f"📦 Активных заказов: {len(active_orders)}\n"
                f"📚 Завершенных заказов: {len(archive_orders)}\n"
                f"💬 Чатов в истории: {len(chat_history)}",
                user_id,
                call.message.message_id,
                parse_mode="Markdown"
            )
        else:
            bot.edit_message_text(
                "❌ Ошибка при создании бэкапа",
                user_id,
                call.message.message_id,
                parse_mode="Markdown"
            )
        
        bot.answer_callback_query(call.id)
        return
    
    elif call.data == "admin_backup_list":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Нет прав")
            return
        
        backups = list_backups()
        
        if not backups:
            bot.edit_message_text(
                "📭 Нет доступных бэкапов",
                user_id,
                call.message.message_id,
                parse_mode="Markdown"
            )
            bot.answer_callback_query(call.id)
            return
        
        text = "📋 *Доступные бэкапы:*\n\n"
        
        # Показываем последние 10 бэкапов
        for i, backup in enumerate(backups[:10], 1):
            size_kb = backup['size'] / 1024
            text += f"{i}. `{backup['filename']}`\n"
            text += f"   📅 {backup['timestamp']}\n"
            text += f"   📦 {size_kb:.1f} KB\n\n"
        
        if len(backups) > 10:
            text += f"... и еще {len(backups) - 10} бэкапов\n\n"
        
        text += "Для восстановления используйте:\n"
        text += "`/restore имя_файла`\n\n"
        text += "Для скачивания:\n"
        text += "`/download имя_файла`"
        
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.row(
            telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_backup_menu")
        )
        
        bot.edit_message_text(
            text,
            user_id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        bot.answer_callback_query(call.id)
        return
    
    elif call.data == "admin_backup_upload":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Нет прав")
            return
        
        # Добавляем пользователя в список ожидающих загрузку
        waiting_for_backup_upload.add(user_id)
        
        bot.edit_message_text(
            "📤 *Загрузка бэкапа*\n\n"
            "Отправьте мне файл бэкапа (JSON-файл).\n\n"
            "⚠️ *ВНИМАНИЕ!*\n"
            "Загруженный файл заменит ВСЕ текущие данные!\n\n"
            "Текущее состояние:\n"
            f"📦 Активных заказов: {len(active_orders)}\n"
            f"📚 Завершенных заказов: {len(archive_orders)}\n"
            f"💬 Чатов в истории: {len(chat_history)}",
            user_id,
            call.message.message_id,
            parse_mode="Markdown"
        )
        bot.answer_callback_query(call.id)
        return
    
    elif call.data == "admin_backup_download_menu":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Нет прав")
            return
        
        backups = list_backups()
        
        if not backups:
            bot.edit_message_text(
                "📭 Нет доступных бэкапов для скачивания",
                user_id,
                call.message.message_id,
                parse_mode="Markdown"
            )
            bot.answer_callback_query(call.id)
            return
        
        # Создаем клавиатуру с кнопками для скачивания последних 10 бэкапов
        keyboard = telebot.types.InlineKeyboardMarkup(row_width=1)
        for backup in backups[:10]:
            keyboard.add(telebot.types.InlineKeyboardButton(
                f"📥 {backup['filename'][:30]} ({backup['timestamp']})",
                callback_data=f"admin_download_{backup['filename']}"
            ))
        
        keyboard.add(telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_backup_menu"))
        
        bot.edit_message_text(
            "📥 *Выберите бэкап для скачивания:*",
            user_id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        bot.answer_callback_query(call.id)
        return
    
    elif call.data.startswith('admin_download_'):
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Нет прав")
            return
        
        filename = call.data.replace('admin_download_', '')
        filepath = os.path.join(BACKUP_DIR, filename)
        
        if not os.path.exists(filepath):
            bot.answer_callback_query(call.id, "❌ Файл не найден")
            return
        
        try:
            with open(filepath, 'rb') as f:
                bot.send_document(
                    user_id,
                    f,
                    caption=f"📥 Бэкап: {filename}"
                )
            bot.answer_callback_query(call.id, "✅ Файл отправлен")
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)[:50]}")
        
        return
    
    elif call.data == "admin_back":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Нет прав")
            return
        
        # Возвращаемся в главное меню админа
        keyboard = telebot.types.InlineKeyboardMarkup(row_width=2)
        keyboard.row(
            telebot.types.InlineKeyboardButton("📋 Активные заказы", callback_data="admin_all_orders"),
            telebot.types.InlineKeyboardButton("📚 Архив заказов", callback_data="admin_archive")
        )
        keyboard.row(
            telebot.types.InlineKeyboardButton("👥 Статистика", callback_data="admin_stats"),
            telebot.types.InlineKeyboardButton("🔍 Поиск", callback_data="admin_search")
        )
        keyboard.row(
            telebot.types.InlineKeyboardButton("📊 Отчет по продавцам", callback_data="admin_sellers")
        )
        keyboard.row(
            telebot.types.InlineKeyboardButton("💾 Управление бэкапами", callback_data="admin_backup_menu")
        )
        
        bot.edit_message_text(
            "👑 *Панель администратора*\n\n"
            "Выберите действие:",
            user_id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        bot.answer_callback_query(call.id)
        return
    
    elif call.data.startswith('admin_chat_'):
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Нет прав")
            return
        
        order_id = call.data.split('_')[2]
        history_text = get_chat_history_text(order_id)
        
        # Разбиваем длинные сообщения
        if len(history_text) > 4000:
            parts = [history_text[i:i+4000] for i in range(0, len(history_text), 4000)]
            for part in parts:
                bot.send_message(user_id, part, parse_mode="Markdown")
        else:
            bot.send_message(user_id, history_text, parse_mode="Markdown")
        
        bot.answer_callback_query(call.id)
        return
    
    elif call.data.startswith('admin_archive_chat_'):
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Нет прав")
            return
        
        order_id = call.data.split('_')[3]
        history_text = get_chat_history_text(order_id)
        
        if len(history_text) > 4000:
            parts = [history_text[i:i+4000] for i in range(0, len(history_text), 4000)]
            for part in parts:
                bot.send_message(user_id, part, parse_mode="Markdown")
        else:
            bot.send_message(user_id, history_text, parse_mode="Markdown")
        
        bot.answer_callback_query(call.id)
        return
    
    elif call.data.startswith('admin_force_close_'):
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Нет прав")
            return
        
        order_id = call.data.split('_')[3]
        
        # Запрашиваем подтверждение
        confirm_keyboard = telebot.types.InlineKeyboardMarkup()
        confirm_keyboard.row(
            telebot.types.InlineKeyboardButton("✅ Да, завершить", callback_data=f"admin_confirm_close_{order_id}"),
            telebot.types.InlineKeyboardButton("❌ Отмена", callback_data="admin_cancel_close")
        )
        
        bot.edit_message_text(
            f"⚠️ *Подтверждение*\n\nВы действительно хотите принудительно завершить заказ #{order_id}?",
            user_id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=confirm_keyboard
        )
        bot.answer_callback_query(call.id)
        return
    
    elif call.data.startswith('admin_confirm_close_'):
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Нет прав")
            return
        
        order_id = call.data.split('_')[3]
        
        # Принудительно завершаем заказ
        success = force_complete_order(user_id, order_id)
        
        if success:
            bot.edit_message_text(
                f"✅ Заказ #{order_id} успешно завершен",
                user_id,
                call.message.message_id,
                parse_mode="Markdown"
            )
        else:
            bot.edit_message_text(
                f"❌ Не удалось завершить заказ #{order_id}",
                user_id,
                call.message.message_id,
                parse_mode="Markdown"
            )
        
        bot.answer_callback_query(call.id)
        return
    
    elif call.data == "admin_cancel_close":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Нет прав")
            return
        
        bot.edit_message_text(
            "❌ Завершение заказа отменено",
            user_id,
            call.message.message_id,
            parse_mode="Markdown"
        )
        bot.answer_callback_query(call.id)
        return
    
    elif call.data == "admin_unavailable":
        bot.answer_callback_query(call.id, "❌ Администратор временно недоступен")
        bot.send_message(
            call.message.chat.id,
            "⚠️ Администратор временно недоступен. Пожалуйста, попробуйте позже или напишите менеджеру на точке."
        )
        return
    
    # ===== КНОПКА НОВОГО ЗАКАЗА =====
    if call.data == "NEW_ORDER":
        bot.answer_callback_query(call.id)
        show_instruction_with_keyboard(chat_id)
        return
    
    # ===== КНОПКИ ПРОДАВЦА =====
    if call.data.startswith('seller_update_'):
        handle_seller_update_callback(call)
        return
    elif call.data.startswith('seller_close_'):
        handle_seller_close_callback(call)
        return
    
    # ===== ОБРАБОТКА ВЫБОРА АДРЕСА =====
    address = call.data
    user_info = user_data.get(user_id)
    
    if not user_info:
        bot.answer_callback_query(call.id, "❌ Ошибка: начните заказ заново")
        bot.send_message(chat_id, "Пожалуйста, напишите что хотите заказать:")
        return
    
    seller_name = pickup_points.get(address)
    seller_id = get_seller_id(seller_name)
    
    if seller_id:
        # Формируем информацию о покупателе
        buyer_name = user_info['name']
        buyer_id = user_info['user_id']
        
        # Генерируем ID заказа в формате А1, Е1 и т.д.
        global seller_counters
        seller_counters[seller_name] += 1
        seller_letter = seller_letters[seller_name]
        order_id = f"{seller_letter}{seller_counters[seller_name]}"
        
        # Сохраняем заказ
        order_data = {
            'order_id': order_id,
            'buyer_id': buyer_id,
            'buyer_name': buyer_name,
            'seller_id': seller_id,
            'seller_name': seller_name,
            'address': address,
            'order_text': user_info['text'],
            'timestamp': datetime.now().strftime("%d.%m.%Y"),
            'updated_at': None,
            'status': 'active'
        }
        active_orders[order_id] = order_data
        
        # Активируем чат покупателя
        active_chats[buyer_id] = order_id
        
        # Инициализируем историю чата
        if order_id not in chat_history:
            chat_history[order_id] = []
        
        # Логируем создание заказа
        log_message(
            order_id,
            buyer_id,
            buyer_name,
            "покупатель",
            f"🆕 Создан заказ: {user_info['text']}"
        )
        
        # Сохраняем данные
        save_data()
        
        # Создаем бэкап при новом заказе
        create_backup()
        cleanup_old_backups()
        
        # Сообщение продавцу
        seller_message = (
            f"📦 *НОВЫЙ ЗАКАЗ #{order_id}*\n"
            f"📅 {datetime.now().strftime('%d.%m.%Y')}\n\n"
            f"👤 *Покупатель:* {buyer_name}\n"
            f"📍 *Точка:* {address}\n"
            f"📝 *Заказ:* {user_info['text']}\n\n"
            f"🆔 ID покупателя: {buyer_id}"
        )
        
        seller_keyboard = telebot.types.InlineKeyboardMarkup()
        seller_keyboard.row(
            telebot.types.InlineKeyboardButton("✏️ Уточнить заказ", callback_data=f"seller_update_{order_id}"),
            telebot.types.InlineKeyboardButton("✅ Завершить заказ", callback_data=f"seller_close_{order_id}")
        )
        
        seller_active_orders = get_seller_active_orders(seller_id)
        if len(seller_active_orders) > 1:
            seller_message += f"\n\n📋 *Ваши активные заказы:* {', '.join([f'#{oid}' for oid in seller_active_orders])}"
        
        seller_message += "\n\n💬 *Чтобы ответить покупателю, напишите:*\n`#" + order_id + " ваш_текст`"
        
        try:
            bot.send_message(seller_id, seller_message, parse_mode="Markdown", reply_markup=seller_keyboard)
            success = True
            
            # Уведомляем админа о новом заказе
            if ADMIN_ID:
                bot.send_message(
                    ADMIN_ID,
                    f"👑 *НОВЫЙ ЗАКАЗ #{order_id}*\n\n"
                    f"👤 Продавец: {seller_name}\n"
                    f"👤 Покупатель: {buyer_name}\n"
                    f"📍 {address}\n"
                    f"📝 {user_info['text']}",
                    parse_mode="Markdown"
                )
                
        except Exception as e:
            print(f"❌ Ошибка отправки продавцу {seller_name}: {e}")
            success = False
        
        # Удаляем сообщение с кнопками выбора адреса
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass
        
        # Сообщение покупателю
        buyer_message = (
            f"🔄 *Ваш заказ в обработке*\n\n"
            f"📍 Адрес: {address}\n"
            f"📝 Ваш заказ: {user_info['text']}\n\n"
            f"*Менеджер скоро свяжется с Вами в этом чате.*"
        )
        
        if success:
            bot.send_message(
                chat_id,
                buyer_message,
                parse_mode="Markdown"
            )
            bot.answer_callback_query(call.id, f"✅ Заказ #{order_id} отправлен менеджеру")
        else:
            bot.send_message(
                chat_id,
                f"⚠️ Заказ принят, но продавец пока не получил уведомление."
            )
            bot.answer_callback_query(call.id, "⚠️ Задержка с уведомлением")
    else:
        bot.answer_callback_query(call.id, "❌ Ошибка: точка временно недоступна")
        print(f"❌ Не удалось получить ID продавца для {seller_name}")

@bot.message_handler(commands=['search'])
def search_order(message):
    """Поиск заказа по номеру (для админа)"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(user_id, "❌ У вас нет прав администратора")
        return
    
    try:
        order_id = message.text.split()[1]
        
        # Ищем сначала в активных, потом в архиве
        order = active_orders.get(order_id)
        is_archive = False
        
        if not order:
            order = archive_orders.get(order_id)
            is_archive = True
        
        if order:
            status = "ЗАВЕРШЕН" if is_archive else "АКТИВЕН"
            order_info = (
                f"🔍 *Заказ #{order_id} ({status})*\n\n"
                f"📅 Создан: {order['timestamp']}\n"
                f"👤 Продавец: {order['seller_name']}\n"
                f"👤 Покупатель: {order['buyer_name']}\n"
                f"📍 Адрес: {order['address']}\n"
                f"📝 Заказ: {order['order_text']}\n"
                f"🔄 Обновлен: {order['updated_at'] if order['updated_at'] else 'нет'}\n"
            )
            
            if is_archive:
                order_info += f"🏁 Завершен: {order.get('completed_at', 'неизвестно')}\n"
            
            order_info += f"\n💬 Сообщений в чате: {len(chat_history.get(order_id, []))}"
            
            keyboard = telebot.types.InlineKeyboardMarkup()
            keyboard.row(
                telebot.types.InlineKeyboardButton("📜 История чата", callback_data=f"admin_chat_{order_id}" if not is_archive else f"admin_archive_chat_{order_id}")
            )
            
            bot.send_message(user_id, order_info, parse_mode="Markdown", reply_markup=keyboard)
        else:
            bot.send_message(user_id, f"❌ Заказ #{order_id} не найден")
            
    except (IndexError, ValueError):
        bot.send_message(user_id, "❌ Используйте: /search А1")

@bot.message_handler(commands=['restore'])
def restore_from_backup_command(message):
    """Восстановление из бэкапа по имени файла"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(user_id, "❌ У вас нет прав администратора")
        return
    
    try:
        backup_filename = message.text.split()[1]
        backup_path = os.path.join(BACKUP_DIR, backup_filename)
        
        if not os.path.exists(backup_path):
            bot.send_message(user_id, f"❌ Файл бэкапа не найден: {backup_filename}")
            return
        
        # Запрашиваем подтверждение
        confirm_keyboard = telebot.types.InlineKeyboardMarkup()
        confirm_keyboard.row(
            telebot.types.InlineKeyboardButton("⚠️ Да, восстановить", callback_data=f"admin_restore_confirm_{backup_filename}"),
            telebot.types.InlineKeyboardButton("❌ Отмена", callback_data="admin_restore_cancel")
        )
        
        bot.send_message(
            user_id,
            f"⚠️ *ВНИМАНИЕ!*\n\n"
            f"Вы собираетесь восстановить данные из бэкапа:\n"
            f"`{backup_filename}`\n\n"
            f"Это ЗАМЕНИТ все текущие данные!\n\n"
            f"Текущее состояние:\n"
            f"📦 Активных заказов: {len(active_orders)}\n"
            f"📚 Завершенных заказов: {len(archive_orders)}\n"
            f"💬 Чатов в истории: {len(chat_history)}\n\n"
            f"Вы уверены?",
            parse_mode="Markdown",
            reply_markup=confirm_keyboard
        )
        
    except (IndexError, ValueError):
        bot.send_message(user_id, "❌ Используйте: /restore backup_20240101_120000.json")

@bot.message_handler(commands=['download'])
def download_backup_command(message):
    """Скачивание бэкапа по имени файла"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(user_id, "❌ У вас нет прав администратора")
        return
    
    try:
        backup_filename = message.text.split()[1]
        backup_path = os.path.join(BACKUP_DIR, backup_filename)
        
        if not os.path.exists(backup_path):
            bot.send_message(user_id, f"❌ Файл бэкапа не найден: {backup_filename}")
            return
        
        with open(backup_path, 'rb') as f:
            bot.send_document(
                user_id,
                f,
                caption=f"📥 Бэкап: {backup_filename}"
            )
        
    except (IndexError, ValueError):
        bot.send_message(user_id, "❌ Используйте: /download backup_20240101_120000.json")
    except Exception as e:
        bot.send_message(user_id, f"❌ Ошибка при скачивании: {str(e)[:100]}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_restore_confirm_'))
def handle_restore_confirm(call):
    """Подтверждение восстановления из бэкапа"""
    user_id = call.from_user.id
    
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "❌ Нет прав")
        return
    
    backup_filename = call.data.replace('admin_restore_confirm_', '')
    backup_path = os.path.join(BACKUP_DIR, backup_filename)
    
    bot.edit_message_text(
        "⏳ Восстанавливаю данные...",
        user_id,
        call.message.message_id,
        parse_mode="Markdown"
    )
    
    success = restore_from_backup(backup_path)
    
    if success:
        bot.edit_message_text(
            f"✅ Данные успешно восстановлены из бэкапа!\n\n"
            f"📦 Активных заказов: {len(active_orders)}\n"
            f"📚 Завершенных заказов: {len(archive_orders)}\n"
            f"💬 Чатов в истории: {len(chat_history)}",
            user_id,
            call.message.message_id,
            parse_mode="Markdown"
        )
    else:
        bot.edit_message_text(
            f"❌ Ошибка при восстановлении из бэкапа",
            user_id,
            call.message.message_id,
            parse_mode="Markdown"
        )
    
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_restore_cancel")
def handle_restore_cancel(call):
    """Отмена восстановления из бэкапа"""
    user_id = call.from_user.id
    
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "❌ Нет прав")
        return
    
    bot.edit_message_text(
        "❌ Восстановление отменено",
        user_id,
        call.message.message_id,
        parse_mode="Markdown"
    )
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Пропускаем команды, которые уже обработаны
    if text in ['Каталог с ценами', 'О нас', 'Связь с Админом']:
        return
    
    # --- АДМИНИСТРАТОР ---
    if is_admin(user_id):
        # Админ может отвечать на любой заказ через #
        if text.startswith('#'):
            try:
                parts = text.split(' ', 1)
                order_num = parts[0][1:]
                order_id = order_num
                message_text = parts[1] if len(parts) > 1 else ""
                
                if not message_text:
                    bot.send_message(user_id, "❌ Не указан текст сообщения")
                    return
                
                # Проверяем сначала активные заказы, потом архив
                order = active_orders.get(order_id)
                is_archive = False
                
                if not order:
                    order = archive_orders.get(order_id)
                    is_archive = True
                
                if order:
                    if is_archive:
                        bot.send_message(user_id, f"❌ Нельзя отвечать на завершенный заказ #{order_id}")
                    else:
                        # Отправляем сообщение покупателю
                        bot.send_message(
                            order['buyer_id'],
                            f"💬 *Сообщение от администратора:*\n\n{message_text}",
                            parse_mode="Markdown"
                        )
                        
                        # Логируем сообщение
                        log_message(
                            order_id,
                            user_id,
                            "Администратор",
                            "админ",
                            message_text
                        )
                        
                        bot.send_message(
                            user_id,
                            f"✅ Сообщение отправлено покупателю (Заказ #{order_id}, продавец: {order['seller_name']})"
                        )
                        
                        # Уведомляем продавца, что админ вмешался
                        bot.send_message(
                            order['seller_id'],
                            f"👑 *Вмешательство администратора*\n\n"
                            f"Администратор отправил сообщение по вашему заказу #{order_id}\n\n"
                            f"💬 {message_text}",
                            parse_mode="Markdown"
                        )
                else:
                    bot.send_message(user_id, f"❌ Заказ #{order_id} не найден")
                    
            except Exception as e:
                bot.send_message(user_id, f"❌ Ошибка: {str(e)[:100]}")
        else:
            # Если админ пишет без #, показываем панель
            admin_panel(message)
        return
    
    # --- ПРОДАВЕЦ ---
    if is_seller(user_id):
        # Проверяем, ожидаем ли мы уточнение заказа от этого продавца
        if user_id in seller_waiting_for_order_update:
            order_id = seller_waiting_for_order_update[user_id]
            order = active_orders.get(order_id)
            
            if order:
                # Обновляем заказ
                old_order_text = order['order_text']
                order['order_text'] = text
                order['updated_at'] = datetime.now().strftime("%d.%m.%Y")
                
                # Логируем уточнение заказа
                log_message(
                    order_id,
                    user_id,
                    order['seller_name'],
                    "продавец",
                    f"✏️ Уточнил заказ: {text}"
                )
                
                # Сохраняем изменения
                save_data()
                
                # Отправляем подтверждение продавцу
                seller_keyboard = telebot.types.InlineKeyboardMarkup()
                seller_keyboard.row(
                    telebot.types.InlineKeyboardButton("✏️ Уточнить заказ", callback_data=f"seller_update_{order_id}"),
                    telebot.types.InlineKeyboardButton("✅ Завершить заказ", callback_data=f"seller_close_{order_id}")
                )
                
                bot.send_message(
                    user_id,
                    f"✅ *Заказ #{order_id} обновлен!*\n\n"
                    f"📝 *Актуальный заказ:* {text}\n"
                    f"📍 *Адрес:* {order['address']}\n\n"
                    f"💬 *Действия:*",
                    parse_mode="Markdown",
                    reply_markup=seller_keyboard
                )
                
                # Отправляем уведомление покупателю
                bot.send_message(
                    order['buyer_id'],
                    f"📝 *Уточненный заказ:*\n\n{text}\n\n"
                    f"📍 *Адрес:* {order['address']}\n\n"
                    f"*Отправьте сообщение, если хотите еще что-то уточнить.*",
                    parse_mode="Markdown"
                )
                
                # Уведомляем админа об изменении заказа
                if ADMIN_ID:
                    bot.send_message(
                        ADMIN_ID,
                        f"👑 *Заказ #{order_id} обновлен*\n\n"
                        f"👤 Продавец: {order['seller_name']}\n"
                        f"📝 Было: {old_order_text[:100]}\n"
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
        
        # Продавец должен указывать номер заказа через #
        if text.startswith('#'):
            try:
                parts = text.split(' ', 1)
                order_num = parts[0][1:]
                order_id = order_num
                message_text = parts[1] if len(parts) > 1 else ""
                
                if not message_text:
                    bot.send_message(user_id, "❌ Не указан текст сообщения. Формат: #номер_заказа текст_сообщения")
                    return
                
                if order_id in active_orders:
                    order = active_orders[order_id]
                    
                    if order['seller_id'] == user_id:
                        # Отправляем сообщение покупателю
                        bot.send_message(
                            order['buyer_id'],
                            f"💬 *Сообщение от менеджера:*\n\n{message_text}",
                            parse_mode="Markdown"
                        )
                        
                        # Логируем сообщение
                        log_message(
                            order_id,
                            user_id,
                            order['seller_name'],
                            "продавец",
                            message_text
                        )
                        
                        bot.send_message(user_id, f"✅ Сообщение отправлено покупателю (Заказ #{order_id})")
                        
                        # Копируем сообщение админу
                        if ADMIN_ID:
                            bot.send_message(
                                ADMIN_ID,
                                f"👑 *Сообщение от менеджера*\n\n"
                                f"📦 Заказ #{order_id}\n"
                                f"👤 Продавец: {order['seller_name']}\n"
                                f"👤 Покупатель: {order['buyer_name']}\n"
                                f"💬 {message_text}",
                                parse_mode="Markdown"
                            )
                    else:
                        bot.send_message(user_id, f"❌ Заказ #{order_id} не принадлежит вам")
                else:
                    bot.send_message(user_id, f"❌ Заказ #{order_id} не найден")
                    
            except Exception as e:
                bot.send_message(user_id, f"❌ Ошибка: {str(e)[:100]}")
        else:
            # Если продавец пишет без #, напоминаем ему о формате
            seller_active_orders = get_seller_active_orders(user_id)
            if seller_active_orders:
                orders_list = '\n'.join([f"• Заказ #{oid}" for oid in seller_active_orders])
                bot.send_message(
                    user_id,
                    f"📋 *У вас {len(seller_active_orders)} активных заказов:*\n\n"
                    f"{orders_list}\n\n"
                    f"💬 *Чтобы ответить покупателю, начните сообщение с номера заказа:*\n"
                    f"Пример: `#А1 Здравствуйте! Ваш заказ будет готов через час`"
                )
            else:
                bot.send_message(user_id, "❌ У вас нет активных заказов.")
        return
    
    # --- ПОКУПАТЕЛЬ ---
    # Проверяем, ведет ли покупатель активный чат
    if user_id in active_chats:
        order_id = active_chats[user_id]
        order = active_orders.get(order_id)
        
        if order:
            # Отправляем сообщение продавцу с двумя кнопками
            try:
                seller_keyboard = telebot.types.InlineKeyboardMarkup()
                seller_keyboard.row(
                    telebot.types.InlineKeyboardButton("✏️ Уточнить заказ", callback_data=f"seller_update_{order_id}"),
                    telebot.types.InlineKeyboardButton("✅ Завершить заказ", callback_data=f"seller_close_{order_id}")
                )
                
                bot.send_message(
                    order['seller_id'],
                    f"📩 *Сообщение от покупателя (Заказ #{order_id}):*\n\n"
                    f"👤 {order['buyer_name']}\n"
                    f"📍 Точка: {order['address']}\n"
                    f"📝 *Текущий заказ:* {order['order_text']}\n\n"
                    f"💬 {text}",
                    parse_mode="Markdown",
                    reply_markup=seller_keyboard
                )
                
                # Логируем сообщение
                log_message(
                    order_id,
                    user_id,
                    order['buyer_name'],
                    "покупатель",
                    text
                )
                
                bot.send_message(
                    user_id,
                    f"✅ Сообщение отправлено менеджеру"
                )
                
                # Копируем сообщение админу
                if ADMIN_ID:
                    bot.send_message(
                        ADMIN_ID,
                        f"👑 *Сообщение от покупателя*\n\n"
                        f"📦 Заказ #{order_id}\n"
                        f"👤 Продавец: {order['seller_name']}\n"
                        f"👤 Покупатель: {order['buyer_name']}\n"
                        f"💬 {text}",
                        parse_mode="Markdown"
                    )
                    
            except Exception as e:
                bot.send_message(
                    user_id,
                    f"❌ Не удалось отправить сообщение: {str(e)[:100]}"
                )
            return
        else:
            # Если заказ не найден, удаляем из активных чатов
            if user_id in active_chats:
                del active_chats[user_id]
                save_data()
    
    # --- НОВЫЙ ЗАКАЗ ОТ ПОКУПАТЕЛЯ ---
    # Проверяем, нет ли у покупателя активного заказа
    if user_id in active_chats:
        bot.send_message(
            user_id,
            "⚠️ У вас уже есть активный заказ. Дождитесь завершения текущего заказа."
        )
        return
    
    # Сохраняем данные
    user_data[user_id] = {
        'text': text,
        'name': message.from_user.first_name or "Покупатель",
        'user_id': user_id
    }
    
    # Создаем кнопки с адресами
    keyboard = telebot.types.InlineKeyboardMarkup()
    for address in pickup_points.keys():
        keyboard.add(telebot.types.InlineKeyboardButton(
            text=address, 
            callback_data=address
        ))
    
    bot.send_message(
        user_id, 
        "✅ Сообщение получено! Выберите удобный адрес:",
        reply_markup=keyboard
    )

def handle_seller_update_callback(call):
    """Обработка кнопки 'Уточнить заказ'"""
    seller_id = call.from_user.id
    parts = call.data.split('_')
    order_id = parts[2]
    
    order = active_orders.get(order_id)
    
    if not order:
        bot.answer_callback_query(call.id, "❌ Заказ не найден")
        return
    
    if order['seller_id'] != seller_id:
        bot.answer_callback_query(call.id, "❌ Этот заказ не ваш")
        return
    
    seller_waiting_for_order_update[seller_id] = order_id
    bot.answer_callback_query(call.id)
    
    bot.send_message(
        seller_id,
        f"✏️ *Уточнение заказа #{order_id}*\n\n"
        f"📍 Адрес: {order['address']}\n"
        f"📝 *Текущий заказ:* {order['order_text']}\n\n"
        f"*Напишите новый состав заказа:*"
    )

def handle_seller_close_callback(call):
    """Обработка кнопки 'Завершить заказ'"""
    seller_id = call.from_user.id
    parts = call.data.split('_')
    order_id = parts[2]
    
    order = active_orders.get(order_id)
    
    if not order:
        bot.answer_callback_query(call.id, "❌ Заказ не найден")
        return
    
    if order['seller_id'] != seller_id:
        bot.answer_callback_query(call.id, "❌ Этот заказ не ваш")
        return
    
    try:
        final_order_text = order['order_text']
        order_date = order['updated_at'] if order['updated_at'] else order['timestamp']
        
        # Логируем завершение
        log_message(
            order_id,
            seller_id,
            order['seller_name'],
            "продавец",
            "✅ Заказ завершен"
        )
        
        # Финальное сообщение покупателю
        final_message = (
            f"✅ *Заказ от {order_date}*\n\n"
            f"📝 *Содержание:* {final_order_text}\n"
            f"📍 *Адрес:* {order['address']}\n\n"
            f"💬 *Чат с менеджером закрыт*"
        )
        
        user_keyboard = telebot.types.InlineKeyboardMarkup()
        user_keyboard.row(
            telebot.types.InlineKeyboardButton("🔄 Сделать новый заказ", callback_data="NEW_ORDER")
        )
        
        bot.send_message(
            order['buyer_id'],
            final_message,
            parse_mode="Markdown",
            reply_markup=user_keyboard
        )
        
        # Уведомляем админа о завершении заказа
        if ADMIN_ID:
            bot.send_message(
                ADMIN_ID,
                f"👑 *ЗАКАЗ ЗАВЕРШЕН #{order_id}*\n\n"
                f"👤 Продавец: {order['seller_name']}\n"
                f"👤 Покупатель: {order['buyer_name']}\n"
                f"📝 {final_order_text}",
                parse_mode="Markdown"
            )
        
        # Сохраняем в архив
        order['completed_at'] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        order['completed_by'] = "seller"
        archive_orders[order_id] = order
        
        # Закрываем чаты
        if order['buyer_id'] in active_chats:
            del active_chats[order['buyer_id']]
        
        del active_orders[order_id]
        
        if seller_id in seller_waiting_for_order_update:
            del seller_waiting_for_order_update[seller_id]
        
        save_data()
        save_archive()
        
        # Создаем бэкап при завершении заказа
        create_backup()
        cleanup_old_backups()
        
        # Обновляем сообщение у продавца
        try:
            bot.edit_message_text(
                f"✅ *ЗАКАЗ ЗАВЕРШЕН #{order_id}*\n\n"
                f"👤 Покупатель: {order['buyer_name']}\n"
                f"📍 Точка: {order['address']}\n"
                f"📝 Заказ: {final_order_text}\n\n"
                f"📅 Создан: {order['timestamp']}\n"
                f"🔄 Обновлен: {order['updated_at'] if order['updated_at'] else 'нет'}\n"
                f"🏁 Завершен: {order['completed_at']}",
                seller_id,
                call.message.message_id,
                parse_mode="Markdown"
            )
        except:
            pass
        
        seller_active_orders = get_seller_active_orders(seller_id)
        if seller_active_orders:
            orders_list = '\n'.join([f"• Заказ #{oid}" for oid in seller_active_orders])
            bot.send_message(
                seller_id,
                f"📋 *Осталось активных заказов: {len(seller_active_orders)}*\n\n"
                f"{orders_list}\n\n"
                f"💬 `#номер_заказа ваш_текст`"
            )
        else:
            bot.send_message(seller_id, "✅ Все заказы завершены!")
        
        bot.answer_callback_query(call.id, "✅ Заказ завершен")
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)[:50]}")

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
    # Создаем папку для бэкапов при запуске
    create_backup_dir()
    
    bot.remove_webhook()
    
    service_name = os.environ.get('RENDER_SERVICE_NAME', 'dp-sbor')
    webhook_url = f'https://{service_name}.onrender.com/webhook'
    
    bot.set_webhook(url=webhook_url)
    print(f"✅ Вебхук установлен: {webhook_url}")
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
