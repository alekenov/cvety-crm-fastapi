#!/usr/bin/env python3
"""
Telegram Bot для уведомлений о синхронизации между Bitrix и Supabase
"""

import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from supabase import create_client
from config import config

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class CvetyTelegramBot:
    """Telegram Bot для мониторинга синхронизации"""
    
    def __init__(self):
        self.application = None
        self.supabase = None
        
        if config.SUPABASE_URL and config.SUPABASE_ANON_KEY:
            self.supabase = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)
        else:
            logger.error("Supabase credentials not found")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start - регистрация пользователя"""
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        try:
            if not self.supabase:
                await update.message.reply_text("❌ База данных недоступна")
                return
            
            # Проверяем существует ли пользователь
            existing_user = self.supabase.table('telegram_users')\
                .select('*')\
                .eq('chat_id', chat_id)\
                .execute()
            
            if existing_user.data:
                # Обновляем активность существующего пользователя
                self.supabase.table('telegram_users')\
                    .update({
                        'is_active': True,
                        'last_activity': datetime.utcnow().isoformat(),
                        'username': user.username,
                        'first_name': user.first_name,
                        'last_name': user.last_name
                    })\
                    .eq('chat_id', chat_id)\
                    .execute()
                
                await update.message.reply_text(
                    f"👋 Добро пожаловать обратно, {user.first_name}!\n\n"
                    "✅ Вы снова подписаны на уведомления о синхронизации товаров и заказов.\n\n"
                    "Доступные команды:\n"
                    "/status - текущий статус синхронизации\n"
                    "/stats - статистика за сегодня\n"
                    "/stop - отписаться от уведомлений"
                )
            else:
                # Создаем нового пользователя
                self.supabase.table('telegram_users').insert({
                    'chat_id': chat_id,
                    'username': user.username,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'is_active': True,
                    'role': 'viewer',
                    'notification_level': 'all'
                }).execute()
                
                await update.message.reply_text(
                    f"🎉 Добро пожаловать, {user.first_name}!\n\n"
                    "Вы подписались на уведомления бота @Dflowersbot о синхронизации данных между Bitrix и Supabase.\n\n"
                    "📦 Вы будете получать уведомления о:\n"
                    "• Новых и обновленных заказах\n"
                    "• Изменениях товаров\n"
                    "• Ошибках синхронизации\n\n"
                    "Доступные команды:\n"
                    "/status - текущий статус синхронизации\n"
                    "/stats - статистика за сегодня\n"
                    "/stop - отписаться от уведомлений"
                )
            
            logger.info(f"User {user.first_name} ({chat_id}) registered/reactivated")
            
        except Exception as e:
            logger.error(f"Error in start_command: {e}")
            await update.message.reply_text("❌ Произошла ошибка при регистрации")
    
    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /stop - отписка от уведомлений"""
        chat_id = update.effective_chat.id
        user = update.effective_user
        
        try:
            if not self.supabase:
                await update.message.reply_text("❌ База данных недоступна")
                return
            
            # Деактивируем пользователя
            result = self.supabase.table('telegram_users')\
                .update({'is_active': False})\
                .eq('chat_id', chat_id)\
                .execute()
            
            if result.data:
                await update.message.reply_text(
                    f"👋 До свидания, {user.first_name}!\n\n"
                    "❌ Вы отписались от уведомлений.\n\n"
                    "Для повторной подписки используйте команду /start"
                )
                logger.info(f"User {user.first_name} ({chat_id}) deactivated")
            else:
                await update.message.reply_text("⚠️ Вы не были зарегистрированы в системе")
                
        except Exception as e:
            logger.error(f"Error in stop_command: {e}")
            await update.message.reply_text("❌ Произошла ошибка при отписке")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /status - текущий статус системы"""
        try:
            await update.message.reply_text("🔄 Получение статуса системы...")
            
            if not self.supabase:
                await update.message.reply_text("❌ База данных недоступна")
                return
            
            # Получаем количество активных товаров и заказов
            products_count = self.supabase.table('products')\
                .select('id', count='exact')\
                .eq('is_active', True)\
                .execute()
            
            orders_count = self.supabase.table('orders')\
                .select('id', count='exact')\
                .execute()
            
            # Последние 3 заказа
            recent_orders = self.supabase.table('orders')\
                .select('id, total_amount, status, created_at')\
                .order('created_at', desc=True)\
                .limit(3)\
                .execute()
            
            status_message = f"📊 **Статус системы Cvety.kz**\n\n"
            status_message += f"🛍 **Товары:** {products_count.count:,} активных\n"
            status_message += f"📦 **Заказы:** {orders_count.count:,} всего\n\n"
            
            if recent_orders.data:
                status_message += "🕐 **Последние заказы:**\n"
                for order in recent_orders.data:
                    order_date = datetime.fromisoformat(order['created_at'].replace('Z', '+00:00'))
                    status_message += f"• #{order['id'][:8]} - {order['total_amount']:,.0f}₸ - {order['status']}\n"
            
            status_message += f"\n⏰ Обновлено: {datetime.now().strftime('%H:%M:%S')}"
            
            await update.message.reply_text(status_message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in status_command: {e}")
            await update.message.reply_text("❌ Ошибка получения статуса системы")
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /stats - статистика за сегодня"""
        try:
            await update.message.reply_text("📈 Получение статистики...")
            
            if not self.supabase:
                await update.message.reply_text("❌ База данных недоступна")
                return
            
            # Статистика за сегодня
            today = datetime.now().date()
            today_start = f"{today}T00:00:00Z"
            
            # Заказы за сегодня
            orders_today = self.supabase.table('orders')\
                .select('id, total_amount', count='exact')\
                .gte('created_at', today_start)\
                .execute()
            
            # Товары обновленные сегодня
            products_updated = self.supabase.table('products')\
                .select('id', count='exact')\
                .gte('updated_at', today_start)\
                .execute()
            
            # Сумма заказов за сегодня
            total_amount = sum(float(order.get('total_amount', 0) or 0) for order in orders_today.data)
            
            stats_message = f"📈 **Статистика за {today.strftime('%d.%m.%Y')}**\n\n"
            stats_message += f"📦 **Новых заказов:** {orders_today.count}\n"
            stats_message += f"💰 **Сумма заказов:** {total_amount:,.0f} ₸\n"
            stats_message += f"🛍 **Товаров обновлено:** {products_updated.count}\n"
            
            if orders_today.count > 0:
                avg_order = total_amount / orders_today.count
                stats_message += f"📊 **Средний чек:** {avg_order:,.0f} ₸\n"
            
            stats_message += f"\n⏰ Обновлено: {datetime.now().strftime('%H:%M:%S')}"
            
            await update.message.reply_text(stats_message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in stats_command: {e}")
            await update.message.reply_text("❌ Ошибка получения статистики")
    
    async def users_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /users - список пользователей (только для админов)"""
        chat_id = update.effective_chat.id
        
        try:
            if not self.supabase:
                await update.message.reply_text("❌ База данных недоступна")
                return
            
            # Проверяем права админа
            user_check = self.supabase.table('telegram_users')\
                .select('role')\
                .eq('chat_id', chat_id)\
                .execute()
            
            if not user_check.data or user_check.data[0].get('role') != 'admin':
                await update.message.reply_text("❌ Недостаточно прав для выполнения команды")
                return
            
            # Получаем список активных пользователей
            active_users = self.supabase.table('telegram_users')\
                .select('chat_id, username, first_name, role, created_at')\
                .eq('is_active', True)\
                .order('created_at', desc=False)\
                .execute()
            
            if not active_users.data:
                await update.message.reply_text("👥 Активных пользователей нет")
                return
            
            users_message = f"👥 **Активные пользователи ({len(active_users.data)}):**\n\n"
            
            for user in active_users.data:
                username = f"@{user['username']}" if user['username'] else "без username"
                role_emoji = "👑" if user['role'] == 'admin' else "👤"
                created = datetime.fromisoformat(user['created_at'].replace('Z', '+00:00'))
                
                users_message += f"{role_emoji} {user['first_name']} ({username})\n"
                users_message += f"   Регистрация: {created.strftime('%d.%m.%Y')}\n\n"
            
            await update.message.reply_text(users_message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in users_command: {e}")
            await update.message.reply_text("❌ Ошибка получения списка пользователей")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help - помощь"""
        help_message = (
            "🤖 **Бот Cvety.kz - Мониторинг синхронизации**\n\n"
            "**Доступные команды:**\n\n"
            "/start - подписаться на уведомления\n"
            "/stop - отписаться от уведомлений\n"
            "/status - текущий статус системы\n"
            "/stats - статистика за сегодня\n"
            "/help - эта справка\n\n"
            "**Типы уведомлений:**\n"
            "📦 Новые и обновленные заказы\n"
            "🛍 Изменения товаров\n"
            "⚠️ Ошибки синхронизации\n\n"
            "По вопросам обращайтесь к администратору."
        )
        
        await update.message.reply_text(help_message, parse_mode='Markdown')
    
    def setup_handlers(self):
        """Настройка обработчиков команд"""
        if not self.application:
            return
        
        # Основные команды
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("stop", self.stop_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        
        # Админские команды
        self.application.add_handler(CommandHandler("users", self.users_command))
    
    async def start_bot(self):
        """Запуск бота"""
        if not config.TELEGRAM_BOT_TOKEN:
            logger.error("TELEGRAM_BOT_TOKEN not found in environment")
            return
        
        logger.info("Starting Telegram bot...")
        
        # Создаем приложение
        self.application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
        
        # Настраиваем обработчики
        self.setup_handlers()
        
        # Запускаем бота
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        logger.info("Telegram bot started successfully!")
        
        # Держим бота активным
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Bot stopping...")
        finally:
            await self.application.stop()

# Глобальный экземпляр бота
bot_instance = None

def get_bot():
    """Получить экземпляр бота"""
    global bot_instance
    if bot_instance is None:
        bot_instance = CvetyTelegramBot()
    return bot_instance

if __name__ == "__main__":
    # Запуск бота как отдельного процесса
    bot = CvetyTelegramBot()
    asyncio.run(bot.start_bot())