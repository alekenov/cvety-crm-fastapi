#!/usr/bin/env python3
"""
Скрипт для очистки старых заказов со статусом 'new'
Обновляет заказы старше 30 дней с 'new' на 'completed'
"""

import os
import sys
from datetime import datetime, timedelta
from supabase import create_client, Client
from config import config as app_config

def get_supabase() -> Client:
    """Get Supabase client"""
    url = app_config.SUPABASE_URL
    key = app_config.SUPABASE_ANON_KEY
    return create_client(url, key)

def cleanup_old_new_orders():
    """
    Найти и обновить старые заказы со статусом 'new' на 'completed'
    """
    db = get_supabase()
    
    # Дата 30 дней назад
    thirty_days_ago = datetime.now() - timedelta(days=30)
    cutoff_date = thirty_days_ago.isoformat()
    
    print(f"🔍 Поиск заказов со статусом 'new' старше {thirty_days_ago.strftime('%Y-%m-%d')}...")
    
    # Найти все старые заказы со статусом 'new'
    result = db.table('orders')\
        .select('id, order_number, status, created_at, total_amount')\
        .eq('status', 'new')\
        .lt('created_at', cutoff_date)\
        .execute()
    
    if not result.data:
        print("✅ Старых заказов со статусом 'new' не найдено")
        return
    
    old_orders = result.data
    print(f"📊 Найдено {len(old_orders)} старых заказов со статусом 'new'")
    
    # Показать первые 10 для примера
    print("\n📋 Примеры заказов для обновления:")
    for order in old_orders[:10]:
        order_num = order.get('order_number', f"Order #{order['id'][:8]}")
        created = order.get('created_at', 'Unknown')[:10]
        amount = order.get('total_amount', 0)
        print(f"  • {order_num} - {created} - {amount}₸")
    
    if len(old_orders) > 10:
        print(f"  ... и еще {len(old_orders) - 10} заказов")
    
    # Подтверждение от пользователя
    print(f"\n⚠️  ВНИМАНИЕ: Будет обновлено {len(old_orders)} заказов с 'new' → 'completed'")
    confirm = input("Продолжить? (yes/no): ").lower().strip()
    
    if confirm not in ['yes', 'y', 'да', 'д']:
        print("❌ Операция отменена")
        return
    
    # Обновление заказов пакетами по 100
    batch_size = 100
    updated_count = 0
    
    for i in range(0, len(old_orders), batch_size):
        batch = old_orders[i:i + batch_size]
        order_ids = [order['id'] for order in batch]
        
        print(f"📝 Обновление пакета {i//batch_size + 1} ({len(batch)} заказов)...")
        
        try:
            update_result = db.table('orders')\
                .update({'status': 'completed'})\
                .in_('id', order_ids)\
                .execute()
            
            if update_result.data:
                updated_count += len(update_result.data)
                print(f"✅ Обновлено {len(update_result.data)} заказов в пакете")
            else:
                print(f"⚠️  Пакет не обновлен (возможно, нет изменений)")
                
        except Exception as e:
            print(f"❌ Ошибка при обновлении пакета: {e}")
            continue
    
    print(f"\n🎉 ЗАВЕРШЕНО! Обновлено {updated_count} заказов с 'new' → 'completed'")
    
    # Проверим результат
    check_result = db.table('orders')\
        .select('status', count='exact')\
        .eq('status', 'new')\
        .lt('created_at', cutoff_date)\
        .execute()
    
    remaining_old_new = check_result.count or 0
    if remaining_old_new == 0:
        print("✅ Все старые заказы со статусом 'new' успешно обновлены")
    else:
        print(f"⚠️  Осталось {remaining_old_new} старых заказов со статусом 'new'")

def show_current_status_stats():
    """Показать текущую статистику статусов"""
    db = get_supabase()
    
    print("📊 Текущая статистика статусов заказов:")
    
    # Получить статистику по статусам
    result = db.table('orders')\
        .select('status')\
        .execute()
    
    if result.data:
        status_counts = {}
        for order in result.data:
            status = order['status']
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Сортировка по количеству
        sorted_statuses = sorted(status_counts.items(), key=lambda x: x[1], reverse=True)
        
        for status, count in sorted_statuses:
            print(f"  {status}: {count:,} заказов")
        
        print(f"\nВсего заказов: {len(result.data):,}")

if __name__ == "__main__":
    print("🧹 Скрипт очистки старых заказов")
    print("=" * 50)
    
    # Показать текущую статистику
    show_current_status_stats()
    
    print("\n" + "=" * 50)
    
    # Выполнить очистку
    cleanup_old_new_orders()