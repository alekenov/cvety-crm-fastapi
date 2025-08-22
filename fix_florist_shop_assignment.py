#!/usr/bin/env python3
"""
Исправление назначения флористов по магазинам в Supabase
Учитывает реальное поле UF_FLORIST_SHOP из MySQL Bitrix
"""

import mysql.connector
from supabase import create_client
from config import config
import logging
from typing import List, Dict, Optional
from datetime import datetime

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Константы
CVETYKZ_SHOP_UUID = "7f52091f-a6f1-4d23-a2c9-6754109065f4"
CVETYKZ_BITRIX_SHOP_ID = "17008"  # Это seller.ID = 2081, но UF_ID_SELLER = 17008
FLORIST_GROUP_ID = 7  # Флористы
CHIEF_FLORIST_GROUP_ID = 13  # Главный флорист

class FloristShopFixer:
    def __init__(self):
        self.mysql_connection = None
        self.supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        self.stats = {
            'total_florists': 0,
            'cvetykz_florists': 0,
            'other_shop_florists': 0,
            'updated_florists': 0,
            'errors': 0
        }
    
    def connect_mysql(self) -> bool:
        """Подключение к MySQL базе"""
        try:
            self.mysql_connection = mysql.connector.connect(
                host='localhost',
                port=3306,
                user='root',
                password='cvety123',
                database='cvety_db',
                charset='utf8mb4',
                autocommit=True
            )
            logger.info("✅ Подключились к MySQL базе")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к MySQL: {e}")
            return False
    
    def get_florists_with_shops(self) -> List[Dict]:
        """Получить всех флористов с их магазинами из MySQL"""
        if not self.mysql_connection:
            logger.error("❌ Нет подключения к MySQL")
            return []
        
        try:
            cursor = self.mysql_connection.cursor(dictionary=True)
            
            # Получаем всех флористов с их магазинами
            query = """
            SELECT 
                u.ID as bitrix_user_id,
                u.NAME,
                u.LAST_NAME,
                u.EMAIL,
                u.PERSONAL_MOBILE as PHONE,
                u.WORK_POSITION,
                u.ACTIVE,
                uts.UF_FLORIST_SHOP as florist_shop_id,
                s.UF_NAME as shop_name,
                s.UF_ID_SELLER as seller_id,
                GROUP_CONCAT(DISTINCT ug.GROUP_ID SEPARATOR ',') as GROUP_IDS,
                GROUP_CONCAT(DISTINCT g.NAME SEPARATOR ', ') as GROUP_NAMES,
                CASE 
                    WHEN MAX(CASE WHEN ug.GROUP_ID = %s THEN 1 ELSE 0 END) = 1 THEN 'Главный флорист'
                    WHEN MAX(CASE WHEN ug.GROUP_ID = %s THEN 1 ELSE 0 END) = 1 THEN 'Флорист'
                    ELSE 'Пользователь'
                END as PRIMARY_ROLE
            FROM b_user u 
            JOIN b_user_group ug ON u.ID = ug.USER_ID 
            JOIN b_group g ON ug.GROUP_ID = g.ID 
            JOIN b_uts_user uts ON u.ID = uts.VALUE_ID
            LEFT JOIN seller s ON uts.UF_FLORIST_SHOP = s.ID
            WHERE ug.GROUP_ID IN (%s, %s)
              AND uts.UF_FLORIST_SHOP IS NOT NULL
            GROUP BY u.ID, u.NAME, u.LAST_NAME, u.EMAIL, u.PERSONAL_MOBILE, u.WORK_POSITION, u.ACTIVE, 
                     uts.UF_FLORIST_SHOP, s.UF_NAME, s.UF_ID_SELLER
            ORDER BY u.ID
            """
            
            cursor.execute(query, (CHIEF_FLORIST_GROUP_ID, FLORIST_GROUP_ID, FLORIST_GROUP_ID, CHIEF_FLORIST_GROUP_ID))
            florists = cursor.fetchall()
            cursor.close()
            
            self.stats['total_florists'] = len(florists)
            logger.info(f"📊 Найдено {len(florists)} флористов с назначенными магазинами в MySQL")
            
            return florists
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения флористов: {e}")
            return []
    
    def get_existing_user_by_bitrix_id(self, bitrix_id: str) -> Optional[Dict]:
        """Найти существующего пользователя в Supabase по bitrix_id"""
        try:
            result = self.supabase.table('users')\
                .select('*')\
                .filter('preferences->>bitrix_id', 'eq', bitrix_id)\
                .execute()
            
            return result.data[0] if result.data else None
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска пользователя {bitrix_id}: {e}")
            return None
    
    def update_florist_shop_assignment(self, user_id: str, florist: Dict) -> bool:
        """Обновить назначение магазина для флориста"""
        try:
            # Получаем текущие preferences
            existing_user = self.supabase.table('users').select('preferences').eq('id', user_id).execute()
            if not existing_user.data:
                return False
                
            current_preferences = existing_user.data[0].get('preferences', {})
            
            # Определяем правильный shop_id
            florist_shop_id = florist.get('florist_shop_id')
            seller_id = florist.get('seller_id')
            
            if str(florist_shop_id) == CVETYKZ_BITRIX_SHOP_ID:
                # Это флорист Cvetykz (проверяем по UF_FLORIST_SHOP напрямую)
                shop_uuid = CVETYKZ_SHOP_UUID
                bitrix_shop_id = CVETYKZ_BITRIX_SHOP_ID
                self.stats['cvetykz_florists'] += 1
                logger.info(f"  → Cvetykz флорист: {florist['NAME']} (florist_shop_id: {florist_shop_id})")
            else:
                # Флорист другого магазина - создаем временный UUID или помечаем как "другой"
                shop_uuid = f"shop_{florist_shop_id}"  # Временное решение
                bitrix_shop_id = str(florist_shop_id)
                self.stats['other_shop_florists'] += 1
                logger.info(f"  → Другой магазин: {florist['NAME']} (shop: {florist.get('shop_name', 'Unknown')}, florist_shop_id: {florist_shop_id})")
            
            # Обновляем preferences
            new_preferences = {
                **current_preferences,
                'bitrix_id': str(florist['bitrix_user_id']),
                'shop_id': shop_uuid,
                'bitrix_shop_id': bitrix_shop_id,
                'florist_shop_id': florist_shop_id,
                'shop_name': florist.get('shop_name'),
                'is_florist': True,
                'florist_role': florist['PRIMARY_ROLE'],
                'bitrix_group_ids': [int(g) for g in florist['GROUP_IDS'].split(',') if g],
                'bitrix_groups': florist['GROUP_NAMES'],
                'work_position': florist.get('WORK_POSITION'),
                'is_active': florist.get('ACTIVE') == 'Y',
                'updated_at': datetime.now().isoformat()
            }
            
            result = self.supabase.table('users')\
                .update({'preferences': new_preferences})\
                .eq('id', user_id)\
                .execute()
            
            self.stats['updated_florists'] += 1
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления флориста {user_id}: {e}")
            self.stats['errors'] += 1
            return False
    
    def fix_florist_assignments(self):
        """Исправить назначения магазинов для флористов"""
        logger.info("🚀 Начинаем исправление назначений флористов по магазинам...")
        
        # Подключаемся к MySQL
        if not self.connect_mysql():
            return False
        
        # Получаем флористов из MySQL
        florists = self.get_florists_with_shops()
        if not florists:
            logger.error("❌ Не найдено флористов для обработки")
            return False
        
        logger.info(f"📋 Будет обработано {len(florists)} флористов...")
        
        # Обрабатываем каждого флориста
        for i, florist in enumerate(florists, 1):
            bitrix_id = str(florist['bitrix_user_id'])
            display_name = florist.get('NAME', 'Без имени')
            
            logger.info(f"⏳ [{i}/{len(florists)}] Обрабатываем флориста: {display_name} (Bitrix ID: {bitrix_id})")
            
            # Ищем пользователя в Supabase
            existing_user = self.get_existing_user_by_bitrix_id(bitrix_id)
            if existing_user:
                self.update_florist_shop_assignment(existing_user['id'], florist)
            else:
                logger.warning(f"⚠️ Пользователь с Bitrix ID {bitrix_id} не найден в Supabase")
            
            # Показываем прогресс каждые 20 пользователей
            if i % 20 == 0:
                logger.info(f"📊 Прогресс: {i}/{len(florists)} - Cvetykz: {self.stats['cvetykz_florists']}, Другие: {self.stats['other_shop_florists']}, Ошибок: {self.stats['errors']}")
        
        # Финальная статистика
        logger.info("=" * 60)
        logger.info("📊 РЕЗУЛЬТАТЫ ИСПРАВЛЕНИЯ:")
        logger.info(f"   Всего флористов обработано: {self.stats['total_florists']}")
        logger.info(f"   Флористов Cvetykz: {self.stats['cvetykz_florists']}")
        logger.info(f"   Флористов других магазинов: {self.stats['other_shop_florists']}")
        logger.info(f"   Успешно обновлено: {self.stats['updated_florists']}")
        logger.info(f"   Ошибок: {self.stats['errors']}")
        logger.info("=" * 60)
        
        # Закрываем соединение с MySQL
        if self.mysql_connection:
            self.mysql_connection.close()
        
        logger.info("✅ Исправление назначений завершено!")
        return True

if __name__ == "__main__":
    fixer = FloristShopFixer()
    fixer.fix_florist_assignments()