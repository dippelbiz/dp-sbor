import os
import telebot
from flask import Flask, request

# ====== НАСТРОЙКИ ======
TOKEN = "8513392038:AAEupfJ198a3AtNinoAsA2h2mmtFIDLOoqk"  # твой токен

# Список точек и продавцов
pickup_points = {
    "ул. Галащука 15": "Александр",
    "ул. Беловежская 4/1": "Юлия",
    "ул. Забалуева 90": "Евгений",
    "ул. Сержанта Коротаева 3": "Татьяна"
}

# Соответствие продавцов и их chat_id
sellers_chat_id = {
    "Александр": 952957376,  # вставь реальные chat_id
    "Юлия": 1518506615,
    "Евгений": 5750504640,
    "Татьяна": 2051690432
}

# ====== КОМАНДЫ ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
" 🟢*Пошаговая инструкция*🟢\n\n"
       "▪️ Напишите, что Вы хотите заказать\n"
       "✉️ *Отправьте сообщение* ✉️\n\n"
    "▪️ Появится список где можно забрать\n\n"
    "▪️ Выберите, что будет удобнее",
 parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['message_text'] = update.message.text
    context.user_data['user_name'] = update.message.from_user.first_name
    context.user_data['user_id'] = update.message.from_user.id

    keyboard = [[InlineKeyboardButton(point, callback_data=point)] for point in pickup_points.keys()]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Выберите удобный адрес:", reply_markup=reply_markup)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "NEW_ORDER":
        context.user_data.clear()
        await query.edit_message_text("Сделать новый заказ.")
        await start(query, context)
        return

    point = data
    message_text = context.user_data.get('message_text')
    user_name = context.user_data.get('user_name')
    user_id = context.user_data.get('user_id')

    seller_name = pickup_points.get(point)
    seller_id = sellers_chat_id.get(seller_name)

    if seller_id:
        await context.bot.send_message(
            chat_id=seller_id,
            text=f"Новый заказ!\nПокупатель: {user_name} [Написать](tg://user?id={user_id})\nТочка: {point}\nСообщение: {message_text}",
            parse_mode="Markdown"
        )

        # Кнопка "Сделать новый заказ"
        keyboard = [[InlineKeyboardButton("Сделать новый заказ", callback_data="NEW_ORDER")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            text=f"Спасибо! Ваш выбор: {point}. Продавец свяжется с Вами в ближайшее время в личных сообщениях ❤️.",
            reply_markup=reply_markup
        )
    else:
        await query.edit_message_text(text="Ошибка. Попробуйте позже.")

# ====== ЗАПУСК БОТА ======
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button))

    print("Бот запущен...")
    app.run_polling()



