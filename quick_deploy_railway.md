# Быстрый деплой на Railway (15 минут)

## 🎯 Цель: Запустить FastAPI в облаке за 15 минут

### Шаг 1: Подготовка кода (2 минуты)

```bash
# 1. Создать requirements.txt
cd /Users/alekenov/cvety-local/crm_python
pip freeze > requirements.txt

# 2. Создать Procfile для Railway
echo "web: uvicorn app:app --host 0.0.0.0 --port \$PORT" > Procfile
```

### Шаг 2: Git репозиторий (3 минуты)

```bash
# Если еще нет git
git init
git add .
git commit -m "FastAPI CRM for Railway deployment"

# Создать репозиторий на GitHub
# Запушить код
```

### Шаг 3: Railway деплой (5 минут)

1. Зайти на https://railway.app
2. Sign up через GitHub
3. "New Project" → "Deploy from GitHub repo"
4. Выбрать ваш репозиторий
5. Railway автоматически определит Python и запустит

### Шаг 4: Environment Variables (3 минуты)

В Railway dashboard добавить:
```
SUPABASE_URL=https://ignabwiietecbznqnroh.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
WEBHOOK_TOKEN=fad5fbe4c8a520cf6d5453685b758c7fd9f6681f084be335fcdcd190ad9aaa0e
HOST=0.0.0.0
PORT=8000
```

### Шаг 5: Обновить webhook в Bitrix (2 минуты)

```bash
# SSH в продакшн
ssh root@185.125.90.141

# Изменить URL в webhook
nano /home/bitrix/www/local/php_interface/init.php

# Заменить:
# PYTHON_CRM_WEBHOOK_URL=http://localhost:8001/webhooks/bitrix/order
# На:
# PYTHON_CRM_WEBHOOK_URL=https://your-app.up.railway.app/webhooks/bitrix/order
```

## ✅ Результат:
- FastAPI работает 24/7 в облаке
- Webhook автоматически синхронизирует заказы
- Ваш Mac может быть выключен
- CRM доступен по https://your-app.up.railway.app/crm

## 💰 Стоимость:
- Первые $5 бесплатно
- Потом ~$5/месяц для базового использования

## 🔄 Альтернатива на сегодня:
Если времени нет на деплой, завтра утром:

```bash
# 1. Включить Mac
cd /Users/alekenov/cvety-local/crm_python
python3 -m uvicorn app:app --host 0.0.0.0 --port 8001 --reload &

# 2. SSH туннель
ssh -f -N -R 8001:localhost:8001 root@185.125.90.141

# 3. Проверить webhook
curl -X POST http://localhost:8001/webhooks/bitrix/order -H "Content-Type: application/json" -d '{"test": true}'

# Тогда новые заказы будут синхронизироваться автоматически
```