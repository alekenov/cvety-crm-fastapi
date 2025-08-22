#!/usr/bin/env python3
"""
Тестирование обновления bitrix_order_id в Supabase
Проверяет, что после создания заказа в Bitrix поле bitrix_order_id правильно обновляется.
"""

import requests
import json
import time
from datetime import datetime

# Настройки
WEBHOOK_URL = "http://localhost:8001/webhooks/bitrix/order"
WEBHOOK_TOKEN = "fad5fbe4c8a520cf6d5453685b758c7fd9f6681f084be335fcdcd190ad9aaa0e"

def test_bitrix_id_update():
    """Создает заказ и проверяет обновление bitrix_order_id"""
    timestamp = int(time.time())
    test_order_id = timestamp + 960000  # Уникальный ID
    test_user_id = timestamp + 110000
    
    payload = {
        "event": "order.create",
        "token": WEBHOOK_TOKEN,
        "data": {
            "ID": str(test_order_id),
            "ACCOUNT_NUMBER": str(test_order_id),
            "STATUS_ID": "N",
            "PRICE": "8000.0000",
            "PRICE_DELIVERY": "1500.0000",
            "USER_ID": str(test_user_id),
            "PAYED": "N",
            "DATE_INSERT": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "PAY_SYSTEM_ID": "10",
            "USER_DESCRIPTION": "Тест обновления bitrix_order_id в Supabase",
            "properties": {
                "phone": "+77777777999",
                "email": "bitrix_id_test@example.com",
                "nameRecipient": "Получатель Для Тестирования bitrix_order_id",
                "phoneRecipient": "+77777777998",
                "addressRecipient": "Тестовый адрес для bitrix_order_id, ул. ID Тест, д. 10",
                "data": "2025-08-24",
                "postcardText": "🔗 Тест обновления bitrix_order_id",
                "city": "2",
                "when": "29",
                "SOURCE_ORDER": "bitrix_id_test",
                "shopId": "17008"
            },
            "basket": [
                {
                    "ID": f"{test_order_id}1",
                    "PRODUCT_ID": "595099",
                    "NAME": "Тестовый букет для bitrix_order_id",
                    "PRICE": "8000.0000",
                    "QUANTITY": "1.0000",
                    "CURRENCY": "KZT"
                }
            ],
            "user": {
                "ID": str(test_user_id),
                "phone": "+77777777999",
                "email": "bitrix_id_test@example.com"
            },
            "webhook_source": "bitrix_id_test",  # НЕ production_real - запускает обратную синхронизацию
            "webhook_timestamp": datetime.now().isoformat()
        }
    }
    
    print("🔗 ТЕСТИРОВАНИЕ ОБНОВЛЕНИЯ BITRIX_ORDER_ID")
    print("=" * 55)
    print(f"📦 Создание заказа {test_order_id} для тестирования bitrix_order_id...")
    print(f"👤 Получатель: {payload['data']['properties']['nameRecipient']}")
    print(f"💰 Сумма: {payload['data']['PRICE']} KZT")
    print(f"🔄 Webhook source: {payload['data']['webhook_source']} (запустит обратную синхронизацию)")
    print("")
    
    try:
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=45  # Увеличиваем timeout для обратной синхронизации
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Webhook успешно обработан:")
            print(f"   • Status: {result.get('status')}")
            print(f"   • Action: {result.get('action')}")
            print(f"   • Supabase Order ID: {result.get('order_id')}")
            print("")
            
            # Даем время на обработку обратной синхронизации
            print("⏳ Ожидаем завершения обратной синхронизации (10 секунд)...")
            time.sleep(10)
            
            print("🔍 Проверка результата:")
            print("   1. Заказ должен быть создан в Supabase")
            print("   2. Заказ должен быть создан в Bitrix через PHP API")
            print("   3. bitrix_order_id должен быть обновлен в Supabase")
            print("")
            print("📋 Для проверки результата:")
            print("   • Проверьте FastAPI логи на сообщения '✅ Reverse sync completed'")
            print("   • Проверьте Supabase таблицу orders на наличие bitrix_order_id")
            print("   • Проверьте Bitrix логи: ssh root@185.125.90.141 'tail -10 /tmp/api_order_create.log'")
            print("")
            
            return True
        else:
            print(f"❌ Ошибка webhook: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Исключение: {e}")
        return False

def main():
    """Основная функция"""
    print("🚀 Запуск теста обновления bitrix_order_id...")
    print("    Создает заказ и проверяет корректное обновление bitrix_order_id в Supabase\\n")
    
    # Проверяем доступность FastAPI
    try:
        response = requests.get("http://localhost:8001/", timeout=5)
        if response.status_code == 200:
            print("✅ FastAPI приложение запущено")
        else:
            print("⚠️ FastAPI приложение отвечает, но не HTTP 200")
    except:
        print("❌ FastAPI приложение НЕ запущено на localhost:8001")
        return
    
    success = test_bitrix_id_update()
    
    if success:
        print("🎉 Тест завершен!")
        print("📊 Результат можно проверить в:")
        print("   • FastAPI логах")
        print("   • Supabase console (битрикс_order_id должен быть заполнен)")
        print("   • Bitrix логах на сервере")
    else:
        print("❌ Тест не пройден")

if __name__ == "__main__":
    main()