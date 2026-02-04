import os
import telebot
from flask import Flask, request

# ====== НАСТРОЙКИ ======
TOKEN = os.environ.get('BOT_TOKEN', "8513392038:AAEupfJ198a3AtNinoAsA2h2mmtFIDLOoqk")
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Хранилище данных пользователей (в памяти)
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

# ====== ОБРАБОТЧИКИ КОМАНД ======
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message,
        " 🟢*Пошаговая инструкция*🟢\n\n"
        "▪️ Напишите, что Вы хотите заказать\n"
        "✉️ *Отправьте сообщение* ✉️\n\n"
        "▪️ Появится список где можно забрать\n\n"
        "▪️ Выберите, что будет удобнее",
        parse_mode="Markdown"
    )

# Обработка текстовых сообщений
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    # Сохраняем данные пользователя
    user_data[message.chat.id] = {
        'text': message.text,
        'name': message.from_user.first_name,
        'user_id': message.from_user.id
    }
    
    # Создаем клавиатуру с кнопками адресов
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

# Обработка нажатий на кнопки
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    
    if call.data == "NEW_ORDER":
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "Сделать новый заказ.", 
            chat_id, 
            call.message.message_id
        )
        bot.send_message(
            chat_id,
            " 🟢*Пошаговая инструкция*🟢\n\n"
            "▪️ Напишите, что Вы хотите заказать\n"
            "✉️ *Отправьте сообщение* ✉️\n\n"
            "▪️ Появится список где можно забрать\n\n"
            "▪️ Выберите, что будет удобнее",
            parse_mode="Markdown"
        )
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
        # Отправляем уведомление продавцу
        bot.send_message(
            seller_id,
            f"📦 *Новый зарок!*\n\n"
            f"👤 Покупатель: {user_info['name']}\n"
            f"🔗 [Написать](tg://user?id={user_info['user_id']})\n"
            f"📍 Точка: {address}\n"
            f"📝 Сообщение: {user_info['text']}",
            parse_mode="Markdown"
        )
        
        # Подтверждение пользователю
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.add(telebot.types.InlineKeyboardButton(
            "🔄 Сделать новый заказ", 
            callback_data="NEW_ORDER"
        ))
        
        bot.edit_message_text(
            f"✅ Спасибо! Ваш выбор: {address}\n"
            f"📞 Продавец свяжется с Вами в ближайшее время в личных сообщениях ❤️.",
            chat_id,
            call.message.message_id,
            reply_markup=keyboard
        )
        bot.answer_callback_query(call.id)
    else:
        bot.answer_callback_query(call.id, "❌ Ошибка. Попробуйте позже.")

# ====== WEBHOOK ДЛЯ RENDER ======
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
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>🤖 Telegram Bot</title>
        <style>
            body { font-family: Arial; text-align: center; padding: 50px; }
            h1 { color: #0088cc; }
        </style>
    </head>
    <body>
        <h1>✅ Telegram Bot работает!</h1>
        <p>Бот запущен и готов принимать заказы.</p>
        <p>Откройте Telegram и найдите своего бота.</p>
    </body>
    </html>
    '''

# ====== ЗАПУСК СЕРВЕРА ======
if __name__ == '__main__':
    # Устанавливаем вебхук
    try:
        bot.remove_webhook()
        
        # Получаем URL из переменных окружения Render
        service_name = os.environ.get('RENDER_SERVICE_NAME', 'dp-sbor-bot')
        webhook_url = f'https://{service_name}.onrender.com/webhook'
        
        bot.set_webhook(url=webhook_url)
        print(f"✅ Вебхук установлен: {webhook_url}")
    except Exception as e:
        print(f"⚠️ Ошибка при установке вебхука: {e}")
    
    # Запускаем Flask сервер
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
