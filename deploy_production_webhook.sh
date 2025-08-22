#!/bin/bash
# Скрипт для развертывания production webhook на сервер Bitrix
# Использование: ./deploy_production_webhook.sh

set -e

echo "🚀 РАЗВЕРТЫВАНИЕ PRODUCTION WEBHOOK"
echo "=================================="

# Конфигурация
PRODUCTION_SERVER="root@185.125.90.141"
BITRIX_PATH="/home/bitrix/www"
PYTHON_CRM_URL="http://localhost:8001"  # Временно локально для тестирования
WEBHOOK_TOKEN="fad5fbe4c8a520cf6d5453685b758c7fd9f6681f084be335fcdcd190ad9aaa0e"

echo "📋 Конфигурация:"
echo "  Server: $PRODUCTION_SERVER"
echo "  Bitrix Path: $BITRIX_PATH"
echo "  Python CRM URL: $PYTHON_CRM_URL"
echo ""

# Проверяем соединение с сервером
echo "🔗 Проверка соединения с production сервером..."
if ! ssh -o ConnectTimeout=10 $PRODUCTION_SERVER "echo 'Connection OK'" >/dev/null 2>&1; then
    echo "❌ Не удается подключиться к $PRODUCTION_SERVER"
    echo "   Проверьте SSH ключи и доступность сервера"
    exit 1
fi
echo "✅ Соединение установлено"

# Создаем резервную копию init.php
echo "💾 Создание резервной копии init.php..."
ssh $PRODUCTION_SERVER "
    cd $BITRIX_PATH/bitrix/php_interface
    if [ -f init.php ]; then
        cp init.php init.php.backup.\$(date +%Y%m%d_%H%M%S)
        echo '✅ Резервная копия создана'
    else
        echo '⚠️ Файл init.php не найден, будет создан новый'
    fi
"

# Подготавливаем webhook код для вставки
echo "📝 Подготовка webhook кода..."
TEMP_WEBHOOK_FILE=$(mktemp)
sed "s|https://your-python-crm-domain.com|$PYTHON_CRM_URL|g; s|production-secure-token-2025|$WEBHOOK_TOKEN|g" production_webhook_integration.php > $TEMP_WEBHOOK_FILE

# Копируем файл на сервер
echo "📤 Копирование webhook кода на сервер..."
scp $TEMP_WEBHOOK_FILE $PRODUCTION_SERVER:/tmp/webhook_code.php

# Добавляем webhook код в init.php
echo "🔧 Интеграция webhook в init.php..."
ssh $PRODUCTION_SERVER "
    cd $BITRIX_PATH/bitrix/php_interface
    
    # Проверяем, не добавлен ли уже webhook
    if grep -q 'Production Webhook Integration' init.php 2>/dev/null; then
        echo '⚠️ Webhook уже интегрирован в init.php'
        echo '   Для повторной установки удалите существующий код'
    else
        echo '' >> init.php
        echo '// === WEBHOOK INTEGRATION START ===' >> init.php
        cat /tmp/webhook_code.php | grep -v '<?php' >> init.php
        echo '// === WEBHOOK INTEGRATION END ===' >> init.php
        echo '✅ Webhook код добавлен в init.php'
    fi
    
    # Проверяем синтаксис PHP
    if php -l init.php > /dev/null; then
        echo '✅ Синтаксис PHP корректный'
    else
        echo '❌ ОШИБКА в синтаксисе PHP!'
        echo '   Восстанавливаем из резервной копии...'
        cp init.php.backup.* init.php
        exit 1
    fi
    
    # Очистка временных файлов
    rm -f /tmp/webhook_code.php
"

# Обновляем переменные окружения Python CRM
echo "🔧 Обновление .env файла Python CRM..."
if [ -f .env ]; then
    # Обновляем существующий .env файл
    sed -i.bak "s|WEBHOOK_TOKEN=.*|WEBHOOK_TOKEN=$WEBHOOK_TOKEN|g" .env
    if ! grep -q "WEBHOOK_TOKEN=" .env; then
        echo "WEBHOOK_TOKEN=$WEBHOOK_TOKEN" >> .env
    fi
    echo "✅ Файл .env обновлен"
else
    echo "⚠️ Файл .env не найден в текущей директории"
    echo "   Необходимо вручную добавить: WEBHOOK_TOKEN=$WEBHOOK_TOKEN"
fi

# Тестирование webhook
echo "🧪 Тестирование webhook интеграции..."
ssh $PRODUCTION_SERVER "
    # Проверяем, что файлы логов могут быть созданы
    touch /tmp/bitrix_webhook.log
    touch /tmp/failed_webhooks.json
    chmod 666 /tmp/bitrix_webhook.log /tmp/failed_webhooks.json
    echo '✅ Файлы логов подготовлены'
    
    # Проверяем доступность Python CRM
    if curl -s --connect-timeout 10 '$PYTHON_CRM_URL/health' > /dev/null; then
        echo '✅ Python CRM доступен'
    else
        echo '⚠️ Python CRM недоступен по адресу $PYTHON_CRM_URL'
        echo '   Webhook будет сохранять неудачные запросы в очередь'
    fi
"

# Настройка cron для обработки неудачных webhook
echo "⏰ Настройка cron для обработки очереди webhook..."
ssh $PRODUCTION_SERVER "
    # Добавляем cron job если его еще нет
    if ! crontab -l 2>/dev/null | grep -q 'processFailedWebhooks'; then
        (crontab -l 2>/dev/null || true; echo '*/5 * * * * php -r \"include \\'$BITRIX_PATH/bitrix/php_interface/init.php\\'; processFailedWebhooks();\" >> /tmp/cron_webhook.log 2>&1') | crontab -
        echo '✅ Cron job добавлен для обработки очереди webhook каждые 5 минут'
    else
        echo '✅ Cron job уже настроен'
    fi
"

# Очистка временных файлов
rm -f $TEMP_WEBHOOK_FILE

echo ""
echo "🎉 WEBHOOK УСПЕШНО РАЗВЕРНУТ!"
echo "============================="
echo ""
echo "📊 Мониторинг:"
echo "  Логи webhook:     ssh $PRODUCTION_SERVER 'tail -f /tmp/bitrix_webhook.log'"
echo "  Очередь ошибок:   ssh $PRODUCTION_SERVER 'cat /tmp/failed_webhooks.json'"
echo "  Логи cron:        ssh $PRODUCTION_SERVER 'tail -f /tmp/cron_webhook.log'"
echo ""
echo "🔧 Управление:"
echo "  Обработка очереди вручную: ssh $PRODUCTION_SERVER 'php -r \"include \\\"$BITRIX_PATH/bitrix/php_interface/init.php\\\"; processFailedWebhooks();\"'"
echo "  Просмотр cron jobs: ssh $PRODUCTION_SERVER 'crontab -l'"
echo ""
echo "⚠️ ВАЖНО:"
echo "  1. Замените $PYTHON_CRM_URL на реальный URL вашего Python CRM"
echo "  2. Убедитесь, что Python CRM доступен по HTTPS"
echo "  3. Протестируйте создание заказа в Bitrix"
echo "  4. Проверьте логи webhook после тестирования"
echo ""
echo "🧪 Тестирование:"
echo "  1. Создайте тестовый заказ в Bitrix админке"
echo "  2. Проверьте логи: tail -f /tmp/bitrix_webhook.log"
echo "  3. Убедитесь, что заказ появился в Python CRM"