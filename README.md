# CRM System - Cvety.kz

Простая CRM система на Python (FastAPI) для управления заказами и товарами. Подключается к существующей базе данных Supabase PostgreSQL.

## 🚀 Возможности

### 📊 Dashboard
- Статистика заказов за сегодня
- Общая выручка
- Распределение заказов по статусам
- Последние заказы

### 📦 Управление заказами
- Список всех заказов с пагинацией
- Фильтрация по статусу и поиск
- Детальная информация о заказе
- Изменение статуса заказа
- Просмотр товаров в заказе

### 🌸 Управление товарами
- Список товаров с поиском
- Редактирование товаров (название, цена, количество)
- Управление активностью товаров

## 🛠 Технологии

- **Backend**: Python 3.8+ + FastAPI
- **Database**: PostgreSQL (Supabase)
- **Frontend**: HTML + Jinja2 templates + CSS
- **Dependencies**: supabase-py, uvicorn, python-dotenv

## 📋 Требования

- Python 3.8 или выше
- Доступ к Supabase проекту с готовой БД

## 🔧 Установка и запуск

### 1. Установка зависимостей

```bash
cd crm_python
pip install -r requirements.txt
```

### 2. Настройка переменных окружения

Создайте файл `.env` на основе `.env.example`:

```bash
cp .env.example .env
```

Заполните необходимые данные:

```env
# Supabase credentials
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key-here
SUPABASE_SERVICE_KEY=your-service-key-here

# Local development settings
HOST=127.0.0.1
PORT=8001
DEBUG=true
```

### 3. Запуск приложения

```bash
python app.py
```

Или через uvicorn:

```bash
uvicorn app:app --reload --host 127.0.0.1 --port 8001
```

### 4. Открыть в браузере

Перейдите по адресу: [http://localhost:8001/crm](http://localhost:8001/crm)

## 📁 Структура проекта

```
crm_python/
├── app.py              # Основное FastAPI приложение
├── config.py           # Настройки приложения
├── models.py           # Pydantic модели данных
├── requirements.txt    # Python зависимости
├── .env.example       # Пример переменных окружения
├── README.md          # Документация
│
└── templates/         # HTML шаблоны
    ├── base.html      # Базовый шаблон
    ├── dashboard.html # Главная страница
    ├── orders.html    # Список заказов
    ├── order_detail.html # Детали заказа
    ├── products.html  # Список товаров
    ├── product_edit.html # Редактирование товара
    └── error.html     # Страница ошибки
```

## 🗄️ Структура базы данных

Приложение ожидает следующие таблицы в Supabase:

### `orders`
- `id` (uuid, primary key)
- `number` (varchar) - номер заказа
- `status` (varchar) - статус: new, processing, shipped, delivered, cancelled
- `recipient_name` (varchar) - имя получателя
- `recipient_phone` (varchar) - телефон получателя
- `delivery_address` (text) - адрес доставки
- `delivery_date` (date) - дата доставки
- `delivery_time` (varchar) - время доставки
- `total` (decimal) - общая сумма
- `payment_method` (varchar) - способ оплаты
- `payment_status` (varchar) - статус оплаты
- `comment` (text) - комментарий
- `postcard_text` (text) - текст открытки
- `created_at` (timestamp)
- `updated_at` (timestamp)

### `order_items`
- `id` (uuid, primary key)
- `order_id` (uuid, foreign key)
- `product_id` (uuid) - ID товара
- `product_name` (varchar) - название товара
- `quantity` (integer) - количество
- `price` (decimal) - цена за единицу

### `products`
- `id` (uuid, primary key)
- `name` (varchar) - название товара
- `slug` (varchar) - URL-friendly название
- `description` (text) - описание
- `price` (decimal) - цена
- `old_price` (decimal) - старая цена
- `quantity` (integer) - количество в наличии
- `category_id` (uuid) - ID категории
- `images` (jsonb) - массив URL изображений
- `attributes` (jsonb) - дополнительные атрибуты
- `is_active` (boolean) - активен ли товар
- `created_at` (timestamp)
- `updated_at` (timestamp)

## 🌐 API Endpoints

### Web Interface
- `GET /crm` - Dashboard
- `GET /crm/orders` - Список заказов
- `GET /crm/orders/{id}` - Детали заказа
- `POST /crm/orders/{id}/status` - Обновить статус заказа
- `GET /crm/products` - Список товаров
- `GET /crm/products/{id}/edit` - Форма редактирования товара
- `POST /crm/products/{id}/edit` - Сохранить изменения товара

### JSON API
- `GET /api/orders/stats` - Статистика заказов

## 🔧 Настройка

### Логирование
Логи выводятся в консоль. Уровень логирования можно изменить в `app.py`:

```python
logging.basicConfig(level=logging.INFO)  # или logging.DEBUG
```

### Пагинация
По умолчанию показывается 50 элементов на страницу. Можно изменить в соответствующих функциях.

## 🐛 Решение проблем

### Ошибка подключения к Supabase
1. Проверьте правильность URL и ключей в `.env`
2. Убедитесь, что используете Service Key, а не Anon Key для полного доступа

### Пустые данные
1. Убедитесь, что таблицы созданы в Supabase
2. Проверьте наличие данных в таблицах
3. Убедитесь, что RLS (Row Level Security) настроен корректно

### Ошибки при запуске
1. Проверьте версию Python: `python --version`
2. Убедитесь, что все зависимости установлены: `pip install -r requirements.txt`
3. Проверьте логи в консоли для подробностей

## 📱 Мобильная версия

Интерфейс адаптивен и работает на мобильных устройствах.

## 🔐 Безопасность

- Используется Service Key для полного доступа к Supabase
- Валидация данных через Pydantic модели
- HTTPS рекомендуется для продакшн среды

## 📈 Масштабирование

Для продакшн использования рекомендуется:
- Настроить reverse proxy (nginx)
- Использовать WSGI сервер (Gunicorn)
- Добавить Redis для кеширования
- Настроить мониторинг

## 🤝 Вклад в разработку

1. Создайте форк репозитория
2. Создайте ветку для вашей функции
3. Внесите изменения
4. Создайте Pull Request