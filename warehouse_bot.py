import os
import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))

# Хранилище ролей (в памяти)
users = {}

def get_users_by_role(role):
    return [cid for cid, data in users.items() if data.get('role') == role]

def get_username(user):
    if user.username:
        return "@%s" % user.username
    return "%s %s" % (user.first_name or "", user.last_name or "").strip()

# === ИНИЦИАЛИЗАЦИЯ ===
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# === КНОПКИ ===
main_kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
main_kb.add(
    KeyboardButton("📦 Отправить лоток"),
    KeyboardButton("✅ Пополнил"),
    KeyboardButton("❌ Не найден"),
    KeyboardButton("🚚 В пути")
)

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    if uid == ADMIN_CHAT_ID:
        users[uid] = {'role': 'admin', 'username': get_username(message.from_user)}
        await message.answer(
            "✅ Вы — админ.\n"
            "Назначайте роли:\n"
            "/роль комплектовщик @user\n"
            "/роль кладовщик @user\n"
            "/роль выходной @user",
            reply_markup=main_kb
        )
    else:
        await message.answer("Ожидайте назначения роли от администратора.")

@dp.message_handler(commands=["роль"])
async def cmd_set_role(message: types.Message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return

    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("Формат: /роль комплектовщик @username")
        return

    role_name = parts[1].lower()
    username = parts[2]

    if role_name not in ['комплектовщик', 'кладовщик', 'выходной']:
        await message.answer("Роль должна быть: комплектовщик, кладовщик или выходной")
        return

    target_id = None
    for uid, data in users.items():
        if data.get('username') == username:
            target_id = uid
            break

    if not target_id:
        await message.answer("Пользователь %s не найден. Он должен написать боту /start." % username)
        return

    role_map = {
        'комплектовщик': 'picker',
        'кладовщик': 'stocker',
        'выходной': 'none'
    }

    users[target_id]['role'] = role_map[role_name]
    status_msg = {
        'picker': 'назначен комплектовщиком',
        'stocker': 'назначен кладовщиком',
        'none': 'переведён в выходные'
    }[role_map[role_name]]

    await message.answer("✅ %s — %s." % (username, status_msg))

@dp.message_handler(content_types=types.ContentTypes.TEXT)
async def handle_text(message: types.Message):
    uid = message.from_user.id
    text = message.text.strip()

    if uid not in users:
        users[uid] = {'username': get_username(message.from_user), 'role': 'none'}
    else:
        users[uid]['username'] = get_username(message.from_user)

    user_role = users[uid]['role']

    if uid == ADMIN_CHAT_ID:
        await message.answer("📢 Админ: %s" % text)
        return

    if user_role == 'picker':
        lot = text.upper()
        stockers = get_users_by_role('stocker')
        if not stockers:
            await message.answer("⚠️ Нет активных кладовщиков.")
            return
        for sid in stockers:
            try:
                await bot.send_message(sid, "❗ Лоток `%s` пуст. Требуется пополнение." % lot, parse_mode="Markdown")
            except:
                pass
        await message.answer("✅ Запрос по лотку `%s` отправлен." % lot, parse_mode="Markdown")
        return

    if user_role == 'stocker':
        if text.startswith("/"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await message.answer("Укажите код лотка, например:\n/пополнил R12.E7.1")
                return
            cmd = parts[0].lower()
            lot = parts[1].upper()
            username = users[uid]['username']
            if cmd == "/пополнил":
                reply = "✅ %s пополнил лоток `%s`." % (username, lot)
            elif cmd == "/не_найден":
                reply = "❌ %s: позиция для лотка `%s` не найдена." % (username, lot)
            elif cmd == "/в_пути":
                reply = "🚚 %s: пополнение лотка `%s` в пути." % (username, lot)
            else:
                await message.answer("Команды: /пополнил, /не_найден, /в_пути")
                return
            await message.answer("✅ Статус отправлен.")
            pickers = get_users_by_role('picker')
            for pid in pickers:
                try:
                    await bot.send_message(pid, reply, parse_mode="Markdown")
                except:
                    pass
            return

    await message.answer("Вы не назначены на работу. Обратитесь к администратору.")

if __name__ == "__main__":
    print("Бот запущен...")
    executor.start_polling(dp, skip_updates=True)
