import os
import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))

# Хранилище
users = {}  # chat_id -> {'role': 'picker'/'stocker', 'username': '@...'}
pending_requests = {}  # picker_id -> {'position': str, 'stocker_id': int or None}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

def get_username(user):
    if user.username:
        return "@%s" % user.username
    return "%s" % (user.first_name or "User")

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    username = get_username(message.from_user)
    # Все — комплектовщики по умолчанию
    users[uid] = {'role': 'picker', 'username': username}
    kb = ReplyKeyboardMarkup(resize_keyboard=True).add("📦 Отправить позицию")
    await message.answer("✅ Вы — комплектовщик.", reply_markup=kb)

# === ОБРАБОТКА ТЕКСТА ===
@dp.message_handler(content_types=types.ContentTypes.TEXT)
async def handle_text(message: types.Message):
    uid = message.from_user.id
    text = message.text.strip()

    if uid not in users:
        await message.answer("Напишите /start")
        return

    role = users[uid]['role']

    # Комплектовщик: отправка позиции
    if role == 'picker':
        if text == "📦 Отправить позицию":
            await message.answer("Введите код позиции (например, `9540 12`):")
            return
        # Подтверждение
        confirm_kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("✅ Да", callback_data=f"confirm_{uid}_{text}"),
            InlineKeyboardButton("❌ Нет", callback_data="cancel")
        )
        await message.answer(f"Запросить пополнение для `{text}`?", parse_mode="Markdown", reply_markup=confirm_kb)

    # Кладовщик: статусы или просмотр заданий
    elif role == 'stocker':
        if text == "🛠 Мои задания":
            tasks = []
            for picker_id, req in pending_requests.items():
                if req.get('stocker_id') is None:  # ещё не взято
                    pos = req['position']
                    picker_name = users.get(picker_id, {}).get('username', 'комплектовщик')
                    tasks.append(f"❗ `{pos}` (от {picker_name})")
            if tasks:
                await message.answer("Активные запросы:\n" + "\n".join(tasks), parse_mode="Markdown")
            else:
                await message.answer("Нет активных запросов.")
        elif text.startswith("/"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await message.answer("Укажите позицию, например:\n/пополнил 9540 12")
                return
            cmd, position = parts[0].lower(), parts[1].strip()
            # Найти активный запрос по позиции, взятый этим кладовщиком
            for picker_id, req in pending_requests.items():
                if req.get('position') == position and req.get('stocker_id') == uid:
                    picker_name = users.get(picker_id, {}).get('username', 'комплектовщик')
                    if cmd == "/пополнил":
                        msg = f"✅ {picker_name}, позиция `{position}` пополнена."
                    elif cmd == "/не_найден":
                        msg = f"❌ {picker_name}, позиция `{position}` не найдена."
                    elif cmd == "/в_пути":
                        msg = f"🚚 {picker_name}, позиция `{position}` в пути."
                    else:
                        return
                    await bot.send_message(picker_id, msg, parse_mode="Markdown")
                    pending_requests.pop(picker_id, None)
                    await message.answer("✅ Статус отправлен.")
                    return
            await message.answer("Нет активного задания для этой позиции.")

# === ПОДТВЕРЖДЕНИЕ ЗАПРОСА ===
@dp.callback_query_handler(lambda c: c.data.startswith("confirm_"))
async def process_confirm(callback: types.CallbackQuery):
    _, picker_id, position = callback.data.split("_", 2)
    picker_id = int(picker_id)
    pending_requests[picker_id] = {'position': position, 'stocker_id': None}

    # Находим ВСЕХ кладовщиков
    stockers = [uid for uid, data in users.items() if data.get('role') == 'stocker']
    if not stockers:
        await bot.send_message(picker_id, "⚠️ Нет активных кладовщиков.")
        pending_requests.pop(picker_id, None)
        return

    # Отправляем уведомление КАЖДОМУ кладовщику
    take_kb = InlineKeyboardMarkup().add(InlineKeyboardButton("✋ Взять", callback_data=f"take_{picker_id}"))
    for sid in stockers:
        try:
            await bot.send_message(
                sid,
                f"❗ Запрос на пополнение:\n`{position}`\n(от {users[picker_id]['username']})",
                parse_mode="Markdown",
                reply_markup=take_kb
            )
        except:
            pass
    await bot.send_message(picker_id, "✅ Запрос отправлен кладовщикам.")
    await callback.answer("Запрос отправлен.")

@dp.callback_query_handler(lambda c: c.data.startswith("take_"))
async def process_take(callback: types.CallbackQuery):
    stocker_id = callback.from_user.id
    picker_id = int(callback.data.split("_")[1])

    if picker_id not in pending_requests:
        await callback.answer("Запрос устарел.", show_alert=True)
        return

    req = pending_requests[picker_id]
    if req['stocker_id'] is not None:
        await callback.answer("Задание уже выполнено.", show_alert=True)
        return

    req['stocker_id'] = stocker_id
    position = req['position']
    await callback.answer("Задание взято!")
    await bot.send_message(
        stocker_id,
        f"Вы взяли: `{position}`\n\nОтправьте:\n/пополнил {position}\n/не_найден {position}\n/в_пути {position}",
        parse_mode="Markdown"
    )

@dp.callback_query_handler(lambda c: c.data == "cancel")
async def cancel(callback: types.CallbackQuery):
    await callback.answer("Отменено.")
    await bot.delete_message(callback.message.chat.id, callback.message.message_id)

if __name__ == "__main__":
    print("Бот запущен...")
    executor.start_polling(dp, skip_updates=True)
