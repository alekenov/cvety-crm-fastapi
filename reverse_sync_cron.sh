#!/bin/bash
# Cron скрипт для обратной синхронизации

cd /Users/alekenov/cvety-local/crm_python
export PATH="/usr/local/bin:/usr/bin:/bin"

# Загружаем переменные окружения
source .env 2>/dev/null || true

# Запускаем тестовую синхронизацию (пока без реального Bitrix API)
python3 test_reverse_sync.py >> /tmp/reverse_sync_cron.log 2>&1

# Добавляем timestamp
echo "$(date): Reverse sync completed" >> /tmp/reverse_sync_cron.log
