# ATLAS-site-bot

Небольшой проект на `FastAPI` + Telegram Bot для обработки заявок с сайта.

Что делает:

- принимает форму через API `POST /api/v1/forms`
- сохраняет заявки в `PostgreSQL`
- отправляет заявку сразу в несколько Telegram-чатов
- показывает статус в сообщении (`Заявка не обработана` -> `В работе` -> `Обработана: отказ`)
- меняет то же Telegram message через inline-кнопки
- умеет панель в Telegram: списки заявок по статусам + статистика (все время / 7 дней / 30 дней)
- делает retry отправки/редактирования Telegram-сообщений и шлет alert об ошибке в чат

## Поля формы

- `task` — задача
- `form_type` — тип формы (сейчас: `main_page`)
- `fio`
- `email`
- `phone`
- `company`

## Стек

- `FastAPI`
- `python-telegram-bot` (polling)
- `PostgreSQL`
- `Docker` / `docker-compose`
- `uv` (опционально для локальной разработки)
- `pytest`

## Переменные окружения

```bash
cp .env.example .env
```

Заполнить `.env`:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_IDS` (список через запятую)
- `SITE_URL`

## Запуск в Docker (рекомендуется)

```bash
docker compose up -d --build
```

Что поднимется:

- `app` (`FastAPI` + Telegram bot polling)
- `db` (`PostgreSQL`)

Сервисы настроены на автоперезапуск: `restart: unless-stopped`.

## Локальный запуск (опционально, через uv)

```bash
uv venv
source .venv/bin/activate
uv sync --dev
uv run uvicorn atlas_site_bot.main:app --reload --host 0.0.0.0 --port 8000
```

Если локально без Docker, укажи свой `DATABASE_URL` в `.env`.

## Пример запроса

```bash
curl -X POST http://127.0.0.1:8000/api/v1/forms \
  -H 'Content-Type: application/json' \
  -d '{
    "task": "Нужен аудит сайта",
    "form_type": "main_page",
    "fio": "Иван Иванов",
    "email": "ivan@example.com",
    "phone": "+79990000000",
    "company": "ATLAS"
  }'
```

## Тесты

```bash
uv run pytest
```

## Telegram bot: команды и интерфейс

- `/start` — возвращает текущий адрес сайта и меню
- `/dashboard` — открывает панель заявок

В панели доступны:

- `Не обработаны`
- `В работе`
- `Отказы`
- статистика `все / 7 дней / 30 дней`
- листание заявок и обработка кнопками прямо из панели
