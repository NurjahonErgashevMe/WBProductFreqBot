# Wildberries Products Frequency Bot

Этот бот анализирует категории Wildberries, собирает данные о товарах через Evirma API и предоставляет результаты в виде Excel-отчётов через Telegram.

## Требования

- **Python**: 3.7 или выше
- **Операционная система**: Windows, macOS, Linux
- **Telegram-бот**: Токен от @BotFather
- **Зависимости**: Указаны в `requirements.txt`

## Установка и запуск

### 1. Клонируйте репозиторий

```bash
git clone https://github.com/NurjahonErgashevMe/WBProductFreqBot
cd WBProductFreqBot
```

### 2. Настройте виртуальное окружение

Создайте и активируйте виртуальное окружение:

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows
```

### 3. Установите зависимости

Установите необходимые библиотеки из `requirements.txt`:

```bash
pip install -r requirements.txt
```

### 4. Настройте переменные окружения

Создайте файл `.env` в корне проекта и добавьте следующие переменные:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
ADMIN_ID=your_telegram_user_id,another_user_id
```

- `TELEGRAM_BOT_TOKEN`: Токен вашего Telegram-бота (получите через @BotFather).
- `ADMIN_ID`: Список Telegram ID пользователей, которым разрешён доступ (через запятую).

### 5. Запустите бота

Запустите основной скрипт:

```bash
python main.py
```

### 6. Используйте бота в Telegram

- Откройте Telegram и найдите вашего бота.
- Отправьте команду `/start` (доступно только для ADMIN_ID).
- Используйте `/parse` для анализа категории Wildberries.

## Структура проекта

- `/src/`: Исходный код бота.
  - `/bot/`: Логика Telegram-бота.
  - `/parser/`: Парсинг Wildberries и Evirma API.
  - `/services/`: Управление файлами и логами.
  - `/config/`: Настройки.
- `/output/`: Папка для Excel-отчётов (удаляются через 15 секунд после отправки).
- `/logs/`: Папка для логов (`wb_parser.log`).

## Команды бота

- `/start`: Показать приветственное сообщение и меню.
- `/parse`: Запросить URL категории Wildberries для анализа.
- `/list`: Показать список админов (только для админов).

## Примечания

- Бот доступен только пользователям, указанным в `ADMIN_ID`.
- Логи парсинга отправляются в Telegram и сохраняются в `/logs/wb_parser.log`.
- Excel-отчёты временно сохраняются в `/output/` и удаляются через 15 секунд после отправки.

## Устранение неполадок

- **Ошибка "No module found"**: Убедитесь, что вы активировали виртуальное окружение и установили зависимости.
- **Нет доступа к боту**: Проверьте, что ваш Telegram ID указан в `ADMIN_ID`.
- **Логи**: Проверьте `/logs/wb_parser.log` для диагностики ошибок.