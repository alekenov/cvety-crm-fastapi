#!/usr/bin/env python3
"""
Тест подключений к базам данных
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

def test_supabase():
    """Тестирует подключение к Supabase"""
    try:
        from supabase import create_client
        
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")
        
        if not url or not key:
            print("❌ Supabase credentials не найдены в .env")
            return False
            
        print("🟡 Тестирование Supabase подключения...")
        supabase = create_client(url, key)
        
        # Простой запрос
        result = supabase.table('orders').select('id').limit(1).execute()
        print("✅ Supabase подключение работает")
        print(f"   Таблица orders доступна")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка Supabase: {e}")
        return False

def test_mysql():
    """Тестирует подключение к MySQL"""
    try:
        import pymysql
        
        print("🟡 Тестирование MySQL подключения...")
        connection = pymysql.connect(
            host=os.getenv("MYSQL_HOST", "localhost"),
            port=int(os.getenv("MYSQL_PORT", "3306")),
            user=os.getenv("MYSQL_USER", "root"),
            password=os.getenv("MYSQL_PASSWORD", "cvety123"),
            database=os.getenv("MYSQL_DATABASE", "cvety_db"),
            charset='utf8mb4'
        )
        
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM b_sale_order WHERE ID > 122000")
        count = cursor.fetchone()[0]
        print("✅ MySQL подключение работает")
        print(f"   Найдено {count} заказов для тестирования")
        
        connection.close()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка MySQL: {e}")
        return False

if __name__ == "__main__":
    print("🔌 ФАЗА 3: Тестирование подключений...")
    print()
    
    mysql_ok = test_mysql()
    print()
    supabase_ok = test_supabase()
    print()
    
    if mysql_ok and supabase_ok:
        print("🎯 ВСЕ ПОДКЛЮЧЕНИЯ РАБОТАЮТ!")
    else:
        print("⚠️  Есть проблемы с подключениями")