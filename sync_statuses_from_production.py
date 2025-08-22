#!/usr/bin/env python3
"""
Скрипт для синхронизации статусов заказов из продакшен MySQL в Supabase
Получает реальные статусы из cvety.kz и обновляет их в Supabase
"""

import os
import sys
import subprocess
from supabase import create_client, Client
from config import config as app_config

def get_supabase() -> Client:
    """Get Supabase client"""
    url = app_config.SUPABASE_URL
    key = app_config.SUPABASE_ANON_KEY
    return create_client(url, key)

def get_production_order_statuses():
    """
    Получить статусы заказов из продакшен MySQL через SSH
    """
    print("🔗 Подключение к продакшен MySQL...")
    
    # SSH команда для получения статусов активных заказов
    ssh_command = [
        'ssh', 'root@185.125.90.141',
        'mysql -u bitrix -p$(cat /home/bitrix/.mysql_password) bitrix -e "' +
        'SELECT ' +
        'ID as order_id, ' +
        'STATUS_ID as status, ' +
        'DATE_INSERT, ' +
        'USER_ID, ' +
        'PRICE ' +
        'FROM b_sale_order ' +
        'WHERE STATUS_ID IN (\\"N\\", \\"AP\\", \\"DE\\", \\"P\\", \\"CO\\", \\"TR\\", \\"CF\\", \\"RO\\", \\"RD\\", \\"PD\\", \\"KC\\", \\"GP\\") ' +
        'AND DATE_INSERT > \\"2025-08-20\\" ' +
        'ORDER BY DATE_INSERT DESC ' +
        'LIMIT 50;' +
        '"'
    ]
    
    try:
        result = subprocess.run(ssh_command, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            print(f"❌ Ошибка SSH: {result.stderr}")
            return None
            
        # Парсим результат MySQL
        lines = result.stdout.strip().split('\n')
        if len(lines) < 2:
            print("❌ Нет данных из MySQL")
            return None
            
        # Первая строка - заголовки, пропускаем
        headers = lines[0].split('\t')
        orders = []
        
        for line in lines[1:]:
            if line.strip():
                values = line.split('\t')
                if len(values) >= 5:
                    order_data = {
                        'order_id': values[0],
                        'status': values[1],
                        'date_insert': values[2],
                        'user_id': values[3],
                        'price': values[4]
                    }
                    orders.append(order_data)
        
        print(f"✅ Получено {len(orders)} заказов из продакшена")
        return orders
        
    except subprocess.TimeoutExpired:
        print("❌ Таймаут подключения к продакшену")
        return None
    except Exception as e:
        print(f"❌ Ошибка при получении данных: {e}")
        return None

def update_supabase_statuses(production_orders):
    """
    Обновить статусы в Supabase на основе данных из продакшена
    """
    if not production_orders:
        print("❌ Нет данных для обновления")
        return
        
    db = get_supabase()
    
    print(f"🔄 Обновление статусов в Supabase...")
    
    # Получаем mapping из prodaction order ID в Supabase order
    updated_count = 0
    
    for prod_order in production_orders:
        bitrix_order_id = int(prod_order['order_id'])
        real_status = prod_order['status']
        
        try:
            # Ищем заказ в Supabase по bitrix_order_id
            supabase_orders = db.table('orders')\
                .select('id, order_number, status')\
                .eq('bitrix_order_id', bitrix_order_id)\
                .execute()
            
            if supabase_orders.data:
                supabase_order = supabase_orders.data[0]
                current_status = supabase_order['status']
                
                if current_status != real_status:
                    # Обновляем статус
                    update_result = db.table('orders')\
                        .update({'status': real_status})\
                        .eq('id', supabase_order['id'])\
                        .execute()
                    
                    if update_result.data:
                        print(f"  ✅ Заказ {bitrix_order_id}: {current_status} → {real_status}")
                        updated_count += 1
                    else:
                        print(f"  ❌ Не удалось обновить заказ {bitrix_order_id}")
                else:
                    print(f"  ℹ️  Заказ {bitrix_order_id}: статус уже правильный ({real_status})")
            else:
                print(f"  ⚠️  Заказ {bitrix_order_id} не найден в Supabase")
                
        except Exception as e:
            print(f"  ❌ Ошибка при обновлении заказа {bitrix_order_id}: {e}")
    
    print(f"\n🎉 Обновлено {updated_count} заказов")

def show_comparison():
    """
    Показать сравнение статусов до и после обновления
    """
    db = get_supabase()
    
    print("\n📊 Текущие статусы в Supabase (недавние заказы):")
    
    # Получаем недавние заказы с bitrix_order_id
    recent_orders = db.table('orders')\
        .select('bitrix_order_id, order_number, status, created_at')\
        .not_.is_('bitrix_order_id', 'null')\
        .gte('created_at', '2025-08-20')\
        .order('created_at', desc=True)\
        .limit(20)\
        .execute()
    
    if recent_orders.data:
        for order in recent_orders.data:
            bitrix_id = order.get('bitrix_order_id', 'N/A')
            status = order.get('status', 'N/A')
            order_num = order.get('order_number', 'N/A')
            created = order.get('created_at', '')[:16] if order.get('created_at') else 'N/A'
            
            print(f"  • {bitrix_id} ({order_num}) - {status} - {created}")

if __name__ == "__main__":
    print("🔄 Синхронизация статусов заказов из продакшена")
    print("=" * 60)
    
    # Показать текущее состояние
    show_comparison()
    
    print("\n" + "=" * 60)
    
    # Получить данные из продакшена
    production_orders = get_production_order_statuses()
    
    if production_orders:
        print("\n📋 Статусы из продакшена:")
        for order in production_orders[:10]:  # Показать первые 10
            print(f"  • {order['order_id']} - {order['status']} - {order['date_insert']}")
        
        if len(production_orders) > 10:
            print(f"  ... и еще {len(production_orders) - 10} заказов")
        
        # Обновить в Supabase
        print("\n" + "=" * 60)
        update_supabase_statuses(production_orders)
        
        # Показать результат
        print("\n" + "=" * 60)
        show_comparison()
    else:
        print("❌ Не удалось получить данные из продакшена")