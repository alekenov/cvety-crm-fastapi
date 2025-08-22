#!/usr/bin/env python3
"""
Test script to create a carnation bouquet order and verify flower inventory deduction.
This tests the complete flower inventory management system.
"""

import requests
import json
import time
from datetime import datetime

BASE_URL = "http://localhost:8001"

def get_carnation_inventory():
    """Get current carnation inventory."""
    response = requests.get(f"{BASE_URL}/api/flowers")
    flowers = response.json()
    
    for flower in flowers:
        if "гвоздик" in flower["name"].lower():
            return flower["id"], flower["name"], flower["quantity"]
    return None, None, None

def get_carnation_bouquet():
    """Get the existing carnation bouquet product."""
    product_id = "a6b0abc6-c7b3-42d2-b480-5fffbf36e6f5"  # Known carnation bouquet ID
    
    # Verify the product exists and get its composition
    response = requests.get(f"{BASE_URL}/api/products/{product_id}/composition")
    if response.status_code != 200:
        print(f"❌ Failed to get product composition: {response.text}")
        return None
        
    composition = response.json()
    print(f"✅ Found carnation bouquet product (ID: {product_id})")
    
    for item in composition:
        if "гвоздик" in item["flower_name"].lower():
            print(f"🌸 Composition: {item['amount']} × {item['flower_name']}")
            
    return product_id

def create_test_order(product_id):
    """Create a test order with the carnation bouquet."""
    order_data = {
        "recipient_name": "Тестовый Клиент",
        "recipient_phone": "+7 777 123 4567",
        "delivery_address": "Алматы, ул. Тестовая 123",
        "delivery_date": "2025-08-25",
        "comment": "Тест автоматического списания цветов с инвентаря",
        "total_amount": 12000,
        "delivery_fee": 1500,
        "payment_method": "cash",
        "items": [
            {
                "product_id": product_id,
                "quantity": 1,
                "price": 12000
            }
        ]
    }
    
    response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
    if response.status_code not in [200, 201]:
        print(f"❌ Failed to create order: {response.text}")
        return None
        
    result = response.json()
    if "success" in result and result["success"]:
        order = result["order"]
        print(f"✅ Created order: {order['order_number']} (ID: {order['id']})")
        return order["id"]
    else:
        print(f"❌ Order creation failed: {result}")
        return None

def main():
    print("🧪 Testing Carnation Bouquet Order & Inventory Management")
    print("=" * 60)
    
    # Step 1: Get initial carnation inventory
    carnation_id, carnation_name, initial_quantity = get_carnation_inventory()
    if not carnation_id:
        print("❌ No carnations found in inventory")
        return
        
    print(f"📊 Initial carnation inventory: {initial_quantity}")
    
    # Step 2: Get existing carnation bouquet product
    product_id = get_carnation_bouquet()
    if not product_id:
        print("❌ Failed to find carnation bouquet")
        return
    
    # Step 3: Create test order
    order_id = create_test_order(product_id)
    if not order_id:
        print("❌ Failed to create test order")
        return
    
    # Step 4: Wait a moment for inventory processing
    print("⏳ Waiting for inventory processing...")
    time.sleep(2)
    
    # Step 5: Check inventory after order
    _, _, final_quantity = get_carnation_inventory()
    
    print("\n" + "=" * 60)
    print("📈 INVENTORY MANAGEMENT TEST RESULTS:")
    print(f"🌸 Flower: {carnation_name}")
    print(f"📊 Initial inventory: {initial_quantity}")
    print(f"📦 Order quantity: 15 carnations")
    print(f"📊 Final inventory: {final_quantity}")
    print(f"📉 Expected deduction: {initial_quantity - 15}")
    
    if final_quantity == initial_quantity - 15:
        print("✅ SUCCESS: Inventory automatically deducted correctly!")
        print(f"✅ Carnations reduced from {initial_quantity} → {final_quantity}")
    else:
        print("❌ ERROR: Inventory deduction failed!")
        print(f"❌ Expected: {initial_quantity - 15}, Got: {final_quantity}")
    
    print(f"\n🔗 Order ID: {order_id}")
    print(f"🔗 Product ID: {product_id}")

if __name__ == "__main__":
    main()