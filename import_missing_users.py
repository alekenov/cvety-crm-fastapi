#!/usr/bin/env python3
"""
Импорт отсутствующих пользователей из production MySQL в Supabase
"""

import os
import sys
import pymysql
import uuid
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Конфигурация
PRODUCTION_MYSQL = {
    'host': '185.125.90.141',
    'user': 'usercvety',
    'password': 'QQlPCtTA@z2%mhy',
    'database': 'dbcvety',
    'charset': 'utf8mb4'
}

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

def connect_to_production():
    """Подключение к production MySQL"""
    try:
        connection = pymysql.connect(
            **PRODUCTION_MYSQL,
            cursorclass=pymysql.cursors.DictCursor
        )
        print("✅ Подключено к production MySQL")
        return connection
    except Exception as e:
        print(f"❌ Ошибка подключения к production MySQL: {e}")
        return None

def connect_to_supabase():
    """Подключение к Supabase"""
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        print("✅ Подключено к Supabase")
        return supabase
    except Exception as e:
        print(f"❌ Ошибка подключения к Supabase: {e}")
        return None

def get_missing_users(connection, user_ids):
    """Получить данные отсутствующих пользователей из production"""
    try:
        with connection.cursor() as cursor:
            # Создаем строку с ID для SQL запроса
            ids_str = ','.join(map(str, user_ids))
            
            query = f"""
            SELECT 
                ID,
                LOGIN,
                EMAIL,
                NAME,
                LAST_NAME,
                PERSONAL_PHONE,
                DATE_REGISTER,
                LAST_LOGIN,
                ACTIVE
            FROM b_user
            WHERE ID IN ({ids_str})
            """
            
            cursor.execute(query)
            users = cursor.fetchall()
            
            print(f"📦 Найдено пользователей в production: {len(users)}")
            return users
            
    except Exception as e:
        print(f"❌ Ошибка получения пользователей: {e}")
        return []

def transform_user_data(mysql_user):
    """Преобразовать данные пользователя из MySQL в формат Supabase"""
    
    # Формируем полное имя
    name_parts = []
    if mysql_user.get('NAME'):
        name_parts.append(mysql_user['NAME'])
    if mysql_user.get('LAST_NAME'):
        name_parts.append(mysql_user['LAST_NAME'])
    
    full_name = ' '.join(name_parts) if name_parts else mysql_user.get('LOGIN', f"User {mysql_user['ID']}")
    
    # Обработка даты регистрации
    created_at = None
    if mysql_user.get('DATE_REGISTER'):
        if isinstance(mysql_user['DATE_REGISTER'], datetime):
            created_at = mysql_user['DATE_REGISTER'].isoformat()
        else:
            created_at = str(mysql_user['DATE_REGISTER'])
    else:
        created_at = datetime.utcnow().isoformat()
    
    # Обработка последнего логина
    last_login = None
    if mysql_user.get('LAST_LOGIN'):
        if isinstance(mysql_user['LAST_LOGIN'], datetime):
            last_login = mysql_user['LAST_LOGIN'].isoformat()
        else:
            last_login = str(mysql_user['LAST_LOGIN'])
    
    # Формируем данные для Supabase
    supabase_user = {
        'id': str(uuid.uuid4()),  # Генерируем новый UUID
        'bitrix_user_id': int(mysql_user['ID']),  # Сохраняем оригинальный ID
        'email': mysql_user.get('EMAIL'),
        'phone': mysql_user.get('PERSONAL_PHONE'),
        'name': full_name,
        'is_active': mysql_user.get('ACTIVE') == 'Y',
        'created_at': created_at,
        'last_login': last_login,
    }
    
    return supabase_user

def import_users_to_supabase(supabase, users_data):
    """Импорт пользователей в Supabase"""
    success_count = 0
    error_count = 0
    
    for user_data in users_data:
        try:
            # Проверяем, существует ли пользователь
            existing = supabase.table('users').select('id').eq('bitrix_user_id', user_data['bitrix_user_id']).execute()
            
            if existing.data:
                print(f"  ⚠️  Пользователь {user_data['bitrix_user_id']} уже существует, пропускаем")
                continue
            
            # Вставляем нового пользователя
            result = supabase.table('users').insert(user_data).execute()
            
            if result.data:
                print(f"  ✅ Пользователь {user_data['bitrix_user_id']} ({user_data['name']}) импортирован")
                success_count += 1
            else:
                print(f"  ❌ Не удалось импортировать пользователя {user_data['bitrix_user_id']}")
                error_count += 1
                
        except Exception as e:
            print(f"  ❌ Ошибка импорта пользователя {user_data['bitrix_user_id']}: {e}")
            error_count += 1
    
    return success_count, error_count

def main():
    print("🚀 Начинаем импорт отсутствующих пользователей")
    print("=" * 60)
    
    # Отсутствующие пользователи из анализа заказов
    missing_user_ids = [171532, 171533, 171534, 171535]
    
    if len(sys.argv) > 1:
        # Можно передать дополнительные ID как аргументы
        additional_ids = [int(uid) for uid in sys.argv[1:]]
        missing_user_ids.extend(additional_ids)
        missing_user_ids = list(set(missing_user_ids))  # Убираем дубликаты
    
    print(f"📋 Пользователи для импорта: {missing_user_ids}")
    
    # Подключения
    mysql_conn = connect_to_production()
    if not mysql_conn:
        return
    
    supabase = connect_to_supabase()
    if not supabase:
        mysql_conn.close()
        return
    
    try:
        # Получаем данные пользователей из production
        print("\n📥 Получаем данные из production MySQL...")
        users_data = get_missing_users(mysql_conn, missing_user_ids)
        
        if not users_data:
            print("❌ Пользователи не найдены")
            return
        
        # Преобразуем данные
        print("\n🔄 Преобразуем данные...")
        supabase_users = []
        for mysql_user in users_data:
            supabase_user = transform_user_data(mysql_user)
            supabase_users.append(supabase_user)
            print(f"  • {mysql_user['ID']}: {supabase_user['name']} ({supabase_user['email']})")
        
        # Импортируем в Supabase
        print(f"\n📤 Импортируем {len(supabase_users)} пользователей в Supabase...")
        success_count, error_count = import_users_to_supabase(supabase, supabase_users)
        
        print(f"\n" + "=" * 60)
        print(f"📊 ИТОГИ ИМПОРТА:")
        print(f"  ✅ Успешно: {success_count}")
        print(f"  ❌ Ошибок: {error_count}")
        print(f"  📍 Всего обработано: {len(supabase_users)}")
        
        if success_count > 0:
            print(f"\n🎉 Пользователи импортированы! Теперь можно тестировать миграцию заказов.")
        
    finally:
        mysql_conn.close()
        print("\n✅ Подключения закрыты")

if __name__ == "__main__":
    main()