#!/usr/bin/env python3
"""
MySQL client for connecting to Bitrix database to get florists and user data
"""

import mysql.connector
from typing import List, Dict, Optional
import logging
from config import config

logger = logging.getLogger(__name__)

class MySQLClient:
    def __init__(self):
        self.connection = None
        
    def connect(self):
        """Connect to MySQL database"""
        try:
            # For Docker connection, use host as localhost since we're port-forwarding
            self.connection = mysql.connector.connect(
                host=config.MYSQL_HOST,
                port=3306,  # Direct port, not from config since Docker port forwarding
                user=config.MYSQL_USER,
                password=config.MYSQL_PASSWORD,
                database=config.MYSQL_DATABASE,
                charset='utf8mb4',
                autocommit=True
            )
            logger.info("Successfully connected to MySQL database")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MySQL: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from MySQL database"""
        if self.connection:
            self.connection.close()
            self.connection = None
    
    def get_florists(self) -> List[Dict]:
        """
        Get all florists from Bitrix b_user table where user is in florist groups (7, 13)
        """
        if not self.connection:
            if not self.connect():
                return []
        
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            # Get all florists with their roles
            query = """
            SELECT 
                u.ID,
                u.NAME,
                u.LAST_NAME,
                u.EMAIL,
                u.PERSONAL_MOBILE,
                u.WORK_POSITION,
                GROUP_CONCAT(g.NAME SEPARATOR ', ') as ROLES,
                CASE 
                    WHEN MAX(CASE WHEN g.ID = 13 THEN 1 ELSE 0 END) = 1 THEN 'Главный флорист'
                    WHEN MAX(CASE WHEN g.ID = 7 THEN 1 ELSE 0 END) = 1 THEN 'Флорист'
                    ELSE 'Пользователь'
                END as PRIMARY_ROLE
            FROM b_user u 
            JOIN b_user_group ug ON u.ID = ug.USER_ID 
            JOIN b_group g ON ug.GROUP_ID = g.ID 
            WHERE ug.GROUP_ID IN (7, 13)  -- 7=Флористы, 13=Главный флорист
            GROUP BY u.ID, u.NAME, u.LAST_NAME, u.EMAIL, u.PERSONAL_MOBILE, u.WORK_POSITION
            ORDER BY 
                CASE 
                    WHEN MAX(CASE WHEN g.ID = 13 THEN 1 ELSE 0 END) = 1 THEN 1
                    ELSE 2
                END,
                u.NAME, u.LAST_NAME
            """
            
            cursor.execute(query)
            florists = cursor.fetchall()
            cursor.close()
            
            # Clean up the data
            cleaned_florists = []
            for florist in florists:
                # Create display name
                display_name = ""
                if florist.get('NAME'):
                    display_name = florist['NAME']
                    if florist.get('LAST_NAME'):
                        display_name += f" {florist['LAST_NAME']}"
                elif florist.get('EMAIL'):
                    display_name = florist['EMAIL']
                else:
                    display_name = f"ID: {florist['ID']}"
                
                cleaned_florists.append({
                    'id': str(florist['ID']),
                    'name': display_name,
                    'email': florist.get('EMAIL'),
                    'phone': florist.get('PERSONAL_MOBILE'),
                    'role': florist.get('PRIMARY_ROLE', 'Флорист'),
                    'roles': florist.get('ROLES', ''),
                    'work_position': florist.get('WORK_POSITION')
                })
                
            logger.info(f"Retrieved {len(cleaned_florists)} florists from MySQL")
            return cleaned_florists
            
        except Exception as e:
            logger.error(f"Failed to get florists from MySQL: {e}")
            return []
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """Get specific user by ID"""
        if not self.connection:
            if not self.connect():
                return None
                
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            query = """
            SELECT 
                u.ID,
                u.NAME,
                u.LAST_NAME,
                u.EMAIL,
                u.PERSONAL_MOBILE,
                u.WORK_POSITION,
                GROUP_CONCAT(g.NAME SEPARATOR ', ') as ROLES
            FROM b_user u 
            LEFT JOIN b_user_group ug ON u.ID = ug.USER_ID 
            LEFT JOIN b_group g ON ug.GROUP_ID = g.ID 
            WHERE u.ID = %s
            GROUP BY u.ID, u.NAME, u.LAST_NAME, u.EMAIL, u.PERSONAL_MOBILE, u.WORK_POSITION
            """
            
            cursor.execute(query, (user_id,))
            user = cursor.fetchone()
            cursor.close()
            
            if user:
                display_name = ""
                if user.get('NAME'):
                    display_name = user['NAME']
                    if user.get('LAST_NAME'):
                        display_name += f" {user['LAST_NAME']}"
                elif user.get('EMAIL'):
                    display_name = user['EMAIL']
                else:
                    display_name = f"ID: {user['ID']}"
                    
                return {
                    'id': str(user['ID']),
                    'name': display_name,
                    'email': user.get('EMAIL'),
                    'phone': user.get('PERSONAL_MOBILE'),
                    'roles': user.get('ROLES', ''),
                    'work_position': user.get('WORK_POSITION')
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get user {user_id} from MySQL: {e}")
            return None

# Global MySQL client instance
mysql_client = MySQLClient()