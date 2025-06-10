# 🛠️ Google Search Bot — @inlinegooglesearchbot

> Живой пример: **[@inlinegooglesearchbot](https://t.me/inlinegooglesearchbot)**  
> Бот ищет в Google прямо из любого чата Telegram через inline-режим.

---

## 👀 Что это

Телеграм-бот на `aiogram 3`, который оборачивает **Google Custom Search API**.  
Запросы кешируются в Redis, настройки хранятся в SQLite.

---

## 🚀 Быстрый старт (два варианта)

### 1. Fork ⇢ GitHub Actions (Production)

1. Сделайте fork репозитория.  
2. Сгенерируйте **SSH-ключ** и положите приватную часть в *Repository → Settings → Secrets → Actions*:  

   | Secret        | Что кладём      |
   |---------------|-----------------|
   | `SSH_HOST`    | IP вашего VPS   |
   | `SSH_USER`    | Логин           |
   | `SSH_PORT`    | (опц.) если ≠ 22 |
   | `SSH_KEY`     | приватный ключ  |
   | `BOT_TOKEN`   | токен бота из @BotFather |
   | `GOOGLE_CX`   | идентификатор поиска (см. ниже) |

3. На сервере установите **Docker** + `docker compose`.  
4. Пушьте в `main` — GitHub Actions сам всё соберёт и перезапустит контейнеры.

### 2. Локальный docker compose

```bash
git clone https://github.com/danosito/inlinegooglesearchbot.git
cd inlinegooglesearchbot
cp .env.sample .env            # заполните переменные
docker compose up -d --build
````

---

## 🔑 Как получить креденшалы

| Что нужно        | Где взять                                                                                     | Шаги                                                                                 |
| ---------------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `BOT_TOKEN`      | [@BotFather](https://t.me/BotFather)                                                          | `/newbot` → имя → юзернейм                                                           |
| `GOOGLE_CX`      | [Programmable Search Engine](https://programmablesearchengine.google.com/controlpanel/create) | «Поиск во всем интернете» → *Create* → копируйте **Search engine ID**                |
| `GOOGLE_API_KEY` | см. команда `/token` в боте                                                                   | Google Cloud Console → включить *Custom Search API* → *Create credentials → API key* |

---

## ⚙️ Технологии и структура

| Слой            | Технологии                           |
| --------------- |--------------------------------------|
| Бот             | Python 3.x, **aiogram 3**, `asyncio` |
| Кэш             | Redis 7 (alpine)                     |
| Хранилище       | SQLite (через `aiosqlite`)           |
| CI/CD           | GitHub Actions → SSH Deploy          |
| Контейнеризация | Docker + `docker compose`            |
| Линт/формат     | **ruff**                             |

---

# 🇬🇧 English README (project is primarily maintained in Russian)

## Google Search Bot — @inlinegooglesearchbot

Inline Telegram bot that shows Google search results inside any chat.

---

### Quick start

#### 1. Fork & GitHub Actions

* Add secrets (`SSH_HOST`, `SSH_USER`, `SSH_KEY`, `BOT_TOKEN`, `GOOGLE_CX`)
* Install Docker on your Linux VPS
* Every push to `main` triggers lint + auto-deploy (`docker compose up -d --build`)

#### 2. Local docker compose

```bash
git clone https://github.com/danosito/inlinegooglesearchbot.git
cd inlinegooglesearchbot
cp .env.sample .env   # fill variables
docker compose up -d --build
```

---

### Credentials

| Variable         | How to get                                                           |
| ---------------- | -------------------------------------------------------------------- |
| `BOT_TOKEN`      | Create bot via [@BotFather](https://t.me/BotFather)                  |
| `GOOGLE_CX`      | Create *Programmable Search Engine* → “Search the entire web”        |
| `GOOGLE_API_KEY` | Google Cloud Console → enable *Custom Search API* → create *API key* |

---

### Stack

* **Python 3.x** + `aiogram 3`
* Redis cache
* SQLite settings store
* Docker / docker-compose
* GitHub Actions CI/CD
* Lint & format via **ruff**

> Project is maintained in **Russian**; feel free to open issues in English too.
