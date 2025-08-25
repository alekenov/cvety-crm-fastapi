#!/usr/bin/env python3
"""
Скрипт для синхронизации неактивных товаров из MySQL Bitrix в Supabase
Находит все товары с ACTIVE='N' в MySQL и обновляет is_active=false в Supabase
"""

import mysql.connector
from supabase import create_client
import os
from dotenv import load_dotenv
from datetime import datetime
import json

# Загружаем переменные окружения
load_dotenv()

# Конфигурация MySQL (локальный Docker)
MYSQL_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'cvety123',
    'database': 'cvety_db'
}

# Конфигурация Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")

def print_section(title: str):
    """Печать заголовка секции"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

def get_inactive_products_from_mysql():
    """Получить все неактивные товары из MySQL"""
    print_section("Получение неактивных товаров из MySQL")
    
    try:
        # Подключение к MySQL
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        cursor = conn.cursor(dictionary=True)
        
        # Запрос для получения неактивных товаров
        query = """
        SELECT 
            e.ID as bitrix_id,
            e.NAME as name,
            e.ACTIVE,
            e.IBLOCK_ID,
            e.TIMESTAMP_X,
            e.DATE_CREATE
        FROM b_iblock_element e
        WHERE e.ACTIVE = 'N'
        AND e.IBLOCK_ID IN (
            SELECT ID FROM b_iblock 
            WHERE IBLOCK_TYPE_ID = 'catalog' 
            OR CODE = 'products'
        )
        ORDER BY e.ID
        """
        
        cursor.execute(query)
        inactive_products = cursor.fetchall()
        
        print(f"✅ Найдено {len(inactive_products)} неактивных товаров в MySQL")
        
        # Показываем первые 5 для примера
        if inactive_products:
            print("\nПримеры неактивных товаров:")
            for i, product in enumerate(inactive_products[:5]):
                print(f"  {i+1}. ID: {product['bitrix_id']}, Название: {product['name']}")
            if len(inactive_products) > 5:
                print(f"  ... и еще {len(inactive_products) - 5} товаров")
        
        cursor.close()
        conn.close()
        
        return inactive_products
        
    except mysql.connector.Error as e:
        print(f"❌ Ошибка MySQL: {e}")
        return []

def sync_to_supabase(inactive_products):
    """Синхронизировать статусы в Supabase"""
    print_section("Синхронизация с Supabase")
    
    if not inactive_products:
        print("❌ Нет товаров для синхронизации")
        return
    
    try:
        # Инициализация Supabase клиента
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Счетчики
        updated_count = 0
        not_found_count = 0
        already_inactive_count = 0
        error_count = 0
        
        print(f"Начинаем синхронизацию {len(inactive_products)} товаров...")
        
        # Обрабатываем товары пакетами по 50
        batch_size = 50
        for i in range(0, len(inactive_products), batch_size):
            batch = inactive_products[i:i + batch_size]
            bitrix_ids = [str(p['bitrix_id']) for p in batch]
            
            try:
                # Получаем товары из Supabase по bitrix_id в metadata
                result = supabase.table('products')\
                    .select('id, name, is_active, metadata')\
                    .in_('metadata->>bitrix_id', bitrix_ids)\
                    .execute()
                
                if result.data:
                    # Создаем словарь для быстрого поиска
                    supabase_products = {
                        str(p['metadata'].get('bitrix_id')): p 
                        for p in result.data 
                        if p.get('metadata', {}).get('bitrix_id')
                    }
                    
                    # Обновляем найденные товары
                    for mysql_product in batch:
                        bitrix_id = str(mysql_product['bitrix_id'])
                        
                        if bitrix_id in supabase_products:
                            sp_product = supabase_products[bitrix_id]
                            
                            if sp_product['is_active']:
                                # Деактивируем товар
                                update_result = supabase.table('products')\
                                    .update({'is_active': False, 'updated_at': 'now()'})\
                                    .eq('id', sp_product['id'])\
                                    .execute()
                                
                                if update_result.data:
                                    updated_count += 1
                                    if updated_count <= 10:
                                        print(f"  ✅ Деактивирован: {sp_product['name']}")
                                else:
                                    error_count += 1
                            else:
                                already_inactive_count += 1
                        else:
                            not_found_count += 1
                else:
                    not_found_count += len(batch)
                
                # Показываем прогресс
                if (i + batch_size) % 200 == 0 or (i + batch_size) >= len(inactive_products):
                    print(f"  Обработано: {min(i + batch_size, len(inactive_products))}/{len(inactive_products)}")
                    
            except Exception as e:
                print(f"  ❌ Ошибка при обработке пакета: {e}")
                error_count += len(batch)
        
        # Итоговая статистика
        print_section("РЕЗУЛЬТАТЫ СИНХРОНИЗАЦИИ")
        print(f"📊 Всего неактивных в MySQL: {len(inactive_products)}")
        print(f"✅ Успешно деактивировано в Supabase: {updated_count}")
        print(f"⏭️  Уже были неактивны: {already_inactive_count}")
        print(f"❓ Не найдено в Supabase: {not_found_count}")
        print(f"❌ Ошибки при обновлении: {error_count}")
        
        # Сохраняем лог
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'total_inactive_mysql': len(inactive_products),
            'updated_count': updated_count,
            'already_inactive': already_inactive_count,
            'not_found': not_found_count,
            'errors': error_count
        }
        
        log_file = f"sync_inactive_products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        print(f"\n📄 Лог сохранен в: {log_file}")
        
        return updated_count > 0
        
    except Exception as e:
        print(f"❌ Критическая ошибка Supabase: {e}")
        return False

def verify_sync():
    """Проверить результаты синхронизации"""
    print_section("Проверка результатов")
    
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Подсчитываем активные и неактивные товары
        active_result = supabase.table('products')\
            .select('id', count='exact')\
            .eq('is_active', True)\
            .execute()
        
        inactive_result = supabase.table('products')\
            .select('id', count='exact')\
            .eq('is_active', False)\
            .execute()
        
        active_count = active_result.count if hasattr(active_result, 'count') else len(active_result.data)
        inactive_count = inactive_result.count if hasattr(inactive_result, 'count') else len(inactive_result.data)
        
        print(f"📊 Статистика Supabase после синхронизации:")
        print(f"  ✅ Активных товаров: {active_count}")
        print(f"  ❌ Неактивных товаров: {inactive_count}")
        print(f"  📦 Всего товаров: {active_count + inactive_count}")
        
    except Exception as e:
        print(f"❌ Ошибка при проверке: {e}")

def main():
    """Основная функция"""
    print("\n" + "🔄 " * 20)
    print("  СИНХРОНИЗАЦИЯ НЕАКТИВНЫХ ТОВАРОВ")
    print("  MySQL (Bitrix) → Supabase")
    print("🔄 " * 20)
    
    # Проверка подключения к MySQL
    print_section("Проверка подключения к MySQL")
    try:
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        conn.close()
        print("✅ Подключение к MySQL успешно")
    except mysql.connector.Error as e:
        print(f"❌ Не удается подключиться к MySQL: {e}")
        print("❗ Убедитесь, что Docker контейнер запущен:")
        print("   cd /Users/alekenov/cvety-local && docker-compose up -d")
        return
    
    # Получаем неактивные товары
    inactive_products = get_inactive_products_from_mysql()
    
    if inactive_products:
        # Запрашиваем подтверждение
        print(f"\n⚠️  Будет обновлено до {len(inactive_products)} товаров в Supabase")
        response = input("Продолжить? (yes/no): ")
        
        if response.lower() in ['yes', 'y', 'да']:
            # Выполняем синхронизацию
            success = sync_to_supabase(inactive_products)
            
            if success:
                # Проверяем результаты
                verify_sync()
                print("\n✅ Синхронизация завершена успешно!")
            else:
                print("\n⚠️  Синхронизация завершена с ошибками")
        else:
            print("\n❌ Синхронизация отменена")
    else:
        print("\n✅ Все товары уже синхронизированы")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    main()