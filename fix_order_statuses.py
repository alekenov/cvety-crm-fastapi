#!/usr/bin/env python3
"""
Fix order statuses to match Bitrix reality
"""

import os
from supabase import create_client
from datetime import datetime

# Supabase configuration
url = os.getenv('SUPABASE_URL', 'https://ignabwiietecbznqnroh.supabase.co')
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlnbmFid2lpZXRlY2J6bnFucm9oIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTUzNjg2MTgsImV4cCI6MjA3MDk0NDYxOH0.WMnwySqQcYVjkYrDrG-EwX1_qyqUzUaOOkcDJGaSTPQ"

client = create_client(url, key)

# Correct statuses based on Bitrix screenshot
updates = [
    # 122354 - Should be "assembled" (Собран) not completed
    {"bitrix_order_id": 122354, "new_status": "assembled", "note": "Собран, в пути"},
    
    # 122358 - Keep as "new" (already correct)
    # 122359 - Should be "new" not "confirmed" 
    {"bitrix_order_id": 122359, "new_status": "new", "note": "Новый заказ"},
    
    # Revert the ones we wrongly set to completed
    {"bitrix_order_id": 122193, "new_status": "paid", "note": "Возврат к правильному статусу"},
    {"bitrix_order_id": 122192, "new_status": "DE", "note": "В пути"},
]

print("🔄 Исправляю статусы заказов на правильные...")

for update in updates:
    try:
        # Find order by bitrix_order_id
        result = client.table('orders')\
            .select('id, bitrix_order_id, status, recipient_name')\
            .eq('bitrix_order_id', update['bitrix_order_id'])\
            .execute()
        
        if result.data:
            order = result.data[0]
            old_status = order['status']
            
            if old_status != update['new_status']:
                # Update status
                update_result = client.table('orders')\
                    .update({
                        'status': update['new_status'],
                        'updated_at': datetime.utcnow().isoformat()
                    })\
                    .eq('id', order['id'])\
                    .execute()
                
                print(f"✅ Заказ {update['bitrix_order_id']} ({order['recipient_name']}): {old_status} → {update['new_status']} ({update['note']})")
            else:
                print(f"ℹ️  Заказ {update['bitrix_order_id']} уже имеет статус {update['new_status']}")
        else:
            print(f"❌ Заказ {update['bitrix_order_id']} не найден в Supabase")
            
    except Exception as e:
        print(f"❌ Ошибка при обновлении заказа {update['bitrix_order_id']}: {e}")

print("\n✅ Статусы исправлены!")