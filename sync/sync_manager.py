#!/usr/bin/env python3
"""
Унифицированный менеджер синхронизации
Объединяет функционал sync_missing_orders.py и sync_production_order.py

Предоставляет единый интерфейс для всех операций синхронизации:
- Поиск и синхронизация пропущенных заказов
- Прямая синхронизация с production сервера
- Batch операции
- Мониторинг и статистика
"""

import os
import sys
import json
import subprocess
import mysql.connector
import asyncio
from datetime import datetime
from typing import List, Dict, Optional, Any
from supabase import create_client
from dotenv import load_dotenv

# Импорты из core модулей
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from core.transformer import OptimizedTransformer

load_dotenv()

# Конфигурация
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

# MySQL конфигурации
MYSQL_CONFIG_LOCAL = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'cvety123',
    'database': 'cvety_db',
    'charset': 'utf8mb4'
}

PRODUCTION_SERVER = '185.125.90.141'
PRODUCTION_DATABASE = 'dbcvety'

class SyncManager:
    """Унифицированный менеджер синхронизации"""
    
    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            raise ValueError("Supabase credentials not found")
        
        self.supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        self.transformer = OptimizedTransformer()
        self.mysql_conn = None
        
    # ==================== ПОДКЛЮЧЕНИЯ ====================
    
    def connect_to_mysql(self, use_local: bool = True) -> bool:
        """
        Подключение к MySQL (локальной копии или production)
        
        Args:
            use_local: True для локального Docker, False для production
            
        Returns:
            True если подключение успешно
        """
        try:
            if use_local:
                self.mysql_conn = mysql.connector.connect(**MYSQL_CONFIG_LOCAL)
                print("✅ Подключен к локальному MySQL (Docker)")
            else:
                # Подключение к production MySQL через SSH
                mysql_config_prod = {
                    'host': '185.125.90.141',
                    'database': 'dbcvety',
                    'user': 'usercvety',
                    'password': 'QQlPCtTA@z2%mhy',
                    'charset': 'utf8mb4',
                    'autocommit': True,
                    'connection_timeout': 30
                }
                self.mysql_conn = mysql.connector.connect(**mysql_config_prod)
                print("✅ Подключен к production MySQL")
            
            return True
        except Exception as e:
            print(f"❌ Ошибка подключения к MySQL: {e}")
            return False
    
    # ==================== ПОИСК ПРОПУЩЕННЫХ ЗАКАЗОВ ====================
    
    def find_missing_orders(self, id_range_start: int, id_range_end: int) -> List[int]:
        """
        Находит ID заказов, которые есть в MySQL, но отсутствуют в Supabase
        
        Args:
            id_range_start: Начальный ID диапазона
            id_range_end: Конечный ID диапазона
            
        Returns:
            Список пропущенных ID заказов
        """
        try:
            # Получаем синхронизированные ID из Supabase
            supabase_result = self.supabase.table('orders')\
                .select('bitrix_order_id')\
                .gte('bitrix_order_id', id_range_start)\
                .lte('bitrix_order_id', id_range_end)\
                .execute()
            
            synced_ids = {int(row['bitrix_order_id']) for row in supabase_result.data if row['bitrix_order_id']}
            
            # Получаем реальные ID из MySQL
            # Проверяем и создаем соединение если нужно
            if self.mysql_conn is None:
                if not self.connect_to_mysql(use_local=True):
                    print("❌ Не удалось подключиться к MySQL для поиска пропущенных заказов")
                    return []
            
            cursor = self.mysql_conn.cursor()
            cursor.execute("""
                SELECT ID FROM b_sale_order 
                WHERE ID BETWEEN %s AND %s 
                AND LID = 's1'
                ORDER BY ID
            """, (id_range_start, id_range_end))
            
            mysql_ids = {row[0] for row in cursor.fetchall()}
            cursor.close()
            
            # Находим пропущенные
            missing_ids = mysql_ids - synced_ids
            
            print(f"📊 MySQL: {len(mysql_ids)} заказов | Supabase: {len(synced_ids)} | Пропущено: {len(missing_ids)}")
            
            return sorted(list(missing_ids))
            
        except Exception as e:
            print(f"❌ Ошибка поиска пропущенных заказов: {e}")
            return []
    
    # ==================== ПОЛУЧЕНИЕ ДАННЫХ ====================
    
    def get_order_from_mysql(self, order_id: int) -> Optional[Dict]:
        """
        Получает полные данные заказа из локального MySQL
        
        Args:
            order_id: ID заказа в Bitrix
            
        Returns:
            Данные заказа в формате webhook или None
        """
        try:
            # Проверяем и создаем соединение если нужно
            if self.mysql_conn is None:
                if not self.connect_to_mysql(use_local=True):
                    print(f"❌ Не удалось подключиться к MySQL для заказа {order_id}")
                    return None
            
            cursor = self.mysql_conn.cursor(dictionary=True)
            
            # Основные данные заказа
            cursor.execute("""
                SELECT 
                    o.ID,
                    o.ORDER_TOPIC as order_number,
                    o.PRICE as total_amount,
                    o.STATUS_ID as status,
                    o.USER_ID,
                    o.DATE_INSERT as created_at,
                    o.DATE_UPDATE as updated_at,
                    o.CURRENCY,
                    o.COMMENTS
                FROM b_sale_order o
                WHERE o.ID = %s AND o.LID = 's1'
            """, (order_id,))
            
            order = cursor.fetchone()
            if not order:
                return None
            
            # Получаем свойства заказа
            cursor.execute("""
                SELECT 
                    p.CODE,
                    p.NAME,
                    pv.VALUE
                FROM b_sale_order_props_value pv
                JOIN b_sale_order_props p ON p.ID = pv.ORDER_PROPS_ID
                WHERE pv.ORDER_ID = %s
            """, (order_id,))
            
            properties = {}
            for prop in cursor.fetchall():
                if prop['CODE']:
                    properties[prop['CODE']] = {
                        'VALUE': prop['VALUE'] or '',
                        'NAME': prop['NAME'] or ''
                    }
            
            cursor.close()
            
            # Формируем структуру как от webhook
            webhook_data = {
                'ID': str(order['ID']),
                'ACCOUNT_NUMBER': str(order['ID']),
                'PRICE': str(order['total_amount']) if order['total_amount'] else '0',
                'STATUS_ID': order['status'] or 'N',
                'USER_ID': str(order['USER_ID']) if order['USER_ID'] else '0',
                'DATE_INSERT': order['created_at'].isoformat() if order['created_at'] else None,
                'DATE_UPDATE': order['updated_at'].isoformat() if order['updated_at'] else None,
                'CURRENCY': order['CURRENCY'] or 'KZT',
                'COMMENTS': order['COMMENTS'] or '',
                'PROPERTIES': properties
            }
            
            return webhook_data
            
        except Exception as e:
            print(f"❌ Ошибка получения заказа {order_id} из MySQL: {e}")
            return None
    
    def get_order_from_production(self, order_id: int) -> Optional[Dict]:
        """
        Получает заказ напрямую с production сервера через SSH
        
        Args:
            order_id: ID заказа в Bitrix
            
        Returns:
            Данные заказа или None
        """
        try:
            # SQL запрос для получения данных
            query = f"""
            SELECT 
                o.ID,
                o.ORDER_TOPIC as order_number,
                o.PRICE as total_amount,
                o.STATUS_ID as status,
                o.USER_ID,
                o.DATE_INSERT as created_at,
                o.DATE_UPDATE as updated_at,
                o.CURRENCY,
                o.COMMENTS
            FROM b_sale_order o
            WHERE o.ID = {order_id} AND o.LID = 's1'
            """
            
            # Выполняем через SSH
            result = subprocess.run([
                'ssh', f'root@{PRODUCTION_SERVER}',
                f'mysql -e "{query}" {PRODUCTION_DATABASE}'
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                print(f"❌ SSH/MySQL ошибка: {result.stderr}")
                return None
            
            lines = result.stdout.strip().split('\n')
            if len(lines) < 2:
                print(f"❌ Заказ {order_id} не найден на production")
                return None
            
            # Парсим данные
            headers = lines[0].split('\t')
            values = lines[1].split('\t')
            order_data = dict(zip(headers, values))
            
            # Упрощенная структура (без свойств пока)
            webhook_data = {
                'ID': order_data['ID'],
                'ACCOUNT_NUMBER': str(order_data['ID']),
                'PRICE': order_data['total_amount'] if order_data['total_amount'] != 'NULL' else '0',
                'STATUS_ID': order_data['status'] if order_data['status'] != 'NULL' else 'N',
                'USER_ID': order_data['USER_ID'] if order_data['USER_ID'] != 'NULL' else '0',
                'DATE_INSERT': order_data['created_at'] if order_data['created_at'] != 'NULL' else None,
                'DATE_UPDATE': order_data['updated_at'] if order_data['updated_at'] != 'NULL' else None,
                'CURRENCY': order_data['CURRENCY'] if order_data['CURRENCY'] != 'NULL' else 'KZT',
                'COMMENTS': order_data['COMMENTS'] if order_data['COMMENTS'] != 'NULL' else '',
                'PROPERTIES': {}
            }
            
            return webhook_data
            
        except Exception as e:
            print(f"❌ Ошибка получения заказа с production: {e}")
            return None
    
    # ==================== СИНХРОНИЗАЦИЯ ====================
    
    async def sync_single_order(self, order_id: int, source: str = 'local') -> bool:
        """
        Синхронизирует один заказ
        
        Args:
            order_id: ID заказа
            source: Источник данных ('local' или 'production')
            
        Returns:
            True если синхронизация успешна
        """
        try:
            print(f"🔄 Синхронизирую заказ {order_id} ({source})...")
            
            # Получаем данные
            if source == 'local':
                order_data = self.get_order_from_mysql(order_id)
            elif source == 'production':
                order_data = self.get_order_from_production(order_id)
            else:
                raise ValueError(f"Неизвестный источник: {source}")
            
            if not order_data:
                print(f"❌ Заказ {order_id} не найден в {source}")
                return False
            
            # Трансформируем
            supabase_order = self.transformer.transform_bitrix_to_supabase(order_data)
            if not supabase_order:
                print(f"❌ Ошибка трансформации заказа {order_id}")
                return False
            
            # Проверяем существование
            existing = self.supabase.table('orders')\
                .select('id')\
                .eq('bitrix_order_id', order_id)\
                .execute()
            
            if existing.data:
                # Обновляем
                result = self.supabase.table('orders')\
                    .update(supabase_order)\
                    .eq('bitrix_order_id', order_id)\
                    .execute()
                action = 'update'
            else:
                # Создаем
                result = self.supabase.table('orders').insert(supabase_order).execute()
                action = 'create'
            
            if result.data:
                print(f"✅ Заказ {order_id} синхронизирован ({action})")
                
                # Логируем
                self.supabase.table('sync_log').insert({
                    'action': f'manual_{action}',
                    'direction': f'{source}_to_supabase',
                    'bitrix_id': str(order_id),
                    'status': 'success',
                    'payload': order_data,
                    'created_at': datetime.now().isoformat()
                }).execute()
                
                return True
            
            return False
            
        except Exception as e:
            print(f"❌ Ошибка синхронизации заказа {order_id}: {e}")
            return False
    
    async def sync_by_ids(self, order_ids: List[int], source: str = 'local') -> Dict[str, int]:
        """
        Синхронизирует заказы по списку ID
        
        Args:
            order_ids: Список ID заказов
            source: Источник данных
            
        Returns:
            Статистика синхронизации
        """
        print(f"🚀 Синхронизация {len(order_ids)} заказов из {source}...")
        
        successful = 0
        failed = 0
        
        for i, order_id in enumerate(order_ids, 1):
            print(f"[{i}/{len(order_ids)}] ", end="")
            
            if await self.sync_single_order(order_id, source):
                successful += 1
            else:
                failed += 1
            
            # Пауза между запросами
            await asyncio.sleep(0.3)
        
        stats = {
            'total': len(order_ids),
            'successful': successful,
            'failed': failed,
            'success_rate': (successful / len(order_ids) * 100) if order_ids else 0
        }
        
        print(f"\n📊 Результат: {successful}/{len(order_ids)} успешно ({stats['success_rate']:.1f}%)")
        return stats
    
    async def sync_by_range(self, id_start: int, id_end: int, max_orders: int = 50, source: str = 'local') -> Dict[str, int]:
        """
        Синхронизирует заказы по диапазону ID
        
        Args:
            id_start: Начальный ID
            id_end: Конечный ID  
            max_orders: Максимальное количество
            source: Источник данных
            
        Returns:
            Статистика синхронизации
        """
        if source == 'local' and not self.connect_to_mysql(use_local=True):
            print("❌ Не удалось подключиться к MySQL")
            return {'total': 0, 'successful': 0, 'failed': 0, 'success_rate': 0}
        
        try:
            if source == 'local':
                missing_ids = self.find_missing_orders(id_start, id_end)
            else:
                # Для production пока используем весь диапазон
                missing_ids = list(range(id_start, id_end + 1))
            
            if not missing_ids:
                print("✅ Пропущенные заказы не найдены!")
                return {'total': 0, 'successful': 0, 'failed': 0, 'success_rate': 100}
            
            # Ограничиваем количество
            if len(missing_ids) > max_orders:
                print(f"⚠️  Ограничиваем до {max_orders} заказов из {len(missing_ids)} найденных")
                missing_ids = missing_ids[:max_orders]
            
            return await self.sync_by_ids(missing_ids, source)
            
        finally:
            if self.mysql_conn:
                self.mysql_conn.close()
                print("🔌 MySQL соединение закрыто")
    
    # ==================== СТАТИСТИКА И МОНИТОРИНГ ====================
    
    def get_sync_statistics(self) -> Dict[str, Any]:
        """
        Получает статистику синхронизации
        
        Returns:
            Словарь со статистикой
        """
        try:
            # Общее количество заказов
            total_result = self.supabase.table('orders')\
                .select('id', count='exact')\
                .execute()
            
            # Синхронизированные из Bitrix
            bitrix_result = self.supabase.table('orders')\
                .select('id', count='exact')\
                .is_('bitrix_order_id', 'not.null')\
                .execute()
            
            # Статистика за последний час
            hour_ago = datetime.now().replace(microsecond=0) - timedelta(hours=1)
            recent_result = self.supabase.table('sync_log')\
                .select('status', count='exact')\
                .gte('created_at', hour_ago.isoformat())\
                .execute()
            
            # Ошибки за час
            errors_result = self.supabase.table('sync_log')\
                .select('status', count='exact')\
                .eq('status', 'error')\
                .gte('created_at', hour_ago.isoformat())\
                .execute()
            
            return {
                'total_orders': total_result.count,
                'bitrix_orders': bitrix_result.count,
                'sync_coverage': (bitrix_result.count / total_result.count * 100) if total_result.count else 0,
                'recent_syncs': recent_result.count,
                'recent_errors': errors_result.count,
                'success_rate': ((recent_result.count - errors_result.count) / recent_result.count * 100) if recent_result.count else 100
            }
            
        except Exception as e:
            print(f"❌ Ошибка получения статистики: {e}")
            return {}
    
    def health_check(self) -> Dict[str, Any]:
        """
        Проверка здоровья системы синхронизации
        
        Returns:
            Информация о состоянии
        """
        try:
            # Проверяем Supabase
            test_result = self.supabase.table('orders').select('id').limit(1).execute()
            supabase_ok = len(test_result.data) >= 0
            
            # Проверяем локальный MySQL
            mysql_ok = self.connect_to_mysql(use_local=True)
            if self.mysql_conn:
                self.mysql_conn.close()
            
            stats = self.get_sync_statistics()
            
            return {
                'supabase_connection': 'ok' if supabase_ok else 'error',
                'mysql_connection': 'ok' if mysql_ok else 'error',
                'sync_statistics': stats,
                'status': 'healthy' if (supabase_ok and mysql_ok) else 'degraded',
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }


async def main():
    """Главная функция CLI"""
    import sys
    
    manager = SyncManager()
    
    if '--health' in sys.argv:
        # Проверка здоровья
        health = manager.health_check()
        print(json.dumps(health, indent=2, ensure_ascii=False))
        
    elif '--stats' in sys.argv:
        # Статистика
        stats = manager.get_sync_statistics()
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        
    elif '--ids' in sys.argv:
        # Синхронизация по ID
        try:
            idx = sys.argv.index('--ids')
            ids_str = sys.argv[idx + 1]
            order_ids = [int(x.strip()) for x in ids_str.split(',')]
            source = 'production' if '--production' in sys.argv else 'local'
            
            result = await manager.sync_by_ids(order_ids, source)
            print(f"📊 Результат: {json.dumps(result, ensure_ascii=False)}")
            
        except (ValueError, IndexError) as e:
            print(f"❌ Неверный формат --ids: {e}")
            
    elif '--range' in sys.argv:
        # Синхронизация по диапазону
        try:
            range_idx = sys.argv.index('--range')
            range_str = sys.argv[range_idx + 1]
            start_id, end_id = map(int, range_str.split('-'))
            
            max_orders = 50
            if '--max' in sys.argv:
                max_idx = sys.argv.index('--max')
                max_orders = int(sys.argv[max_idx + 1])
            
            source = 'production' if '--production' in sys.argv else 'local'
            
            result = await manager.sync_by_range(start_id, end_id, max_orders, source)
            print(f"📊 Результат: {json.dumps(result, ensure_ascii=False)}")
            
        except (ValueError, IndexError) as e:
            print(f"❌ Неверный формат --range: {e}")
            
    else:
        # Показать справку
        print("""
🔄 Унифицированный менеджер синхронизации

Использование:
  python3 sync/sync_manager.py --health                          # Проверка состояния
  python3 sync/sync_manager.py --stats                           # Статистика
  python3 sync/sync_manager.py --ids 122185,122186               # Конкретные заказы
  python3 sync/sync_manager.py --range 122000-122200 --max 50    # Диапазон заказов
  python3 sync/sync_manager.py --ids 122185 --production         # Из production
  
Источники данных:
  --production    Получать данные с production сервера через SSH
  (по умолчанию)  Использовать локальную копию MySQL
        """)


if __name__ == "__main__":
    asyncio.run(main())