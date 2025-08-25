from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
from datetime import datetime
from decimal import Decimal

class User(BaseModel):
    """User/Florist model"""
    id: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    is_florist: bool = False
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def get_display_name(self) -> str:
        """Get display name for the user"""
        if self.name:
            return self.name
        if self.email:
            return self.email.split('@')[0]
        return f"User {self.id[:8] if self.id else 'Unknown'}"

class Product(BaseModel):
    """Product model for the catalog"""
    id: Optional[str] = None
    name: str
    slug: Optional[str] = None
    description: Optional[str] = None
    price: Decimal
    old_price: Optional[Decimal] = None
    quantity: int = 0
    category_id: Optional[str] = None
    metadata: Optional[dict] = {}
    is_active: bool = True
    sort_order: Optional[int] = 500
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    @property
    def composition(self) -> Optional[str]:
        """Get composition from metadata"""
        if self.metadata:
            return self.metadata.get('composition')
        return None
    
    @property
    def sku(self) -> Optional[str]:
        """Get SKU from metadata"""
        if self.metadata:
            return self.metadata.get('sku')
        return None
    
    @property
    def seller_id(self) -> Optional[str]:
        """Get seller_id from metadata"""
        if self.metadata:
            return self.metadata.get('seller_id')
        return None
    
    def get_image_url(self) -> Optional[str]:
        """Get the miniature image URL from metadata with full domain"""
        if self.metadata and 'properties' in self.metadata:
            img_path = self.metadata['properties'].get('ru_img_miniature')
            if img_path and img_path.startswith('/'):
                # Convert relative path to absolute URL on production server
                return f"https://cvety.kz{img_path}"
            return img_path
        return None
    
    def get_category(self) -> Optional[str]:
        """Get category from metadata"""
        if self.metadata:
            return self.metadata.get('category')
        return None

class OrderItem(BaseModel):
    """Single item in an order"""
    id: Optional[str] = None
    order_id: Optional[str] = None
    product_id: str
    product_name: str
    quantity: int = Field(..., gt=0)
    price: Decimal = Field(..., gt=0)
    total: Optional[Decimal] = None
    product_snapshot: Optional[dict] = {}
    
    def calculate_total(self) -> Decimal:
        """Calculate total price for this item"""
        return self.price * self.quantity
    
    def get_product_name(self) -> str:
        """Get product name from snapshot or fallback to product_name"""
        if self.product_snapshot and 'name' in self.product_snapshot:
            return self.product_snapshot['name']
        return self.product_name

class Order(BaseModel):
    """Order model"""
    id: Optional[str] = None
    order_number: Optional[str] = None
    status: str = "new"
    
    # User information
    user_id: Optional[str] = None
    user_phone: Optional[str] = None
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    
    # Recipient information
    recipient_name: str
    recipient_phone: str
    
    # Delivery information
    delivery_address: str
    delivery_date: Optional[str] = None
    delivery_time: Optional[str] = None
    delivery_cost: Optional[Decimal] = Decimal('0')
    
    # Pricing
    subtotal: Optional[Decimal] = Decimal('0')
    discount: Optional[Decimal] = Decimal('0')
    total_amount: Decimal
    
    # Additional information
    payment_method: Optional[str] = None
    payment_status: Optional[str] = "pending"
    comment: Optional[str] = None
    postcard_text: Optional[str] = None
    courier_comment: Optional[str] = None
    delivery_coordinates: Optional[dict] = None
    delivery_fee: Optional[Decimal] = Decimal('0')
    discount_amount: Optional[Decimal] = Decimal('0')
    source: Optional[str] = None
    metadata: Optional[dict] = {}
    
    # City and seller
    city_id: Optional[str] = None
    seller_id: Optional[str] = None
    
    # Responsible florist
    responsible_id: Optional[str] = None
    responsible_name: Optional[str] = None
    
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Related data (not stored in DB, loaded separately)
    items: Optional[List[OrderItem]] = []

class ProductCreateRequest(BaseModel):
    """Request model for creating new products"""
    name: str = Field(..., min_length=1, max_length=255)
    price: Decimal = Field(..., gt=0)
    quantity: int = Field(default=0, ge=0)
    description: Optional[str] = None
    composition: Optional[str] = None  # Состав букета
    category_id: Optional[str] = None
    sku: Optional[str] = None
    is_active: bool = True
    
    def generate_slug(self) -> str:
        """Generate URL-friendly slug from product name"""
        import re
        slug = self.name.lower()
        # Replace spaces and special chars with hyphens
        slug = re.sub(r'[^a-z0-9а-я]+', '-', slug)
        slug = slug.strip('-')
        return slug

class OrderCreateRequest(BaseModel):
    """Request model for creating new orders"""
    recipient_name: str
    recipient_phone: str
    delivery_address: str
    delivery_date: Optional[str] = None
    delivery_time: Optional[str] = None
    items: List[OrderItem]
    comment: Optional[str] = None
    payment_method: Optional[str] = "cash"

class OrderStatusUpdate(BaseModel):
    """Model for updating order status"""
    status: str = Field(..., description="Order status code")

# Order statuses based on REAL DATA analysis from MySQL Bitrix
# Top 13 actually used statuses (96.9% of all orders)
ORDER_STATUSES = {
    # Most used - Final states (97.3% of orders)
    "F": "✅ Выполнен",           # 69.7% - Main success status
    "UN": "❌ Отменен",          # 27.6% - Main cancellation status  
    
    # Problem handling (1.4% of orders)
    "RF": "↩️ Возврат",          # 0.9% - Returns/refunds
    "RD": "📅 Перенесен",        # 0.5% - Rescheduled orders
    
    # Active workflow statuses (from production analysis)
    "AP": "🟣 Принят",           # ПРИНЯТ (розовая кнопка в продакшне)
    "DE": "🟢 В пути",           # В ПУТИ (зеленая кнопка в продакшне)
    "CO": "📦 Собран",           # 0.1% - Assembled
    "TR": "🚚 Передан курьеру",  # 0.8% - Handed to courier
    "N": "🆕 Новый заказ",       # 0.1% - New orders
    "PD": "💰 Оплачен",          # 0.04% - Paid
    "RO": "🔄 Переназначен",     # 0.1% - Reassigned
    "CF": "💳 Ждем оплату",      # 0.1% - Waiting for payment
    "P": "🔄 В обработке",       # Processing status
    "KC": "🏪 У партнера",       # Partner handling
    "GP": "🎁 Подарок",          # Gift status
    
    # System errors
    "CA": "⚠️ Отменен системой", # 0.02% - System cancelled
    "ER": "⚠️ Ошибка оплаты",    # 0.02% - Payment error
    
    # Compatibility with Supabase  
    "completed": "✅ Выполнен",    # Maps to F
    "new": "🆕 Новый",           # Maps to N
    "cancelled": "❌ Отменён",    # Maps to UN
    "processing": "🔄 В обработке", # Maps to P
    "paid": "💰 Оплачен",        # Maps to PD
    "unrealized": "❓ Нереализован"
}

PAYMENT_METHODS = {
    "cash": "💵 Наличные",
    "card": "💳 Банковская карта",
    "kaspi": "🟡 Kaspi Pay",
    "transfer": "🏦 Банковский перевод",
    "unknown": "❓ Не указан"
}

# Status filtering for active/archive view
ACTIVE_STATUSES = [
    # Supabase statuses (после трансформации из Bitrix)
    "new",              # Новый (с фильтрацией мусора в API)
    "paid",             # Оплачен
    "processing",       # В обработке
    "confirmed",        # Подтвержден
    "assembled",        # Собран
    "ready_delivery",   # Готов к доставке
    "ready_pickup",     # Готов к выдаче
    "in_transit",       # В пути (доставляется)
    "shipped",          # Отгружен
    "unpaid",           # Не оплачен (ждем оплату)
    "payment_error",    # Ошибка при оплате
    "problematic",      # Проблемный
    "reassemble",       # Пересобрать заказ
    "waiting_processing", # Ожидает обработки
    "waiting_approval",   # Ждем одобрения заказчика
    "waiting_group_buy",  # Ждем группового закупа
    "auction",           # Аукцион
    "decide",            # Решить
    
    # Kaspi статусы
    "kaspi_waiting_qr",   # Kaspi ждем сканирования QR
    "kaspi_qr_scanned",   # Kaspi отсканирован QR, ждем оплату
    "kaspi_paid",         # Kaspi заказ оплачен
    "kaspi_payment_error", # Kaspi ошибка оплаты
    
    # Cloudpayments статусы
    "cloudpay_authorized", # Cloudpayments: Авторизован
    "cloudpay_confirmed",  # Cloudpayments: Подтверждение оплаты
    
    # Bitrix codes that actually exist in DB (not transformed)
    "DE",   # В пути (exists as-is in DB for some orders)
]

ARCHIVE_STATUSES = [
    # Supabase statuses (архивные/завершенные)
    "completed",           # Выполнен
    "cancelled",           # Отменен
    "refunded",           # Возврат
    "unrealized",         # Нереализован
    "cloudpay_canceled",  # Cloudpayments: Отмена авторизованного платежа
    "cloudpay_refunded",  # Cloudpayments: Возврат оплаты
    
    # Bitrix codes (для обратной совместимости)
    "F",    # Выполнен
    "UN",   # Нереализован
    "RF",   # Возврат
    "ER",   # Ошибка оплаты (удален дубликат CA)
    "AR",   # Cloudpayments: Отмена авторизованного платежа
    "RR",   # Cloudpayments: Возврат оплаты
]

# Status mapping for Bitrix synchronization
BITRIX_STATUS_MAPPING = {
    # Supabase → Bitrix
    "new": "N",
    "paid": "PD", 
    "processing": "P",
    "completed": "F",
    "cancelled": "UN",
    "refunded": "RF",
    "accepted": "AP",
    "delivering": "DE",
    "assembled": "CO",
}

REVERSE_BITRIX_MAPPING = {
    # Bitrix → Supabase  
    "N": "new",
    "PD": "paid",
    "P": "processing",
    "CO": "assembled", 
    "F": "completed",
    "UN": "cancelled",
    "RF": "refunded",
    "AP": "accepted",      # Принят
    "DE": "delivering",    # В пути / Доставляется
    "TR": "courier",       # Передан курьеру
    "CF": "awaiting_payment", # Ждем оплату
    "RO": "reassigned",    # Переназначен
    "RD": "rescheduled",   # Перенесен
    "CA": "cancelled",     # Отменен системой
    "ER": "payment_error", # Ошибка оплаты
    "KC": "partner",       # У партнера
    "GP": "gift",          # Подарок
}

class Flower(BaseModel):
    """Flower dictionary model"""
    id: Optional[str] = None
    xml_id: str
    name: str
    name_en: Optional[str] = None
    quantity: int = 0  # Количество на складе
    sort_order: int = 500
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class ProductComposition(BaseModel):
    """Product composition item - links product to flower with quantity"""
    id: Optional[str] = None
    product_id: str
    flower_id: str
    flower_name: Optional[str] = None  # Denormalized for display
    amount: int = Field(..., gt=0)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class ProductCompositionRequest(BaseModel):
    """Request model for updating product composition"""
    flower_id: str
    amount: int = Field(..., gt=0)

class FlowerUpdateRequest(BaseModel):
    """Request model for updating flower data"""
    name: str = Field(..., min_length=1, max_length=255)
    name_en: Optional[str] = Field(None, max_length=255)
    sort_order: int = Field(default=500, ge=0, le=9999)
    is_active: bool = True

class FlowerMovement(BaseModel):
    """Flower inventory movement model"""
    id: Optional[str] = None
    flower_id: str
    flower_name: Optional[str] = None  # Denormalized for display
    movement_type: str = Field(..., description="delivery, writeoff, or order_usage")
    quantity: int = Field(..., gt=0)
    reason: Optional[str] = None
    note: Optional[str] = None
    delivery_date: Optional[str] = None  # For deliveries
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class FlowerDeliveryRequest(BaseModel):
    """Request model for adding flower delivery"""
    flower_id: str = Field(..., description="UUID of the flower")
    quantity: int = Field(..., gt=0, description="Number of flowers received")
    delivery_date: Optional[str] = Field(None, description="Date when flowers were received (YYYY-MM-DD)")
    reason: Optional[str] = Field(None, max_length=255, description="Reason for delivery")
    note: Optional[str] = Field(None, description="Additional notes")

class FlowerWriteoffRequest(BaseModel):
    """Request model for flower writeoff"""
    flower_id: str = Field(..., description="UUID of the flower")
    quantity: int = Field(..., gt=0, description="Number of flowers to writeoff")
    reason: str = Field(..., min_length=1, max_length=255, description="Reason for writeoff")
    note: Optional[str] = Field(None, description="Additional notes")