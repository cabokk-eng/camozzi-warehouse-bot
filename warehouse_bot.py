import os
import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))

# Хранилище
users = {}  # chat_id -> {'role': 'picker'/'stocker', 'username': '@...'}
pending_requests = {}  # request_id (int) -> { 'picker_id': ..., 'position': ..., 'stocker_id': None or int }

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

def get_username(user):
    if user.username:
        return "@%s" % user.username
    return "%s" % (user.first_name or "User")

def main_menu(role):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if role == 'picker':
        kb.add("📦 Отправить позицию", "📋 Мои запросы")
    elif role == 'stocker':
        kb.add("🛠 Активные запросы")
    return kb

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    username = get_username(message.from_user)
    users[uid] = {'role': 'picker', 'username': username}
    await message.answer(
        "✅ Вы — комплектовщик.\n\n"
        "Если вы кладовщик — напишите админу, чтобы он дал вам роль.",
        reply_markup=main_menu('picker')
    )

# === КОМПЛЕКТОВЩИК: ОТПРАВКА ПОЗИЦИИ ===
@dp.message_handler(lambda m: m.text == "📦 Отправить позицию")
async def ask_position(message: types.Message):
    await message.answer("Введите код позиции (например, `9540 12`):")

@dp.message_handler(lambda m: m.text not in ["📦 Отправить позицию", "📋 Мои запросы", "🛠 Активные запросы"])
async def handle_position_input(message: types.Message):
    uid = message.from_user.id
    if uid not in users or users[uid]['role'] != 'picker':
        return
    position = message.text.strip()
    if not position:
        return

    # Генерируем уникальный ID запроса
    req_id = len(pending_requests) + 1
    pending_requests[req_id] = {
        'picker_id': uid,
        'position': position,
        'stocker_id': None
    }

    # Уведомление
    await message.answer(
        f"✅ Запрос на пополнение `{position}` добавлен в очередь.\n"
        f"Как только появится кладовщик — он увидит ваш запрос.",
        parse_mode="Markdown"
    )

# === КОМПЛЕКТОВЩИК: МОИ ЗАПРОСЫ ===
@dp.message_handler(lambda m: m.text == "📋 Мои запросы")
async def my_requests(message: types.Message):
    uid = message.from_user.id
    my_reqs = [
        (rid, req) for rid, req in pending_requests.items()
        if req['picker_id'] == uid and req['stocker_id'] is None
    ]
    if not my_reqs:
        await message.answer("📭 У вас нет активных запросов.")
        return

    text = "📬 Ваши запросы:\n"
    for rid, req in my_reqs:
        text += f"{rid}. `{req['position']}`\n"
    text += "\nОтправьте номер запроса, чтобы отменить его."
    await message.answer(text, parse_mode="Markdown")

@dp.message_handler(lambda m: m.text.isdigit())
async def cancel_request_by_id(message: types.Message):
    uid = message.from_user.id
    req_id = int(message.text)
    if req_id not in pending_requests:
        return
    req = pending_requests[req_id]
    if req['picker_id'] != uid:
        return
    if req['stocker_id'] is not None:
        await message.answer("❌ Этот запрос уже взят в работу.")
        return
    pending_requests.pop(req_id, None)
    await message.answer(f"✅ Запрос №{req_id} отменён.")

# === КЛАДОВЩИК: АКТИВНЫЕ ЗАПРОСЫ ===
@dp.message_handler(lambda m: m.text == "🛠 Активные запросы")
async def stocker_requests(message: types.Message):
    uid = message.from_user.id
    if uid not in users or users[uid]['role'] != 'stocker':
        # Делаем пользователя кладовщиком при первом нажатии
        users[uid] = {'role': 'stocker', 'username': get_username(message.from_user)}
        await message.answer("✅ Теперь вы — кладовщик.", reply_markup=main_menu('stocker'))

    active_reqs = [
        (rid, req) for rid, req in pending_requests.items() if req['stocker_id'] is None
    ]
    if not active_reqs:
        await message.answer("📭 Нет активных запросов.")
        return

    text = "📬 Активные запросы:\n"
    for rid, req in active_reqs:
        picker_name = users.get(req['picker_id'], {}).get('username', 'комплектовщик')
        text += f"{rid}. `{req['position']}` (от {picker_name})\n"
    text += "\nНажмите на номер запроса, чтобы взять его в работу."
    await message.answer(text, parse_mode="Markdown")

@dp.message_handler(lambda m: m.text.isdigit())
async def take_request_by_id(message: types.Message):
    uid = message.from_user.id
    if uid not in users or users[uid]['role'] != 'stocker':
        return
    req_id = int(message.text)
    if req_id not in pending_requests:
        return
    req = pending_requests[req_id]
    if req['stocker_id'] is not None:
        await message.answer("❌ Этот запрос уже взят другим кладовщиком.")
        return

    req['stocker_id'] = uid
    picker_id = req['picker_id']
    position = req['position']

    # Уведомляем комплектовщика
    try:
        await bot.send_message(
            picker_id,
            f"🛠 Кладовщик взял в работу запрос на `{position}`.",
            parse_mode="Markdown"
        )
    except:
        pass

    await message.answer(
        f"✅ Вы взяли в работу запрос №{req_id} (`{position}`).\n"
        f"Теперь отправьте:\n/пополнил {position}\n/не_найден {position}\n/в_пути {position}",
        parse_mode="Markdown"
    )

# === СТАТУСЫ ОТ КЛАДОВЩИКА ===
@dp.message_handler(content_types=types.ContentTypes.TEXT)
async def handle_text(message: types.Message):
    uid = message.from_user.id
    text = message.text.strip()
    if not text.startswith("/"):
        return

    if uid not in users or users[uid]['role'] != 'stocker':
        return

    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return
    cmd, position = parts[0].lower(), parts[1].strip()

    # Найти активный запрос по позиции и кладовщику
    req_found = None
    for rid, req in pending_requests.items():
        if req.get('stocker_id') == uid and req.get('position') == position:
            req_found = (rid, req)
            break

    if not req_found:
        await message.answer("❌ Нет активного задания для этой позиции.")
        return

    rid, req = req_found
    picker_id = req['picker_id']
    picker_name = users.get(picker_id, {}).get('username', 'комплектовщик')

    if cmd == "/пополнил":
        msg = f"✅ {picker_name}, позиция `{position}` пополнена."
    elif cmd == "/не_найден":
        msg = f"❌ {picker_name}, позиция `{position}` не найдена."
    elif cmd == "/в_пути":
        msg = f"🚚 {picker_name}, позиция `{position}` в пути."
    else:
        return

    try:
        await bot.send_message(picker_id, msg, parse_mode="Markdown")
    except:
        pass

    pending_requests.pop(rid, None)
    await message.answer("✅ Статус отправлен.")

if __name__ == "__main__":
    print("Бот запущен...")
    executor.start_polling(dp, skip_updates=True)

