import os
import logging
from aiogram import Bot, Dispatcher, executor, types

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
    if uid not in users or users[uid]['role'] not in ['picker', 'admin']:
        return
    position = message.text.strip()
    if not position:
        return
    pending_requests.append({'picker_id': uid, 'position': position})
    await message.answer(f"✅ Запрос на пополнение `{position}` добавлен в очередь.", parse_mode="Markdown")

@dp.message_handler(lambda m: m.text == "🛠 Активные запросы")
async def show_requests(message: types.Message):
    uid = message.from_user.id
    if uid not in users:
        await message.answer("Напишите /start")
        return
    role = users[uid]['role']
    if role not in ['stocker', 'admin']:
        # Становимся кладовщиком при первом нажатии
        users[uid]['role'] = 'stocker'
        await message.answer("✅ Теперь вы — кладовщик.")

    if not pending_requests:
        await message.answer("📭 Нет активных запросов.")
        return

    text = "📬 Активные запросы:\n"
    for i, req in enumerate(pending_requests, 1):
        picker_name = users.get(req['picker_id'], {}).get('username', 'комплектовщик')
        text += f"{i}. `{req['position']}` (от {picker_name})\n"
    text += "\nПосле пополнения отправьте:\n`/готово [позиция]`"
    await message.answer(text, parse_mode="Markdown")

# === КОМАНДА /ГОТОВО ===
@dp.message_handler(lambda m: m.text.startswith("/готово"))
async def cmd_ready(message: types.Message):
    uid = message.from_user.id
    if uid not in users or users[uid]['role'] not in ['stocker', 'admin']:
        await message.answer("Только кладовщики могут использовать `/готово`.")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Укажите позицию, например:\n`/готово 9540 1/2`", parse_mode="Markdown")
        return

    position = parts[1].strip()
    # Находим всех комплектовщиков, запросивших эту позицию
    target_pickers = []
    remaining_requests = []

    for req in pending_requests:
        if req['position'] == position:
            target_pickers.append(req['picker_id'])
        else:
            remaining_requests.append(req)

    if not target_pickers:
        await message.answer(f"❌ Нет активных запросов для позиции `{position}`.", parse_mode="Markdown")
        return

    # Удаляем обработанные запросы
    pending_requests.clear()
    pending_requests.extend(remaining_requests)

    # Уведомляем всех комплектовщиков
    for pid in set(target_pickers):  # set() — на случай дублей
        try:
            await bot.send_message(pid, f"✅ Позиция `{position}` пополнена. Можете взять.", parse_mode="Markdown")
        except:
            pass

    await message.answer(f"✅ Позиция `{position}` помечена как пополненная.", parse_mode="Markdown")

if __name__ == "__main__":
    print("Бот запущен...")
    executor.start_polling(dp, skip_updates=True)
