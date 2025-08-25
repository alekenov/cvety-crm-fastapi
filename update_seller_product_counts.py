#!/usr/bin/env python3
"""
Скрипт для обновления количества товаров у каждого продавца в description
Временное решение пока не создана RPC функция
"""

from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")

def update_product_counts():
    """Обновить количество товаров в описании каждого продавца"""
    
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    print("Получаем всех продавцов...")
    sellers_result = supabase.table('sellers').select('id, name, description').execute()
    
    if not sellers_result.data:
        print("Продавцы не найдены")
        return
    
    sellers = sellers_result.data
    print(f"Найдено {len(sellers)} продавцов")
    
    updated_count = 0
    
    # Для каждого продавца обновляем количество товаров
    for i, seller in enumerate(sellers):
        if i % 50 == 0:
            print(f"Обработано: {i}/{len(sellers)}")
        
        # Подсчитываем товары
        count_result = supabase.table('products')\
            .select('id', count='exact')\
            .eq('seller_id', seller['id'])\
            .execute()
        
        product_count = count_result.count if hasattr(count_result, 'count') else 0
        
        # Обновляем описание с количеством товаров
        new_description = f"Товаров: {product_count}"
        if seller.get('description'):
            # Если есть описание, добавляем к нему
            if 'Товаров:' not in seller['description']:
                new_description = f"{seller['description']} | Товаров: {product_count}"
            else:
                # Обновляем существующее количество
                import re
                new_description = re.sub(r'Товаров: \d+', f'Товаров: {product_count}', seller['description'])
        
        try:
            # Обновляем продавца
            supabase.table('sellers')\
                .update({'description': new_description})\
                .eq('id', seller['id'])\
                .execute()
            
            updated_count += 1
            
            if product_count > 0 and updated_count <= 10:
                print(f"  ✅ {seller['name']}: {product_count} товаров")
                
        except Exception as e:
            print(f"  ❌ Ошибка для {seller['name']}: {e}")
    
    print(f"\n✅ Обновлено {updated_count} продавцов")
    
    # Показываем топ продавцов
    print("\n📊 Топ-10 продавцов по количеству товаров:")
    
    # Получаем обновленных продавцов
    sellers_result = supabase.table('sellers').select('name, description').execute()
    
    if sellers_result.data:
        # Извлекаем количество из описания
        sellers_with_counts = []
        for seller in sellers_result.data:
            if seller.get('description') and 'Товаров:' in seller['description']:
                import re
                match = re.search(r'Товаров: (\d+)', seller['description'])
                if match:
                    count = int(match.group(1))
                    if count > 0:
                        sellers_with_counts.append({
                            'name': seller['name'],
                            'count': count
                        })
        
        # Сортируем и показываем топ-10
        sellers_with_counts.sort(key=lambda x: x['count'], reverse=True)
        for i, seller in enumerate(sellers_with_counts[:10], 1):
            print(f"  {i}. {seller['name']}: {seller['count']} товаров")

if __name__ == "__main__":
    print("="*60)
    print("  ОБНОВЛЕНИЕ КОЛИЧЕСТВА ТОВАРОВ")
    print("="*60)
    
    update_product_counts()
    
    print("\n" + "="*60)