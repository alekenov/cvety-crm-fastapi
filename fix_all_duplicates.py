#!/usr/bin/env python3
"""
Агрессивное удаление ВСЕХ дубликатов магазинов
Оставляет только один экземпляр с максимальным количеством товаров
"""

from supabase import create_client
import os
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")

def aggressive_duplicate_removal():
    """Удалить ВСЕ дубликаты, оставив только лучшие версии"""
    
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    print("Получаем всех продавцов с описанием...")
    result = supabase.table('sellers').select('id, name, description').execute()
    
    if not result.data:
        print("Продавцы не найдены")
        return
    
    # Группируем по имени (без учета регистра и пробелов)
    sellers_by_name = defaultdict(list)
    for seller in result.data:
        # Нормализуем имя для сравнения
        normalized_name = seller['name'].strip().lower()
        sellers_by_name[normalized_name].append(seller)
    
    print(f"Уникальных названий: {len(sellers_by_name)}")
    
    total_to_delete = 0
    sellers_to_delete = []
    
    for normalized_name, sellers_list in sellers_by_name.items():
        if len(sellers_list) > 1:
            # Извлекаем количество товаров из описания
            sellers_with_counts = []
            for seller in sellers_list:
                product_count = 0
                if seller.get('description') and 'Товаров:' in seller.get('description', ''):
                    import re
                    match = re.search(r'Товаров: (\d+)', seller['description'])
                    if match:
                        product_count = int(match.group(1))
                
                sellers_with_counts.append({
                    **seller,
                    'product_count': product_count
                })
            
            # Сортируем по количеству товаров
            sellers_with_counts.sort(key=lambda x: x['product_count'], reverse=True)
            
            # Оставляем только первого (с максимальным количеством)
            keeper = sellers_with_counts[0]
            to_delete = sellers_with_counts[1:]
            
            if len(to_delete) > 0:
                print(f"\n'{seller['name']}': {len(sellers_list)} записей")
                print(f"  ✅ Оставляем: {keeper['product_count']} товаров")
                
                for seller in to_delete:
                    print(f"  ❌ Удаляем: {seller['product_count']} товаров")
                    sellers_to_delete.append(seller['id'])
                    total_to_delete += 1
    
    if sellers_to_delete:
        print(f"\n⚠️  Будет удалено {total_to_delete} дубликатов")
        print("Удаляем автоматически...")
        
        deleted_count = 0
        for seller_id in sellers_to_delete:
            try:
                # Удаляем продавца
                supabase.table('sellers')\
                    .delete()\
                    .eq('id', seller_id)\
                    .execute()
                
                deleted_count += 1
            except Exception as e:
                print(f"  ⚠️  Ошибка при удалении: {e}")
        
        print(f"\n✅ Удалено {deleted_count} дубликатов")
    else:
        print("\n✅ Дубликаты не найдены")
    
    # Финальная проверка
    result = supabase.table('sellers').select('id', count='exact').execute()
    total = result.count if hasattr(result, 'count') else 0
    print(f"\n📊 Всего продавцов после очистки: {total}")

if __name__ == "__main__":
    print("="*60)
    print("  АГРЕССИВНОЕ УДАЛЕНИЕ ВСЕХ ДУБЛИКАТОВ")
    print("="*60)
    
    aggressive_duplicate_removal()
    
    print("\n" + "="*60)