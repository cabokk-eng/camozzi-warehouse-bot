import os
import logging  # ← ЭТА СТРОКА ОБЯЗАТЕЛЬНА
import uuid
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))

users = {}
pending_requests = {}  # {req_id: {picker_id, position, completed, stocker_id}}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

def get_username(user):
    return f"@{user.username}" if user.username else user.first_name or "User"

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    users[uid] = {'role': 'picker', 'username': get_username(message.from_user)}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("📦 Отправить позицию")
    await message.answer("✅ Вы — комплектовщик.", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "📦 Отправить позицию")
async def ask_position(message: types.Message):
    await message.answer("Введите код позиции:")

@dp.message_handler(content_types=types.ContentTypes.TEXT)
async def handle_position(message: types.Message):
    uid = message.from_user.id
    if uid not in users or users[uid]['role'] != 'picker':
        return

    position = message.text.strip()
    if not position:
        return

    # Создаём запрос с уникальным ID
    req_id = str(uuid.uuid4())
    pending_requests[req_id] = {
        'picker_id': uid,
        'position': position,
        'completed': False
    }
    await message.answer(f"✅ Запрос на `{position}` добавлен.", parse_mode="Markdown")

@dp.message_handler(lambda m: m.text == "🛠 Активные запросы")
async def show_requests(message: types.Message):
    active = [(rid, r) for rid, r in pending_requests.items() if not r['completed']]
    if not active:
        await message.answer("📭 Нет активных запросов.")
        return

    text = "📬 Активные запросы:\n"
    kb = InlineKeyboardMarkup(row_width=5)
    buttons = []

    for i, (req_id, req) in enumerate(active, 1):
        picker_name = users.get(req['picker_id'], {}).get('username', 'комплектовщик')
        text += f"{i}. `{req['position']}` (от {picker_name})\n"
        buttons.append(InlineKeyboardButton(str(i), callback_data=f"take_{req_id}"))

    kb.add(*buttons)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("take_"))
async def take_request(callback: types.CallbackQuery):
    req_id = callback.data.split("_", 1)[1]
    if req_id not in pending_requests:
        await callback.answer("❌ Запрос не найден.", show_alert=True)
        return

    req = pending_requests[req_id]
    if req['completed']:
        await callback.answer("✅ Уже выполнен.", show_alert=True)
        return

    req['completed'] = True
    req['stocker_id'] = callback.from_user.id

    try:
        await bot.send_message(
            req['picker_id'],
            f"✅ Позиция `{req['position']}` пополнена.",
            parse_mode="Markdown"
        )
    except:
        pass

    await callback.answer("✅ Выполнено!")

if __name__ == "__main__":
    print("Бот запущен...")
    executor.start_polling(dp, skip_updates=True)

