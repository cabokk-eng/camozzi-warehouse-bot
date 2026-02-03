import os
import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))

# Хранилище
users = {}  # chat_id -> {'role': 'picker'/'stocker', 'username': '@...'}
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
        kb = ReplyKeyboardMarkup(resize_keyboard=True).add(
            "📦 Отправить позицию",
            "🛠 Активные запросы"
        )
        await message.answer("✅ Вы — админ (комплектовщик + кладовщик).", reply_markup=kb)
    else:
        users[uid] = {'role': 'picker', 'username': username}
        kb = ReplyKeyboardMarkup(resize_keyboard=True).add("📦 Отправить позицию")
        await message.answer("✅ Вы — комплектовщик.", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "📦 Отправить позицию")
async def ask_position(message: types.Message):
    await message.answer("Введите код позиции (например, `9540 1/2`):")

@dp.message_handler(lambda m: m.text not in ["📦 Отправить позицию", "🛠 Активные запросы"])
async def handle_position_input(message: types.Message):
    uid = message.from_user.id
    if uid not in users:
        await message.answer("Напишите /start")
        return
    role = users[uid]['role']
    if role != 'picker' and role != 'admin':
        return

    position = message.text.strip()
    if not position:
        return

    # Подтверждение
    confirm_kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("✅ Да", callback_data=f"confirm_{uid}_{position}"),
        InlineKeyboardButton("❌ Нет", callback_data="cancel")
    )
    await message.answer(f"Запросить пополнение для `{position}`?", parse_mode="Markdown", reply_markup=confirm_kb)

@dp.callback_query_handler(lambda c: c.data.startswith("confirm_"))
async def process_confirm(callback: types.CallbackQuery):
    _, picker_id, position = callback.data.split("_", 2)
    picker_id = int(picker_id)
    pending_requests.append({'picker_id': picker_id, 'position': position})
    await bot.send_message(picker_id, f"✅ Запрос на пополнение `{position}` добавлен в очередь.", parse_mode="Markdown")
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == "cancel")
async def cancel(callback: types.CallbackQuery):
    await callback.answer("Отменено.")
    await bot.delete_message(callback.message.chat.id, callback.message.message_id)

# === КЛАДОВЩИК: ПРОСМОТР ЗАПРОСОВ ===
@dp.message_handler(lambda m: m.text == "🛠 Активные запросы")
async def show_requests(message: types.Message):
    uid = message.from_user.id
    if uid not in users:
        await message.answer("Напишите /start")
        return
    role = users[uid]['role']
    if role != 'stocker' and role != 'admin':
        # Делаем пользователя кладовщиком при первом нажатии
        users[uid]['role'] = 'stocker'
        await message.answer("✅ Теперь вы — кладовщик.")

    if not pending_requests:
        await message.answer("📭 Нет активных запросов.")
        return

    text = "📬 Активные запросы:\n"
    for i, req in enumerate(pending_requests, 1):
        picker_name = users.get(req['picker_id'], {}).get('username', 'комплектовщик')
        text += f"{i}. `{req['position']}` (от {picker_name})\n"
    text += "\nНажмите на номер запроса, чтобы взять его в работу."
    await message.answer(text, parse_mode="Markdown")

@dp.message_handler(lambda m: m.text.isdigit())
async def take_request_by_id(message: types.Message):
    uid = message.from_user.id
    if uid not in users or users[uid]['role'] not in ['stocker', 'admin']:
        return
    try:
        idx = int(message.text) - 1
        if 0 <= idx < len(pending_requests):
            req = pending_requests.pop(idx)
            picker_id = req['picker_id']
            position = req['position']
            picker_name = users.get(picker_id, {}).get('username', 'комплектовщик')
            try:
                await bot.send_message(picker_id, f"✅ Позиция `{position}` пополнена.", parse_mode="Markdown")
            except:
                pass
            await message.answer(f"✅ Вы пополнили запрос от {picker_name}: `{position}`.", parse_mode="Markdown")
        else:
            await message.answer("❌ Неверный номер запроса.")
    except:
        await message.answer("❌ Неверный формат.")

if __name__ == "__main__":
    print("Бот запущен...")
    executor.start_polling(dp, skip_updates=True)
