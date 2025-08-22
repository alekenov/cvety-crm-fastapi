#!/usr/bin/env python3
"""
Тест синхронизации заказов
"""

import asyncio
from sync.sync_manager import SyncManager

async def test_single_sync():
    """Тестирует синхронизацию одного заказа"""
    
    print("🔄 ФАЗА 5: Тестирование синхронизации...")
    print()
    print("🟡 Тест синхронизации одного заказа...")
    
    try:
        manager = SyncManager()
        
        # Выбираем заказ 122118 для теста
        test_order_id = 122118
        print(f"   Синхронизируем заказ {test_order_id}...")
        
        result = await manager.sync_single_order(test_order_id, source='local')
        
        if result:
            print(f"   ✅ Заказ {test_order_id} синхронизирован успешно")
            return True
        else:
            print(f"   ❌ Ошибка синхронизации заказа {test_order_id}")
            return False
            
    except Exception as e:
        print(f"   ❌ Исключение при синхронизации: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_batch_sync():
    """Тестирует пакетную синхронизацию"""
    
    print()
    print("🟡 Тест пакетной синхронизации (5 заказов)...")
    
    try:
        manager = SyncManager()
        
        # Синхронизируем 5 заказов: 122100-122105
        start_id = 122100
        end_id = 122105
        print(f"   Синхронизируем заказы с {start_id} по {end_id}...")
        
        results = await manager.sync_by_range(start_id, end_id, max_orders=5)
        
        print(f"   📊 Результаты пакетной синхронизации:")
        print(f"      ✅ Успешно: {results.get('success', 0)}")
        print(f"      ❌ Ошибок: {results.get('failed', 0)}")
        print(f"      ⏩ Пропущено: {results.get('skipped', 0)}")
        print(f"      📋 Всего обработано: {results.get('total', 0)}")
        
        if results.get('success', 0) > 0:
            print(f"   ✅ Пакетная синхронизация прошла успешно")
            return True
        else:
            print(f"   ❌ Пакетная синхронизация не дала результатов")
            return False
            
    except Exception as e:
        print(f"   ❌ Исключение при пакетной синхронизации: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_sync_by_ids():
    """Тестирует синхронизацию по конкретным ID"""
    
    print()
    print("🟡 Тест синхронизации по конкретным ID...")
    
    try:
        manager = SyncManager()
        
        # Список конкретных ID для синхронизации
        order_ids = [122110, 122111, 122112]
        print(f"   Синхронизируем заказы: {order_ids}...")
        
        results = await manager.sync_by_ids(order_ids, source='local')
        
        print(f"   📊 Результаты синхронизации по ID:")
        print(f"      ✅ Успешно: {results.get('success', 0)}")
        print(f"      ❌ Ошибок: {results.get('failed', 0)}")
        print(f"      ⏩ Пропущено: {results.get('skipped', 0)}")
        
        if results.get('success', 0) > 0:
            print(f"   ✅ Синхронизация по ID прошла успешно")
            return True
        else:
            print(f"   ⚠️  Синхронизация по ID не дала результатов")
            return False
            
    except Exception as e:
        print(f"   ❌ Исключение при синхронизации по ID: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Главная функция тестирования"""
    
    print("🚀 ЗАПУСК ТЕСТОВ СИНХРОНИЗАЦИИ")
    print("=" * 50)
    
    # Тесты
    test1 = await test_single_sync()
    test2 = await test_batch_sync() 
    test3 = await test_sync_by_ids()
    
    print()
    print("=" * 50)
    if test1 and test2 and test3:
        print("🎯 ВСЕ ТЕСТЫ СИНХРОНИЗАЦИИ ПРОШЛИ УСПЕШНО!")
        print("   Система готова к производственному использованию")
    else:
        print("⚠️  НЕКОТОРЫЕ ТЕСТЫ СИНХРОНИЗАЦИИ НЕ ПРОШЛИ")
        print("   Требуется дополнительная настройка")

if __name__ == "__main__":
    asyncio.run(main())