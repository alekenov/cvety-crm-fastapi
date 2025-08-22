#!/usr/bin/env python3
"""
Product Transformer для синхронизации товаров Bitrix → Supabase
Преобразует данные товаров из формата Bitrix в формат Supabase PostgreSQL
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class ProductTransformer:
    """Transformer для преобразования данных товаров"""
    
    def __init__(self):
        """Инициализация трансформера"""
        self.product_types = {
            '1': 'bouquet',      # Букеты
            '2': 'composition',  # Композиции  
            '3': 'individual',   # Индивидуальные цветы
            '4': 'gift',         # Подарки
            '5': 'accessory'     # Аксессуары
        }
        
        self.availability_map = {
            'Y': True,    # В наличии
            'N': False,   # Нет в наличии
            '1': True,    # Доступен
            '0': False    # Недоступен
        }
    
    def transform_product(self, bitrix_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Преобразовать данные товара из Bitrix в формат Supabase
        
        Args:
            bitrix_data: Данные товара от Bitrix webhook
            
        Returns:
            Dict: Данные товара для Supabase
        """
        try:
            product_data = bitrix_data.get('data', {})
            
            # Базовые поля товара (используем существующую структуру Supabase)
            transformed = {
                'name': product_data.get('NAME', ''),
                'slug': self._generate_slug(product_data.get('NAME', ''), product_data.get('ID', '')),
                'description': product_data.get('DETAIL_TEXT', ''),
                'price': self._parse_price(self._get_main_price(product_data)),
                'old_price': self._parse_price(product_data.get('OLD_PRICE', 0)),
                'quantity': int(float(product_data.get('QUANTITY', 0) or 0)),
                'sku': product_data.get('CODE', '') or f"product_{product_data.get('ID', '')}",
                'is_active': self._parse_availability(product_data.get('ACTIVE', 'Y')),
                'is_featured': False,
                'sort_order': int(product_data.get('SORT', 500)),
                'category_id': self._parse_category(product_data),
                'images': self._parse_images(product_data),
                'metadata': self._build_metadata(product_data),
                'search_vector': None,  # Будет обновлен автоматически
                'seller_id': None,  # Может быть обновлен позже
                'created_at': self._parse_datetime(product_data.get('DATE_CREATE')),
                'updated_at': self._parse_datetime(product_data.get('TIMESTAMP_X')) or datetime.utcnow().isoformat()
            }
            
            # SEO поля - оставляем только поддерживаемые поля
            # Остальные поля сохраняются в metadata
            
            logger.info(f"Product transformed: Bitrix ID {product_data.get('ID')} → {transformed['name']}")
            return transformed
            
        except Exception as e:
            logger.error(f"Product transformation error: {e}")
            logger.error(f"Bitrix data: {bitrix_data}")
            raise
    
    def _parse_price(self, price_value: Any) -> float:
        """Парсинг цены"""
        if not price_value:
            return 0.0
        
        try:
            # Убираем валютные символы и пробелы
            price_str = str(price_value).replace('₸', '').replace('KZT', '').replace(' ', '').replace(',', '')
            return float(price_str)
        except (ValueError, TypeError):
            return 0.0
    
    def _parse_availability(self, active_value: Any) -> bool:
        """Парсинг доступности товара"""
        if isinstance(active_value, bool):
            return active_value
        
        return self.availability_map.get(str(active_value).upper(), True)
    
    def _get_product_type(self, product_data: Dict[str, Any]) -> str:
        """Определение типа товара"""
        # Попробуем определить по IBLOCK_ID или свойствам
        iblock_id = product_data.get('IBLOCK_ID', '')
        
        # Стандартные IBLOCK_ID для Bitrix Cvety.kz
        if str(iblock_id) == '2':  # Основной каталог
            return 'bouquet'
        elif str(iblock_id) == '27':  # Торговые предложения
            return 'offer'
        
        # Определяем по названию или свойствам
        name = product_data.get('NAME', '').lower()
        if any(word in name for word in ['букет', 'bouquet']):
            return 'bouquet'
        elif any(word in name for word in ['композиция', 'composition']):
            return 'composition'
        elif any(word in name for word in ['подарок', 'gift']):
            return 'gift'
        
        return 'bouquet'  # По умолчанию
    
    def _parse_category(self, product_data: Dict[str, Any]) -> Optional[str]:
        """Парсинг категории товара - возвращаем None для category_id, так как в Supabase используются UUID"""
        # В Supabase таблица categories использует UUID, а у нас integer ID из Bitrix
        # Поэтому оставляем category_id как null, а Bitrix section_id сохраняем в metadata
        return None
    
    def _parse_images(self, product_data: Dict[str, Any]) -> List[str]:
        """Парсинг изображений товара"""
        images = []
        
        # Основное изображение
        if product_data.get('PREVIEW_PICTURE'):
            preview_url = self._parse_image_url(product_data['PREVIEW_PICTURE'])
            if preview_url:
                images.append(preview_url)
        
        # Детальное изображение
        if product_data.get('DETAIL_PICTURE'):
            detail_url = self._parse_image_url(product_data['DETAIL_PICTURE'])
            if detail_url and detail_url not in images:
                images.append(detail_url)
        
        # Дополнительные изображения из свойств
        properties = product_data.get('PROPERTIES', {})
        if isinstance(properties, dict):
            for prop_code, prop_data in properties.items():
                if 'PHOTO' in prop_code.upper() or 'IMAGE' in prop_code.upper():
                    if isinstance(prop_data, dict) and 'VALUE' in prop_data:
                        image_url = self._parse_image_url(prop_data['VALUE'])
                        if image_url and image_url not in images:
                            images.append(image_url)
        
        return images
    
    def _parse_image_url(self, image_data: Any) -> Optional[str]:
        """Парсинг URL изображения"""
        if not image_data:
            return None
        
        # Если это уже URL
        if isinstance(image_data, str):
            if image_data.startswith('http'):
                return image_data
            elif image_data.startswith('/'):
                return f"https://cvety.kz{image_data}"
        
        # Если это ID файла или объект с файлом
        if isinstance(image_data, (int, str)) and str(image_data).isdigit():
            # Можно сделать запрос к Bitrix API для получения URL файла
            # Пока возвращаем базовый URL
            return f"https://cvety.kz/upload/iblock/{image_data}"
        
        return None
    
    def _parse_properties(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """Парсинг свойств товара"""
        properties = {}
        
        bitrix_props = product_data.get('PROPERTIES', {})
        if isinstance(bitrix_props, dict):
            for prop_code, prop_data in bitrix_props.items():
                if isinstance(prop_data, dict):
                    value = prop_data.get('VALUE')
                    if value:
                        properties[prop_code.lower()] = value
                else:
                    # Простое значение
                    properties[prop_code.lower()] = prop_data
        
        # Стандартные свойства
        standard_props = [
            'ARTNUMBER', 'COLOR', 'SIZE', 'MATERIAL', 'BRAND',
            'WEIGHT', 'DIMENSIONS', 'CARE_INSTRUCTIONS'
        ]
        
        for prop in standard_props:
            if prop in product_data:
                properties[prop.lower()] = product_data[prop]
        
        return properties
    
    def _generate_slug(self, name: str, product_id: str) -> str:
        """Генерация slug для товара"""
        import re
        
        if not name:
            return f"product-{product_id}"
        
        # Простое создание slug
        slug = name.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)  # Убираем спецсимволы
        slug = re.sub(r'[-\s]+', '-', slug)  # Заменяем пробелы и дефисы
        slug = slug.strip('-')
        
        return f"{slug}-{product_id}"
    
    def _get_main_price(self, product_data: Dict[str, Any]) -> float:
        """Получение основной цены товара"""
        # Сначала проверяем прямую цену
        if 'PRICE' in product_data:
            return product_data['PRICE']
        
        # Проверяем в свойствах
        properties = product_data.get('PROPERTIES', {})
        if isinstance(properties, dict):
            for prop_code, prop_data in properties.items():
                if 'PRICE' in prop_code.upper():
                    if isinstance(prop_data, dict) and 'VALUE' in prop_data:
                        return prop_data['VALUE']
                    else:
                        return prop_data
        
        # Проверяем в массиве цен
        prices = product_data.get('PRICES', [])
        if prices and len(prices) > 0:
            return prices[0].get('PRICE', 0)
        
        return 0
    
    def _build_metadata(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """Построение метаданных"""
        metadata = {
            'bitrix_id': product_data.get('ID'),
            'bitrix_iblock_id': product_data.get('IBLOCK_ID'),
            'bitrix_section_id': product_data.get('IBLOCK_SECTION_ID'),
            'bitrix_type_id': product_data.get('IBLOCK_TYPE_ID'),
            'bitrix_code': product_data.get('CODE'),
            'xml_id': product_data.get('XML_ID'),
            'stock_quantity': int(float(product_data.get('QUANTITY', 0) or 0)),
            'preview_picture_id': product_data.get('PREVIEW_PICTURE'),
            'detail_picture_id': product_data.get('DETAIL_PICTURE'),
            'sync_timestamp': datetime.utcnow().isoformat(),
            'webhook_source': 'bitrix_product_sync',
            'properties': self._parse_properties(product_data),
            'prices': product_data.get('PRICES', [])
        }
        
        # Добавляем системные поля Bitrix
        system_fields = [
            'CODE', 'XML_ID', 'TAGS', 'SHOW_COUNTER', 'SHOW_COUNTER_START',
            'WF_STATUS_ID', 'WF_PARENT_ELEMENT_ID', 'WF_LAST_HISTORY_ID',
            'WF_NEW', 'WF_LOCKED', 'WF_DATE_LOCK', 'WF_COMMENTS'
        ]
        
        for field in system_fields:
            if field in product_data:
                metadata[f'bitrix_{field.lower()}'] = product_data[field]
        
        return metadata
    
    def _parse_datetime(self, date_str: Any) -> Optional[str]:
        """Парсинг даты и времени"""
        if not date_str:
            return None
        
        try:
            # Различные форматы дат Bitrix
            formats = [
                '%Y-%m-%d %H:%M:%S',
                '%d.%m.%Y %H:%M:%S', 
                '%Y-%m-%d',
                '%d.%m.%Y'
            ]
            
            for fmt in formats:
                try:
                    dt = datetime.strptime(str(date_str), fmt)
                    return dt.isoformat()
                except ValueError:
                    continue
            
            # Если не удалось распарсить - возвращаем как есть
            return str(date_str)
            
        except Exception as e:
            logger.warning(f"Date parsing error: {e}, value: {date_str}")
            return None

    def validate_product_data(self, product_data: Dict[str, Any]) -> bool:
        """
        Валидация данных товара перед сохранением
        
        Args:
            product_data: Преобразованные данные товара
            
        Returns:
            bool: True если данные валидны
        """
        required_fields = ['name', 'metadata']
        
        for field in required_fields:
            if not product_data.get(field):
                logger.error(f"Missing required field: {field}")
                return False
        
        # Проверка типов данных
        metadata = product_data.get('metadata', {})
        if not metadata.get('bitrix_id'):
            logger.error("metadata.bitrix_id is required")
            return False
        
        if not isinstance(product_data.get('price', 0), (int, float)):
            logger.error("price must be numeric")
            return False
        
        return True

# Экспортируем главный класс
__all__ = ['ProductTransformer']