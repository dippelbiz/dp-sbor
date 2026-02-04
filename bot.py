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
        'name': message.from_user.first_name or "Покупатель",
        'user_id': message.from_user.id,
        'username': message.from_user.username or ""
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
        "✅ Сообщение получено!\n\nВыберите удобный адрес для получения заказа:",
        reply_markup=keyboard
    )

# Обработка нажатий на кнопки
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    
    if call.data == "NEW_ORDER":
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "🔄 Начинаем новый заказ", 
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
        bot.answer_callback_query(call.id, "❌ Ошибка: данные не найдены. Начните заказ заново.")
        return
    
    seller_name = pickup_points.get(address)
    seller_id = sellers_chat_id.get(seller_name)
    
    if seller_id:
        # Формируем информацию о покупателе
        buyer_info = f"{user_info['name']}"
        if user_info.get('username'):
            buyer_info += f" (@{user_info['username']})"
        
        # Создаем сообщение для продавца
        seller_message = (
            f"🛒 *НОВЫЙ ЗАКАЗ!*\n\n"
            f"👤 *Покупатель:* {buyer_info}\n"
            f"📞 *ID:* `{user_info['user_id']}`\n"
            f"📍 *Точка выдачи:* {address}\n"
            f"📝 *Заказ:* {user_info['text']}\n\n"
            f"⏰ *Время:* {call.message.date.strftime('%H:%M %d.%m.%Y')}"
        )
        
        # Создаем кнопки для продавца
        seller_keyboard = telebot.types.InlineKeyboardMarkup(row_width=1)
        
        # Кнопка для связи с покупателем
        seller_keyboard.add(
            telebot.types.InlineKeyboardButton(
                text=f"💬 Написать {user_info['name']}",
                url=f"tg://user?id={user_info['user_id']}"
            )
        )
        
        # Дополнительная кнопка с копированием ID (если нужно)
        seller_keyboard.add(
            telebot.types.InlineKeyboardButton(
                text="📋 Скопировать ID покупателя",
                callback_data=f"copy_{user_info['user_id']}"
            )
        )
        
        # Отправляем уведомление продавцу
        try:
            bot.send_message(
                seller_id,
                seller_message,
                parse_mode="Markdown",
                reply_markup=seller_keyboard
            )
            seller_notified = True
        except Exception as e:
            print(f"Ошибка отправки продавцу {seller_name}: {e}")
            seller_notified = False
        
        # Подтверждение пользователю
        user_keyboard = telebot.types.InlineKeyboardMarkup()
        user_keyboard.add(
            telebot.types.InlineKeyboardButton(
                "🔄 Сделать новый заказ", 
                callback_data="NEW_ORDER"
            )
        )
        
        if seller_notified:
            confirmation_text = (
                f"✅ *Заказ принят!*\n\n"
                f"📍 *Ваш выбор:* {address}\n"
                f"📝 *Ваш заказ:* {user_info['text']}\n\n"
                f"👨‍💼 *Продавец {seller_name}* свяжется с Вами в ближайшее время в личных сообщениях.\n\n"
                f"❤️ Спасибо за заказ!"
            )
            bot.answer_callback_query(call.id, "✅ Заказ отправлен продавцу!")
        else:
            confirmation_text = (
                f"⚠️ *Заказ принят, но возникла небольшая задержка*\n\n"
                f"📍 *Ваш выбор:* {address}\n"
                f"📝 *Ваш заказ:* {user_info['text']}\n\n"
                f"Продавец получит уведомление в ближайшее время.\n"
                f"Приносим извинения за возможную задержку."
            )
            bot.answer_callback_query(call.id, "⚠️ Заказ принят, но есть задержка уведомления")
        
        bot.edit_message_text(
            confirmation_text,
            chat_id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=user_keyboard
        )
        
    else:
        bot.answer_callback_query(call.id, "❌ Ошибка: продавец не найден")
        bot.edit_message_text(
            "❌ К сожалению, выбранная точка временно недоступна.\n\n"
            "Пожалуйста, выберите другую точку или попробуйте позже.",
            chat_id,
            call.message.message_id
        )

# Обработка кнопки копирования ID (для продавца)
@bot.callback_query_handler(func=lambda call: call.data.startswith('copy_'))
def handle_copy_id(call):
    user_id = call.data.replace('copy_', '')
    bot.answer_callback_query(
        call.id,
        f"ID скопирован: {user_id}",
        show_alert=True
    )

# ====== WEBHOOK ДЛЯ RENDER ======
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>🤖 Вебхук бота</title>
            <style>
                body { font-family: Arial; text-align: center; padding: 50px; }
                .success { color: green; }
                .info { color: blue; }
            </style>
        </head>
        <body>
            <h1 class="success">✅ Вебхук активен</h1>
            <p class="info">Бот работает и готов принимать заказы</p>
            <p>Telegram: @dp_sbor_bot</p>
            <p><a href="/">На главную</a></p>
        </body>
        </html>
        '''
    
    # Обработка POST-запросов от Telegram
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
        <title>🤖 Бот приема заказов</title>
        <meta charset="utf-8">
        <style>
            body {
                font-family: 'Arial', sans-serif;
                text-align: center;
                padding: 50px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
            }
            .container {
                background: rgba(255, 255, 255, 0.1);
                backdrop-filter: blur(10px);
                padding: 40px;
                border-radius: 20px;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
                max-width: 600px;
                width: 90%;
            }
            h1 {
                font-size: 2.5em;
                margin-bottom: 20px;
                text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
            }
            .status {
                background: rgba(76, 175, 80, 0.2);
                border: 2px solid #4CAF50;
                padding: 15px;
                border-radius: 10px;
                margin: 20px 0;
                font-size: 1.2em;
            }
            .features {
                text-align: left;
                margin: 30px 0;
                background: rgba(255, 255, 255, 0.1);
                padding: 20px;
                border-radius: 10px;
            }
            .features li {
                margin: 10px 0;
                padding-left: 10px;
            }
            .button {
                display: inline-block;
                background: #4CAF50;
                color: white;
                padding: 15px 30px;
                text-decoration: none;
                border-radius: 50px;
                font-weight: bold;
                margin-top: 20px;
                transition: all 0.3s;
                border: none;
                cursor: pointer;
                font-size: 1.1em;
            }
            .button:hover {
                background: #45a049;
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(0, 0, 0, 0.3);
            }
            .telegram-icon {
                font-size: 3em;
                margin-bottom: 20px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="telegram-icon">🤖</div>
            <h1>Бот приема заказов</h1>
            
            <div class="status">
                ✅ <strong>Статус:</strong> Активен и работает 24/7
            </div>
            
            <div class="features">
                <h3>📋 Возможности бота:</h3>
                <ul>
                    <li>✅ Прием заказов от покупателей</li>
                    <li>📍 Выбор точек самовывоза</li>
                    <li>👨‍💼 Автоматическое уведомление продавцов</li>
                    <li>💬 Прямая связь продавец-покупатель</li>
                    <li>🔄 Многократные заказы</li>
                    <li>☁️ Работает в облаке 24/7</li>
                </ul>
            </div>
            
            <p>Для использования откройте Telegram и найдите бота</p>
            
            <a href="https://t.me/dp_sbor_bot" class="button" target="_blank">
                📱 Открыть в Telegram
            </a>
            
            <p style="margin-top: 30px; font-size: 0.9em; opacity: 0.8;">
                Бот работает на Render.com | Обновляется автоматически
            </p>
        </div>
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
        print(f"🤖 Бот запущен и готов к работе!")
        print(f"🔗 Ссылка на бота: https://t.me/dp_sbor_bot")
    except Exception as e:
        print(f"⚠️ Ошибка при установке вебхука: {e}")
    
    # Запускаем Flask сервер
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
