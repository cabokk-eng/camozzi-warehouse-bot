import os
import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))

# Хранилище
users = {}  # chat_id -> {'role': 'picker'/'stocker'/'admin', 'username': '@...'}
pending_requests = []  # [{'picker_id': ..., 'position': str}, ...]

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

@dp.message_handler(lambda m: m.text not in ["📦 Отправить позицию", "🛠 Активные запросы"])
async def handle_position_input(message: types.Message):
    uid = message.from_user.id
    role = users.get(uid, {}).get('role')
    if role in ['picker', 'admin']:
        position = message.text.strip()
        if position:
            pending_requests.append({'picker_id': uid, 'position': position})
            await message.answer(f"✅ Запрос на пополнение `{position}` добавлен в очередь.", parse_mode="Markdown")
    else:
        await message.answer("Вы не можете отправлять запросы.")

@dp.message_handler(lambda m: m.text == "🛠 Активные запросы")
async def show_requests(message: types.Message):
    uid = message.from_user.id
    role = users.get(uid, {}).get('role')
    if role not in ['stocker', 'admin']:
        # Делаем пользователя кладовщиком при первом нажатии
        users[uid] = {'role': 'stocker', 'username': get_username(message.from_user)}
        role = 'stocker'

    if not pending_requests:
        await message.answer("📭 Нет активных запросов.")
        return

    text = "📬 Активные запросы:\n"
    for i, req in enumerate(pending_requests, 1):
        picker_name = users.get(req['picker_id'], {}).get('username', 'комплектовщик')
        text += f"{i}. `{req['position']}` (от {picker_name})\n"

    # Кнопки: 1, 2, 3...
    kb = InlineKeyboardMarkup(row_width=5)
    buttons = [InlineKeyboardButton(str(i), callback_data=f"fulfill_{i}") for i in range(1, min(len(pending_requests) + 1, 21))]
    kb.add(*buttons)

    await message.answer(text, parse_mode="Markdown", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("fulfill_"))
async def fulfill_request(callback: types.CallbackQuery):
    stocker_id = callback.from_user.id
    try:
        idx = int(callback.data.split("_")[1]) - 1
        if 0 <= idx < len(pending_requests):
            req = pending_requests.pop(idx)
            position = req['position']
            picker_id = req['picker_id']

            # Уведомляем комплектовщика
            try:
                await bot.send_message(
                    picker_id,
                    f"✅ Позиция `{position}` пополнена. Можете взять.",
                    parse_mode="Markdown"
                )
            except:
                pass

            await callback.answer("✅ Запрос выполнен.")
            await bot.send_message(stocker_id, f"✅ Вы пополнили: `{position}`", parse_mode="Markdown")
        else:
            await callback.answer("❌ Неверный номер запроса.")
    except Exception as e:
        await callback.answer("❌ Ошибка.")

if __name__ == "__main__":
    print("Бот запущен...")
    executor.start_polling(dp, skip_updates=True)
