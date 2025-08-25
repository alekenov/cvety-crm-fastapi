#!/usr/bin/env python3
"""
Скрипт для удаления дубликатов магазинов в Supabase
Оставляет только один экземпляр каждого магазина с максимальным количеством товаров
"""

from supabase import create_client
import os
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")

def find_and_remove_duplicates():
    """Найти и удалить дубликаты магазинов"""
    
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    print("Получаем всех продавцов...")
    # Получаем всех продавцов
    result = supabase.table('sellers').select('id, name, slug').execute()
    
    if not result.data:
        print("Продавцы не найдены")
        return
    
    # Группируем по имени
    sellers_by_name = defaultdict(list)
    for seller in result.data:
        sellers_by_name[seller['name']].append(seller)
    
    # Находим дубликаты
    duplicates = {name: sellers for name, sellers in sellers_by_name.items() if len(sellers) > 1}
    
    if not duplicates:
        print("✅ Дубликаты не найдены")
        return
    
    print(f"\n❗ Найдено {len(duplicates)} названий с дубликатами:")
    
    total_to_delete = 0
    sellers_to_delete = []
    
    for name, sellers_list in duplicates.items():
        print(f"\n'{name}': {len(sellers_list)} записей")
        
        # Для каждого дубликата проверяем количество товаров
        sellers_with_counts = []
        for seller in sellers_list:
            count_result = supabase.table('products')\
                .select('id', count='exact')\
                .eq('seller_id', seller['id'])\
                .execute()
            
            product_count = count_result.count if hasattr(count_result, 'count') else 0
            sellers_with_counts.append({
                **seller,
                'product_count': product_count
            })
        
        # Сортируем по количеству товаров (по убыванию)
        sellers_with_counts.sort(key=lambda x: x['product_count'], reverse=True)
        
        # Оставляем первого (с максимальным количеством товаров)
        keeper = sellers_with_counts[0]
        to_delete = sellers_with_counts[1:]
        
        print(f"  ✅ Оставляем: ID={keeper['id'][:8]}... ({keeper['product_count']} товаров)")
        
        for seller in to_delete:
            print(f"  ❌ Удаляем: ID={seller['id'][:8]}... ({seller['product_count']} товаров)")
            sellers_to_delete.append(seller['id'])
            total_to_delete += 1
    
    if sellers_to_delete:
        print(f"\n⚠️  Будет удалено {total_to_delete} дубликатов")
        response = input("Продолжить удаление? (yes/no): ")
        
        if response.lower() in ['yes', 'y', 'да']:
            deleted_count = 0
            for seller_id in sellers_to_delete:
                try:
                    # Сначала обнуляем seller_id у товаров
                    supabase.table('products')\
                        .update({'seller_id': None, 'seller_name': None})\
                        .eq('seller_id', seller_id)\
                        .execute()
                    
                    # Удаляем продавца
                    supabase.table('sellers')\
                        .delete()\
                        .eq('id', seller_id)\
                        .execute()
                    
                    deleted_count += 1
                except Exception as e:
                    print(f"  ⚠️  Ошибка при удалении {seller_id}: {e}")
            
            print(f"\n✅ Удалено {deleted_count} дубликатов")
        else:
            print("\n❌ Удаление отменено")
    
    # Проверяем результат
    print("\n📊 Проверка результатов...")
    result = supabase.table('sellers').select('id', count='exact').execute()
    total_sellers = result.count if hasattr(result, 'count') else len(result.data)
    print(f"Всего продавцов после очистки: {total_sellers}")

if __name__ == "__main__":
    print("="*60)
    print("  УДАЛЕНИЕ ДУБЛИКАТОВ МАГАЗИНОВ")
    print("="*60)
    
    find_and_remove_duplicates()
    
    print("\n" + "="*60)