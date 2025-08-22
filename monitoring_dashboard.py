#!/usr/bin/env python3
"""
Мониторинг dashboard для системы синхронизации
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

class SyncMonitoringDashboard:
    def __init__(self):
        self.supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    
    def check_fastapi_status(self):
        """Проверка статуса FastAPI сервера"""
        try:
            response = requests.get("http://localhost:8001/health", timeout=5)
            return {"status": "healthy", "code": response.status_code}
        except:
            try:
                # Пробуем webhook endpoint
                response = requests.post("http://localhost:8001/webhooks/bitrix/order", 
                                       json={"test": True}, timeout=5)
                return {"status": "webhook_accessible", "code": response.status_code}
            except:
                return {"status": "down", "code": None}
    
    def check_supabase_connection(self):
        """Проверка подключения к Supabase"""
        try:
            result = self.supabase.table('orders').select('id').limit(1).execute()
            return {"status": "connected", "data_available": len(result.data) > 0}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def get_sync_statistics(self):
        """Получение статистики синхронизации"""
        try:
            # Статистика за последние 24 часа
            yesterday = (datetime.now() - timedelta(days=1)).isoformat()
            
            result = self.supabase.rpc('get_sync_stats', {
                'since_time': yesterday
            }).execute()
            
            if result.data:
                return result.data[0]
            else:
                # Fallback - простые счетчики
                total_orders = self.supabase.table('orders').select('id', count='exact').execute()
                recent_orders = self.supabase.table('orders').select('id', count='exact')\
                    .gte('created_at', yesterday).execute()
                
                return {
                    'total_orders': total_orders.count,
                    'recent_orders': recent_orders.count,
                    'sync_success_rate': 'N/A'
                }
                
        except Exception as e:
            return {"error": str(e)}
    
    def check_production_webhook_status(self):
        """Проверка статуса production webhook"""
        try:
            # Проверяем логи webhook на сервере
            import subprocess
            result = subprocess.run([
                'ssh', 'root@185.125.90.141', 
                'tail -n 5 /tmp/bitrix_webhook.log 2>/dev/null || echo "No logs"'
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                return {"status": "accessible", "recent_logs": result.stdout.strip()}
            else:
                return {"status": "ssh_error", "error": result.stderr}
        except:
            return {"status": "unknown", "note": "Cannot access production logs"}
    
    def check_reverse_sync_status(self):
        """Проверка статуса обратной синхронизации"""
        try:
            # Проверяем логи cron
            if os.path.exists('/tmp/reverse_sync_cron.log'):
                with open('/tmp/reverse_sync_cron.log', 'r') as f:
                    lines = f.readlines()
                    last_lines = ''.join(lines[-3:]) if lines else "No logs"
                return {"status": "active", "recent_logs": last_lines}
            else:
                return {"status": "no_logs", "note": "Cron logs not found"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def display_dashboard(self):
        """Отображение dashboard"""
        print("🚀 СИСТЕМА СИНХРОНИЗАЦИИ - MONITORING DASHBOARD")
        print("=" * 60)
        print(f"⏰ Время проверки: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # FastAPI Status
        print("🔧 FASTAPI SERVER:")
        fastapi_status = self.check_fastapi_status()
        if fastapi_status["status"] == "healthy":
            print("  ✅ Сервер работает (Health endpoint доступен)")
        elif fastapi_status["status"] == "webhook_accessible":
            print("  ⚠️ Webhook endpoint доступен (Health endpoint отсутствует)")
        else:
            print("  ❌ Сервер недоступен")
        print()
        
        # Supabase Status
        print("🗄️ SUPABASE DATABASE:")
        supabase_status = self.check_supabase_connection()
        if supabase_status["status"] == "connected":
            print("  ✅ Подключение активно")
            if supabase_status["data_available"]:
                print("  ✅ Данные доступны")
        else:
            print(f"  ❌ Ошибка подключения: {supabase_status.get('error', 'Unknown')}")
        print()
        
        # Sync Statistics
        print("📊 СТАТИСТИКА СИНХРОНИЗАЦИИ:")
        stats = self.get_sync_statistics()
        if 'error' not in stats:
            print(f"  📦 Всего заказов: {stats.get('total_orders', 'N/A')}")
            print(f"  🕐 За последние 24ч: {stats.get('recent_orders', 'N/A')}")
            print(f"  ✅ Success rate: {stats.get('sync_success_rate', 'N/A')}")
        else:
            print(f"  ❌ Ошибка получения статистики: {stats['error']}")
        print()
        
        # Production Webhook Status
        print("🌐 PRODUCTION WEBHOOK:")
        webhook_status = self.check_production_webhook_status()
        if webhook_status["status"] == "accessible":
            print("  ✅ Webhook развернут и доступен")
            if webhook_status.get("recent_logs"):
                print("  📄 Последние логи:")
                for line in webhook_status["recent_logs"].split('\n')[-2:]:
                    if line.strip():
                        print(f"    {line}")
        else:
            print(f"  ⚠️ Статус: {webhook_status['status']}")
        print()
        
        # Reverse Sync Status
        print("🔄 ОБРАТНАЯ СИНХРОНИЗАЦИЯ:")
        reverse_status = self.check_reverse_sync_status()
        if reverse_status["status"] == "active":
            print("  ✅ Cron job активен")
            if reverse_status.get("recent_logs"):
                print("  📄 Последние логи:")
                for line in reverse_status["recent_logs"].split('\n')[-2:]:
                    if line.strip():
                        print(f"    {line}")
        else:
            print(f"  ⚠️ Статус: {reverse_status['status']}")
        print()
        
        # System Health Summary
        print("🎯 ОБЩИЙ СТАТУС СИСТЕМЫ:")
        all_healthy = (
            fastapi_status["status"] in ["healthy", "webhook_accessible"] and
            supabase_status["status"] == "connected" and
            webhook_status["status"] == "accessible" and
            reverse_status["status"] == "active"
        )
        
        if all_healthy:
            print("  🟢 ВСЕ СИСТЕМЫ РАБОТАЮТ")
            print("  ✅ Bidirectional синхронизация готова к production")
        else:
            print("  🟡 ЧАСТИЧНАЯ РАБОТОСПОСОБНОСТЬ")
            print("  ⚠️ Некоторые компоненты требуют внимания")
        
        print("=" * 60)
    
    def check_sync_health(self):
        """
        Проверяет здоровье синхронизации и возвращает метрики
        
        Returns:
            dict с метриками здоровья системы
        """
        try:
            # Получаем статистику за последний час
            one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
            
            # Общие статистики
            result = self.supabase.table('sync_log')\
                .select('status', count='exact')\
                .gte('created_at', one_hour_ago)\
                .execute()
            
            total_syncs = result.count
            
            # Ошибки за час
            errors_result = self.supabase.table('sync_log')\
                .select('*', count='exact')\
                .eq('status', 'error')\
                .gte('created_at', one_hour_ago)\
                .execute()
            
            errors_count = errors_result.count
            
            # Ошибки с датами за час
            date_errors_result = self.supabase.table('sync_log')\
                .select('*', count='exact')\
                .eq('status', 'error')\
                .like('error_message', '%date/time field value out of range%')\
                .gte('created_at', one_hour_ago)\
                .execute()
            
            date_errors_count = date_errors_result.count
            
            # Вычисляем success rate
            success_rate = 0
            if total_syncs > 0:
                success_count = total_syncs - errors_count
                success_rate = (success_count / total_syncs) * 100
            
            # Последние критические ошибки
            critical_errors = self.supabase.table('sync_log')\
                .select('*')\
                .eq('status', 'error')\
                .gte('created_at', one_hour_ago)\
                .order('created_at', desc=True)\
                .limit(3)\
                .execute()
            
            return {
                'timestamp': datetime.now().isoformat(),
                'total_syncs_last_hour': total_syncs,
                'errors_last_hour': errors_count,
                'date_errors_last_hour': date_errors_count,
                'success_rate': success_rate,
                'is_healthy': success_rate >= 95 and errors_count < 10,
                'critical_errors': critical_errors.data,
                'status': 'healthy' if success_rate >= 95 and errors_count < 10 else 'degraded'
            }
            
        except Exception as e:
            print(f"❌ Ошибка проверки здоровья: {e}")
            return {
                'timestamp': datetime.now().isoformat(),
                'error': str(e),
                'status': 'error',
                'is_healthy': False
            }
    
    async def send_health_alert(self, health_metrics: dict):
        """
        Отправляет алерт в Telegram при проблемах
        
        Args:
            health_metrics: Метрики здоровья системы
        """
        try:
            from telegram_notifier import get_notifier
            
            notifier = get_notifier()
            
            # Определяем нужно ли отправлять алерт
            if health_metrics.get('is_healthy', False):
                return  # Система работает нормально
            
            # Формируем сообщение об алерте
            success_rate = health_metrics.get('success_rate', 0)
            errors_count = health_metrics.get('errors_last_hour', 0)
            date_errors = health_metrics.get('date_errors_last_hour', 0)
            
            message = f"🚨 <b>АЛЕРТ: Проблемы синхронизации</b>\n\n"
            message += f"📊 Success rate за час: {success_rate:.1f}%\n"
            message += f"❌ Ошибок за час: {errors_count}\n"
            
            if date_errors > 0:
                message += f"📅 Ошибки с датами: {date_errors}\n"
            
            # Добавляем последние критические ошибки
            critical_errors = health_metrics.get('critical_errors', [])
            if critical_errors:
                message += f"\n⚠️ <b>Последние ошибки:</b>\n"
                for i, error in enumerate(critical_errors[:2], 1):
                    error_msg = error.get('error_message', 'Unknown error')[:100]
                    message += f"{i}. <code>{error_msg}...</code>\n"
            
            message += f"\n🕒 Время: {datetime.now().strftime('%H:%M:%S')}"
            message += f"\n💡 Запустите fix_sync_errors.py для исправления"
            
            # Отправляем всем кто хочет получать алерты об ошибках
            users = await notifier._get_active_users('errors_only')
            
            sent_count = 0
            for user in users:
                if await notifier._send_message(user['chat_id'], message):
                    sent_count += 1
            
            print(f"📤 Алерт отправлен {sent_count} пользователям")
            
        except Exception as e:
            print(f"❌ Ошибка отправки алерта: {e}")
    
    def run_health_check(self):
        """
        Запускает полную проверку здоровья системы с алертами
        """
        print("\n🏥 ПРОВЕРКА ЗДОРОВЬЯ СИСТЕМЫ")
        print("=" * 40)
        
        # Получаем метрики
        health = self.check_sync_health()
        
        print(f"🕒 Время проверки: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📊 Синхронизаций за час: {health.get('total_syncs_last_hour', 0)}")
        print(f"❌ Ошибок за час: {health.get('errors_last_hour', 0)}")
        print(f"📅 Ошибки дат за час: {health.get('date_errors_last_hour', 0)}")
        print(f"✅ Success rate: {health.get('success_rate', 0):.1f}%")
        
        status = health.get('status', 'unknown')
        if status == 'healthy':
            print(f"🟢 Статус: СИСТЕМА ЗДОРОВА")
        elif status == 'degraded':
            print(f"🟡 Статус: ПРОИЗВОДИТЕЛЬНОСТЬ СНИЖЕНА") 
            print(f"💡 Рекомендуется запустить: python3 fix_sync_errors.py")
        else:
            print(f"🔴 Статус: КРИТИЧЕСКИЕ ПРОБЛЕМЫ")
        
        # Отправляем алерт если нужно (асинхронно)
        if not health.get('is_healthy', False):
            try:
                import asyncio
                asyncio.create_task(self.send_health_alert(health))
            except Exception as e:
                print(f"⚠️  Не удалось отправить алерт: {e}")
        
        print("=" * 40)
        
        return health

def main():
    """Основная функция для запуска dashboard или health check"""
    import sys
    
    dashboard = SyncMonitoringDashboard()
    
    # Проверяем аргументы командной строки
    if '--health' in sys.argv:
        dashboard.run_health_check()
    else:
        dashboard.display_dashboard()

if __name__ == "__main__":
    main()