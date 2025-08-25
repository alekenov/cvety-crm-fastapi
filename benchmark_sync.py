#!/usr/bin/env python3
"""
Benchmark для тестирования производительности синхронизации
"""
import time
import requests
import json
import statistics
from typing import List

def benchmark_webhook(order_id: str = "122379", iterations: int = 5) -> dict:
    """Тестирует скорость обработки webhook"""
    
    webhook_url = "http://localhost:8001/webhooks/bitrix/order"
    payload = {
        "event": "order.status_change",
        "token": "fad5fbe4c8a520cf6d5453685b758c7fd9f6681f084be335fcdcd190ad9aaa0e",
        "data": {
            "ID": order_id,
            "STATUS_ID": "AP"
        }
    }
    
    times = []
    errors = 0
    
    print(f"🏃 Запуск бенчмарка webhook для заказа {order_id}...")
    print(f"Итераций: {iterations}\n")
    
    for i in range(iterations):
        start = time.time()
        try:
            response = requests.post(webhook_url, json=payload, timeout=30)
            elapsed = time.time() - start
            times.append(elapsed)
            
            status_icon = "✅" if response.status_code == 200 else "⚠️"
            print(f"  Итерация {i+1}: {elapsed:.3f}s {status_icon}")
        except Exception as e:
            errors += 1
            print(f"  Итерация {i+1}: ❌ Ошибка: {e}")
        
        # Небольшая пауза между запросами
        time.sleep(0.5)
    
    if times:
        return {
            "min": min(times),
            "max": max(times),
            "avg": statistics.mean(times),
            "median": statistics.median(times),
            "errors": errors,
            "success_rate": (len(times) / iterations) * 100
        }
    else:
        return {"errors": errors, "success_rate": 0}

def benchmark_order_detail(order_id: str = "2b5d8bca-335a-459f-882f-09eb07d9bbb5", iterations: int = 5) -> dict:
    """Тестирует скорость загрузки страницы заказа"""
    
    detail_url = f"http://localhost:8001/crm/orders/{order_id}"
    
    times = []
    errors = 0
    
    print(f"\n📄 Запуск бенчмарка страницы заказа...")
    print(f"Итераций: {iterations}\n")
    
    for i in range(iterations):
        start = time.time()
        try:
            response = requests.get(detail_url, timeout=30)
            elapsed = time.time() - start
            times.append(elapsed)
            
            status_icon = "✅" if response.status_code == 200 else "⚠️"
            print(f"  Итерация {i+1}: {elapsed:.3f}s {status_icon}")
        except Exception as e:
            errors += 1
            print(f"  Итерация {i+1}: ❌ Ошибка: {e}")
        
        time.sleep(0.5)
    
    if times:
        return {
            "min": min(times),
            "max": max(times),
            "avg": statistics.mean(times),
            "median": statistics.median(times),
            "errors": errors,
            "success_rate": (len(times) / iterations) * 100
        }
    else:
        return {"errors": errors, "success_rate": 0}

def benchmark_orders_list(iterations: int = 5) -> dict:
    """Тестирует скорость загрузки списка заказов"""
    
    list_url = "http://localhost:8001/crm/orders"
    
    times = []
    errors = 0
    
    print(f"\n📋 Запуск бенчмарка списка заказов...")
    print(f"Итераций: {iterations}\n")
    
    for i in range(iterations):
        start = time.time()
        try:
            response = requests.get(list_url, timeout=30)
            elapsed = time.time() - start
            times.append(elapsed)
            
            status_icon = "✅" if response.status_code == 200 else "⚠️"
            print(f"  Итерация {i+1}: {elapsed:.3f}s {status_icon}")
        except Exception as e:
            errors += 1
            print(f"  Итерация {i+1}: ❌ Ошибка: {e}")
        
        time.sleep(0.5)
    
    if times:
        return {
            "min": min(times),
            "max": max(times),
            "avg": statistics.mean(times),
            "median": statistics.median(times),
            "errors": errors,
            "success_rate": (len(times) / iterations) * 100
        }
    else:
        return {"errors": errors, "success_rate": 0}

def print_results(name: str, results: dict):
    """Красиво выводит результаты"""
    print(f"\n📊 Результаты {name}:")
    print("─" * 40)
    
    if results.get("success_rate", 0) > 0:
        print(f"  ⚡ Минимальное время: {results['min']:.3f}s")
        print(f"  🐌 Максимальное время: {results['max']:.3f}s")
        print(f"  📈 Среднее время: {results['avg']:.3f}s")
        print(f"  📊 Медиана: {results['median']:.3f}s")
        print(f"  ✅ Успешных: {results['success_rate']:.1f}%")
        if results['errors'] > 0:
            print(f"  ❌ Ошибок: {results['errors']}")
    else:
        print(f"  ❌ Все запросы завершились с ошибкой")

def save_results(results: dict, filename: str):
    """Сохраняет результаты в файл"""
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n💾 Результаты сохранены в {filename}")

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 БЕНЧМАРК ПРОИЗВОДИТЕЛЬНОСТИ CRM")
    print("=" * 50)
    
    all_results = {}
    
    # Тест webhook
    webhook_results = benchmark_webhook(iterations=5)
    print_results("Webhook синхронизация", webhook_results)
    all_results["webhook"] = webhook_results
    
    # Тест детальной страницы
    detail_results = benchmark_order_detail(iterations=5)
    print_results("Страница заказа", detail_results)
    all_results["order_detail"] = detail_results
    
    # Тест списка заказов
    list_results = benchmark_orders_list(iterations=5)
    print_results("Список заказов", list_results)
    all_results["orders_list"] = list_results
    
    # Сохраняем результаты
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    save_results(all_results, f"benchmark_before_{timestamp}.json")
    
    print("\n" + "=" * 50)
    print("✅ Бенчмарк завершен!")
    print("=" * 50)