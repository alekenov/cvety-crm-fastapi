# План развертывания FastAPI в облаке

## 🎯 Цель
Перенести FastAPI приложение из локального Mac в облако для 24/7 работы webhook синхронизации.

## 🚀 Вариант 1: Cloudflare Workers (Быстро)

### Преимущества:
- Бесплатно до 100k запросов/день
- Глобальная CDN
- Автоматическое масштабирование
- Минимальная задержка

### Шаги:
1. Установить Wrangler CLI: `npm install -g wrangler`
2. Адаптировать FastAPI под Workers format
3. Настроить environment variables
4. Деплой: `wrangler deploy`

### Изменения в коде:
```python
# worker.py - адаптер для Cloudflare Workers
from fastapi import FastAPI
from app import app

def handler(request):
    # Обработка запросов в формате Workers
    return app
```

## 🐳 Вариант 2: Railway/Render (Альтернатива)

### Railway:
- Простой деплой из GitHub
- Автоматический HTTPS
- PostgreSQL включен
- $5/месяц

### Render:
- Бесплатный tier
- Автоматический деплой
- Встроенный monitoring

## 🔧 Вариант 3: VPS (Максимальный контроль)

### DigitalOcean/Hetzner:
- Ubuntu 22.04 LTS
- Docker + docker-compose
- nginx reverse proxy
- SSL через Let's Encrypt

### Стоимость: $5-10/месяц

## 📋 Checklist для миграции:

### 1. Подготовка кода:
- [ ] Добавить health check endpoint
- [ ] Настроить логирование 
- [ ] Добавить error handling
- [ ] Тесты для webhook

### 2. Environment Variables:
- [ ] SUPABASE_URL
- [ ] SUPABASE_ANON_KEY  
- [ ] WEBHOOK_TOKEN
- [ ] Все остальные из .env

### 3. Настройка производства:
- [ ] Изменить webhook URL в Bitrix
- [ ] Настроить monitoring
- [ ] Backup стратегия
- [ ] SSL сертификаты

### 4. Тестирование:
- [ ] Webhook получает заказы
- [ ] Данные сохраняются в Supabase
- [ ] CRM показывает актуальные заказы
- [ ] Обработка ошибок работает

## 🔄 Обновление webhook в продакшене:

```php
// В /home/bitrix/www/local/php_interface/init.php
define('PYTHON_CRM_WEBHOOK_URL', 'https://your-app.workers.dev/webhooks/bitrix/order');
```

## ⏱️ Временная схема работы:

### До миграции:
1. Mac включен → Webhook работает
2. Mac выключен → Заказы накапливаются в Bitrix
3. Mac включен → Ручная синхронизация

### После миграции:
1. Заказы поступают 24/7 → Автоматическая синхронизация
2. CRM всегда актуален
3. Независимость от локального Mac