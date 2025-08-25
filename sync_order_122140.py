#!/usr/bin/env python3
"""
Script to manually sync order 122140 from Bitrix to Supabase
This order failed to sync on Aug 22 due to webhook errors
"""

import os
import sys
import json
from datetime import datetime
from supabase import create_client
import requests

# Configuration
ORDER_ID = 122140
BITRIX_WEBHOOK_URL = "http://localhost:8001/webhooks/bitrix/order"
WEBHOOK_TOKEN = "fad5fbe4c8a520cf6d5453685b758c7fd9f6681f084be335fcdcd190ad9aaa0e"

def main():
    print(f"🔄 Syncing order {ORDER_ID} from Bitrix to Supabase...")
    
    # Create test webhook payload for order 122140
    webhook_payload = {
        "event": "order.create",
        "token": WEBHOOK_TOKEN,
        "data": {
            "ID": str(ORDER_ID),
            "STATUS_ID": "AP",  # Принят status from screenshot
            "PRICE": "30",
            "CURRENCY": "USD",
            "properties": {
                "nameRecipient": "Получатель заказа 122140",
                "phoneRecipient": "+7 XXX XXX XX XX",
                "addressRecipient": "Рудный",
                "city": "3",  # Рудный city ID
                "data": "2025-08-24",
                "when": "18",  # Узнать время у получателя
                "shopId": "17008"
            },
            "basket": [],
            "user": {
                "ID": "1079",
                "NAME": "ЛАУРА КОСТАНАЯ",
                "EMAIL": "eileen@test.kz"
            }
        }
    }
    
    # Send webhook to local FastAPI
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {WEBHOOK_TOKEN}"
    }
    
    try:
        response = requests.post(
            BITRIX_WEBHOOK_URL,
            json=webhook_payload,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            print(f"✅ Order {ORDER_ID} successfully synced!")
            print(f"Response: {response.json()}")
        else:
            print(f"❌ Failed to sync order {ORDER_ID}")
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Error syncing order: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())