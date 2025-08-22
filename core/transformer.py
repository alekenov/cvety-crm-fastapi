"""
Оптимизированный трансформер данных
Унифицированное преобразование между форматами Bitrix ↔ Supabase
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
import json
import re
from functools import lru_cache

logger = logging.getLogger(__name__)

# Константы ограничений полей БД
class FieldLimits:
    ORDER_NUMBER = 20
    STATUS = 50
    PAYMENT_METHOD = 50
    PAYMENT_STATUS = 50
    SOURCE = 50
    RECIPIENT_NAME = 255

# Константы маппинга
class StatusMapping:
    # Полный маппинг всех статусов из продакшна (28 статусов)
    BITRIX_TO_SUPABASE = {
        'N': 'new',               # Новый
        'UN': 'unrealized',       # Нереализован  
        'AP': 'confirmed',        # Подтвержден
        'PD': 'paid',            # Оплачен
        'CO': 'assembled',       # Собран
        'RD': 'ready_delivery',  # Готов к доставке
        'RP': 'ready_pickup',    # Готов к выдаче
        'DE': 'in_transit',      # В пути
        'DF': 'shipped',         # Отгружен
        'F': 'completed',        # Выполнен
        'RF': 'refunded',        # Возврат
        'CF': 'unpaid',          # Не оплачен
        'ER': 'payment_error',   # Ошибка при оплате
        'TR': 'problematic',     # Проблемный
        'RO': 'reassemble',      # Пересобрать заказ
        'DN': 'waiting_processing', # Ожидает обработки
        'WA': 'waiting_approval',    # Ждем одобрения заказчика
        'GP': 'waiting_group_buy',   # Ждем группового закупа
        'AN': 'auction',            # Аукцион
        'CA': 'decide',             # Решить
        # Kaspi статусы
        'KA': 'kaspi_waiting_qr',   # Kaspi ждем сканирования QR
        'KB': 'kaspi_qr_scanned',   # Kaspi отсканирован QR, ждем оплату
        'KC': 'kaspi_paid',         # Kaspi заказ оплачен
        'KD': 'kaspi_payment_error', # Kaspi ошибка оплаты
        # Cloudpayments статусы
        'AU': 'cloudpay_authorized', # Cloudpayments: Авторизован
        'CP': 'cloudpay_confirmed',  # Cloudpayments: Подтверждение оплаты
        'AR': 'cloudpay_canceled',   # Cloudpayments: Отмена авторизованного платежа
        'RR': 'cloudpay_refunded',   # Cloudpayments: Возврат оплаты
    }
    
    # Supabase → Битрикс (обратный маппинг)
    SUPABASE_TO_BITRIX = {v: k for k, v in BITRIX_TO_SUPABASE.items()}

class PaymentMapping:
    METHODS = {
        '1': 'cash',
        '2': 'card', 
        '3': 'kaspi',
        '4': 'transfer',
        'cash': 'cash',
        'card': 'card',
        'kaspi': 'kaspi',
        'transfer': 'transfer'
    }

class OptimizedTransformer:
    """Оптимизированный трансформер с кешированием и валидацией"""
    
    def __init__(self):
        self._date_formats = [
            '%d.%m.%Y %H:%M:%S',   # Российский формат из Bitrix (приоритет!)
            '%d.%m.%Y',            # Короткий российский формат
            '%Y-%m-%d %H:%M:%S',   # ISO формат
            '%Y-%m-%dT%H:%M:%S',   # ISO T формат
            '%Y-%m-%dT%H:%M:%S.%f', # ISO с микросекундами
            '%Y-%m-%d',            # Только дата ISO
        ]
        
        # Кеш для часто используемых преобразований
        self._status_cache = {}
        self._payment_cache = {}
    
    @lru_cache(maxsize=256)
    def _parse_datetime(self, date_str: Optional[str]) -> Optional[str]:
        """
        Кешированный парсер дат с приоритетом для российского формата
        
        Args:
            date_str: Строка с датой
            
        Returns:
            ISO формат даты или None
        """
        if not date_str or date_str in ('NULL', '0000-00-00', '0000-00-00 00:00:00'):
            return None
        
        # Очистка строки
        date_str = str(date_str).strip()
        
        for fmt in self._date_formats:
            try:
                parsed_date = datetime.strptime(date_str, fmt)
                # Проверяем валидность даты
                if parsed_date.year < 1900 or parsed_date.year > 2100:
                    continue
                return parsed_date.isoformat()
            except (ValueError, TypeError):
                continue
        
        logger.warning(f"Не удалось распарсить дату: {date_str}")
        return None
    
    @lru_cache(maxsize=128)
    def _get_status_mapping(self, bitrix_status: str, default: str = 'new') -> str:
        """Кешированный маппинг статусов"""
        return StatusMapping.BITRIX_TO_SUPABASE.get(bitrix_status, default)
    
    @lru_cache(maxsize=64)
    def _get_payment_method(self, payment_id: str, default: str = 'cash') -> str:
        """Кешированный маппинг методов оплаты"""
        return PaymentMapping.METHODS.get(str(payment_id), default)
    
    def _truncate_field(self, value: Any, max_length: int) -> str:
        """
        Обрезает поле до максимальной длины
        
        Args:
            value: Значение поля
            max_length: Максимальная длина
            
        Returns:
            Обрезанная строка
        """
        if not value or value == 'NULL':
            return ''
        
        str_value = str(value).strip()
        if len(str_value) > max_length:
            logger.debug(f"Truncating field from {len(str_value)} to {max_length} chars")
            return str_value[:max_length]
        
        return str_value
    
    def _validate_numeric(self, value: Any, default: float = 0.0) -> float:
        """
        Валидирует и конвертирует числовые значения
        
        Args:
            value: Значение для конверсии
            default: Значение по умолчанию
            
        Returns:
            Валидное число
        """
        if not value or value == 'NULL':
            return default
        
        try:
            # Очищаем от лишних символов
            cleaned = re.sub(r'[^\d.-]', '', str(value))
            if not cleaned:
                return default
            
            result = float(cleaned)
            # Проверяем на разумность
            if result < -1000000 or result > 1000000:
                logger.warning(f"Suspicious numeric value: {result}")
                return default
                
            return result
        except (ValueError, TypeError):
            logger.warning(f"Invalid numeric value: {value}")
            return default
    
    def transform_bitrix_to_supabase(self, bitrix_order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Преобразует заказ из формата Bitrix в формат Supabase
        
        Args:
            bitrix_order: Данные заказа из Bitrix
            
        Returns:
            Заказ в формате Supabase или None при ошибке
        """
        try:
            # Извлекаем базовые данные с валидацией
            order_id = str(bitrix_order.get('ID', ''))
            account_number = str(bitrix_order.get('ACCOUNT_NUMBER') or order_id)
            
            # Базовые поля заказа с ограничениями
            supabase_order = {
                'order_number': self._truncate_field(account_number, FieldLimits.ORDER_NUMBER),
                'status': self._truncate_field(
                    self._get_status_mapping(bitrix_order.get('STATUS_ID', 'N')), 
                    FieldLimits.STATUS
                ),
                'total_amount': self._validate_numeric(bitrix_order.get('PRICE')),
                'delivery_fee': self._validate_numeric(bitrix_order.get('PRICE_DELIVERY')),
                'discount_amount': self._validate_numeric(bitrix_order.get('DISCOUNT_VALUE')),
                'payment_status': self._truncate_field(
                    'paid' if bitrix_order.get('PAYED') == 'Y' else 'pending',
                    FieldLimits.PAYMENT_STATUS
                ),
                'source': self._truncate_field('bitrix', FieldLimits.SOURCE),
                'created_at': self._parse_datetime(bitrix_order.get('DATE_INSERT')),
                'updated_at': datetime.now().isoformat()
            }
            
            # Обработка пользователя
            if 'USER_ID' in bitrix_order and bitrix_order['USER_ID']:
                try:
                    supabase_order['bitrix_user_id'] = int(bitrix_order['USER_ID'])
                except (ValueError, TypeError):
                    logger.warning(f"Invalid USER_ID: {bitrix_order['USER_ID']}")
            
            # Сохраняем оригинальный Bitrix Order ID
            if order_id:
                try:
                    supabase_order['bitrix_order_id'] = int(order_id)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid order ID: {order_id}")
            
            # Метаданные с дополнительной информацией
            metadata = {
                'bitrix_id': order_id,
                'bitrix_status': bitrix_order.get('STATUS_ID'),
                'currency': bitrix_order.get('CURRENCY', 'KZT'),
                'original_data_keys': list(bitrix_order.keys())
            }
            
            # Обработка свойств заказа (поддержка разных форматов)
            props_data = None
            if 'PROPERTIES' in bitrix_order:
                props_data = bitrix_order['PROPERTIES']
            elif 'properties' in bitrix_order:  # Новый формат webhook
                props_data = bitrix_order['properties']
            
            if props_data and isinstance(props_data, dict):
                extracted_props = self._extract_order_properties(props_data)
                supabase_order.update(extracted_props)
                
                # Сохраняем важные свойства в metadata
                pickup_order = False
                for key, prop in props_data.items():
                    # Поддержка разных форматов свойств
                    if isinstance(prop, dict) and prop.get('VALUE'):
                        # Формат: {"CODE": "city", "VALUE": "2"}
                        prop_code = prop.get('CODE', key)
                        prop_value = prop.get('VALUE')
                    else:
                        # Формат: {"city": "2", "phone": "+77..."}
                        prop_code = key
                        prop_value = prop
                    
                    if prop_value:
                        # Проверяем свойства самовывоза
                        if prop_code in ('iWillGet', 'pickup') and str(prop_value).upper() == 'Y':
                            pickup_order = True
                        
                        # Сохраняем важные свойства
                        if prop_code.upper() in ('PHONE', 'EMAIL', 'ADDRESS', 'DELIVERY_DATE', 'CITY'):
                            metadata[f'bitrix_{prop_code.lower()}'] = str(prop_value)
                
                # Добавляем флаг самовывоза в метаданные
                metadata['pickup_order'] = pickup_order
            
            # Комментарии
            if 'USER_DESCRIPTION' in bitrix_order:
                supabase_order['comment'] = str(bitrix_order['USER_DESCRIPTION'])[:500]  # Лимит
            
            if 'COMMENTS' in bitrix_order:
                supabase_order['courier_comment'] = str(bitrix_order['COMMENTS'])[:500]  # Лимит
            
            # Метод оплаты
            if 'PAY_SYSTEM_ID' in bitrix_order:
                payment_method = self._get_payment_method(
                    bitrix_order['PAY_SYSTEM_ID']
                )
                supabase_order['payment_method'] = self._truncate_field(
                    payment_method, 
                    FieldLimits.PAYMENT_METHOD
                )
            
            # Дата доставки (только дата, без времени)
            if 'DELIVERY_DATE' in bitrix_order:
                delivery_date = self._parse_datetime(bitrix_order['DELIVERY_DATE'])
                if delivery_date:
                    # Берем только дату
                    supabase_order['delivery_date'] = delivery_date.split('T')[0]
            
            supabase_order['metadata'] = metadata
            
            return supabase_order
            
        except Exception as e:
            logger.error(f"Error transforming Bitrix order to Supabase: {e}")
            logger.error(f"Order data: {json.dumps(bitrix_order, default=str, indent=2)}")
            return None
    
    def _extract_order_properties(self, props: Dict[str, Any]) -> Dict[str, Any]:
        """
        Извлекает и обрабатывает свойства заказа из Bitrix
        
        Args:
            props: Свойства заказа из Bitrix
            
        Returns:
            Обработанные свойства для Supabase
        """
        result = {}
        
        # Мапинг важных свойств
        property_mapping = {
            # Старые форматы
            'PHONE': 'recipient_phone',
            'FIO': 'recipient_name',
            'EMAIL': 'recipient_email',
            'ADDRESS': 'delivery_address',
            'CITY': 'city_name',
            'DELIVERY_TIME': 'delivery_time',
            'RECIPIENT_NAME': 'recipient_name',
            # Новые форматы из продакшна
            'phoneRecipient': 'recipient_phone',
            'nameRecipient': 'recipient_name', 
            'addressRecipient': 'delivery_address',
            'data': 'delivery_date_raw',  # Дата доставки
            'postcardText': 'postcard_text',
            'city': 'bitrix_city_id'
            # Примечание: phone и email заказчика сохраняются в таблице users, не orders
        }
        
        # Флаг самовывоза для отслеживания
        is_pickup_order = False
        
        for prop_code, prop_data in props.items():
            # Поддержка разных форматов свойств
            if isinstance(prop_data, dict) and 'VALUE' in prop_data:
                # Старый формат: {"CODE": "city", "VALUE": "2"}
                value = str(prop_data.get('VALUE', '')).strip()
            else:
                # Новый формат: {"city": "2", "phone": "+77..."}
                value = str(prop_data).strip() if prop_data else ''
            
            if not value or value == 'NULL':
                continue
            
            # Проверяем свойства самовывоза
            if prop_code in ('iWillGet', 'pickup') and value.upper() == 'Y':
                is_pickup_order = True
                continue
            
            # Маппим в поля Supabase
            if prop_code in property_mapping:
                field_name = property_mapping[prop_code]
                
                # Специальная обработка для разных типов полей
                if field_name == 'recipient_name':
                    result[field_name] = self._truncate_field(value, FieldLimits.RECIPIENT_NAME)
                elif field_name == 'recipient_phone':
                    # Очищаем телефонные номера получателя
                    phone_clean = ''.join(c for c in value if c.isdigit() or c == '+')
                    if phone_clean and not phone_clean.startswith('+'):
                        phone_clean = '+' + phone_clean
                    result[field_name] = phone_clean[:20]
                elif field_name == 'delivery_date_raw':
                    # Обрабатываем дату доставки в формате YYYY-MM-DD
                    if len(value) == 10 and value.count('-') == 2:  # Формат YYYY-MM-DD
                        result['delivery_date'] = value
                    else:
                        result[field_name] = value[:50]
                elif field_name == 'bitrix_city_id':
                    # Сохраняем ID города для справки
                    try:
                        result['bitrix_city_id'] = int(value)
                    except (ValueError, TypeError):
                        result[field_name] = value[:50]
                elif field_name == 'postcard_text':
                    # Текст открытки может быть длинным
                    result[field_name] = value[:500]
                else:
                    result[field_name] = value[:255]  # Общий лимит для текстовых полей
            
            # Специальная обработка city для bitrix_city_id
            if prop_code.lower() == 'city':
                try:
                    result['bitrix_city_id'] = int(value)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid city ID: {value}")
        
        # Обрабатываем заказы самовывоза
        if is_pickup_order:
            result['delivery_address'] = 'Самовывоз'
            # Убираем recipient данные для самовывоза, так как клиент сам приедет
            if 'recipient_name' not in result or not result['recipient_name']:
                result['recipient_name'] = 'Самовывоз'
        
        return result
    
    def transform_bitrix_update(self, bitrix_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Преобразует частичные данные из Bitrix для обновления заказа в Supabase
        Используется для обработки webhook событий order.update и order.status_change
        
        Args:
            bitrix_data: Частичные данные заказа из Bitrix
            
        Returns:
            Данные для обновления в Supabase
        """
        update_data = {}
        
        # Обновляем статус заказа
        if 'STATUS_ID' in bitrix_data:
            bitrix_status = bitrix_data['STATUS_ID']
            supabase_status = StatusMapping.BITRIX_TO_SUPABASE.get(bitrix_status, 'new')
            update_data['status'] = self._truncate_field(supabase_status, FieldLimits.STATUS)
            
            # Добавляем информацию об изменении статуса в metadata
            if not update_data.get('metadata'):
                update_data['metadata'] = {}
            update_data['metadata']['last_status_change'] = {
                'bitrix_status': bitrix_status,
                'supabase_status': supabase_status,
                'timestamp': datetime.now().isoformat()
            }
        
        # Обновляем сумму заказа
        if 'PRICE' in bitrix_data:
            try:
                update_data['total_amount'] = float(bitrix_data['PRICE'])
            except (ValueError, TypeError):
                logger.warning(f"Invalid PRICE value: {bitrix_data['PRICE']}")
        
        # Обновляем статус оплаты
        if 'PAYED' in bitrix_data:
            payment_status = 'paid' if bitrix_data['PAYED'] == 'Y' else 'pending'
            update_data['payment_status'] = self._truncate_field(payment_status, FieldLimits.PAYMENT_STATUS)
        
        # Обновляем комментарии
        if 'USER_DESCRIPTION' in bitrix_data:
            comment = str(bitrix_data['USER_DESCRIPTION']) if bitrix_data['USER_DESCRIPTION'] else ''
            update_data['comment'] = comment[:500]  # Лимит для текста
        
        if 'COMMENTS' in bitrix_data:
            courier_comment = str(bitrix_data['COMMENTS']) if bitrix_data['COMMENTS'] else ''
            update_data['courier_comment'] = courier_comment[:500]  # Лимит для текста
        
        # Обновляем ответственного
        if 'RESPONSIBLE_ID' in bitrix_data:
            if not update_data.get('metadata'):
                update_data['metadata'] = {}
            update_data['metadata']['bitrix_responsible_id'] = str(bitrix_data['RESPONSIBLE_ID'])
        
        # Обрабатываем свойства заказа (если переданы)
        props_data = None
        if 'PROPERTIES' in bitrix_data:
            props_data = bitrix_data['PROPERTIES']
        elif 'properties' in bitrix_data:
            props_data = bitrix_data['properties']
        
        if props_data and isinstance(props_data, dict):
            extracted_props = self._extract_order_properties(props_data)
            update_data.update(extracted_props)
        
        # Обновляем timestamp
        update_data['updated_at'] = datetime.now().isoformat()
        
        logger.info(f"Update data prepared: {len(update_data)} fields to update")
        return update_data
    
    def transform_supabase_to_bitrix(self, supabase_order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Преобразует заказ из формата Supabase в формат Bitrix
        
        Args:
            supabase_order: Данные заказа из Supabase
            
        Returns:
            Заказ в формате Bitrix или None при ошибке
        """
        try:
            # Обратная трансформация для интеграции с Bitrix API
            bitrix_order = {
                'ORDER_TOPIC': supabase_order.get('order_number', ''),
                'STATUS_ID': StatusMapping.SUPABASE_TO_BITRIX.get(
                    supabase_order.get('status', 'new'), 'N'
                ),
                'PRICE': str(supabase_order.get('total_amount', 0)),
                'PRICE_DELIVERY': str(supabase_order.get('delivery_fee', 0)),
                'DISCOUNT_VALUE': str(supabase_order.get('discount_amount', 0)),
                'CURRENCY': supabase_order.get('metadata', {}).get('currency', 'KZT'),
                'USER_DESCRIPTION': supabase_order.get('comment', ''),
                'COMMENTS': supabase_order.get('courier_comment', ''),
            }
            
            # Дата доставки в формате Bitrix
            if supabase_order.get('delivery_date'):
                try:
                    delivery_date = datetime.fromisoformat(supabase_order['delivery_date'])
                    bitrix_order['DELIVERY_DATE'] = delivery_date.strftime('%d.%m.%Y')
                except:
                    pass
            
            return bitrix_order
            
        except Exception as e:
            logger.error(f"Error transforming Supabase order to Bitrix: {e}")
            return None
    
    def transform_basket_item(self, bitrix_item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Трансформирует товар из корзины Bitrix в формат для order_items
        
        Args:
            bitrix_item: Данные товара из Bitrix
            
        Returns:
            Данные товара для сохранения в order_items
        """
        try:
            # Извлекаем основные данные товара
            product_id = bitrix_item.get('PRODUCT_ID')
            quantity = float(bitrix_item.get('QUANTITY', 1))
            price = float(bitrix_item.get('PRICE', 0))
            discount_price = float(bitrix_item.get('DISCOUNT_PRICE', 0))
            
            # Рассчитываем итоговую цену с учетом скидки
            final_price = price - discount_price if discount_price > 0 else price
            total_amount = final_price * quantity
            
            # Формируем данные товара (только поля, которые существуют в БД)
            order_item = {
                'quantity': int(quantity),
                'price': final_price,
                'total': total_amount,
                'bitrix_product_id': int(product_id) if product_id else None,
                'created_at': datetime.now().isoformat(),
                # Сохраняем детальную информацию в product_snapshot
                'product_snapshot': {
                    'name': str(bitrix_item.get('NAME', '')),
                    'currency': str(bitrix_item.get('CURRENCY', 'KZT')),
                    'original_price': price,
                    'discount_price': discount_price,
                    'bitrix_basket_id': int(bitrix_item.get('ID')) if bitrix_item.get('ID') else None,
                    'product_xml_id': str(bitrix_item.get('PRODUCT_XML_ID')) if bitrix_item.get('PRODUCT_XML_ID') else None
                }
            }
            
            logger.debug(f"Transformed basket item: {product_id} -> quantity={quantity}, price={final_price}")
            return order_item
            
        except Exception as e:
            logger.error(f"Error transforming basket item: {e}")
            logger.debug(f"Bitrix item data: {bitrix_item}")
            
            # Возвращаем минимальные данные в случае ошибки
            return {
                'quantity': 1,
                'price': 0.0,
                'total': 0.0,
                'created_at': datetime.now().isoformat(),
                'product_snapshot': {'name': 'Unknown Product', 'currency': 'KZT'}
            }
    
    def transform_bitrix_user(self, user_data: Dict[str, Any], bitrix_user_id: str) -> Dict[str, Any]:
        """
        Трансформирует данные пользователя из Bitrix в формат для users
        
        Args:
            user_data: Данные пользователя из Bitrix
            bitrix_user_id: ID пользователя в Bitrix
            
        Returns:
            Данные пользователя для сохранения в users
        """
        try:
            # Основные данные пользователя
            user = {
                'phone': self._truncate_field(str(user_data.get('phone', '')), 20),
                'email': self._truncate_field(str(user_data.get('email', '')), 100),
                'bitrix_user_id': int(bitrix_user_id) if bitrix_user_id else None,
                'created_at': datetime.now().isoformat()
            }
            
            # Убираем пустые email типа "noemail@cvety.kz"
            if user['email'] in ('noemail@cvety.kz', 'no-email@cvety.kz', ''):
                user['email'] = None
            
            # Очищаем телефон от лишних символов
            if user['phone']:
                # Убираем все кроме цифр и плюса
                phone_clean = ''.join(c for c in user['phone'] if c.isdigit() or c == '+')
                if phone_clean and not phone_clean.startswith('+'):
                    phone_clean = '+' + phone_clean
                user['phone'] = phone_clean[:20]  # Ограничиваем длину
            
            # Добавляем имя из ID пользователя, если нет других данных
            if user_data.get('ID') and not user.get('name'):
                user['name'] = f"User_{user_data['ID']}"
            
            logger.debug(f"Transformed user: {bitrix_user_id} -> phone={user['phone']}, email={user['email']}")
            return user
            
        except Exception as e:
            logger.error(f"Error transforming user data: {e}")
            logger.debug(f"User data: {user_data}")
            
            # Возвращаем минимальные данные в случае ошибки
            return {
                'bitrix_user_id': int(bitrix_user_id) if bitrix_user_id else None,
                'created_at': datetime.now().isoformat()
            }
    
    def validate_order_data(self, order_data: Dict[str, Any]) -> List[str]:
        """
        Валидирует данные заказа перед сохранением
        
        Args:
            order_data: Данные заказа
            
        Returns:
            Список ошибок валидации
        """
        errors = []
        
        # Проверяем обязательные поля
        required_fields = ['order_number', 'status', 'total_amount']
        for field in required_fields:
            if not order_data.get(field):
                errors.append(f"Missing required field: {field}")
        
        # Проверяем ограничения длины
        length_checks = [
            ('order_number', FieldLimits.ORDER_NUMBER),
            ('status', FieldLimits.STATUS),
            ('payment_method', FieldLimits.PAYMENT_METHOD),
            ('recipient_name', FieldLimits.RECIPIENT_NAME)
        ]
        
        for field, max_length in length_checks:
            value = order_data.get(field)
            if value and len(str(value)) > max_length:
                errors.append(f"Field '{field}' too long: {len(str(value))} > {max_length}")
        
        # Проверяем числовые поля
        numeric_fields = ['total_amount', 'delivery_fee', 'discount_amount']
        for field in numeric_fields:
            value = order_data.get(field)
            if value is not None:
                try:
                    float(value)
                except (ValueError, TypeError):
                    errors.append(f"Invalid numeric value in '{field}': {value}")
        
        return errors
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Получает статистику кеширования
        
        Returns:
            Статистика использования кеша
        """
        return {
            'date_parse_cache': self._parse_datetime.cache_info()._asdict(),
            'status_cache': self._get_status_mapping.cache_info()._asdict(),
            'payment_cache': self._get_payment_method.cache_info()._asdict(),
        }
    
    def clear_cache(self):
        """Очищает все кеши"""
        self._parse_datetime.cache_clear()
        self._get_status_mapping.cache_clear()
        self._get_payment_method.cache_clear()
        logger.info("All transformer caches cleared")