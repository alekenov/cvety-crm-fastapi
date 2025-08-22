#!/usr/bin/env python3
"""
Скрипт для запуска Telegram бота @Dflowersbot
"""

import asyncio
import signal
import logging
from telegram_bot import CvetyTelegramBot
from config import config

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальная переменная для бота
bot_instance = None

def signal_handler(signum, frame):
    """Обработчик сигналов для graceful shutdown"""
    logger.info(f"Received signal {signum}, shutting down bot...")
    if bot_instance:
        asyncio.create_task(bot_instance.application.stop())

async def main():
    """Основная функция запуска бота"""
    global bot_instance
    
    logger.info("Starting Cvety.kz Telegram Bot...")
    
    # Проверяем наличие токена
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables")
        logger.error("Please set TELEGRAM_BOT_TOKEN in .env file")
        return
    
    if not config.TELEGRAM_NOTIFICATIONS_ENABLED:
        logger.warning("Telegram notifications are disabled in config")
        logger.info("Set TELEGRAM_NOTIFICATIONS_ENABLED=true to enable notifications")
    
    # Настраиваем обработчик сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Создаем экземпляр бота
        bot_instance = CvetyTelegramBot()
        
        # Запускаем бота
        await bot_instance.start_bot()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed with error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
    finally:
        logger.info("Bot shutdown completed")

if __name__ == "__main__":
    # Запускаем бота
    print("🤖 Starting Cvety.kz Telegram Bot...")
    print(f"🔗 Bot username: @Dflowersbot")
    print(f"📊 Notifications enabled: {config.TELEGRAM_NOTIFICATIONS_ENABLED}")
    print("🛑 Press Ctrl+C to stop the bot")
    print("-" * 50)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        exit(1)