#!/usr/bin/env python3
"""
Миграция заказов из локальной MySQL базы данных в Python CRM через webhook
Безопасное тестирование перед применением на продакшене
"""

import pymysql
import requests
import json
from datetime import datetime
import time
import sys
from typing import Dict, List, Any, Optional

# Конфигурация
MYSQL_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'cvety123',
    'database': 'cvety_db',
    'charset': 'utf8mb4'
}

WEBHOOK_CONFIG = {
    'url': 'http://localhost:8001/api/webhooks/bitrix/order',
    'token': 'secret-webhook-token-2024',
    'timeout': 30
}

# Цвета для консоли
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
MAGENTA = '\033[95m'
RESET = '\033[0m'

class LocalMySQLMigrator:
    """Мигратор заказов из локальной MySQL в Python CRM"""
    
    def __init__(self):
        """Инициализация подключения к MySQL"""
        try:
            self.connection = pymysql.connect(**MYSQL_CONFIG)
            self.cursor = self.connection.cursor(pymysql.cursors.DictCursor)
            print(f"{GREEN}✅ Подключено к MySQL на localhost:3306{RESET}")
            self._check_database_stats()
        except Exception as e:
            print(f"{RED}❌ Ошибка подключения к MySQL: {e}{RESET}")
            sys.exit(1)
    
    def _check_database_stats(self):
        """Показывает статистику базы данных"""
        try:
            # Общее количество заказов
            self.cursor.execute("SELECT COUNT(*) as total FROM b_sale_order")
            total = self.cursor.fetchone()['total']
            
            # Заказы за последний месяц
            self.cursor.execute("""
                SELECT COUNT(*) as recent 
                FROM b_sale_order 
                WHERE DATE_INSERT >= DATE_SUB(NOW(), INTERVAL 30 DAY)
            """)
            recent = self.cursor.fetchone()['recent']
            
            # Последний заказ
            self.cursor.execute("""
                SELECT ID, DATE_INSERT 
                FROM b_sale_order 
                ORDER BY ID DESC 
                LIMIT 1
            """)
            last_order = self.cursor.fetchone()
            
            print(f"\n{BLUE}📊 Статистика локальной базы данных:{RESET}")
            print(f"  • Всего заказов: {total:,}")
            print(f"  • За последние 30 дней: {recent:,}")
            print(f"  • Последний заказ: ID {last_order['ID']} от {last_order['DATE_INSERT']}")
            print("")
            
        except Exception as e:
            print(f"{YELLOW}⚠️ Не удалось получить статистику: {e}{RESET}")
    
    def get_orders(self, limit: int = 10, offset: int = 0, start_id: Optional[int] = None) -> List[Dict]:
        """
        Получает заказы из MySQL с полными данными
        
        Args:
            limit: Количество заказов
            offset: Смещение
            start_id: ID заказа с которого начинать (для инкрементальной загрузки)
        """
        try:
            # Базовый запрос заказов
            if start_id:
                query = """
                    SELECT 
                        o.ID,
                        o.ACCOUNT_NUMBER,
                        o.STATUS_ID,
                        o.PRICE,
                        o.CURRENCY,
                        o.USER_ID,
                        o.PAY_SYSTEM_ID,
                        o.PAYED,
                        o.DATE_PAYED,
                        o.PRICE_DELIVERY,
                        o.ALLOW_DELIVERY,
                        o.DATE_ALLOW_DELIVERY,
                        o.DISCOUNT_VALUE,
                        o.TAX_VALUE,
                        o.USER_DESCRIPTION,
                        o.COMMENTS,
                        o.RESPONSIBLE_ID,
                        o.DATE_INSERT,
                        o.DATE_UPDATE
                    FROM b_sale_order o
                    WHERE o.ID > %s
                    ORDER BY o.ID
                    LIMIT %s
                """
                self.cursor.execute(query, (start_id, limit))
            else:
                query = """
                    SELECT 
                        o.ID,
                        o.ACCOUNT_NUMBER,
                        o.STATUS_ID,
                        o.PRICE,
                        o.CURRENCY,
                        o.USER_ID,
                        o.PAY_SYSTEM_ID,
                        o.PAYED,
                        o.DATE_PAYED,
                        o.PRICE_DELIVERY,
                        o.ALLOW_DELIVERY,
                        o.DATE_ALLOW_DELIVERY,
                        o.DISCOUNT_VALUE,
                        o.TAX_VALUE,
                        o.USER_DESCRIPTION,
                        o.COMMENTS,
                        o.RESPONSIBLE_ID,
                        o.DATE_INSERT,
                        o.DATE_UPDATE
                    FROM b_sale_order o
                    ORDER BY o.ID DESC
                    LIMIT %s OFFSET %s
                """
                self.cursor.execute(query, (limit, offset))
            
            orders = self.cursor.fetchall()
            
            # Для каждого заказа получаем дополнительные данные
            for order in orders:
                order_id = order['ID']
                
                # Получаем товары в заказе
                order['basket'] = self._get_order_basket(order_id)
                
                # Получаем свойства заказа
                order['properties'] = self._get_order_properties(order_id)
                
                # Преобразуем datetime в строки
                for key, value in order.items():
                    if isinstance(value, datetime):
                        order[key] = value.strftime('%Y-%m-%d %H:%M:%S')
            
            return orders
            
        except Exception as e:
            print(f"{RED}❌ Ошибка получения заказов: {e}{RESET}")
            return []
    
    def _get_order_basket(self, order_id: int) -> List[Dict]:
        """Получает товары в заказе"""
        try:
            query = """
                SELECT 
                    ID,
                    PRODUCT_ID,
                    PRODUCT_PRICE_ID,
                    NAME,
                    PRICE,
                    CURRENCY,
                    QUANTITY,
                    LID,
                    PRODUCT_XML_ID,
                    DISCOUNT_PRICE,
                    DISCOUNT_VALUE,
                    VAT_RATE,
                    SUBSCRIBE,
                    RESERVED,
                    BARCODE_MULTI,
                    CUSTOM_PRICE,
                    DETAIL_PAGE_URL,
                    CATALOG_XML_ID,
                    PRODUCT_PROVIDER_CLASS,
                    TYPE,
                    SET_PARENT_ID
                FROM b_sale_basket
                WHERE ORDER_ID = %s
            """
            self.cursor.execute(query, (order_id,))
            basket_items = self.cursor.fetchall()
            
            # Преобразуем Decimal в float для JSON
            for item in basket_items:
                for key, value in item.items():
                    if hasattr(value, 'real'):  # Это Decimal
                        item[key] = str(value)
                    elif isinstance(value, datetime):
                        item[key] = value.strftime('%Y-%m-%d %H:%M:%S')
            
            return basket_items
            
        except Exception as e:
            print(f"{YELLOW}⚠️ Ошибка получения товаров для заказа {order_id}: {e}{RESET}")
            return []
    
    def _get_order_properties(self, order_id: int) -> Dict:
        """Получает свойства заказа"""
        try:
            query = """
                SELECT 
                    p.CODE,
                    v.VALUE
                FROM b_sale_order_props_value v
                JOIN b_sale_order_props p ON v.ORDER_PROPS_ID = p.ID
                WHERE v.ORDER_ID = %s
            """
            self.cursor.execute(query, (order_id,))
            props = self.cursor.fetchall()
            
            # Преобразуем в словарь {CODE: VALUE}
            properties = {}
            for prop in props:
                if prop['CODE'] and prop['VALUE']:
                    # Маппинг кодов свойств на наши названия
                    code_map = {
                        'FIO': 'nameRecipient',
                        'PHONE': 'phoneRecipient',
                        'ADDRESS': 'addressRecipient',
                        'CITY': 'city',
                        'LOCATION': 'location',
                        'ZIP': 'zip',
                        'EMAIL': 'email',
                        'CONTACT_PERSON': 'contactPerson',
                        'DELIVERY_DATE': 'data',
                        'DELIVERY_TIME': 'when',
                        'POSTCARD_TEXT': 'postcardText',
                        'USER_DESCRIPTION': 'notes'
                    }
                    
                    mapped_code = code_map.get(prop['CODE'], prop['CODE'])
                    properties[mapped_code] = prop['VALUE']
            
            return properties
            
        except Exception as e:
            print(f"{YELLOW}⚠️ Ошибка получения свойств для заказа {order_id}: {e}{RESET}")
            return {}
    
    def send_order_to_webhook(self, order: Dict) -> bool:
        """
        Отправляет заказ через webhook в Python CRM
        
        Args:
            order: Данные заказа из MySQL
            
        Returns:
            True если успешно, False если ошибка
        """
        try:
            # Преобразуем в формат webhook
            # Конвертируем Decimal в строки для JSON
            webhook_data = {
                'ID': order['ID'],
                'order_id': order['ID'],
                'ACCOUNT_NUMBER': order['ACCOUNT_NUMBER'],
                'STATUS_ID': order['STATUS_ID'],
                'PRICE': str(order['PRICE']) if order['PRICE'] else '0',
                'PRICE_DELIVERY': str(order['PRICE_DELIVERY']) if order['PRICE_DELIVERY'] else '0',
                'DISCOUNT_VALUE': str(order['DISCOUNT_VALUE']) if order['DISCOUNT_VALUE'] else '0',
                'USER_ID': order['USER_ID'],
                'DATE_INSERT': order['DATE_INSERT'],
                'USER_DESCRIPTION': order['USER_DESCRIPTION'],
                'COMMENTS': order['COMMENTS'],
                'PAYED': order['PAYED'],
                'PAY_SYSTEM_ID': order['PAY_SYSTEM_ID'],
                'basket': order.get('basket', []),
                'properties': order.get('properties', {})
            }
            
            # Отправляем webhook
            headers = {
                'Content-Type': 'application/json',
                'X-Webhook-Token': WEBHOOK_CONFIG['token']
            }
            
            response = requests.post(
                WEBHOOK_CONFIG['url'],
                json=webhook_data,
                headers=headers,
                timeout=WEBHOOK_CONFIG['timeout']
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"{GREEN}✅ Заказ {order['ID']}: {result.get('action', 'success')}{RESET}")
                return True
            else:
                print(f"{RED}❌ Заказ {order['ID']}: HTTP {response.status_code}{RESET}")
                if response.text:
                    print(f"   Ответ: {response.text[:200]}")
                return False
                
        except Exception as e:
            print(f"{RED}❌ Ошибка отправки заказа {order.get('ID', '?')}: {e}{RESET}")
            return False
    
    def migrate_orders(self, count: int = 10, start_id: Optional[int] = None, delay: float = 0.5):
        """
        Основной метод миграции заказов
        
        Args:
            count: Количество заказов для миграции
            start_id: ID с которого начинать (для продолжения прерванной миграции)
            delay: Задержка между отправками (секунды)
        """
        print(f"\n{BLUE}🚀 Начинаем миграцию {count} заказов{RESET}")
        if start_id:
            print(f"   Начиная с ID > {start_id}")
        print("")
        
        # Получаем заказы
        orders = self.get_orders(limit=count, start_id=start_id)
        
        if not orders:
            print(f"{YELLOW}⚠️ Нет заказов для миграции{RESET}")
            return
        
        print(f"{MAGENTA}📦 Получено {len(orders)} заказов из MySQL{RESET}")
        print(f"   ID range: {orders[-1]['ID']} - {orders[0]['ID']}")
        print("")
        
        # Статистика
        success_count = 0
        error_count = 0
        last_id = 0
        
        # Мигрируем каждый заказ
        for i, order in enumerate(orders, 1):
            print(f"\n{BLUE}[{i}/{len(orders)}] Обрабатываем заказ {order['ID']}{RESET}")
            print(f"  • Дата: {order['DATE_INSERT']}")
            print(f"  • Сумма: {order['PRICE']} {order.get('CURRENCY', 'KZT')}")
            print(f"  • Товаров: {len(order.get('basket', []))}")
            
            # Отправляем через webhook
            if self.send_order_to_webhook(order):
                success_count += 1
            else:
                error_count += 1
            
            last_id = order['ID']
            
            # Задержка между запросами
            if i < len(orders):
                time.sleep(delay)
        
        # Итоговая статистика
        print(f"\n{BLUE}{'='*60}{RESET}")
        print(f"{BLUE}📊 ИТОГИ МИГРАЦИИ{RESET}")
        print(f"{BLUE}{'='*60}{RESET}")
        print(f"  {GREEN}✅ Успешно: {success_count}{RESET}")
        if error_count > 0:
            print(f"  {RED}❌ Ошибок: {error_count}{RESET}")
        print(f"  📍 Последний ID: {last_id}")
        print(f"\n💡 Для продолжения используйте: --start-id {last_id}")
        print(f"{BLUE}{'='*60}{RESET}")
        
        # Сохраняем checkpoint
        self._save_checkpoint(last_id, success_count, error_count)
    
    def _save_checkpoint(self, last_id: int, success: int, errors: int):
        """Сохраняет точку для возможности продолжения"""
        checkpoint = {
            'last_id': last_id,
            'success_count': success,
            'error_count': errors,
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            with open('migration_checkpoint.json', 'w') as f:
                json.dump(checkpoint, f, indent=2)
            print(f"\n💾 Checkpoint сохранен в migration_checkpoint.json")
        except Exception as e:
            print(f"{YELLOW}⚠️ Не удалось сохранить checkpoint: {e}{RESET}")
    
    def get_order_details(self, order_id: int):
        """Получает и выводит детальную информацию о заказе"""
        print(f"\n{BLUE}🔍 Детали заказа {order_id}:{RESET}\n")
        
        # Получаем заказ
        self.cursor.execute("SELECT * FROM b_sale_order WHERE ID = %s", (order_id,))
        order = self.cursor.fetchone()
        
        if not order:
            print(f"{RED}❌ Заказ {order_id} не найден{RESET}")
            return
        
        # Основная информация
        print(f"{GREEN}📋 Основные данные:{RESET}")
        print(f"  • ID: {order['ID']}")
        print(f"  • Номер: {order['ACCOUNT_NUMBER']}")
        print(f"  • Статус: {order['STATUS_ID']}")
        print(f"  • Сумма: {order['PRICE']} {order['CURRENCY']}")
        print(f"  • Пользователь: {order['USER_ID']}")
        print(f"  • Дата: {order['DATE_INSERT']}")
        
        # Товары
        basket = self._get_order_basket(order_id)
        if basket:
            print(f"\n{GREEN}🛒 Товары ({len(basket)} шт):{RESET}")
            for item in basket:
                print(f"  • {item['NAME']}")
                print(f"    Цена: {item['PRICE']} x {item['QUANTITY']} = {float(item['PRICE']) * float(item['QUANTITY'])}")
        
        # Свойства
        props = self._get_order_properties(order_id)
        if props:
            print(f"\n{GREEN}📝 Свойства заказа:{RESET}")
            for key, value in props.items():
                if value:
                    print(f"  • {key}: {value}")
    
    def close(self):
        """Закрывает соединение с базой данных"""
        if self.connection:
            self.connection.close()
            print(f"\n{GREEN}✅ Соединение с MySQL закрыто{RESET}")

def main():
    """Главная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Миграция заказов из MySQL в Python CRM')
    parser.add_argument('--count', type=int, default=10, help='Количество заказов для миграции (по умолчанию 10)')
    parser.add_argument('--start-id', type=int, help='ID заказа с которого начать')
    parser.add_argument('--delay', type=float, default=0.5, help='Задержка между отправками в секундах')
    parser.add_argument('--details', type=int, help='Показать детали конкретного заказа')
    
    args = parser.parse_args()
    
    # Создаем мигратор
    migrator = LocalMySQLMigrator()
    
    try:
        if args.details:
            # Показываем детали заказа
            migrator.get_order_details(args.details)
        else:
            # Выполняем миграцию
            migrator.migrate_orders(
                count=args.count,
                start_id=args.start_id,
                delay=args.delay
            )
    finally:
        migrator.close()

if __name__ == "__main__":
    main()