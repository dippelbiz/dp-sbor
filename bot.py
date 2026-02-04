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
    # Сохраняем данные с проверкой на None
    user_name = message.from_user.first_name or "Покупатель"
    user_id = message.from_user.id
    username = message.from_user.username or ""  # Если username нет, будет пустая строка
    
    user_data[message.chat.id] = {
        'text': message.text,
        'name': user_name,
        'user_id': user_id,
        'username': username  # Может быть пустой строкой
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
        "✅ Сообщение получено!\n\nВыберите удобный адрес:",
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
        
        # Сообщение продавцу с КНОПКОЙ
        seller_message = (
            f"📦 *НОВЫЙ ЗАКАЗ!*\n\n"
            f"👤 *Покупатель:* {buyer_name}\n"
            f"📍 *Точка:* {address}\n"
            f"📝 *Заказ:* {user_info['text']}\n"
            f"🆔 *ID:* `{buyer_id}`"
        )
        
        # СОЗДАЕМ КНОПКУ ДЛЯ СВЯЗИ (работает даже без username)
        seller_keyboard = telebot.types.InlineKeyboardMarkup()
        seller_keyboard.add(telebot.types.InlineKeyboardButton(
            text=f"💬 Написать {buyer_name}",
            url=f"tg://user?id={buyer_id}"  # Эта ссылка работает по ID, не нужен username
        ))
        
        # Отправляем продавцу
        try:
            bot.send_message(
                seller_id,
                seller_message,
                parse_mode="Markdown",
                reply_markup=seller_keyboard
            )
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
                f"✅ *Заказ принят!*\n\n"
                f"📍 *Адрес:* {address}\n"
                f"📝 *Ваш заказ:* {user_info['text']}\n\n"
                f"Продавец *{seller_name}* свяжется с Вами в ближайшее время.",
                chat_id,
                call.message.message_id,
                parse_mode="Markdown",
                reply_markup=user_keyboard
            )
            bot.answer_callback_query(call.id, "✅ Заказ отправлен продавцу!")
        else:
            bot.edit_message_text(
                f"⚠️ *Заказ принят, но возникла задержка*\n\n"
                f"Продавец получит уведомление в ближайшее время.",
                chat_id,
                call.message.message_id,
                reply_markup=user_keyboard
            )
            bot.answer_callback_query(call.id, "⚠️ Заказ принят, но есть задержка")
    else:
        bot.answer_callback_query(call.id, "❌ Ошибка: точка временно недоступна")
        bot.edit_message_text(
            "❌ Выбранная точка временно недоступна.\nПожалуйста, выберите другую.",
            chat_id,
            call.message.message_id
        )

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
