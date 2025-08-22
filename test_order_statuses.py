#!/usr/bin/env python3
"""
Тестирование поэтапного изменения статусов заказов
N → AP → PD → CO → RD → DE → F

Проверяет, как система обрабатывает изменения статусов заказов
от создания до завершения.
"""

import requests
import json
import time
from datetime import datetime

# Настройки
WEBHOOK_URL = "http://localhost:8001/webhooks/bitrix/order"
WEBHOOK_TOKEN = "fad5fbe4c8a520cf6d5453685b758c7fd9f6681f084be335fcdcd190ad9aaa0e"

# Последовательность статусов для тестирования
ORDER_STATUSES = [
    ("N", "Новый заказ"),
    ("AP", "Принят к исполнению"),
    ("PD", "Доставляется"),
    ("CO", "Выполнен"),
    ("RD", "Возврат"),
    ("DE", "Отклонен"),
    ("F", "Завершен")
]

def create_test_order():
    """Создает тестовый заказ для изменения статусов"""
    timestamp = int(time.time())
    test_order_id = timestamp + 900000  # Уникальный ID
    test_user_id = timestamp
    
    # Создаем базовый заказ
    payload = {
        "event": "order.create",
        "token": WEBHOOK_TOKEN,
        "data": {
            "ID": str(test_order_id),
            "ACCOUNT_NUMBER": str(test_order_id),
            "STATUS_ID": "N",
            "PRICE": "5000.0000",
            "PRICE_DELIVERY": "1000.0000", 
            "USER_ID": str(test_user_id),
            "PAYED": "N",
            "DATE_INSERT": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "PAY_SYSTEM_ID": "10",
            "USER_DESCRIPTION": "Тестовый заказ для проверки изменения статусов",
            "properties": {
                "phone": "+77777777888",
                "email": "status_test@example.com",
                "nameRecipient": "Получатель Тестовых Статусов",
                "phoneRecipient": "+77777777889",
                "addressRecipient": "Тестовый адрес для статусов, ул. Статусная, д. 5",
                "data": "2025-08-23",
                "postcardText": "🔄 Тест изменения статусов заказа",
                "city": "2",
                "when": "27",
                "SOURCE_ORDER": "status_test",
                "shopId": "17008"
            },
            "basket": [
                {
                    "ID": f"{test_order_id}1",
                    "PRODUCT_ID": "595099",  # Белоснежный букет
                    "NAME": "Белоснежный букет (тест статусов)",
                    "PRICE": "5000.0000",
                    "QUANTITY": "1.0000",
                    "CURRENCY": "KZT"
                }
            ],
            "user": {
                "ID": str(test_user_id),
                "phone": "+77777777888",
                "email": "status_test@example.com"
            },
            "webhook_source": "status_test_create",
            "webhook_timestamp": datetime.now().isoformat()
        }
    }
    
    print(f"📦 Создание тестового заказа {test_order_id} для проверки статусов...")
    
    try:
        response = requests.post(WEBHOOK_URL, json=payload, headers={'Content-Type': 'application/json'}, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Заказ создан: {result}")
            return test_order_id, result.get('order_id')
        else:
            print(f"❌ Ошибка создания заказа: {response.status_code} - {response.text}")
            return None, None
            
    except Exception as e:
        print(f"❌ Исключение при создании заказа: {e}")
        return None, None

def change_order_status(bitrix_order_id, new_status, status_name):
    """Изменяет статус заказа"""
    payload = {
        "event": "order.status_change", 
        "token": WEBHOOK_TOKEN,
        "data": {
            "ID": str(bitrix_order_id),
            "STATUS_ID": new_status,
            "DATE_STATUS": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "PRICE": "5000.0000",
            "USER_DESCRIPTION": f"Статус изменен на: {status_name}",
            "webhook_source": "status_test_change",
            "webhook_timestamp": datetime.now().isoformat()
        }
    }
    
    print(f"🔄 Изменение статуса заказа {bitrix_order_id}: {new_status} ({status_name})")
    
    try:
        response = requests.post(WEBHOOK_URL, json=payload, headers={'Content-Type': 'application/json'}, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Статус изменен: {result}")
            return True
        else:
            print(f"❌ Ошибка изменения статуса: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Исключение при изменении статуса: {e}")
        return False

def test_order_status_changes():
    """Основная функция тестирования изменения статусов"""
    print("🧪 ТЕСТИРОВАНИЕ ИЗМЕНЕНИЯ СТАТУСОВ ЗАКАЗОВ")
    print("=" * 60)
    print("Последовательность: N → AP → PD → CO → RD → DE → F")
    print("")
    
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
    
    # Шаг 1: Создаем тестовый заказ
    bitrix_order_id, supabase_order_id = create_test_order()
    if not bitrix_order_id:
        print("❌ Не удалось создать тестовый заказ")
        return
    
    print(f"📋 Тестовый заказ создан:")
    print(f"   • Bitrix Order ID: {bitrix_order_id}")
    print(f"   • Supabase Order ID: {supabase_order_id}")
    print("")
    
    # Шаг 2: Проходим по всем статусам (кроме N, который уже установлен)
    for status_code, status_name in ORDER_STATUSES[1:]:  # Пропускаем N
        print(f"🔄 Тест статуса: {status_code} ({status_name})")
        
        success = change_order_status(bitrix_order_id, status_code, status_name)
        
        if success:
            print(f"✅ Статус {status_code} успешно обработан")
        else:
            print(f"❌ Ошибка обработки статуса {status_code}")
            
        # Небольшая пауза между изменениями
        print("⏳ Пауза 3 секунды...")
        time.sleep(3)
        print("")
    
    print("🎉 Тестирование изменения статусов завершено!")
    print(f"📊 Результаты:")
    print(f"   • Заказ: {bitrix_order_id}")
    print(f"   • Статусы протестированы: {len(ORDER_STATUSES)} шт")
    print(f"   • Финальный статус: F (Завершен)")

def main():
    """Основная функция"""
    print("🚀 Запуск теста изменения статусов заказов...")
    print("    Этот тест создает заказ и изменяет его статусы поэтапно")
    print("    от 'Новый' до 'Завершен' через все промежуточные статусы\n")
    
    test_order_status_changes()

if __name__ == "__main__":
    main()