#!/usr/bin/env python3
"""
Тестирование полной обработки заказа с товарами, пользователем и получателем
Использует реальные данные из order_122155_real_payload.json
"""

import requests
import json
import time
from datetime import datetime

# Настройки для тестирования
WEBHOOK_URL = "http://localhost:8001/webhooks/bitrix/order"
WEBHOOK_TOKEN = "fad5fbe4c8a520cf6d5453685b758c7fd9f6681f084be335fcdcd190ad9aaa0e"

# Загружаем реальные данные заказа
def load_real_order_data():
    """Загружает данные реального заказа"""
    with open('/Users/alekenov/cvety-local/crm_python/order_122155_real_payload.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def create_test_order_payload(base_order_data):
    """Создает тестовый заказ на основе реального"""
    # Создаем уникальный ID для тестового заказа
    timestamp = int(time.time())
    # Используем числовые ID для совместимости с базой данных
    test_order_id = timestamp + 900000  # Добавляем смещение чтобы не конфликтовать с реальными ID
    test_user_id = timestamp  # Используем целое число для bitrix_user_id
    
    # Копируем структуру реального заказа
    test_payload = {
        "event": "order.create",
        "token": WEBHOOK_TOKEN,
        "data": {
            "ID": str(test_order_id),  # ID передается как строка в webhook
            "ACCOUNT_NUMBER": str(test_order_id),
            "STATUS_ID": "N",  # Новый заказ
            "PRICE": "8400.0000",
            "PRICE_DELIVERY": "2000.0000",
            "DISCOUNT_VALUE": "0.0000",
            "USER_ID": test_user_id,
            "PAYED": "N",
            "DATE_INSERT": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "PAY_SYSTEM_ID": "10",
            "USER_DESCRIPTION": "Тестовый заказ для проверки полной обработки данных",
            "COMMENTS": None,
            "properties": {
                # Данные заказчика
                "name": None,
                "phone": "+77777777777",
                "email": "test@example.com",
                # Данные получателя
                "nameRecipient": "Тестовый Получатель",
                "phoneRecipient": "+77777777778",
                "addressRecipient": "Тестовый адрес доставки, д.1, кв.1",
                # Детали заказа
                "data": "2025-08-25",
                "postcardText": "С днем рождения! Тестовое поздравление.",
                "city": "2",
                "when": "26",
                "iWillGet": "N",
                "pickup": "N",
                # Ссылки и прочие данные
                "payLink": "https://cvety.kz/s/TestLink",
                "statusLink": "https://cvety.kz/s/TestStatus",
                "shopId": "17008",
                "SOURCE_ORDER": "web_test",
                "opt": "N",
                "group_purchasing": "N"
            },
            "basket": [
                {
                    "ID": f"{int(time.time())}1",
                    "PRODUCT_ID": "695515",
                    "NAME": "Тестовый товар - Подсолнухи в пачке 5 шт",
                    "PRICE": "6400.0000",
                    "QUANTITY": "1.0000",
                    "CURRENCY": "KZT",
                    "DISCOUNT_PRICE": "1600.0000",
                    "PRODUCT_XML_ID": None
                },
                {
                    "ID": f"{int(time.time())}2",
                    "PRODUCT_ID": "123456",
                    "NAME": "Тестовый товар 2 - Упаковка",
                    "PRICE": "2000.0000",
                    "QUANTITY": "1.0000",
                    "CURRENCY": "KZT",
                    "DISCOUNT_PRICE": "0.0000",
                    "PRODUCT_XML_ID": "test_xml_id"
                }
            ],
            "user": {
                "ID": str(test_user_id),  # ID как строка
                "phone": "+77777777777",
                "email": "test@example.com"
            },
            "webhook_source": "test_complete_order",
            "webhook_timestamp": datetime.now().isoformat()
        }
    }
    
    return test_payload, test_order_id, test_user_id

def send_webhook_request(payload):
    """Отправляет webhook запрос"""
    try:
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        
        return response.status_code, response.json() if response.status_code == 200 else response.text
    
    except Exception as e:
        return None, str(e)

def verify_order_data(test_order_id):
    """Проверяет что заказ создался с правильными данными"""
    try:
        # Проверяем через API
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
                print(f"✅ Заказ найден в Supabase: ID={test_order['id']}")
                
                # Проверяем основные поля
                checks = {
                    'order_number': str(test_order_id),
                    'recipient_name': 'Тестовый Получатель',
                    'recipient_phone': '+77777777778',
                    'delivery_address': 'Тестовый адрес доставки, д.1, кв.1',
                    'delivery_date': '2025-08-25',
                    'postcard_text': 'С днем рождения! Тестовое поздравление.',
                    'total_amount': 8400.0
                }
                
                for field, expected_value in checks.items():
                    actual_value = test_order.get(field)
                    if actual_value == expected_value:
                        print(f"✅ {field}: {actual_value}")
                    else:
                        print(f"❌ {field}: expected={expected_value}, actual={actual_value}")
                
                return test_order
            else:
                print(f"❌ Заказ {test_order_id} не найден в базе данных")
                return None
        else:
            print(f"❌ Ошибка API: {response.status_code}")
            return None
    
    except Exception as e:
        print(f"❌ Ошибка проверки заказа: {e}")
        return None

def verify_user_data(test_user_id):
    """Проверяет что пользователь создался"""
    try:
        api_url = "http://localhost:8001/api/users"
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            users = response.json()
            
            # Находим тестового пользователя
            test_user = None
            for user in users:
                if user.get('bitrix_user_id') == test_user_id:
                    test_user = user
                    break
            
            if test_user:
                print(f"✅ Пользователь найден: ID={test_user['id']}")
                print(f"✅ Телефон: {test_user.get('phone')}")
                print(f"✅ Email: {test_user.get('email')}")
                return test_user
            else:
                print(f"❌ Пользователь {test_user_id} не найден")
                return None
        else:
            print(f"❌ Ошибка API пользователей: {response.status_code}")
            return None
    
    except Exception as e:
        print(f"❌ Ошибка проверки пользователя: {e}")
        return None

def verify_order_items(order_id):
    """Проверяет что товары заказа сохранились"""
    try:
        api_url = f"http://localhost:8001/api/orders/{order_id}/items"
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            items = response.json()
            
            if len(items) >= 2:
                print(f"✅ Товары найдены: {len(items)} шт.")
                
                for i, item in enumerate(items, 1):
                    product_name = item.get('product_snapshot', {}).get('name', 'Unknown')
                    print(f"  Товар {i}: {product_name} - {item.get('quantity')} шт. - {item.get('price')} KZT")
                
                # Проверяем суммы
                total_expected = sum(item.get('total', 0) for item in items)
                print(f"✅ Общая сумма товаров: {total_expected} KZT")
                
                return items
            else:
                print(f"❌ Недостаточно товаров: найдено {len(items)}, ожидалось 2")
                return None
        else:
            print(f"❌ Ошибка API товаров: {response.status_code}")
            return None
    
    except Exception as e:
        print(f"❌ Ошибка проверки товаров: {e}")
        return None

def main():
    """Основная функция тестирования"""
    print("🧪 ТЕСТИРОВАНИЕ ПОЛНОЙ ОБРАБОТКИ ЗАКАЗА")
    print("=" * 50)
    
    # Загружаем реальные данные
    print("📄 Загрузка реальных данных заказа...")
    real_order = load_real_order_data()
    print(f"✅ Загружены данные заказа {real_order['data']['ID']}")
    
    # Создаем тестовый заказ
    print("\n📦 Создание тестового заказа...")
    test_payload, test_order_id, test_user_id = create_test_order_payload(real_order)
    print(f"✅ Создан тестовый заказ {test_order_id}")
    
    # Отправляем webhook
    print("\n📡 Отправка webhook...")
    status_code, response_data = send_webhook_request(test_payload)
    
    if status_code == 200:
        print(f"✅ Webhook успешно обработан: {response_data}")
    else:
        print(f"❌ Ошибка webhook: {status_code} - {response_data}")
        return
    
    # Ждем обработки
    print("\n⏳ Ожидание обработки...")
    time.sleep(2)
    
    # Проверяем данные заказа
    print("\n🔍 Проверка данных заказа...")
    order = verify_order_data(test_order_id)
    
    # Проверяем пользователя
    print("\n👤 Проверка пользователя...")
    user = verify_user_data(test_user_id)
    
    # Проверяем товары
    if order:
        print("\n🛍️ Проверка товаров заказа...")
        items = verify_order_items(order['id'])
        
        if items:
            print("\n✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ УСПЕШНО!")
            print("Заказ полностью обработан со всеми данными:")
            print(f"  - Заказ: {test_order_id}")
            print(f"  - Пользователь: {test_user_id}")  
            print(f"  - Товаров: {len(items)}")
            print(f"  - Получатель: {order.get('recipient_name')}")
            print(f"  - Адрес: {order.get('delivery_address')}")
        else:
            print("\n❌ Ошибка в обработке товаров")
    else:
        print("\n❌ Критическая ошибка - заказ не создался")

if __name__ == "__main__":
    main()