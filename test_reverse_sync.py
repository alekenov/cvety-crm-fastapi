#!/usr/bin/env python3
"""
Тестирование обратной синхронизации Supabase → Bitrix
Создает тестовый заказ через webhook, который должен синхронизироваться с Bitrix
"""

import requests
import json
import time
from datetime import datetime

# Настройки для тестирования
WEBHOOK_URL = "http://localhost:8001/webhooks/bitrix/order"
WEBHOOK_TOKEN = "fad5fbe4c8a520cf6d5453685b758c7fd9f6681f084be335fcdcd190ad9aaa0e"

def test_reverse_synchronization():
    """
    Тестирует обратную синхронизацию:
    1. Создает заказ через webhook (не из продакшн Bitrix)
    2. Заказ должен создаться в Supabase
    3. Заказ должен автоматически синхронизироваться в Bitrix
    4. В Supabase должен появиться bitrix_order_id
    """
    print("🧪 ТЕСТИРОВАНИЕ ОБРАТНОЙ СИНХРОНИЗАЦИИ Supabase → Bitrix")
    print("=" * 60)
    
    # Создаем уникальные ID для тестового заказа
    timestamp = int(time.time())
    test_order_id = timestamp + 800000  # Смещение чтобы не конфликтовать с реальными ID
    test_user_id = timestamp
    
    # Создаем тестовый заказ (НЕ из продакшн Bitrix)
    test_payload = {
        "event": "order.create",
        "token": WEBHOOK_TOKEN,
        "data": {
            "ID": str(test_order_id),
            "ACCOUNT_NUMBER": str(test_order_id),
            "STATUS_ID": "N",
            "PRICE": "7200.0000",
            "PRICE_DELIVERY": "1800.0000",
            "DISCOUNT_VALUE": "0.0000",
            "USER_ID": str(test_user_id),
            "PAYED": "N",
            "DATE_INSERT": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "PAY_SYSTEM_ID": "10",
            "USER_DESCRIPTION": "Тестовый заказ для проверки обратной синхронизации",
            "COMMENTS": None,
            "properties": {
                # Данные заказчика
                "phone": "+77777777799",
                "email": "reverse_sync_test@example.com",
                # Данные получателя
                "nameRecipient": "Получатель Обратной Синхронизации",
                "phoneRecipient": "+77777777800",
                "addressRecipient": "Тестовый адрес обратной синхронизации, ул. Синхронизации, д. 1",
                # Детали заказа
                "data": "2025-08-23",
                "postcardText": "🔄 Тест обратной синхронизации! Заказ должен появиться в Bitrix CRM.",
                "city": "2",
                "when": "27",
                "iWillGet": "N",
                "pickup": "N",
                "SOURCE_ORDER": "reverse_sync_test",
                "shopId": "17008",
                "opt": "N"
            },
            "basket": [
                {
                    "ID": f"{test_order_id}1",
                    "PRODUCT_ID": "695515",  # Подсолнухи
                    "NAME": "Подсолнухи в пачке 5 шт (тест обратной синхронизации)",
                    "PRICE": "7200.0000",
                    "QUANTITY": "1.0000",
                    "CURRENCY": "KZT",
                    "DISCOUNT_PRICE": "0.0000",
                    "PRODUCT_XML_ID": None
                }
            ],
            "user": {
                "ID": str(test_user_id),
                "phone": "+77777777799",
                "email": "reverse_sync_test@example.com"
            },
            "webhook_source": "test_reverse_sync",  # НЕ production_real - должен триггерить обратную синхронизацию
            "webhook_timestamp": datetime.now().isoformat()
        }
    }
    
    print(f"📦 Создание тестового заказа для обратной синхронизации...")
    print(f"   Test Order ID: {test_order_id}")
    print(f"   Test User ID: {test_user_id}")
    print(f"   Webhook Source: test_reverse_sync (должен триггерить обратную синхронизацию)")
    
    # Отправляем webhook
    print(f"\n📡 Отправка webhook на {WEBHOOK_URL}...")
    try:
        response = requests.post(
            WEBHOOK_URL,
            json=test_payload,
            headers={'Content-Type': 'application/json'},
            timeout=60  # Увеличиваем timeout для обратной синхронизации
        )
        
        if response.status_code == 200:
            webhook_result = response.json()
            print(f"✅ Webhook успешно обработан: {webhook_result}")
            
            action = webhook_result.get('action')
            supabase_order_id = webhook_result.get('order_id')
            
            if action == 'create_order' and supabase_order_id:
                print(f"✅ Заказ создан в Supabase: {supabase_order_id}")
                
                # Ждем завершения обратной синхронизации
                print(f"\n⏳ Ожидание завершения обратной синхронизации (10 сек)...")
                time.sleep(10)
                
                # Проверяем, что bitrix_order_id появился в Supabase
                print(f"\n🔍 Проверка результатов обратной синхронизации...")
                check_reverse_sync_result(test_order_id, supabase_order_id)
                
            else:
                print(f"❌ Неожиданный результат webhook: action={action}, order_id={supabase_order_id}")
        else:
            print(f"❌ Ошибка webhook: {response.status_code} - {response.text}")
            
    except requests.exceptions.Timeout:
        print(f"❌ Timeout при отправке webhook (возможно, обратная синхронизация занимает много времени)")
    except Exception as e:
        print(f"❌ Ошибка при отправке webhook: {e}")

def check_reverse_sync_result(test_order_id, supabase_order_id):
    """Проверяет результат обратной синхронизации"""
    try:
        # Проверяем заказ через API
        api_url = "http://localhost:8001/api/orders"
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            orders = response.json()
            
            # Находим наш тестовый заказ
            test_order = None
            for order in orders:
                if order.get('bitrix_order_id') == test_order_id:
                    test_order = order
                    break
            
            if test_order:
                print(f"✅ Заказ найден в Supabase:")
                print(f"   • Supabase ID: {test_order['id']}")
                print(f"   • Order Number: {test_order.get('order_number')}")
                print(f"   • Bitrix Order ID: {test_order.get('bitrix_order_id')}")
                print(f"   • Recipient: {test_order.get('recipient_name')}")
                print(f"   • Phone: {test_order.get('recipient_phone')}")
                print(f"   • Address: {test_order.get('delivery_address')}")
                print(f"   • Postcard: {test_order.get('postcard_text')}")
                print(f"   • Total: {test_order.get('total_amount')} KZT")
                
                # Проверяем обратную синхронизацию
                bitrix_order_id = test_order.get('bitrix_order_id')
                if bitrix_order_id and bitrix_order_id != test_order_id:
                    print(f"\n🎉 ОБРАТНАЯ СИНХРОНИЗАЦИЯ УСПЕШНА!")
                    print(f"   📊 Supabase Order: {test_order['id']}")
                    print(f"   🔄 Bitrix Order: {bitrix_order_id}")
                    print(f"   ✅ Заказ должен быть виден в https://cvety.kz/crm/")
                    
                    # Дополнительная проверка - можно добавить прямую проверку Bitrix MySQL
                    check_bitrix_order_exists(bitrix_order_id)
                    
                elif bitrix_order_id == test_order_id:
                    print(f"\n⚠️  ОБРАТНАЯ СИНХРОНИЗАЦИЯ НЕ СРАБОТАЛА")
                    print(f"   bitrix_order_id остался тем же: {bitrix_order_id}")
                    print(f"   Заказ создался только в Supabase")
                    
                else:
                    print(f"\n❌ ОБРАТНАЯ СИНХРОНИЗАЦИЯ НЕ СРАБОТАЛА")
                    print(f"   bitrix_order_id = NULL или пустой")
                    print(f"   Заказ НЕ синхронизирован с Bitrix")
                
            else:
                print(f"❌ Заказ {test_order_id} не найден в Supabase")
        else:
            print(f"❌ Ошибка API: {response.status_code}")
    
    except Exception as e:
        print(f"❌ Ошибка проверки результата: {e}")

def check_bitrix_order_exists(bitrix_order_id):
    """Дополнительная проверка - существует ли заказ в Bitrix"""
    print(f"\n🔍 Дополнительная проверка: ищем заказ {bitrix_order_id} в Bitrix...")
    
    # Можно добавить прямой запрос к MySQL Bitrix или к API
    # Пока что просто выводим инструкции для ручной проверки
    print(f"📋 Для ручной проверки:")
    print(f"   1. Откройте https://cvety.kz/crm/")
    print(f"   2. Найдите заказ #{bitrix_order_id}")
    print(f"   3. Проверьте данные получателя: 'Получатель Обратной Синхронизации'")
    print(f"   4. Проверьте текст открытки: '🔄 Тест обратной синхронизации!'")

def main():
    """Основная функция"""
    print("🚀 Запуск теста обратной синхронизации...")
    print("    Этот тест создает заказ в Supabase через webhook")
    print("    и проверяет, что он автоматически синхронизируется в Bitrix\n")
    
    # Проверяем, что FastAPI приложение запущено
    try:
        response = requests.get("http://localhost:8001/", timeout=5)
        if response.status_code == 200:
            print("✅ FastAPI приложение запущено")
        else:
            print("⚠️ FastAPI приложение отвечает, но не HTTP 200")
    except:
        print("❌ FastAPI приложение НЕ запущено на localhost:8001")
        print("   Запустите: python3 -m uvicorn app:app --host 0.0.0.0 --port 8001 --reload")
        return
    
    # Запускаем тест
    test_reverse_synchronization()

if __name__ == "__main__":
    main()