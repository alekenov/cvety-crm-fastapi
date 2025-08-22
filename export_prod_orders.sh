#!/bin/bash
# Скрипт для экспорта заказов с продакшена за 18-19 августа 2025

echo "📥 Экспорт заказов с продакшена за 18-19 августа 2025..."
echo "================================================"

# SSH команда для выполнения на продакшене
ssh root@185.125.90.141 << 'ENDSSH'

# Переходим в временную директорию
cd /tmp

# Экспортируем заказы за 18-19 августа
echo "Экспортируем заказы..."
mysql -u root -p cvety_db << 'ENDMYSQL' > orders_aug_18_19.sql
-- Экспортируем структуру и данные заказов за 18-19 августа 2025
SELECT CONCAT('INSERT INTO b_sale_order VALUES ', 
    GROUP_CONCAT(
        CONCAT('(', 
            ID, ',',
            IFNULL(LID, "NULL"), ',',
            IFNULL(CONCAT("'", ACCOUNT_NUMBER, "'"), "NULL"), ',',
            IFNULL(CONCAT("'", TRACKING_NUMBER, "'"), "NULL"), ',',
            IFNULL(PAY_SYSTEM_ID, "NULL"), ',',
            IFNULL(CONCAT("'", PAYED, "'"), "NULL"), ',',
            IFNULL(CONCAT("'", DATE_PAYED, "'"), "NULL"), ',',
            IFNULL(EMP_PAYED_ID, "NULL"), ',',
            IFNULL(CONCAT("'", CANCELED, "'"), "NULL"), ',',
            IFNULL(CONCAT("'", DATE_CANCELED, "'"), "NULL"), ',',
            IFNULL(EMP_CANCELED_ID, "NULL"), ',',
            IFNULL(CONCAT("'", REASON_CANCELED, "'"), "NULL"), ',',
            IFNULL(CONCAT("'", STATUS_ID, "'"), "NULL"), ',',
            IFNULL(CONCAT("'", DATE_STATUS, "'"), "NULL"), ',',
            IFNULL(EMP_STATUS_ID, "NULL"), ',',
            IFNULL(CONCAT("'", PRICE_DELIVERY, "'"), "NULL"), ',',
            IFNULL(CONCAT("'", ALLOW_DELIVERY, "'"), "NULL"), ',',
            IFNULL(CONCAT("'", DATE_ALLOW_DELIVERY, "'"), "NULL"), ',',
            IFNULL(EMP_ALLOW_DELIVERY_ID, "NULL"), ',',
            IFNULL(CONCAT("'", PRICE, "'"), "NULL"), ',',
            IFNULL(CONCAT("'", CURRENCY, "'"), "NULL"), ',',
            IFNULL(CONCAT("'", DISCOUNT_VALUE, "'"), "NULL"), ',',
            IFNULL(USER_ID, "NULL"), ',',
            IFNULL(PAY_VOUCHER_NUM, "NULL"), ',',
            IFNULL(CONCAT("'", PAY_VOUCHER_DATE, "'"), "NULL"), ',',
            IFNULL(CONCAT("'", TAX_VALUE, "'"), "NULL"), ',',
            IFNULL(CONCAT("'", STAT_GID, "'"), "NULL"), ',',
            IFNULL(CONCAT("'", RECURRING_ID, "'"), "NULL"), ',',
            IFNULL(CONCAT("'", RECOUNT_FLAG, "'"), "NULL"), ',',
            IFNULL(AFFILIATE_ID, "NULL"), ',',
            IFNULL(DELIVERY_ID, "NULL"), ',',
            IFNULL(CONCAT("'", DELIVERY_DOC_NUM, "'"), "NULL"), ',',
            IFNULL(CONCAT("'", DELIVERY_DOC_DATE, "'"), "NULL"), ',',
            IFNULL(CONCAT("'", STORE_ID, "'"), "NULL"), ',',
            IFNULL(ORDER_TOPIC, "NULL"), ',',
            IFNULL(RESPONSIBLE_ID, "NULL"), ',',
            IFNULL(CONCAT("'", DATE_PAY_BEFORE, "'"), "NULL"), ',',
            IFNULL(CONCAT("'", DATE_BILL, "'"), "NULL"), ',',
            IFNULL(CONCAT("'", USER_DESCRIPTION, "'"), "NULL"), ',',
            IFNULL(CONCAT("'", COMMENTS, "'"), "NULL"), ',',
            IFNULL(COMPANY_ID, "NULL"), ',',
            IFNULL(CONCAT("'", CREATED_BY, "'"), "NULL"), ',',
            IFNULL(CONCAT("'", DATE_INSERT, "'"), "NULL"), ',',
            IFNULL(CONCAT("'", DATE_UPDATE, "'"), "NULL"), ',',
            ')'
        )
    SEPARATOR ','), ';')
FROM b_sale_order
WHERE DATE(DATE_INSERT) BETWEEN '2025-08-18' AND '2025-08-19'
ORDER BY ID;
ENDMYSQL

echo "Заказы экспортированы в /tmp/orders_aug_18_19.sql"

# Экспортируем товары для этих заказов
echo "Экспортируем товары в заказах..."
mysql -u root -p cvety_db << 'ENDMYSQL' > basket_aug_18_19.sql
SELECT CONCAT('INSERT INTO b_sale_basket VALUES ', 
    GROUP_CONCAT(
        CONCAT('(', 
            b.ID, ',',
            -- Здесь все поля b_sale_basket
            ')'
        )
    SEPARATOR ','), ';')
FROM b_sale_basket b
JOIN b_sale_order o ON b.ORDER_ID = o.ID
WHERE DATE(o.DATE_INSERT) BETWEEN '2025-08-18' AND '2025-08-19'
GROUP BY b.ORDER_ID;
ENDMYSQL

echo "Товары экспортированы в /tmp/basket_aug_18_19.sql"

# Экспортируем свойства заказов
echo "Экспортируем свойства заказов..."
mysql -u root -p cvety_db << 'ENDMYSQL' > props_aug_18_19.sql
SELECT CONCAT('INSERT INTO b_sale_order_props_value VALUES ', 
    GROUP_CONCAT(
        CONCAT('(', 
            pv.ID, ',',
            -- Здесь все поля b_sale_order_props_value
            ')'
        )
    SEPARATOR ','), ';')
FROM b_sale_order_props_value pv
JOIN b_sale_order o ON pv.ORDER_ID = o.ID
WHERE DATE(o.DATE_INSERT) BETWEEN '2025-08-18' AND '2025-08-19'
GROUP BY pv.ORDER_ID;
ENDMYSQL

echo "Свойства экспортированы в /tmp/props_aug_18_19.sql"

# Создаем архив
tar -czf orders_aug_18_19.tar.gz orders_aug_18_19.sql basket_aug_18_19.sql props_aug_18_19.sql

echo "✅ Архив создан: /tmp/orders_aug_18_19.tar.gz"

ENDSSH

echo ""
echo "📥 Скачиваем архив с продакшена..."
scp root@185.125.90.141:/tmp/orders_aug_18_19.tar.gz ./

echo "✅ Архив скачан в текущую директорию"
echo ""
echo "Для импорта в локальную базу запустите:"
echo "  ./import_orders_to_local.sh"