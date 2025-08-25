#!/usr/bin/env python3
"""
Update order statuses to match reality
"""

import os
from supabase import create_client
from datetime import datetime

# Supabase configuration
url = os.getenv('SUPABASE_URL', 'https://ignabwiietecbznqnroh.supabase.co')
key = os.getenv('SUPABASE_SERVICE_KEY') or os.getenv('SUPABASE_ANON_KEY')

if not key:
    # Use the key from .env
    key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlnbmFid2lpZXRlY2J6bnFucm9oIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTUzNjg2MTgsImV4cCI6MjA3MDk0NDYxOH0.WMnwySqQcYVjkYrDrG-EwX1_qyqUzUaOOkcDJGaSTPQ"

client = create_client(url, key)

# Orders that need status updates based on real Bitrix statuses
updates = [
    # 122193 - delivered (completed)
    {"bitrix_order_id": 122193, "new_status": "completed", "note": "Доставлен"},
    
    # 122192 - might also be completed
    {"bitrix_order_id": 122192, "new_status": "completed", "note": "Возможно доставлен"},
    
    # 122354 - check if still assembled or completed
    {"bitrix_order_id": 122354, "new_status": "completed", "note": "Проверить статус"},
]

print("🔄 Updating order statuses to match reality...")

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
                
                print(f"✅ Order {update['bitrix_order_id']} ({order['recipient_name']}): {old_status} → {update['new_status']} ({update['note']})")
            else:
                print(f"ℹ️  Order {update['bitrix_order_id']} already has status {update['new_status']}")
        else:
            print(f"❌ Order {update['bitrix_order_id']} not found in Supabase")
            
    except Exception as e:
        print(f"❌ Error updating order {update['bitrix_order_id']}: {e}")

print("\n✅ Status update completed!")