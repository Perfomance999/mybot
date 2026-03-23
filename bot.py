import asyncio
import logging
import os
import json
import base64
import time
import hashlib
import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from aiogram.client.default import DefaultBotProperties

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY", "")
OPERATOR_PASS = "oper123"
OBRAB_PASS = "obrab456"
SECRET_WORD = "getlinks"
SESSIONS_FILE = "sessions.json"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()


def load_sessions():
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, "r") as f:
                data = json.load(f)
                sessions = {int(k): v for k, v in data.get("sessions", {}).items()}
                counters = data.get("counters", {"operator": 0, "obrab": 0})
                return sessions, counters
        except Exception:
            pass
    return {}, {"operator": 0, "obrab": 0}


def save_sessions():
    try:
        with open(SESSIONS_FILE, "w") as f:
            json.dump({"sessions": sessions, "counters": counters}, f)
    except Exception as e:
        logger.warning("Failed to save sessions: %s", e)


sessions, counters = load_sessions()


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
    save_sessions()
    return label


def generate_receipt_id():
    return "#" + str(int(time.time()))[-6:]


async def get_amount_from_image(image_bytes):
    try:
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        headers = {
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 100,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": "This is a receipt or payment screenshot. Find the total amount paid. Reply with ONLY the amount and currency, nothing else. Example: $50.00 or 300.000 COP or 1500 RUB. If you cannot find an amount, reply: Not found.",
                        },
                    ],
                }
            ],
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
            ) as resp:
                result = await resp.json()
                logger.info("Claude raw response: %s", result)
                content = result.get("content", [])
                if content and content[0].get("type") == "text":
                    return content[0]["text"].strip()
    except Exception as e:
        logger.warning("Claude API error: %s", e)
    return None


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
        save_sessions()
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
    amount_text = None

    if message.photo:
        try:
            file = await bot.get_file(message.photo[-1].file_id)
            file_url = "https://api.telegram.org/file/bot" + BOT_TOKEN + "/" + file.file_path
            async with aiohttp.ClientSession() as s:
                async with s.get(file_url) as resp:
                    image_bytes = await resp.read()
            amount_text = await get_amount_from_image(image_bytes)
            logger.info("Claude response: %s", amount_text)
        except Exception as e:
            logger.warning("Photo download error: %s", e)

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
                await bot.send_sticker(uid, message.sticker.file_id)
            elif message.voice:
                await bot.send_voice(uid, message.voice.file_id, caption=full)
            elif message.document:
                await bot.send_document(uid, message.document.file_id, caption=full)
            elif message.text:
                await bot.send_message(uid, header + "\n\n" + message.text)
            sent += 1
        except Exception as e:
            logger.warning("Error: %s", e)

    if amount_text and amount_text != "Not found":
        receipt_id = generate_receipt_id()
        result = receipt_id + " | Amount: " + amount_text
        for uid in list(sessions.keys()):
            try:
                await bot.send_message(uid, result)
            except Exception as e:
                logger.warning("Error sending amount: %s", e)
        await message.answer(result)

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
    logger.info("Bot started. Sessions loaded: %d", len(sessions))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
