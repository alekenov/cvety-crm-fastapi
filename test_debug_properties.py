#!/usr/bin/env python3
"""
Debug тест для проверки передачи всех свойств в Bitrix
Использует debug endpoint с детальным логированием
"""

import requests
import json
import time
from datetime import datetime

# Настройки
WEBHOOK_URL = "http://localhost:8001/webhooks/bitrix/order"
WEBHOOK_TOKEN = "fad5fbe4c8a520cf6d5453685b758c7fd9f6681f084be335fcdcd190ad9aaa0e"

def test_debug_properties():
    """Создает заказ с полными свойствами и детальным логированием"""
    timestamp = int(time.time())
    test_order_id = timestamp + 500000  # Уникальный ID
    test_user_id = timestamp + 100000
    
    # Реальный товар
    real_product = {"id": 696613, "name": "Букет Стандарт", "price": 7500.00}
    
    payload = {
        "event": "order.create",
        "token": WEBHOOK_TOKEN,
        "data": {
            "ID": str(test_order_id),
            "ACCOUNT_NUMBER": str(test_order_id),
            "STATUS_ID": "N",
            "PRICE": str(real_product["price"]),
            "PRICE_DELIVERY": "1500.0000",
            "USER_ID": str(test_user_id),
            "PAYED": "N",
            "DATE_INSERT": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "PAY_SYSTEM_ID": "10",
            "USER_DESCRIPTION": "DEBUG ТЕСТ: Детальная проверка свойств",
            "properties": {
                # Основные свойства получателя
                "phone": "+77777777999",
                "email": "debug_test@example.com",
                "nameRecipient": "DEBUG Получатель Тестовый",
                "phoneRecipient": "+77777777998",
                "addressRecipient": "DEBUG адрес для тестирования свойств, ул. Тестовая, д. 999",
                
                # КРИТИЧЕСКИ ВАЖНЫЕ свойства для отображения в CRM
                "city": "2",  # Алматы (должен отображаться в CRM)
                "when": "18",  # 15:00-16:00 (должно отображаться время доставки)
                "data": "2025-08-25",  # Дата доставки
                "shopId": "17008",  # CVETYKZ (должно отображаться название магазина)
                
                # Дополнительные свойства
                "postcardText": "🔍 DEBUG тест: Эта открытка должна быть видна в поле 'Открытка'",
                "SOURCE_ORDER": "debug_properties_test"
            },
            "basket": [
                {
                    "ID": f"{test_order_id}1",
                    "PRODUCT_ID": str(real_product["id"]),
                    "NAME": real_product["name"],
                    "PRICE": str(real_product["price"]),
                    "QUANTITY": "1.0000",
                    "CURRENCY": "KZT"
                }
            ],
            "user": {
                "ID": str(test_user_id),
                "phone": "+77777777999",
                "email": "debug_test@example.com"
            },
            "webhook_source": "debug_properties_test",  # Запускает обратную синхронизацию
            "webhook_timestamp": datetime.now().isoformat()
        }
    }
    
    print("🔍 DEBUG ТЕСТ - ДЕТАЛЬНАЯ ПРОВЕРКА СВОЙСТВ")
    print("=" * 70)
    print(f"📦 Создание заказа {test_order_id} с DEBUG логированием...")
    print(f"🎯 Товар: {real_product['name']} (ID: {real_product['id']})")
    print(f"💰 Цена: {real_product['price']:,.0f} KZT + доставка 1,500 KZT")
    print("")
    print("🔧 DEBUG свойства передаваемые в Bitrix:")
    for key, value in payload["data"]["properties"].items():
        print(f"   • {key}: '{value}'")
    print("")
    
    try:
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Webhook успешно обработан:")
            print(f"   • Status: {result.get('status')}")
            print(f"   • Action: {result.get('action')}")
            print(f"   • Supabase Order ID: {result.get('order_id')}")
            print("")
            
            # Ожидаем обратную синхронизацию
            print("⏳ Ожидаем завершения обратной синхронизации (25 секунд)...")
            time.sleep(25)
            
            print("📊 ПРОВЕРКА DEBUG ЛОГОВ:")
            print("   ssh root@185.125.90.141 'tail -50 /tmp/api_order_create.log'")
            print("")
            print("🔍 Ищите в логах:")
            print("   ✅ 'Set postcardText: 🔍 DEBUG тест...'")
            print("   ✅ 'Set when: 18'")
            print("   ✅ 'Set city: 2'")
            print("   ✅ 'Set shopId: 17008'")
            print("")
            
            return result.get('order_id')
        else:
            print(f"❌ Ошибка webhook: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Исключение: {e}")
        return None

def main():
    """Основная функция тестирования"""
    print("🚀 Запуск DEBUG теста свойств...")
    print("    Этот тест использует специальный debug endpoint с детальным логированием\n")
    
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
    
    print("")
    supabase_order_id = test_debug_properties()
    
    if supabase_order_id:
        print("🎉 DEBUG тест завершен!")
        print("")
        print("📋 СЛЕДУЮЩИЕ ШАГИ:")
        print("   1. Проверьте логи: ssh root@185.125.90.141 'tail -50 /tmp/api_order_create.log'")
        print("   2. Найдите заказ в Bitrix CRM с SOURCE_ORDER = 'api_supabase_debug'")
        print("   3. Убедитесь, что все поля заполнены как в образце 122183")
        print("")
        print(f"🆔 Supabase Order ID: {supabase_order_id}")
    else:
        print("❌ DEBUG тест не пройден")

if __name__ == "__main__":
    main()