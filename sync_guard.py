"""
Sync Guard - prevents feedback loops between webhook processing and sync-back
"""

import time
from typing import Set
import threading
import logging

logger = logging.getLogger(__name__)

class SyncGuard:
    """Guard against sync-back operations during webhook processing"""
    
    def __init__(self, pause_duration: int = 60):
        """
        Initialize sync guard
        
        Args:
            pause_duration: How long to pause sync-back after webhook processing (seconds)
        """
        self.pause_duration = pause_duration
        self._paused_orders: Set[str] = set()  # order IDs currently paused
        self._pause_times: dict[str, float] = {}  # order_id -> pause_end_time
        self._lock = threading.Lock()
    
    def pause_sync_back(self, order_id: str):
        """
        Pause sync-back for a specific order (called when processing webhook)
        
        Args:
            order_id: Bitrix order ID to pause sync-back for
        """
        with self._lock:
            str_order_id = str(order_id)
            self._paused_orders.add(str_order_id)
            self._pause_times[str_order_id] = time.time() + self.pause_duration
            logger.info(f"Sync-back paused for order {order_id} for {self.pause_duration}s")
    
    def is_sync_back_allowed(self, order_id: str) -> bool:
        """
        Check if sync-back is allowed for an order
        
        Args:
            order_id: Bitrix order ID to check
            
        Returns:
            True if sync-back is allowed, False if paused
        """
        with self._lock:
            str_order_id = str(order_id)
            
            # Clean up expired pauses
            current_time = time.time()
            expired_orders = [
                oid for oid, pause_end in self._pause_times.items()
                if current_time > pause_end
            ]
            
            for oid in expired_orders:
                self._paused_orders.discard(oid)
                del self._pause_times[oid]
                logger.info(f"Sync-back pause expired for order {oid}")
            
            # Check if this order is paused
            if str_order_id in self._paused_orders:
                remaining = self._pause_times[str_order_id] - current_time
                logger.info(f"Sync-back blocked for order {order_id} (remaining: {remaining:.1f}s)")
                return False
            
            return True
    
    def get_stats(self) -> dict:
        """Get current sync guard statistics"""
        with self._lock:
            return {
                'paused_orders_count': len(self._paused_orders),
                'paused_orders': list(self._paused_orders),
                'pause_duration': self.pause_duration
            }
    
    def clear_all_pauses(self):
        """Clear all pauses (for testing)"""
        with self._lock:
            self._paused_orders.clear()
            self._pause_times.clear()
            logger.info("All sync-back pauses cleared")

# Global instance
sync_guard = SyncGuard(pause_duration=60)  # 1 minute pause after webhook processing