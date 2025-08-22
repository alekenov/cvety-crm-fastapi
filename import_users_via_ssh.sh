#!/bin/bash
# Импорт отсутствующих пользователей через SSH

echo "📥 Импорт отсутствующих пользователей из production"
echo "=================================================="

# Отсутствующие пользователи
MISSING_USERS="171532,171533,171534,171535"

echo "👥 Пользователи для импорта: $MISSING_USERS"
echo ""

# Экспортируем пользователей с production
echo "🔗 Подключаемся к production и экспортируем пользователей..."
ssh root@185.125.90.141 << ENDSSH
cd /tmp

echo "Экспортируем пользователей с ID: $MISSING_USERS"
mysqldump -u usercvety -p'QQlPCtTA@z2%mhy' dbcvety b_user \
  --where="ID IN ($MISSING_USERS)" \
  --no-create-info \
  --complete-insert \
  --skip-triggers > missing_users.sql

# Также экспортируем дополнительные поля пользователей
mysqldump -u usercvety -p'QQlPCtTA@z2%mhy' dbcvety b_uts_user \
  --where="VALUE_ID IN ($MISSING_USERS)" \
  --no-create-info \
  --complete-insert \
  --skip-triggers > missing_users_fields.sql

echo "Создаем архив..."
tar -czf missing_users.tar.gz missing_users.sql missing_users_fields.sql

# Показываем что получилось
echo "Найдено пользователей:"
grep -c "INSERT INTO" missing_users.sql

ENDSSH

echo ""
echo "📥 Скачиваем архив с пользователями..."
scp root@185.125.90.141:/tmp/missing_users.tar.gz ./

if [ -f missing_users.tar.gz ]; then
  echo "📦 Распаковываем архив..."
  tar -xzf missing_users.tar.gz
  
  echo ""
  echo "🔄 Импортируем в локальную MySQL..."
  
  # Проверяем Docker
  if docker ps | grep -q cvety_mysql; then
    # Импортируем пользователей
    if [ -f missing_users.sql ]; then
      echo "  • Импортируем основные данные пользователей..."
      docker exec -i cvety_mysql mysql -u root -pcvety123 cvety_db < missing_users.sql
    fi
    
    # Импортируем дополнительные поля (если есть)
    if [ -f missing_users_fields.sql ]; then
      echo "  • Импортируем дополнительные поля пользователей..."
      docker exec -i cvety_mysql mysql -u root -pcvety123 cvety_db < missing_users_fields.sql
    fi
    
    echo ""
    echo "✅ Импорт в локальную MySQL завершен!"
    
    # Проверяем результат
    echo ""
    echo "📊 Проверка импортированных пользователей:"
    docker exec cvety_mysql mysql -u root -pcvety123 cvety_db -e "
      SELECT 
        ID,
        LOGIN,
        EMAIL,
        NAME,
        LAST_NAME,
        PERSONAL_PHONE,
        DATE_REGISTER
      FROM b_user
      WHERE ID IN ($MISSING_USERS)
      ORDER BY ID;
    "
    
    # Теперь запускаем Python скрипт для импорта в Supabase
    echo ""
    echo "🚀 Запускаем импорт в Supabase..."
    python3 import_missing_users_from_local.py $MISSING_USERS
    
  else
    echo "❌ Docker контейнер cvety_mysql не запущен!"
    echo "   Запустите: cd /Users/alekenov/cvety-local && docker-compose up -d"
  fi
  
  # Очистка
  echo ""
  echo "🧹 Очистка временных файлов..."
  rm -f missing_users.sql missing_users_fields.sql missing_users.tar.gz
  
else
  echo "❌ Не удалось скачать архив с пользователями"
fi

echo ""
echo "Готово! Теперь можно тестировать миграцию заказов."