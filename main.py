import asyncio
import logging
import os
import uuid
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (InlineQuery, InlineQueryResultArticle,
                           InputTextMessageContent, Message)
from dotenv import load_dotenv

load_dotenv()                          # Подхватываем переменные из .env
TOKEN = os.getenv("BOT_TOKEN")         # Токен бота

# ─── Логирование ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# ─── Роутеры / хэндлеры ─────────────────────────────────────────────────────────
router = Dispatcher()

@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """
    /start — короткое приветствие и подсказка об инлайн-режиме.
    """
    await message.answer(
        "Привет! 🔍\n\n"
        "Я *Google Search Bot*.\n"
        "Чтобы воспользоваться мной, напиши в любом чате:\n"
        "`@inlinegooglesearchbot <ваш запрос>`\n\n"
        "Я сразу предложу несколько вариантов поиска. Удачи! 🤖",
        parse_mode=ParseMode.MARKDOWN,
    )

@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """
    /help — подробности о работе и полезные ссылки.
    """
    await message.answer(
        "*Как пользоваться ботом*\n"
        "1. В любом чате начните вводить: `@inlinegooglesearchbot запрос`.\n"
        "2. Выберите нужный вариант из списка — он моментально отправится в чат.\n\n"
        "Исходники доступны на [GitHub](https://github.com/danosito/inlinegooglesearchbot).\n"
        "Связь с разработчиком — [@danosito](https://t.me/danosito).",
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )

@router.inline_query()
async def inline_query_handler(query: InlineQuery) -> None:
    """
    Обрабатываем инлайн-запрос и отдаём три варианта:
      <arg> 1, <arg> 2, <arg> 3
    """
    text = query.query.strip()
    if not text:
        # Telegram требует ответ даже на "пустой" запрос; отдаём пустой список
        await query.answer([], cache_time=1)
        return

    results = [
        InlineQueryResultArticle(
            id=str(uuid.uuid4()),
            title=f"{text} {i}",
            description=f"Вариант {i}",
            input_message_content=InputTextMessageContent(
                message_text=f"{text} {i}"
            ),
        )
        for i in range(1, 4)
    ]

    await query.answer(results, cache_time=1)   # cache_time = 1 — чтобы не кэшировать

# ─── Точка входа ────────────────────────────────────────────────────────────────
async def main() -> None:
    bot = Bot(TOKEN)
    await router.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
