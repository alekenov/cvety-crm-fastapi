#!/usr/bin/env python3
"""
Тестирование создания заказа с ПОЛНЫМИ свойствами
Проверяет city, when, data, shopId, nameRecipient, addressRecipient
"""

import requests
import json
import time
from datetime import datetime

# Настройки
WEBHOOK_URL = "http://localhost:8001/webhooks/bitrix/order"
WEBHOOK_TOKEN = "fad5fbe4c8a520cf6d5453685b758c7fd9f6681f084be335fcdcd190ad9aaa0e"

def test_complete_order_with_all_properties():
    """Создает заказ с полными свойствами как в реальном Bitrix"""
    timestamp = int(time.time())
    test_order_id = timestamp + 990000  # Уникальный ID
    test_user_id = timestamp + 140000
    
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
            "USER_DESCRIPTION": "Тест с полными свойствами заказа",
            "properties": {
                # Основные свойства получателя
                "phone": "+77777777333",
                "email": "complete_test@example.com",
                "nameRecipient": "Получатель С Полными Свойствами",
                "phoneRecipient": "+77777777334",
                "addressRecipient": "Полный адрес с городом и временем, ул. Полная, д. 40, кв. 15",
                
                # КРИТИЧЕСКИ ВАЖНЫЕ свойства для отображения в CRM
                "city": "2",  # Алматы (должен отображаться в CRM)
                "when": "18",  # 15:00-16:00 (должно отображаться время доставки)
                "data": "2025-08-25",  # Дата доставки
                "shopId": "17008",  # CVETYKZ (должно отображаться название магазина)
                
                # Дополнительные свойства
                "postcardText": "🏷️ Тест полных свойств: город, время, магазин",
                "SOURCE_ORDER": "complete_properties_test"
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
                "phone": "+77777777333",
                "email": "complete_test@example.com"
            },
            "webhook_source": "complete_properties_test",  # Запускает обратную синхронизацию
            "webhook_timestamp": datetime.now().isoformat()
        }
    }
    
    print("🏷️ ТЕСТИРОВАНИЕ ЗАКАЗА С ПОЛНЫМИ СВОЙСТВАМИ")
    print("=" * 65)
    print(f"📦 Создание заказа {test_order_id} с полными свойствами...")
    print(f"🎯 Товар: {real_product['name']} (ID: {real_product['id']})")
    print(f"💰 Цена: {real_product['price']:,.0f} KZT + доставка 1,500 KZT")
    print("")
    print("📋 Тестируемые свойства:")
    print(f"   🏙️ Город: {payload['data']['properties']['city']} (должен быть Алматы)")
    print(f"   ⏰ Время: {payload['data']['properties']['when']} (должно быть 15:00-16:00)")
    print(f"   📅 Дата: {payload['data']['properties']['data']}")
    print(f"   🏪 Магазин: {payload['data']['properties']['shopId']} (должен быть CVETYKZ)")
    print(f"   👤 Получатель: {payload['data']['properties']['nameRecipient']}")
    print(f"   📍 Адрес: {payload['data']['properties']['addressRecipient']}")
    print("")
    
    try:
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=60  # Увеличиваем timeout
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Webhook успешно обработан:")
            print(f"   • Status: {result.get('status')}")
            print(f"   • Action: {result.get('action')}")
            print(f"   • Supabase Order ID: {result.get('order_id')}")
            print("")
            
            # Ожидаем обратную синхронизацию
            print("⏳ Ожидаем завершения обратной синхронизации (20 секунд)...")
            time.sleep(20)
            
            print("🔍 Результат должен содержать:")
            print("   ✅ Заказ создан в Supabase")
            print("   ✅ Заказ создан в Bitrix с товаром")
            print("   ✅ В Bitrix CRM должны отображаться:")
            print("      • Город доставки (не пустой)")
            print("      • Время доставки (15:00-16:00)")
            print("      • Название магазина (CVETYKZ вместо пустоты)")
            print("")
            print("📊 Проверка в Bitrix CRM:")
            print("   1. Откройте список заказов")
            print("   2. Найдите заказ с суммой 7,500₸ от текущей даты")
            print("   3. Проверьте, что заполнены все поля как у заказов 122183/122193")
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
    """Основная функция тестирования"""
    print("🚀 Запуск теста полных свойств заказа...")
    print("    Этот тест проверяет отображение всех свойств в Bitrix CRM\\n")
    
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
    success = test_complete_order_with_all_properties()
    
    if success:
        print("🎉 Тест завершен успешно!")
        print("")
        print("📋 ДЛЯ ПРОВЕРКИ РЕЗУЛЬТАТА:")
        print("   1. Откройте Bitrix CRM -> Заказы")
        print("   2. Найдите заказ с сегодняшней датой и суммой 7,500₸")
        print("   3. Убедитесь, что заказ содержит:")
        print("      ✅ Город доставки")
        print("      ✅ Время доставки") 
        print("      ✅ Название магазина (CVETYKZ)")
        print("      ✅ Товар в корзине")
        print("")
        print("🔗 Логи для отладки:")
        print("   ssh root@185.125.90.141 'tail -30 /tmp/api_order_create.log'")
    else:
        print("❌ Тест не пройден")

if __name__ == "__main__":
    main()