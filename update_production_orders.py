#!/usr/bin/env python3
"""
Скрипт для обновления статусов тестовых заказов в продакшене через Bitrix API
Переводит тестовые заказы в статус "UN" (Нереализован)
"""

import requests
import json
from config import config as app_config

def update_order_status_in_bitrix(order_id: int, new_status: str = "UN") -> bool:
    """
    Обновить статус заказа в Bitrix через REST API
    
    Args:
        order_id: ID заказа в Bitrix
        new_status: Новый статус ("UN" = Нереализован)
    
    Returns:
        True если успешно, False при ошибке
    """
    
    # URL для обновления заказа в Bitrix
    bitrix_api_url = "https://cvety.kz/astana/rest/1/cvety-api-token-2024-secure-123/sale.order.update"
    
    # Данные для обновления
    payload = {
        "id": order_id,
        "fields": {
            "STATUS_ID": new_status
        }
    }
    
    try:
        print(f"🔄 Обновление заказа {order_id} в Bitrix на статус '{new_status}'...")
        
        response = requests.post(
            bitrix_api_url,
            json=payload,
            timeout=30,
            headers={
                'Content-Type': 'application/json'
            }
        )
        
        if response.status_code == 200:
            try:
                result = response.json()
                
                if result.get('result'):
                    print(f"✅ Заказ {order_id} успешно обновлен на статус '{new_status}'")
                    return True
                else:
                    error_msg = result.get('error_description', result.get('error', 'Unknown error'))
                    print(f"❌ Ошибка API при обновлении заказа {order_id}: {error_msg}")
                    return False
                    
            except json.JSONDecodeError:
                print(f"❌ Некорректный JSON ответ от Bitrix для заказа {order_id}")
                print(f"Response: {response.text}")
                return False
        else:
            print(f"❌ HTTP ошибка {response.status_code} при обновлении заказа {order_id}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print(f"❌ Таймаут при обновлении заказа {order_id}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка сети при обновлении заказа {order_id}: {e}")
        return False
    except Exception as e:
        print(f"❌ Неожиданная ошибка при обновлении заказа {order_id}: {e}")
        return False

def get_order_info_from_bitrix(order_id: int) -> dict:
    """
    Получить информацию о заказе из Bitrix
    """
    bitrix_api_url = "https://cvety.kz/astana/rest/1/cvety-api-token-2024-secure-123/sale.order.get"
    
    payload = {
        "id": order_id
    }
    
    try:
        response = requests.post(
            bitrix_api_url,
            json=payload,
            timeout=30,
            headers={
                'Content-Type': 'application/json'
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('result'):
                return result['result']
        
        return {}
        
    except Exception as e:
        print(f"⚠️  Не удалось получить информацию о заказе {order_id}: {e}")
        return {}

def update_test_orders():
    """
    Обновить статусы тестовых заказов в продакшене
    """
    
    # Тестовые заказы, которые нужно перевести в "Нереализован"
    test_orders = [
        23632,  # Заказ "к" - 10₸
        23631,  # Заказ None - 12₸  
        23569   # Заказ "Алексей Владимирович Цыкарев" - 90₸
    ]
    
    print("🎯 Обновление статусов тестовых заказов в продакшене")
    print("=" * 60)
    
    print("📋 Список заказов для обновления:")
    for order_id in test_orders:
        print(f"  • Заказ {order_id}")
    
    print(f"\n🔄 Начинаем обновление через Bitrix REST API...")
    print("Новый статус: UN (Нереализован)")
    
    updated_count = 0
    
    for order_id in test_orders:
        print(f"\n--- Заказ {order_id} ---")
        
        # Сначала получаем текущую информацию
        order_info = get_order_info_from_bitrix(order_id)
        if order_info:
            current_status = order_info.get('STATUS_ID', 'Unknown')
            print(f"Текущий статус: {current_status}")
        
        # Обновляем статус
        if update_order_status_in_bitrix(order_id, "UN"):
            updated_count += 1
        
        # Небольшая пауза между запросами
        import time
        time.sleep(1)
    
    print(f"\n🎉 ЗАВЕРШЕНО!")
    print(f"Обновлено заказов: {updated_count}/{len(test_orders)}")
    
    if updated_count == len(test_orders):
        print("✅ Все тестовые заказы успешно переведены в статус 'Нереализован'")
        print("📱 Проверьте https://cvety.kz/crm/ - заказы должны исчезнуть из активных")
    else:
        print("⚠️  Не все заказы удалось обновить. Проверьте ошибки выше.")

if __name__ == "__main__":
    update_test_orders()