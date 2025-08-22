#!/usr/bin/env python3
"""
Финальный тест - создание идеального заказа как 122183
Проверяет исправленные открытку и время доставки
"""

import requests
import json
import time
from datetime import datetime

# Настройки
WEBHOOK_URL = "http://localhost:8001/webhooks/bitrix/order"
WEBHOOK_TOKEN = "fad5fbe4c8a520cf6d5453685b758c7fd9f6681f084be335fcdcd190ad9aaa0e"

def test_perfect_order_like_122183():
    """Создает заказ максимально похожий на образцовый 122183"""
    timestamp = int(time.time())
    test_order_id = timestamp + 999000  # Уникальный ID
    test_user_id = timestamp + 150000
    
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
            "USER_DESCRIPTION": "ФИНАЛЬНЫЙ ТЕСТ: Заказ как в образце 122183",
            "properties": {
                # Основные свойства
                "phone": "+77777777444",
                "email": "perfect_test@example.com",
                "nameRecipient": "Получатель Идеального Заказа",
                "phoneRecipient": "+77777777445",
                "addressRecipient": "Идеальный адрес для тестирования, ул. Образцовая, д. 50",
                
                # КРИТИЧЕСКИЕ исправленные поля
                "city": "2",  # Алматы (как в 122183)
                "when": "18",  # 15:00-16:00 (как время "33" в 122183, но используем 18)
                "data": "2025-08-25",  # Дата доставки
                "shopId": "17008",  # CVETYKZ (как в 122183)
                "postcardText": "🌹 Финальный тест: это должно быть в открытке, не в комментариях! Проверка исправленного кода.",
                
                # Дополнительные
                "SOURCE_ORDER": "perfect_final_test"
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
                "phone": "+77777777444",
                "email": "perfect_test@example.com"
            },
            "webhook_source": "perfect_final_test",  # Запускает обратную синхронизацию
            "webhook_timestamp": datetime.now().isoformat()
        }
    }
    
    print("🌹 ФИНАЛЬНЫЙ ТЕСТ - ИДЕАЛЬНЫЙ ЗАКАЗ КАК 122183")
    print("=" * 70)
    print(f"📦 Создание заказа {test_order_id} с исправленными полями...")
    print("")
    print("🔧 ИСПРАВЛЕНИЯ В ЭТОМ ТЕСТЕ:")
    print("   ✅ postcardText теперь в properties[\"postcardText\"] (НЕ в postcard_text)")
    print("   ✅ Добавлено логирование установки полей в PHP")
    print("   ✅ Все свойства передаются в правильной структуре")
    print("")
    print("📋 Ожидаемый результат (как в заказе 122183):")
    print(f"   🏙️ Город: Алматы (city=2)")
    print(f"   ⏰ Время: 15:00-16:00 (when=18)")
    print(f"   📅 Дата: 2025-08-25")
    print(f"   🏪 Магазин: CVETYKZ (shopId=17008)")
    print(f"   💌 Открытка: \"🌹 Финальный тест: это должно быть в открытке...\"")
    print(f"   🎯 Товар: {real_product['name']} - {real_product['price']:,.0f} KZT")
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
            print("⏳ Ожидаем завершения обратной синхронизации (25 секунд)...")
            time.sleep(25)
            
            print("🎯 ПРОВЕРКА РЕЗУЛЬТАТА:")
            print("   1. Откройте Bitrix CRM -> Заказы")
            print("   2. Найдите заказ с суммой 7,500₸ от текущего времени")
            print("   3. Убедитесь, что заказ содержит ВСЕ данные как 122183:")
            print("      ✅ Открытка: полный текст (НЕ в комментариях!)")
            print("      ✅ Время доставки: 15:00-16:00")
            print("      ✅ Город: Алматы") 
            print("      ✅ Магазин: CVETYKZ")
            print("      ✅ Товар в корзине")
            print("")
            print("🔗 Проверка логов с исправлениями:")
            print("   ssh root@185.125.90.141 'tail -30 /tmp/api_order_create.log'")
            print("   (Должны быть сообщения 'Set postcardText' и 'Set when')")
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
    print("🚀 ФИНАЛЬНЫЙ ТЕСТ СИСТЕМЫ...")
    print("    Проверяет ВСЕ исправления для создания идеального заказа\\n")
    
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
    supabase_order_id = test_perfect_order_like_122183()
    
    if supabase_order_id:
        print("🎉 ФИНАЛЬНЫЙ ТЕСТ ЗАВЕРШЕН!")
        print("")
        print("📊 РЕЗУЛЬТАТЫ ДОЛЖНЫ БЫТЬ ИДЕНТИЧНЫ ЗАКАЗУ 122183:")
        print(f"   • Supabase Order: {supabase_order_id}")
        print(f"   • Bitrix Order: (проверьте в CRM)")
        print("   • Открытка: ДОЛЖНА отображаться в поле 'Открытка'")
        print("   • Время: ДОЛЖНО быть '15:00-16:00' (не просто дата)")
        print("   • Город: ДОЛЖЕН быть 'Алматы'")
        print("   • Магазин: ДОЛЖЕН быть 'CVETYKZ'")
        print("")
        print("🏆 Если все поля заполнены корректно - система готова к production!")
    else:
        print("❌ Финальный тест не пройден")

if __name__ == "__main__":
    main()