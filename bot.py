import os
import telebot
from flask import Flask, request

# ====== НАСТРОЙКИ ======
TOKEN = os.environ.get('BOT_TOKEN', "8513392038:AAEoKqOuaLIbNc5rcR7QT09VjQeGOpXtHiw")
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Хранилище данных пользователей
user_data = {}

# Список точек и продавцов
pickup_points = {
    "ул. Галущака 15": "Александр",
    "ул. Беловежская 4/1": "Юлия", 
    "ул. Забалуева 90": "Евгений",
    "ул. Сержанта Коротаева 3": "Татьяна",
    "ул. Бетонная 14/1": "Рабочий"
}

sellers_chat_id = {
    "Александр": 952957376,
    "Юлия": 1518506615,
    "Евгений": 5750504640,
    "Татьяна": 2051690432,
    "Рабочий": 8230946109
}

# ====== ОБРАБОТЧИКИ ======
@bot.message_handler(commands=['start'])
def send_welcome(message):
    # Создаем клавиатуру с постоянными кнопками
    main_keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    main_keyboard.row('Каталог с ценами', 'О нас')
    
    bot.send_message(
        message.chat.id,
        "🟢 *Пошаговая инструкция:*\n\n"
        "1. Напишите, что хотите заказать\n"
        "2. Выберите откуда удобнее забрать\n"
        "3. Менеджер свяжется с вами",
        parse_mode="Markdown",
        reply_markup=main_keyboard
    )

@bot.message_handler(func=lambda message: message.text == 'Каталог с ценами')
def send_catalog(message):
    catalog_text = (
        "📋 *Каталог с ценами*\n\n"
        "1. Грецкий орех очищенный, 500г - 400 ₽\n"
        "2. Миндаль золотой, 1000г - 950 ₽\n"
        "3. Кешью WW320, 1000г - 1000 ₽\n"
        "4. Манго сушеное, 500г - 250 ₽\n"
        "5. Клубника сушеная, 500г- 350 ₽\n\n"
        "*Для заказа просто напишите что Вам нужно*"
    )
    bot.send_message(message.chat.id, catalog_text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == 'О нас')
def send_about(message):
    about_text = (
        "🏢 *О нашей компании*\n\n"
        "*DP SBOR | Отборные орехи и сухофрукты • Новосибирск*\n"
        "Мы выбираем продукты по качеству, вкусу и внешнему виду, а не по минимальной цене\n"
"Всё, начиная от выбора товара, заканчивая фасовкой и упаковкой проходит жесткий контроль\n"
        "*Вы гарантированно получаете высшее качество по шикарным ценам*\n"
📍 На данный момент есть 5 точек *в Новосибирске*, где можно забрать заказ\n"
"*Наш канал: t.me/dp_sbor *"
    )
    bot.send_message(message.chat.id, about_text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    # Пропускаем команды, которые уже обработаны
    if message.text in ['Каталог с ценами', 'О нас']:
        return
    
    # Сохраняем данные
    user_data[message.chat.id] = {
        'text': message.text,
        'name': message.from_user.first_name or "Покупатель",
        'user_id': message.from_user.id
    }
    
    # Создаем кнопки с адресами
    keyboard = telebot.types.InlineKeyboardMarkup()
    for address in pickup_points.keys():
        keyboard.add(telebot.types.InlineKeyboardButton(
            text=address, 
            callback_data=address
        ))
    
    bot.send_message(
        message.chat.id, 
        "✅ Сообщение получено! Выберите удобный адрес:",
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    
    if call.data == "NEW_ORDER":
        bot.answer_callback_query(call.id)
        bot.edit_message_text("🔄 Начинаем новый заказ", chat_id, call.message.message_id)
        bot.send_message(chat_id, "Напишите что хотите заказать:")
        return
    
    # Обработка выбора адреса
    address = call.data
    user_info = user_data.get(chat_id)
    
    if not user_info:
        bot.answer_callback_query(call.id, "❌ Ошибка: начните заказ заново")
        bot.send_message(chat_id, "Пожалуйста, напишите что хотите заказать:")
        return
    
    seller_name = pickup_points.get(address)
    seller_id = sellers_chat_id.get(seller_name)
    
    if seller_id:
        # Формируем информацию о покупателе
        buyer_name = user_info['name']
        buyer_id = user_info['user_id']
        
        # Сообщение продавцу
        seller_message = (
            f"📦 НОВЫЙ ЗАКАЗ!\n\n"
            f"👤 Покупатель: {buyer_name}\n"
            f"📍 Точка: {address}\n"
            f"📝 Заказ: {user_info['text']}\n"
            f"🆔 ID: {buyer_id}\n\n"
            f"💬 Ссылка: tg://user?id={buyer_id}"
        )
        
        try:
            bot.send_message(seller_id, seller_message)
            success = True
        except Exception as e:
            print(f"Ошибка отправки продавцу: {e}")
            success = False
        
        # Ответ покупателю
        user_keyboard = telebot.types.InlineKeyboardMarkup()
        user_keyboard.add(telebot.types.InlineKeyboardButton(
            "🔄 Сделать новый заказ", 
            callback_data="NEW_ORDER"
        ))
        
        if success:
            bot.edit_message_text(
                f"✅ Заказ принят!\n\n"
                f"📍 Адрес: {address}\n"
                f"📝 Ваш заказ: {user_info['text']}\n\n"
                f"*Менеджер свяжется с Вами в ближайшее время*.",
                chat_id,
                call.message.message_id,
                parse_mode="Markdown",
                reply_markup=user_keyboard
            )
            bot.answer_callback_query(call.id, "✅ Заказ отправлен!")
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
