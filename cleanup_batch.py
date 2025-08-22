#!/usr/bin/env python3
"""
Batch cleanup script - runs automatically without confirmation
Cleans up old orders with 'new' status in batches
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

def cleanup_old_new_orders_batch():
    """
    Automatically clean up old orders with 'new' status
    """
    db = get_supabase()
    
    # Date 30 days ago
    thirty_days_ago = datetime.now() - timedelta(days=30)
    cutoff_date = thirty_days_ago.isoformat()
    
    print(f"🔍 Поиск заказов со статусом 'new' старше {thirty_days_ago.strftime('%Y-%m-%d')}...")
    
    # Find all old orders with 'new' status - limit to 1000 per batch
    result = db.table('orders')\
        .select('id, order_number, status, created_at, total_amount')\
        .eq('status', 'new')\
        .lt('created_at', cutoff_date)\
        .limit(1000)\
        .execute()
    
    if not result.data:
        print("✅ Больше старых заказов со статусом 'new' не найдено")
        return 0
    
    old_orders = result.data
    print(f"📊 Найдено {len(old_orders)} старых заказов со статусом 'new'")
    
    # Show first 5 for example
    print("\n📋 Примеры заказов для обновления:")
    for order in old_orders[:5]:
        order_num = order.get('order_number', f"Order #{order['id'][:8]}")
        created = order.get('created_at', 'Unknown')[:10]
        amount = order.get('total_amount', 0)
        print(f"  • {order_num} - {created} - {amount}₸")
    
    if len(old_orders) > 5:
        print(f"  ... и еще {len(old_orders) - 5} заказов")
    
    # Update orders in batches of 100
    batch_size = 100
    updated_count = 0
    
    print(f"\n🚀 АВТОМАТИЧЕСКОЕ ОБНОВЛЕНИЕ: {len(old_orders)} заказов с 'new' → 'completed'")
    
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
    return updated_count

def show_status_stats():
    """Show current status statistics"""
    db = get_supabase()
    
    print("📊 Текущая статистика статусов заказов:")
    
    result = db.table('orders')\
        .select('status')\
        .execute()
    
    if result.data:
        status_counts = {}
        for order in result.data:
            status = order['status']
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Sort by count
        sorted_statuses = sorted(status_counts.items(), key=lambda x: x[1], reverse=True)
        
        for status, count in sorted_statuses:
            print(f"  {status}: {count:,} заказов")
        
        print(f"\nВсего заказов: {len(result.data):,}")

if __name__ == "__main__":
    print("🧹 Автоматическая очистка старых заказов")
    print("=" * 50)
    
    # Show current stats
    show_status_stats()
    
    print("\n" + "=" * 50)
    
    # Run cleanup in batches until no more old orders
    total_cleaned = 0
    batch_num = 1
    
    while True:
        print(f"\n🔄 ПАКЕТ #{batch_num}")
        cleaned = cleanup_old_new_orders_batch()
        
        if cleaned == 0:
            break
            
        total_cleaned += cleaned
        batch_num += 1
        
        # Safety limit - don't clean more than 10,000 orders at once
        if total_cleaned >= 10000:
            print(f"\n⚠️  Достигнут лимит безопасности: {total_cleaned} заказов")
            break
    
    print(f"\n🏁 ОБЩИЙ ИТОГ: Очищено {total_cleaned} старых заказов")
    
    # Show final stats
    print("\n" + "=" * 50)
    show_status_stats()