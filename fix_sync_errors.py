#!/usr/bin/env python3
"""
Скрипт для исправления ошибок синхронизации с датами
Находит и исправляет ошибки типа 'date/time field value out of range'
"""

import os
import sys
import json
from datetime import datetime
from supabase import create_client
from transformers.order_transformer import OrderTransformer
from webhook_handler import WebhookHandler
from telegram_notifier import send_sync_result_notification
import asyncio
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

class SyncErrorFixer:
    """Класс для исправления ошибок синхронизации"""
    
    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            raise ValueError("Supabase credentials not found in environment")
        
        self.supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        self.transformer = OrderTransformer()
        
    def get_date_errors(self, limit: int = 50):
        """
        Получает ошибки связанные с датами
        
        Args:
            limit: Максимальное количество ошибок для обработки
            
        Returns:
            Список ошибок с датами
        """
        try:
            # Ищем ошибки с датами в sync_log
            result = self.supabase.table('sync_log')\
                .select('*')\
                .eq('status', 'error')\
                .like('error_message', '%date/time field value out of range%')\
                .order('created_at', desc=True)\
                .limit(limit)\
                .execute()
            
            return result.data
            
        except Exception as e:
            print(f"❌ Ошибка получения списка ошибок: {e}")
            return []
    
    def extract_bitrix_id_from_error(self, error_log: dict) -> str:
        """Извлекает Bitrix ID из лога ошибки"""
        try:
            # Проверяем bitrix_id в логе
            if error_log.get('bitrix_id'):
                return str(error_log['bitrix_id'])
            
            # Ищем в payload
            payload = error_log.get('payload', {})
            if payload:
                return str(payload.get('order_id') or payload.get('ID', ''))
            
            return None
            
        except Exception as e:
            print(f"⚠️  Не удалось извлечь Bitrix ID из ошибки: {e}")
            return None
    
    def fix_order_dates(self, bitrix_order_data: dict) -> dict:
        """
        Исправляет формат дат в данных заказа
        
        Args:
            bitrix_order_data: Оригинальные данные заказа из Bitrix
            
        Returns:
            Данные с исправленными датами
        """
        try:
            # Преобразуем заказ через улучшенный трансформер
            fixed_order = self.transformer.transform_bitrix_to_supabase(bitrix_order_data)
            
            # Дополнительная валидация дат
            date_fields = ['created_at', 'updated_at', 'delivery_date']
            for field in date_fields:
                if field in fixed_order and fixed_order[field]:
                    try:
                        # Проверяем, что дата валидна
                        if isinstance(fixed_order[field], str):
                            test_date = datetime.fromisoformat(fixed_order[field].replace('Z', '+00:00'))
                            
                            # Для delivery_date берем только дату
                            if field == 'delivery_date':
                                fixed_order[field] = test_date.date().isoformat()
                            else:
                                fixed_order[field] = test_date.isoformat()
                                
                    except (ValueError, TypeError):
                        print(f"⚠️  Удаляем невалидную дату {field}: {fixed_order[field]}")
                        if field == 'delivery_date':
                            fixed_order[field] = None
                        else:
                            fixed_order[field] = datetime.now().isoformat()
            
            return fixed_order
            
        except Exception as e:
            print(f"❌ Ошибка исправления дат: {e}")
            return None
    
    async def retry_failed_sync(self, error_log: dict) -> bool:
        """
        Повторяет синхронизацию с исправленными датами
        
        Args:
            error_log: Лог ошибки из sync_log
            
        Returns:
            True если синхронизация успешна
        """
        try:
            # Извлекаем оригинальные данные
            payload = error_log.get('payload', {})
            if not payload:
                print(f"❌ Нет данных для повтора синхронизации")
                return False
            
            bitrix_order_id = self.extract_bitrix_id_from_error(error_log)
            if not bitrix_order_id:
                print(f"❌ Не удалось найти Bitrix Order ID")
                return False
            
            print(f"🔄 Повторяем синхронизацию заказа {bitrix_order_id}...")
            
            # Исправляем данные
            fixed_order = self.fix_order_dates(payload)
            if not fixed_order:
                return False
            
            # Проверяем, существует ли заказ в Supabase
            existing_order = self.supabase.table('orders')\
                .select('id')\
                .eq('bitrix_order_id', int(bitrix_order_id))\
                .execute()
            
            if existing_order.data:
                # Обновляем существующий заказ
                result = self.supabase.table('orders')\
                    .update(fixed_order)\
                    .eq('bitrix_order_id', int(bitrix_order_id))\
                    .execute()
                
                action = 'fix_update'
            else:
                # Создаем новый заказ
                result = self.supabase.table('orders').insert(fixed_order).execute()
                action = 'fix_create'
            
            if result.data:
                print(f"✅ Заказ {bitrix_order_id} успешно синхронизирован ({action})")
                
                # Логируем успешное исправление
                self.supabase.table('sync_log').insert({
                    'action': f'{action}_success',
                    'direction': 'error_fix',
                    'bitrix_id': bitrix_order_id,
                    'status': 'success',
                    'payload': payload,
                    'created_at': datetime.now().isoformat()
                }).execute()
                
                # Отправляем уведомление
                await send_sync_result_notification(
                    order_data=payload,
                    status='success',
                    action=f'error_fix_{action}'
                )
                
                return True
            else:
                print(f"❌ Не удалось сохранить заказ {bitrix_order_id}")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка повтора синхронизации: {e}")
            return False
    
    async def fix_all_date_errors(self, max_errors: int = 20, dry_run: bool = False):
        """
        Исправляет все ошибки с датами
        
        Args:
            max_errors: Максимальное количество ошибок для исправления
            dry_run: Если True, только показывает что будет исправлено без реальных изменений
        """
        print(f"🔍 Поиск ошибок с датами (лимит: {max_errors})...")
        
        date_errors = self.get_date_errors(max_errors)
        if not date_errors:
            print("✅ Ошибки с датами не найдены!")
            return
        
        print(f"📝 Найдено {len(date_errors)} ошибок с датами")
        
        if dry_run:
            print("\n🔍 DRY RUN - Показываем что будет исправлено:")
            for i, error in enumerate(date_errors, 1):
                bitrix_id = self.extract_bitrix_id_from_error(error)
                error_msg = error.get('error_message', '')[:100]
                created_at = error.get('created_at', '')[:19]
                print(f"  {i}. Заказ {bitrix_id} | {created_at} | {error_msg}...")
            return
        
        fixed_count = 0
        failed_count = 0
        
        print(f"\n🚀 Начинаем исправление {len(date_errors)} ошибок...")
        
        for i, error in enumerate(date_errors, 1):
            bitrix_id = self.extract_bitrix_id_from_error(error)
            print(f"\n[{i}/{len(date_errors)}] Исправляем заказ {bitrix_id}...")
            
            try:
                if await self.retry_failed_sync(error):
                    fixed_count += 1
                else:
                    failed_count += 1
                    
            except Exception as e:
                print(f"❌ Критическая ошибка при исправлении заказа {bitrix_id}: {e}")
                failed_count += 1
            
            # Пауза между запросами
            await asyncio.sleep(0.5)
        
        print(f"\n📊 РЕЗУЛЬТАТ ИСПРАВЛЕНИЯ:")
        print(f"✅ Исправлено: {fixed_count}")
        print(f"❌ Не удалось исправить: {failed_count}")
        print(f"📈 Success rate: {(fixed_count / len(date_errors) * 100):.1f}%")
        
        # Отправляем сводку в Telegram
        try:
            summary_data = {
                'order_number': 'BATCH_FIX',
                'total_amount': 0
            }
            await send_sync_result_notification(
                order_data=summary_data,
                status='success',
                action=f'batch_fix_{fixed_count}_of_{len(date_errors)}'
            )
        except:
            pass


async def main():
    """Главная функция"""
    print("🔧 Fix Sync Errors - Исправление ошибок синхронизации дат")
    print("=" * 60)
    
    try:
        fixer = SyncErrorFixer()
        
        # Получаем аргументы командной строки
        dry_run = '--dry-run' in sys.argv
        max_errors = 20
        
        if '--max' in sys.argv:
            try:
                max_idx = sys.argv.index('--max')
                max_errors = int(sys.argv[max_idx + 1])
            except (ValueError, IndexError):
                print("⚠️  Неверный формат --max, используем 20")
        
        await fixer.fix_all_date_errors(max_errors, dry_run)
        
    except KeyboardInterrupt:
        print("\n❌ Прервано пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("\n🚀 Использование:")
    print("  python3 fix_sync_errors.py                 # Исправить до 20 ошибок")
    print("  python3 fix_sync_errors.py --max 50        # Исправить до 50 ошибок")
    print("  python3 fix_sync_errors.py --dry-run       # Показать что будет исправлено")
    print("")
    
    asyncio.run(main())