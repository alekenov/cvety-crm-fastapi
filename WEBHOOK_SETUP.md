# 🔄 Настройка Webhook Синхронизации Bitrix ↔ Python CRM

## 📋 Что реализовано

### ✅ Готовые компоненты:

1. **Webhook endpoints в Python CRM**
   - `/api/webhooks/bitrix/order` - прием новых/обновленных заказов
   - `/api/webhooks/bitrix/status` - прием изменений статуса
   - `/api/sync/status` - API для получения статистики

2. **Трансформация данных**
   - `transformers/order_transformer.py` - преобразование структур Bitrix ↔ Supabase
   - Маппинг статусов, полей, свойств заказов

3. **PHP скрипт для Bitrix**
   - `bitrix_webhook.php` - готовый код для добавления в init.php
   - Обработчики событий создания и обновления заказов

4. **Обратная синхронизация**
   - `sync_back.py` - отправка изменений из CRM обратно в Bitrix
   - Автоматическая синхронизация при изменении статуса

5. **Мониторинг**
   - `/crm/sync` - страница мониторинга синхронизации
   - Статистика, логи, ошибки

## 🚀 Инструкция по запуску

### 1. Создание таблиц в Supabase

```bash
# Откройте Supabase Dashboard → SQL Editor
# Выполните скрипт:
cat create_sync_tables.sql
# Скопируйте и выполните в SQL Editor
```

### 2. Запуск Python CRM

```bash
cd /Users/alekenov/cvety-local/crm_python

# Установка зависимостей (если еще не установлены)
pip install -r requirements.txt

# Запуск сервера
python app.py
# Сервер запустится на http://localhost:8001
```

### 3. Тестирование webhook локально

```bash
# В новом терминале
cd /Users/alekenov/cvety-local/crm_python

# Запустите тест
python test_webhook.py
```

Ожидаемый результат:
```
✅ Сервер Python CRM доступен
🚀 Отправляем тестовый webhook...
✅ Webhook успешно обработан!
```

### 4. Проверка мониторинга

Откройте в браузере: http://localhost:8001/crm/sync

Вы должны увидеть:
- Статистику синхронизации
- Последние синхронизированные заказы
- Логи операций

## 🔧 Настройка на продакшене

### 1. Добавление PHP кода в Bitrix

SSH на продакшн сервер:
```bash
ssh root@185.125.90.141
```

Откройте файл init.php:
```bash
nano /home/bitrix/www/local/php_interface/init.php
```

Добавьте в конец файла:
```php
// Webhook интеграция с Python CRM
require_once(__DIR__ . '/webhook_integration.php');
```

Создайте файл webhook_integration.php:
```bash
nano /home/bitrix/www/local/php_interface/webhook_integration.php
```

Скопируйте содержимое из `bitrix_webhook.php` и измените:
- `WEBHOOK_URL` на адрес вашего Python CRM
- `WEBHOOK_TOKEN` на секретный токен

### 2. Настройка Python CRM на сервере

Если используете облачный хостинг (Render, Railway):

1. Добавьте переменные окружения:
   ```
   WEBHOOK_TOKEN=your-secret-token-here
   BITRIX_API_URL=https://cvety.kz/api/
   SYNC_ENABLED=true
   ```

2. Деплой приложения

3. Проверьте доступность:
   ```bash
   curl https://your-app.com/api/sync/status
   ```

### 3. Тестирование на продакшене

В Bitrix создайте тестовый заказ и проверьте:
1. Появился ли заказ в Python CRM
2. Логи в `/home/bitrix/www/upload/webhook_log.txt`
3. Страницу мониторинга в CRM

## 📊 Мониторинг и отладка

### Просмотр логов Bitrix:
```bash
tail -f /home/bitrix/www/upload/webhook_log.txt
```

### Просмотр логов Python:
```bash
# Локально
tail -f crm_python.log

# На сервере (если используете systemd)
journalctl -u crm-sync -f
```

### Проверка синхронизации через API:
```bash
curl -H "X-Webhook-Token: secret-webhook-token-2024" \
     https://your-crm.com/api/sync/status
```

## 🛠️ Устранение проблем

### Webhook не доходят до Python CRM

1. Проверьте токен в обеих системах
2. Проверьте URL в PHP скрипте
3. Проверьте файрвол/порты
4. Смотрите логи: `/home/bitrix/www/upload/webhook_log.txt`

### Заказы не появляются в Supabase

1. Проверьте таблицы `sync_mapping` и `sync_log`
2. Проверьте права доступа к Supabase
3. Смотрите Python логи на ошибки трансформации

### Обратная синхронизация не работает

1. Проверьте, создан ли PHP endpoint на Bitrix
2. Проверьте `BITRIX_API_URL` в конфигурации
3. Смотрите `sync_log` таблицу на ошибки

## 📈 Следующие шаги

1. **Настройка HTTPS** для продакшена
2. **Добавление retry логики** для failed webhooks
3. **Настройка алертов** при ошибках синхронизации
4. **Оптимизация производительности** для больших объемов
5. **Добавление синхронизации товаров и пользователей**

## 📞 Поддержка

При возникновении проблем проверьте:
- Логи в обеих системах
- Страницу мониторинга `/crm/sync`
- Таблицу `sync_log` в Supabase

---

**Готово к использованию!** 🎉