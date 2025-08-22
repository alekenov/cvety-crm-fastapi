"""
Трансформер для преобразования данных заказов между Bitrix и Supabase
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)

class OrderTransformer:
    """Преобразование структуры заказов Bitrix <-> Supabase"""
    
    # Маппинг статусов Bitrix -> Supabase
    STATUS_MAP = {
        'N': 'new',           # Новый
        'P': 'processing',    # В обработке
        'F': 'completed',     # Выполнен
        'D': 'delivered',     # Доставлен
        'DN': 'cancelled',    # Отменен
        'DF': 'cancelled',    # Отклонен
    }
    
    # Обратный маппинг Supabase -> Bitrix
    STATUS_MAP_REVERSE = {v: k for k, v in STATUS_MAP.items()}
    
    # Маппинг методов оплаты
    PAYMENT_MAP = {
        '1': 'cash',         # Наличные
        '2': 'card',         # Карта
        '3': 'kaspi',        # Kaspi
        '4': 'transfer',     # Перевод
        'cash': 'cash',
        'card': 'card',
        'kaspi': 'kaspi',
        'transfer': 'transfer'
    }
    
    def transform_bitrix_to_supabase(self, bitrix_order: Dict[str, Any]) -> Dict[str, Any]:
        """
        Преобразует заказ из формата Bitrix в формат Supabase
        
        Args:
            bitrix_order: Данные заказа из Bitrix
            
        Returns:
            Заказ в формате Supabase
        """
        try:
            # Базовые поля заказа
            supabase_order = {
                'order_number': str(bitrix_order.get('ACCOUNT_NUMBER') or bitrix_order.get('ID', ''))[:20],
                'status': self.STATUS_MAP.get(bitrix_order.get('STATUS_ID', 'N'), 'new')[:50],
                'total_amount': float(bitrix_order.get('PRICE', 0)),
                'delivery_fee': float(bitrix_order.get('PRICE_DELIVERY', 0)),
                'discount_amount': float(bitrix_order.get('DISCOUNT_VALUE', 0)),
                'payment_status': ('paid' if bitrix_order.get('PAYED') == 'Y' else 'pending')[:50],
                'source': 'bitrix'[:50],
                'created_at': self._parse_datetime(bitrix_order.get('DATE_INSERT')),
                'updated_at': datetime.now().isoformat()
            }
            
            # Обработка свойств заказа (если переданы)
            if 'properties' in bitrix_order or 'props' in bitrix_order:
                props = bitrix_order.get('properties') or bitrix_order.get('props', {})
                supabase_order.update(self._extract_order_properties(props))
            
            # Обработка пользователя - сохраняем как integer ID
            if 'USER_ID' in bitrix_order:
                supabase_order['bitrix_user_id'] = int(bitrix_order['USER_ID'])
                supabase_order['metadata'] = supabase_order.get('metadata', {})
                supabase_order['metadata']['bitrix_user_id'] = bitrix_order['USER_ID']
            
            # Обработка ответственного
            if 'RESPONSIBLE_ID' in bitrix_order and bitrix_order['RESPONSIBLE_ID']:
                supabase_order['metadata'] = supabase_order.get('metadata', {})
                supabase_order['metadata']['bitrix_responsible_id'] = bitrix_order['RESPONSIBLE_ID']
            
            # Сохраняем оригинальный Bitrix Order ID как integer
            if 'ID' in bitrix_order:
                supabase_order['bitrix_order_id'] = int(bitrix_order['ID'])
            
            # Сохраняем в metadata для обратной совместимости
            supabase_order['metadata'] = supabase_order.get('metadata', {})
            supabase_order['metadata']['bitrix_id'] = bitrix_order.get('ID')
            supabase_order['metadata']['bitrix_status'] = bitrix_order.get('STATUS_ID')
            
            # Комментарии
            if 'USER_DESCRIPTION' in bitrix_order:
                supabase_order['comment'] = bitrix_order['USER_DESCRIPTION']
            
            if 'COMMENTS' in bitrix_order:
                supabase_order['courier_comment'] = bitrix_order['COMMENTS']
            
            # Метод оплаты
            if 'PAY_SYSTEM_ID' in bitrix_order:
                supabase_order['payment_method'] = self.PAYMENT_MAP.get(
                    str(bitrix_order['PAY_SYSTEM_ID']), 
                    'cash'
                )[:50]
            
            return supabase_order
            
        except Exception as e:
            logger.error(f"Error transforming Bitrix order to Supabase: {e}")
            raise
    
    def _extract_order_properties(self, props: Any) -> Dict[str, Any]:
        """
        Извлекает свойства заказа из Bitrix properties
        
        Args:
            props: Свойства заказа (может быть dict или list)
            
        Returns:
            Словарь с извлеченными свойствами
        """
        result = {}
        
        # Если props - это список свойств
        if isinstance(props, list):
            props_dict = {}
            for prop in props:
                if isinstance(prop, dict):
                    code = prop.get('CODE') or prop.get('code')
                    value = prop.get('VALUE') or prop.get('value')
                    if code:
                        props_dict[code] = value
            props = props_dict
        
        # Если props - это словарь
        if isinstance(props, dict):
            # Получатель
            result['recipient_name'] = (props.get('RECIPIENT_NAME') or 
                                      props.get('nameRecipient') or 
                                      props.get('NAME_RECIPIENT', ''))
            
            # Обрабатываем телефон получателя (учитываем самовывоз)
            recipient_phone = (props.get('PHONE') or 
                             props.get('phoneRecipient') or 
                             props.get('PHONE_RECIPIENT', ''))
            
            # Проверяем случай самовывоза: если phoneRecipient = "+7" или пустой
            is_self_pickup = props.get('iWillGet') == 'Y' or recipient_phone in ['+7', '', None]
            
            # Сохраняем информацию о самовывозе в metadata (таблица не содержит колонку is_self_pickup)
            result['metadata'] = result.get('metadata', {})
            result['metadata']['is_self_pickup'] = is_self_pickup
            
            if is_self_pickup:
                # Для самовывоза используем основной телефон заказа
                main_phone = props.get('phone', '')  # Основной телефон заказчика
                result['recipient_phone'] = main_phone if main_phone else recipient_phone
            else:
                result['recipient_phone'] = recipient_phone
            
            # Адрес доставки и город
            delivery_address = (props.get('ADDRESS') or 
                              props.get('addressRecipient') or 
                              props.get('ADDRESS_RECIPIENT', ''))
            
            # Для самовывоза адрес не нужен
            if is_self_pickup:
                result['delivery_address'] = 'Самовывоз'
            else:
                result['delivery_address'] = delivery_address
            
            # Дата и время доставки
            if 'data' in props or 'DATE_DELIVERY' in props:
                result['delivery_date'] = props.get('data') or props.get('DATE_DELIVERY')
            
            if 'when' in props or 'TIME_DELIVERY' in props:
                time_value = props.get('when') or props.get('TIME_DELIVERY')
                
                # Маппинг кодов времени доставки из Bitrix
                time_slots = {
                    '24': '09:00:00',  # Утро
                    '25': '12:00:00',  # День  
                    '26': '15:00:00',  # После обеда
                    '27': '18:00:00',  # Вечер
                    '28': '21:00:00',  # Поздний вечер
                }
                
                # Проверяем, является ли это кодом временного слота
                if str(time_value) in time_slots:
                    result['delivery_time'] = time_slots[str(time_value)]
                elif time_value and ':' in str(time_value):
                    # Это уже время в формате HH:MM или HH:MM:SS
                    if '-' in str(time_value):
                        # Диапазон времени "14:00-16:00"
                        start_time = time_value.split('-')[0].strip()
                        if len(start_time.split(':')) == 2:
                            result['delivery_time'] = f"{start_time}:00"
                        else:
                            result['delivery_time'] = start_time
                    else:
                        # Обычное время
                        if len(str(time_value).split(':')) == 2:
                            result['delivery_time'] = f"{time_value}:00"
                        else:
                            result['delivery_time'] = time_value
                # Если не удалось распознать - не добавляем поле
            
            # Текст открытки
            if 'postcardText' in props or 'POSTCARD_TEXT' in props:
                result['postcard_text'] = props.get('postcardText') or props.get('POSTCARD_TEXT')
            
            # Примечания
            if 'notes' in props or 'NOTES' in props:
                result['courier_comment'] = props.get('notes') or props.get('NOTES')
            
            # Город - сохраняем как integer ID из MySQL
            if 'city' in props or 'CITY' in props:
                city = props.get('city') or props.get('CITY')
                # Маппинг городов на MySQL ID
                # Обновлен после анализа продакшна - найдены реальные ID
                city_map = {
                    'astana': 2,      # Астана в MySQL имеет ID = 2
                    'almaty': 357,    # Алматы в MySQL имеет ID = 357 (исправлено!)
                    'Астана': 2,
                    'Алматы': 357,
                    'Костанай': 390,
                    'Рудный': 402,
                    'Уральск': 420,
                    'Усть-Каменогорск': 421,
                    # Старые ID для обратной совместимости
                    '1': 357,         # Старый ID Алматы -> новый ID Алматы
                    '2': 2,           # ID Астаны
                    '357': 357,       # ID Алматы напрямую
                    '390': 390,       # ID Костанай напрямую  
                    '402': 402,       # ID Рудный напрямую
                    '420': 420,       # ID Уральск напрямую
                    '421': 421,       # ID Усть-Каменогорск напрямую
                    1: 357,
                    2: 2,
                    357: 357,
                    390: 390,
                    402: 402,
                    420: 420,
                    421: 421
                }
                # Если город известен, используем маппинг, иначе сохраняем исходный ID
                if city in city_map:
                    result['bitrix_city_id'] = city_map[city]
                else:
                    # Пытаемся преобразовать в int, если это строка с числом
                    try:
                        result['bitrix_city_id'] = int(city)
                    except (ValueError, TypeError):
                        result['bitrix_city_id'] = 2  # Астана по умолчанию только если не удается распознать
            
            # Сохраняем все свойства в metadata для дебага
            result['metadata'] = result.get('metadata', {})
            result['metadata']['order_properties'] = props
        
        return result
    
    def transform_bitrix_update(self, bitrix_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Преобразует данные для обновления заказа
        
        Args:
            bitrix_data: Частичные данные заказа из Bitrix
            
        Returns:
            Данные для обновления в Supabase
        """
        update_data = {}
        
        # Обновляем только переданные поля
        if 'STATUS_ID' in bitrix_data:
            update_data['status'] = self.STATUS_MAP.get(bitrix_data['STATUS_ID'], 'new')
        
        if 'PRICE' in bitrix_data:
            update_data['total_amount'] = float(bitrix_data['PRICE'])
        
        if 'PAYED' in bitrix_data:
            update_data['payment_status'] = 'paid' if bitrix_data['PAYED'] == 'Y' else 'pending'
        
        if 'RESPONSIBLE_ID' in bitrix_data:
            update_data['metadata'] = update_data.get('metadata', {})
            update_data['metadata']['bitrix_responsible_id'] = bitrix_data['RESPONSIBLE_ID']
        
        if 'USER_DESCRIPTION' in bitrix_data:
            update_data['comment'] = bitrix_data['USER_DESCRIPTION']
        
        if 'COMMENTS' in bitrix_data:
            update_data['courier_comment'] = bitrix_data['COMMENTS']
        
        return update_data
    
    def transform_basket_item(self, bitrix_item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Преобразует товар корзины из Bitrix в order_item для Supabase
        
        Args:
            bitrix_item: Товар из b_sale_basket
            
        Returns:
            order_item для Supabase
        """
        try:
            # Базовая структура товара
            # quantity должен быть integer в Supabase
            qty = bitrix_item.get('QUANTITY', 1)
            if isinstance(qty, str):
                # Конвертируем строку в float, затем в int
                qty = int(float(qty))
            elif isinstance(qty, float):
                qty = int(qty)
            else:
                qty = int(qty) if qty else 1
                
            order_item = {
                'quantity': qty,
                'price': float(bitrix_item.get('PRICE', 0)),
                'total': float(bitrix_item.get('PRICE', 0)) * qty
            }
            
            # Сохраняем Bitrix product ID как integer
            if 'PRODUCT_ID' in bitrix_item:
                order_item['bitrix_product_id'] = int(bitrix_item['PRODUCT_ID'])
            
            # Сохраняем snapshot товара
            order_item['product_snapshot'] = {
                'name': bitrix_item.get('NAME', 'Товар'),
                'bitrix_product_id': bitrix_item.get('PRODUCT_ID'),
                'sku': bitrix_item.get('PRODUCT_XML_ID'),
                'detail_url': bitrix_item.get('DETAIL_PAGE_URL'),
                'discount': float(bitrix_item.get('DISCOUNT_PRICE', 0)),
                'vat_rate': float(bitrix_item.get('VAT_RATE', 0))
            }
            
            # Если есть ID товара в нашей базе
            if 'product_id' in bitrix_item:
                order_item['product_id'] = bitrix_item['product_id']
            
            return order_item
            
        except Exception as e:
            logger.error(f"Error transforming basket item: {e}")
            # Возвращаем минимальную структуру
            return {
                'quantity': 1,
                'price': 0,
                'total': 0,
                'product_snapshot': {
                    'name': 'Товар',
                    'error': str(e)
                }
            }
    
    def transform_supabase_to_bitrix(self, supabase_order: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обратное преобразование из Supabase в формат для Bitrix API
        
        Args:
            supabase_order: Заказ из Supabase
            
        Returns:
            Данные для отправки в Bitrix
        """
        bitrix_data = {
            'STATUS_ID': self.STATUS_MAP_REVERSE.get(supabase_order.get('status'), 'N'),
            'PRICE': supabase_order.get('total_amount', 0),
            'PRICE_DELIVERY': supabase_order.get('delivery_fee', 0),
            'DISCOUNT_VALUE': supabase_order.get('discount_amount', 0),
            'USER_DESCRIPTION': supabase_order.get('comment', ''),
            'COMMENTS': supabase_order.get('courier_comment', '')
        }
        
        # Статус оплаты
        if supabase_order.get('payment_status') == 'paid':
            bitrix_data['PAYED'] = 'Y'
            bitrix_data['DATE_PAYED'] = datetime.now().isoformat()
        
        # Ответственный
        if supabase_order.get('responsible_id'):
            # Нужно будет маппить UUID на Bitrix ID
            metadata = supabase_order.get('metadata', {})
            if 'bitrix_responsible_id' in metadata:
                bitrix_data['RESPONSIBLE_ID'] = metadata['bitrix_responsible_id']
        
        return bitrix_data
    
    def _parse_datetime(self, date_str: Optional[str]) -> str:
        """
        Парсит дату из различных форматов в ISO формат
        
        Args:
            date_str: Строка с датой
            
        Returns:
            Дата в ISO формате
        """
        if not date_str:
            return datetime.now().isoformat()
        
        if isinstance(date_str, datetime):
            return date_str.isoformat()
        
        # Пробуем разные форматы - российский формат в начале (критично!)
        formats = [
            '%d.%m.%Y %H:%M:%S',   # Российский формат из Bitrix (приоритет!)
            '%d.%m.%Y',            # Короткий российский формат
            '%Y-%m-%d %H:%M:%S',   # ISO формат
            '%Y-%m-%dT%H:%M:%S',   # ISO с T
            '%Y-%m-%d',            # Короткий ISO
            '%d/%m/%Y %H:%M:%S',   # Альтернативный формат
            '%m/%d/%Y %H:%M:%S'    # US формат
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(str(date_str), fmt)
                return dt.isoformat()
            except ValueError:
                continue
            except Exception as e:
                logger.debug(f"Unexpected error parsing date {date_str} with format {fmt}: {e}")
                continue
        
        # Если ничего не подошло, логируем более детально и возвращаем текущее время
        logger.error(f"Could not parse date: '{date_str}' (type: {type(date_str)})")
        return datetime.now().isoformat()