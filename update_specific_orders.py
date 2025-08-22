#!/usr/bin/env python3
"""
Обновление статусов для конкретных заказов на основе скриншота
"""

from supabase import create_client, Client
from config import config as app_config

def get_supabase() -> Client:
    """Get Supabase client"""
    url = app_config.SUPABASE_URL
    key = app_config.SUPABASE_ANON_KEY
    return create_client(url, key)

def update_specific_orders():
    """
    Обновить статусы для конкретных заказов на основе скриншота:
    - 122183: должен быть AP (Принят)
    - 122192: должен быть DE (В пути)  
    - 122228-122233: это новые заказы, можно оставить как есть
    """
    db = get_supabase()
    
    # Статусы из скриншота
    order_updates = {
        122183: "AP",  # Принят (розовая кнопка)
        122192: "DE",  # В пути (зеленая кнопка)
    }
    
    print("🔄 Обновление статусов конкретных заказов...")
    
    for bitrix_order_id, new_status in order_updates.items():
        try:
            # Ищем заказ в Supabase
            orders = db.table('orders')\
                .select('id, order_number, status')\
                .eq('bitrix_order_id', bitrix_order_id)\
                .execute()
            
            if orders.data:
                order = orders.data[0]
                current_status = order['status']
                order_number = order['order_number']
                
                if current_status != new_status:
                    # Обновляем статус
                    update_result = db.table('orders')\
                        .update({'status': new_status})\
                        .eq('id', order['id'])\
                        .execute()
                    
                    if update_result.data:
                        print(f"✅ Заказ {bitrix_order_id} ({order_number}): {current_status} → {new_status}")
                    else:
                        print(f"❌ Не удалось обновить заказ {bitrix_order_id}")
                else:
                    print(f"ℹ️  Заказ {bitrix_order_id}: статус уже правильный ({new_status})")
            else:
                print(f"⚠️  Заказ {bitrix_order_id} не найден в Supabase")
                
                # Возможно, нужно создать этот заказ
                print(f"   Попробуем найти заказ с order_number = {bitrix_order_id}")
                orders_by_number = db.table('orders')\
                    .select('id, order_number, status, bitrix_order_id')\
                    .eq('order_number', str(bitrix_order_id))\
                    .execute()
                
                if orders_by_number.data:
                    order = orders_by_number.data[0]
                    print(f"   Найден заказ по номеру: {order}")
                    
                    # Обновляем как bitrix_order_id, так и статус
                    update_result = db.table('orders')\
                        .update({
                            'bitrix_order_id': bitrix_order_id,
                            'status': new_status
                        })\
                        .eq('id', order['id'])\
                        .execute()
                    
                    if update_result.data:
                        print(f"✅ Заказ {bitrix_order_id}: обновлен битрикс ID и статус → {new_status}")
                    else:
                        print(f"❌ Не удалось обновить заказ {bitrix_order_id}")
                
        except Exception as e:
            print(f"❌ Ошибка при обновлении заказа {bitrix_order_id}: {e}")

def show_active_orders():
    """Показать текущие активные заказы"""
    db = get_supabase()
    
    print("\n📊 Текущие активные заказы:")
    
    # Активные статусы
    active_statuses = ["new", "paid", "processing", "AP", "DE", "PD", "CO", "TR", "CF", "RO", "RD", "P", "KC", "GP", "N"]
    
    active_orders = db.table('orders')\
        .select('bitrix_order_id, order_number, status, recipient_name, total_amount, created_at')\
        .in_('status', active_statuses)\
        .order('created_at', desc=True)\
        .limit(20)\
        .execute()
    
    if active_orders.data:
        for order in active_orders.data:
            bitrix_id = order.get('bitrix_order_id', 'N/A')
            status = order.get('status', 'N/A')
            order_num = order.get('order_number', 'N/A')
            recipient = order.get('recipient_name', 'N/A')
            amount = order.get('total_amount', 0)
            created = order.get('created_at', '')[:16] if order.get('created_at') else 'N/A'
            
            print(f"  • {bitrix_id} ({order_num}) - {status} - {recipient} - {amount}₸ - {created}")
    else:
        print("  Активных заказов не найдено")

if __name__ == "__main__":
    print("🎯 Обновление статусов конкретных заказов")
    print("=" * 50)
    
    # Показать текущее состояние
    show_active_orders()
    
    print("\n" + "=" * 50)
    
    # Обновить конкретные заказы
    update_specific_orders()
    
    print("\n" + "=" * 50)
    
    # Показать результат
    show_active_orders()