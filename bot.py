import os
import telebot
from flask import Flask, request
from datetime import datetime
import json
import time

# ====== НАСТРОЙКИ ======
TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не установлен!")
    exit(1)

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Имя файла для хранения данных
DATA_FILE = 'bot_data.json'

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
order_counter = 0  # Счетчик заказов
active_orders = {}  # Активные заказы {order_id: order_data}
active_chats = {}   # Активные чаты {buyer_id: order_id}
seller_waiting_for_order_update = {}  # Ожидание уточнения заказа {seller_id: order_id}

# Список точек
pickup_points = {
    "ул. Галущака 15": "Александр",
    "ул. Беловежская 4/1": "Юлия", 
    "ул. Забалуева 90": "Евгений",
    "ул. Сержанта Коротаева 3": "Татьяна",
    "ул. Бетонная 14/1": "Рабочий"
}

# ====== УПРОЩЕННАЯ ФУНКЦИЯ ЗАГРУЗКИ ======
def load_data():
    """Загружаем активные заказы и счетчик из файла"""
    global order_counter, active_orders, active_chats
    
    if not os.path.exists(DATA_FILE):
        print("📁 Файл данных не найден, начинаем с нуля")
        return
    
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        order_counter = data.get('order_counter', 0)
        active_orders = {}
        active_chats = {}
        
        # Восстанавливаем активные заказы
        loaded_orders = 0
        for order_id_str, order in data.get('active_orders', {}).items():
            order_id = int(order_id_str)
            
            # ПРЕОБРАЗУЕМ ID В ЧИСЛА
            if 'buyer_id' in order:
                order['buyer_id'] = int(order['buyer_id'])
            if 'seller_id' in order:
                order['seller_id'] = int(order['seller_id'])
            if 'order_id' in order:
                order['order_id'] = int(order['order_id'])
            
            active_orders[order_id] = order
            loaded_orders += 1
            
            # Восстанавливаем активные чаты
            if 'buyer_id' in order and order['buyer_id']:
                active_chats[order['buyer_id']] = order_id
        
        print(f"✅ Загружено {loaded_orders} активных заказов")
        
    except Exception as e:
        print(f"❌ Ошибка загрузки данных: {e}")

def save_data():
    """Сохраняем активные заказы и счетчик в файл"""
    data = {
        'order_counter': order_counter,
        'active_orders': {}
    }
    
    # Преобразуем заказы в сохраняемый формат
    for order_id, order in active_orders.items():
        data['active_orders'][str(order_id)] = order
    
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ Данные сохранены: {len(active_orders)} активных заказов")
    except Exception as e:
        print(f"❌ Ошибка сохранения данных: {e}")

# Загружаем данные при старте
load_data()

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

def show_instruction_with_keyboard(chat_id):
    """Показать инструкцию с клавиатурой"""
    main_keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    main_keyboard.add('Каталог с ценами')
    main_keyboard.add('О нас')
    
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

# ====== ФУНКЦИЯ ПЕРЕОТПРАВКИ ЗАКАЗА ======
def resend_order_to_seller(order_id, admin_id=None):
    """
    Переотправить заказ продавцу
    Покупатель НЕ получает уведомлений
    """
    if order_id not in active_orders:
        return {'success': False, 'error': 'Заказ не найден'}
    
    order = active_orders[order_id]
    seller_id = order['seller_id']
    seller_name = order['seller_name']
    
    # Формируем сообщение для продавца
    seller_message = (
        f"📦 *ЗАКАЗ #{order_id}*\n"
        f"📅 {order['timestamp']}\n\n"
        f"👤 *Покупатель:* {order['buyer_name']}\n"
        f"📍 *Точка:* {order['address']}\n"
        f"📝 *Заказ:* {order['order_text']}\n"
    )
    
    if admin_id:
        seller_message += f"\n👑 Переотправлено администратором"
    
    # Клавиатура для продавца
    seller_keyboard = telebot.types.InlineKeyboardMarkup()
    seller_keyboard.row(
        telebot.types.InlineKeyboardButton("✏️ Уточнить заказ", callback_data=f"seller_update_{order_id}"),
        telebot.types.InlineKeyboardButton("✅ Завершить заказ", callback_data=f"seller_close_{order_id}")
    )
    
    try:
        bot.send_message(
            seller_id, 
            seller_message, 
            parse_mode="Markdown", 
            reply_markup=seller_keyboard
        )
        
        # Активируем чат с покупателем
        if order['buyer_id'] not in active_chats:
            active_chats[order['buyer_id']] = order_id
        
        save_data()
        
        return {
            'success': True, 
            'seller_name': seller_name,
            'order_id': order_id
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)[:100]}

# ====== АДМИН-ПАНЕЛЬ ======
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(user_id, "❌ У вас нет прав администратора")
        return
    
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row("📋 Активные заказы", "📊 Статистика")
    keyboard.row("🔄 Переотправить заказ", "👥 По продавцам")
    keyboard.row("🔍 Поиск по номеру", "🏠 Главное меню")
    
    bot.send_message(
        user_id,
        "👑 *Панель администратора*\n\n"
        "Выберите действие:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

@bot.message_handler(func=lambda message: message.text == "📋 Активные заказы")
def show_active_orders(message):
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return
    
    if not active_orders:
        bot.send_message(user_id, "📭 Нет активных заказов")
        return
    
    for order_id, order in sorted(active_orders.items()):
        order_info = (
            f"📦 *Заказ #{order_id}*\n"
            f"📅 {order['timestamp']}\n"
            f"👤 Продавец: {order['seller_name']}\n"
            f"👤 Покупатель: {order['buyer_name']}\n"
            f"📍 {order['address']}\n"
            f"📝 {order['order_text']}\n"
        )
        
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.row(
            telebot.types.InlineKeyboardButton(
                "🔄 Переотправить продавцу", 
                callback_data=f"admin_resend_{order_id}"
            )
        )
        
        bot.send_message(
            user_id,
            order_info,
            parse_mode="Markdown",
            reply_markup=keyboard
        )

@bot.message_handler(func=lambda message: message.text == "🔄 Переотправить заказ")
def resend_order_prompt(message):
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return
    
    msg = bot.send_message(
        user_id,
        "🔍 Введите номер заказа для переотправки (например: 6):"
    )
    bot.register_next_step_handler(msg, process_resend_order)

def process_resend_order(message):
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return
    
    try:
        order_id = int(message.text.strip())
        
        if order_id not in active_orders:
            bot.send_message(user_id, f"❌ Заказ #{order_id} не найден")
            return
        
        result = resend_order_to_seller(order_id, admin_id=user_id)
        
        if result['success']:
            bot.send_message(
                user_id,
                f"✅ Заказ #{order_id} переотправлен продавцу {result['seller_name']}"
            )
        else:
            bot.send_message(user_id, f"❌ Ошибка: {result['error']}")
            
    except ValueError:
        bot.send_message(user_id, "❌ Введите корректный номер заказа")

@bot.message_handler(func=lambda message: message.text == "📊 Статистика")
def admin_stats(message):
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return
    
    total_orders = len(active_orders)
    
    seller_stats = {}
    for order in active_orders.values():
        seller = order['seller_name']
        seller_stats[seller] = seller_stats.get(seller, 0) + 1
    
    report = "📊 *СТАТИСТИКА*\n\n"
    report += f"📦 Всего активных заказов: {total_orders}\n\n"
    report += "*По продавцам:*\n"
    
    for seller, count in seller_stats.items():
        report += f"• {seller}: {count} заказов\n"
    
    bot.send_message(user_id, report, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "👥 По продавцам")
def sellers_list(message):
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return
    
    for seller_name in pickup_points.values():
        seller_id = get_seller_id(seller_name)
        if seller_id:
            seller_orders = get_seller_active_orders(seller_id)
            
            if seller_orders:
                report = f"👤 *{seller_name}*\n"
                report += f"📦 Заказов: {len(seller_orders)}\n"
                
                for order_id in seller_orders:
                    order = active_orders[order_id]
                    report += f"  • #{order_id}: {order['buyer_name']} - {order['order_text'][:30]}...\n"
                
                bot.send_message(user_id, report, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "🔍 Поиск по номеру")
def search_prompt(message):
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return
    
    msg = bot.send_message(
        user_id,
        "🔍 Введите номер заказа:"
    )
    bot.register_next_step_handler(msg, process_search)

def process_search(message):
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return
    
    try:
        order_id = int(message.text.strip())
        order = active_orders.get(order_id)
        
        if order:
            order_info = (
                f"🔍 *Заказ #{order_id}*\n\n"
                f"📅 Создан: {order['timestamp']}\n"
                f"👤 Продавец: {order['seller_name']}\n"
                f"👤 Покупатель: {order['buyer_name']}\n"
                f"📍 Адрес: {order['address']}\n"
                f"📝 Заказ: {order['order_text']}\n"
                f"💬 Чтобы ответить: `#{order_id} ваш_текст`"
            )
            
            keyboard = telebot.types.InlineKeyboardMarkup()
            keyboard.row(
                telebot.types.InlineKeyboardButton(
                    "🔄 Переотправить", 
                    callback_data=f"admin_resend_{order_id}"
                )
            )
            
            bot.send_message(user_id, order_info, parse_mode="Markdown", reply_markup=keyboard)
        else:
            bot.send_message(user_id, f"❌ Заказ #{order_id} не найден")
            
    except ValueError:
        bot.send_message(user_id, "❌ Введите корректный номер заказа")

@bot.message_handler(func=lambda message: message.text == "🏠 Главное меню")
def back_to_main(message):
    show_instruction_with_keyboard(message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_resend_'))
def admin_resend_callback(call):
    user_id = call.from_user.id
    
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "❌ Нет прав")
        return
    
    order_id = int(call.data.replace('admin_resend_', ''))
    
    result = resend_order_to_seller(order_id, admin_id=user_id)
    
    if result['success']:
        bot.answer_callback_query(call.id, f"✅ Заказ #{order_id} переотправлен")
        
        # Обновляем сообщение
        try:
            order = active_orders[order_id]
            new_text = (
                f"📦 *Заказ #{order_id} (ПЕРЕОТПРАВЛЕН)*\n"
                f"📅 {order['timestamp']}\n"
                f"👤 Продавец: {order['seller_name']}\n"
                f"👤 Покупатель: {order['buyer_name']}\n"
                f"📍 {order['address']}\n"
                f"📝 {order['order_text']}\n"
                f"🔄 Переотправлено: {datetime.now().strftime('%H:%M %d.%m.%Y')}"
            )
            bot.edit_message_text(new_text, user_id, call.message.message_id, parse_mode="Markdown")
        except:
            pass
    else:
        bot.answer_callback_query(call.id, f"❌ {result['error']}")

# ====== ОБРАБОТЧИКИ ДЛЯ ПОКУПАТЕЛЕЙ И ПРОДАВЦОВ ======
@bot.message_handler(commands=['start'])
def send_welcome(message):
    show_instruction_with_keyboard(message.chat.id)

@bot.message_handler(func=lambda message: message.text == 'Каталог с ценами')
def send_catalog(message):
    catalog_text = (
        "📋 *Каталог с ценами*\n\n"
        "1. *Фисташки иранские*, 500г - 600 ₽\n"
        "2. *Грецкий орех очищенный*, 500г - 400 ₽\n"
        "3. *Миндаль золотой*, 1000г - 950 ₽\n"
        "4. *Кешью WW320*, 1000г - 1000 ₽\n"
        "5. *Манго сушеное*, 500г - 250 ₽\n"
        "6. *Клубника сушеная*, 500г- 350 ₽\n"
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

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    if text in ['📋 Активные заказы', '📊 Статистика', '🔄 Переотправить заказ', 
                '👥 По продавцам', '🔍 Поиск по номеру', '🏠 Главное меню', 
                'Каталог с ценами', 'О нас']:
        return
    
    # --- ПРОДАВЕЦ ---
    if is_seller(user_id):
        if user_id in seller_waiting_for_order_update:
            order_id = seller_waiting_for_order_update[user_id]
            order = active_orders.get(order_id)
            
            if order:
                order['order_text'] = text
                order['updated_at'] = datetime.now().strftime("%d.%m.%Y")
                save_data()
                
                seller_keyboard = telebot.types.InlineKeyboardMarkup()
                seller_keyboard.row(
                    telebot.types.InlineKeyboardButton("✏️ Уточнить заказ", callback_data=f"seller_update_{order_id}"),
                    telebot.types.InlineKeyboardButton("✅ Завершить заказ", callback_data=f"seller_close_{order_id}")
                )
                
                bot.send_message(
                    user_id,
                    f"✅ *Заказ #{order_id} обновлен!*\n\n📝 *Актуальный заказ:* {text}",
                    parse_mode="Markdown",
                    reply_markup=seller_keyboard
                )
                
                bot.send_message(
                    order['buyer_id'],
                    f"📝 *Уточненный заказ:*\n\n{text}",
                    parse_mode="Markdown"
                )
                
                del seller_waiting_for_order_update[user_id]
                return
        
        if text.startswith('#'):
            try:
                parts = text.split(' ', 1)
                order_id = int(parts[0][1:])
                message_text = parts[1] if len(parts) > 1 else ""
                
                if order_id in active_orders and active_orders[order_id]['seller_id'] == user_id:
                    order = active_orders[order_id]
                    bot.send_message(order['buyer_id'], f"💬 *Сообщение от менеджера:*\n\n{message_text}")
                    bot.send_message(user_id, f"✅ Сообщение отправлено")
                else:
                    bot.send_message(user_id, "❌ Заказ не найден")
            except:
                bot.send_message(user_id, "❌ Ошибка формата")
        return
    
    # --- ПОКУПАТЕЛЬ ---
    if user_id in active_chats:
        order_id = active_chats[user_id]
        order = active_orders.get(order_id)
        
        if order:
            seller_keyboard = telebot.types.InlineKeyboardMarkup()
            seller_keyboard.row(
                telebot.types.InlineKeyboardButton("✏️ Уточнить заказ", callback_data=f"seller_update_{order_id}"),
                telebot.types.InlineKeyboardButton("✅ Завершить заказ", callback_data=f"seller_close_{order_id}")
            )
            
            bot.send_message(
                order['seller_id'],
                f"📩 *Сообщение от покупателя (Заказ #{order_id}):*\n\n💬 {text}",
                reply_markup=seller_keyboard
            )
            bot.send_message(user_id, "✅ Сообщение отправлено")
            return
    
    # --- НОВЫЙ ЗАКАЗ ---
    user_data[user_id] = {
        'text': text,
        'name': message.from_user.first_name or "Покупатель",
        'user_id': user_id
    }
    
    keyboard = telebot.types.InlineKeyboardMarkup()
    for address in pickup_points.keys():
        keyboard.add(telebot.types.InlineKeyboardButton(text=address, callback_data=address))
    
    bot.send_message(user_id, "✅ Сообщение получено! Выберите удобный адрес:", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    if call.data == "NEW_ORDER":
        bot.answer_callback_query(call.id)
        show_instruction_with_keyboard(chat_id)
        return
    
    if call.data.startswith('seller_update_'):
        order_id = int(call.data.split('_')[2])
        order = active_orders.get(order_id)
        
        if order and order['seller_id'] == user_id:
            seller_waiting_for_order_update[user_id] = order_id
            bot.answer_callback_query(call.id)
            bot.send_message(user_id, f"✏️ Напишите новый состав заказа #{order_id}:")
        return
    
    if call.data.startswith('seller_close_'):
        order_id = int(call.data.split('_')[2])
        order = active_orders.get(order_id)
        
        if order and order['seller_id'] == user_id:
            final_message = (
                f"✅ *Заказ от {order['timestamp']}*\n\n"
                f"📝 *Содержание:* {order['order_text']}\n"
                f"📍 *Адрес:* {order['address']}\n\n"
                f"💬 *Чат с менеджером закрыт*"
            )
            
            user_keyboard = telebot.types.InlineKeyboardMarkup()
            user_keyboard.row(telebot.types.InlineKeyboardButton("🔄 Сделать новый заказ", callback_data="NEW_ORDER"))
            
            bot.send_message(order['buyer_id'], final_message, reply_markup=user_keyboard)
            
            if order['buyer_id'] in active_chats:
                del active_chats[order['buyer_id']]
            
            del active_orders[order_id]
            save_data()
            
            bot.answer_callback_query(call.id, "✅ Заказ завершен")
            bot.edit_message_text(f"✅ Заказ #{order_id} завершен", user_id, call.message.message_id)
        return
    
    # Обработка выбора адреса
    address = call.data
    user_info = user_data.get(user_id)
    
    if not user_info:
        bot.answer_callback_query(call.id, "❌ Ошибка")
        return
    
    seller_name = pickup_points.get(address)
    seller_id = get_seller_id(seller_name)
    
    if seller_id:
        global order_counter
        order_counter += 1
        order_id = order_counter
        
        order_data = {
            'order_id': order_id,
            'buyer_id': user_id,
            'buyer_name': user_info['name'],
            'seller_id': seller_id,
            'seller_name': seller_name,
            'address': address,
            'order_text': user_info['text'],
            'timestamp': datetime.now().strftime("%d.%m.%Y"),
            'status': 'active'
        }
        
        active_orders[order_id] = order_data
        active_chats[user_id] = order_id
        save_data()
        
        # Отправка продавцу
        try:
            seller_message = (
                f"📦 *НОВЫЙ ЗАКАЗ #{order_id}*\n"
                f"📅 {order_data['timestamp']}\n\n"
                f"👤 *Покупатель:* {user_info['name']}\n"
                f"📍 *Точка:* {address}\n"
                f"📝 *Заказ:* {user_info['text']}"
            )
            
            seller_keyboard = telebot.types.InlineKeyboardMarkup()
            seller_keyboard.row(
                telebot.types.InlineKeyboardButton("✏️ Уточнить заказ", callback_data=f"seller_update_{order_id}"),
                telebot.types.InlineKeyboardButton("✅ Завершить заказ", callback_data=f"seller_close_{order_id}")
            )
            
            bot.send_message(seller_id, seller_message, parse_mode="Markdown", reply_markup=seller_keyboard)
            
            bot.send_message(
                chat_id,
                f"🔄 *Ваш заказ в обработке*\n\n📍 Адрес: {address}\n📝 Ваш заказ: {user_info['text']}",
                parse_mode="Markdown"
            )
            
            if ADMIN_ID:
                bot.send_message(ADMIN_ID, f"👑 *НОВЫЙ ЗАКАЗ #{order_id}*\n\n👤 Продавец: {seller_name}")
            
        except Exception as e:
            bot.send_message(chat_id, "⚠️ Заказ принят, но продавец временно недоступен")
        
        bot.answer_callback_query(call.id, f"✅ Заказ #{order_id} создан")
        
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass

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
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
