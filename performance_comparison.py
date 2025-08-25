#!/usr/bin/env python3
"""
Сравнение результатов производительности до и после оптимизации
"""
import json
import glob

def load_benchmark_results():
    """Загружает результаты бенчмарков"""
    files = glob.glob("benchmark_before_*.json")
    
    if len(files) < 2:
        print("❌ Недостаточно файлов с результатами бенчмарков")
        return None, None
    
    # Сортируем по времени создания
    files.sort()
    
    # Берем первый (до оптимизации) и последний (после оптимизации)
    with open(files[0], 'r') as f:
        before = json.load(f)
    
    with open(files[-1], 'r') as f:
        after = json.load(f)
    
    return before, after

def compare_results(before, after):
    """Сравнивает результаты и показывает улучшения"""
    
    print("📊 СРАВНЕНИЕ ПРОИЗВОДИТЕЛЬНОСТИ")
    print("=" * 50)
    
    tests = ['webhook', 'order_detail', 'orders_list']
    test_names = {
        'webhook': 'Webhook синхронизация',
        'order_detail': 'Страница заказа', 
        'orders_list': 'Список заказов'
    }
    
    improvements = []
    
    for test in tests:
        if test in before and test in after:
            before_avg = before[test].get('avg', 0)
            after_avg = after[test].get('avg', 0)
            
            if before_avg > 0 and after_avg > 0:
                improvement = ((before_avg - after_avg) / before_avg) * 100
                speed_ratio = before_avg / after_avg
                
                print(f"\n🔍 {test_names[test]}:")
                print(f"  До:       {before_avg:.3f}s")
                print(f"  После:    {after_avg:.3f}s")
                
                if improvement > 0:
                    print(f"  ✅ Улучшение: {improvement:.1f}% (в {speed_ratio:.2f}x быстрее)")
                else:
                    print(f"  ⚠️  Замедление: {abs(improvement):.1f}% (в {1/speed_ratio:.2f}x медленнее)")
                
                improvements.append({
                    'test': test,
                    'improvement_percent': improvement,
                    'speed_ratio': speed_ratio
                })
    
    # Общая статистика
    if improvements:
        avg_improvement = sum(imp['improvement_percent'] for imp in improvements) / len(improvements)
        avg_speed_ratio = sum(imp['speed_ratio'] for imp in improvements) / len(improvements)
        
        print(f"\n📈 ОБЩИЙ РЕЗУЛЬТАТ:")
        print("─" * 30)
        if avg_improvement > 0:
            print(f"✅ Среднее улучшение: {avg_improvement:.1f}%")
            print(f"✅ Среднее ускорение: в {avg_speed_ratio:.2f}x раз")
        else:
            print(f"⚠️ Среднее замедление: {abs(avg_improvement):.1f}%")
    
    return improvements

def show_optimizations():
    """Показывает примененные оптимизации"""
    print(f"\n🛠️ ПРИМЕНЕННЫЕ ОПТИМИЗАЦИИ:")
    print("─" * 40)
    print("1. ✅ N+1 Query Fix: Batch загрузка продуктов")
    print("   - Заменили отдельные запросы на batch .in_('id', product_ids)")
    print("   - Снизили количество запросов к базе данных")
    
    print("2. ✅ In-Memory кэширование:")
    print("   - Добавили SimpleCache с TTL = 5 минут для продуктов")
    print("   - Избегаем повторных запросов к одним и тем же данным")
    
    print("3. ✅ Мониторинг:")
    print("   - /cache/stats - статистика кэша")
    print("   - /cache/clear - очистка кэша")

if __name__ == "__main__":
    before, after = load_benchmark_results()
    
    if before and after:
        improvements = compare_results(before, after)
        show_optimizations()
        
        print(f"\n🎯 ВЫВОДЫ:")
        print("─" * 20)
        if improvements:
            best_improvement = max(improvements, key=lambda x: x['improvement_percent'])
            if best_improvement['improvement_percent'] > 0:
                print(f"✅ Лучший результат: {best_improvement['improvement_percent']:.1f}% улучшение")
                print("✅ Оптимизации работают!")
            else:
                print("⚠️ Необходимы дополнительные оптимизации")
        
        print("💡 Рекомендации для дальнейшего улучшения:")
        print("   - Добавить Redis для distributed кэширования")
        print("   - Реализовать connection pooling для Supabase")
        print("   - Добавить CDN для статических ресурсов")
        print("   - Оптимизировать SQL индексы")
        
    else:
        print("❌ Не удалось загрузить результаты бенчмарков")