#!/usr/bin/env python3
"""
Унифицированная обратная синхронизация
Supabase → Production Bitrix

Отправляет обновления статусов заказов и другие изменения обратно в Bitrix CMS
Объединяет функциональность sync_back.py и reverse_sync_service.py
"""

import os
import requests
import json
import time
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/reverse_sync.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Конфигурация
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
BITRIX_WEBHOOK_URL = os.getenv("BITRIX_WEBHOOK_URL", "https://cvety.kz/rest/1/webhook_token/")
SYNC_ENABLED = os.getenv("REVERSE_SYNC_ENABLED", "true").lower() == "true"

# Маппинг статусов Supabase → Bitrix
STATUS_MAP = {
    'new': 'N',           # Новый
    'processing': 'P',     # В обработке
    'completed': 'F',      # Выполнен
    'delivered': 'D',      # Доставлен
    'cancelled': 'DN',     # Отменен
    'refunded': 'RF'       # Возврат
}

class UnifiedReverseSync:
    """Унифицированная система обратной синхронизации"""
    
    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            raise ValueError("Supabase credentials not found")
        
        self.supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        self.enabled = SYNC_ENABLED
        self.last_check = datetime.now()
        
        logger.info("Reverse sync service initialized")
    
    def sync_order_status(self, supabase_order_id: str, new_status: str, bitrix_order_id: Optional[int] = None) -> bool:
        """
        Синхронизирует изменение статуса заказа обратно в Bitrix
        
        Args:
            supabase_order_id: UUID заказа в Supabase
            new_status: Новый статус в формате Supabase
            bitrix_order_id: ID заказа в Bitrix (если известен)
            
        Returns:
            True если синхронизация успешна
        """
        if not self.enabled:
            logger.info("Reverse sync disabled")
            return False
        
        try:
            # Получаем bitrix_order_id если не передан
            if not bitrix_order_id:
                order = self.supabase.table('orders')\
                    .select('bitrix_order_id')\
                    .eq('id', supabase_order_id)\
                    .single()\
                    .execute()
                
                if not order.data or not order.data.get('bitrix_order_id'):
                    logger.warning(f"No bitrix_order_id found for Supabase order {supabase_order_id}")
                    return False
                
                bitrix_order_id = order.data['bitrix_order_id']
            
            # Конвертируем статус в формат Bitrix
            bitrix_status = STATUS_MAP.get(new_status, 'N')
            
            # Отправляем обновление в Bitrix
            response = requests.post(
                f"{BITRIX_WEBHOOK_URL}sale.order.update",
                json={
                    'id': bitrix_order_id,
                    'fields': {
                        'STATUS_ID': bitrix_status,
                        'DATE_STATUS': datetime.now().strftime('%d.%m.%Y %H:%M:%S')
                    }
                },
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('result'):
                    logger.info(f"✅ Order {bitrix_order_id} status updated to {bitrix_status}")
                    
                    # Логируем в reverse_sync_log
                    self.supabase.table('reverse_sync_log').insert({
                        'supabase_order_id': supabase_order_id,
                        'bitrix_order_id': bitrix_order_id,
                        'action': 'status_update',
                        'old_status': 'unknown',  # TODO: можно получать из истории
                        'new_status': new_status,
                        'bitrix_status': bitrix_status,
                        'status': 'success',
                        'created_at': datetime.now().isoformat()
                    }).execute()
                    
                    return True
                else:
                    logger.error(f"❌ Bitrix API error: {result.get('error', 'Unknown error')}")
                    return False
            else:
                logger.error(f"❌ HTTP error {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error syncing order status: {e}")
            return False
    
    def get_pending_updates(self, since: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        Получает заказы с обновлениями для синхронизации
        
        Args:
            since: Время с которого искать обновления
            
        Returns:
            Список заказов для синхронизации
        """
        try:
            if not since:
                since = datetime.now() - timedelta(hours=1)
            
            # Ищем заказы, обновленные после последней проверки
            result = self.supabase.table('orders')\
                .select('id, bitrix_order_id, status, updated_at')\
                .gte('updated_at', since.isoformat())\
                .is_('bitrix_order_id', 'not.null')\
                .order('updated_at')\
                .execute()
            
            return result.data or []
            
        except Exception as e:
            logger.error(f"❌ Error getting pending updates: {e}")
            return []
    
    def sync_batch_updates(self, max_orders: int = 50) -> Dict[str, int]:
        """
        Синхронизирует пакет обновлений
        
        Args:
            max_orders: Максимальное количество заказов для обработки
            
        Returns:
            Статистика синхронизации
        """
        logger.info("Starting batch reverse sync...")
        
        pending_orders = self.get_pending_updates(since=self.last_check)
        if not pending_orders:
            logger.info("No pending updates found")
            return {'processed': 0, 'successful': 0, 'failed': 0}
        
        # Ограничиваем количество
        if len(pending_orders) > max_orders:
            pending_orders = pending_orders[:max_orders]
            logger.info(f"Limited to {max_orders} orders")
        
        successful = 0
        failed = 0
        
        for order in pending_orders:
            try:
                if self.sync_order_status(
                    order['id'], 
                    order['status'], 
                    order['bitrix_order_id']
                ):
                    successful += 1
                else:
                    failed += 1
                    
                # Пауза между запросами
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"❌ Error processing order {order['id']}: {e}")
                failed += 1
        
        self.last_check = datetime.now()
        
        stats = {
            'processed': len(pending_orders),
            'successful': successful,
            'failed': failed,
            'success_rate': (successful / len(pending_orders) * 100) if pending_orders else 0
        }
        
        logger.info(f"Batch sync completed: {stats}")
        return stats
    
    async def run_continuous_sync(self, interval_seconds: int = 300):
        """
        Запускает непрерывную синхронизацию с интервалом
        
        Args:
            interval_seconds: Интервал между проверками в секундах
        """
        logger.info(f"Starting continuous reverse sync (interval: {interval_seconds}s)")
        
        while True:
            try:
                stats = self.sync_batch_updates()
                
                if stats['processed'] > 0:
                    logger.info(f"📊 Sync stats: {stats['successful']}/{stats['processed']} successful")
                
                await asyncio.sleep(interval_seconds)
                
            except KeyboardInterrupt:
                logger.info("Stopping continuous sync...")
                break
            except Exception as e:
                logger.error(f"❌ Error in continuous sync: {e}")
                await asyncio.sleep(60)  # Пауза при ошибке
    
    def health_check(self) -> Dict[str, Any]:
        """
        Проверка состояния обратной синхронизации
        
        Returns:
            Информация о состоянии системы
        """
        try:
            # Проверяем подключение к Supabase
            test_query = self.supabase.table('orders').select('id').limit(1).execute()
            supabase_ok = len(test_query.data) >= 0
            
            # Проверяем подключение к Bitrix
            bitrix_ok = False
            try:
                response = requests.get(f"{BITRIX_WEBHOOK_URL}app.info", timeout=5)
                bitrix_ok = response.status_code == 200
            except:
                pass
            
            # Статистика за последний час
            hour_ago = datetime.now() - timedelta(hours=1)
            recent_syncs = self.supabase.table('reverse_sync_log')\
                .select('status', count='exact')\
                .gte('created_at', hour_ago.isoformat())\
                .execute()
            
            return {
                'enabled': self.enabled,
                'supabase_connection': 'ok' if supabase_ok else 'error',
                'bitrix_connection': 'ok' if bitrix_ok else 'error',
                'recent_syncs': recent_syncs.count,
                'last_check': self.last_check.isoformat(),
                'status': 'healthy' if (supabase_ok and self.enabled) else 'degraded'
            }
            
        except Exception as e:
            logger.error(f"❌ Health check error: {e}")
            return {
                'enabled': self.enabled,
                'status': 'error',
                'error': str(e)
            }


def main():
    """Главная функция для запуска синхронизации"""
    import sys
    
    sync_service = UnifiedReverseSync()
    
    if '--continuous' in sys.argv:
        # Непрерывная синхронизация
        interval = 300  # 5 минут по умолчанию
        if '--interval' in sys.argv:
            try:
                idx = sys.argv.index('--interval')
                interval = int(sys.argv[idx + 1])
            except (ValueError, IndexError):
                pass
        
        asyncio.run(sync_service.run_continuous_sync(interval))
        
    elif '--health' in sys.argv:
        # Проверка состояния
        health = sync_service.health_check()
        print(json.dumps(health, indent=2))
        
    else:
        # Разовая синхронизация
        max_orders = 50
        if '--max' in sys.argv:
            try:
                idx = sys.argv.index('--max')
                max_orders = int(sys.argv[idx + 1])
            except (ValueError, IndexError):
                pass
        
        stats = sync_service.sync_batch_updates(max_orders)
        print(f"📊 Reverse sync completed: {stats}")


if __name__ == "__main__":
    main()