#!/bin/bash
# Получение свежих заказов с продакшена за 18-19 августа 2025

echo "📥 Получаем свежие заказы с продакшена..."
echo "========================================="
echo ""

# Создаем SQL файл для экспорта
cat > export_orders.sql << 'EOF'
-- Экспортируем заказы за 18-19 августа 2025
SELECT 
    ID,
    ACCOUNT_NUMBER,
    STATUS_ID,
    PRICE,
    CURRENCY,
    USER_ID,
    PAY_SYSTEM_ID,
    PAYED,
    DATE_PAYED,
    PRICE_DELIVERY,
    DISCOUNT_VALUE,
    TAX_VALUE,
    USER_DESCRIPTION,
    COMMENTS,
    RESPONSIBLE_ID,
    DATE_INSERT,
    DATE_UPDATE
FROM b_sale_order
WHERE DATE(DATE_INSERT) BETWEEN '2025-08-18' AND '2025-08-19'
ORDER BY ID DESC
INTO OUTFILE '/tmp/orders_aug_18_19.csv'
FIELDS TERMINATED BY '|'
ENCLOSED BY '"'
LINES TERMINATED BY '\n';
EOF

echo "📤 Отправляем SQL на продакшн и выполняем..."
echo ""

# Выполняем на продакшене
ssh root@185.125.90.141 << 'ENDSSH'
echo "Подключено к продакшену"

# Создаем CSV с заказами
mysql -u root -pcvety123 cvety_db -e "
SELECT 
    o.ID,
    o.ACCOUNT_NUMBER,
    o.STATUS_ID,
    o.PRICE,
    o.CURRENCY,
    o.USER_ID,
    o.PAY_SYSTEM_ID,
    o.PAYED,
    o.DATE_PAYED,
    o.PRICE_DELIVERY,
    o.DISCOUNT_VALUE,
    o.TAX_VALUE,
    o.USER_DESCRIPTION,
    o.COMMENTS,
    o.RESPONSIBLE_ID,
    o.DATE_INSERT,
    o.DATE_UPDATE
FROM b_sale_order o
WHERE DATE(o.DATE_INSERT) BETWEEN '2025-08-18' AND '2025-08-19'
ORDER BY o.ID DESC;
" > /tmp/orders_aug_18_19.csv

# Считаем количество заказов
COUNT=$(wc -l < /tmp/orders_aug_18_19.csv)
echo "Найдено заказов: $((COUNT - 1))"

# Также экспортируем товары для этих заказов
mysql -u root -pcvety123 cvety_db -e "
SELECT 
    b.ID,
    b.ORDER_ID,
    b.PRODUCT_ID,
    b.NAME,
    b.PRICE,
    b.CURRENCY,
    b.QUANTITY,
    b.DISCOUNT_PRICE
FROM b_sale_basket b
WHERE b.ORDER_ID IN (
    SELECT ID FROM b_sale_order 
    WHERE DATE(DATE_INSERT) BETWEEN '2025-08-18' AND '2025-08-19'
);
" > /tmp/basket_aug_18_19.csv

# Экспортируем свойства заказов
mysql -u root -pcvety123 cvety_db -e "
SELECT 
    pv.ID,
    pv.ORDER_ID,
    pv.ORDER_PROPS_ID,
    pv.NAME,
    pv.VALUE,
    pv.CODE
FROM b_sale_order_props_value pv
JOIN b_sale_order_props p ON pv.ORDER_PROPS_ID = p.ID
WHERE pv.ORDER_ID IN (
    SELECT ID FROM b_sale_order 
    WHERE DATE(DATE_INSERT) BETWEEN '2025-08-18' AND '2025-08-19'
);
" > /tmp/props_aug_18_19.csv

echo "✅ Экспорт завершен"

ENDSSH

echo ""
echo "📥 Скачиваем файлы..."

# Скачиваем файлы
scp root@185.125.90.141:/tmp/orders_aug_18_19.csv ./
scp root@185.125.90.141:/tmp/basket_aug_18_19.csv ./
scp root@185.125.90.141:/tmp/props_aug_18_19.csv ./

echo ""
echo "✅ Файлы скачаны:"
echo "  - orders_aug_18_19.csv"
echo "  - basket_aug_18_19.csv"
echo "  - props_aug_18_19.csv"
echo ""

# Показываем первые строки
echo "📊 Пример данных (первые 3 заказа):"
head -n 4 orders_aug_18_19.csv

echo ""
echo "Для импорта в локальную MySQL запустите:"
echo "  python3 import_csv_to_mysql.py"