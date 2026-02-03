import os
import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))

users = {}  # chat_id -> {'role': ..., 'username': ...}
pending_requests = {}  # picker_id -> {'position': ..., 'stocker_id': None}

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
        await message.answer("✅ Вы — админ.\nНазначайте кладовщиков: /кладовщик @username")
    else:
        users[uid] = {'role': 'picker', 'username': username}
        kb = ReplyKeyboardMarkup(resize_keyboard=True).add("📦 Отправить позицию")
        await message.answer("✅ Вы — комплектовщик.", reply_markup=kb)

@dp.message_handler(commands=["кладовщик"])
async def cmd_set_stocker(message: types.Message):
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
            await message.answer("✅ %s назначен кладовщиком." % target_username)
            return
    await message.answer("Пользователь %s не найден. Он должен написать боту /start." % target_username)

@dp.message_handler(content_types=types.ContentTypes.TEXT)
async def handle_text(message: types.Message):
    uid = message.from_user.id
    if uid not in users:
        await message.answer("Напишите /start")
        return
    role = users[uid]['role']
    text = message.text.strip()

    if text == "📦 Отправить позицию":
        await message.answer("Введите код позиции (например, `9540 12`):")
        return

    if role == 'picker':
        # Подтверждение
        confirm_kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("✅ Да", callback_data=f"confirm_{uid}_{text}"),
            InlineKeyboardButton("❌ Нет", callback_data="cancel")
        )
        await message.answer(f"Запросить пополнение для `{text}`?", parse_mode="Markdown", reply_markup=confirm_kb)
    elif role == 'stocker':
        if text.startswith("/"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await message.answer("Укажите позицию, например:\n/пополнил 9540 12")
                return
            cmd, position = parts[0].lower(), parts[1].strip()
            # Найти активный запрос
            for picker_id, req in pending_requests.items():
                if req.get('position') == position and req.get('stocker_id') == uid:
                    picker_name = users[picker_id]['username']
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
            await message.answer("Нет активного задания для `%s`." % position, parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data.startswith("confirm_"))
async def process_confirm(callback: types.CallbackQuery):
    _, picker_id, position = callback.data.split("_", 2)
    picker_id = int(picker_id)
    stockers = [uid for uid, d in users.items() if d.get('role') == 'stocker']
    if not stockers:
        await bot.send_message(picker_id, "⚠️ Нет активных кладовщиков.")
        return
    pending_requests[picker_id] = {'position': position, 'stocker_id': None}
    take_kb = InlineKeyboardMarkup().add(InlineKeyboardButton("✋ Взять", callback_data=f"take_{picker_id}"))
    for sid in stockers:
        try:
            await bot.send_message(sid, f"❗ Запрос на пополнение:\n`{position}`\n(от {users[picker_id]['username']})", parse_mode="Markdown", reply_markup=take_kb)
        except:
            pass
    await bot.send_message(picker_id, "✅ Запрос отправлен кладовщикам.")
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("take_"))
async def process_take(callback: types.CallbackQuery):
    stocker_id = callback.from_user.id
    picker_id = int(callback.data.split("_")[1])
    if picker_id in pending_requests and pending_requests[picker_id]['stocker_id'] is None:
        pending_requests[picker_id]['stocker_id'] = stocker_id
        pos = pending_requests[picker_id]['position']
        await callback.answer("Задание взято!")
        await bot.send_message(stocker_id, f"Вы взяли: `{pos}`\nОтправьте:\n/пополнил {pos}\n/не_найден {pos}\n/в_пути {pos}", parse_mode="Markdown")
    else:
        await callback.answer("Задание уже выполнено.", show_alert=True)

if __name__ == "__main__":
    print("Бот запущен...")
    executor.start_polling(dp, skip_updates=True)
