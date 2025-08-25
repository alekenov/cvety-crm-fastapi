#!/usr/bin/env python3
"""
Скрипт для синхронизации магазинов из продакшн MySQL в Supabase через SSH
Использует SSH для безопасного доступа к продакшн базе данных
"""

import subprocess
import json
from supabase import create_client
import os
from dotenv import load_dotenv
from datetime import datetime
import sys

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
SHOPS_IBLOCK_ID = 32  # ID инфоблока магазинов
SELLER_PROPERTY_ID = 290  # ID свойства "Продавец" для товаров

def print_section(title: str):
    """Печать заголовка секции"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

def execute_mysql_query(query):
    """Выполнить MySQL запрос через SSH"""
    # Добавляем export LANG=C чтобы избежать проблем с locale
    # Используем двойные кавычки для SSH команды чтобы избежать проблем с экранированием
    cmd = f'ssh {SSH_HOST} "export LANG=C; mysql -u {MYSQL_USER} -p\'{MYSQL_PASS}\' {MYSQL_DB} -N -e \\"{query}\\" 2>&1 | grep -v \\"warning: setlocale\\" | grep -v \\"Warning] Using a password\\""'
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            # Попробуем альтернативный вариант без фильтрации
            cmd_alt = f'ssh {SSH_HOST} \'export LANG=C; mysql -u {MYSQL_USER} -p"{MYSQL_PASS}" {MYSQL_DB} -N -e "{query}"\''
            result_alt = subprocess.run(cmd_alt, shell=True, capture_output=True, text=True, timeout=30)
            if result_alt.returncode == 0:
                # Фильтруем предупреждения из вывода
                lines = result_alt.stdout.strip().split('\n')
                filtered_lines = [
                    line for line in lines 
                    if not ('warning: setlocale' in line or 'Warning] Using a password' in line)
                ]
                return '\n'.join(filtered_lines)
            else:
                print(f"Ошибка выполнения запроса")
                return None
    except subprocess.TimeoutExpired:
        print("Таймаут при выполнении запроса")
        return None
    except Exception as e:
        print(f"Ошибка: {e}")
        return None

def get_shops_from_mysql_via_ssh(active_only=True):
    """Получить магазины из продакшн MySQL через SSH"""
    print_section(f"Получение {'активных' if active_only else 'всех'} магазинов через SSH")
    
    # Формируем запрос - упрощенная версия
    active_filter = "AND ACTIVE = 'Y'" if active_only else ""
    query = f"SELECT ID, NAME, IFNULL(CODE, ''), ACTIVE, IFNULL(SORT, 500) FROM b_iblock_element WHERE IBLOCK_ID = {SHOPS_IBLOCK_ID} {active_filter} ORDER BY SORT, NAME"
    
    print("Загружаем магазины из продакшн базы...")
    result = execute_mysql_query(query)
    
    if not result:
        print("❌ Не удалось получить данные")
        return []
    
    # Парсим результаты
    shops = []
    lines = result.split('\n')
    
    for line in lines:
        if line.strip():
            parts = line.split('\t')
            if len(parts) >= 5:
                shop = {
                    'bitrix_id': int(parts[0]) if parts[0].isdigit() else 0,
                    'name': parts[1],
                    'slug': parts[2] if parts[2] else None,
                    'ACTIVE': parts[3],
                    'sort_order': int(parts[4]) if parts[4].isdigit() else 500,
                    'description': None,
                    'DATE_CREATE': None,
                    'TIMESTAMP_X': None,
                    'product_count': 0
                }
                shops.append(shop)
    
    print(f"✅ Найдено {len(shops)} магазинов")
    
    # Получаем количество товаров для топ-10 магазинов
    print("\nПолучаем статистику по товарам для топ магазинов...")
    
    # Сначала сортируем по ID для получения основных магазинов
    top_shops = sorted(shops[:30], key=lambda x: x['bitrix_id'])
    
    for shop in top_shops:
        count_query = f"""
        SELECT COUNT(DISTINCT ep.IBLOCK_ELEMENT_ID)
        FROM b_iblock_element_property ep
        WHERE ep.IBLOCK_PROPERTY_ID = {SELLER_PROPERTY_ID}
        AND ep.VALUE = {shop['bitrix_id']}
        """.replace('\n', ' ')
        
        count_result = execute_mysql_query(count_query)
        shop['product_count'] = int(count_result) if count_result and count_result.isdigit() else 0
    
    # Для остальных магазинов ставим 0
    for shop in shops[30:]:
        shop['product_count'] = 0
    
    # Показываем топ-10 по количеству товаров
    shops_with_products = [s for s in shops if s.get('product_count', 0) > 0]
    shops_with_products.sort(key=lambda x: x['product_count'], reverse=True)
    
    if shops_with_products:
        print("\n📊 Топ-10 магазинов по количеству товаров:")
        for i, shop in enumerate(shops_with_products[:10], 1):
            status = "✅" if shop['ACTIVE'] == 'Y' else "❌"
            print(f"  {i}. {shop['name']} (ID: {shop['bitrix_id']}, Товаров: {shop['product_count']}) {status}")
    
    return shops

def clear_test_shops(supabase):
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
                
                if deleted_count > 5:
                    print(f"  ... и еще {deleted_count - 5} магазинов")
                
                print(f"✅ Удалено {deleted_count} тестовых магазинов")
            else:
                print("✅ Тестовые магазины не найдены")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при очистке: {e}")
        return False

def sync_shops_to_supabase(mysql_shops):
    """Синхронизировать магазины в Supabase"""
    print_section("Синхронизация с Supabase")
    
    if not mysql_shops:
        print("❌ Нет магазинов для синхронизации")
        return False
    
    try:
        # Инициализация Supabase клиента
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Очищаем тестовые данные
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
        error_count = 0
        
        print(f"\nНачинаем синхронизацию {len(mysql_shops)} магазинов...")
        print(f"Уже существует в Supabase: {len(existing_shops)} магазинов")
        
        # Обрабатываем магазины
        for shop in mysql_shops:
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
                        'product_count': shop.get('product_count', 0),
                        'sort_order': shop.get('sort_order', 500),
                        'synced_at': datetime.now().isoformat()
                    }
                }
                
                if bitrix_id in existing_shops:
                    # Обновляем существующий магазин
                    result = supabase.table('sellers')\
                        .update(shop_data)\
                        .eq('id', existing_shops[bitrix_id]['id'])\
                        .execute()
                    
                    if result.data:
                        updated_count += 1
                        if updated_count <= 5:
                            print(f"  ✅ Обновлен: {shop['name']}")
                else:
                    # Создаем новый магазин
                    result = supabase.table('sellers')\
                        .insert(shop_data)\
                        .execute()
                    
                    if result.data:
                        created_count += 1
                        if created_count <= 5:
                            print(f"  ✅ Создан: {shop['name']} (ID: {result.data[0]['id']})")
                
            except Exception as e:
                error_count += 1
                if error_count <= 3:
                    print(f"  ❌ Ошибка для {shop['name']}: {e}")
        
        # Итоговая статистика
        print_section("РЕЗУЛЬТАТЫ СИНХРОНИЗАЦИИ")
        print(f"📊 Всего магазинов в MySQL: {len(mysql_shops)}")
        print(f"✅ Создано новых: {created_count}")
        print(f"🔄 Обновлено существующих: {updated_count}")
        print(f"❌ Ошибки: {error_count}")
        
        # Сохраняем лог
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'total_mysql': len(mysql_shops),
            'created': created_count,
            'updated': updated_count,
            'errors': error_count,
            'top_shops': [
                {
                    'name': s['name'],
                    'bitrix_id': s['bitrix_id'],
                    'product_count': s.get('product_count', 0),
                    'active': s['ACTIVE'] == 'Y'
                }
                for s in sorted(mysql_shops, key=lambda x: x.get('product_count', 0), reverse=True)
                if s.get('product_count', 0) > 0
            ][:20]
        }
        
        log_file = f"sync_shops_ssh_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
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
            
            # Показываем первые 10 магазинов
            print("\n📊 Первые 10 магазинов в Supabase:")
            for i, shop in enumerate(all_shops.data[:10], 1):
                status = "✅" if shop.get('is_active') else "❌"
                bitrix_id = shop.get('metadata', {}).get('bitrix_id', '-')
                print(f"  {i}. {shop['name']} (Bitrix ID: {bitrix_id}) {status}")
        else:
            print("❌ Магазины не найдены в Supabase")
        
    except Exception as e:
        print(f"❌ Ошибка при проверке: {e}")

def main():
    """Основная функция"""
    print("\n" + "🔄 " * 20)
    print("  СИНХРОНИЗАЦИЯ МАГАЗИНОВ ЧЕРЕЗ SSH")
    print("  MySQL (Bitrix Production) → Supabase")
    print("🔄 " * 20)
    
    # Проверка SSH подключения
    print_section("Проверка SSH подключения")
    test_result = execute_mysql_query("SELECT VERSION()")
    if test_result:
        print(f"✅ SSH подключение работает. MySQL версия: {test_result}")
    else:
        print("❌ Не удается подключиться через SSH")
        return
    
    # Проверка Supabase
    print_section("Проверка подключения к Supabase")
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Не найдены переменные окружения SUPABASE_URL или SUPABASE_KEY")
        return
    print("✅ Переменные окружения найдены")
    
    # Получаем магазины
    print("\n⏳ Получение магазинов из продакшн базы (это может занять минуту)...")
    mysql_shops = get_shops_from_mysql_via_ssh(active_only=True)
    
    if mysql_shops:
        # Запрашиваем подтверждение
        print(f"\n⚠️  Будет синхронизировано {len(mysql_shops)} активных магазинов")
        print("Это удалит тестовые магазины и заменит их реальными данными!")
        response = input("Продолжить? (yes/no): ")
        
        if response.lower() in ['yes', 'y', 'да']:
            # Выполняем синхронизацию
            success = sync_shops_to_supabase(mysql_shops)
            
            if success:
                # Проверяем результаты
                verify_sync()
                print("\n✅ Синхронизация завершена успешно!")
                print("\n💡 Следующий шаг: запустите update_product_shop_links.py")
            else:
                print("\n⚠️  Синхронизация завершена с ошибками")
        else:
            print("\n❌ Синхронизация отменена")
    else:
        print("\n❌ Не удалось получить магазины из MySQL")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    main()