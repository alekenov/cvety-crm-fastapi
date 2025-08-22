#!/usr/bin/env python3
"""
Полный интеграционный тест системы синхронизации
"""

import asyncio
import requests
import json
import time
from datetime import datetime
from sync.sync_manager import SyncManager

async def test_full_cycle():
    """Тестирует полный цикл: webhook → transform → save → check"""
    
    print("🚀 ПОЛНЫЙ ИНТЕГРАЦИОННЫЙ ТЕСТ")
    print("=" * 60)
    
    # 1. Создаем уникальный тестовый заказ
    test_order_id = int(time.time()) % 1000000  # Уникальный ID
    
    webhook_payload = {
        "token": "fad5fbe4c8a520cf6d5453685b758c7fd9f6681f084be335fcdcd190ad9aaa0e",
        "event": "order.create",
        "data": {
            "ID": test_order_id,
            "STATUS_ID": "N",
            "DATE_INSERT": "22.08.2025 16:30:00",
            "PRICE": "7500.00",
            "USER_ID": 1079,
            "PHONE": "+77777777777",
            "EMAIL": "integration@test.com",
            "DELIVERY_ADDRESS": "г. Алматы, ул. Тестовая 1",
            "COMMENT": f"Интеграционный тест {test_order_id}",
            "PAYMENT_ID": "kaspi",
            "PAYMENT_STATUS": "Y"
        }
    }
    
    print(f"📝 Шаг 1: Создаем тестовый заказ ID {test_order_id}")
    
    # 2. Отправляем webhook
    try:
        response = requests.post(
            "http://localhost:8001/webhooks/bitrix/order",
            json=webhook_payload,
            timeout=15
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Webhook принят: {result.get('status', 'unknown')}")
            supabase_order_id = result.get('order_id')
            print(f"   Supabase Order ID: {supabase_order_id}")
        else:
            print(f"❌ Ошибка webhook: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка отправки webhook: {e}")
        return False
    
    # 3. Проверяем что заказ появился в Supabase
    print(f"\n📊 Шаг 2: Проверяем заказ в Supabase...")
    
    try:
        from supabase import create_client
        from config import config
        
        supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        
        # Ищем заказ по bitrix_order_id
        result = supabase.table('orders').select('*').eq('bitrix_order_id', test_order_id).execute()
        
        if result.data:
            order = result.data[0]
            print(f"✅ Заказ найден в Supabase!")
            print(f"   ID: {order.get('id')}")
            print(f"   Статус: {order.get('status')}")
            print(f"   Сумма: {order.get('total_amount')}")
            print(f"   Создан: {order.get('created_at')}")
            return True
        else:
            print(f"❌ Заказ не найден в Supabase")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка проверки Supabase: {e}")
        return False

async def test_sync_performance():
    """Тестирует производительность синхронизации"""
    
    print(f"\n⚡ ТЕСТ ПРОИЗВОДИТЕЛЬНОСТИ")
    print("=" * 60)
    
    manager = SyncManager()
    
    # Тестируем синхронизацию 10 заказов
    test_ids = [122100 + i for i in range(10)]
    
    print(f"📊 Синхронизируем {len(test_ids)} заказов...")
    start_time = time.time()
    
    try:
        results = await manager.sync_by_ids(test_ids, source='local')
        duration = time.time() - start_time
        
        print(f"\n📈 РЕЗУЛЬТАТЫ ПРОИЗВОДИТЕЛЬНОСТИ:")
        print(f"   Время выполнения: {duration:.2f} секунд")
        print(f"   Скорость: {len(test_ids)/duration:.2f} заказов/сек")
        print(f"   Успешно: {results.get('success', 0)}")
        print(f"   Ошибок: {results.get('failed', 0)}")
        print(f"   Пропущено: {results.get('skipped', 0)}")
        
        if duration < 30:  # Должно быть быстрее 30 секунд
            print("✅ Производительность приемлемая")
            return True
        else:
            print("⚠️  Медленная производительность")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка теста производительности: {e}")
        return False

async def test_reverse_sync():
    """Тестирует обратную синхронизацию"""
    
    print(f"\n🔄 ТЕСТ ОБРАТНОЙ СИНХРОНИЗАЦИИ")
    print("=" * 60)
    
    try:
        from sync.reverse_sync import UnifiedReverseSync
        
        reverse = UnifiedReverseSync()
        
        # Получаем изменения за последний час
        updates = reverse.get_pending_updates()
        print(f"📊 Найдено {len(updates)} изменений для отправки в Bitrix")
        
        if updates:
            # Синхронизируем первые 3
            results = reverse.sync_batch_updates(max_orders=3)
            print(f"✅ Синхронизировано: {results}")
            return True
        else:
            print("ℹ️  Нет изменений для синхронизации (это нормально)")
            return True
            
    except Exception as e:
        print(f"❌ Ошибка обратной синхронизации: {e}")
        return False

async def main():
    """Главная функция интеграционного теста"""
    
    print("🎯 ЗАПУСК ПОЛНОГО ИНТЕГРАЦИОННОГО ТЕСТИРОВАНИЯ")
    print("=" * 60)
    
    tests_passed = 0
    total_tests = 3
    
    # Тест 1: Полный цикл
    if await test_full_cycle():
        tests_passed += 1
        
    # Тест 2: Производительность
    if await test_sync_performance():
        tests_passed += 1
        
    # Тест 3: Обратная синхронизация
    if await test_reverse_sync():
        tests_passed += 1
    
    print("\n" + "=" * 60)
    print(f"🎯 ИТОГИ ИНТЕГРАЦИОННОГО ТЕСТИРОВАНИЯ:")
    print(f"   Пройдено тестов: {tests_passed}/{total_tests}")
    print(f"   Успешность: {tests_passed/total_tests*100:.1f}%")
    
    if tests_passed == total_tests:
        print("🎉 ВСЕ ИНТЕГРАЦИОННЫЕ ТЕСТЫ ПРОЙДЕНЫ!")
        print("   Система готова к production использованию")
    else:
        print("⚠️  НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОЙДЕНЫ")
        print("   Требуется дополнительная настройка")

if __name__ == "__main__":
    asyncio.run(main())