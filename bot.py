import os
import telebot
from flask import Flask, request

# ====== НАСТРОЙКИ ======
TOKEN = os.environ.get('BOT_TOKEN', "8513392038:AAEupfJ198a3AtNinoAsA2h2mmtFIDLOoqk")
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

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
def start(message):
    bot.reply_to(message,
        " 🟢*Пошаговая инструкция*🟢\n\n"
        "▪️ Напишите, что Вы хотите заказать\n"
        "✉️ *Отправьте сообщение* ✉️\n\n"
        "▪️ Появится список где можно забрать\n\n"
        "▪️ Выберите, что будет удобнее",
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    from telebot import types
    
    # Сохраняем данные
    bot.user_data = getattr(bot, 'user_data', {})
    bot.user_data[message.chat.id] = {
        'text': message.text,
        'name': message.from_user.first_name,
        'id': message.from_user.id
    }
    
    # Создаем клавиатуру с адресами
    keyboard = types.InlineKeyboardMarkup()
    for point in pickup_points.keys():
        keyboard.add(types.InlineKeyboardButton(point, callback_data=point))
    
    bot.reply_to(message, "Выберите удобный адрес:", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == "NEW_ORDER":
        bot.answer_callback_query(call.id)
        bot.edit_message_text("Сделать новый заказ.", call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id,
            " 🟢*Пошаговая инструкция*🟢\n\n"
            "▪️ Напишите, что Вы хотите заказать\n"
            "✉️ *Отправьте сообщение* ✉️\n\n"
            "▪️ Появится список где можно забрать\n\n"
            "▪️ Выберите, что будет удобнее",
            parse_mode="Markdown"
        )
        return
    
    point = call.data
    user_data = getattr(bot, 'user_data', {}).get(call.message.chat.id, {})
    
    seller_name = pickup_points.get(point)
    seller_id = sellers_chat_id.get(seller_name)
    
    if seller_id and user_data:
        bot.send_message(
            seller_id,
            f"Новый заказ!\nПокупатель: {user_data['name']} [Написать](tg://user?id={user_data['id']})\n"
            f"Точка: {point}\nСообщение: {user_data['text']}",
            parse_mode="Markdown"
        )
        
        # Кнопка для нового заказа
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Сделать новый заказ", callback_data="NEW_ORDER"))
        
        bot.edit_message_text(
            f"Спасибо! Ваш выбор: {point}. Продавец свяжется с Вами в ближайшее время в личных сообщениях ❤️.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
    else:
        bot.answer_callback_query(call.id, "Ошибка. Попробуйте позже.")

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
    return '🤖 Бот работает! Откройте Telegram и найдите бота.'

@app.route('/set_webhook')
def set_webhook():
    bot.remove_webhook()
    service_name = os.environ.get('RENDER_SERVICE_NAME', 'dp-sbor-bot')
    webhook_url = f'https://{service_name}.onrender.com/webhook'
    bot.set_webhook(url=webhook_url)
    return f'✅ Webhook установлен: {webhook_url}'

# ====== ЗАПУСК ======
if __name__ == '__main__':
    # Устанавливаем вебхук
    service_name = os.environ.get('RENDER_SERVICE_NAME', 'dp-sbor-bot')
    webhook_url = f'https://{service_name}.onrender.com/webhook'
    bot.remove_webhook()
    bot.set_webhook(url=webhook_url)
    print(f"✅ Webhook установлен: {webhook_url}")
    
    # Запускаем Flask
    app.run(host='0.0.0.0', port=10000, debug=False)

