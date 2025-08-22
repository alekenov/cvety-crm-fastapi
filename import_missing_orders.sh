#!/bin/bash
# Импорт недостающих заказов (17-19 августа) с продакшена в локальную MySQL

echo "📥 Получаем недостающие заказы с продакшена (17-19 августа)..."
echo "============================================================"
echo ""

# Экспортируем с продакшена
echo "🔗 Подключаемся к продакшену и экспортируем данные..."
ssh root@185.125.90.141 << 'ENDSSH'
cd /tmp

echo "📊 Экспортируем заказы за 17-19 августа 2025..."

# Экспорт заказов
mysqldump -u root -p'yQ~f*hajq~' cvety_db b_sale_order \
  --where="DATE(DATE_INSERT) BETWEEN '2025-08-17' AND '2025-08-19'" \
  --no-create-info \
  --complete-insert \
  --skip-triggers > orders_aug_17_19.sql

# Подсчет количества заказов
COUNT=$(grep -c "INSERT INTO" orders_aug_17_19.sql)
echo "  Найдено заказов: $COUNT"

# Получаем ID заказов для экспорта связанных данных
mysql -u root -p'yQ~f*hajq~' cvety_db -N -e "
  SELECT ID FROM b_sale_order 
  WHERE DATE(DATE_INSERT) BETWEEN '2025-08-17' AND '2025-08-19'
" > order_ids.txt

# Конвертируем в формат для WHERE IN
ORDER_IDS=$(cat order_ids.txt | tr '\n' ',' | sed 's/,$//')

if [ ! -z "$ORDER_IDS" ]; then
  echo "📦 Экспортируем товары в заказах..."
  mysqldump -u root -p'yQ~f*hajq~' cvety_db b_sale_basket \
    --where="ORDER_ID IN ($ORDER_IDS)" \
    --no-create-info \
    --complete-insert \
    --skip-triggers > basket_aug_17_19.sql
  
  echo "📝 Экспортируем свойства заказов..."
  mysqldump -u root -p'yQ~f*hajq~' cvety_db b_sale_order_props_value \
    --where="ORDER_ID IN ($ORDER_IDS)" \
    --no-create-info \
    --complete-insert \
    --skip-triggers > props_aug_17_19.sql
  
  # Создаем архив
  tar -czf orders_aug_17_19.tar.gz orders_aug_17_19.sql basket_aug_17_19.sql props_aug_17_19.sql
  echo "✅ Архив создан: /tmp/orders_aug_17_19.tar.gz"
else
  echo "⚠️ Заказы не найдены"
fi

# Очистка
rm -f order_ids.txt

ENDSSH

echo ""
echo "📥 Скачиваем архив с продакшена..."
scp root@185.125.90.141:/tmp/orders_aug_17_19.tar.gz ./

if [ -f orders_aug_17_19.tar.gz ]; then
  echo "📦 Распаковываем архив..."
  tar -xzf orders_aug_17_19.tar.gz
  
  echo ""
  echo "🔄 Импортируем в локальную MySQL..."
  
  # Проверяем что Docker контейнер запущен
  if docker ps | grep -q cvety_mysql; then
    # Импорт заказов
    if [ -f orders_aug_17_19.sql ]; then
      echo "  • Импортируем заказы..."
      docker exec -i cvety_mysql mysql -u root -pcvety123 cvety_db < orders_aug_17_19.sql
    fi
    
    # Импорт товаров
    if [ -f basket_aug_17_19.sql ]; then
      echo "  • Импортируем товары..."
      docker exec -i cvety_mysql mysql -u root -pcvety123 cvety_db < basket_aug_17_19.sql
    fi
    
    # Импорт свойств
    if [ -f props_aug_17_19.sql ]; then
      echo "  • Импортируем свойства..."
      docker exec -i cvety_mysql mysql -u root -pcvety123 cvety_db < props_aug_17_19.sql
    fi
    
    echo ""
    echo "✅ Импорт завершен!"
    
    # Проверяем результат
    echo ""
    echo "📊 Проверка импортированных данных:"
    docker exec cvety_mysql mysql -u root -pcvety123 cvety_db -e "
      SELECT 
        DATE(DATE_INSERT) as date,
        COUNT(*) as orders_count,
        MIN(ID) as first_id,
        MAX(ID) as last_id
      FROM b_sale_order
      WHERE DATE(DATE_INSERT) BETWEEN '2025-08-17' AND '2025-08-19'
      GROUP BY DATE(DATE_INSERT)
      ORDER BY date;
    "
    
  else
    echo "❌ Docker контейнер cvety_mysql не запущен!"
    echo "   Запустите: cd /Users/alekenov/cvety-local && docker-compose up -d"
  fi
  
  # Очистка временных файлов
  echo ""
  echo "🧹 Очистка временных файлов..."
  rm -f orders_aug_17_19.sql basket_aug_17_19.sql props_aug_17_19.sql
  
else
  echo "❌ Не удалось скачать архив с продакшена"
fi

echo ""
echo "Готово! Теперь можно тестировать миграцию:"
echo "  python3 migrate_from_local_mysql.py --count 10 --start-id 122005"