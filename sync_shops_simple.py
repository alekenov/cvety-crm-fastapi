#!/usr/bin/env python3
"""
Упрощенная синхронизация магазинов без использования metadata
Сохраняет bitrix_id в slug в формате: shop-name-bitrixID
"""

import subprocess
from supabase import create_client
import os
from dotenv import load_dotenv
from datetime import datetime
import json
import re

# Загружаем переменные окружения
load_dotenv()

# Конфигурация SSH и MySQL
SSH_HOST = "root@185.125.90.141"
MYSQL_USER = "usercvety"
MYSQL_PASS = "QQlPCtTA@z2%mhy"
MYSQL_DB = "dbcvety"

# Конфигурация Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")

# Константы
SHOPS_IBLOCK_ID = 32
SELLER_PROPERTY_ID = 290

def print_section(title: str):
    """Печать заголовка секции"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

def execute_mysql_query(query):
    """Выполнить MySQL запрос через SSH"""
    cmd = f'ssh {SSH_HOST} "export LANG=C; mysql -u {MYSQL_USER} -p\'{MYSQL_PASS}\' {MYSQL_DB} -N -e \\"{query}\\" 2>&1 | grep -v \\"warning: setlocale\\" | grep -v \\"Warning] Using a password\\""'
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            # Альтернативный вариант
            cmd_alt = f'ssh {SSH_HOST} "export LANG=C; mysql -u {MYSQL_USER} -p\'{MYSQL_PASS}\' {MYSQL_DB} -N -e \\"{query}\\""'
            result_alt = subprocess.run(cmd_alt, shell=True, capture_output=True, text=True, timeout=30)
            if result_alt.returncode == 0:
                lines = result_alt.stdout.strip().split('\n')
                filtered_lines = [
                    line for line in lines 
                    if not ('warning: setlocale' in line or 'Warning] Using a password' in line)
                ]
                return '\n'.join(filtered_lines)
        return None
    except Exception as e:
        print(f"Ошибка: {e}")
        return None

def get_top_shops_from_mysql():
    """Получить топовые магазины с товарами из MySQL"""
    print_section("Получение топовых магазинов из MySQL")
    
    # Сначала получаем магазины с товарами
    query = """
    SELECT 
        s.ID as shop_id,
        s.NAME as shop_name,
        s.CODE as shop_code,
        s.ACTIVE,
        COUNT(DISTINCT ep.IBLOCK_ELEMENT_ID) as product_count
    FROM b_iblock_element s
    LEFT JOIN b_iblock_element_property ep ON ep.VALUE = s.ID AND ep.IBLOCK_PROPERTY_ID = 290
    WHERE s.IBLOCK_ID = 32 
    AND s.ACTIVE = 'Y'
    GROUP BY s.ID, s.NAME, s.CODE, s.ACTIVE
    HAVING product_count > 0
    ORDER BY product_count DESC
    LIMIT 50
    """.replace('\n', ' ')
    
    print("Загружаем топ-50 магазинов с товарами...")
    result = execute_mysql_query(query)
    
    if not result:
        print("❌ Не удалось получить данные")
        return []
    
    shops = []
    lines = result.split('\n')
    
    for line in lines:
        if line.strip():
            parts = line.split('\t')
            if len(parts) >= 5:
                shop = {
                    'bitrix_id': int(parts[0]) if parts[0].isdigit() else 0,
                    'name': parts[1],
                    'original_slug': parts[2] if parts[2] else None,
                    'ACTIVE': parts[3],
                    'product_count': int(parts[4]) if parts[4].isdigit() else 0
                }
                # Создаем уникальный slug с bitrix_id
                base_slug = shop['original_slug'] or re.sub(r'[^a-z0-9-]', '-', shop['name'].lower())
                shop['unique_slug'] = f"{base_slug}-bid{shop['bitrix_id']}"
                shops.append(shop)
    
    print(f"✅ Найдено {len(shops)} магазинов с товарами")
    
    if shops:
        print("\n📊 Топ-10 магазинов по количеству товаров:")
        for i, shop in enumerate(shops[:10], 1):
            print(f"  {i}. {shop['name']} (ID: {shop['bitrix_id']}, Товаров: {shop['product_count']})")
    
    # Теперь получаем остальные активные магазины без товаров
    query2 = """
    SELECT ID, NAME, CODE, ACTIVE
    FROM b_iblock_element
    WHERE IBLOCK_ID = 32 
    AND ACTIVE = 'Y'
    AND ID NOT IN (
        SELECT DISTINCT s.ID
        FROM b_iblock_element s
        JOIN b_iblock_element_property ep ON ep.VALUE = s.ID AND ep.IBLOCK_PROPERTY_ID = 290
        WHERE s.IBLOCK_ID = 32
    )
    ORDER BY NAME
    LIMIT 150
    """.replace('\n', ' ')
    
    print("\nЗагружаем остальные активные магазины...")
    result2 = execute_mysql_query(query2)
    
    if result2:
        lines2 = result2.split('\n')
        count_without_products = 0
        
        for line in lines2:
            if line.strip():
                parts = line.split('\t')
                if len(parts) >= 4:
                    shop = {
                        'bitrix_id': int(parts[0]) if parts[0].isdigit() else 0,
                        'name': parts[1],
                        'original_slug': parts[2] if parts[2] else None,
                        'ACTIVE': parts[3],
                        'product_count': 0
                    }
                    base_slug = shop['original_slug'] or re.sub(r'[^a-z0-9-]', '-', shop['name'].lower())
                    shop['unique_slug'] = f"{base_slug}-bid{shop['bitrix_id']}"
                    shops.append(shop)
                    count_without_products += 1
        
        print(f"✅ Добавлено {count_without_products} магазинов без товаров")
    
    print(f"\n📊 Всего загружено: {len(shops)} активных магазинов")
    
    return shops

def clear_test_shops(supabase):
    """Удалить тестовые магазины"""
    print_section("Очистка тестовых данных")
    
    try:
        result = supabase.table('sellers').select('id, name').execute()
        
        if result.data:
            emoji_chars = ['🌸', '🌺', '🌻', '🌷', '🌹', '💐', '🏪', '🎁', '🌼', '🌵']
            test_sellers = [
                s for s in result.data 
                if any(char in s['name'] for char in emoji_chars)
            ]
            
            if test_sellers:
                print(f"Найдено {len(test_sellers)} тестовых магазинов")
                
                for seller in test_sellers[:5]:
                    try:
                        # Обнуляем связи
                        supabase.table('products')\
                            .update({'seller_id': None, 'seller_name': None})\
                            .eq('seller_id', seller['id'])\
                            .execute()
                        
                        # Удаляем магазин
                        supabase.table('sellers')\
                            .delete()\
                            .eq('id', seller['id'])\
                            .execute()
                        
                        print(f"  ❌ Удален: {seller['name']}")
                    except Exception as e:
                        print(f"  ⚠️  Ошибка: {e}")
                
                if len(test_sellers) > 5:
                    # Удаляем остальные пакетом
                    for seller in test_sellers[5:]:
                        try:
                            supabase.table('sellers').delete().eq('id', seller['id']).execute()
                        except:
                            pass
                    print(f"  ... и еще {len(test_sellers) - 5} магазинов")
                
                print(f"✅ Удалено {len(test_sellers)} тестовых магазинов")
            else:
                print("✅ Тестовые магазины не найдены")
        
        return True
    except Exception as e:
        print(f"⚠️  Ошибка при очистке: {e}")
        return False

def extract_bitrix_id_from_slug(slug):
    """Извлечь bitrix_id из slug формата name-bidXXX"""
    if slug and '-bid' in slug:
        match = re.search(r'-bid(\d+)$', slug)
        if match:
            return int(match.group(1))
    return None

def sync_shops_to_supabase(mysql_shops):
    """Синхронизировать магазины в Supabase"""
    print_section("Синхронизация с Supabase")
    
    if not mysql_shops:
        print("❌ Нет магазинов для синхронизации")
        return False
    
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Очищаем тестовые данные
        clear_test_shops(supabase)
        
        # Получаем существующие магазины
        existing_result = supabase.table('sellers').select('id, name, slug').execute()
        
        # Создаем словарь по bitrix_id из slug
        existing_shops = {}
        if existing_result.data:
            for shop in existing_result.data:
                bitrix_id = extract_bitrix_id_from_slug(shop.get('slug'))
                if bitrix_id:
                    existing_shops[str(bitrix_id)] = shop
        
        print(f"Найдено существующих: {len(existing_shops)} магазинов")
        
        created_count = 0
        updated_count = 0
        error_count = 0
        
        print(f"\nСинхронизируем {len(mysql_shops)} магазинов...")
        
        for shop in mysql_shops:
            try:
                bitrix_id = str(shop['bitrix_id'])
                
                # Данные для Supabase
                shop_data = {
                    'name': shop['name'],
                    'slug': shop['unique_slug'],  # Содержит bitrix_id
                    'description': f"Bitrix ID: {shop['bitrix_id']}, Товаров: {shop['product_count']}",
                    'is_active': shop['ACTIVE'] == 'Y'
                }
                
                if bitrix_id in existing_shops:
                    # Обновляем
                    result = supabase.table('sellers')\
                        .update(shop_data)\
                        .eq('id', existing_shops[bitrix_id]['id'])\
                        .execute()
                    
                    if result.data:
                        updated_count += 1
                        if updated_count <= 3:
                            print(f"  ✅ Обновлен: {shop['name']}")
                else:
                    # Создаем новый
                    result = supabase.table('sellers')\
                        .insert(shop_data)\
                        .execute()
                    
                    if result.data:
                        created_count += 1
                        if created_count <= 5:
                            print(f"  ✅ Создан: {shop['name']} ({shop['product_count']} товаров)")
                
            except Exception as e:
                error_count += 1
                if error_count <= 3:
                    print(f"  ❌ Ошибка для {shop['name']}: {e}")
        
        print_section("РЕЗУЛЬТАТЫ СИНХРОНИЗАЦИИ")
        print(f"📊 Всего магазинов: {len(mysql_shops)}")
        print(f"✅ Создано новых: {created_count}")
        print(f"🔄 Обновлено: {updated_count}")
        print(f"❌ Ошибки: {error_count}")
        
        # Сохраняем лог
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'total': len(mysql_shops),
            'created': created_count,
            'updated': updated_count,
            'errors': error_count,
            'top_shops': [
                {
                    'name': s['name'],
                    'bitrix_id': s['bitrix_id'],
                    'product_count': s['product_count']
                }
                for s in sorted(mysql_shops, key=lambda x: x['product_count'], reverse=True)[:20]
            ]
        }
        
        with open(f"sync_shops_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", 'w', encoding='utf-8') as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)
        
        return True
        
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        return False

def verify_sync():
    """Проверить результаты"""
    print_section("Проверка результатов")
    
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Получаем магазины
        result = supabase.table('sellers')\
            .select('id, name, slug, is_active')\
            .order('name')\
            .limit(200)\
            .execute()
        
        if result.data:
            active = [s for s in result.data if s.get('is_active')]
            
            print(f"📊 В Supabase:")
            print(f"  ✅ Активных: {len(active)}")
            print(f"  📦 Всего: {len(result.data)}")
            
            # Показываем примеры с bitrix_id
            print("\n📊 Примеры магазинов:")
            for i, shop in enumerate(result.data[:10], 1):
                bitrix_id = extract_bitrix_id_from_slug(shop.get('slug'))
                status = "✅" if shop.get('is_active') else "❌"
                print(f"  {i}. {shop['name']} (Bitrix ID: {bitrix_id}) {status}")
            
            # Проверяем топовые магазины
            known_shops = ['Cvetykz', 'FLOVER', 'Оранж', 'Eileen flowers', 'ArtDi Flowers']
            print("\n📊 Проверка известных магазинов:")
            for shop_name in known_shops:
                found = any(shop_name.lower() in s['name'].lower() for s in result.data)
                if found:
                    print(f"  ✅ {shop_name} - найден")
                else:
                    print(f"  ❌ {shop_name} - не найден")
        else:
            print("❌ Магазины не найдены")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")

def main():
    """Основная функция"""
    print("\n" + "🔄 " * 20)
    print("  УПРОЩЕННАЯ СИНХРОНИЗАЦИЯ МАГАЗИНОВ")
    print("  MySQL → Supabase (без metadata)")
    print("🔄 " * 20)
    
    # Проверка SSH
    print_section("Проверка подключений")
    test_result = execute_mysql_query("SELECT VERSION()")
    if test_result:
        print(f"✅ SSH/MySQL: {test_result}")
    else:
        print("❌ Не удается подключиться")
        return
    
    # Проверка Supabase
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Переменные окружения не найдены")
        return
    print("✅ Supabase настроен")
    
    # Получаем магазины
    mysql_shops = get_top_shops_from_mysql()
    
    if mysql_shops:
        print(f"\n⚠️  Будет синхронизировано {len(mysql_shops)} магазинов")
        print("Это заменит тестовые данные реальными!")
        response = input("Продолжить? (yes/no): ")
        
        if response.lower() in ['yes', 'y', 'да']:
            if sync_shops_to_supabase(mysql_shops):
                verify_sync()
                print("\n✅ Синхронизация завершена!")
            else:
                print("\n⚠️  Синхронизация завершена с ошибками")
        else:
            print("\n❌ Отменено")
    else:
        print("\n❌ Не удалось получить магазины")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    main()