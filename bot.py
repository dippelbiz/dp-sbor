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

# ====== ФУНКЦИИ ДЛЯ РАБОТЫ С ФАЙЛАМИ ======
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
        fixed_orders = 0  # Счетчик исправленных заказов
        
        for order_id_str, order in data.get('active_orders', {}).items():
            order_id = int(order_id_str)
            
            # ПРЕОБРАЗУЕМ ВСЕ ID ИЗ СТРОК В ЧИСЛА
            if 'order_id' in order:
                order['order_id'] = int(order['order_id'])
            if 'buyer_id' in order:
                order['buyer_id'] = int(order['buyer_id'])
            if 'seller_id' in order:
                order['seller_id'] = int(order['seller_id'])
            
            # ===== ВАЖНО: Добавляем поля для старых заказов =====
            changed = False
            if 'sent_to_seller' not in order:
                order['sent_to_seller'] = True  # Старые заказы считаем доставленными
                changed = True
                print(f"🛠 Добавлено поле sent_to_seller для заказа #{order_id}")
            
            if 'resend_count' not in order:
                order['resend_count'] = 0
                changed = True
            
            if changed:
                fixed_orders += 1
            # ==================================================
            
            active_orders[order_id] = order
            loaded_orders += 1
            
            # Восстанавливаем активные чаты
            if 'buyer_id' in order and order['buyer_id']:
                active_chats[order['buyer_id']] = order_id
                print(f"🔄 Восстановлен чат: покупатель {order['buyer_id']} -> заказ #{order_id}")
        
        print(f"✅ Данные загружены: {loaded_orders} активных заказов")
        if fixed_orders > 0:
            print(f"🛠 Исправлено старых заказов: {fixed_orders}")
        print(f"📊 Текущий счетчик заказов: {order_counter}")
        print(f"💬 Активных чатов восстановлено: {len(active_chats)}")
        
        # Выводим список восстановленных заказов
        if loaded_orders > 0:
            print("📋 Активные заказы:")
            for oid, ord in active_orders.items():
                status = "✅" if ord.get('sent_to_seller', True) else "❌"
                print(f"   {status} #{oid}: {ord['buyer_name']} - {ord['order_text'][:30]}...")
        
        # Сохраняем исправленные данные обратно в файл
        if fixed_orders > 0:
            save_data()
            print(f"💾 Исправленные данные сохранены в {DATA_FILE}")
        
    except Exception as e:
        print(f"❌ Ошибка загрузки данных: {e}")

# Загружаем данные при старте
load_data()

# ПРОВЕРКА: Если есть активные заказы, покажем их в логах
if active_orders:
    print(f"\n🚀 БОТ ЗАПУЩЕН С {len(active_orders)} АКТИВНЫМИ ЗАКАЗАМИ:")
    for order_id, order in active_orders.items():
        status = "✅" if order.get('sent_to_seller', True) else "❌"
        print(f"   {status} #{order_id}: {order['buyer_name']} - {order['order_text'][:50]}...")
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
    resend_text = " (ПОВТОРНАЯ ОТПРАВКА)" if order.get('sent_to_seller', False) else ""
    admin_text = "\n👑 Переотправлено администратором" if admin_id else ""
    
    seller_message = (
        f"📦 *ЗАКАЗ #{order_id}{resend_text}*\n"
        f"📅 {order['timestamp']}\n\n"
        f"👤 *Покупатель:* {order['buyer_name']}\n"
        f"📍 *Точка:* {order['address']}\n"
        f"📝 *Заказ:* {order['order_text']}{admin_text}"
    )
    
    # Клавиатура для продавца
    seller_keyboard = telebot.types.InlineKeyboardMarkup()
    seller_keyboard.row(
        telebot.types.InlineKeyboardButton("✏️ Уточнить заказ", callback_data=f"seller_update_{order_id}"),
        telebot.types.InlineKeyboardButton("✅ Завершить заказ", callback_data=f"seller_close_{order_id}")
    )
    
    try:
        # Отправляем только продавцу
        bot.send_message(
            seller_id, 
            seller_message, 
            parse_mode="Markdown", 
            reply_markup=seller_keyboard
        )
        
        # Обновляем статус заказа
        order['sent_to_seller'] = True
        order['last_resend'] = datetime.now().strftime("%d.%m.%Y %H:%M")
        order['resend_count'] = order.get('resend_count', 0) + 1
        
        # Активируем чат с покупателем (если еще не активен)
        if order['buyer_id'] not in active_chats:
            active_chats[order['buyer_id']] = order_id
        
        # Сохраняем изменения
        save_data()
        
        return {
            'success': True, 
            'seller_name': seller_name,
            'order_id': order_id
        }
        
    except Exception as e:
        error_msg = str(e)
        return {'success': False, 'error': error_msg[:100]}

# ====== КОМАНДА ДЛЯ ВОССТАНОВЛЕНИЯ СТАРЫХ ЗАКАЗОВ ======
@bot.message_handler(commands=['fix_orders'])
def fix_old_orders(message):
    """Команда для принудительного восстановления старых заказов"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(user_id, "❌ Нет прав")
        return
    
    fixed = 0
    for order_id, order in active_orders.items():
        changed = False
        if 'sent_to_seller' not in order:
            order['sent_to_seller'] = True
            changed = True
        if 'resend_count' not in order:
            order['resend_count'] = 0
            changed = True
        
        if changed:
            fixed += 1
    
    if fixed > 0:
        save_data()
        bot.send_message(
            user_id, 
            f"✅ Исправлено {fixed} старых заказов. Теперь они отображаются в админ-панели."
        )
    else:
        bot.send_message(user_id, "✅ Все заказы уже в правильном формате.")

# ====== НОВАЯ АДМИН-ПАНЕЛЬ С КНОПКОЙ "АКТИВНЫЕ ЗАКАЗЫ" ======
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    """Панель администратора с постоянными кнопками"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(user_id, "❌ У вас нет прав администратора")
        return
    
    # Создаем Reply клавиатуру (постоянные кнопки)
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
    """Показать все активные заказы"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return
    
    if not active_orders:
        bot.send_message(user_id, "📭 Нет активных заказов")
        return
    
    bot.send_message(user_id, f"📋 *Всего активных заказов: {len(active_orders)}*", parse_mode="Markdown")
    
    for order_id, order in sorted(active_orders.items()):
        # Определяем статус доставки
        sent_status = "✅" if order.get('sent_to_seller', True) else "❌"
        resend_info = f" (переотправлен {order.get('resend_count', 0)} раз)" if order.get('resend_count', 0) > 0 else ""
        
        # Информация о заказе
        order_info = (
            f"{sent_status} *Заказ #{order_id}*{resend_info}\n"
            f"📅 {order['timestamp']}\n"
            f"👤 Продавец: {order['seller_name']}\n"
            f"👤 Покупатель: {order['buyer_name']}\n"
            f"📍 {order['address']}\n"
            f"📝 {order['order_text']}\n"
        )
        
        # Если заказ не дошел, добавляем предупреждение
        if not order.get('sent_to_seller', True):
            order_info += f"⚠️ *НЕ ДОСТАВЛЕН ПРОДАВЦУ!*\n"
        
        # Кнопка переотправки для каждого заказа
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
    """Запрос номера заказа для переотправки"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return
    
    msg = bot.send_message(
        user_id,
        "🔍 Введите номер заказа для переотправки (например: 6):"
    )
    bot.register_next_step_handler(msg, process_resend_order)

def process_resend_order(message):
    """Обработка переотправки конкретного заказа"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return
    
    try:
        order_id = int(message.text.strip())
        
        if order_id not in active_orders:
            bot.send_message(user_id, f"❌ Заказ #{order_id} не найден")
            return
        
        # Переотправляем заказ
        result = resend_order_to_seller(order_id, admin_id=user_id)
        
        if result['success']:
            order = active_orders[order_id]
            bot.send_message(
                user_id,
                f"✅ Заказ #{order_id} переотправлен продавцу {result['seller_name']}\n"
                f"📦 Товар: {order['order_text'][:100]}..."
            )
        else:
            bot.send_message(
                user_id,
                f"❌ Ошибка: {result['error']}"
            )
            
    except ValueError:
        bot.send_message(user_id, "❌ Введите корректный номер заказа")

@bot.message_handler(func=lambda message: message.text == "📊 Статистика")
def admin_stats(message):
    """Статистика для админа"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return
    
    # Считаем статистику
    total_orders = len(active_orders)
    delivered = sum(1 for o in active_orders.values() if o.get('sent_to_seller', False))
    not_delivered = total_orders - delivered
    total_resends = sum(o.get('resend_count', 0) for o in active_orders.values())
    
    # По продавцам
    seller_stats = {}
    for order in active_orders.values():
        seller = order['seller_name']
        if seller not in seller_stats:
            seller_stats[seller] = {'total': 0, 'not_delivered': 0}
        seller_stats[seller]['total'] += 1
        if not order.get('sent_to_seller', False):
            seller_stats[seller]['not_delivered'] += 1
    
    report = "📊 *СТАТИСТИКА*\n\n"
    report += f"📦 Всего активных заказов: {total_orders}\n"
    report += f"✅ Доставлено продавцам: {delivered}\n"
    report += f"❌ Не доставлено: {not_delivered}\n"
    report += f"🔄 Всего переотправок: {total_resends}\n\n"
    
    report += "*По продавцам:*\n"
    for seller, stats in seller_stats.items():
        report += f"• {seller}: {stats['total']} заказов"
        if stats['not_delivered'] > 0:
            report += f" (❌ {stats['not_delivered']} не доставлено)"
        report += "\n"
    
    bot.send_message(user_id, report, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "👥 По продавцам")
def sellers_list(message):
    """Список продавцов с их заказами"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return
    
    for seller_name in pickup_points.values():
        seller_id = get_seller_id(seller_name)
        if seller_id:
            seller_orders = get_seller_active_orders(seller_id)
            
            if seller_orders:
                report = f"👤 *{seller_name}*\n"
                report += f"📍 {pickup_points.get(seller_name)}\n"
                report += f"📦 Заказов: {len(seller_orders)}\n"
                
                for order_id in seller_orders:
                    order = active_orders[order_id]
                    status = "✅" if order.get('sent_to_seller', True) else "❌"
                    report += f"  {status} #{order_id}: {order['buyer_name']} - {order['order_text'][:30]}...\n"
                
                bot.send_message(user_id, report, parse_mode="Markdown")
    
    bot.send_message(user_id, "Для переотправки используйте /admin → Активные заказы")

@bot.message_handler(func=lambda message: message.text == "🔍 Поиск по номеру")
def search_prompt(message):
    """Поиск заказа по номеру"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return
    
    msg = bot.send_message(
        user_id,
        "🔍 Введите номер заказа:"
    )
    bot.register_next_step_handler(msg, process_search)

def process_search(message):
    """Обработка поиска"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return
    
    try:
        order_id = int(message.text.strip())
        order = active_orders.get(order_id)
        
        if order:
            status = "✅ доставлен" if order.get('sent_to_seller', True) else "❌ НЕ ДОСТАВЛЕН"
            resend_info = f"\n🔄 Переотправлен: {order.get('resend_count', 0)} раз" if order.get('resend_count', 0) > 0 else ""
            
            order_info = (
                f"🔍 *Заказ #{order_id}*\n\n"
                f"📅 Создан: {order['timestamp']}\n"
                f"👤 Продавец: {order['seller_name']}\n"
                f"👤 Покупатель: {order['buyer_name']}\n"
                f"📍 Адрес: {order['address']}\n"
                f"📝 Заказ: {order['order_text']}\n"
                f"📦 Статус: {status}{resend_info}\n"
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
    """Возврат в главное меню"""
    show_instruction_with_keyboard(message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_resend_'))
def admin_resend_callback(call):
    """Переотправка заказа по кнопке"""
    user_id = call.from_user.id
    
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "❌ Нет прав")
        return
    
    order_id = int(call.data.replace('admin_resend_', ''))
    
    # Переотправляем заказ
    result = resend_order_to_seller(order_id, admin_id=user_id)
    
    if result['success']:
        order = active_orders[order_id]
        bot.answer_callback_query(
            call.id, 
            f"✅ Заказ #{order_id} переотправлен {result['seller_name']}"
        )
        
        # Обновляем сообщение с заказом
        sent_status = "✅" if order.get('sent_to_seller', True) else "❌"
        resend_info = f" (переотправлен {order.get('resend_count', 0)} раз)" if order.get('resend_count', 0) > 0 else ""
        
        new_text = (
            f"{sent_status} *Заказ #{order_id}*{resend_info}\n"
            f"📅 {order['timestamp']}\n"
            f"👤 Продавец: {order['seller_name']}\n"
            f"👤 Покупатель: {order['buyer_name']}\n"
            f"📍 {order['address']}\n"
            f"📝 {order['order_text']}\n"
            f"🔄 Переотправлено: {datetime.now().strftime('%H:%M %d.%m.%Y')}"
        )
        
        try:
            bot.edit_message_text(
                new_text,
                user_id,
                call.message.message_id,
                parse_mode="Markdown"
            )
        except:
            pass
    else:
        bot.answer_callback_query(call.id, f"❌ {result['error']}")

# ====== ОСТАЛЬНЫЕ КОМАНДЫ АДМИНА ======
@bot.message_handler(commands=['stats'])
def admin_stats_command(message):
    """Быстрая статистика"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(user_id, "❌ У вас нет прав администратора")
        return
    
    admin_stats(message)

# ====== ОБРАБОТЧИКИ ======
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
    
    # Пропускаем команды, которые уже обработаны админ-панелью
    if text in ['📋 Активные заказы', '📊 Статистика', '🔄 Переотправить заказ', 
                '👥 По продавцам', '🔍 Поиск по номеру', '🏠 Главное меню']:
        return
    
    # --- АДМИНИСТРАТОР ---
    if is_admin(user_id):
        # Админ может отвечать на любой заказ через #
        if text.startswith('#'):
            try:
                parts = text.split(' ', 1)
                order_num = parts[0][1:]
                order_id = int(order_num)
                message_text = parts[1] if len(parts) > 1 else ""
                
                if not message_text:
                    bot.send_message(user_id, "❌ Не указан текст сообщения")
                    return
                
                if order_id in active_orders:
                    order = active_orders[order_id]
                    # Отправляем сообщение покупателю
                    bot.send_message(
                        order['buyer_id'],
                        f"💬 *Сообщение от администратора:*\n\n{message_text}",
                        parse_mode="Markdown"
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
                    
            except ValueError:
                bot.send_message(user_id, "❌ Неправильный номер заказа")
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
                order_id = int(order_num)
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
                    
            except ValueError:
                bot.send_message(user_id, "❌ Неправильный номер заказа. Используйте #1, #2 и т.д.")
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
                    f"Пример: `#1 Здравствуйте! Ваш заказ будет готов через час`"
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

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
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
        
        # Генерируем ID заказа
        global order_counter
        order_counter += 1
        order_id = order_counter
        
        # Сохраняем заказ с флагом отправки
        sent_successfully = False
        try:
            # Пробуем отправить продавцу
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
            
            bot.send_message(seller_id, seller_message, parse_mode="Markdown", reply_markup=seller_keyboard)
            sent_successfully = True
            
        except Exception as e:
            print(f"❌ Ошибка отправки продавцу {seller_name}: {e}")
            sent_successfully = False
        
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
            'status': 'active',
            'sent_to_seller': sent_successfully,  # Важно! Отмечаем, дошел ли заказ
            'resend_count': 0
        }
        active_orders[order_id] = order_data
        
        # Активируем чат покупателя
        active_chats[buyer_id] = order_id
        
        # Сохраняем данные
        save_data()
        
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
        
        bot.send_message(chat_id, buyer_message, parse_mode="Markdown")
        
        # Уведомляем админа о новом заказе
        if ADMIN_ID:
            status_text = "✅" if sent_successfully else "❌ НЕ ДОСТАВЛЕН"
            bot.send_message(
                ADMIN_ID,
                f"👑 *НОВЫЙ ЗАКАЗ #{order_id}*\n\n"
                f"👤 Продавец: {seller_name}\n"
                f"👤 Покупатель: {buyer_name}\n"
                f"📍 {address}\n"
                f"📝 {user_info['text']}\n\n"
                f"📦 Статус: {status_text}",
                parse_mode="Markdown"
            )
        
        bot.answer_callback_query(call.id, f"✅ Заказ #{order_id} создан")
    else:
        bot.answer_callback_query(call.id, "❌ Ошибка: точка временно недоступна")
        print(f"❌ Не удалось получить ID продавца для {seller_name}")

def handle_seller_update_callback(call):
    """Обработка кнопки 'Уточнить заказ'"""
    seller_id = call.from_user.id
    parts = call.data.split('_')
    order_id = int(parts[2])
    
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
    order_id = int(parts[2])
    
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
        
        # Закрываем чаты
        if order['buyer_id'] in active_chats:
            del active_chats[order['buyer_id']]
        
        del active_orders[order_id]
        
        if seller_id in seller_waiting_for_order_update:
            del seller_waiting_for_order_update[seller_id]
        
        save_data()
        
        # Обновляем сообщение у продавца
        try:
            bot.edit_message_text(
                f"✅ *ЗАКАЗ ЗАВЕРШЕН #{order_id}*\n\n"
                f"👤 Покупатель: {order['buyer_name']}\n"
                f"📍 Точка: {order['address']}\n"
                f"📝 Заказ: {final_order_text}\n\n"
                f"📅 Создан: {order['timestamp']}\n"
                f"🔄 Обновлен: {order['updated_at'] if order['updated_at'] else 'нет'}\n"
                f"🏁 Завершен: {datetime.now().strftime('%d.%m.%Y')}",
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
    bot.remove_webhook()
    
    service_name = os.environ.get('RENDER_SERVICE_NAME', 'dp-sbor')
    webhook_url = f'https://{service_name}.onrender.com/webhook'
    
    bot.set_webhook(url=webhook_url)
    print(f"✅ Вебхук установлен: {webhook_url}")
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
