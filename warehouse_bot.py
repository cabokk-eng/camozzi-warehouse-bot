import os
import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))

# Хранилище
users = {}  # chat_id -> {'role': 'picker' / 'stocker', 'username': '@...'}
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
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("📦 Отправить позицию", "🛠 Активные запросы")
        await message.answer("✅ Вы — админ (комплектовщик + кладовщик).", reply_markup=kb)
    else:
        users[uid] = {'role': 'picker', 'username': username}
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("📦 Отправить позицию")
        await message.answer("✅ Вы — комплектовщик.", reply_markup=kb)

@dp.message_handler(commands=["кладовщик"])
async def cmd_add_stocker(message: types.Message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Формат: /кладовщик @username")
        return
    target_username = parts[1]
    for uid, data in users.items():
        if data.get('username') == target_username:
            users[uid]['role'] = 'stocker'
            await message.answer(f"✅ {target_username} назначен кладовщиком.")
            return
    await message.answer(f"Пользователь {target_username} не найден. Он должен написать /start.")

@dp.message_handler(content_types=types.ContentTypes.TEXT)
async def handle_text(message: types.Message):
    uid = message.from_user.id
    text = message.text.strip()

    if uid not in users:
        await message.answer("Напишите /start")
        return

    role = users[uid]['role']

    # === Комплектовщик: отправка позиции ===
    if role == 'picker' and text == "📦 Отправить позицию":
        await message.answer("Введите код позиции (например, `9540 1/2`):")
        return

    if role == 'picker' and text != "📦 Отправить позицию":
        # Сохраняем запрос как есть (сохраняем дроби!)
        pending_requests.append({'picker_id': uid, 'position': text})
        await message.answer(f"✅ Запрос на пополнение `{text}` добавлен в очередь.", parse_mode="Markdown")
        return

    # === Кладовщик или админ: просмотр запросов ===
    if (role == 'stocker' or role == 'admin') and text == "🛠 Активные запросы":
        if not pending_requests:
            await message.answer("📭 Нет активных запросов.")
            return

        text_list = []
        for i, req in enumerate(pending_requests, 1):
            picker_name = users.get(req['picker_id'], {}).get('username', 'комплектовщик')
            text_list.append(f"{i}. `{req['position']}` (от {picker_name})")

        full_text = "📬 Активные запросы:\n" + "\n".join(text_list)
        full_text += "\n\nВыберите номер(а) через запятую (например: 1,3,5):"

        # Кнопки: 1, 2, 3...
        kb = InlineKeyboardMarkup(row_width=5)
        buttons = [InlineKeyboardButton(str(i), callback_data=f"take_{i}") for i in range(1, min(len(pending_requests)+1, 11))]
        kb.add(*buttons)
        if len(pending_requests) > 1:
            kb.add(InlineKeyboardButton("Все", callback_data="take_all"))
        await message.answer(full_text, parse_mode="Markdown", reply_markup=kb)
        return

    # === Обработка выбора через текст (например: "1,2,3") ===
    if (role == 'stocker' or role == 'admin') and ',' in text:
        try:
            indices = [int(x.strip()) for x in text.split(",")]
            await process_take_by_indices(uid, indices, message)
        except:
            await message.answer("Неверный формат. Используйте: 1,2,3")

# === ОБРАБОТКА КНОПОК ===
@dp.callback_query_handler(lambda c: c.data.startswith("take_"))
async def process_callback(callback: types.CallbackQuery):
    stocker_id = callback.from_user.id
    data = callback.data

    if data == "take_all":
        indices = list(range(1, len(pending_requests) + 1))
    else:
        try:
            idx = int(data.split("_")[1])
            indices = [idx]
        except:
            await callback.answer("Ошибка", show_alert=True)
            return

    await process_take_by_indices(stocker_id, indices)
    await callback.answer("Обработано!")

# === ЛОГИКА ВЗЯТИЯ ЗАПРОСОВ ===
async def process_take_by_indices(stocker_id, indices, message=None):
    global pending_requests
    to_remove = []
    responses = {}  # position -> set of picker_ids

    for idx in indices:
        if 1 <= idx <= len(pending_requests):
            req = pending_requests[idx - 1]
            pos = req['position']
            picker_id = req['picker_id']

            if pos not in responses:
                responses[pos] = set()
            responses[pos].add(picker_id)
            to_remove.append(idx - 1)

    if not to_remove:
        if message:
            await message.answer("❌ Неверные номера.")
        return

    # Отправляем уведомления всем комплектовщикам по каждой позиции
    for pos, picker_ids in responses.items():
        for pid in picker_ids:
            try:
                await bot.send_message(pid, f"✅ Позиция `{pos}` пополнена.", parse_mode="Markdown")
            except:
                pass

    # Удаляем обработанные запросы
    for idx in sorted(to_remove, reverse=True):
        del pending_requests[idx]

    if message:
        await message.answer("✅ Запрос(ы) обработан(ы).")

if __name__ == "__main__":
    print("Бот запущен...")
    executor.start_polling(dp, skip_updates=True)
