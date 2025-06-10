import asyncio
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager

import aiohttp
import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
)
from dotenv import load_dotenv

# ─── env & logging ─────────────────────────────────────────────────────────────
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_CX = os.getenv("GOOGLE_CX")  # общий CX (идентификатор поисковой системы)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# ─── FSM для приёма токена ─────────────────────────────────────────────────────
class TokenStates(StatesGroup):
    waiting_key: State = State()

# ─── Помощники работы с БД ─────────────────────────────────────────────────────
DB_PATH = "tokens.db"


@asynccontextmanager
async def with_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS tokens (user_id INTEGER PRIMARY KEY, key TEXT)"
        )
        await db.commit()
        yield db


async def save_token(user_id: int, key: str):
    async with with_db() as db:
        await db.execute(
            "INSERT OR REPLACE INTO tokens (user_id, key) VALUES (?, ?)",
            (user_id, key),
        )
        await db.commit()


async def fetch_token(user_id: int) -> str | None:
    async with with_db() as db:
        async with db.execute("SELECT key FROM tokens WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


# ─── Google Search ─────────────────────────────────────────────────────────────
GOOGLE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"


async def google_search(api_key: str, query: str, *, session: aiohttp.ClientSession):
    """Возвращает список результатов Google Search (title, link, snippet)."""
    params = {"key": api_key, "cx": GOOGLE_CX, "q": query, "num": 5}
    async with session.get(GOOGLE_ENDPOINT, params=params, timeout=10) as resp:
        if resp.status != 200:
            text = await resp.text()
            raise RuntimeError(f"Google API error {resp.status}: {text}")
        data = await resp.json()
        return [
            {
                "title": item["title"],
                "link": item["link"],
                "snippet": item.get("snippet", ""),
            }
            for item in data.get("items", [])
        ]


# ─── Роутеры ───────────────────────────────────────────────────────────────────
router = Dispatcher()

# ——— /start
@router.message(CommandStart())
async def cmd_start(msg: Message):
    await msg.answer(
        "Привет! 🔍\n\n"
        "Я *Google Search Bot*.\n"
        "Чтобы искать: в любом чате наберите\n"
        "`@inlinegooglesearchbot <ваш запрос>`\n\n"
        "Для помощи напишите /help 🤖",
        parse_mode=ParseMode.MARKDOWN,
    )


# ——— /help
@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "*Как пользоваться*\n"
        "1. Введите `@inlinegooglesearchbot запрос` и выберите результат.\n"
        "2. Для использования собственных квот Google добавьте API-ключ командой /token.\n\n"
        "• Документация API — [Google Custom Search](https://developers.google.com/custom-search/v1/introduction)\n"
        "• Исходники — [GitHub](https://github.com/danosito/inlinegooglesearchbot)\n"
        "• Автор — [@danosito](https://t.me/danosito)",
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )


# ——— /token
TOKEN_REGEX = re.compile(r"^AIza[0-9A-Za-z_\-]{35}$")


@router.message(Command("token"))
async def cmd_token(msg: Message, state: FSMContext):
    await msg.answer(
        "ℹ️ *Добавление Google API-ключа*\n\n"
        "1. Получите ключ в [Google Cloud Console]"
        "(https://console.cloud.google.com/apis/credentials) (тип *API key*).\n"
        "2. Убедитесь, что в проекте включено API *Custom Search JSON API*.\n"
        "3. Пришлите _только_ сам ключ одним сообщением.\n\n"
        "_После проверки ключ сохранится за вашим аккаунтом._",
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )
    await state.set_state(TokenStates.waiting_key)


@router.message(TokenStates.waiting_key)
async def receive_token(msg: Message, state: FSMContext):
    key = msg.text.strip()
    if not TOKEN_REGEX.match(key):
        await msg.reply(
            "❌ Похоже, это не похоже на API-ключ Google. Попробуйте ещё раз или /cancel."
        )
        return

    await msg.reply("🔍 Проверяю ключ, подождите…")
    async with aiohttp.ClientSession() as session:
        try:
            await google_search(key, "4:20", session=session)
        except Exception as e:
            logging.warning("Key test failed: %s", e)
            await msg.reply(
                f"🚫 Не удалось выполнить запрос с этим ключом.\n"
                f"Ошибка: `{e}`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

    await save_token(msg.from_user.id, key)
    await msg.reply("✅ Ключ сохранён! Теперь попробуйте инлайн-поиск.")
    await state.clear()


# ——— Отлов неизвестных команд
@router.message(F.text.startswith("/"))
async def unknown_command(msg: Message):
    await msg.reply(
        "🤷 Я не знаю такой команды.\nПопробуйте /start или /help."
    )


# ——— Инлайн-поиск
@router.inline_query()
async def inline_google(query: InlineQuery):
    user_id = query.from_user.id
    q = query.query.strip() or "…"

    key = await fetch_token(user_id)
    results = []

    async with aiohttp.ClientSession() as session:
        if key:
            try:
                items = await google_search(key, q, session=session)
                logging.info("Google items for %s: %s", q, items)
                for item in items:
                    results.append(
                        InlineQueryResultArticle(
                            id=str(uuid.uuid4()),
                            title=item["title"],
                            description=item["snippet"],
                            url=item["link"],
                            input_message_content=InputTextMessageContent(
                                message_text=item["link"]
                            ),
                        )
                    )
            except Exception as e:
                logging.error("Google search failed: %s", e)
                # fallback на сообщение об ошибке
                results.append(
                    InlineQueryResultArticle(
                        id=str(uuid.uuid4()),
                        title="Ошибка запроса к Google API",
                        description=str(e),
                        input_message_content=InputTextMessageContent(
                            message_text="Не удалось выполнить поиск 🤖"
                        ),
                    )
                )
        else:
            # У пользователя нет ключа — предлагаем его добавить
            bot_username = (await query.bot.me()).username
            article_text = (
                f"Чтобы получить результаты поиска, добавьте API-ключ Google.\n"
                f"Откройте чат @{bot_username} и отправьте /token"
            )
            results.append(
                InlineQueryResultArticle(
                    id="need_token",
                    title="🔑 Добавьте Google API-ключ (команда /token)",
                    input_message_content=InputTextMessageContent(
                        message_text=article_text
                    ),
                )
            )

    await query.answer(results, cache_time=1)


# ─── Запуск ─────────────────────────────────────────────────────────────────────
async def main():
    bot = Bot(BOT_TOKEN)
    # Меню команд
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Начать работу"),
            BotCommand(command="help", description="Справка"),
            BotCommand(command="token", description="Добавить Google API-ключ"),
        ]
    )
    await router.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
