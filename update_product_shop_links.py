#!/usr/bin/env python3
"""
Скрипт для обновления связей товар-магазин из продакшн MySQL в Supabase
Обновляет seller_id и seller_name для всех товаров на основе данных из MySQL
"""

import mysql.connector
from supabase import create_client
import os
from dotenv import load_dotenv
from datetime import datetime
import json
import time

# Загружаем переменные окружения
load_dotenv()

# Конфигурация продакшн MySQL
MYSQL_CONFIG = {
    'host': '185.125.90.141',
    'port': 3306,
    'user': 'usercvety',
    'password': 'QQlPCtTA@z2%mhy',
    'database': 'dbcvety'
}

# Конфигурация Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")

# Константы
SHOPS_IBLOCK_ID = 32  # ID инфоблока магазинов
SELLER_PROPERTY_ID = 290  # ID свойства "Продавец" для товаров
PRODUCTS_IBLOCK_IDS = [2, 17]  # ID инфоблоков товаров

def print_section(title: str):
    """Печать заголовка секции"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

def get_product_shop_links_from_mysql(limit=None):
    """Получить связи товар-магазин из продакшн MySQL"""
    print_section("Получение связей товар-магазин из MySQL")
    
    try:
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        cursor = conn.cursor(dictionary=True)
        
        # Сначала получаем общее количество связей
        count_query = f"""
        SELECT COUNT(DISTINCT ep.IBLOCK_ELEMENT_ID) as total
        FROM b_iblock_element_property ep
        JOIN b_iblock_element p ON p.ID = ep.IBLOCK_ELEMENT_ID
        JOIN b_iblock_element s ON s.ID = ep.VALUE
        WHERE ep.IBLOCK_PROPERTY_ID = {SELLER_PROPERTY_ID}
        AND p.IBLOCK_ID IN ({','.join(map(str, PRODUCTS_IBLOCK_IDS))})
        AND s.IBLOCK_ID = {SHOPS_IBLOCK_ID}
        AND ep.VALUE IS NOT NULL
        AND ep.VALUE != ''
        """
        
        cursor.execute(count_query)
        total_count = cursor.fetchone()['total']
        print(f"📊 Всего найдено связей товар-магазин: {total_count}")
        
        # Теперь получаем сами связи
        limit_clause = f"LIMIT {limit}" if limit else ""
        query = f"""
        SELECT 
            p.ID as product_bitrix_id,
            p.NAME as product_name,
            p.ACTIVE as product_active,
            s.ID as shop_bitrix_id,
            s.NAME as shop_name,
            s.ACTIVE as shop_active
        FROM b_iblock_element_property ep
        JOIN b_iblock_element p ON p.ID = ep.IBLOCK_ELEMENT_ID
        JOIN b_iblock_element s ON s.ID = ep.VALUE
        WHERE ep.IBLOCK_PROPERTY_ID = {SELLER_PROPERTY_ID}
        AND p.IBLOCK_ID IN ({','.join(map(str, PRODUCTS_IBLOCK_IDS))})
        AND s.IBLOCK_ID = {SHOPS_IBLOCK_ID}
        AND ep.VALUE IS NOT NULL
        AND ep.VALUE != ''
        ORDER BY s.NAME, p.NAME
        {limit_clause}
        """
        
        cursor.execute(query)
        links = cursor.fetchall()
        
        if limit:
            print(f"📦 Загружено {len(links)} связей (лимит: {limit})")
        else:
            print(f"📦 Загружено {len(links)} связей")
        
        # Показываем статистику по магазинам
        shop_stats = {}
        for link in links:
            shop_name = link['shop_name']
            if shop_name not in shop_stats:
                shop_stats[shop_name] = 0
            shop_stats[shop_name] += 1
        
        # Сортируем по количеству товаров
        sorted_shops = sorted(shop_stats.items(), key=lambda x: x[1], reverse=True)
        
        print("\n📊 Топ-10 магазинов по количеству товаров в выборке:")
        for i, (shop_name, count) in enumerate(sorted_shops[:10], 1):
            print(f"  {i}. {shop_name}: {count} товаров")
        
        cursor.close()
        conn.close()
        
        return links, total_count
        
    except mysql.connector.Error as e:
        print(f"❌ Ошибка MySQL: {e}")
        return [], 0

def get_shop_mapping(supabase):
    """Получить маппинг bitrix_id -> supabase_id для магазинов"""
    print_section("Создание маппинга магазинов")
    
    try:
        # Получаем все магазины из Supabase
        result = supabase.table('sellers')\
            .select('id, name, metadata')\
            .execute()
        
        if not result.data:
            print("❌ Магазины не найдены в Supabase")
            print("❗ Сначала запустите sync_shops_from_production.py")
            return {}
        
        # Создаем маппинг
        shop_mapping = {}
        for shop in result.data:
            if shop.get('metadata', {}).get('bitrix_id'):
                bitrix_id = str(shop['metadata']['bitrix_id'])
                shop_mapping[bitrix_id] = {
                    'id': shop['id'],
                    'name': shop['name']
                }
        
        print(f"✅ Создан маппинг для {len(shop_mapping)} магазинов")
        
        return shop_mapping
        
    except Exception as e:
        print(f"❌ Ошибка при создании маппинга: {e}")
        return {}

def update_product_links(links, shop_mapping, supabase, batch_size=100, dry_run=False):
    """Обновить связи товар-магазин в Supabase"""
    print_section(f"Обновление связей в Supabase {'(DRY RUN)' if dry_run else ''}")
    
    if not links:
        print("❌ Нет связей для обновления")
        return False
    
    if not shop_mapping:
        print("❌ Маппинг магазинов пустой")
        return False
    
    # Счетчики
    updated_count = 0
    not_found_products = 0
    not_found_shops = 0
    already_correct = 0
    error_count = 0
    
    print(f"\nОбрабатываем {len(links)} связей батчами по {batch_size}...")
    
    start_time = time.time()
    
    # Обрабатываем батчами
    for i in range(0, len(links), batch_size):
        batch = links[i:i + batch_size]
        batch_start = time.time()
        
        # Собираем bitrix_id товаров в батче
        product_bitrix_ids = [str(link['product_bitrix_id']) for link in batch]
        
        try:
            # Получаем товары из Supabase по bitrix_id
            products_result = supabase.table('products')\
                .select('id, name, seller_id, seller_name, metadata')\
                .in_('metadata->>bitrix_id', product_bitrix_ids)\
                .execute()
            
            if products_result.data:
                # Создаем словарь товаров
                products_dict = {}
                for product in products_result.data:
                    if product.get('metadata', {}).get('bitrix_id'):
                        bitrix_id = str(product['metadata']['bitrix_id'])
                        products_dict[bitrix_id] = product
                
                # Обновляем каждый товар
                for link in batch:
                    product_bitrix_id = str(link['product_bitrix_id'])
                    shop_bitrix_id = str(link['shop_bitrix_id'])
                    
                    if product_bitrix_id in products_dict:
                        product = products_dict[product_bitrix_id]
                        
                        if shop_bitrix_id in shop_mapping:
                            shop_info = shop_mapping[shop_bitrix_id]
                            
                            # Проверяем, нужно ли обновление
                            if product['seller_id'] == shop_info['id'] and product['seller_name'] == shop_info['name']:
                                already_correct += 1
                            else:
                                if not dry_run:
                                    # Обновляем товар
                                    update_result = supabase.table('products')\
                                        .update({
                                            'seller_id': shop_info['id'],
                                            'seller_name': shop_info['name'],
                                            'updated_at': 'now()'
                                        })\
                                        .eq('id', product['id'])\
                                        .execute()
                                    
                                    if update_result.data:
                                        updated_count += 1
                                        if updated_count <= 10:
                                            print(f"  ✅ Обновлен: {link['product_name'][:50]} -> {shop_info['name']}")
                                    else:
                                        error_count += 1
                                else:
                                    updated_count += 1
                                    if updated_count <= 10:
                                        print(f"  🔄 Будет обновлен: {link['product_name'][:50]} -> {shop_info['name']}")
                        else:
                            not_found_shops += 1
                            if not_found_shops <= 5:
                                print(f"  ❓ Магазин не найден в маппинге: {link['shop_name']} (ID: {shop_bitrix_id})")
                    else:
                        not_found_products += 1
            else:
                not_found_products += len(batch)
            
        except Exception as e:
            error_count += len(batch)
            print(f"  ❌ Ошибка при обработке батча: {e}")
        
        # Показываем прогресс
        batch_time = time.time() - batch_start
        total_time = time.time() - start_time
        avg_time = total_time / (i + batch_size)
        remaining = (len(links) - i - batch_size) * avg_time / batch_size
        
        if (i + batch_size) % 500 == 0 or (i + batch_size) >= len(links):
            print(f"  Прогресс: {min(i + batch_size, len(links))}/{len(links)} " +
                  f"(~{remaining:.0f}с осталось)")
            print(f"    Обновлено: {updated_count}, Уже корректны: {already_correct}, " +
                  f"Не найдено: товаров={not_found_products}, магазинов={not_found_shops}")
    
    total_time = time.time() - start_time
    
    # Итоговая статистика
    print_section("РЕЗУЛЬТАТЫ ОБНОВЛЕНИЯ СВЯЗЕЙ")
    print(f"📊 Всего обработано связей: {len(links)}")
    print(f"✅ Обновлено: {updated_count}")
    print(f"✓  Уже были корректны: {already_correct}")
    print(f"❓ Товары не найдены в Supabase: {not_found_products}")
    print(f"❓ Магазины не найдены в маппинге: {not_found_shops}")
    print(f"❌ Ошибки: {error_count}")
    print(f"⏱️  Время выполнения: {total_time:.1f} секунд")
    
    if not dry_run:
        # Сохраняем лог
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'total_links': len(links),
            'updated': updated_count,
            'already_correct': already_correct,
            'not_found_products': not_found_products,
            'not_found_shops': not_found_shops,
            'errors': error_count,
            'execution_time': total_time
        }
        
        log_file = f"update_product_links_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n📄 Лог сохранен в: {log_file}")
    
    return updated_count > 0

def verify_links():
    """Проверить результаты обновления связей"""
    print_section("Проверка результатов")
    
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Статистика по товарам
        total_products = supabase.table('products')\
            .select('id', count='exact')\
            .execute()
        
        with_seller = supabase.table('products')\
            .select('id', count='exact')\
            .not_.is_('seller_id', 'null')\
            .execute()
        
        without_seller = supabase.table('products')\
            .select('id', count='exact')\
            .is_('seller_id', 'null')\
            .execute()
        
        total_count = total_products.count if hasattr(total_products, 'count') else 0
        with_seller_count = with_seller.count if hasattr(with_seller, 'count') else 0
        without_seller_count = without_seller.count if hasattr(without_seller, 'count') else 0
        
        print(f"📊 Статистика товаров в Supabase:")
        print(f"  📦 Всего товаров: {total_count}")
        print(f"  ✅ С магазином: {with_seller_count} ({with_seller_count*100/total_count:.1f}%)")
        print(f"  ❌ Без магазина: {without_seller_count} ({without_seller_count*100/total_count:.1f}%)")
        
        # Топ магазинов по товарам
        print("\n📊 Топ-10 магазинов по количеству товаров:")
        
        sellers_result = supabase.table('sellers')\
            .select('id, name')\
            .execute()
        
        if sellers_result.data:
            shop_stats = []
            for seller in sellers_result.data[:50]:  # Проверяем первые 50 магазинов
                count_result = supabase.table('products')\
                    .select('id', count='exact')\
                    .eq('seller_id', seller['id'])\
                    .execute()
                
                count = count_result.count if hasattr(count_result, 'count') else 0
                if count > 0:
                    shop_stats.append({
                        'name': seller['name'],
                        'count': count
                    })
            
            # Сортируем и показываем топ-10
            shop_stats.sort(key=lambda x: x['count'], reverse=True)
            for i, shop in enumerate(shop_stats[:10], 1):
                print(f"  {i}. {shop['name']}: {shop['count']} товаров")
        
    except Exception as e:
        print(f"❌ Ошибка при проверке: {e}")

def main():
    """Основная функция"""
    print("\n" + "🔄 " * 20)
    print("  ОБНОВЛЕНИЕ СВЯЗЕЙ ТОВАР-МАГАЗИН")
    print("  MySQL (Bitrix Production) → Supabase")
    print("🔄 " * 20)
    
    # Проверка подключений
    print_section("Проверка подключений")
    
    # MySQL
    try:
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        conn.close()
        print("✅ Подключение к MySQL успешно")
    except mysql.connector.Error as e:
        print(f"❌ Не удается подключиться к MySQL: {e}")
        return
    
    # Supabase
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Не найдены переменные окружения для Supabase")
        return
    print("✅ Переменные окружения Supabase найдены")
    
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"❌ Ошибка подключения к Supabase: {e}")
        return
    
    # Меню действий
    print("\n" + "="*60)
    print("Выберите действие:")
    print("1. Обновить первые 1000 связей (тест)")
    print("2. Обновить первые 5000 связей")
    print("3. Обновить ВСЕ связи (может занять время)")
    print("4. Dry run - показать что будет сделано (первые 100)")
    print("5. Только проверить текущее состояние")
    print("0. Выход")
    
    choice = input("\nВаш выбор (0-5): ").strip()
    
    if choice == '0':
        print("❌ Выход")
        return
    elif choice == '5':
        verify_links()
        return
    elif choice in ['1', '2', '3', '4']:
        # Определяем параметры
        if choice == '1':
            limit = 1000
            dry_run = False
        elif choice == '2':
            limit = 5000
            dry_run = False
        elif choice == '3':
            limit = None
            dry_run = False
        else:  # choice == '4'
            limit = 100
            dry_run = True
        
        # Получаем связи из MySQL
        links, total_count = get_product_shop_links_from_mysql(limit=limit)
        
        if not links:
            print("\n❌ Не удалось получить связи из MySQL")
            return
        
        # Получаем маппинг магазинов
        shop_mapping = get_shop_mapping(supabase)
        
        if not shop_mapping:
            print("\n❌ Не удалось создать маппинг магазинов")
            print("❗ Сначала запустите sync_shops_from_production.py")
            return
        
        # Запрашиваем подтверждение
        if not dry_run:
            print(f"\n⚠️  Будет обновлено до {len(links)} связей товар-магазин")
            if limit is None:
                print(f"Всего в базе {total_count} связей - это может занять несколько минут!")
            response = input("Продолжить? (yes/no): ")
            
            if response.lower() not in ['yes', 'y', 'да']:
                print("\n❌ Обновление отменено")
                return
        
        # Выполняем обновление
        success = update_product_links(links, shop_mapping, supabase, dry_run=dry_run)
        
        if success and not dry_run:
            # Проверяем результаты
            verify_links()
            print("\n✅ Обновление связей завершено!")
        elif dry_run:
            print("\n✅ Dry run завершен. Используйте опции 1-3 для реального обновления")
        else:
            print("\n⚠️  Обновление завершено с предупреждениями")
    else:
        print("❌ Неверный выбор")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    main()