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
active_chats = {}   # Активные чаты {buyer_id: order_id} и {seller_id: order_id}

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
    
    # Пропускаем команды, которые уже обработаны
    if message.text in ['Каталог с ценами', 'О нас']:
        return
    
    # Проверяем, является ли пользователь продавцом
    if is_seller(user_id):
        # Проверяем, ведет ли продавец активный чат
        if user_id in active_chats:
            order_id = active_chats[user_id]
            order = active_orders.get(order_id)
            
            if order:
                # Отправляем сообщение покупателю
                try:
                    bot.send_message(
                        order['buyer_id'],
                        f"💬 *Сообщение от менеджера:*\n\n{message.text}",
                        parse_mode="Markdown"
                    )
                    bot.send_message(
                        user_id,
                        f"✅ Сообщение отправлено покупателю"
                    )
                except Exception as e:
                    bot.send_message(
                        user_id,
                        f"❌ Не удалось отправить сообщение"
                    )
                return
        
        # Если продавец не в активном чате, игнорируем сообщение
        bot.send_message(
            user_id,
            "Вы не ведете активный чат. Дождитесь нового заказа."
        )
        return
    
    # --- ПОКУПАТЕЛЬ ---
    # Проверяем, ведет ли покупатель активный чат
    if user_id in active_chats:
        order_id = active_chats[user_id]
        order = active_orders.get(order_id)
        
        if order:
            # Отправляем сообщение продавцу С КНОПКОЙ "Завершить заказ"
            try:
                seller_keyboard = telebot.types.InlineKeyboardMarkup()
                seller_keyboard.row(
                    telebot.types.InlineKeyboardButton("✅ Завершить заказ", callback_data=f"seller_close_{order_id}")
                )
                
                bot.send_message(
                    order['seller_id'],
                    f"📩 *Сообщение от покупателя:*\n\n"
                    f"👤 {order['buyer_name']}\n"
                    f"📝 Заказ: {order['order_text']}\n\n"
                    f"💬 {message.text}",
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
    
    # --- НОВЫЙ ЗАКАЗ ОТ ПОКУПАТЕЛЯ ---
    # Сохраняем данные
    user_data[user_id] = {
        'text': message.text,
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
        # Сбрасываем активный чат для покупателя
        if user_id in active_chats:
            del active_chats[user_id]
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text("🔄 Начинаем новый заказ", chat_id, call.message.message_id)
        bot.send_message(chat_id, "Напишите что хотите заказать:")
        return
    
    # Обработка кнопки "Завершить заказ"
    if call.data.startswith('seller_close_'):
        handle_seller_callback(call)
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
            'status': 'active'
        }
        active_orders[order_id] = order_data
        
        # Активируем чаты
        active_chats[buyer_id] = order_id
        active_chats[seller_id] = order_id
        
        # Сообщение продавцу С КНОПКОЙ "Завершить заказ"
        seller_message = (
            f"📦 *НОВЫЙ ЗАКАЗ #{order_id}*\n"
            f"⏰ {datetime.now().strftime('%H:%M %d.%m.%Y')}\n\n"
            f"👤 *Покупатель:* {buyer_name}\n"
            f"📍 *Точка:* {address}\n"
            f"📝 *Заказ:* {user_info['text']}\n\n"
            f"🆔 ID покупателя: {buyer_id}\n\n"
            f"💬 *Чат активирован!*\n"
            f"Теперь вы можете общаться с покупателем.\n"
            f"Просто напишите сообщение - оно отправится покупателю."
        )
        
        # Клавиатура для продавца
        seller_keyboard = telebot.types.InlineKeyboardMarkup()
        seller_keyboard.row(
            telebot.types.InlineKeyboardButton("✅ Завершить заказ", callback_data=f"seller_close_{order_id}")
        )
        
        try:
            bot.send_message(seller_id, seller_message, parse_mode="Markdown", reply_markup=seller_keyboard)
            success = True
        except Exception as e:
            print(f"❌ Ошибка отправки продавцу {seller_name}: {e}")
            success = False
        
        # Сообщение покупателю
        buyer_message = (
            f"✅ *Заказ принят!*\n\n"
            f"📍 Адрес: {address}\n"
            f"📝 Ваш заказ: {user_info['text']}\n\n"
            f"💬 *Чат с менеджером открыт!*\n"
            f"Теперь вы можете общаться с менеджером.\n"
            f"Просто напишите сообщение - оно отправится менеджеру."
        )
        
        user_keyboard = telebot.types.InlineKeyboardMarkup()
        user_keyboard.add(telebot.types.InlineKeyboardButton(
            "🔄 Сделать новый заказ", 
            callback_data="NEW_ORDER"
        ))
        
        if success:
            bot.edit_message_text(
                buyer_message,
                chat_id,
                call.message.message_id,
                parse_mode="Markdown",
                reply_markup=user_keyboard
            )
            bot.answer_callback_query(call.id, "✅ Заказ отправлен! Можете общаться с менеджером")
        else:
            bot.edit_message_text(
                f"⚠️ Заказ принят, но продавец пока не получил уведомление.",
                chat_id,
                call.message.message_id,
                reply_markup=user_keyboard
            )
            bot.answer_callback_query(call.id, "⚠️ Задержка с уведомлением")
    else:
        bot.answer_callback_query(call.id, "❌ Ошибка: точка временно недоступна")
        print(f"❌ Не удалось получить ID продавца для {seller_name}")

def handle_seller_callback(call):
    """Обработка действий продавца"""
    seller_id = call.from_user.id
    parts = call.data.split('_')
    order_id = int(parts[2])
    
    order = active_orders.get(order_id)
    
    if not order:
        bot.answer_callback_query(call.id, "❌ Заказ не найден")
        return
    
    # Завершаем заказ
    try:
        # Отправляем финальное сообщение покупателю
        bot.send_message(
            order['buyer_id'],
            f"✅ *Ваш заказ принят и завершен!*\n\n"
            f"📍 Адрес получения: {order['address']}\n"
            f"📝 Ваш заказ: {order['order_text']}\n\n"
            f"Заказ готов к выдаче!\n"
            f"Спасибо за покупку! 🛍️\n\n"
            f"💬 *Чат с менеджером закрыт*",
            parse_mode="Markdown"
        )
        
        # Даем покупателю кнопку для нового заказа
        user_keyboard = telebot.types.InlineKeyboardMarkup()
        user_keyboard.add(telebot.types.InlineKeyboardButton(
            "🔄 Сделать новый заказ", 
            callback_data="NEW_ORDER"
        ))
        
        bot.send_message(
            order['buyer_id'],
            "Хотите сделать еще один заказ?",
            reply_markup=user_keyboard
        )
        
        # Закрываем активные чаты
        if order['buyer_id'] in active_chats:
            del active_chats[order['buyer_id']]
        if seller_id in active_chats:
            del active_chats[seller_id]
        
        # Удаляем заказ из активных
        del active_orders[order_id]
        
        # Обновляем последнее сообщение продавца
        try:
            bot.edit_message_text(
                f"✅ *ЗАКАЗ ЗАВЕРШЕН #{order_id}*\n\n"
                f"👤 Покупатель: {order['buyer_name']}\n"
                f"📍 Точка: {order['address']}\n"
                f"📝 Заказ: {order['order_text']}\n\n"
                f"🕒 Создан: {order['timestamp']}\n"
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
                f"📝 Заказ: {order['order_text']}\n\n"
                f"🕒 Создан: {order['timestamp']}\n"
                f"🏁 Завершен: {datetime.now().strftime('%H:%M %d.%m.%Y')}",
                parse_mode="Markdown"
            )
        
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
