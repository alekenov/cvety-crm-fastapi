"""
Connection Pool для оптимизации подключений к базам данных
Поддержка MySQL и Supabase с автоматическим управлением соединениями
"""

import asyncio
import pymysql
from typing import Dict, Any, Optional, AsyncContextManager
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from threading import Lock
import time

from supabase import create_client, Client
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config
from core.exceptions import DatabaseConnectionError, DatabaseQueryError, ConfigurationError

# Адаптер для совместимости со старой структурой настроек
class DatabaseConfig:
    def __init__(self):
        self.supabase_url = config.Config.SUPABASE_URL
        self.supabase_service_key = config.Config.SUPABASE_SERVICE_KEY
        
    @property
    def mysql_config(self):
        return {
            'host': config.Config.MYSQL_HOST,
            'port': config.Config.MYSQL_PORT,
            'user': config.Config.MYSQL_USER,
            'password': config.Config.MYSQL_PASSWORD,
            'database': config.Config.MYSQL_DATABASE,
            'charset': 'utf8mb4',
            'autocommit': True
        }
        
    @property
    def production_mysql_config(self):
        return {
            'host': '185.125.90.141',  # Production host
            'port': 3306,
            'user': 'root',
            'password': '',  # Пустой пароль из claude.md
            'database': 'dbcvety',
            'charset': 'utf8mb4',
            'autocommit': True
        }

class ProductionConfig:
    max_connections = 30

# Создаем экземпляры для совместимости
settings = type('Settings', (), {
    'database': DatabaseConfig(),
    'production': ProductionConfig()
})()

logger = logging.getLogger(__name__)

@dataclass
class PoolStats:
    """Статистика пула соединений"""
    active_connections: int = 0
    idle_connections: int = 0
    total_created: int = 0
    total_closed: int = 0
    last_activity: Optional[datetime] = None
    errors_count: int = 0

class MySQLConnectionPool:
    """Пул соединений для MySQL"""
    
    def __init__(self, config: Dict[str, Any], max_connections: int = 10, min_connections: int = 2):
        self.config = config
        self.max_connections = max_connections
        self.min_connections = min_connections
        self._pool: list = []
        self._lock = Lock()
        self._stats = PoolStats()
        self._last_cleanup = datetime.now()
        
        # Инициализируем минимальное количество соединений
        self._initialize_pool()
    
    def _initialize_pool(self):
        """Создает минимальное количество соединений"""
        for _ in range(self.min_connections):
            try:
                conn = self._create_connection()
                self._pool.append({
                    'connection': conn,
                    'created_at': datetime.now(),
                    'last_used': datetime.now(),
                    'in_use': False
                })
                self._stats.total_created += 1
                self._stats.idle_connections += 1
            except Exception as e:
                logger.error(f"Failed to initialize MySQL connection: {e}")
                raise DatabaseConnectionError("MySQL", self.config.get('host'))
    
    def _create_connection(self):
        """Создает новое соединение с MySQL"""
        try:
            connection = pymysql.connect(
                host=self.config['host'],
                port=self.config['port'],
                user=self.config['user'],
                password=self.config['password'],
                database=self.config['database'],
                charset=self.config.get('charset', 'utf8mb4'),
                autocommit=self.config.get('autocommit', True),
                connect_timeout=30,
                read_timeout=60,
                write_timeout=60
            )
            return connection
        except Exception as e:
            self._stats.errors_count += 1
            raise DatabaseConnectionError("MySQL", self.config.get('host'), original_error=str(e))
    
    def _is_connection_valid(self, connection) -> bool:
        """Проверяет валидность соединения"""
        try:
            connection.ping(reconnect=False)
            return True
        except:
            return False
    
    def _cleanup_pool(self):
        """Очищает устаревшие соединения"""
        current_time = datetime.now()
        
        # Очищаем каждые 5 минут
        if current_time - self._last_cleanup < timedelta(minutes=5):
            return
        
        with self._lock:
            new_pool = []
            for pool_item in self._pool:
                # Удаляем соединения старше 1 часа или неактивные более 30 минут
                age = current_time - pool_item['created_at']
                idle_time = current_time - pool_item['last_used']
                
                if (not pool_item['in_use'] and 
                    (age > timedelta(hours=1) or idle_time > timedelta(minutes=30)) and
                    len(new_pool) >= self.min_connections):
                    
                    try:
                        pool_item['connection'].close()
                        self._stats.total_closed += 1
                        self._stats.idle_connections -= 1
                    except:
                        pass
                else:
                    new_pool.append(pool_item)
            
            self._pool = new_pool
            self._last_cleanup = current_time
    
    @asynccontextmanager
    async def get_connection(self):
        """Получает соединение из пула"""
        self._cleanup_pool()
        
        connection_item = None
        
        with self._lock:
            # Ищем свободное соединение
            for item in self._pool:
                if not item['in_use'] and self._is_connection_valid(item['connection']):
                    item['in_use'] = True
                    item['last_used'] = datetime.now()
                    connection_item = item
                    self._stats.active_connections += 1
                    self._stats.idle_connections -= 1
                    break
            
            # Если нет свободных, создаем новое (если лимит позволяет)
            if not connection_item and len(self._pool) < self.max_connections:
                try:
                    new_conn = self._create_connection()
                    connection_item = {
                        'connection': new_conn,
                        'created_at': datetime.now(),
                        'last_used': datetime.now(),
                        'in_use': True
                    }
                    self._pool.append(connection_item)
                    self._stats.total_created += 1
                    self._stats.active_connections += 1
                except Exception as e:
                    raise DatabaseConnectionError("MySQL", self.config.get('host'), original_error=str(e))
        
        if not connection_item:
            raise DatabaseConnectionError("MySQL", details={'reason': 'Pool exhausted'})
        
        try:
            self._stats.last_activity = datetime.now()
            yield connection_item['connection']
        finally:
            # Возвращаем соединение в пул
            with self._lock:
                if connection_item:
                    connection_item['in_use'] = False
                    self._stats.active_connections -= 1
                    self._stats.idle_connections += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику пула"""
        return {
            'active_connections': self._stats.active_connections,
            'idle_connections': self._stats.idle_connections,
            'total_connections': len(self._pool),
            'total_created': self._stats.total_created,
            'total_closed': self._stats.total_closed,
            'last_activity': self._stats.last_activity.isoformat() if self._stats.last_activity else None,
            'errors_count': self._stats.errors_count,
            'max_connections': self.max_connections
        }
    
    def close_all(self):
        """Закрывает все соединения"""
        with self._lock:
            for item in self._pool:
                try:
                    item['connection'].close()
                    self._stats.total_closed += 1
                except:
                    pass
            self._pool.clear()
            self._stats.active_connections = 0
            self._stats.idle_connections = 0

class SupabaseConnectionPool:
    """Пул клиентов для Supabase"""
    
    def __init__(self, url: str, service_key: str, max_clients: int = 5):
        self.url = url
        self.service_key = service_key
        self.max_clients = max_clients
        self._clients: list = []
        self._lock = Lock()
        self._stats = PoolStats()
        
        # Проверяем конфигурацию
        if not url or not service_key:
            raise ConfigurationError("Supabase URL and service key are required")
        
        # Создаем начальный клиент
        self._initialize_pool()
    
    def _initialize_pool(self):
        """Создает начальный пул клиентов"""
        try:
            client = create_client(self.url, self.service_key)
            self._clients.append({
                'client': client,
                'created_at': datetime.now(),
                'last_used': datetime.now(),
                'in_use': False
            })
            self._stats.total_created += 1
            self._stats.idle_connections += 1
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            raise DatabaseConnectionError("Supabase", self.url)
    
    def _create_client(self) -> Client:
        """Создает нового клиента Supabase"""
        try:
            return create_client(self.url, self.service_key)
        except Exception as e:
            self._stats.errors_count += 1
            raise DatabaseConnectionError("Supabase", self.url, original_error=str(e))
    
    @asynccontextmanager
    async def get_client(self):
        """Получает клиента из пула"""
        client_item = None
        
        with self._lock:
            # Ищем свободного клиента
            for item in self._clients:
                if not item['in_use']:
                    item['in_use'] = True
                    item['last_used'] = datetime.now()
                    client_item = item
                    self._stats.active_connections += 1
                    self._stats.idle_connections -= 1
                    break
            
            # Создаем нового клиента если нужно
            if not client_item and len(self._clients) < self.max_clients:
                try:
                    new_client = self._create_client()
                    client_item = {
                        'client': new_client,
                        'created_at': datetime.now(),
                        'last_used': datetime.now(),
                        'in_use': True
                    }
                    self._clients.append(client_item)
                    self._stats.total_created += 1
                    self._stats.active_connections += 1
                except Exception as e:
                    raise DatabaseConnectionError("Supabase", self.url, original_error=str(e))
        
        if not client_item:
            # Ждем освобождения клиента
            await asyncio.sleep(0.1)
            async with self.get_client() as client:
                yield client
            return
        
        try:
            self._stats.last_activity = datetime.now()
            yield client_item['client']
        finally:
            # Возвращаем клиента в пул
            with self._lock:
                if client_item:
                    client_item['in_use'] = False
                    self._stats.active_connections -= 1
                    self._stats.idle_connections += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику пула"""
        return {
            'active_connections': self._stats.active_connections,
            'idle_connections': self._stats.idle_connections,
            'total_connections': len(self._clients),
            'total_created': self._stats.total_created,
            'errors_count': self._stats.errors_count,
            'max_clients': self.max_clients,
            'last_activity': self._stats.last_activity.isoformat() if self._stats.last_activity else None
        }

class DatabasePoolManager:
    """Менеджер пулов соединений"""
    
    def __init__(self):
        self._mysql_local_pool: Optional[MySQLConnectionPool] = None
        self._mysql_production_pool: Optional[MySQLConnectionPool] = None
        self._supabase_pool: Optional[SupabaseConnectionPool] = None
        self._initialized = False
    
    def initialize(self):
        """Инициализирует все пулы"""
        if self._initialized:
            return
        
        try:
            # MySQL локальный пул
            self._mysql_local_pool = MySQLConnectionPool(
                settings.database.mysql_config,
                max_connections=settings.production.max_connections // 3,
                min_connections=2
            )
            
            # MySQL production пул
            self._mysql_production_pool = MySQLConnectionPool(
                settings.database.production_mysql_config,
                max_connections=settings.production.max_connections // 3,
                min_connections=1
            )
            
            # Supabase пул
            self._supabase_pool = SupabaseConnectionPool(
                settings.database.supabase_url,
                settings.database.supabase_service_key,
                max_clients=settings.production.max_connections // 3
            )
            
            self._initialized = True
            logger.info("Database pools initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database pools: {e}")
            raise ConfigurationError("Database pool initialization failed", original_error=str(e))
    
    @asynccontextmanager
    async def mysql_local(self):
        """Получает соединение к локальной MySQL"""
        if not self._initialized:
            self.initialize()
        async with self._mysql_local_pool.get_connection() as conn:
            yield conn
    
    @asynccontextmanager
    async def mysql_production(self):
        """Получает соединение к production MySQL"""
        if not self._initialized:
            self.initialize()
        async with self._mysql_production_pool.get_connection() as conn:
            yield conn
    
    @asynccontextmanager
    async def supabase(self):
        """Получает клиента Supabase"""
        if not self._initialized:
            self.initialize()
        async with self._supabase_pool.get_client() as client:
            yield client
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику всех пулов"""
        if not self._initialized:
            return {'status': 'not_initialized'}
        
        return {
            'mysql_local': self._mysql_local_pool.get_stats(),
            'mysql_production': self._mysql_production_pool.get_stats(),
            'supabase': self._supabase_pool.get_stats(),
            'total_connections': (
                self._mysql_local_pool.get_stats()['total_connections'] +
                self._mysql_production_pool.get_stats()['total_connections'] +
                self._supabase_pool.get_stats()['total_connections']
            )
        }
    
    def close_all(self):
        """Закрывает все пулы"""
        if self._mysql_local_pool:
            self._mysql_local_pool.close_all()
        if self._mysql_production_pool:
            self._mysql_production_pool.close_all()
        
        self._initialized = False
        logger.info("All database pools closed")

# Глобальный менеджер пулов
pool_manager = DatabasePoolManager()