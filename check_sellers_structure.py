#!/usr/bin/env python3
"""
Проверка и обновление структуры таблицы sellers
"""

from supabase import create_client
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")

def check_and_update_sellers_table():
    """Проверить и обновить структуру таблицы sellers"""
    
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Пробуем получить данные с metadata
        print("Проверяем структуру таблицы sellers...")
        
        try:
            # Пробуем запрос с metadata
            result = supabase.table('sellers').select('id, name, metadata').limit(1).execute()
            print("✅ Колонка metadata существует")
            return True
        except Exception as e:
            if 'metadata does not exist' in str(e):
                print("❌ Колонка metadata не найдена")
                print("Добавляем колонку metadata...")
                
                # Добавляем колонку через RPC или raw SQL
                # Для Supabase нужно использовать миграцию или Dashboard
                print("\n⚠️  Необходимо добавить колонку metadata в таблицу sellers")
                print("Выполните следующий SQL запрос в Supabase Dashboard:")
                print("-" * 60)
                print("ALTER TABLE sellers ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;")
                print("-" * 60)
                
                return False
            else:
                print(f"Ошибка при проверке: {e}")
                return False
                
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        return False

def test_sellers_operations():
    """Протестировать операции с таблицей sellers"""
    
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        print("\nТестирование операций с таблицей sellers...")
        
        # Получаем первых 5 продавцов
        result = supabase.table('sellers').select('*').limit(5).execute()
        
        if result.data:
            print(f"✅ Найдено {len(result.data)} продавцов")
            print("\nПримеры продавцов:")
            for seller in result.data:
                print(f"  - ID: {seller['id']}, Название: {seller['name']}")
                
            # Проверяем какие колонки есть
            if result.data[0]:
                print(f"\nДоступные колонки: {', '.join(result.data[0].keys())}")
        else:
            print("❌ Продавцы не найдены")
            
    except Exception as e:
        print(f"❌ Ошибка при тестировании: {e}")

if __name__ == "__main__":
    print("="*60)
    print("  ПРОВЕРКА СТРУКТУРЫ ТАБЛИЦЫ SELLERS")
    print("="*60)
    
    if check_and_update_sellers_table():
        test_sellers_operations()
    else:
        print("\n❗ Сначала добавьте колонку metadata в таблицу sellers")
        print("   Затем запустите синхронизацию снова")
    
    print("\n" + "="*60)