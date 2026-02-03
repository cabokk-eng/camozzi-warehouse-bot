import os
import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))

# Хранилище
users = {}  # chat_id -> {'role': 'picker'/'stocker'/'admin', 'username': '@...'}
pending_requests = {}  # request_id -> {'picker_id': ..., 'position': ..., 'stocker_id': None}

# Инициализация
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

def get_username(user):
    if user.username:
        return "@%s" % user.username
    return "%s %s" % (user.first_name or "", user.last_name or "").strip()

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    username = get_username(message.from_user)

    # Все — комплектовщики по умолчанию
    if uid == ADMIN_CHAT_ID:
        users[uid] = {'role': 'admin', 'username': username}
        await message.answer(
            "✅ Вы — админ.\n"
            "Назначайте кладовщиков: /кладовщик @user",
            reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add("📦 Отправить позицию")
        )
    else:
        users[uid] = {'role': 'picker', 'username': username}
        await message.answer(
            "✅ Вы — комплектовщик.\n"
            "Отправьте код позиции для запроса пополнения.",
            reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add("📦 Отправить позицию")
        )

@dp.message_handler(commands=["кладовщик"])
async def cmd_set_stocker(message: types.Message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Формат: /кладовщик @username")
        return
    username = parts[1]
    target_id = None
    for uid, data in users.items():
        if data.get('username') == username:
            target_id = uid
            break
    if not target_id:
        await message.answer("Пользователь %s не найден. Он должен написать боту /start." % username)
        return
    users[target_id]['role'] = 'stocker'
    await message.answer("✅ %s назначен кладовщиком." % username)

# === ОБРАБОТКА ТЕКСТА ===
@dp.message_handler(content_types=types.ContentTypes.TEXT)
async def handle_text(message: types.Message):
    uid = message.from_user.id
    text = message.text.strip()

    if uid not in users:
        await message.answer("Напишите /start")
        return

    role = users[uid]['role']
    username = users[uid]['username']

    # Админ — только управление
    if uid == ADMIN_CHAT_ID:
        return

    # Комплектовщик отправляет позицию
    if role == 'picker':
        if text == "📦 Отправить позицию":
            await message.answer("Введите код позиции (например, `9540 12`):")
            return
        # Сохраняем запрос для подтверждения
        pending_requests[uid] = {'position': text, 'confirmed': False}
        confirm_kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("✅ Да, запросить", callback_data=f"confirm_{uid}"),
            InlineKeyboardButton("❌ Отмена", callback_data="cancel")
        )
        await message.answer(
            "Вы точно хотите запросить пополнение для `%s`?" % text,
            parse_mode="Markdown",
            reply_markup=confirm_kb
        )

    # Кладовщик — только статусы
    elif role == 'stocker':
        if text.startswith("/"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await message.answer("Укажите код позиции, например:\n/пополнил 9540 12")
                return
            cmd = parts[0].lower()
            position = parts[1].strip()
            # Найти активный запрос по позиции
            req_id = None
            for rid, req in pending_requests.items():
                if req.get('position') == position and req.get('stocker_id') == uid:
                    req_id = rid
                    break
            if not req_id:
                await message.answer("Нет активного задания для `%s`." % position, parse_mode="Markdown")
                return
            picker_id = req_id
            picker_name = users.get(picker_id, {}).get('username', 'комплектовщик')
            if cmd == "/пополнил":
                reply = "✅ %s, позиция `%s` пополнена." % (picker_name, position)
            elif cmd == "/не_найден":
                reply = "❌ %s, позиция `%s` не найдена." % (picker_name, position)
            elif cmd == "/в_пути":
                reply = "🚚 %s, позиция `%s` в пути." % (picker_name, position)
            else:
                await message.answer("Команды: /пополнил, /не_найден, /в_пути")
                return
            await bot.send_message(picker_id, reply, parse_mode="Markdown")
            pending_requests.pop(req_id, None)
            await message.answer("✅ Статус отправлен.")
        else:
            await message.answer("Используйте команды:\n/пополнил [позиция]\n/не_найден [позиция]\n/в_пути [позиция]")

# === ОБРАБОТКА КНОПОК ===
@dp.callback_query_handler(lambda c: c.data.startswith("confirm_"))
async def process_confirm(callback_query: types.CallbackQuery):
    picker_id = int(callback_query.data.split("_")[1])
    if picker_id not in pending_requests:
        await callback_query.answer("Запрос устарел.", show_alert=True)
        return
    position = pending_requests[picker_id]['position']
    pending_requests[picker_id]['confirmed'] = True

    # Находим всех кладовщиков
    stockers = [uid for uid, data in users.items() if data.get('role') == 'stocker']
    if not stockers:
        await bot.send_message(picker_id, "⚠️ Нет активных кладовщиков.")
        pending_requests.pop(picker_id, None)
        return

    # Отправляем запрос каждому кладовщику с кнопкой "Взять"
    take_kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("✋ Взять в работу", callback_data=f"take_{picker_id}")
    )
    for sid in stockers:
        try:
            await bot.send_message(
                sid,
                "❗ Запрос на пополнение:\n`%s`\n(от %s)" % (position, users[picker_id]['username']),
                parse_mode="Markdown",
                reply_markup=take_kb
            )
        except:
            pass
    await bot.send_message(picker_id, "✅ Запрос отправлен кладовщикам.")
    await callback_query.answer("Запрос отправлен.")

@dp.callback_query_handler(lambda c: c.data == "cancel")
async def process_cancel(callback_query: types.CallbackQuery):
    await callback_query.answer("Отменено.")
    await bot.delete_message(callback_query.message.chat.id, callback_query.message.message_id)

@dp.callback_query_handler(lambda c: c.data.startswith("take_"))
async def process_take(callback_query: types.CallbackQuery):
    stocker_id = callback_query.from_user.id
    picker_id = int(callback_query.data.split("_")[1])

    # Проверяем, не взято ли уже
    if picker_id not in pending_requests or pending_requests[picker_id].get('stocker_id'):
        await callback_query.answer("Задание уже выполнено или взято другим.", show_alert=True)
        return

    # Назначаем кладовщика
    pending_requests[picker_id]['stocker_id'] = stocker_id
    position = pending_requests[picker_id]['position']

    # Удаляем сообщение у других кладовщиков (нельзя — но можно уведомить)
    # Вместо этого — просто подтверждаем текущему
    await bot.send_message(
        stocker_id,
        "Вы взяли в работу: `%s`\n\nТеперь отправьте:\n/пополнил %s\n/не_найден %s\n/в_пути %s" % (position, position, position, position),
        parse_mode="Markdown"
    )
    await callback_query.answer("Задание взято в работу.")

if __name__ == "__main__":
    print("Бот запущен...")
    executor.start_polling(dp, skip_updates=True)
