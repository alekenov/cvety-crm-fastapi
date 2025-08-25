#!/usr/bin/env python3
"""
Тест подключений к базам данных (локальные и продакшн)
"""

import os
import sys
from dotenv import load_dotenv

# Добавляем корневую директорию в путь для импорта cvety_connection
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

def test_mysql_local():
    """Тестирует подключение к локальному MySQL Docker"""
    try:
        import pymysql
        
        print("🟡 Тестирование локального MySQL подключения...")
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
        print("✅ Локальный MySQL подключение работает")
        print(f"   Найдено {count} заказов для тестирования")
        
        connection.close()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка локального MySQL: {e}")
        return False

def test_production():
    """Тестирует все продакшн подключения"""
    try:
        from cvety_connection import CvetyConnection
        
        print("🟡 Тестирование ПРОДАКШН подключений...")
        print("   (SSH + MySQL + SFTP)")
        print()
        
        cvety = CvetyConnection()
        results = cvety.test_connections()
        
        print("Результаты тестов продакшна:")
        print(f"  SSH:   {'✅ Работает' if results['ssh'] else '❌ Не работает'}")
        print(f"  MySQL: {'✅ Работает' if results['mysql'] else '❌ Не работает'}")
        print(f"  SFTP:  {'✅ Работает' if results['sftp'] else '❌ Не работает'}")
        
        # Дополнительный тест: получение реальных данных
        if results['mysql']:
            print("\n📊 Тест получения данных с продакшна:")
            try:
                # Получаем последние 3 заказа
                recent_orders = cvety.execute_query("""
                    SELECT ID, ACCOUNT_NUMBER, STATUS_ID, PRICE, DATE_INSERT 
                    FROM b_sale_order 
                    ORDER BY ID DESC 
                    LIMIT 3
                """)
                
                if recent_orders:
                    print(f"   Последние заказы ({len(recent_orders)} шт.):")
                    for order in recent_orders:
                        order_id, number, status, price, date = order
                        print(f"   • #{order_id} ({number}) - {price}₸ - {status} - {date}")
                else:
                    print("   Заказы не найдены")
                    
            except Exception as e:
                print(f"   ❌ Ошибка получения данных: {e}")
                results['mysql'] = False
        
        return all(results.values())
        
    except ImportError:
        print("❌ cvety_connection не найден. Убедитесь что файл создан.")
        return False
    except Exception as e:
        print(f"❌ Ошибка тестирования продакшна: {e}")
        return False

def test_production_quick():
    """Быстрый тест продакшн подключения с примером использования"""
    try:
        from cvety_connection import get_production_orders
        
        print("🚀 Быстрый тест: получение заказов за сегодня...")
        
        # Получаем заказы за последние 7 дней
        from datetime import datetime, timedelta
        
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        orders = get_production_orders(start_date, end_date)
        
        print(f"✅ Найдено {len(orders)} заказов за последние 7 дней")
        if orders:
            print("   Примеры заказов:")
            for order in orders[:3]:
                order_id, number, status, price, user_id, date = order
                print(f"   • #{order_id} ({number}) - {price}₸ - {status}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка быстрого теста: {e}")
        return False

if __name__ == "__main__":
    print("🔌 КОМПЛЕКСНОЕ ТЕСТИРОВАНИЕ ПОДКЛЮЧЕНИЙ")
    print("=" * 50)
    print()
    
    # Тестируем локальные подключения
    print("1️⃣ ЛОКАЛЬНЫЕ ПОДКЛЮЧЕНИЯ:")
    mysql_ok = test_mysql_local()
    print()
    supabase_ok = test_supabase()
    print()
    
    # Тестируем продакшн подключения
    print("2️⃣ ПРОДАКШН ПОДКЛЮЧЕНИЯ:")
    production_ok = test_production()
    print()
    
    # Быстрый тест удобных функций
    print("3️⃣ ТЕСТ УДОБНЫХ ФУНКЦИЙ:")
    quick_ok = test_production_quick()
    print()
    
    # Итоговый результат
    print("=" * 50)
    if mysql_ok and supabase_ok and production_ok and quick_ok:
        print("🎯 ВСЕ ПОДКЛЮЧЕНИЯ РАБОТАЮТ ОТЛИЧНО!")
        print("\n💡 Теперь можно использовать:")
        print("   from cvety_connection import CvetyConnection")
        print("   cvety = CvetyConnection()")
        print("   orders = cvety.execute_query('SELECT * FROM b_sale_order LIMIT 10')")
    else:
        print("⚠️  Есть проблемы с подключениями:")
        if not mysql_ok:
            print("   • Локальный MySQL не работает")
        if not supabase_ok:
            print("   • Supabase не работает") 
        if not production_ok:
            print("   • Продакшн подключения не работают")
        if not quick_ok:
            print("   • Быстрые функции не работают")