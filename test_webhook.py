#!/usr/bin/env python3
"""
Тест webhook endpoint
"""

import json
import requests
import time

def test_webhook_endpoint():
    """Тестирует webhook endpoint"""
    
    print("🌐 ФАЗА 6: Тестирование webhook endpoint...")
    print()
    
    # URL и заголовки
    url = "http://localhost:8001/webhooks/bitrix/order"
    # Попробуем разные варианты токенов
    token_variants = [
        "fad5fbe4c8a520cf6d5453685b758c7fd9f6681f084be335fcdcd190ad9aaa0e",  # Из .env
        "secret-webhook-token-2024"  # Default из config
    ]
    
    for i, token in enumerate(token_variants):
        print(f"   🔑 Пробуем токен #{i+1}...")
        headers = {
            "Content-Type": "application/json", 
            "Authorization": f"Bearer {token}"
        }
    
    # Тестовый payload
    test_payload = {
        "event": "order.create",
        "data": {
            "ID": 999999,
            "STATUS_ID": "N",
            "DATE_INSERT": "22.08.2025 15:00:00",
            "PRICE": "10000.00",
            "USER_ID": 1079,
            "PHONE": "+77015211545",
            "EMAIL": "test@webhook.com",
            "COMMENT": "Тестовый заказ от webhook"
        }
    }
    
    print("🟡 Отправляем тестовый webhook...")
    print(f"   URL: {url}")
    print(f"   Payload: {json.dumps(test_payload, indent=2, ensure_ascii=False)[:200]}...")
    
    try:
        response = requests.post(
            url, 
            json=test_payload, 
            headers=headers,
            timeout=10
        )
        
        print(f"   📡 HTTP Status: {response.status_code}")
        
        if response.status_code == 200:
            print("   ✅ Webhook endpoint отвечает успешно")
            try:
                response_data = response.json()
                print(f"   📤 Ответ: {json.dumps(response_data, indent=2, ensure_ascii=False)[:200]}...")
            except:
                print(f"   📤 Ответ (text): {response.text[:200]}...")
            return True
            
        elif response.status_code == 404:
            print("   ❌ Endpoint не найден (404)")
            print("   💡 Проверьте что app.py содержит правильные routes")
            return False
            
        elif response.status_code == 401:
            print("   ❌ Ошибка авторизации (401)")
            print("   💡 Проверьте webhook token")
            return False
            
        else:
            print(f"   ❌ Неожиданный статус: {response.status_code}")
            print(f"   📤 Ответ: {response.text[:200]}...")
            return False
            
    except requests.exceptions.ConnectionError:
        print("   ❌ Не удалось подключиться к серверу")
        print("   💡 Убедитесь что FastAPI сервер запущен на порту 8001")
        return False
        
    except requests.exceptions.Timeout:
        print("   ❌ Таймаут запроса (>10s)")
        return False
        
    except Exception as e:
        print(f"   ❌ Ошибка запроса: {e}")
        return False

def test_server_status():
    """Проверяет что сервер запущен"""
    
    print("🟡 Проверяем статус сервера...")
    
    # Попробуем разные endpoints
    endpoints_to_try = [
        "/",
        "/docs", 
        "/openapi.json",
        "/health",
        "/status"
    ]
    
    for endpoint in endpoints_to_try:
        try:
            response = requests.get(f"http://localhost:8001{endpoint}", timeout=3)
            print(f"   {endpoint}: HTTP {response.status_code}")
            if response.status_code != 404:
                return True
        except requests.exceptions.ConnectionError:
            continue
        except:
            continue
    
    print("   ❌ Сервер не отвечает ни на один endpoint")
    return False

if __name__ == "__main__":
    print("🚀 ТЕСТИРОВАНИЕ WEBHOOK ENDPOINT")
    print("=" * 50)
    
    server_running = test_server_status()
    print()
    
    if server_running:
        webhook_works = test_webhook_endpoint()
        print()
        
        if webhook_works:
            print("🎯 WEBHOOK ENDPOINT РАБОТАЕТ!")
        else:
            print("⚠️  WEBHOOK ENDPOINT НЕ РАБОТАЕТ")
    else:
        print("❌ СЕРВЕР НЕ ЗАПУЩЕН")
        print("   Запустите: python3 -m uvicorn app:app --host 0.0.0.0 --port 8001 --reload")
        
    print("=" * 50)