import os
import telebot
from flask import Flask, request
from datetime import datetime

# ====== НАСТРОЙКИ ======
TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не установлен!")
    exit(1)

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

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

# ФУНКЦИЯ ДЛЯ ПОЛУЧЕНИЯ ID ПРОДАВЦОВ
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

def is_seller(user_id):
    """Проверка, является ли пользователь продавцом"""
    return user_id in get_all_seller_ids()

def get_seller_active_orders(seller_id):
    """Получить все активные заказы продавца"""
    seller_orders = []
    for order_id, order in active_orders.items():
        if order['seller_id'] == seller_id:
            seller_orders.append(order_id)
    return seller_orders

# Проверяем при запуске
print("=" * 50)
print("🔍 Проверка настроек продавцов:")
for seller_name in ["Александр", "Юлия", "Евгений", "Татьяна", "Рабочий"]:
    seller_id = get_seller_id(seller_name)
    if seller_id:
        print(f"✅ {seller_name}: ID установлен")
    else:
        print(f"❌ {seller_name}: ID НЕ установлен")
print("=" * 50)

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

# ====== ОБРАБОТЧИКИ ======
@bot.message_handler(commands=['start'])
def send_welcome(message):
    show_instruction_with_keyboard(message.chat.id)

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

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Пропускаем команды, которые уже обработаны
    if text in ['Каталог с ценами', 'О нас']:
        return
    
    # Проверяем, является ли пользователь продавцом
    if is_seller(user_id):
        # Проверяем, ожидаем ли мы уточнение заказа от этого продавца
        if user_id in seller_waiting_for_order_update:
            order_id = seller_waiting_for_order_update[user_id]
            order = active_orders.get(order_id)
            
            if order:
                # Обновляем заказ
                old_order_text = order['order_text']
                order['order_text'] = text
                order['updated_at'] = datetime.now().strftime("%H:%M %d.%m.%Y")
                
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
                
                # Отправляем уведомление покупателю (это сообщение будет удалено при завершении)
                bot.send_message(
                    order['buyer_id'],
                    f"📝 *Уточненный заказ:*\n\n{text}\n\n"
                    f"📍 *Адрес:* {order['address']}\n\n"
                    f"*Отправьте сообщение, если хотите еще что-то уточнить.*",
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
                order_num = parts[0][1:]  # Убираем #
                order_id = int(order_num)
                message_text = parts[1] if len(parts) > 1 else ""
                
                if not message_text:
                    bot.send_message(user_id, "❌ Не указан текст сообщения. Формат: #номер_заказа текст_сообщения")
                    return
                
                if order_id in active_orders and active_orders[order_id]['seller_id'] == user_id:
                    order = active_orders[order_id]
                    # Отправляем сообщение покупателю (будет удалено при завершении)
                    bot.send_message(
                        order['buyer_id'],
                        f"💬 *Сообщение от менеджера:*\n\n{message_text}",
                        parse_mode="Markdown"
                    )
                    bot.send_message(user_id, f"✅ Сообщение отправлено покупателю (Заказ #{order_id})")
                else:
                    bot.send_message(user_id, f"❌ Заказ #{order_id} не найден или не принадлежит вам")
            except ValueError:
                bot.send_message(user_id, "❌ Неправильный номер заказа. Используйте числовой номер, например: #1 привет")
            except:
                bot.send_message(user_id, "❌ Неправильный формат. Используйте: #номер_заказа текст_сообщения")
        else:
            # Если продавец пишет без #, напоминаем ему о формате
            seller_active_orders = get_seller_active_orders(user_id)
            if seller_active_orders:
                bot.send_message(
                    user_id,
                    f"📋 *У вас {len(seller_active_orders)} активных заказов:*\n"
                    f"{', '.join([f'#{oid}' for oid in seller_active_orders])}\n\n"
                    f"💬 *Чтобы ответить покупателю, начните сообщение с номера заказа:*\n"
                    f"Пример: `#1 Здравствуйте! Ваш заказ будет готов через час`"
                )
            else:
                bot.send_message(user_id, "У вас нет активных заказов.")
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
            except Exception as e:
                bot.send_message(
                    user_id,
                    f"❌ Не удалось отправить сообщение"
                )
            return
        else:
            # Если заказ не найден, удаляем из активных чатов
            if user_id in active_chats:
                del active_chats[user_id]
    
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
    
    if call.data == "NEW_ORDER":
        # Покупатель хочет сделать новый заказ
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, "Напишите что хотите заказать:")
        return
    
    # Обработка кнопок продавца
    if call.data.startswith('seller_update_'):
        handle_seller_update_callback(call)
        return
    elif call.data.startswith('seller_close_'):
        handle_seller_close_callback(call)
        return
    
    # --- ОБРАБОТКА ВЫБОРА АДРЕСА (ДЛЯ ПОКУПАТЕЛЕЙ) ---
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
        
        # Сохраняем заказ
        order_data = {
            'order_id': order_id,
            'buyer_id': buyer_id,
            'buyer_name': buyer_name,
            'seller_id': seller_id,
            'seller_name': seller_name,
            'address': address,
            'order_text': user_info['text'],
            'timestamp': datetime.now().strftime("%H:%M %d.%m.%Y"),
            'updated_at': None,
            'status': 'active'
        }
        active_orders[order_id] = order_data
        
        # Активируем чат покупателя
        active_chats[buyer_id] = order_id
        
        # Сообщение продавцу с двумя кнопками
        seller_message = (
            f"📦 *НОВЫЙ ЗАКАЗ #{order_id}*\n"
            f"⏰ {datetime.now().strftime('%H:%M %d.%m.%Y')}\n\n"
            f"👤 *Покупатель:* {buyer_name}\n"
            f"📍 *Точка:* {address}\n"
            f"📝 *Заказ:* {user_info['text']}\n\n"
            f"🆔 ID покупателя: {buyer_id}"
        )
        
        # Клавиатура для продавца - ДВЕ КНОПКИ
        seller_keyboard = telebot.types.InlineKeyboardMarkup()
        seller_keyboard.row(
            telebot.types.InlineKeyboardButton("✏️ Уточнить заказ", callback_data=f"seller_update_{order_id}"),
            telebot.types.InlineKeyboardButton("✅ Завершить заказ", callback_data=f"seller_close_{order_id}")
        )
        
        # Отправляем продавцу список его активных заказов
        seller_active_orders = get_seller_active_orders(seller_id)
        if len(seller_active_orders) > 1:
            seller_message += f"\n\n📋 *Ваши активные заказы:* {', '.join([f'#{oid}' for oid in seller_active_orders])}"
        
        seller_message += "\n\n💬 *Чтобы ответить покупателю, напишите:*\n`#" + str(order_id) + " ваш_текст`"
        
        try:
            bot.send_message(seller_id, seller_message, parse_mode="Markdown", reply_markup=seller_keyboard)
            success = True
        except Exception as e:
            print(f"❌ Ошибка отправки продавцу {seller_name}: {e}")
            success = False
        
        # Сообщение покупателю - ЗАКАЗ В ОБРАБОТКЕ (будет удалено при завершении)
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
        
        # Удаляем сообщение с кнопками выбора адреса
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass
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
    
    # Проверяем, что продавец уточняет свой заказ
    if order['seller_id'] != seller_id:
        bot.answer_callback_query(call.id, "❌ Этот заказ не ваш")
        return
    
    # Устанавливаем ожидание нового текста заказа
    seller_waiting_for_order_update[seller_id] = order_id
    
    bot.answer_callback_query(call.id)
    
    # Отправляем запрос на уточнение заказа
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
    
    # Проверяем, что продавец завершает свой заказ
    if order['seller_id'] != seller_id:
        bot.answer_callback_query(call.id, "❌ Этот заказ не ваш")
        return
    
    # Завершаем заказ
    try:
        # Получаем финальный текст заказа (уточненный или оригинальный)
        final_order_text = order['order_text']
        order_date = order['updated_at'] if order['updated_at'] else order['timestamp']
        
        # Отправляем финальное сообщение покупателю
        final_message = (
            f"✅ *Заказ от {order_date}*\n\n"
            f"📝 *Содержание:* {final_order_text}\n"
            f"📍 *Адрес:* {order['address']}\n\n"
            f"💬 *Чат с менеджером закрыт*"
        )
        
        # Создаем клавиатуру с кнопкой "Сделать новый заказ"
        user_keyboard = telebot.types.InlineKeyboardMarkup()
        user_keyboard.row(
            telebot.types.InlineKeyboardButton("🔄 Сделать новый заказ", callback_data="NEW_ORDER")
        )
        
        # Отправляем финальное сообщение
        bot.send_message(
            order['buyer_id'],
            final_message,
            parse_mode="Markdown",
            reply_markup=user_keyboard
        )
        
        # Закрываем активные чаты покупателя
        if order['buyer_id'] in active_chats:
            del active_chats[order['buyer_id']]
        
        # Удаляем заказ из активных
        del active_orders[order_id]
        
        # Очищаем ожидание уточнения, если было
        if seller_id in seller_waiting_for_order_update:
            del seller_waiting_for_order_update[seller_id]
        
        # Обновляем сообщение у продавца
        try:
            bot.edit_message_text(
                f"✅ *ЗАКАЗ ЗАВЕРШЕН #{order_id}*\n\n"
                f"👤 Покупатель: {order['buyer_name']}\n"
                f"📍 Точка: {order['address']}\n"
                f"📝 Заказ: {final_order_text}\n\n"
                f"🕒 Создан: {order['timestamp']}\n"
                f"🔄 Обновлен: {order['updated_at'] if order['updated_at'] else 'нет'}\n"
                f"🏁 Завершен: {datetime.now().strftime('%H:%M %d.%m.%Y')}",
                seller_id,
                call.message.message_id,
                parse_mode="Markdown"
            )
        except:
            # Если не удалось отредактировать, отправляем новое сообщение
            bot.send_message(
                seller_id,
                f"✅ *ЗАКАЗ ЗАВЕРШЕН #{order_id}*\n\n"
                f"👤 Покупатель: {order['buyer_name']}\n"
                f"📍 Точка: {order['address']}\n"
                f"📝 Заказ: {final_order_text}\n\n"
                f"🕒 Создан: {order['timestamp']}\n"
                f"🔄 Обновлен: {order['updated_at'] if order['updated_at'] else 'нет'}\n"
                f"🏁 Завершен: {datetime.now().strftime('%H:%M %d.%m.%Y')}",
                parse_mode="Markdown"
            )
        
        # Показываем продавцу оставшиеся активные заказы
        seller_active_orders = get_seller_active_orders(seller_id)
        if seller_active_orders:
            orders_list = '\n'.join([f"• Заказ #{oid}" for oid in seller_active_orders])
            bot.send_message(
                seller_id,
                f"📋 *Осталось активных заказов: {len(seller_active_orders)}*\n\n"
                f"{orders_list}\n\n"
                f"💬 *Ответьте конкретному заказу:*\n"
                f"`#номер_заказа ваш_текст`"
            )
        else:
            bot.send_message(seller_id, "✅ Все заказы завершены!")
        
        bot.answer_callback_query(call.id, "✅ Заказ завершен, чат закрыт")
        
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
    # Устанавливаем вебхук
    bot.remove_webhook()
    
    service_name = os.environ.get('RENDER_SERVICE_NAME', 'dp-sbor')
    webhook_url = f'https://{service_name}.onrender.com/webhook'
    
    bot.set_webhook(url=webhook_url)
    print(f"✅ Вебхук установлен: {webhook_url}")
    
    # Запускаем сервер
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
