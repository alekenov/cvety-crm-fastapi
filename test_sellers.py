#!/usr/bin/env python3
"""Тест получения продавцов из Supabase"""

from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Получаем продавцов
sellers_result = supabase.table("sellers").select("id, name").limit(10).execute()

print(f"Найдено продавцов: {len(sellers_result.data) if sellers_result.data else 0}")

if sellers_result.data:
    for seller in sellers_result.data[:5]:
        print(f"  - ID: {seller['id']}, Name: {seller['name']}")
        
        # Подсчитаем товары
        count_result = supabase.table("products")\
            .select("id", count="exact")\
            .eq("seller_id", seller['id'])\
            .execute()
        
        count = count_result.count if hasattr(count_result, 'count') else 0
        print(f"    Товаров: {count}")