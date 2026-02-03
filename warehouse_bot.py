import os
import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))

# Хранилище ролей: { chat_id: set('picker', 'stocker') }
users = {}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

def get_username(user):
    if user.username:
        return "@%s" % user.username
    return "%s" % (user.first_name or "User")

# Главное меню
def main_menu(roles):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if 'picker' in roles:
        kb.add("📦 Отправить позицию")
    if 'stocker' in roles:
        kb.add("🛠 Мои задания")
    kb.add("🔄 Сменить роль")
    return kb

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    username = get_username(message.from_user)

    # Админ всегда имеет обе роли
    if uid == ADMIN_CHAT_ID:
        users[uid] = {'roles': {'picker', 'stocker'}, 'username': username}
        await message.answer(
            "✅ Вы — админ (комплектовщик + кладовщик).",
            reply_markup=main_menu({'picker', 'stocker'})
        )
        return

    # Если уже выбрана роль — показываем меню
    if uid in users:
        roles = users[uid]['roles']
        await message.answer(
            "Вы уже выбрали роль. Хотите сменить?",
            reply_markup=main_menu(roles)
        )
        return

    # Иначе — выбор роли
    role_kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("📦 Комплектовщик", callback_data="role_picker"),
        InlineKeyboardButton("🛠 Кладовщик", callback_data="role_stocker")
    )
    await message.answer("Выберите вашу роль:", reply_markup=role_kb)

@dp.callback_query_handler(lambda c: c.data.startswith("role_"))
async def select_role(callback: types.CallbackQuery):
    uid = callback.from_user.id
    username = get_username(callback.from_user)
    role = callback.data.split("_")[1]

    if role == "picker":
        users[uid] = {'roles': {'picker'}, 'username': username}
        await bot.send_message(uid, "✅ Вы — комплектовщик.", reply_markup=main_menu({'picker'}))
    elif role == "stocker":
        users[uid] = {'roles': {'stocker'}, 'username': username}
        await bot.send_message(uid, "✅ Вы — кладовщик.", reply_markup=main_menu({'stocker'}))

    await callback.answer()

@dp.message_handler(content_types=types.ContentTypes.TEXT)
async def handle_text(message: types.Message):
    uid = message.from_user.id
    text = message.text.strip()

    if uid not in users:
        await message.answer("Напишите /start и выберите роль.")
        return

    roles = users[uid]['roles']

    # Смена роли
    if text == "🔄 Сменить роль":
        role_kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("📦 Комплектовщик", callback_data="role_picker"),
            InlineKeyboardButton("🛠 Кладовщик", callback_data="role_stocker")
        )
        await message.answer("Выберите новую роль:", reply_markup=role_kb)
        return

    # Комплектовщик: отправка позиции
    if 'picker' in roles and text == "📦 Отправить позицию":
        await message.answer("Введите код позиции (например, `9540 12`):")
        return

    if 'picker' in roles and text != "📦 Отправить позицию" and not text.startswith("/"):
        # Подтверждение
        confirm_kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("✅ Да", callback_data=f"confirm_{uid}_{text}"),
            InlineKeyboardButton("❌ Нет", callback_data="cancel")
        )
        await message.answer(f"Запросить пополнение для `{text}`?", parse_mode="Markdown", reply_markup=confirm_kb)
        return

    # Кладовщик: статусы
    if 'stocker' in roles and text.startswith("/"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Укажите позицию, например:\n/пополнил 9540 12")
            return
        cmd, position = parts[0].lower(), parts[1].strip()
        # Найти активный запрос по позиции, взятый этим кладовщиком
        for req_id, req in pending_requests.items():
            if req.get('position') == position and req.get('stocker_id') == uid:
                picker_name = users.get(req_id, {}).get('username', 'комплектовщик')
                if cmd == "/пополнил":
                    msg = f"✅ {picker_name}, позиция `{position}` пополнена."
                elif cmd == "/не_найден":
                    msg = f"❌ {picker_name}, позиция `{position}` не найдена."
                elif cmd == "/в_пути":
                    msg = f"🚚 {picker_name}, позиция `{position}` в пути."
                else:
                    return
                await bot.send_message(req_id, msg, parse_mode="Markdown")
                pending_requests.pop(req_id, None)
                await message.answer("✅ Статус отправлен.")
                return
        await message.answer("Нет активного задания для этой позиции.")

# === Очередь запросов ===
pending_requests = {}  # picker_id -> { 'position': ..., 'stocker_id': ... }

@dp.callback_query_handler(lambda c: c.data.startswith("confirm_"))
async def process_confirm(callback: types.CallbackQuery):
    _, picker_id, position = callback.data.split("_", 2)
    picker_id = int(picker_id)

    # Находим всех кладовщиков
    stockers = [uid for uid, data in users.items() if 'stocker' in data.get('roles', set())]
    if not stockers:
        await bot.send_message(picker_id, "⚠️ Нет активных кладовщиков.")
        return

    pending_requests[picker_id] = {'position': position, 'stocker_id': None}
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
    await callback.answer()

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
    pos = req['position']
    await callback.answer("Задание взято!")
    await bot.send_message(
        stocker_id,
        f"Вы взяли: `{pos}`\n\nОтправьте:\n/пополнил {pos}\n/не_найден {pos}\n/в_пути {pos}",
        parse_mode="Markdown"
    )

@dp.callback_query_handler(lambda c: c.data == "cancel")
async def cancel(callback: types.CallbackQuery):
    await callback.answer("Отменено.")
    await bot.delete_message(callback.message.chat.id, callback.message.message_id)

if __name__ == "__main__":
    print("Бот запущен...")
    executor.start_polling(dp, skip_updates=True)
