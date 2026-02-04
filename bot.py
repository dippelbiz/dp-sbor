import os
import telebot
from flask import Flask, request

# ====== НАСТРОЙКИ ======
TOKEN = os.environ.get('BOT_TOKEN', "8513392038:AAEupfJ198a3AtNinoAsA2h2mmtFIDLOoqk")
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Хранилище данных пользователей
user_data = {}

# Список точек и продавцов
pickup_points = {
    "ул. Галащука 15": "Александр",
    "ул. Беловежская 4/1": "Юлия", 
    "ул. Забалуева 90": "Евгений",
    "ул. Сержанта Коротаева 3": "Татьяна"
}

sellers_chat_id = {
    "Александр": 952957376,
    "Юлия": 1518506615,
    "Евгений": 5750504640,
    "Татьяна": 2051690432
}

# ====== ОБРАБОТЧИКИ ======
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message,
        "🟢 *Пошаговая инструкция:*\n\n"
        "1. Напишите, что хотите заказать\n"
        "2. Выберите адрес из списка\n"
        "3. Продавец свяжется с вами",
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    # Сохраняем данные
    user_data[message.chat.id] = {
        'text': message.text,
        'name': message.from_user.first_name,
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
        "Выберите удобный адрес:",
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    
    if call.data == "NEW_ORDER":
        bot.answer_callback_query(call.id)
        bot.edit_message_text("Новый заказ", chat_id, call.message.message_id)
        bot.send_message(chat_id, "Напишите что хотите заказать:")
        return
    
    # Обработка выбора адреса
    address = call.data
    user_info = user_data.get(chat_id)
    
    if not user_info:
        bot.answer_callback_query(call.id, "Ошибка: данные не найдены")
        return
    
    seller_name = pickup_points.get(address)
    seller_id = sellers_chat_id.get(seller_name)
    
    if seller_id:
        # Сообщение продавцу с КНОПКОЙ
        seller_message = (
            f"📦 *Новый заказ!*\n\n"
            f"👤 Покупатель: {user_info['name']}\n"
            f"📍 Точка: {address}\n"
            f"📝 Заказ: {user_info['text']}"
        )
        
        # СОЗДАЕМ КНОПКУ ДЛЯ СВЯЗИ
        seller_keyboard = telebot.types.InlineKeyboardMarkup()
        seller_keyboard.add(telebot.types.InlineKeyboardButton(
            text=f"💬 Написать {user_info['name']}",
            url=f"tg://user?id={user_info['user_id']}"
        ))
        
        # Отправляем продавцу
        bot.send_message(
            seller_id,
            seller_message,
            parse_mode="Markdown",
            reply_markup=seller_keyboard
        )
        
        # Ответ покупателю
        user_keyboard = telebot.types.InlineKeyboardMarkup()
        user_keyboard.add(telebot.types.InlineKeyboardButton(
            "🔄 Сделать новый заказ", 
            callback_data="NEW_ORDER"
        ))
        
        bot.edit_message_text(
            f"✅ Спасибо! Ваш выбор: {address}\n"
            f"Продавец свяжется с Вами в ближайшее время.",
            chat_id,
            call.message.message_id,
            reply_markup=user_keyboard
        )
        bot.answer_callback_query(call.id, "✅ Заказ отправлен!")
    else:
        bot.answer_callback_query(call.id, "❌ Ошибка")

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
    
    service_name = os.environ.get('RENDER_SERVICE_NAME', 'dp-sbor-bot')
    webhook_url = f'https://{service_name}.onrender.com/webhook'
    
    bot.set_webhook(url=webhook_url)
    print(f"✅ Вебхук установлен: {webhook_url}")
    
    # Запускаем сервер
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
