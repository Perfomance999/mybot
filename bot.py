import asyncio
import os
import logging
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from aiogram.client.default import DefaultBotProperties

BOT_TOKEN = os.getenv("BOT_TOKEN", "8611253814:AAGw7gDgiBwOJelgSOVJGhCT_feFlthDqLY")
OPERATOR_PASS = "oper123"
OBRAB_PASS = "obrab456"
SECRET_WORD = "getlinks"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sessions = {}
counters = {"operator": 0, "obrab": 0}
router = Router()


def get_label(user_id):
    if user_id in sessions:
        return sessions[user_id]["label"]
    return "Unknown"


def get_role(user_id):
    if user_id in sessions:
        return sessions[user_id]["role"]
    return None


def all_users_except(sender_id):
    return [uid for uid in sessions if uid != sender_id]


def register(user_id, role):
    counters[role] += 1
    label = ("Operator " if role == "operator" else "Obrab ") + str(counters[role])
    sessions[user_id] = {"role": role, "label": label}
    return label


@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=1)
    payload = parts[1].strip() if len(parts) > 1 else ""

    if user_id in sessions:
        await message.answer("Already logged in as " + get_label(user_id))
        return

    if payload == "op_" + OPERATOR_PASS:
        label = register(user_id, "operator")
        await message.answer("Logged in as " + label + ".")
        return

    if payload == "ob_" + OBRAB_PASS:
        label = register(user_id, "obrab")
        await message.answer("Logged in as " + label + ".")
        return

    await message.answer("Access denied. Use your invite link.")


@router.message(Command("users"))
async def cmd_users(message: Message):
    if message.from_user.id not in sessions:
        await message.answer("Not logged in.")
        return
    ops = [s["label"] for s in sessions.values() if s["role"] == "operator"]
    obs = [s["label"] for s in sessions.values() if s["role"] == "obrab"]
    text = "Online:\n"
    text += "Operators: " + (", ".join(ops) if ops else "none") + "\n"
    text += "Obrabs: " + (", ".join(obs) if obs else "none")
    await message.answer(text)


@router.message(Command("logout"))
async def cmd_logout(message: Message):
    user_id = message.from_user.id
    if user_id in sessions:
        label = get_label(user_id)
        del sessions[user_id]
        await message.answer("Logged out from " + label)
    else:
        await message.answer("Not logged in.")


async def relay(message: Message, bot: Bot):
    sender_id = message.from_user.id

    if sender_id not in sessions:
        await message.answer("Not logged in.")
        return

    text = message.text or ""

    if text == SECRET_WORD:
        if get_role(sender_id) != "obrab":
            await message.answer("Access denied.")
            return
        me = await bot.get_me()
        op_link = "https://t.me/" + me.username + "?start=op_" + OPERATOR_PASS
        ob_link = "https://t.me/" + me.username + "?start=ob_" + OBRAB_PASS
        await message.answer("For Operators:\n" + op_link + "\n\nFor Obrabs:\n" + ob_link)
        return

    recipients = all_users_except(sender_id)

    if not recipients:
        await message.answer("No one else connected yet.")
        return

    header = "From " + get_label(sender_id) + ":"
    cap = message.caption or ""
    full = header + "\n" + cap if cap else header
    sent = 0

    for uid in recipients:
        try:
            if message.photo:
                await bot.send_photo(uid, message.photo[-1].file_id, caption=full)
            elif message.video:
                await bot.send_video(uid, message.video.file_id, caption=full)
            elif message.animation:
                await bot.send_animation(uid, message.animation.file_id, caption=full)
            elif message.sticker:
                await bot.send_message(uid, header)
                await bot.


send_sticker(uid, message.sticker.file_id)
            elif message.voice:
                await bot.send_voice(uid, message.voice.file_id, caption=full)
            elif message.document:
                await bot.send_document(uid, message.document.file_id, caption=full)
            elif message.text:
                await bot.send_message(uid, header + "\n\n" + message.text)
            sent += 1
        except Exception as e:
            logger.warning("Error: %s", e)

    if sent:
        await message.answer("Sent.")
    else:
        await message.answer("Failed.")


@router.message(F.text & ~F.text.startswith("/"))
async def on_text(m: Message, bot: Bot):
    await relay(m, bot)


@router.message(F.photo)
async def on_photo(m: Message, bot: Bot):
    await relay(m, bot)


@router.message(F.video)
async def on_video(m: Message, bot: Bot):
    await relay(m, bot)


@router.message(F.animation)
async def on_gif(m: Message, bot: Bot):
    await relay(m, bot)


@router.message(F.sticker)
async def on_sticker(m: Message, bot: Bot):
    await relay(m, bot)


@router.message(F.voice)
async def on_voice(m: Message, bot: Bot):
    await relay(m, bot)


@router.message(F.document)
async def on_document(m: Message, bot: Bot):
    await relay(m, bot)


async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if name == "__main__":
    asyncio.run(main())
