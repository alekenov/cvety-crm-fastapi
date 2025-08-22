import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Configuration settings for the CRM application"""
    
    # Supabase settings
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY") 
    SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")  # Service key for full access
    
    # MySQL settings (for florists data from Bitrix)
    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "cvety123")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "cvety_db")
    
    # Local development settings
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", 8001))
    
    # App settings
    APP_TITLE = "CRM System - Cvety.kz"
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    
    # Webhook settings
    WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "secret-webhook-token-2024")
    
    # Bitrix API settings for reverse synchronization
    BITRIX_API_URL = os.getenv("BITRIX_API_URL", "https://cvety.kz/supabase-reverse-sync.php")
    BITRIX_API_TOKEN = os.getenv("BITRIX_API_TOKEN", "cvety_reverse_sync_token_2025_secure_key_789")
    BITRIX_SYNC_ENABLED = os.getenv("BITRIX_SYNC_ENABLED", "true").lower() == "true"
    
    # Legacy sync settings
    SYNC_ENABLED = os.getenv("SYNC_ENABLED", "true").lower() == "true"
    
    # Telegram Bot settings
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_NOTIFICATIONS_ENABLED = os.getenv("TELEGRAM_NOTIFICATIONS_ENABLED", "true").lower() == "true"
    TELEGRAM_ADMIN_IDS = [int(id.strip()) for id in os.getenv("TELEGRAM_ADMIN_IDS", "").split(",") if id.strip()]
    
    # Webhook deduplication settings
    WEBHOOK_CACHE_TTL = int(os.getenv("WEBHOOK_CACHE_TTL", 300))  # 5 minutes
    NOTIFICATION_RATE_LIMIT = int(os.getenv("NOTIFICATION_RATE_LIMIT", 300))  # 5 minutes between notifications

config = Config()