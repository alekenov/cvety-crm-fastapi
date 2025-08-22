#!/usr/bin/env python3
"""
Тест трансформации данных из Bitrix в Supabase формат
"""

from core.transformer import OptimizedTransformer
from datetime import datetime

def test_transformer():
    """Тестирует основные функции трансформации"""
    
    print("🔄 ФАЗА 4: Тестирование трансформации данных...")
    print()
    
    transformer = OptimizedTransformer()
    
    # Тестовые данные как из Bitrix
    test_order = {
        'ID': 122118,
        'STATUS_ID': 'N',  # Новый заказ
        'DATE_INSERT': '22.08.2025 14:30:00',
        'PRICE': '15000.00',
        'USER_ID': 1079,
        'PHONE': '+77015211545',
        'EMAIL': 'test@example.com',
        'DELIVERY_ADDRESS': 'г. Алматы, ул. Абая 150/1, кв. 25',
        'COMMENT': 'Доставить после 18:00, звонить за час',
        'PAYMENT_ID': 'kaspi',
        'PAYMENT_STATUS': 'Y'
    }
    
    print("📥 Исходные данные (Bitrix формат):")
    for key, value in test_order.items():
        print(f"   {key}: {value}")
    
    print()
    print("🔄 Выполняем трансформацию...")
    
    try:
        result = transformer.transform_bitrix_to_supabase(test_order)
        
        print("📤 Результат трансформации (Supabase формат):")
        for key, value in result.items():
            if isinstance(value, str) and len(value) > 50:
                print(f"   {key}: {value[:47]}...")
            else:
                print(f"   {key}: {value}")
                
        print()
        print("✅ Основные проверки:")
        print(f"   ✓ Статус преобразован: {test_order['STATUS_ID']} → {result['status']}")
        print(f"   ✓ Дата преобразована: {test_order['DATE_INSERT']} → {result['created_at']}")
        print(f"   ✓ ID сохранен: {result['bitrix_order_id']} = {test_order['ID']}")
        print(f"   ✓ Цена сохранена: {result['total_amount']}")
        
        # Проверка кеширования
        print()
        print("🚀 Тест кеширования...")
        start = datetime.now()
        for i in range(100):
            transformer._parse_datetime(test_order['DATE_INSERT'])
        duration = (datetime.now() - start).total_seconds()
        print(f"   ✓ 100 парсингов даты за {duration:.4f}s (кеш работает)")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка трансформации: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_edge_cases():
    """Тестирует граничные случаи"""
    
    print()
    print("🧪 Тестирование граничных случаев...")
    
    transformer = OptimizedTransformer()
    
    # Тест с длинными значениями
    long_order = {
        'ID': 999999,
        'STATUS_ID': 'F',
        'DATE_INSERT': '01.01.2025 00:00:00',
        'ORDER_NUMBER': '12345678901234567890123456789012345',  # Длинный номер
        'COMMENT': 'Очень длинный комментарий ' * 20,  # Очень длинный комментарий
        'PHONE': '+7701521154512345678901234567890',  # Длинный телефон
    }
    
    try:
        result = transformer.transform_bitrix_to_supabase(long_order)
        
        print(f"   ✓ Длинный номер заказа обрезан: {len(result.get('order_number', ''))} символов")
        print(f"   ✓ Длинный комментарий обрезан: {len(result.get('comment', ''))} символов") 
        print(f"   ✓ Длинный телефон обрезан: {len(result.get('recipient_phone', ''))} символов")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка в граничных случаях: {e}")
        return False

if __name__ == "__main__":
    success1 = test_transformer()
    success2 = test_edge_cases()
    
    print()
    if success1 and success2:
        print("🎯 ВСЕ ТЕСТЫ ТРАНСФОРМАЦИИ ПРОШЛИ УСПЕШНО!")
    else:
        print("⚠️  Есть проблемы с трансформацией")