"""
Webhook deduplication module
Prevents duplicate webhook processing and notification spam
"""

import json
import hashlib
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class WebhookDeduplicator:
    """In-memory webhook deduplication cache"""
    
    def __init__(self, cache_ttl: int = 300):
        """
        Initialize deduplicator
        
        Args:
            cache_ttl: Time to live for cache entries in seconds (default 5 minutes)
        """
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._notification_cache: Dict[str, float] = {}  # order_id -> last_notification_time
    
    def _cleanup_cache(self):
        """Remove expired cache entries"""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self._cache.items() 
            if current_time - entry['timestamp'] > self.cache_ttl
        ]
        
        for key in expired_keys:
            del self._cache[key]
        
        # Clean notification cache (keep 1 hour history)
        notification_expired = [
            order_id for order_id, timestamp in self._notification_cache.items()
            if current_time - timestamp > 3600
        ]
        
        for order_id in notification_expired:
            del self._notification_cache[order_id]
    
    def _create_cache_key(self, order_id: str, webhook_data: Dict[str, Any]) -> str:
        """
        Create a cache key based on order ID and critical webhook data
        
        Args:
            order_id: Order ID from webhook
            webhook_data: Full webhook data
            
        Returns:
            Cache key string
        """
        # Extract fields that matter for deduplication
        critical_fields = {
            'STATUS_ID': webhook_data.get('STATUS_ID'),
            'VERSION': webhook_data.get('VERSION'),
            'DATE_UPDATE': webhook_data.get('DATE_UPDATE'),
            'PRICE': webhook_data.get('PRICE'),
            'CANCELED': webhook_data.get('CANCELED'),
            'PAYED': webhook_data.get('PAYED')
        }
        
        # Create hash of critical fields
        data_string = json.dumps(critical_fields, sort_keys=True)
        data_hash = hashlib.md5(data_string.encode()).hexdigest()[:10]
        
        return f"order_{order_id}_{data_hash}"
    
    def should_process_webhook(self, event: str, order_id: str, webhook_data: Dict[str, Any]) -> bool:
        """
        Check if webhook should be processed
        
        Args:
            event: Webhook event type
            order_id: Order ID
            webhook_data: Webhook data
            
        Returns:
            True if webhook should be processed, False if it's a duplicate
        """
        self._cleanup_cache()
        
        cache_key = self._create_cache_key(order_id, webhook_data)
        current_time = time.time()
        
        # Check if we've seen this exact webhook recently
        if cache_key in self._cache:
            cached_entry = self._cache[cache_key]
            time_diff = current_time - cached_entry['timestamp']
            
            logger.info(f"Duplicate webhook detected for order {order_id}: "
                       f"last seen {time_diff:.1f}s ago, cache_key: {cache_key}")
            
            # If it's within the TTL window, it's a duplicate
            if time_diff < self.cache_ttl:
                return False
        
        # Store this webhook in cache
        self._cache[cache_key] = {
            'timestamp': current_time,
            'event': event,
            'order_id': order_id,
            'version': webhook_data.get('VERSION'),
            'status_id': webhook_data.get('STATUS_ID')
        }
        
        logger.info(f"New webhook for order {order_id} accepted, cache_key: {cache_key}")
        return True
    
    def should_send_notification(self, order_id: str, event: str) -> bool:
        """
        Check if notification should be sent (rate limiting)
        
        Args:
            order_id: Order ID
            event: Event type
            
        Returns:
            True if notification should be sent
        """
        current_time = time.time()
        
        # Check last notification time for this order
        if order_id in self._notification_cache:
            time_diff = current_time - self._notification_cache[order_id]
            
            if time_diff < self.cache_ttl:
                logger.info(f"Notification rate limited for order {order_id}: "
                           f"last sent {time_diff:.1f}s ago")
                return False
        
        # Update notification cache
        self._notification_cache[order_id] = current_time
        logger.info(f"Notification allowed for order {order_id}")
        return True
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get deduplication cache statistics"""
        return {
            'cache_size': len(self._cache),
            'notification_cache_size': len(self._notification_cache),
            'cache_ttl': self.cache_ttl,
            'current_time': datetime.now().isoformat()
        }
    
    def clear_cache(self):
        """Clear all cache entries (for testing)"""
        self._cache.clear()
        self._notification_cache.clear()
        logger.info("Webhook deduplication cache cleared")

# Global instance
webhook_deduplicator = WebhookDeduplicator()