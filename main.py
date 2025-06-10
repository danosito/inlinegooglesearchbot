import asyncio
import json
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import aiohttp
import aiosqlite
import redis.asyncio as aioredis
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
)
from dotenv import load_dotenv

# ─── env & logging ─────────────────────────────────────────────────────────────
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_CX = os.getenv("GOOGLE_CX")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
ADMIN_CONTACT = "@danosito"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


# ─── FSM для приёма токена ─────────────────────────────────────────────────────
class TokenStates(StatesGroup):
    waiting_key: State = State()


# ─── БД (SQLite) ───────────────────────────────────────────────────────────────
DB_PATH = "tokens_and_settings.db"


@asynccontextmanager
async def with_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # две таблицы: токены и настройки
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS tokens (
                user_id INTEGER PRIMARY KEY,
                key TEXT
            );
            CREATE TABLE IF NOT EXISTS settings (
                user_id INTEGER PRIMARY KEY,
                show_logo INTEGER DEFAULT 1,     -- 1 = True
                lim INTEGER DEFAULT 5
            );
            """
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


async def fetch_token(user_id: int) -> Optional[str]:
    async with with_db() as db:
        async with db.execute(
                "SELECT key FROM tokens WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def fetch_settings(user_id: int) -> Dict[str, Any]:
    async with with_db() as db:
        async with db.execute(
                "SELECT show_logo, lim FROM settings WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                return {"show_logo": bool(row[0]), "limit": row[1]}
        # defaults
        return {"show_logo": True, "limit": 5}


async def update_settings(user_id: int, *, show_logo: Optional[bool] = None, limit: Optional[int] = None):
    async with with_db() as db:
        current = await fetch_settings(user_id)
        show_logo_val = int(show_logo) if show_logo is not None else int(current["show_logo"])
        limit_val = limit if limit is not None else current["limit"]
        await db.execute(
            """
            INSERT OR REPLACE INTO settings (user_id, show_logo, lim)
            VALUES (?, ?, ?)
            """,
            (user_id, show_logo_val, limit_val),
        )
        await db.commit()


# ─── Redis кэш ─────────────────────────────────────────────────────────────────
redis_client: aioredis.Redis  # будет инициализирован в main()


async def cache_get(q: str) -> Optional[List[Dict[str, str]]]:
    data = await redis_client.get(f"google:{q.lower()}")
    return json.loads(data) if data else None


async def cache_set(q: str, items: List[Dict[str, str]]):
    await redis_client.setex(f"google:{q.lower()}", 24 * 3600, json.dumps(items))


# ─── Google Search ─────────────────────────────────────────────────────────────
GOOGLE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"


async def google_search(api_key: str, query: str, *, limit: int, session: aiohttp.ClientSession):
    params = {"key": api_key, "cx": GOOGLE_CX, "q": query, "num": limit}
    async with session.get(GOOGLE_ENDPOINT, params=params, timeout=10) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Google API error {resp.status}: {await resp.text()}")
        data = await resp.json()

    results = []
    for item in data.get("items", []):
        thumb = None
        pagemap = item.get("pagemap", {})
        # иногда в cse_thumbnail -> [ { "src": "…" } ]
        if "cse_thumbnail" in pagemap and pagemap["cse_thumbnail"]:
            thumb = pagemap["cse_thumbnail"][0].get("src")
        elif "metatags" in pagemap and pagemap["metatags"]:
            thumb = pagemap["metatags"][0].get("og:image")

        results.append(
            {
                "title": item["title"],
                "link": item["link"],
                "snippet": item.get("snippet", ""),
                "thumbnail": thumb,
            }
        )
    return results


# ─── Telegram роутеры ──────────────────────────────────────────────────────────
router = Dispatcher()


# ——— /start
@router.message(CommandStart())
async def cmd_start(msg: Message):
    await msg.answer(
        "Привет! 🔍\n\n"
        "Я *Google Search Bot*.\n"
        "Чтобы искать: в любом чате напишите\n"
        "`@inlinegooglesearchbot <ваш запрос>`\n\n"
        "Помощь → /help",
        parse_mode=ParseMode.MARKDOWN,
    )


# ——— /help
@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "*Как пользоваться*\n"
        "1. Введите `@inlinegooglesearchbot запрос` и выберите результат.\n"
        "2. *По желанию* подключите свой Google API-ключ — /token.\n\n"
        "• Документация — [Google Custom Search](https://developers.google.com/custom-search/v1/introduction)\n"
        "• Исходники — [GitHub](https://github.com/danosito/inlinegooglesearchbot)\n"
        f"• Автор — {ADMIN_CONTACT}",
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )


# ——— /settings
def settings_keyboard(show_logo: bool, limit: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"Логотипы: {'✅ On' if show_logo else '❌ Off'}",
                callback_data=f"set_logo:{int(not show_logo)}",
            )
        ],
        [
            InlineKeyboardButton(text="Результатов 3", callback_data="set_lim:3"),
            InlineKeyboardButton(text="Результатов 5", callback_data="set_lim:5"),
            InlineKeyboardButton(text="Результатов 10", callback_data="set_lim:10"),
        ],
    ])


@router.message(Command("settings"))
async def cmd_settings(msg: Message):
    st = await fetch_settings(msg.from_user.id)
    await msg.answer(
        "*Ваши настройки*",
        reply_markup=settings_keyboard(st["show_logo"], st["limit"]),
        parse_mode=ParseMode.MARKDOWN,
    )


@router.callback_query(F.data.startswith("set_logo"))
async def cb_set_logo(cb: CallbackQuery):
    new_val = bool(int(cb.data.split(":")[1]))
    await update_settings(cb.from_user.id, show_logo=new_val)
    st = await fetch_settings(cb.from_user.id)
    await cb.message.edit_reply_markup(settings_keyboard(st["show_logo"], st["limit"]))
    await cb.answer("Обновлено!")


@router.callback_query(F.data.startswith("set_lim"))
async def cb_set_lim(cb: CallbackQuery):
    new_lim = int(cb.data.split(":")[1])
    await update_settings(cb.from_user.id, limit=new_lim)
    st = await fetch_settings(cb.from_user.id)
    await cb.message.edit_reply_markup(settings_keyboard(st["show_logo"], st["limit"]))
    await cb.answer("Обновлено!")


# ——— /token
TOKEN_REGEX = re.compile(r"^AIza[0-9A-Za-z_\-]{35}$")


@router.message(Command("token"))
async def cmd_token(msg: Message, state: FSMContext):
    await msg.answer(
        "ℹ️ *Добавление Google API-ключа*\n\n"
        "1. Создайте ключ в [Google Cloud Console]"
        "(https://console.cloud.google.com/apis/credentials) (тип *API key*).\n"
        "2. Убедитесь, что включено API *Custom Search JSON API*.\n"
        "3. Пришлите *только* ключ одним сообщением.",
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )
    await state.set_state(TokenStates.waiting_key)


@router.message(TokenStates.waiting_key)
async def receive_token(msg: Message, state: FSMContext):
    key = msg.text.strip()
    if not TOKEN_REGEX.match(key):
        await msg.reply("❌ Это не похоже на ключ Google API. Попробуйте снова или /cancel.")
        return

    await msg.reply("🔍 Проверяю ключ…")
    try:
        async with aiohttp.ClientSession() as session:
            await google_search(key, "4:20", limit=1, session=session)
    except Exception as e:
        await msg.reply(f"🚫 Не удалось выполнить запрос: `{e}`", parse_mode=ParseMode.MARKDOWN)
        return

    await save_token(msg.from_user.id, key)
    await msg.reply("✅ Ключ сохранён! Можно пользоваться.")
    await state.clear()


# ——— Отлов неизвестных команд
@router.message(F.text.startswith("/"))
async def unknown_command(msg: Message):
    await msg.reply("🤷 Я не знаю такой команды. Попробуйте /start или /help.")


# ——— Инлайн-поиск
@router.inline_query()
async def inline_google(query: InlineQuery, bot: Bot):
    q = query.query.strip()
    if not q:  # пусто или одни пробелы
        await query.answer([], cache_time=1)
        return

    user_id = query.from_user.id
    token = await fetch_token(user_id)
    settings = await fetch_settings(user_id)
    limit = settings["limit"]
    show_logo = settings["show_logo"]

    # пробуем кэш
    cached = await cache_get(q)
    if cached:
        items = cached[:limit]
    else:
        if not token:
            # статьи-заглушки, предлагающие добавить токен
            bot_username = (await query.bot.me()).username
            text = (
                f"Чтобы получить результаты поиска, добавьте Google API-ключ.\n"
                f"Откройте чат @{bot_username} и отправьте /token"
            )
            await query.answer(
                [
                    InlineQueryResultArticle(
                        id="need_token",
                        title="🔑 Добавьте Google API-ключ",
                        description=f"Откройте @{bot_username} → /token",
                        input_message_content=InputTextMessageContent(message_text=text),
                    )
                ],
                cache_time=1,
            )
            return

        # нет кэша — делаем запрос к Google
        try:
            async with aiohttp.ClientSession() as session:
                items = await google_search(token, q, limit=limit, session=session)
            # кэшируем FULL набор (5, 10). TTL = 24 ч
            await cache_set(q, items)
        except Exception as e:
            logging.error("Google search error: %s", e)
            # оповестим пользователя личным сообщением
            await bot.send_message(
                user_id,
                f"😔 Ошибка при поиске: {e}\nЕсли проблема повторяется, напишите {ADMIN_CONTACT}",
            )
            await query.answer(
                [
                    InlineQueryResultArticle(
                        id="err",
                        title="🚫 Ошибка поиска",
                        description="Произошла ошибка. Подробности в личном сообщении.",
                        input_message_content=InputTextMessageContent(
                            message_text="К сожалению, произошла ошибка поиска 😔"
                        ),
                    )
                ],
                cache_time=1,
            )
            return

    # формируем результаты
    results = []
    for it in items[:limit]:
        thumb = it["thumbnail"] if (show_logo and it["thumbnail"]) else None
        results.append(
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title=it["title"],
                description=it["snippet"],
                url=it["link"],
                thumb_url=thumb,
                input_message_content=InputTextMessageContent(message_text=it["link"]),
            )
        )

    await query.answer(results, cache_time=1)


# ─── Запуск ─────────────────────────────────────────────────────────────────────
async def main():
    global redis_client
    redis_client = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)

    bot = Bot(BOT_TOKEN)
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Начать работу"),
            BotCommand(command="help", description="Справка"),
            BotCommand(command="token", description="Добавить Google API-ключ"),
            BotCommand(command="settings", description="Настройки"),
        ]
    )
    await router.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
