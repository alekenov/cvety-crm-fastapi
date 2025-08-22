"""
Кастомные исключения для системы синхронизации
Централизованная обработка всех типов ошибок
"""

from typing import Dict, Any, Optional
from datetime import datetime
import traceback

class SyncBaseException(Exception):
    """Базовое исключение для всех ошибок синхронизации"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, error_code: Optional[str] = None):
        self.message = message
        self.details = details or {}
        self.error_code = error_code
        self.timestamp = datetime.now()
        self.traceback = traceback.format_exc()
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертирует исключение в словарь для логирования"""
        return {
            'error_type': self.__class__.__name__,
            'message': self.message,
            'error_code': self.error_code,
            'details': self.details,
            'timestamp': self.timestamp.isoformat(),
            'traceback': self.traceback
        }

class DatabaseConnectionError(SyncBaseException):
    """Ошибки подключения к базе данных"""
    
    def __init__(self, db_type: str, host: str = None, **kwargs):
        self.db_type = db_type
        self.host = host
        details = {'db_type': db_type, 'host': host}
        super().__init__(f"Database connection failed: {db_type}", details, "DB_CONNECTION_ERROR")

class DatabaseQueryError(SyncBaseException):
    """Ошибки выполнения SQL запросов"""
    
    def __init__(self, query: str, db_type: str, original_error: str = None, **kwargs):
        self.query = query[:200] + "..." if len(query) > 200 else query  # Обрезаем длинные запросы
        self.db_type = db_type
        details = {'query': self.query, 'db_type': db_type, 'original_error': original_error}
        super().__init__(f"Database query failed in {db_type}", details, "DB_QUERY_ERROR")

class DataTransformationError(SyncBaseException):
    """Ошибки преобразования данных"""
    
    def __init__(self, field_name: str, value: Any, expected_type: str, **kwargs):
        self.field_name = field_name
        self.value = str(value) if value is not None else None
        self.expected_type = expected_type
        details = {'field_name': field_name, 'value': self.value, 'expected_type': expected_type}
        super().__init__(f"Data transformation failed for field '{field_name}'", details, "DATA_TRANSFORM_ERROR")

class ValidationError(SyncBaseException):
    """Ошибки валидации данных"""
    
    def __init__(self, field_name: str, value: Any, validation_rule: str, **kwargs):
        self.field_name = field_name
        self.value = str(value) if value is not None else None
        self.validation_rule = validation_rule
        details = {'field_name': field_name, 'value': self.value, 'validation_rule': validation_rule}
        super().__init__(f"Validation failed for field '{field_name}': {validation_rule}", details, "VALIDATION_ERROR")

class WebhookError(SyncBaseException):
    """Ошибки webhook запросов"""
    
    def __init__(self, endpoint: str, status_code: int = None, response_text: str = None, **kwargs):
        self.endpoint = endpoint
        self.status_code = status_code
        self.response_text = response_text[:500] + "..." if response_text and len(response_text) > 500 else response_text
        details = {'endpoint': endpoint, 'status_code': status_code, 'response_text': self.response_text}
        super().__init__(f"Webhook request failed to {endpoint}", details, "WEBHOOK_ERROR")

class SyncConflictError(SyncBaseException):
    """Ошибки конфликтов при синхронизации"""
    
    def __init__(self, order_id: str, conflict_type: str, local_value: Any = None, remote_value: Any = None, **kwargs):
        self.order_id = order_id
        self.conflict_type = conflict_type
        self.local_value = str(local_value) if local_value is not None else None
        self.remote_value = str(remote_value) if remote_value is not None else None
        details = {
            'order_id': order_id, 
            'conflict_type': conflict_type,
            'local_value': self.local_value,
            'remote_value': self.remote_value
        }
        super().__init__(f"Sync conflict for order {order_id}: {conflict_type}", details, "SYNC_CONFLICT_ERROR")

class RateLimitError(SyncBaseException):
    """Ошибки превышения лимитов"""
    
    def __init__(self, service: str, limit_type: str, current_count: int = None, limit: int = None, **kwargs):
        self.service = service
        self.limit_type = limit_type
        self.current_count = current_count
        self.limit = limit
        details = {
            'service': service,
            'limit_type': limit_type,
            'current_count': current_count,
            'limit': limit
        }
        super().__init__(f"Rate limit exceeded for {service}: {limit_type}", details, "RATE_LIMIT_ERROR")

class ConfigurationError(SyncBaseException):
    """Ошибки конфигурации"""
    
    def __init__(self, config_key: str, expected_type: str = None, **kwargs):
        self.config_key = config_key
        self.expected_type = expected_type
        details = {'config_key': config_key, 'expected_type': expected_type}
        super().__init__(f"Configuration error: {config_key}", details, "CONFIG_ERROR")

class TimeoutError(SyncBaseException):
    """Ошибки таймаутов"""
    
    def __init__(self, operation: str, timeout_seconds: int, **kwargs):
        self.operation = operation
        self.timeout_seconds = timeout_seconds
        details = {'operation': operation, 'timeout_seconds': timeout_seconds}
        super().__init__(f"Operation timed out: {operation} ({timeout_seconds}s)", details, "TIMEOUT_ERROR")

class RetryExhaustedError(SyncBaseException):
    """Ошибки исчерпания попыток повтора"""
    
    def __init__(self, operation: str, max_retries: int, last_error: str = None, **kwargs):
        self.operation = operation
        self.max_retries = max_retries
        self.last_error = last_error
        details = {'operation': operation, 'max_retries': max_retries, 'last_error': last_error}
        super().__init__(f"Max retries ({max_retries}) exhausted for operation: {operation}", details, "RETRY_EXHAUSTED_ERROR")

# Утилиты для работы с исключениями
class ErrorHandler:
    """Централизованный обработчик ошибок"""
    
    @staticmethod
    def handle_database_error(e: Exception, db_type: str, query: str = None) -> SyncBaseException:
        """Обрабатывает ошибки базы данных"""
        if "connection" in str(e).lower() or "connect" in str(e).lower():
            return DatabaseConnectionError(db_type=db_type, original_error=str(e))
        elif query:
            return DatabaseQueryError(query=query, db_type=db_type, original_error=str(e))
        else:
            return SyncBaseException(f"Database error in {db_type}: {str(e)}", {'db_type': db_type}, "DB_ERROR")
    
    @staticmethod
    def handle_http_error(e: Exception, endpoint: str) -> WebhookError:
        """Обрабатывает HTTP ошибки"""
        status_code = getattr(e, 'status_code', None) or getattr(e, 'response', {}).get('status_code')
        response_text = getattr(e, 'text', None) or str(e)
        return WebhookError(endpoint=endpoint, status_code=status_code, response_text=response_text)
    
    @staticmethod
    def create_summary(errors: list) -> Dict[str, Any]:
        """Создает сводку по ошибкам"""
        if not errors:
            return {'total': 0, 'by_type': {}, 'critical_count': 0}
        
        error_types = {}
        critical_errors = 0
        
        for error in errors:
            if isinstance(error, SyncBaseException):
                error_type = error.__class__.__name__
                error_types[error_type] = error_types.get(error_type, 0) + 1
                
                # Критические ошибки
                if isinstance(error, (DatabaseConnectionError, ConfigurationError, RetryExhaustedError)):
                    critical_errors += 1
            else:
                error_types['UnknownError'] = error_types.get('UnknownError', 0) + 1
        
        return {
            'total': len(errors),
            'by_type': error_types,
            'critical_count': critical_errors,
            'needs_attention': critical_errors > 0
        }