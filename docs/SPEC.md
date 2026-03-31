# SPEC — Technical Specification

## 1. Контекст

Ссылка на PRD: `docs/PRD.md`  
Цель документа: описать архитектуру, API и детали реализации Telegram-бота.

## 2. Технический стек

- Язык: `<Node.js / Python / ...>`
- Фреймворк бота: `<Telegraf / aiogram / ...>`
- Хранение данных: `<PostgreSQL / Redis / SQLite / ...>`
- Хостинг: `<Render / Fly.io / VPS / ...>`

## 3. Архитектура

### Компоненты

- Bot Handler Layer — обработчики команд и сообщений
- Service Layer — бизнес-логика
- Data Layer — доступ к БД/кэшу
- Integration Layer — внешние API

### Поток запроса

1. Пользователь отправляет сообщение в Telegram.
2. Webhook/Polling принимает событие.
3. Роутер выбирает обработчик.
4. Обработчик вызывает сервис.
5. Сервис читает/пишет данные и возвращает результат.
6. Бот отправляет ответ пользователю.

## 4. Структура кода (предложение)

```text
bot/
  src/
    bot/
      commands/
      middlewares/
      handlers/
    services/
    repositories/
    integrations/
    config/
    utils/
    index.<js|ts|py>
  tests/
```

## 5. API и контракты

### Команды Telegram

- `/start` — инициализация пользователя
- `/help` — список возможностей
- `/settings` — пользовательские настройки (опционально)

### Внутренние контракты

- `UserService.createOrUpdateUser(telegramUser)`  
- `MessageService.processIncomingMessage(message)`  
- `NotificationService.sendMessage(chatId, text)`

## 6. Модель данных (черновик)

### Таблица `users`

- `id`
- `telegram_id` (unique)
- `username`
- `first_name`
- `created_at`
- `updated_at`

### Таблица `events_log`

- `id`
- `user_id`
- `event_type`
- `payload`
- `created_at`

## 7. Конфигурация и переменные окружения

- `BOT_TOKEN`
- `APP_ENV`
- `LOG_LEVEL`
- `DATABASE_URL`
- `REDIS_URL` (если нужен кэш)

## 8. Ошибки и устойчивость

- Глобальный error handler
- Retries для внешних API
- Circuit breaker (по необходимости)
- Логирование ошибок с correlation id

## 9. Тестирование

- Unit-тесты для сервисов
- Integration-тесты для ключевых сценариев
- Smoke-тест команды `/start`

## 10. Безопасность

- Не хранить токены в коде
- Валидировать входные данные
- Ограничивать частоту запросов (rate limit)
- Минимизировать персональные данные в логах

## 11. План реализации

- Шаг 1: каркас проекта и запуск бота
- Шаг 2: базовые команды и middleware
- Шаг 3: подключение БД и хранение данных
- Шаг 4: бизнес-функции MVP
- Шаг 5: тесты и деплой

