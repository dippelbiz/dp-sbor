import os
import telebot
from flask import Flask, request
from datetime import datetime
import json

TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не установлен!")
    exit(1)

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

DATA_FILE = 'bot_data.json'
ADMIN_ID = os.environ.get('ADMIN_ID')
if ADMIN_ID:
    ADMIN_ID = int(ADMIN_ID)

# ====== ДАННЫЕ ======
user_data = {}
seller_counters = {'Александр': 0, 'Евгений': 0, 'Юлия': 0, 'Татьяна': 0, 'Рабочий': 0}
seller_prefixes = {"Александр": "А", "Евгений": "Е", "Юлия": "Ю", "Татьяна": "Т", "Рабочий": "Р"}
active_orders = {}
completed_orders = {}
active_chats = {}
seller_waiting = {}

pickup_points = {
    "ул. Галущака 15": "Александр",
    "ул. Беловежская 4/1": "Юлия",
    "ул. Забалуева 90": "Евгений",
    "ул. Сержанта Коротаева 3": "Татьяна",
    "ул. Бетонная 14/1": "Рабочий"
}

# ====== ФУНКЦИИ ======
def save_data():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'seller_counters': seller_counters,
            'active_orders': active_orders,
            'completed_orders': completed_orders,
            'active_chats': active_chats,
            'seller_waiting': seller_waiting
        }, f, ensure_ascii=False, indent=2)

def load_data():
    global seller_counters, active_orders, completed_orders, active_chats, seller_waiting
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            seller_counters = data.get('seller_counters', seller_counters)
            active_orders = data.get('active_orders', {})
            completed_orders = data.get('completed_orders', {})
            active_chats = data.get('active_chats', {})
            seller_waiting = data.get('seller_waiting', {})

load_data()

def get_seller_id(seller_name):
    return os.environ.get(f"Seller_{seller_name}")

def get_seller_prefix(seller_name):
    return seller_prefixes.get(seller_name, "?")

def generate_order_ref(seller_name):
    seller_counters[seller_name] = seller_counters.get(seller_name, 0) + 1
    return f"{get_seller_prefix(seller_name)}{seller_counters[seller_name]}"

def is_seller(user_id):
    for seller in pickup_points.values():
        if str(user_id) == get_seller_id(seller):
            return True
    return False

def get_seller_name_by_id(user_id):
    for seller in pickup_points.values():
        if str(user_id) == get_seller_id(seller):
            return seller
    return None

# ====== КЛАВИАТУРЫ ======
def main_keyboard():
    kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row('📋 Каталог с ценами', '🏢 О нас')
    kb.row('👤 Связаться с админом')
    return kb

def address_keyboard():
    kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for address in pickup_points.keys():
        kb.add(address)
    return kb

# ====== ПОКУПАТЕЛЬ ======
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "🟢 *Пошаговая инструкция:*\n\n1. Напишите, что хотите заказать\n2. Выберите откуда удобнее забрать\n3. Менеджер свяжется с вами",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

@bot.message_handler(func=lambda m: m.text == '📋 Каталог с ценами')
def catalog(message):
    bot.send_message(
        message.chat.id,
        "📋 *Каталог с ценами*\n\n1. Грецкий орех очищенный, 500г - 400 ₽\n2. Миндаль золотой, 1000г - 950 ₽\n3. Кешью WW320, 1000г - 1000 ₽\n4. Манго сушеное, 500г - 250 ₽\n5. Клубника сушеная, 500г - 350 ₽",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

@bot.message_handler(func=lambda m: m.text == '🏢 О нас')
def about(message):
    bot.send_message(
        message.chat.id,
        "🏢 *О нашей компании*\n\nDP SBOR | Отборные орехи и сухофрукты • Новосибирск",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

@bot.message_handler(func=lambda m: m.text == '👤 Связаться с админом')
def contact_admin(message):
    if ADMIN_ID:
        kb = telebot.types.InlineKeyboardMarkup()
        kb.add(telebot.types.InlineKeyboardButton("👤 Написать администратору", url=f"tg://user?id={ADMIN_ID}"))
        bot.send_message(message.chat.id, "Нажмите кнопку ниже:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in pickup_points.keys())
def address_selected(message):
    user_id = message.from_user.id
    address = message.text
    
    if user_id not in user_data:
        bot.send_message(user_id, "Сначала напишите, что хотите заказать")
        return
    
    seller_name = pickup_points[address]
    seller_id = get_seller_id(seller_name)
    
    if not seller_id:
        bot.send_message(user_id, "Ошибка, попробуйте позже")
        return
    
    order_ref = generate_order_ref(seller_name)
    
    order_data = {
        'order_ref': order_ref,
        'buyer_id': user_id,
        'buyer_name': user_data[user_id]['name'],
        'seller_id': int(seller_id),
        'seller_name': seller_name,
        'address': address,
        'order_text': user_data[user_id]['text'],
        'timestamp': datetime.now().strftime("%d.%m.%Y %H:%M")
    }
    
    active_orders[order_ref] = order_data
    active_chats[user_id] = order_ref
    
    bot.send_message(
        user_id,
        f"🔄 *Ваш заказ в обработке*\n\n📍 Адрес: {address}\n📝 Ваш заказ: {user_data[user_id]['text']}\n\nМенеджер скоро свяжется",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    
    # Отправляем продавцу
    seller_msg = f"📦 *НОВЫЙ ЗАКАЗ {order_ref}*\n\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n👤 Покупатель: {user_data[user_id]['name']}\n📍 {address}\n📝 {user_data[user_id]['text']}"
    
    bot.send_message(int(seller_id), seller_msg, parse_mode="Markdown")
    bot.send_message(int(seller_id), f"💬 Чтобы ответить: #{order_ref} ваш текст")
    
    del user_data[user_id]
    save_data()

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    user_id = message.from_user.id
    
    # Если есть активный заказ - пересылаем продавцу
    if user_id in active_chats:
        order_ref = active_chats[user_id]
        order = active_orders.get(order_ref)
        if order:
            bot.send_message(
                order['seller_id'],
                f"📩 *От {order['buyer_name']} (Заказ {order_ref}):*\n\n{message.text}",
                parse_mode="Markdown"
            )
            bot.send_message(user_id, "✅ Сообщение отправлено")
        return
    
    # Новый заказ
    user_data[user_id] = {
        'text': message.text,
        'name': message.from_user.first_name or "Покупатель"
    }
    
    bot.send_message(
        user_id,
        "✅ Сообщение получено! Выберите адрес:",
        reply_markup=address_keyboard()
    )

# ====== ПРОДАВЕЦ ======
@bot.message_handler(func=lambda m: is_seller(m.from_user.id) and m.text.startswith('#'))
def seller_reply(message):
    seller_id = message.from_user.id
    text = message.text
    
    if ' ' not in text:
        bot.send_message(seller_id, "❌ Формат: #А1 текст")
        return
    
    ref, reply_text = text[1:].split(' ', 1)
    
    if ref not in active_orders:
        bot.send_message(seller_id, f"❌ Заказ {ref} не найден")
        return
    
    order = active_orders[ref]
    
    if order['seller_id'] != seller_id:
        bot.send_message(seller_id, f"❌ Это не ваш заказ")
        return
    
    bot.send_message(
        order['buyer_id'],
        f"💬 *Сообщение от менеджера:*\n\n{reply_text}",
        parse_mode="Markdown"
    )
    
    bot.send_message(seller_id, f"✅ Отправлено (Заказ {ref})")

@bot.message_handler(func=lambda m: is_seller(m.from_user.id))
def seller_help(message):
    seller_id = message.from_user.id
    orders = [ref for ref, o in active_orders.items() if o['seller_id'] == seller_id]
    
    if orders:
        text = "📋 *Ваши заказы:*\n"
        for ref in orders:
            text += f"• #{ref}\n"
        text += "\n💬 Чтобы ответить: #А1 текст"
        bot.send_message(seller_id, text, parse_mode="Markdown")
    else:
        bot.send_message(seller_id, "📋 Нет активных заказов")

# ====== АДМИН (упрощенно) ======
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    text = "👑 *Активные заказы:*\n"
    for ref, order in active_orders.items():
        text += f"• {ref} - {order['buyer_name']} - {order['order_text'][:30]}...\n"
    
    text += "\n📜 *Завершенные:*\n"
    for ref, order in list(completed_orders.items())[-5:]:
        text += f"• {ref} - {order['buyer_name']}\n"
    
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# ====== WEBHOOK ======
@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
        bot.process_new_updates([update])
        return ''
    return 'Bad Request', 400

@app.route('/')
def index():
    return 'Бот работает'

if __name__ == '__main__':
    bot.remove_webhook()
    service_name = os.environ.get('RENDER_SERVICE_NAME', 'dp-sbor')
    bot.set_webhook(url=f'https://{service_name}.onrender.com/webhook')
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
