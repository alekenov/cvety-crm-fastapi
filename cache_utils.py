"""
Простое in-memory кэширование для оптимизации производительности
"""
import time
from typing import Any, Optional, Dict

class SimpleCache:
    """Простой in-memory кэш с TTL"""
    
    def __init__(self):
        self._cache: Dict[str, Dict] = {}
    
    def get(self, key: str) -> Optional[Any]:
        """Получить значение из кэша"""
        if key not in self._cache:
            return None
            
        entry = self._cache[key]
        
        # Проверяем TTL
        if time.time() > entry['expires']:
            del self._cache[key]
            return None
            
        entry['hits'] += 1
        return entry['value']
    
    def set(self, key: str, value: Any, ttl_seconds: int = 60):
        """Сохранить значение в кэш"""
        self._cache[key] = {
            'value': value,
            'expires': time.time() + ttl_seconds,
            'created': time.time(),
            'hits': 0
        }
    
    def invalidate(self, key: str):
        """Удалить ключ из кэша"""
        if key in self._cache:
            del self._cache[key]
    
    def clear(self):
        """Очистить весь кэш"""
        self._cache.clear()
    
    def stats(self) -> Dict:
        """Статистика кэша"""
        now = time.time()
        active_keys = 0
        total_hits = 0
        
        for key, entry in self._cache.items():
            if now <= entry['expires']:
                active_keys += 1
                total_hits += entry['hits']
        
        return {
            'active_keys': active_keys,
            'total_keys': len(self._cache),
            'total_hits': total_hits,
            'hit_ratio': total_hits / max(1, active_keys)
        }

# Глобальный экземпляр кэша
simple_cache = SimpleCache()

def cache_key(*args) -> str:
    """Создает ключ кэша из аргументов"""
    return ':'.join(str(arg) for arg in args)