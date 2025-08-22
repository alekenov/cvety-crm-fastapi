#!/usr/bin/env python3
"""
Тестирование создания заказов с РЕАЛЬНЫМИ товарами
Использует существующие в базе ID товаров
"""

import requests
import json
import time
from datetime import datetime

# Настройки
WEBHOOK_URL = "http://localhost:8001/webhooks/bitrix/order"
WEBHOOK_TOKEN = "fad5fbe4c8a520cf6d5453685b758c7fd9f6681f084be335fcdcd190ad9aaa0e"

# Реальные товары из базы данных
REAL_PRODUCTS = [
    {"id": 696624, "name": "Букет Премиум", "price": 15000.00},
    {"id": 696613, "name": "Букет Стандарт", "price": 7500.00},
    {"id": 696585, "name": "Букет Эконом", "price": 7500.00},
    {"id": 695515, "name": "Букет Мини", "price": 4800.00}
]

def create_test_order_with_real_items():
    """Создает заказ с реальными товарами из базы"""
    timestamp = int(time.time())
    test_order_id = timestamp + 970000  # Уникальный ID
    test_user_id = timestamp + 120000
    
    # Выбираем случайный товар для теста
    selected_product = REAL_PRODUCTS[1]  # Букет Стандарт 7500₸
    
    payload = {
        "event": "order.create",
        "token": WEBHOOK_TOKEN,
        "data": {
            "ID": str(test_order_id),
            "ACCOUNT_NUMBER": str(test_order_id),
            "STATUS_ID": "N",
            "PRICE": str(selected_product["price"]),
            "PRICE_DELIVERY": "1500.0000",
            "USER_ID": str(test_user_id),
            "PAYED": "N",
            "DATE_INSERT": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "PAY_SYSTEM_ID": "10",
            "USER_DESCRIPTION": f"Тест с реальным товаром {selected_product['name']}",
            "properties": {
                "phone": "+77777777111",
                "email": "real_items_test@example.com",
                "nameRecipient": "Получатель Реальных Товаров",
                "phoneRecipient": "+77777777112",
                "addressRecipient": "Реальный адрес для реальных товаров, ул. Товарная, д. 20",
                "data": "2025-08-25",
                "postcardText": "🛍️ Тест с реальными товарами из базы данных",
                "city": "2",
                "when": "30",
                "SOURCE_ORDER": "real_items_test",
                "shopId": "17008"
            },
            "basket": [
                {
                    "ID": f"{test_order_id}1",
                    "PRODUCT_ID": str(selected_product["id"]),  # РЕАЛЬНЫЙ ID товара
                    "NAME": selected_product["name"],
                    "PRICE": str(selected_product["price"]),
                    "QUANTITY": "1.0000",
                    "CURRENCY": "KZT",
                    "DISCOUNT_PRICE": "0.0000"
                }
            ],
            "user": {
                "ID": str(test_user_id),
                "phone": "+77777777111",
                "email": "real_items_test@example.com"
            },
            "webhook_source": "real_items_test",  # НЕ production_real - запускает обратную синхронизацию
            "webhook_timestamp": datetime.now().isoformat()
        }
    }
    
    print("🛍️ ТЕСТИРОВАНИЕ ЗАКАЗОВ С РЕАЛЬНЫМИ ТОВАРАМИ")
    print("=" * 60)
    print(f"📦 Создание заказа {test_order_id} с реальным товаром...")
    print(f"🎯 Товар: {selected_product['name']} (ID: {selected_product['id']})")
    print(f"💰 Цена: {selected_product['price']:,.0f} KZT")
    print(f"👤 Получатель: {payload['data']['properties']['nameRecipient']}")
    print(f"📍 Адрес: {payload['data']['properties']['addressRecipient']}")
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
            print("⏳ Ожидаем завершения обратной синхронизации (15 секунд)...")
            time.sleep(15)
            
            print("🔍 Результат должен содержать:")
            print("   ✅ Заказ создан в Supabase")
            print("   ✅ Заказ создан в Bitrix с товаром")
            print("   ✅ Товар добавлен в корзину Bitrix")
            print("   ✅ bitrix_order_id обновлен в Supabase")
            print("")
            print("📋 Для проверки:")
            print("   • Bitrix CRM -> заказ должен содержать товар")
            print("   • Supabase console -> bitrix_order_id должен быть заполнен")
            print("   • Логи: ssh root@185.125.90.141 'tail -20 /tmp/api_order_create.log'")
            print("")
            
            return True
        else:
            print(f"❌ Ошибка webhook: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Исключение: {e}")
        return False

def test_multiple_items_order():
    """Создает заказ с несколькими товарами"""
    timestamp = int(time.time())
    test_order_id = timestamp + 980000  # Уникальный ID
    test_user_id = timestamp + 130000
    
    # Выбираем 2 товара
    selected_products = REAL_PRODUCTS[2:4]  # Эконом + Мини
    total_price = sum(p["price"] for p in selected_products)
    
    basket = []
    for i, product in enumerate(selected_products):
        basket.append({
            "ID": f"{test_order_id}{i+1}",
            "PRODUCT_ID": str(product["id"]),
            "NAME": product["name"],
            "PRICE": str(product["price"]),
            "QUANTITY": "1.0000",
            "CURRENCY": "KZT",
            "DISCOUNT_PRICE": "0.0000"
        })
    
    payload = {
        "event": "order.create",
        "token": WEBHOOK_TOKEN,
        "data": {
            "ID": str(test_order_id),
            "ACCOUNT_NUMBER": str(test_order_id),
            "STATUS_ID": "N",
            "PRICE": str(total_price),
            "PRICE_DELIVERY": "2000.0000",
            "USER_ID": str(test_user_id),
            "PAYED": "N",
            "DATE_INSERT": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "PAY_SYSTEM_ID": "10",
            "USER_DESCRIPTION": f"Тест с {len(selected_products)} товарами",
            "properties": {
                "phone": "+77777777222",
                "email": "multi_items_test@example.com",
                "nameRecipient": "Получатель Множественных Товаров",
                "phoneRecipient": "+77777777223",
                "addressRecipient": "Адрес для множественных товаров, ул. Мульти, д. 30",
                "data": "2025-08-25",
                "postcardText": f"🛍️ Тест с {len(selected_products)} реальными товарами",
                "city": "2",
                "when": "31",
                "SOURCE_ORDER": "multi_items_test",
                "shopId": "17008"
            },
            "basket": basket,
            "user": {
                "ID": str(test_user_id),
                "phone": "+77777777222",
                "email": "multi_items_test@example.com"
            },
            "webhook_source": "multi_items_test",
            "webhook_timestamp": datetime.now().isoformat()
        }
    }
    
    print("🛒 ТЕСТИРОВАНИЕ ЗАКАЗА С НЕСКОЛЬКИМИ ТОВАРАМИ")
    print("=" * 60)
    print(f"📦 Создание заказа {test_order_id} с {len(selected_products)} товарами...")
    
    for i, product in enumerate(selected_products, 1):
        print(f"🎯 Товар {i}: {product['name']} (ID: {product['id']}) - {product['price']:,.0f} KZT")
    
    print(f"💰 Общая сумма: {total_price:,.0f} KZT + доставка 2000 KZT")
    print(f"👤 Получатель: {payload['data']['properties']['nameRecipient']}")
    print("")
    
    try:
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=45
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Webhook успешно обработан:")
            print(f"   • Status: {result.get('status')}")
            print(f"   • Supabase Order ID: {result.get('order_id')}")
            print("")
            
            print("⏳ Ожидаем завершения обратной синхронизации (15 секунд)...")
            time.sleep(15)
            
            print("🎉 Заказ с несколькими товарами создан!")
            return True
        else:
            print(f"❌ Ошибка: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Исключение: {e}")
        return False

def main():
    """Основная функция тестирования"""
    print("🚀 Запуск тестирования заказов с реальными товарами...")
    print("    Этот тест использует существующие ID товаров из базы данных\\n")
    
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
    
    print("📋 Доступные товары для тестирования:")
    for product in REAL_PRODUCTS:
        print(f"   • {product['name']} (ID: {product['id']}) - {product['price']:,.0f} KZT")
    print("")
    
    # Тест 1: Один товар
    print("🧪 ТЕСТ 1: Заказ с одним товаром")
    success1 = create_test_order_with_real_items()
    
    if success1:
        print("✅ Тест 1 завершен успешно!\\n")
        
        # Тест 2: Несколько товаров
        print("🧪 ТЕСТ 2: Заказ с несколькими товарами")
        success2 = test_multiple_items_order()
        
        if success2:
            print("✅ Тест 2 завершен успешно!")
            print("")
            print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
            print("📊 Результаты:")
            print("   • Создано 2 заказа с реальными товарами")
            print("   • Товары должны отображаться в Bitrix CRM")
            print("   • Суммы заказов должны соответствовать ценам товаров")
        else:
            print("❌ Тест 2 не пройден")
    else:
        print("❌ Тест 1 не пройден")

if __name__ == "__main__":
    main()