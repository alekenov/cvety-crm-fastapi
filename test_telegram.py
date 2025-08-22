#!/usr/bin/env python3
"""
Тестирование Telegram уведомлений с полными данными
"""

import requests
import json
import time
from datetime import datetime

# Настройки
WEBHOOK_URL = "http://localhost:8001/webhooks/bitrix/order"
WEBHOOK_TOKEN = "fad5fbe4c8a520cf6d5453685b758c7fd9f6681f084be335fcdcd190ad9aaa0e"

def test_telegram_notification():
    """Создает заказ для тестирования Telegram уведомлений"""
    timestamp = int(time.time())
    test_order_id = timestamp + 950000
    test_user_id = timestamp + 100000
    
    payload = {
        "event": "order.create",
        "token": WEBHOOK_TOKEN,
        "data": {
            "ID": str(test_order_id),
            "ACCOUNT_NUMBER": str(test_order_id),
            "STATUS_ID": "N",
            "PRICE": "15000.0000",
            "PRICE_DELIVERY": "2500.0000",
            "USER_ID": str(test_user_id),
            "PAYED": "N",
            "DATE_INSERT": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "PAY_SYSTEM_ID": "10",
            "USER_DESCRIPTION": "Тест Telegram уведомлений - полные данные",
            "properties": {
                "phone": "+77777777555",
                "email": "telegram_full_test@example.com",
                "nameRecipient": "Получатель Полных Telegram Данных",
                "phoneRecipient": "+77777777556", 
                "addressRecipient": "Полный адрес для Telegram, ул. Тестовая, д. 15, кв. 25",
                "data": "2025-08-25",
                "postcardText": "📱 Полный тест Telegram уведомлений: данные заказа, получателя и товаров",
                "city": "2",
                "when": "18",
                "SOURCE_ORDER": "telegram_full_test",
                "shopId": "17008"
            },
            "basket": [
                {
                    "ID": str(test_order_id) + "1",
                    "PRODUCT_ID": "595099",
                    "NAME": "Премиум букет для Telegram теста",
                    "PRICE": "15000.0000",
                    "QUANTITY": "1.0000", 
                    "CURRENCY": "KZT",
                    "DISCOUNT_PRICE": "0.0000"
                }
            ],
            "user": {
                "ID": str(test_user_id),
                "phone": "+77777777555",
                "email": "telegram_full_test@example.com"
            },
            "webhook_source": "telegram_full_test",
            "webhook_timestamp": datetime.now().isoformat()
        }
    }
    
    print("📱 ТЕСТИРОВАНИЕ TELEGRAM УВЕДОМЛЕНИЙ")
    print("=" * 50)
    print(f"📦 Создание заказа {test_order_id} для Telegram уведомлений...")
    print(f"👤 Получатель: {payload['data']['properties']['nameRecipient']}")
    print(f"📍 Адрес: {payload['data']['properties']['addressRecipient']}")
    print(f"💰 Сумма: {payload['data']['PRICE']} KZT + доставка {payload['data']['PRICE_DELIVERY']} KZT")
    print(f"📝 Открытка: {payload['data']['properties']['postcardText']}")
    print("")
    
    try:
        response = requests.post(
            WEBHOOK_URL, 
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Webhook успешно обработан:")
            print(f"   • Status: {result.get('status')}")
            print(f"   • Action: {result.get('action')}")
            print(f"   • Order ID: {result.get('order_id')}")
            print("")
            print("📱 Проверьте Telegram бот на наличие уведомления с полными данными:")
            print("   • Информация о заказе")
            print("   • Данные получателя")
            print("   • Детали товара")
            print("   • Адрес доставки")
            print("   • Текст открытки")
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
    print("🚀 Запуск теста Telegram уведомлений...")
    print("    Создает заказ и проверяет отправку полных данных в Telegram\n")
    
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
    
    success = test_telegram_notification()
    
    if success:
        print("🎉 Тест Telegram уведомлений завершен!")
        print("📱 Проверьте Telegram бот на получение уведомления")
    else:
        print("❌ Тест не пройден")

if __name__ == "__main__":
    main()