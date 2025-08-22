"""
Webhook handler для приема данных от Bitrix
Обрабатывает входящие webhooks и синхронизирует данные с Supabase
"""

from fastapi import HTTPException, Request, Header, Depends
from supabase import Client
from typing import Optional, Dict, Any
import logging
from datetime import datetime
import json
import hashlib
import hmac
from config import config

logger = logging.getLogger(__name__)

class WebhookHandler:
    """Обработчик webhook запросов от Bitrix"""
    
    def __init__(self, supabase: Client):
        self.supabase = supabase
        self.webhook_token = config.WEBHOOK_TOKEN if hasattr(config, 'WEBHOOK_TOKEN') else 'secret-webhook-token-2024'
    
    def verify_webhook_token(self, token: str) -> bool:
        """Проверка токена webhook для безопасности"""
        return token == self.webhook_token
    
    def verify_webhook_signature(self, payload: str, signature: str) -> bool:
        """Проверка подписи webhook (если Bitrix отправляет HMAC)"""
        expected_signature = hmac.new(
            self.webhook_token.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected_signature, signature)
    
    async def handle_order_webhook(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обработка webhook создания/обновления заказа
        
        Args:
            data: Данные заказа от Bitrix
            
        Returns:
            Результат обработки
        """
        start_time = datetime.now()
        
        try:
            # Извлекаем данные заказа
            bitrix_order_id = data.get('order_id') or data.get('ID')
            if not bitrix_order_id:
                raise ValueError("Order ID not found in webhook data")
            
            # Проверяем, существует ли уже этот заказ
            # Сначала пробуем найти по bitrix_order_id напрямую в orders
            existing_order = self.supabase.table('orders')\
                .select('id')\
                .eq('bitrix_order_id', int(bitrix_order_id))\
                .execute()
            
            if existing_order.data:
                # Заказ уже существует по bitrix_order_id
                existing_mapping_data = [{'supabase_id': existing_order.data[0]['id']}]
            else:
                # Проверяем в таблице маппинга (для обратной совместимости)
                existing_mapping = self.supabase.table('sync_mapping')\
                    .select('*')\
                    .eq('entity_type', 'order')\
                    .eq('bitrix_id', bitrix_order_id)\
                    .execute()
                existing_mapping_data = existing_mapping.data if existing_mapping.data else None
            
            if existing_mapping_data:
                # Заказ уже существует, обновляем
                result = await self._update_existing_order(
                    existing_mapping_data[0]['supabase_id'],
                    data
                )
                action = 'update_order'
            else:
                # Создаем новый заказ
                result = await self._create_new_order(data)
                action = 'create_order'
            
            # Записываем в лог успешную синхронизацию
            processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
            self._log_sync(
                action=action,
                direction='bitrix_to_supabase',
                bitrix_id=bitrix_order_id,
                supabase_id=result.get('order_id'),
                status='success',
                processing_time_ms=processing_time,
                payload=data
            )
            
            # Отправляем уведомление об успешной синхронизации в Telegram
            try:
                from telegram_notifier import send_sync_result_notification
                import asyncio
                asyncio.create_task(send_sync_result_notification(
                    order_data=data,
                    status='success',
                    action=action
                ))
            except Exception as e:
                logger.warning(f"Failed to send success notification: {e}")
            
            return {
                'success': True,
                'action': action,
                'order_id': result.get('order_id'),
                'bitrix_id': bitrix_order_id,
                'processing_time_ms': processing_time
            }
            
        except Exception as e:
            logger.error(f"Error processing order webhook: {e}")
            
            # Логируем ошибку
            processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
            self._log_sync(
                action='order_webhook_error',
                direction='bitrix_to_supabase',
                bitrix_id=data.get('order_id'),
                status='error',
                error_message=str(e),
                processing_time_ms=processing_time,
                payload=data
            )
            
            # Отправляем уведомление об ошибке в Telegram
            try:
                from telegram_notifier import send_sync_result_notification
                import asyncio
                asyncio.create_task(send_sync_result_notification(
                    order_data=data,
                    status='error',
                    error=str(e),
                    action='webhook_processing'
                ))
            except Exception as notification_error:
                logger.warning(f"Failed to send error notification: {notification_error}")
            
            raise HTTPException(status_code=500, detail=str(e))
    
    async def _create_new_order(self, bitrix_data: Dict[str, Any]) -> Dict[str, Any]:
        """Создание нового заказа в Supabase"""
        from transformers.order_transformer import OrderTransformer
        
        transformer = OrderTransformer()
        
        # Трансформируем данные
        supabase_order = transformer.transform_bitrix_to_supabase(bitrix_data)
        
        # ВАЖНО: Дополнительная валидация дат перед сохранением в PostgreSQL
        supabase_order = self._validate_dates(supabase_order)
        
        # Создаем заказ в Supabase
        order_result = self.supabase.table('orders').insert(supabase_order).execute()
        
        if not order_result.data:
            raise Exception("Failed to create order in Supabase")
        
        new_order = order_result.data[0]
        
        # Создаем маппинг
        self.supabase.table('sync_mapping').insert({
            'entity_type': 'order',
            'bitrix_id': bitrix_data.get('order_id') or bitrix_data.get('ID'),
            'supabase_id': new_order['id'],
            'sync_status': 'synced'
        }).execute()
        
        # Обрабатываем товары заказа, если они есть
        if 'items' in bitrix_data or 'basket' in bitrix_data:
            await self._sync_order_items(
                new_order['id'],
                bitrix_data.get('items') or bitrix_data.get('basket', [])
            )
        
        return {'order_id': new_order['id']}
    
    async def _update_existing_order(self, supabase_order_id: str, bitrix_data: Dict[str, Any]) -> Dict[str, Any]:
        """Обновление существующего заказа"""
        from transformers.order_transformer import OrderTransformer
        
        transformer = OrderTransformer()
        
        # Трансформируем только обновляемые поля
        update_data = transformer.transform_bitrix_update(bitrix_data)
        update_data['updated_at'] = datetime.now().isoformat()
        
        # Валидируем даты перед обновлением
        update_data = self._validate_dates(update_data)
        
        # Обновляем заказ
        self.supabase.table('orders')\
            .update(update_data)\
            .eq('id', supabase_order_id)\
            .execute()
        
        # Обновляем маппинг
        self.supabase.table('sync_mapping')\
            .update({
                'last_sync_at': datetime.now().isoformat(),
                'sync_status': 'synced'
            })\
            .eq('entity_type', 'order')\
            .eq('supabase_id', supabase_order_id)\
            .execute()
        
        return {'order_id': supabase_order_id}
    
    async def _sync_order_items(self, order_id: str, bitrix_items: list) -> None:
        """Синхронизация товаров заказа"""
        from transformers.order_transformer import OrderTransformer
        
        transformer = OrderTransformer()
        
        # Удаляем существующие товары (для простоты, можно улучшить)
        self.supabase.table('order_items').delete().eq('order_id', order_id).execute()
        
        # Добавляем новые товары
        for item in bitrix_items:
            order_item = transformer.transform_basket_item(item)
            order_item['order_id'] = order_id
            
            self.supabase.table('order_items').insert(order_item).execute()
    
    async def handle_status_webhook(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обработка webhook изменения статуса заказа
        """
        try:
            bitrix_order_id = data.get('order_id')
            new_status = data.get('status')
            
            if not bitrix_order_id or not new_status:
                raise ValueError("Order ID or status not found in webhook data")
            
            # Находим заказ в маппинге
            mapping = self.supabase.table('sync_mapping')\
                .select('supabase_id')\
                .eq('entity_type', 'order')\
                .eq('bitrix_id', bitrix_order_id)\
                .execute()
            
            if not mapping.data:
                raise ValueError(f"Order mapping not found for Bitrix ID: {bitrix_order_id}")
            
            supabase_order_id = mapping.data[0]['supabase_id']
            
            # Маппинг статусов Bitrix -> Supabase
            status_map = {
                'N': 'new',
                'P': 'processing',
                'F': 'completed',
                'D': 'delivered',
                'DN': 'cancelled'
            }
            
            supabase_status = status_map.get(new_status, 'new')
            
            # Обновляем статус в Supabase
            self.supabase.table('orders')\
                .update({
                    'status': supabase_status,
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('id', supabase_order_id)\
                .execute()
            
            # Логируем успешную синхронизацию
            self._log_sync(
                action='update_status',
                direction='bitrix_to_supabase',
                bitrix_id=bitrix_order_id,
                supabase_id=supabase_order_id,
                status='success',
                payload={'new_status': new_status}
            )
            
            return {
                'success': True,
                'order_id': supabase_order_id,
                'new_status': supabase_status
            }
            
        except Exception as e:
            logger.error(f"Error processing status webhook: {e}")
            
            self._log_sync(
                action='status_webhook_error',
                direction='bitrix_to_supabase',
                bitrix_id=data.get('order_id'),
                status='error',
                error_message=str(e),
                payload=data
            )
            
            raise HTTPException(status_code=500, detail=str(e))
    
    def _log_sync(self, **kwargs):
        """Запись в лог синхронизации"""
        try:
            log_entry = {
                'action': kwargs.get('action'),
                'direction': kwargs.get('direction'),
                'bitrix_id': kwargs.get('bitrix_id'),
                'supabase_id': kwargs.get('supabase_id'),
                'status': kwargs.get('status'),
                'error_message': kwargs.get('error_message'),
                'processing_time_ms': kwargs.get('processing_time_ms'),
                'payload': kwargs.get('payload'),
                'created_at': datetime.now().isoformat()
            }
            
            self.supabase.table('sync_log').insert(log_entry).execute()
            
        except Exception as e:
            logger.error(f"Failed to write sync log: {e}")
    
    def get_sync_statistics(self) -> Dict[str, Any]:
        """Получение статистики синхронизации"""
        try:
            # Последние синхронизации
            recent_syncs = self.supabase.table('sync_log')\
                .select('*')\
                .order('created_at', desc=True)\
                .limit(10)\
                .execute()
            
            # Статистика за последние 24 часа
            from datetime import timedelta
            yesterday = (datetime.now() - timedelta(days=1)).isoformat()
            
            daily_stats = self.supabase.table('sync_log')\
                .select('action, status', count='exact')\
                .gte('created_at', yesterday)\
                .execute()
            
            # Последние ошибки
            recent_errors = self.supabase.table('sync_log')\
                .select('*')\
                .eq('status', 'error')\
                .order('created_at', desc=True)\
                .limit(5)\
                .execute()
            
            return {
                'recent_syncs': recent_syncs.data,
                'daily_count': daily_stats.count,
                'recent_errors': recent_errors.data,
                'last_sync': recent_syncs.data[0] if recent_syncs.data else None
            }
            
        except Exception as e:
            logger.error(f"Failed to get sync statistics: {e}")
            return {
                'error': str(e),
                'recent_syncs': [],
                'daily_count': 0,
                'recent_errors': []
            }
    
    def _validate_dates(self, supabase_order: Dict[str, Any]) -> Dict[str, Any]:
        """
        Валидирует и исправляет форматы дат перед сохранением в PostgreSQL
        
        Args:
            supabase_order: Заказ для проверки
            
        Returns:
            Заказ с валидными датами
        """
        date_fields = ['created_at', 'updated_at', 'delivery_date']
        
        for field in date_fields:
            if field in supabase_order and supabase_order[field]:
                try:
                    # Пробуем распарсить дату
                    if isinstance(supabase_order[field], str):
                        # Проверяем, что дата в правильном формате
                        test_date = datetime.fromisoformat(supabase_order[field].replace('Z', '+00:00'))
                        
                        # Если дата успешно парсится, оставляем как есть
                        # Если поле delivery_date, берем только дату без времени
                        if field == 'delivery_date':
                            supabase_order[field] = test_date.date().isoformat()
                        else:
                            supabase_order[field] = test_date.isoformat()
                            
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid date format for {field}: {supabase_order[field]}, error: {e}")
                    
                    # Убираем невалидные даты вместо того чтобы крашить синхронизацию
                    if field == 'delivery_date':
                        supabase_order[field] = None
                    else:
                        # Для обязательных полей created_at/updated_at используем текущее время
                        supabase_order[field] = datetime.now().isoformat()
                        
                except Exception as e:
                    logger.error(f"Unexpected error validating date {field}: {e}")
                    # Безопасная обработка - убираем проблемное поле
                    if field in ['created_at', 'updated_at']:
                        supabase_order[field] = datetime.now().isoformat()
                    else:
                        supabase_order[field] = None
        
        return supabase_order