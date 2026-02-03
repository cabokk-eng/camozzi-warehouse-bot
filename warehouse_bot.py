import os
import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))

# Список ID кладовщиков (добавляйте сюда вручную)
STOCKERS = {
    1940681422,  # ваш ID — вы тоже кладовщик
    # 123456789,  # пример: добавьте ID другого кладовщика
}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

def get_username(user):
    if user.username:
        return "@%s" % user.username
    return "%s" % (user.first_name or "User")

# Хранилище запросов: { picker_id: 'position' }
pending_requests = {}

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    username = get_username(message.from_user)

    if uid == ADMIN_CHAT_ID:
        # Админ — и комплектовщик, и кладовщик
        kb = ReplyKeyboardMarkup(resize_keyboard=True).add(
            "📦 Отправить позицию",
            "🛠 Мои задания"
        )
        await message.answer("✅ Вы — админ (комплектовщик + кладовщик).", reply_markup=kb)
    else:
        # Все остальные — комплектовщики
        kb = ReplyKeyboardMarkup(resize_keyboard=True).add("📦 Отправить позицию")
        await message.answer("✅ Вы — комплектовщик.", reply_markup=kb)

@dp.message_handler(content_types=types.ContentTypes.TEXT)
async def handle_text(message: types.Message):
    uid = message.from_user.id
    text = message.text.strip()

    if text == "📦 Отправить позицию":
        await message.answer("Введите код позиции (например, `9540 12`):")
        return

    if text == "🛠 Мои задания":
        if uid not in STOCKERS:
            await message.answer("Вы не кладовщик.")
            return
        tasks = []
        for picker_id, pos in pending_requests.items():
            picker_name = get_username(await bot.get_chat(picker_id))
            tasks.append(f"❗ `{pos}` (от {picker_name})")
        if tasks:
            await message.answer("Активные запросы:\n" + "\n".join(tasks), parse_mode="Markdown")
        else:
            await message.answer("Нет активных запросов.")
        return

    # Комплектовщик отправляет позицию
    if uid != ADMIN_CHAT_ID and uid not in STOCKERS:
        # Подтверждение
        confirm_kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2).add(
            "✅ Да, запросить", "❌ Нет"
        )
        pending_requests[uid] = text  # временно сохраняем
        await message.answer(f"Запросить пополнение для `{text}`?", parse_mode="Markdown", reply_markup=confirm_kb)
        return

    # Обработка подтверждения
    if text == "✅ Да, запросить":
        if uid in pending_requests:
            position = pending_requests[uid]
            # Рассылаем ВСЕМ кладовщикам
            for sid in STOCKERS:
                try:
                    await bot.send_message(
                        sid,
                        f"❗ Запрос на пополнение:\n`{position}`\n(от {get_username(message.from_user)})",
                        parse_mode="Markdown"
                    )
                except:
                    pass
            await message.answer("✅ Запрос отправлен кладовщикам.")
            del pending_requests[uid]
        return

    if text == "❌ Нет":
        if uid in pending_requests:
            del pending_requests[uid]
        await message.answer("Отменено.")
        return

    # Кладовщик отправляет статус: /пополнил 9540 12
    if uid in STOCKERS and text.startswith("/"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Укажите позицию, например:\n/пополнил 9540 12")
            return
        cmd, position = parts[0].lower(), parts[1].strip()
        # Находим комплектовщика с таким запросом
        target_picker = None
        for pid, pos in pending_requests.items():
            if pos == position:
                target_picker = pid
                break
        if not target_picker:
            await message.answer("Нет активного запроса для этой позиции.")
            return

        # Формируем ответ
        picker_name = get_username(await bot.get_chat(target_picker))
        if cmd == "/пополнил":
            reply = f"✅ {picker_name}, позиция `{position}` пополнена."
        elif cmd == "/не_найден":
            reply = f"❌ {picker_name}, позиция `{position}` не найдена."
        elif cmd == "/в_пути":
            reply = f"🚚 {picker_name}, позиция `{position}` в пути."
        else:
            return

        await bot.send_message(target_picker, reply, parse_mode="Markdown")
        pending_requests.pop(target_picker, None)
        await message.answer("✅ Статус отправлен.")
        return

if __name__ == "__main__":
    print("Бот запущен...")
    executor.start_polling(dp, skip_updates=True)
