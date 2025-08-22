#!/bin/bash
# Настройка cron для обратной синхронизации

echo "⏰ НАСТРОЙКА АВТОМАТИЧЕСКОЙ ОБРАТНОЙ СИНХРОНИЗАЦИИ"
echo "================================================"

SCRIPT_DIR=$(pwd)
PYTHON_PATH=$(which python3)

echo "📍 Рабочая директория: $SCRIPT_DIR"
echo "🐍 Python путь: $PYTHON_PATH"

# Создаем простой cron-совместимый скрипт
cat > reverse_sync_cron.sh << 'EOF'
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
EOF

chmod +x reverse_sync_cron.sh

echo "✅ Создан скрипт: reverse_sync_cron.sh"

# Проверяем существующие cron jobs
echo ""
echo "📋 Текущие cron jobs:"
crontab -l 2>/dev/null || echo "  (пусто)"

echo ""
echo "🔧 Добавление cron job для обратной синхронизации..."

# Добавляем cron job (каждые 5 минут)
CRON_JOB="*/5 * * * * $SCRIPT_DIR/reverse_sync_cron.sh"

# Получаем существующие cron jobs и добавляем новый
(crontab -l 2>/dev/null | grep -v "reverse_sync_cron.sh"; echo "$CRON_JOB") | crontab -

echo "✅ Cron job добавлен!"

echo ""
echo "📊 МОНИТОРИНГ:"
echo "  Логи: tail -f /tmp/reverse_sync_cron.log"
echo "  Проверка cron: crontab -l"
echo "  Тест скрипта: ./reverse_sync_cron.sh"

echo ""
echo "🧪 Запуск тестирования..."
./reverse_sync_cron.sh

echo ""
echo "✅ АВТОМАТИЧЕСКАЯ ОБРАТНАЯ СИНХРОНИЗАЦИЯ НАСТРОЕНА!"
echo "   Будет выполняться каждые 5 минут"