#!/usr/bin/env python3
"""
Telegram Notifier для отправки уведомлений о синхронизации
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
import aiohttp
from supabase import create_client
from config import config

logger = logging.getLogger(__name__)

class TelegramNotifier:
    """Класс для отправки Telegram уведомлений"""
    
    # Полный маппинг статусов с эмодзи (обновлено согласно продакшну)
    STATUS_DESCRIPTIONS = {
        # Supabase статусы
        'new': '🆕 Новый',
        'unrealized': '❌ Нереализован',
        'confirmed': '✅ Подтвержден', 
        'paid': '💳 Оплачен',
        'assembled': '📦 Собран',
        'ready_delivery': '🚚 Готов к доставке',
        'ready_pickup': '🏪 Готов к выдаче',
        'in_transit': '🚀 В пути',
        'shipped': '📤 Отгружен',
        'completed': '✅ Выполнен',
        'refunded': '💰 Возврат',
        'unpaid': '💔 Не оплачен',
        'payment_error': '⚠️ Ошибка оплаты',
        'problematic': '🚨 Проблемный',
        'reassemble': '🔄 Пересобрать',
        'waiting_processing': '⏳ Ожидает обработки',
        'waiting_approval': '🤔 Ждем одобрения',
        'waiting_group_buy': '👥 Групповая покупка',
        'auction': '🔨 Аукцион',
        'decide': '🎯 Решить',
        # Kaspi статусы
        'kaspi_waiting_qr': '📱 Kaspi: ждем QR',
        'kaspi_qr_scanned': '📲 Kaspi: QR отсканирован',
        'kaspi_paid': '💳 Kaspi: оплачен',
        'kaspi_payment_error': '⚠️ Kaspi: ошибка оплаты',
        # Cloudpayments статусы
        'cloudpay_authorized': '🔐 CloudPay: авторизован',
        'cloudpay_confirmed': '✅ CloudPay: подтвержден',
        'cloudpay_canceled': '❌ CloudPay: отменен',
        'cloudpay_refunded': '💰 CloudPay: возврат',
        
        # Bitrix статусы (для обратной совместимости)
        'N': '🆕 Новый',
        'UN': '❌ Нереализован',
        'AP': '✅ Подтвержден',
        'PD': '💳 Оплачен',
        'CO': '📦 Собран',
        'RD': '🚚 Готов к доставке',
        'RP': '🏪 Готов к выдаче',
        'DE': '🚀 В пути',
        'DF': '📤 Отгружен',
        'F': '✅ Выполнен',
        'RF': '💰 Возврат',
        'CF': '💔 Не оплачен',
        'ER': '⚠️ Ошибка оплаты',
        'TR': '🚨 Проблемный',
        'RO': '🔄 Пересобрать',
        'DN': '⏳ Ожидает обработки',
        'WA': '🤔 Ждем одобрения',
        'GP': '👥 Групповая покупка',
        'AN': '🔨 Аукцион',
        'CA': '🎯 Решить',
        'KA': '📱 Kaspi: ждем QR',
        'KB': '📲 Kaspi: QR отсканирован',
        'KC': '💳 Kaspi: оплачен',
        'KD': '⚠️ Kaspi: ошибка оплаты',
        'AU': '🔐 CloudPay: авторизован',
        'CP': '✅ CloudPay: подтвержден',
        'AR': '❌ CloudPay: отменен',
        'RR': '💰 CloudPay: возврат'
    }
    
    # Маппинг городов по ID (обновлен после анализа продакшна)
    CITY_NAMES = {
        1: 'Алматы',         # Старый ID Алматы
        2: 'Астана',         # ID Астаны
        357: 'Алматы',       # Реальный ID Алматы в продакшне
        390: 'Костанай',     # ID Костаная
        402: 'Рудный',       # ID Рудного
        420: 'Уральск',      # ID Уральска
        421: 'Усть-Каменогорск',  # ID Усть-Каменогорска
        # Строковые версии
        '1': 'Алматы',
        '2': 'Астана', 
        '357': 'Алматы',
        '390': 'Костанай',
        '402': 'Рудный',
        '420': 'Уральск',
        '421': 'Усть-Каменогорск'
    }
    
    def __init__(self):
        self.bot_token = config.TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None
        self.supabase = None
        
        if config.SUPABASE_URL and config.SUPABASE_ANON_KEY:
            self.supabase = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)
        
        self._session = None
    
    async def _get_session(self):
        """Получить HTTP сессию"""
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def _get_active_users(self, notification_level: str = 'all') -> List[Dict]:
        """Получить список активных пользователей для уведомлений"""
        if not self.supabase:
            return []
        
        try:
            # Получаем пользователей по уровню уведомлений
            if notification_level == 'admin_only':
                query = self.supabase.table('telegram_users')\
                    .select('chat_id, username, first_name, role, notification_level')\
                    .eq('is_active', True)\
                    .eq('role', 'admin')
            elif notification_level == 'errors_only':
                query = self.supabase.table('telegram_users')\
                    .select('chat_id, username, first_name, role, notification_level')\
                    .eq('is_active', True)\
                    .in_('notification_level', ['all', 'errors_only'])
            else:
                query = self.supabase.table('telegram_users')\
                    .select('chat_id, username, first_name, role, notification_level')\
                    .eq('is_active', True)
            
            result = query.execute()
            return result.data if result.data else []
            
        except Exception as e:
            logger.error(f"Error getting active users: {e}")
            return []
    
    async def _send_message(self, chat_id: int, text: str, parse_mode: str = 'HTML') -> bool:
        """Отправить сообщение в конкретный чат"""
        if not self.base_url:
            logger.error("Bot token not configured")
            return False
        
        try:
            session = await self._get_session()
            
            data = {
                'chat_id': chat_id,
                'text': text,
                'parse_mode': parse_mode
            }
            
            async with session.post(f"{self.base_url}/sendMessage", data=data) as response:
                if response.status == 200:
                    return True
                elif response.status == 403:
                    # Пользователь заблокировал бота
                    await self._deactivate_user(chat_id)
                    logger.warning(f"User {chat_id} blocked the bot, deactivating")
                    return False
                else:
                    response_text = await response.text()
                    logger.error(f"Failed to send message to {chat_id}: {response.status} - {response_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error sending message to {chat_id}: {e}")
            return False
    
    async def _deactivate_user(self, chat_id: int):
        """Деактивировать пользователя (когда бот заблокирован)"""
        if not self.supabase:
            return
        
        try:
            self.supabase.table('telegram_users')\
                .update({'is_active': False})\
                .eq('chat_id', chat_id)\
                .execute()
        except Exception as e:
            logger.error(f"Error deactivating user {chat_id}: {e}")
    
    def get_status_description(self, status):
        """Получить описание статуса с эмодзи"""
        if not status:
            return '❓ Неизвестно'
        
        # Сначала ищем точное совпадение
        description = self.STATUS_DESCRIPTIONS.get(status)
        if description:
            return description
            
        # Если не найдено, возвращаем оригинальный статус с предупреждением
        return f'❓ {status}'
    
    def get_city_name(self, city_value):
        """Получить название города по ID или другому значению"""
        if not city_value:
            return 'Не указан'
            
        # Если это уже строка с названием города
        if isinstance(city_value, str) and len(city_value) > 3:
            if any(city_name in city_value for city_name in ['Алматы', 'Астана', 'Костанай', 'Рудный', 'Уральск', 'Усть-Каменогорск']):
                return city_value
        
        # Если это ID города
        city_id = None
        try:
            city_id = int(city_value) if city_value else None
        except (ValueError, TypeError):
            pass
            
        if city_id:
            return self.CITY_NAMES.get(city_id, f'Город ID {city_id}')
            
        # Попробуем по строковому ключу
        return self.CITY_NAMES.get(str(city_value), str(city_value) if city_value else 'Не указан')
    
    def format_order_notification(self, order_data: Dict[str, Any], action: str) -> str:
        """Форматировать уведомление о заказе с улучшенной обработкой данных"""
        
        # Используем правильные поля из Supabase
        order_number = order_data.get('order_number', order_data.get('bitrix_order_id', 'N/A'))
        customer_phone = order_data.get('recipient_phone', '')
        total_amount = order_data.get('total_amount', 0)
        
        # Получаем информацию о городе из разных источников
        city_name = 'Не указан'
        
        # 1. Сначала пробуем получить город из bitrix_city_id
        bitrix_city_id = order_data.get('bitrix_city_id')
        if bitrix_city_id:
            city_name = self.get_city_name(bitrix_city_id)
        
        # 2. Если нет, пробуем из bitrix_data (исходных данных)
        if city_name == 'Не указан' and order_data.get('bitrix_data', {}).get('properties'):
            props = order_data['bitrix_data']['properties']
            city_from_props = props.get('city', props.get('CITY'))
            if city_from_props:
                city_name = self.get_city_name(city_from_props)
        
        # Определяем тип доставки
        # Получаем информацию о самовывозе из metadata (новое поле pickup_order)
        metadata = order_data.get('metadata', {})
        is_self_pickup = metadata.get('pickup_order', metadata.get('is_self_pickup', order_data.get('is_self_pickup', False)))
        
        # Дополнительно проверяем по адресу доставки
        delivery_address = order_data.get('delivery_address', '')
        if delivery_address == 'Самовывоз':
            is_self_pickup = True
            
        delivery_type = 'Самовывоз' if is_self_pickup else 'Доставка'
        
        # Обрабатываем адрес
        address = order_data.get('delivery_address', '')
        if is_self_pickup:
            address = 'Самовывоз'
        elif not address:
            address = 'Не указан'
        
        # Определяем эмодзи и текст действия
        if action == 'status_change':
            emoji = '🔄'
            action_name = 'Статус изменен'
        else:
            action_emoji = {
                'create': '📦',
                'create_order': '📦',
                'update': '🔄',
                'update_existing': '🔄',
                'delete': '❌'
            }
            
            action_text = {
                'create': 'Новый заказ',
                'create_order': 'Новый заказ',
                'update': 'Заказ обновлен',
                'update_existing': 'Заказ обновлен', 
                'delete': 'Заказ удален'
            }
            
            emoji = action_emoji.get(action, '📦')
            action_name = action_text.get(action, 'Изменение заказа')
        
        # Формируем сообщение
        message = f"{emoji} <b>{action_name}</b>\n"
        message += f"🆔 Заказ: #{order_number}\n"
        
        # Показываем изменение статуса
        if action in ('status_change', 'update', 'order.status_change', 'order.update') and order_data.get('previous_status'):
            current_status = order_data.get('status', '')
            previous_status = order_data.get('previous_status', '')
            
            current_desc = self.get_status_description(current_status)
            previous_desc = self.get_status_description(previous_status)
            
            # Убираем эмодзи из описаний для стрелки
            current_clean = current_desc.split(' ', 1)[1] if ' ' in current_desc else current_desc
            previous_clean = previous_desc.split(' ', 1)[1] if ' ' in previous_desc else previous_desc
            
            message += f"📋 Статус: {previous_clean} → {current_clean}\n"
        else:
            # Показываем текущий статус
            current_status = order_data.get('status', '')
            status_desc = self.get_status_description(current_status)
            message += f"📋 Статус: {status_desc}\n"
        
        # Информация о получателе
        if customer_phone and len(customer_phone) > 3:
            # Маскируем телефон для безопасности
            if len(customer_phone) >= 7:
                masked_phone = customer_phone[:4] + '*' * (len(customer_phone) - 7) + customer_phone[-3:]
            else:
                masked_phone = customer_phone
            message += f"👤 Получатель: {masked_phone}\n"
        
        # Информация о доставке
        delivery_icon = "🏪" if is_self_pickup else "🚚"
        message += f"{delivery_icon} Тип: {delivery_type}\n"
        message += f"📍 Город: {city_name}\n"
        
        if not is_self_pickup and address != 'Не указан':
            # Обрезаем адрес если слишком длинный
            short_address = address[:50] + '...' if len(address) > 50 else address
            message += f"🏠 Адрес: {short_address}\n"
        
        # Сумма заказа
        if total_amount and total_amount > 0:
            message += f"💰 Сумма: {total_amount:,.0f} ₸\n"
        
        message += f"✅ Синхронизирован в Supabase\n"
        message += f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        
        return message
    
    def format_product_notification(self, product_data: Dict[str, Any], action: str) -> str:
        """Форматировать уведомление о товаре"""
        product_name = product_data.get('name', 'N/A')
        price = product_data.get('price', 0)
        bitrix_id = product_data.get('metadata', {}).get('bitrix_id', 'N/A')
        
        action_emoji = {
            'create': '🛍',
            'update': '🔄',
            'delete': '❌'
        }
        
        action_text = {
            'create': 'Новый товар',
            'update': 'Товар обновлен',
            'delete': 'Товар удален'
        }
        
        emoji = action_emoji.get(action, '🛍')
        action_name = action_text.get(action, 'Изменение товара')
        
        message = f"{emoji} <b>{action_name}</b>\n"
        message += f"📝 Название: {product_name}\n"
        message += f"💰 Цена: {price:,.0f} ₸\n"
        message += f"🆔 Bitrix ID: {bitrix_id}\n"
        message += f"✅ Синхронизирован в Supabase\n"
        message += f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        
        return message
    
    def format_error_notification(self, error_type: str, error_data: Dict[str, Any]) -> str:
        """Форматировать уведомление об ошибке"""
        entity_id = error_data.get('entity_id', 'N/A')
        error_message = error_data.get('error_message', 'Unknown error')
        
        message = f"⚠️ <b>Ошибка синхронизации</b>\n"
        message += f"📋 Тип: {error_type}\n"
        message += f"🆔 ID: {entity_id}\n"
        message += f"❌ Ошибка: {error_message[:200]}\n"  # Ограничиваем длину
        message += f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        
        return message
    
    async def notify_order_sync(self, order_data: Dict[str, Any], action: str):
        """Уведомление о синхронизации заказа"""
        if not config.TELEGRAM_NOTIFICATIONS_ENABLED:
            return
        
        try:
            # Админы получают все уведомления о заказах
            users = await self._get_active_users('admin_only')
            
            if not users:
                logger.info("No active admin users for order notifications")
                return
            
            message = self.format_order_notification(order_data, action)
            
            # Отправляем всем админам
            sent_count = 0
            for user in users:
                if await self._send_message(user['chat_id'], message):
                    sent_count += 1
            
            logger.info(f"Order notification sent to {sent_count}/{len(users)} admin users")
            
        except Exception as e:
            logger.error(f"Error sending order notification: {e}")
    
    async def notify_product_sync(self, product_data: Dict[str, Any], action: str):
        """Уведомление о синхронизации товара"""
        if not config.TELEGRAM_NOTIFICATIONS_ENABLED:
            return
        
        try:
            # Товары - только для админов (много уведомлений)
            users = await self._get_active_users('admin_only')
            
            if not users:
                logger.info("No active admin users for product notifications")
                return
            
            message = self.format_product_notification(product_data, action)
            
            sent_count = 0
            for user in users:
                if await self._send_message(user['chat_id'], message):
                    sent_count += 1
            
            logger.info(f"Product notification sent to {sent_count}/{len(users)} admin users")
            
        except Exception as e:
            logger.error(f"Error sending product notification: {e}")
    
    async def notify_sync_result(self, order_data: Dict[str, Any], status: str, error: str = None, action: str = 'sync'):
        """
        Уведомление о результате синхронизации (успех или ошибка)
        
        Args:
            order_data: Данные заказа
            status: 'success' или 'error'
            error: Текст ошибки (если есть)
            action: Тип действия ('create', 'update', 'sync')
        """
        if not config.TELEGRAM_NOTIFICATIONS_ENABLED:
            return
            
        try:
            # Для ошибок уведомляем всех активных пользователей
            # Для успехов - только админов (много уведомлений)
            if status == 'error':
                users = await self._get_active_users('errors_only')  # Все кто хочет получать ошибки
            else:
                users = await self._get_active_users('admin_only')   # Только админы для успехов
            
            if not users:
                return
            
            # Формируем сообщение
            if status == 'success':
                order_number = order_data.get('order_number') or order_data.get('ID', 'N/A')
                total_amount = order_data.get('total_amount', 0)
                
                # Короткое успешное уведомление
                message = f"✅ <b>Синхронизация успешна</b>\n"
                message += f"📦 Заказ #{order_number}\n"
                message += f"💰 Сумма: {total_amount:,.0f} ₸\n"
                message += f"🔄 Действие: {action}"
                
            else:
                # Детальное уведомление об ошибке
                order_number = order_data.get('order_number') or order_data.get('ID', 'N/A')
                
                message = f"❌ <b>ОШИБКА СИНХРОНИЗАЦИИ</b>\n"
                message += f"📦 Заказ #{order_number}\n"
                message += f"🔄 Действие: {action}\n"
                message += f"⚠️ Ошибка: <code>{error[:200]}{'...' if len(str(error)) > 200 else ''}</code>\n\n"
                message += f"🕒 Время: {datetime.now().strftime('%H:%M:%S')}"
            
            # Отправляем уведомления
            sent_count = 0
            for user in users:
                if await self._send_message(user['chat_id'], message):
                    sent_count += 1
            
            logger.info(f"Sync result notification ({status}) sent to {sent_count}/{len(users)} users")
            
        except Exception as e:
            logger.error(f"Error sending sync result notification: {e}")
    
    async def notify_error(self, error_type: str, error_data: Dict[str, Any]):
        """Уведомление об ошибке - всем пользователям"""
        if not config.TELEGRAM_NOTIFICATIONS_ENABLED:
            return
        
        try:
            # Ошибки отправляем всем активным пользователям
            users = await self._get_active_users('errors_only')
            
            if not users:
                logger.info("No active users for error notifications")
                return
            
            message = self.format_error_notification(error_type, error_data)
            
            sent_count = 0
            for user in users:
                if await self._send_message(user['chat_id'], message):
                    sent_count += 1
            
            logger.info(f"Error notification sent to {sent_count}/{len(users)} users")
            
        except Exception as e:
            logger.error(f"Error sending error notification: {e}")
    
    async def notify_daily_stats(self):
        """Ежедневная статистика - только админам"""
        if not config.TELEGRAM_NOTIFICATIONS_ENABLED:
            return
        
        try:
            users = await self._get_active_users('admin_only')
            
            if not users or not self.supabase:
                return
            
            # Статистика за сегодня
            today = datetime.now().date()
            today_start = f"{today}T00:00:00Z"
            
            orders_today = self.supabase.table('orders')\
                .select('id, total_amount', count='exact')\
                .gte('created_at', today_start)\
                .execute()
            
            total_amount = sum(float(order.get('total_amount', 0) or 0) for order in orders_today.data)
            
            message = f"📈 <b>Ежедневная статистика</b>\n"
            message += f"📅 {today.strftime('%d.%m.%Y')}\n\n"
            message += f"📦 Новых заказов: {orders_today.count}\n"
            message += f"💰 Сумма: {total_amount:,.0f} ₸\n"
            
            if orders_today.count > 0:
                avg_order = total_amount / orders_today.count
                message += f"📊 Средний чек: {avg_order:,.0f} ₸\n"
            
            message += f"\n🤖 Бот Cvety.kz"
            
            sent_count = 0
            for user in users:
                if await self._send_message(user['chat_id'], message):
                    sent_count += 1
            
            logger.info(f"Daily stats sent to {sent_count}/{len(users)} admin users")
            
        except Exception as e:
            logger.error(f"Error sending daily stats: {e}")
    
    async def close(self):
        """Закрыть сессию"""
        if self._session:
            await self._session.close()
            self._session = None

# Глобальный экземпляр notifier
notifier_instance = None

def get_notifier():
    """Получить экземпляр notifier"""
    global notifier_instance
    if notifier_instance is None:
        notifier_instance = TelegramNotifier()
    return notifier_instance

async def send_order_notification(order_data: Dict[str, Any], action: str):
    """Асинхронная отправка уведомления о заказе"""
    notifier = get_notifier()
    await notifier.notify_order_sync(order_data, action)

async def send_product_notification(product_data: Dict[str, Any], action: str):
    """Асинхронная отправка уведомления о товаре"""
    notifier = get_notifier()
    await notifier.notify_product_sync(product_data, action)

async def send_error_notification(error_type: str, error_data: Dict[str, Any]):
    """Асинхронная отправка уведомления об ошибке"""
    notifier = get_notifier()
    await notifier.notify_error(error_type, error_data)

async def send_sync_result_notification(order_data: Dict[str, Any], status: str, error: str = None, action: str = 'sync'):
    """Асинхронная отправка уведомления о результате синхронизации"""
    notifier = get_notifier()
    await notifier.notify_sync_result(order_data, status, error, action)