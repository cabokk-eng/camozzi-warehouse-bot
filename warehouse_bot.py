import os
import logging
import uuid
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))

# Хранилище
users = {}  # chat_id -> {'role': 'picker'/'stocker'/'admin', 'username': '@...'}
pending_requests = {}  # {req_id: {'picker_id': ..., 'position': ..., 'completed': False}}

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
    if uid == ADMIN_CHAT_ID:
        users[uid] = {'role': 'admin', 'username': username}
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add(
            "📦 Отправить позицию",
            "🛠 Активные запросы"
        )
        await message.answer("✅ Вы — админ (комплектовщик + кладовщик).", reply_markup=kb)
    else:
        users[uid] = {'role': 'picker', 'username': username}
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("📦 Отправить позицию")
        await message.answer("✅ Вы — комплектовщик.", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "📦 Отправить позицию")
async def ask_position(message: types.Message):
    await message.answer("Введите код позиции (например, `9540 1/2`):")

@dp.message_handler(content_types=types.ContentTypes.TEXT)
async def handle_text(message: types.Message):
    uid = message.from_user.id
    text = message.text.strip()

    if uid not in users:
        await message.answer("Напишите /start")
        return

    role = users[uid]['role']

    # Комплектовщик или админ отправляет позицию
    if text != "📦 Отправить позицию" and text != "🛠 Активные запросы":
        if role in ['picker', 'admin']:
            if text:
                req_id = str(uuid.uuid4())
                pending_requests[req_id] = {
                    'picker_id': uid,
                    'position': text,
                    'completed': False
                }
                await message.answer(f"✅ Запрос на пополнение `{text}` добавлен в очередь.", parse_mode="Markdown")
        return

    # Кладовщик или админ просматривает запросы
    if text == "🛠 Активные запросы":
        if role not in ['stocker', 'admin']:
            # Становимся кладовщиком
            users[uid]['role'] = 'stocker'
            role = 'stocker'

        active = [(rid, r) for rid, r in pending_requests.items() if not r['completed']]
        if not active:
            await message.answer("📭 Нет активных запросов.")
            return

        # Формируем короткий список
        lines = []
        for i, (rid, req) in enumerate(active, 1):
            picker_name = users.get(req['picker_id'], {}).get('username', 'комплектовщик')
            lines.append(f"{i}. {req['position']} ({picker_name})")

        text_list = "Запросы:\n" + "\n".join(lines)
        kb = InlineKeyboardMarkup(row_width=5)
        buttons = [
            InlineKeyboardButton(str(i), callback_data=f"take_{rid}")
            for i, (rid, _) in enumerate(active, 1)
        ]
        kb.add(*buttons)

        # Отправляем коротко, чтобы кнопки были видны
        if len(active) <= 6:
            await message.answer(text_list + "\n\n", reply_markup=kb)
        else:
            await message.answer("📬 Активные запросы:")
            await message.answer("\n".join(lines), reply_markup=kb)

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
    position = req['position']
    picker_id = req['picker_id']

    try:
        await bot.send_message(
            picker_id,
            f"✅ Позиция `{position}` пополнена.",
            parse_mode="Markdown"
        )
    except:
        pass

    await callback.answer("✅ Выполнено!")
    await bot.send_message(callback.from_user.id, f"✅ Вы пополнили: `{position}`", parse_mode="Markdown")

if __name__ == "__main__":
    print("Бот запущен...")
    executor.start_polling(dp, skip_updates=True)

