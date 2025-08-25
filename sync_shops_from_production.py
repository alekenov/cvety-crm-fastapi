#!/usr/bin/env python3
"""
Скрипт для синхронизации магазинов из продакшн MySQL Bitrix в Supabase
Импортирует реальные магазины из продакшн базы данных
"""

import mysql.connector
from supabase import create_client
import os
from dotenv import load_dotenv
from datetime import datetime
import json
import sys

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

def print_section(title: str):
    """Печать заголовка секции"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

def get_shops_from_mysql(active_only=True):
    """Получить магазины из продакшн MySQL"""
    print_section(f"Получение {'активных' if active_only else 'всех'} магазинов из продакшн MySQL")
    
    try:
        # Подключение к MySQL
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        cursor = conn.cursor(dictionary=True)
        
        # Запрос для получения магазинов
        active_filter = "AND e.ACTIVE = 'Y'" if active_only else ""
        query = f"""
        SELECT 
            e.ID as bitrix_id,
            e.NAME as name,
            e.CODE as slug,
            e.ACTIVE,
            e.PREVIEW_TEXT as description,
            e.DATE_CREATE,
            e.TIMESTAMP_X,
            e.SORT as sort_order
        FROM b_iblock_element e
        WHERE e.IBLOCK_ID = {SHOPS_IBLOCK_ID}
        {active_filter}
        ORDER BY e.SORT, e.NAME
        """
        
        cursor.execute(query)
        shops = cursor.fetchall()
        
        print(f"✅ Найдено {len(shops)} магазинов в MySQL")
        
        # Подсчитываем товары для каждого магазина
        for shop in shops:
            count_query = f"""
            SELECT COUNT(DISTINCT ep.IBLOCK_ELEMENT_ID) as product_count
            FROM b_iblock_element_property ep
            WHERE ep.IBLOCK_PROPERTY_ID = {SELLER_PROPERTY_ID}
            AND ep.VALUE = %s
            """
            cursor.execute(count_query, (shop['bitrix_id'],))
            count_result = cursor.fetchone()
            shop['product_count'] = count_result['product_count'] if count_result else 0
        
        # Сортируем по количеству товаров для вывода топа
        shops_sorted = sorted(shops, key=lambda x: x['product_count'], reverse=True)
        
        # Показываем топ-10 магазинов
        print("\n📊 Топ-10 магазинов по количеству товаров:")
        for i, shop in enumerate(shops_sorted[:10], 1):
            status = "✅" if shop['ACTIVE'] == 'Y' else "❌"
            print(f"  {i}. {shop['name']} (ID: {shop['bitrix_id']}, Товаров: {shop['product_count']}) {status}")
        
        if len(shops) > 10:
            print(f"  ... и еще {len(shops) - 10} магазинов")
        
        cursor.close()
        conn.close()
        
        return shops
        
    except mysql.connector.Error as e:
        print(f"❌ Ошибка MySQL: {e}")
        return []

def clear_test_shops(supabase, dry_run=False):
    """Удалить тестовые магазины с emoji-названиями"""
    print_section("Очистка тестовых данных")
    
    try:
        # Получаем всех текущих продавцов
        result = supabase.table('sellers').select('id, name').execute()
        
        if result.data:
            # Ищем тестовых продавцов по emoji в названии
            emoji_chars = ['🌸', '🌺', '🌻', '🌷', '🌹', '💐', '🏪', '🎁', '🌼', '🌵']
            test_sellers = [
                s for s in result.data 
                if any(char in s['name'] for char in emoji_chars)
            ]
            
            if test_sellers:
                print(f"Найдено {len(test_sellers)} тестовых магазинов для удаления")
                
                if dry_run:
                    print("🔍 DRY RUN режим - показываем что будет удалено:")
                    for seller in test_sellers[:10]:
                        print(f"  - {seller['name']}")
                    if len(test_sellers) > 10:
                        print(f"  ... и еще {len(test_sellers) - 10} магазинов")
                else:
                    # Удаляем тестовых продавцов
                    deleted_count = 0
                    for seller in test_sellers:
                        try:
                            # Сначала обнуляем seller_id у товаров
                            supabase.table('products')\
                                .update({'seller_id': None, 'seller_name': None})\
                                .eq('seller_id', seller['id'])\
                                .execute()
                            
                            # Затем удаляем продавца
                            supabase.table('sellers')\
                                .delete()\
                                .eq('id', seller['id'])\
                                .execute()
                            
                            deleted_count += 1
                            if deleted_count <= 5:
                                print(f"  ❌ Удален: {seller['name']}")
                        except Exception as e:
                            print(f"  ⚠️  Ошибка при удалении {seller['name']}: {e}")
                    
                    print(f"✅ Удалено {deleted_count} тестовых магазинов")
            else:
                print("✅ Тестовые магазины не найдены")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при очистке: {e}")
        return False

def sync_shops_to_supabase(mysql_shops, dry_run=False):
    """Синхронизировать магазины в Supabase"""
    print_section(f"Синхронизация с Supabase {'(DRY RUN)' if dry_run else ''}")
    
    if not mysql_shops:
        print("❌ Нет магазинов для синхронизации")
        return False
    
    try:
        # Инициализация Supabase клиента
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Очищаем тестовые данные
        if not dry_run:
            clear_test_shops(supabase)
        
        # Получаем существующие магазины из Supabase
        existing_result = supabase.table('sellers')\
            .select('id, name, metadata')\
            .execute()
        
        # Создаем словарь существующих магазинов по bitrix_id
        existing_shops = {}
        if existing_result.data:
            for shop in existing_result.data:
                if shop.get('metadata', {}).get('bitrix_id'):
                    bitrix_id = str(shop['metadata']['bitrix_id'])
                    existing_shops[bitrix_id] = shop
        
        # Счетчики
        created_count = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0
        
        print(f"\nНачинаем синхронизацию {len(mysql_shops)} магазинов...")
        print(f"Уже существует в Supabase: {len(existing_shops)} магазинов")
        
        # Обрабатываем магазины батчами
        batch_size = 50
        for i in range(0, len(mysql_shops), batch_size):
            batch = mysql_shops[i:i + batch_size]
            
            for shop in batch:
                try:
                    bitrix_id = str(shop['bitrix_id'])
                    
                    # Подготавливаем данные для вставки/обновления
                    shop_data = {
                        'name': shop['name'],
                        'slug': shop['slug'] or shop['name'].lower().replace(' ', '-').replace('.', ''),
                        'description': shop['description'],
                        'is_active': shop['ACTIVE'] == 'Y',
                        'metadata': {
                            'bitrix_id': shop['bitrix_id'],
                            'product_count': shop['product_count'],
                            'sort_order': shop.get('sort_order', 500),
                            'created_at': shop['DATE_CREATE'].isoformat() if shop['DATE_CREATE'] else None,
                            'updated_at': shop['TIMESTAMP_X'].isoformat() if shop['TIMESTAMP_X'] else None,
                            'synced_at': datetime.now().isoformat()
                        }
                    }
                    
                    if dry_run:
                        if bitrix_id in existing_shops:
                            print(f"  🔄 Будет обновлен: {shop['name']}")
                            updated_count += 1
                        else:
                            print(f"  ➕ Будет создан: {shop['name']}")
                            created_count += 1
                    else:
                        if bitrix_id in existing_shops:
                            # Обновляем существующий магазин
                            result = supabase.table('sellers')\
                                .update(shop_data)\
                                .eq('id', existing_shops[bitrix_id]['id'])\
                                .execute()
                            
                            if result.data:
                                updated_count += 1
                                if updated_count <= 5:
                                    print(f"  ✅ Обновлен: {shop['name']} ({shop['product_count']} товаров)")
                        else:
                            # Создаем новый магазин
                            result = supabase.table('sellers')\
                                .insert(shop_data)\
                                .execute()
                            
                            if result.data:
                                created_count += 1
                                if created_count <= 5:
                                    print(f"  ✅ Создан: {shop['name']} (ID: {result.data[0]['id']}, {shop['product_count']} товаров)")
                    
                except Exception as e:
                    error_count += 1
                    print(f"  ❌ Ошибка для {shop['name']}: {e}")
            
            # Показываем прогресс
            if (i + batch_size) % 100 == 0 or (i + batch_size) >= len(mysql_shops):
                print(f"  Обработано: {min(i + batch_size, len(mysql_shops))}/{len(mysql_shops)}")
        
        # Итоговая статистика
        print_section("РЕЗУЛЬТАТЫ СИНХРОНИЗАЦИИ")
        print(f"📊 Всего магазинов в MySQL: {len(mysql_shops)}")
        print(f"✅ Создано новых: {created_count}")
        print(f"🔄 Обновлено существующих: {updated_count}")
        print(f"⏭️  Пропущено: {skipped_count}")
        print(f"❌ Ошибки: {error_count}")
        
        if not dry_run:
            # Сохраняем лог
            log_data = {
                'timestamp': datetime.now().isoformat(),
                'total_mysql': len(mysql_shops),
                'created': created_count,
                'updated': updated_count,
                'skipped': skipped_count,
                'errors': error_count,
                'top_shops': [
                    {
                        'name': s['name'],
                        'bitrix_id': s['bitrix_id'],
                        'product_count': s['product_count'],
                        'active': s['ACTIVE'] == 'Y'
                    }
                    for s in sorted(mysql_shops, key=lambda x: x['product_count'], reverse=True)[:20]
                ]
            }
            
            log_file = f"sync_shops_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, ensure_ascii=False, indent=2)
            
            print(f"\n📄 Лог сохранен в: {log_file}")
        
        return created_count + updated_count > 0
        
    except Exception as e:
        print(f"❌ Критическая ошибка Supabase: {e}")
        return False

def verify_sync():
    """Проверить результаты синхронизации"""
    print_section("Проверка результатов")
    
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Получаем статистику по магазинам
        all_shops = supabase.table('sellers')\
            .select('id, name, is_active, metadata')\
            .execute()
        
        if all_shops.data:
            active_shops = [s for s in all_shops.data if s.get('is_active')]
            inactive_shops = [s for s in all_shops.data if not s.get('is_active')]
            
            print(f"📊 Статистика магазинов в Supabase:")
            print(f"  ✅ Активных: {len(active_shops)}")
            print(f"  ❌ Неактивных: {len(inactive_shops)}")
            print(f"  📦 Всего: {len(all_shops.data)}")
            
            # Показываем топ магазинов по количеству товаров
            shops_with_products = []
            for shop in all_shops.data:
                # Подсчитываем товары
                count_result = supabase.table('products')\
                    .select('id', count='exact')\
                    .eq('seller_id', shop['id'])\
                    .execute()
                
                product_count = count_result.count if hasattr(count_result, 'count') else 0
                shops_with_products.append({
                    'name': shop['name'],
                    'product_count': product_count,
                    'bitrix_id': shop.get('metadata', {}).get('bitrix_id', '-'),
                    'active': shop.get('is_active')
                })
            
            # Сортируем по количеству товаров
            shops_with_products.sort(key=lambda x: x['product_count'], reverse=True)
            
            print("\n📊 Топ-10 магазинов по количеству товаров в Supabase:")
            for i, shop in enumerate(shops_with_products[:10], 1):
                status = "✅" if shop['active'] else "❌"
                print(f"  {i}. {shop['name']} (Bitrix ID: {shop['bitrix_id']}, Товаров: {shop['product_count']}) {status}")
        else:
            print("❌ Магазины не найдены в Supabase")
        
    except Exception as e:
        print(f"❌ Ошибка при проверке: {e}")

def main():
    """Основная функция"""
    print("\n" + "🔄 " * 20)
    print("  СИНХРОНИЗАЦИЯ МАГАЗИНОВ ИЗ ПРОДАКШН")
    print("  MySQL (Bitrix Production) → Supabase")
    print("🔄 " * 20)
    
    # Проверка подключения к продакшн MySQL
    print_section("Проверка подключения к продакшн MySQL")
    try:
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()
        print(f"✅ Подключение успешно. MySQL версия: {version[0]}")
        cursor.close()
        conn.close()
    except mysql.connector.Error as e:
        print(f"❌ Не удается подключиться к продакшн MySQL: {e}")
        print("❗ Проверьте настройки подключения и VPN если требуется")
        return
    
    # Проверка Supabase
    print_section("Проверка подключения к Supabase")
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Не найдены переменные окружения SUPABASE_URL или SUPABASE_KEY")
        print("❗ Создайте файл .env с необходимыми переменными")
        return
    print("✅ Переменные окружения найдены")
    
    # Меню действий
    print("\n" + "="*60)
    print("Выберите действие:")
    print("1. Синхронизировать только АКТИВНЫЕ магазины (рекомендуется)")
    print("2. Синхронизировать ВСЕ магазины (активные и неактивные)")
    print("3. Dry run - показать что будет сделано без изменений")
    print("4. Только проверить текущее состояние")
    print("0. Выход")
    
    choice = input("\nВаш выбор (1-4, 0): ").strip()
    
    if choice == '0':
        print("❌ Выход")
        return
    elif choice == '4':
        verify_sync()
        return
    elif choice in ['1', '2', '3']:
        # Определяем параметры
        active_only = choice == '1'
        dry_run = choice == '3'
        
        # Получаем магазины из MySQL
        mysql_shops = get_shops_from_mysql(active_only=active_only)
        
        if mysql_shops:
            # Запрашиваем подтверждение
            if not dry_run:
                print(f"\n⚠️  Будет синхронизировано {len(mysql_shops)} магазинов")
                print("Это удалит тестовые магазины и заменит их реальными данными!")
                response = input("Продолжить? (yes/no): ")
                
                if response.lower() not in ['yes', 'y', 'да']:
                    print("\n❌ Синхронизация отменена")
                    return
            
            # Выполняем синхронизацию
            success = sync_shops_to_supabase(mysql_shops, dry_run=dry_run)
            
            if success and not dry_run:
                # Проверяем результаты
                verify_sync()
                print("\n✅ Синхронизация завершена успешно!")
                print("\n💡 Следующий шаг: запустите update_product_shop_links.py для обновления связей товаров")
            elif dry_run:
                print("\n✅ Dry run завершен. Используйте опцию 1 или 2 для реальной синхронизации")
            else:
                print("\n⚠️  Синхронизация завершена с ошибками")
        else:
            print("\n❌ Не удалось получить магазины из MySQL")
    else:
        print("❌ Неверный выбор")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    main()