from fastapi import FastAPI, Request, Form, HTTPException, Depends, Header, File, UploadFile
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from supabase import create_client, Client
from config import config as app_config
from models import Product, Order, OrderItem, User, ORDER_STATUSES, PAYMENT_METHODS, ProductCreateRequest, OrderCreateRequest, Flower, ProductComposition, ProductCompositionRequest, FlowerMovement, FlowerDeliveryRequest, FlowerWriteoffRequest, ACTIVE_STATUSES, ARCHIVE_STATUSES
from typing import Optional, List
from datetime import datetime, date
import logging
import json
import asyncio
import requests
import httpx
from order_number_generator import order_number_generator
import os
import uuid
import shutil
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title=app_config.APP_TITLE,
    debug=app_config.DEBUG
)

# Templates and static files
templates = Jinja2Templates(directory="templates")
# Mount static files only if directory exists
import os
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Supabase client
supabase: Client = None

# ==================== REVERSE SYNC FUNCTIONS ====================

async def create_order_in_bitrix(order_data: dict, order_items: List[dict] = None) -> Optional[int]:
    """
    Создает заказ в Bitrix через API endpoint
    Обратная синхронизация Supabase → Bitrix
    
    Args:
        order_data: Данные заказа из Supabase
        order_items: Товары заказа
        
    Returns:
        bitrix_order_id или None при ошибке
    """
    if not app_config.BITRIX_SYNC_ENABLED:
        logger.info("Bitrix sync is disabled")
        return None
        
    try:
        # Подготовка данных для Bitrix API
        bitrix_payload = {
            'user_id': order_data.get('bitrix_user_id', 1),
            'recipient_name': order_data.get('recipient_name', ''),
            'recipient_phone': order_data.get('recipient_phone', ''),
            'delivery_address': order_data.get('delivery_address', ''),
            'delivery_date': order_data.get('delivery_date', ''),
            'postcard_text': order_data.get('postcard_text', ''),
            'comment': order_data.get('comment', ''),
            'total_amount': float(order_data.get('total_amount', 0)),
            'delivery_fee': float(order_data.get('delivery_fee', 0)),
            'delivery_id': 1,  # Доставка курьером
            'payment_method_id': 1,  # Наличные курьеру
            'items': [],
            'properties': {
                'city': str(order_data.get('bitrix_city_id', '2')),  # Алматы по умолчанию
                'when': '18',  # 15:00-16:00 время доставки (статическое значение)
                'data': order_data.get('delivery_date', ''),  # Дата доставки
                'shopId': '17008',  # CVETYKZ (статическое значение)
                'postcardText': order_data.get('postcard_text', ''),  # Открытка в properties
                'phone': order_data.get('recipient_phone', ''),
                'email': order_data.get('recipient_phone', '')  # Используем телефон как email
            }
        }
        
        # Добавляем товары
        if order_items:
            for item in order_items:
                product_snapshot = item.get('product_snapshot', {})
                bitrix_payload['items'].append({
                    'bitrix_product_id': item.get('bitrix_product_id'),
                    'quantity': int(item.get('quantity', 1)),
                    'price': float(item.get('price', 0)),
                    'product_snapshot': product_snapshot
                })
        
        logger.info(f"Sending order to Bitrix API: {bitrix_payload.get('recipient_name', 'N/A')} -> {app_config.BITRIX_API_URL}")
        
        # Отправляем запрос к Bitrix API
        response = requests.post(
            app_config.BITRIX_API_URL,
            json=bitrix_payload,
            headers={
                'X-API-TOKEN': app_config.BITRIX_API_TOKEN,
                'Content-Type': 'application/json'
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                bitrix_order_id = result.get('order_id')
                order_number = result.get('order_number')
                logger.info(f"✅ Order created in Bitrix: ID={bitrix_order_id}, Number={order_number}")
                return bitrix_order_id
            else:
                logger.error(f"❌ Bitrix API returned success=false: {result}")
                return None
        else:
            logger.error(f"❌ Failed to create order in Bitrix: {response.status_code} - {response.text}")
            return None
            
    except requests.exceptions.Timeout:
        logger.error("❌ Timeout while creating order in Bitrix")
        return None
    except requests.exceptions.ConnectionError:
        logger.error("❌ Connection error while creating order in Bitrix")
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected error creating order in Bitrix: {e}")
        return None


async def sync_product_status_to_bitrix(bitrix_product_id: int, is_active: bool) -> bool:
    """
    Синхронизирует статус товара с Bitrix через PHP endpoint
    
    Args:
        bitrix_product_id: ID товара в Bitrix
        is_active: True для активации, False для деактивации
        
    Returns:
        True если синхронизация успешна, False если ошибка
    """
    if not app_config.BITRIX_SYNC_ENABLED:
        logger.info("Bitrix sync is disabled for products")
        return False
        
    try:
        # Подготовка данных для PHP endpoint
        payload = {
            'product_id': bitrix_product_id,
            'is_active': is_active,
            'action': 'activate' if is_active else 'deactivate'
        }
        
        logger.info(f"🔄 Syncing product status to Bitrix: ID={bitrix_product_id}, active={is_active}")
        
        # URL для синхронизации статуса товара
        # TODO: Создать этот endpoint на production сервере
        product_sync_url = app_config.BITRIX_API_URL.replace(
            'supabase-reverse-sync-with-items.php',
            'supabase-product-status-sync.php'
        )
        
        # Отправляем запрос к Bitrix API
        response = requests.post(
            product_sync_url,
            json=payload,
            headers={
                'X-API-TOKEN': app_config.BITRIX_API_TOKEN,
                'Content-Type': 'application/json'
            },
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                logger.info(f"✅ Product status synced to Bitrix: ID={bitrix_product_id}")
                return True
            else:
                logger.error(f"❌ Bitrix returned error: {result.get('error', 'Unknown error')}")
                return False
        else:
            logger.error(f"❌ HTTP {response.status_code} from Bitrix: {response.text[:200]}")
            return False
            
    except requests.exceptions.Timeout:
        logger.error("❌ Timeout while syncing product status to Bitrix")
        return False
    except requests.exceptions.ConnectionError:
        logger.error("❌ Connection error while syncing product status to Bitrix")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error syncing product status to Bitrix: {e}")
        return False


async def sync_photos_to_bitrix(order_id: str, order_number: str, bitrix_order_id: int, photo_paths: List[str]) -> bool:
    """
    Синхронизирует фотографии до доставки с Bitrix через PHP endpoint
    
    Args:
        order_id: ID заказа в Supabase
        order_number: Номер заказа
        bitrix_order_id: ID заказа в Bitrix
        photo_paths: Пути к фотографиям для синхронизации
        
    Returns:
        True если синхронизация успешна, False если ошибка
    """
    if not app_config.BITRIX_SYNC_ENABLED:
        logger.info(f"Bitrix sync is disabled, skipping photo sync for order {order_id}")
        return False
        
    if not bitrix_order_id or not photo_paths:
        logger.info(f"No bitrix_order_id or photos for order {order_id}, skipping photo sync")
        return False
        
    try:
        import base64
        import os
        
        # Подготавливаем данные фотографий
        photos_data = []
        for photo_path in photo_paths:
            if os.path.exists(photo_path):
                with open(photo_path, 'rb') as file:
                    photo_binary = file.read()
                    base64_data = base64.b64encode(photo_binary).decode('utf-8')
                    
                    photos_data.append({
                        "filename": os.path.basename(photo_path),
                        "base64_data": base64_data,
                        "uploaded_at": datetime.now().isoformat()
                    })
            else:
                logger.warning(f"Photo file not found: {photo_path}")
        
        if not photos_data:
            logger.warning(f"No valid photos found for order {order_id}")
            return False
        
        # URL для синхронизации фотографий
        photo_sync_url = "https://cvety.kz/supabase-photo-sync.php"
        
        payload = {
            "order_number": order_number,
            "bitrix_order_id": bitrix_order_id,
            "photos": photos_data
        }
        
        # Отправляем фотографии в Bitrix
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                photo_sync_url,
                json=payload,
                headers={
                    "X-API-TOKEN": "cvety_photo_sync_token_2025_secure_key_789",
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    photos_saved = result.get("data", {}).get("photos_saved", 0)
                    logger.info(f"✅ Successfully synced {photos_saved} photos to Bitrix for order {bitrix_order_id}")
                    return True
                else:
                    logger.error(f"❌ Bitrix photo sync failed: {result.get('message', 'Unknown error')}")
                    return False
            else:
                logger.error(f"❌ Failed to sync photos to Bitrix: HTTP {response.status_code} - {response.text}")
                return False
                
    except httpx.TimeoutException:
        logger.error(f"⏱️ Timeout syncing photos for order {order_id} to Bitrix")
        return False
    except Exception as e:
        logger.error(f"❌ Error syncing photos for order {order_id} to Bitrix: {e}")
        return False


@app.on_event("startup")
async def startup():
    """Initialize Supabase client on startup"""
    global supabase
    
    logger.info("Starting CRM application...")
    logger.info(f"SUPABASE_URL present: {bool(app_config.SUPABASE_URL)}")
    logger.info(f"SUPABASE_SERVICE_KEY present: {bool(app_config.SUPABASE_SERVICE_KEY)}")
    
    if not app_config.SUPABASE_URL or (not app_config.SUPABASE_SERVICE_KEY and not app_config.SUPABASE_ANON_KEY):
        logger.error("Missing Supabase configuration. Please check your .env file.")
        return
    
    try:
        # Try service key first, fallback to anon key if needed
        service_key = app_config.SUPABASE_SERVICE_KEY or app_config.SUPABASE_ANON_KEY
        supabase = create_client(app_config.SUPABASE_URL, service_key)
        logger.info(f"Supabase client created with {'service' if app_config.SUPABASE_SERVICE_KEY else 'anon'} key")
        
        # Test connection with a simple query that should work with anon key
        test_result = supabase.table("orders").select("id").limit(1).execute()
        logger.info("Supabase connection test successful")
        logger.info("CRM application started successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Supabase: {e}")
        # Try with anon key as fallback
        try:
            supabase = create_client(app_config.SUPABASE_URL, app_config.SUPABASE_ANON_KEY)
            logger.info("Fallback: Using anon key for Supabase connection")
            logger.info("CRM application started with limited database access")
        except Exception as e2:
            logger.error(f"Fallback also failed: {e2}")
            logger.info("CRM application started with database connection issues")

def get_supabase():
    """Dependency to get Supabase client"""
    if not supabase:
        raise HTTPException(status_code=500, detail="Database not initialized")
    return supabase

# ==================== DASHBOARD ====================

@app.get("/")
async def root():
    """Redirect root to CRM orders"""
    return RedirectResponse(url="/crm/orders")

@app.get("/crm")
async def crm_redirect():
    """Redirect /crm to orders page"""
    return RedirectResponse(url="/crm/orders")

# ==================== ORDERS ====================

@app.get("/crm/orders", response_class=HTMLResponse)
async def list_orders(
    request: Request,
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    view: str = "active",  # active or archive
    db: Client = Depends(get_supabase)
):
    """List orders with filtering and pagination"""
    
    try:
        limit = 50
        offset = (page - 1) * limit
        
        
        # Build query - оптимизированная выборка только нужных полей для списка
        query = db.table('orders').select(
            'id, order_number, status, recipient_name, recipient_phone, delivery_address, total_amount, created_at, responsible_name',
            count='exact'
        )
        
        # Apply filters
        if status and status != 'all':
            query = query.eq('status', status)
        
        # Apply view filter (active or archive)
        if view == "archive":
            query = query.in_('status', ARCHIVE_STATUSES)
            logger.info(f"Filtering by ARCHIVE_STATUSES: {len(ARCHIVE_STATUSES)} statuses")
        else:  # default to active - показываем ТОЛЬКО заказы с активными рабочими статусами
            query = query.in_('status', ACTIVE_STATUSES)
            logger.info(f"Filtering by ACTIVE_STATUSES: {len(ACTIVE_STATUSES)} statuses, completed in list: {'completed' in ACTIVE_STATUSES}")
        
        if search:
            # For search functionality, we'll filter by multiple OR conditions
            # Since or_ method may not exist, we'll temporarily disable complex search
            # and implement simple single-field search for now
            search_term = f"%{search}%"
            # Search primarily in order_number field  
            query = query.ilike('order_number', search_term)
        
        # Sort and paginate
        query = query.order('created_at', desc=True)
        query = query.range(offset, offset + limit - 1)
        
        result = query.execute()
        
        # Log what we got before filtering
        logger.info(f"Query executed. Got {len(result.data) if result.data else 0} orders for view={view}")
        if result.data:
            from collections import Counter
            status_counts = Counter([o.get('status') for o in result.data])
            logger.info(f"Before filtering - statuses in result: {dict(status_counts)}")
        
        # Minimal filtering - only skip obvious test/sync orders
        if view == "active" and result.data:
            filtered_orders = []
            for order in result.data:
                bitrix_id = order.get('bitrix_order_id')
                recipient = order.get('recipient_name', '')
                
                # Skip only obvious test/sync orders
                if bitrix_id and str(bitrix_id).startswith('175691'):  # Very specific test pattern
                    logger.debug(f"Skipping test order with timestamp-like ID: {bitrix_id}")
                    continue
                    
                # Skip test/sync orders by recipient name
                if 'Получатель Обратной Синхронизации' in str(recipient):
                    logger.debug(f"Skipping test order by recipient: {recipient}")
                    continue
                if 'Синхронизации' in str(recipient) or 'reverse_sync' in str(recipient).lower():
                    logger.debug(f"Skipping sync order by recipient: {recipient}")
                    continue
                
                # Accept all other orders (including those with empty recipient_name)
                filtered_orders.append(order)
            
            result.data = filtered_orders
            result.count = len(filtered_orders)
            logger.info(f"After minimal filtering: {len(filtered_orders)} orders for view={view} (showing legitimate orders with any recipient status)")
        
        total_pages = (result.count // limit) + (1 if result.count % limit > 0 else 0)
        
        # PERFORMANCE OPTIMIZATION: Batch load order items and products
        # Instead of N+1 queries, use 2-3 batch queries for all orders
        
        orders_with_images = []
        if result.data:
            # Step 1: Collect all order IDs
            order_ids = [order['id'] for order in result.data]
            
            # Step 2: Batch load multiple order items for each order (up to 6 items)
            all_order_items = db.table('order_items')\
                .select('order_id, product_id, product_snapshot')\
                .in_('order_id', order_ids)\
                .execute()
            
            # Group items by order_id (keep up to 6 items per order)
            items_by_order = {}
            if all_order_items.data:
                for item in all_order_items.data:
                    order_id = item['order_id']
                    if order_id not in items_by_order:
                        items_by_order[order_id] = []
                    # Keep only up to 6 items per order
                    if len(items_by_order[order_id]) < 6:
                        items_by_order[order_id].append(item)
            
            # Step 3: Collect all product_ids that need images
            product_ids_needed = []
            for items_list in items_by_order.values():
                for item in items_list:
                    if item.get('product_id'):
                        product_ids_needed.append(item['product_id'])
            
            # Step 4: Batch load product images for all needed products
            products_data = {}
            if product_ids_needed:
                products_result = db.table('products')\
                    .select('id, metadata')\
                    .in_('id', product_ids_needed)\
                    .execute()
                
                # Index products by ID for fast lookup
                if products_result.data:
                    products_data = {product['id']: product for product in products_result.data}
                else:
                    products_data = {}
            
            # Step 5: Assemble final data structure
            for order in result.data:
                order_dict = dict(order)
                order_id = order['id']
                
                item_images = []
                if order_id in items_by_order:
                    items = items_by_order[order_id]
                    
                    for item in items:
                        product_id = item.get('product_id')
                        item_image = None
                        
                        # Try to get image from regular products first
                        if product_id and product_id in products_data:
                            product = products_data[product_id]
                            if (product.get('metadata') and 
                                product['metadata'].get('properties', {}).get('ru_img_miniature')):
                                img_path = product['metadata']['properties']['ru_img_miniature']
                                item_image = f"https://cvety.kz{img_path}"
                        
                        # Fallback: Try to get image for dynamic products (assembled bouquets) from production server
                        if not item_image and item.get('product_snapshot'):
                            snapshot = item['product_snapshot']
                            if isinstance(snapshot, dict) and snapshot.get('bitrix', {}).get('product_id'):
                                bitrix_product_id = snapshot['bitrix']['product_id']
                                item_image = f"https://cvety.kz/miniature/{bitrix_product_id}-obrannyy-buket.jpg"
                        
                        if item_image:
                            item_images.append(item_image)
                
                order_dict['item_images'] = item_images
                # Keep backward compatibility for now
                order_dict['first_item_image'] = item_images[0] if item_images else None
                orders_with_images.append(order_dict)
        else:
            orders_with_images = []
        
        response = templates.TemplateResponse("orders.html", {
            "request": request,
            "orders": orders_with_images,
            "total": result.count,
            "page": page,
            "total_pages": total_pages,
            "active_page": "orders",
            "current_status": status,
            "search_term": search,
            "current_view": view,
            "order_statuses": ORDER_STATUSES
        })
        
        # Add cache-busting headers to ensure fresh order data
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        
        return response
        
    except Exception as e:
        logger.error(f"Orders list error: {e}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Failed to load orders",
            "active_page": "orders"
        })

async def process_flower_inventory_for_products(items, db: Client, movement_type="order_usage"):
    """
    Process flower inventory based on product compositions
    For each product in the order, deduct flowers from inventory based on product composition
    """
    try:
        flower_movements = []
        
        for item in items:
            product_id = item.get('product_id')
            order_quantity = item.get('quantity', 1)
            
            if not product_id:
                continue
            
            # Get product composition (what flowers are needed for this product)
            composition_result = db.table('product_composition')\
                .select('flower_id, amount, flowers(name)')\
                .eq('product_id', product_id)\
                .execute()
            
            if not composition_result.data:
                logger.info(f"No flower composition found for product {product_id}, skipping flower deduction")
                continue
            
            # For each flower in the product composition
            for comp in composition_result.data:
                flower_id = comp['flower_id']
                flowers_per_product = comp['amount']
                total_flowers_needed = flowers_per_product * order_quantity
                flower_name = comp.get('flowers', {}).get('name', 'Unknown')
                
                # Check flower availability
                flower_result = db.table('flowers')\
                    .select('quantity')\
                    .eq('id', flower_id)\
                    .single()\
                    .execute()
                
                if not flower_result.data:
                    raise ValueError(f"Flower {flower_id} not found")
                
                current_flower_quantity = flower_result.data.get('quantity', 0)
                
                if current_flower_quantity < total_flowers_needed:
                    raise ValueError(f"Insufficient flower stock for {flower_name}. Available: {current_flower_quantity}, Required: {total_flowers_needed}")
                
                new_flower_quantity = current_flower_quantity - total_flowers_needed
                
                # Update flower quantity
                db.table('flowers')\
                    .update({'quantity': new_flower_quantity, 'updated_at': datetime.utcnow().isoformat()})\
                    .eq('id', flower_id)\
                    .execute()
                
                # Create flower movement record
                db.table('flower_inventory_movements').insert({
                    'flower_id': flower_id,
                    'movement_type': movement_type,
                    'quantity': total_flowers_needed,
                    'reason': f'Used in order (Product composition)',
                    'note': f'Product requires {flowers_per_product} flowers × {order_quantity} quantity',
                    'created_by': 'Order System'
                }).execute()
                
                flower_movements.append({
                    'flower_id': flower_id,
                    'flower_name': flower_name,
                    'old_quantity': current_flower_quantity,
                    'new_quantity': new_flower_quantity,
                    'used_quantity': total_flowers_needed
                })
                
                logger.info(f"Flower inventory updated: {flower_name} {current_flower_quantity} → {new_flower_quantity} (used: {total_flowers_needed})")
        
        return {
            'success': True,
            'updates': flower_movements,
            'message': f"Processed flower inventory for {len(flower_movements)} flower types"
        }
        
    except Exception as e:
        logger.error(f"Flower inventory processing error: {e}")
        return {
            'success': False,
            'error': str(e)
        }

async def restore_flower_inventory_for_products(items, db: Client):
    """
    Restore flower inventory when orders are cancelled/refunded
    For each product in the order, restore flowers to inventory based on product composition
    """
    try:
        flower_movements = []
        
        for item in items:
            product_id = item.get('product_id')
            order_quantity = item.get('quantity', 1)
            
            if not product_id:
                continue
            
            # Get product composition (what flowers were used for this product)
            composition_result = db.table('product_composition')\
                .select('flower_id, amount, flowers(name)')\
                .eq('product_id', product_id)\
                .execute()
            
            if not composition_result.data:
                logger.info(f"No flower composition found for product {product_id}, skipping flower restoration")
                continue
            
            # For each flower in the product composition
            for comp in composition_result.data:
                flower_id = comp['flower_id']
                flowers_per_product = comp['amount']
                total_flowers_to_restore = flowers_per_product * order_quantity
                flower_name = comp.get('flowers', {}).get('name', 'Unknown')
                
                # Get current flower quantity
                flower_result = db.table('flowers')\
                    .select('quantity')\
                    .eq('id', flower_id)\
                    .single()\
                    .execute()
                
                if not flower_result.data:
                    logger.warning(f"Flower {flower_id} not found during restoration")
                    continue
                
                current_flower_quantity = flower_result.data.get('quantity', 0)
                new_flower_quantity = current_flower_quantity + total_flowers_to_restore
                
                # Update flower quantity
                db.table('flowers')\
                    .update({'quantity': new_flower_quantity, 'updated_at': datetime.utcnow().isoformat()})\
                    .eq('id', flower_id)\
                    .execute()
                
                # Create flower movement record for restoration (using 'delivery' type for restoration)
                db.table('flower_inventory_movements').insert({
                    'flower_id': flower_id,
                    'movement_type': 'delivery',
                    'quantity': total_flowers_to_restore,
                    'reason': f'Order cancelled/refunded (restored)',
                    'note': f'Product required {flowers_per_product} flowers × {order_quantity} quantity - now restored',
                    'created_by': 'Order System'
                }).execute()
                
                flower_movements.append({
                    'flower_id': flower_id,
                    'flower_name': flower_name,
                    'old_quantity': current_flower_quantity,
                    'new_quantity': new_flower_quantity,
                    'restored_quantity': total_flowers_to_restore
                })
                
                logger.info(f"Flower inventory restored: {flower_name} {current_flower_quantity} → {new_flower_quantity} (restored: {total_flowers_to_restore})")
        
        return {
            'success': True,
            'updates': flower_movements,
            'message': f"Restored flower inventory for {len(flower_movements)} flower types"
        }
        
    except Exception as e:
        logger.error(f"Flower inventory restoration error: {e}")
        return {
            'success': False,
            'error': str(e)
        }

async def check_flower_availability(items, db: Client):
    """
    Check if there are enough flowers available for all products in the order
    Returns detailed information about flower availability and shortages
    """
    try:
        flower_requirements = {}  # flower_id -> total_amount_needed
        flower_shortages = []
        
        for item in items:
            product_id = item.get('product_id')
            order_quantity = item.get('quantity', 1)
            
            if not product_id:
                continue
            
            # Get product composition (what flowers are needed for this product)
            composition_result = db.table('product_composition')\
                .select('flower_id, amount, flowers(name)')\
                .eq('product_id', product_id)\
                .execute()
            
            if not composition_result.data:
                # No composition - skip flower checking for this product
                continue
            
            # Calculate total flower requirements for this product
            for composition in composition_result.data:
                flower_id = composition['flower_id']
                flowers_per_product = composition['amount']
                total_flowers_needed = flowers_per_product * order_quantity
                
                if flower_id in flower_requirements:
                    flower_requirements[flower_id] += total_flowers_needed
                else:
                    flower_requirements[flower_id] = total_flowers_needed
        
        # Check availability for each required flower
        if flower_requirements:
            flower_ids = list(flower_requirements.keys())
            flowers_result = db.table('flowers')\
                .select('id, name, quantity')\
                .in_('id', flower_ids)\
                .execute()
            
            flowers_data = {flower['id']: flower for flower in flowers_result.data}
            
            for flower_id, needed_amount in flower_requirements.items():
                if flower_id not in flowers_data:
                    flower_shortages.append({
                        'flower_id': flower_id,
                        'flower_name': 'Unknown',
                        'needed': needed_amount,
                        'available': 0,
                        'shortage': needed_amount
                    })
                    continue
                
                flower = flowers_data[flower_id]
                available_amount = flower.get('quantity', 0)
                
                if available_amount < needed_amount:
                    flower_shortages.append({
                        'flower_id': flower_id,
                        'flower_name': flower['name'],
                        'needed': needed_amount,
                        'available': available_amount,
                        'shortage': needed_amount - available_amount
                    })
        
        return {
            'success': len(flower_shortages) == 0,
            'flower_requirements': flower_requirements,
            'shortages': flower_shortages,
            'message': 'All flowers available' if len(flower_shortages) == 0 else f'Insufficient flowers: {len(flower_shortages)} types'
        }
        
    except Exception as e:
        logger.error(f"Flower availability check error: {e}")
        return {
            'success': False,
            'error': str(e),
            'shortages': []
        }

async def validate_and_update_inventory(items, db: Client, operation="reserve"):
    """
    Validate product availability and update inventory
    operation: 'reserve' (decrease quantity) or 'release' (increase quantity)
    
    NEW LOGIC: For products with flower composition, check flower availability instead of product quantity
    """
    try:
        # STEP 1: Check flower availability for products with composition
        if operation == "reserve":
            flower_check = await check_flower_availability(items, db)
            if not flower_check['success']:
                # Build detailed error message for flower shortages
                shortage_details = []
                for shortage in flower_check['shortages']:
                    shortage_details.append(
                        f"{shortage['flower_name']}: нужно {shortage['needed']}, доступно {shortage['available']} (нехватка: {shortage['shortage']})"
                    )
                raise ValueError(f"Недостаточно цветов в инвентаре:\n" + "\n".join(shortage_details))
        
        # STEP 2: Process product inventory updates
        inventory_updates = []
        
        for item in items:
            product_id = item.get('product_id')
            quantity = item.get('quantity', 1)
            
            if not product_id:
                continue
                
            # Get current product inventory
            product_result = db.table('products')\
                .select('id, name, quantity')\
                .eq('id', product_id)\
                .single()\
                .execute()
                
            if not product_result.data:
                raise ValueError(f"Product {product_id} not found")
                
            product = product_result.data
            current_quantity = product.get('quantity', 0)
            
            # Check if product has flower composition
            composition_result = db.table('product_composition')\
                .select('flower_id')\
                .eq('product_id', product_id)\
                .limit(1)\
                .execute()
            
            has_composition = len(composition_result.data) > 0
            
            if operation == "reserve":
                if has_composition:
                    # For products with composition, flower availability was already checked above
                    # We can skip product quantity validation as flowers are the primary constraint
                    new_quantity = current_quantity  # Keep product quantity unchanged for flower-based products
                else:
                    # For products without composition, use traditional product quantity checking
                    if current_quantity < quantity:
                        raise ValueError(f"Insufficient stock for {product['name']}. Available: {current_quantity}, Required: {quantity}")
                    new_quantity = current_quantity - quantity
            else:  # release
                if has_composition:
                    # For flower-based products, don't modify product quantity
                    new_quantity = current_quantity
                else:
                    # For traditional products, restore quantity
                    new_quantity = current_quantity + quantity
            
            inventory_updates.append({
                'product_id': product_id,
                'product_name': product['name'],
                'old_quantity': current_quantity,
                'new_quantity': new_quantity,
                'change_quantity': quantity if operation == "release" else -quantity
            })
        
        # Apply all inventory updates
        for update in inventory_updates:
            db.table('products')\
                .update({'quantity': update['new_quantity'], 'updated_at': datetime.utcnow().isoformat()})\
                .eq('id', update['product_id'])\
                .execute()
                
            logger.info(f"Inventory updated: {update['product_name']} {update['old_quantity']} → {update['new_quantity']}")
        
        # Process flower inventory for each product
        flower_updates = []
        if operation == "reserve":
            flower_result = await process_flower_inventory_for_products(items, db, "order_usage")
            if not flower_result['success']:
                # Rollback product inventory changes
                for update in inventory_updates:
                    db.table('products')\
                        .update({'quantity': update['old_quantity'], 'updated_at': datetime.utcnow().isoformat()})\
                        .eq('id', update['product_id'])\
                        .execute()
                logger.error(f"Flower inventory error, rolled back product changes: {flower_result['error']}")
                return flower_result
            flower_updates = flower_result.get('updates', [])
        elif operation == "release":
            # Restore flower inventory when order is cancelled/refunded
            flower_result = await restore_flower_inventory_for_products(items, db)
            if flower_result['success']:
                flower_updates = flower_result.get('updates', [])
            else:
                logger.warning(f"Failed to restore flower inventory: {flower_result['error']}")

        return {
            'success': True,
            'updates': inventory_updates,
            'flower_updates': flower_updates,
            'message': f"Inventory {operation}d for {len(inventory_updates)} products, {len(flower_updates)} flower movements"
        }
        
    except Exception as e:
        logger.error(f"Inventory validation error: {e}")
        return {
            'success': False,
            'error': str(e)
        }

@app.get("/crm/orders/new", response_class=HTMLResponse)
async def new_order_form(request: Request):
    """Display form for creating new order"""
    return templates.TemplateResponse("order_new.html", {
        "request": request,
        "active_page": "orders",
        "today": date.today().isoformat()
    })

@app.post("/crm/orders/new")
async def create_order(
    order_data: dict,  # Using dict to handle complex nested structure
    db: Client = Depends(get_supabase)
):
    """Create a new order"""
    try:
        # Generate order number using synchronized production number generator
        new_number = order_number_generator.generate_order_number(
            is_webhook=False,
            force_local=False
        )
        logger.info(f"Generated new order number: {new_number}")
        
        # Check if number already exists in Supabase
        existing_order = db.table('orders').select('id').eq('order_number', new_number).execute()
        if existing_order.data:
            # If exists, use local prefix to avoid conflicts
            new_number = order_number_generator.generate_local_order_number()
            logger.warning(f"Order number collision detected, using local number: {new_number}")
        
        # Validate and update inventory first
        inventory_result = await validate_and_update_inventory(order_data.get('items', []), db, operation="reserve")
        if not inventory_result['success']:
            raise HTTPException(status_code=400, detail=f"Inventory error: {inventory_result['error']}")
        
        # Calculate total amount
        total = sum(item['price'] * item['quantity'] for item in order_data.get('items', []))
        
        # Prepare order data - use actual table columns
        new_order = {
            "order_number": new_number,
            "status": "new",
            "recipient_name": order_data.get('recipient_name'),
            "recipient_phone": order_data.get('recipient_phone'),
            "delivery_address": order_data.get('delivery_address'),
            "delivery_date": order_data.get('delivery_date'),
            "delivery_time": order_data.get('delivery_time'),
            "payment_method": order_data.get('payment_method', 'cash'),
            "payment_status": "pending",
            "postcard_text": order_data.get('postcard_text'),
            "comment": order_data.get('comment'),
            "total_amount": total,
            "delivery_fee": 0,
            "discount_amount": 0,
            "metadata": {
                "user_name": order_data.get('user_name'),
                "user_phone": order_data.get('user_phone')
            },
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Insert order
        order_result = db.table('orders').insert(new_order).execute()
        
        if order_result.data:
            order_id = order_result.data[0]['id']
            
            try:
                # Insert order items
                for item in order_data.get('items', []):
                    order_item = {
                        "order_id": order_id,
                        "product_id": item['product_id'],
                        "quantity": item['quantity'],
                        "price": item['price'],
                        "total": item['price'] * item['quantity'],
                        "product_snapshot": {
                            "name": item.get('product_name', 'Product'),
                            "price": item['price']
                        }
                    }
                    db.table('order_items').insert(order_item).execute()
                
                logger.info(f"Created new order: {order_id} with number {new_number} (inventory reserved: {len(inventory_result['updates'])} products)")
                return {"id": order_id, "order_number": new_number, "status": "success"}
                
            except Exception as e:
                # If order items creation fails, rollback inventory changes
                logger.error(f"Order items creation failed, rolling back inventory: {e}")
                await validate_and_update_inventory(order_data.get('items', []), db, operation="release")
                raise e
        else:
            # If order creation fails, rollback inventory changes
            await validate_and_update_inventory(order_data.get('items', []), db, operation="release")
            raise HTTPException(status_code=400, detail="Failed to create order")
            
    except Exception as e:
        logger.error(f"Order creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/crm/orders/{order_id}", response_class=HTMLResponse)
async def order_detail(
    request: Request,
    order_id: str,
    db: Client = Depends(get_supabase)
):
    """Order detail page"""
    
    try:
        # Get order
        order_result = db.table('orders')\
            .select('*')\
            .eq('id', order_id)\
            .execute()
        
        if not order_result.data:
            raise HTTPException(status_code=404, detail="Order not found")
        
        # Get first order from results
        order_data = order_result.data[0] if order_result.data else None
        if not order_data:
            raise HTTPException(status_code=404, detail="Order not found")
        
        # Get order items
        items_result = db.table('order_items')\
            .select('*')\
            .eq('order_id', order_id)\
            .execute()
        
        # OPTIMIZATION: Batch load products to avoid N+1 queries with caching
        from cache_utils import simple_cache, cache_key
        
        product_ids = [item.get('product_id') for item in items_result.data if item.get('product_id')]
        products_by_id = {}
        uncached_product_ids = []
        
        # Проверяем кэш для каждого продукта
        for product_id in product_ids:
            cache_k = cache_key('product', product_id)
            cached_product = simple_cache.get(cache_k)
            if cached_product:
                products_by_id[product_id] = cached_product
            else:
                uncached_product_ids.append(product_id)
        
        # Загружаем только те продукты, которых нет в кэше
        if uncached_product_ids:
            products_query = db.table('products')\
                .select('id, name, metadata')\
                .in_('id', uncached_product_ids)\
                .execute()
            
            # Добавляем в кэш и результат
            for prod in products_query.data:
                products_by_id[prod['id']] = prod
                cache_k = cache_key('product', prod['id'])
                simple_cache.set(cache_k, prod, ttl_seconds=300)  # 5 минут кэш для продуктов
        
        # Enrich order items with product images and names
        items_with_images = []
        for item in items_result.data:
            item_dict = dict(item)
            
            # Get product data if product_id exists
            product_image = None
            product_name = None
            
            if item.get('product_id') and item['product_id'] in products_by_id:
                product = products_by_id[item['product_id']]
                # Get product name
                product_name = product.get('name')
                
                # Get product image
                if (product.get('metadata') and 
                    product['metadata'].get('properties', {}).get('ru_img_miniature')):
                    img_path = product['metadata']['properties']['ru_img_miniature']
                    product_image = f"https://cvety.kz{img_path}"
            
            # Fallback: if no product_id or product not found, try product_snapshot
            if not product_name and item.get('product_snapshot'):
                snapshot = item['product_snapshot']
                if isinstance(snapshot, dict) and snapshot.get('name'):
                    product_name = snapshot['name']
                    
                    # Try to get image for dynamic products from production server
                    if not product_image and snapshot.get('bitrix', {}).get('product_id'):
                        bitrix_product_id = snapshot['bitrix']['product_id']
                        # Format: https://cvety.kz/miniature/{product_id}-obrannyy-buket.jpg
                        product_image = f"https://cvety.kz/miniature/{bitrix_product_id}-obrannyy-buket.jpg"
            
            # Final fallback for product name
            if not product_name:
                product_name = "Товар (название не указано)"
            
            item_dict['product_image'] = product_image
            item_dict['product_name'] = product_name
            items_with_images.append(item_dict)
        
        # Get customer information
        customer_info = None
        
        if order_data.get('user_id'):
            try:
                customer_result = db.table('users')\
                    .select('*')\
                    .eq('id', order_data['user_id'])\
                    .execute()
                
                if customer_result.data:
                    customer_info = customer_result.data[0]
            except Exception as e:
                logger.warning(f"Failed to load customer info for order {order_id}: {e}")
        
        # Get responsible florist information
        florist_info = None
        
        if order_data.get('responsible_id'):
            try:
                florist_result = db.table('users')\
                    .select('*')\
                    .eq('id', order_data['responsible_id'])\
                    .execute()
                
                if florist_result.data:
                    florist_info = florist_result.data[0]
            except Exception as e:
                logger.warning(f"Failed to load florist info for order {order_id}: {e}")
        
        # Extract payment method from metadata
        payment_method = "unknown"
        if order_data.get('metadata', {}).get('order_properties'):
            props = order_data['metadata']['order_properties']
            
            # Check for Kaspi payment indicators
            if props.get('kaspiPhone') or props.get('CHECK_NUMBER'):
                payment_method = "kaspi"
            elif props.get('METHOD_PAY'):
                method = props['METHOD_PAY'].lower()
                if 'cash' in method or 'наличн' in method:
                    payment_method = "cash"
                elif 'card' in method or 'карт' in method:
                    payment_method = "card"
                elif 'transfer' in method or 'перевод' in method:
                    payment_method = "transfer"
        
        response = templates.TemplateResponse("order_detail.html", {
            "request": request,
            "order": order_data,
            "items": items_with_images,
            "customer": customer_info,
            "florist": florist_info,
            "payment_method": payment_method,
            "active_page": "orders",
            "order_statuses": ORDER_STATUSES,
            "payment_methods": PAYMENT_METHODS
        })
        
        # Add cache-busting headers to ensure fresh status data
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Order detail error: {e}")
        logger.error(f"Stack trace: {traceback.format_exc()}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Failed to load order details",
            "active_page": "orders"
        })

@app.post("/crm/orders/{order_id}/status")
async def update_order_status(
    order_id: str,
    status: str = Form(...),
    db: Client = Depends(get_supabase)
):
    """Update order status"""
    
    try:
        if status not in ORDER_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status")
        
        # Get current order status and items for inventory management
        current_order = db.table('orders')\
            .select('id, status, order_items(*)')\
            .eq('id', order_id)\
            .single()\
            .execute()
        
        if not current_order.data:
            raise HTTPException(status_code=404, detail="Order not found")
        
        current_status = current_order.data['status']
        order_items = current_order.data.get('order_items', [])
        
        # Handle inventory changes for status transitions
        if current_status != status:
            # Release inventory when order is cancelled or refunded
            if status in ['cancelled', 'refunded'] and current_status not in ['cancelled', 'refunded']:
                if order_items:
                    # Convert order items to expected format for inventory function
                    items_for_release = []
                    for item in order_items:
                        items_for_release.append({
                            'product_id': item['product_id'],
                            'quantity': item['quantity']
                        })
                    
                    inventory_result = await validate_and_update_inventory(items_for_release, db, operation="release")
                    if inventory_result['success']:
                        logger.info(f"Released inventory for cancelled/refunded order {order_id}: {len(inventory_result['updates'])} products")
            
            # Reserve inventory when order is reactivated from cancelled/refunded
            elif current_status in ['cancelled', 'refunded'] and status not in ['cancelled', 'refunded']:
                if order_items:
                    # Convert order items to expected format for inventory function
                    items_for_reserve = []
                    for item in order_items:
                        items_for_reserve.append({
                            'product_id': item['product_id'],
                            'quantity': item['quantity']
                        })
                    
                    inventory_result = await validate_and_update_inventory(items_for_reserve, db, operation="reserve")
                    if not inventory_result['success']:
                        raise HTTPException(status_code=400, detail=f"Cannot reactivate order - inventory error: {inventory_result['error']}")
                    logger.info(f"Reserved inventory for reactivated order {order_id}: {len(inventory_result['updates'])} products")
        
        # Update order status
        db.table('orders')\
            .update({
                'status': status,
                'updated_at': datetime.now().isoformat()
            })\
            .eq('id', order_id)\
            .execute()
        
        # Синхронизируем изменение обратно в Bitrix (опционально)
        try:
            from sync_back import sync_back_service
            sync_back_service.sync_order_status(order_id, status)
        except ImportError:
            logger.warning("sync_back module not available, skipping reverse sync")
        
        return RedirectResponse(f"/crm/orders/{order_id}", status_code=303)
        
    except Exception as e:
        logger.error(f"Update status error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update order status")

# ==================== PRODUCTS ====================

@app.get("/crm/products", response_class=HTMLResponse)
async def list_products(
    request: Request,
    category: Optional[str] = None,
    search: Optional[str] = None,
    seller_id: Optional[str] = None,
    show_inactive: bool = True,  # CRM показывает все товары по умолчанию
    page: int = 1,
    db: Client = Depends(get_supabase)
):
    """List products with filtering and pagination"""
    
    try:
        limit = 50
        offset = (page - 1) * limit
        
        # Получаем список всех активных магазинов для фильтра (с description для подсчета)
        sellers_query = db.table('sellers').select('id, name, description').eq('is_active', True).order('name')
        sellers_result = sellers_query.execute()
        sellers = sellers_result.data if sellers_result.data else []
        
        # Debug: логируем количество найденных магазинов
        logger.info(f"Found {len(sellers)} active sellers for filter dropdown")
        
        # Извлекаем количество товаров из описания (временное решение)
        # Количество сохранено в формате "Товаров: N" в поле description
        import re
        for seller in sellers:
            product_count = 0
            if seller.get('description') and 'Товаров:' in seller.get('description', ''):
                match = re.search(r'Товаров: (\d+)', seller['description'])
                if match:
                    product_count = int(match.group(1))
            seller['product_count'] = product_count
        
        # Debug: проверяем первых 3 магазинов
        if sellers:
            logger.info(f"First 3 sellers: {sellers[:3]}")
        
        # Build query - оптимизированная выборка только нужных полей
        query = db.table('products').select(
            'id, name, price, old_price, is_active, created_at, description, slug, metadata, seller_id',
            count='exact'
        )
        
        # CRM логика: показывать все товары или только активные
        if not show_inactive:
            # Если явно запросили только активные товары
            query = query.eq('is_active', True)
        # По умолчанию (show_inactive=True) показываем все товары для администраторов
        
        # Apply filters
        if category:
            query = query.eq('category_id', category)
        
        if seller_id:
            query = query.eq('seller_id', seller_id)
        
        if search:
            search_term = f"%{search}%"
            query = query.ilike('name', search_term)
        
        # Sort and paginate - активные товары первыми, затем по дате создания
        query = query.order('is_active', desc=True).order('created_at', desc=True)
        query = query.range(offset, offset + limit - 1)
        
        result = query.execute()
        total_pages = (result.count // limit) + (1 if result.count % limit > 0 else 0)
        
        # Если есть seller_id в товарах, получаем информацию о магазинах
        if result.data:
            seller_ids = list(set([p['seller_id'] for p in result.data if p.get('seller_id')]))
            if seller_ids:
                sellers_info_query = db.table('sellers').select('id, name').in_('id', seller_ids)
                sellers_info_result = sellers_info_query.execute()
                sellers_dict = {s['id']: s['name'] for s in sellers_info_result.data} if sellers_info_result.data else {}
                
                # Добавляем название магазина к каждому товару
                for product in result.data:
                    if product.get('seller_id'):
                        product['seller_name'] = sellers_dict.get(product['seller_id'], 'Неизвестный')
        
        return templates.TemplateResponse("products.html", {
            "request": request,
            "products": result.data,
            "total": result.count,
            "page": page,
            "total_pages": total_pages,
            "active_page": "products",
            "search_term": search,
            "sellers": sellers,
            "selected_seller_id": seller_id
        })
        
    except Exception as e:
        logger.error(f"Products list error: {e}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Failed to load products",
            "active_page": "products"
        })

@app.get("/crm/products/new", response_class=HTMLResponse)
async def new_product_form(request: Request):
    """Display form for creating new product"""
    return templates.TemplateResponse("product_new.html", {
        "request": request,
        "active_page": "products"
    })

@app.post("/crm/products/new")
async def create_product(
    request: Request,
    db: Client = Depends(get_supabase)
):
    """Create a new product with composition"""
    try:
        # Parse JSON body
        data = await request.json()
        
        # Generate slug from name
        slug = data['name'].lower().replace(' ', '-').replace('"', '').replace("'", '')
        
        # Extract composition if provided
        composition = data.pop('composition', [])
        
        # Prepare product data
        new_product = {
            "name": data['name'],
            "slug": slug,
            "price": float(data['price']),
            "quantity": data.get('quantity', 0),
            "description": data.get('description'),
            "category_id": data.get('category_id'),
            "is_active": data.get('is_active', True),
            "images": data.get('images', []),  # Store photo URLs/base64
            "metadata": {},  # No SKU anymore
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Insert product into database
        result = db.table('products').insert(new_product).execute()
        
        if result.data:
            product_id = result.data[0]['id']
            logger.info(f"Created new product: {product_id}")
            
            # Save composition if provided
            if composition and isinstance(composition, list):
                for item in composition:
                    if item.get('flower_id') and item.get('amount'):
                        db.table('product_composition').insert({
                            'product_id': product_id,
                            'flower_id': item['flower_id'],
                            'amount': item['amount']
                        }).execute()
            
            return {"id": product_id, "status": "success"}
        else:
            raise HTTPException(status_code=400, detail="Failed to create product")
            
    except Exception as e:
        logger.error(f"Product creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/crm/products/{product_id}", response_class=HTMLResponse)
async def product_detail(
    request: Request,
    product_id: str,
    db: Client = Depends(get_supabase)
):
    """Product detail page"""
    
    try:
        # Get product
        product_result = db.table('products')\
            .select('*')\
            .eq('id', product_id)\
            .single()\
            .execute()
        
        if not product_result.data:
            raise HTTPException(status_code=404, detail="Product not found")
        
        # Get product composition
        composition_result = db.table('product_composition')\
            .select('*, flowers(id, xml_id, name)')\
            .eq('product_id', product_id)\
            .order('amount', desc=True)\
            .execute()
        
        composition = []
        for item in composition_result.data:
            if item.get('flowers'):
                composition.append({
                    'flower_name': item['flowers']['name'],
                    'amount': item['amount']
                })
        
        # Get seller info if available
        seller = None
        if product_result.data.get('seller_id'):
            seller_result = db.table('sellers')\
                .select('*')\
                .eq('id', product_result.data['seller_id'])\
                .single()\
                .execute()
            if seller_result.data:
                seller = seller_result.data
        
        return templates.TemplateResponse("product_detail.html", {
            "request": request,
            "product": product_result.data,
            "composition": composition,
            "seller": seller,
            "active_page": "products"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Product detail error: {e}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Failed to load product details",
            "active_page": "products"
        })

@app.get("/crm/products/{product_id}/edit", response_class=HTMLResponse)
async def edit_product_form(
    request: Request,
    product_id: str,
    db: Client = Depends(get_supabase)
):
    """Product edit form"""
    
    try:
        product_result = db.table('products')\
            .select('*')\
            .eq('id', product_id)\
            .single()\
            .execute()
        
        if not product_result.data:
            raise HTTPException(status_code=404, detail="Product not found")
        
        # Get product composition
        composition_result = db.table('product_composition')\
            .select('*, flowers(id, xml_id, name)')\
            .eq('product_id', product_id)\
            .order('amount', desc=True)\
            .execute()
        
        composition = []
        for item in composition_result.data:
            if item.get('flowers'):
                composition.append({
                    'flower_id': item['flower_id'],
                    'flower_name': item['flowers']['name'],
                    'amount': item['amount']
                })
        
        return templates.TemplateResponse("product_edit.html", {
            "request": request,
            "product": product_result.data,
            "composition": composition,
            "active_page": "products"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Product edit form error: {e}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Failed to load product",
            "active_page": "products"
        })

@app.post("/crm/products/{product_id}/edit")
async def update_product(
    product_id: str,
    request: Request,
    db: Client = Depends(get_supabase)
):
    """Update product with composition"""
    
    try:
        # Parse form data (HTML form submit)
        form_data = await request.form()
        
        # Get current product to preserve metadata
        current = db.table('products').select('metadata').eq('id', product_id).single().execute()
        current_metadata = current.data.get('metadata', {}) if current.data else {}
        
        # Parse composition data from hidden input
        composition_data = form_data.get('composition_data', '[]')
        try:
            composition = json.loads(composition_data) if composition_data else []
        except json.JSONDecodeError:
            composition = []
            logger.warning(f"Invalid composition data: {composition_data}")
        
        # Update product
        db.table('products').update({
            'name': form_data.get('name'),
            'price': float(form_data.get('price', 0)),
            'quantity': int(form_data.get('quantity', 0)),
            'description': form_data.get('description'),
            'metadata': current_metadata,
            'is_active': form_data.get('is_active') == 'true',
            'updated_at': datetime.now().isoformat()
        }).eq('id', product_id).execute()
        
        # Update composition
        # First, delete existing composition
        db.table('product_composition').delete().eq('product_id', product_id).execute()
        
        # Then add new composition
        if composition and isinstance(composition, list):
            for item in composition:
                if item.get('flower_id') and item.get('amount'):
                    db.table('product_composition').insert({
                        'product_id': product_id,
                        'flower_id': item['flower_id'],
                        'amount': item['amount']
                    }).execute()
        
        return RedirectResponse("/crm/products", status_code=303)
        
    except Exception as e:
        logger.error(f"Update product error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update product")

@app.delete("/api/products/{product_id}")
async def delete_product(
    product_id: str,
    db: Client = Depends(get_supabase)
):
    """Delete product and its composition"""
    
    try:
        # First check if product exists
        product_result = db.table('products')\
            .select('id, name')\
            .eq('id', product_id)\
            .single()\
            .execute()
        
        if not product_result.data:
            raise HTTPException(status_code=404, detail="Product not found")
        
        product_name = product_result.data['name']
        
        # Delete composition first (foreign key constraint)
        db.table('product_composition').delete().eq('product_id', product_id).execute()
        
        # Delete the product
        result = db.table('products').delete().eq('id', product_id).execute()
        
        logger.info(f"Deleted product {product_id}: {product_name}")
        
        return {
            "success": True, 
            "message": f"Товар '{product_name}' успешно удален",
            "deleted_product_id": product_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete product error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete product")

# ==================== PRODUCT STATUS MANAGEMENT ====================

async def sync_product_status_to_bitrix(bitrix_id: str, is_active: bool):
    """
    Синхронизирует статус товара с Bitrix через PHP endpoint
    
    Args:
        bitrix_id: ID товара в Bitrix
        is_active: Новый статус товара
    """
    
    # Проверка включена ли синхронизация
    if not app_config.BITRIX_PRODUCT_SYNC_ENABLED:
        logger.info(f"Product sync disabled, skipping sync for bitrix_id={bitrix_id}")
        return
    
    # Проверка наличия bitrix_id
    if not bitrix_id:
        logger.warning("No bitrix_id provided, skipping sync")
        return
    
    payload = {
        "action": "update_product_status",
        "bitrix_id": bitrix_id,
        "is_active": is_active
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                app_config.BITRIX_PRODUCT_SYNC_URL,
                json=payload,
                headers={"X-API-TOKEN": app_config.BITRIX_API_TOKEN}
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    logger.info(f"✅ Product {bitrix_id} status synced to Bitrix (active={is_active})")
                else:
                    logger.error(f"❌ Bitrix sync failed: {result.get('error', 'Unknown error')}")
            else:
                logger.error(f"❌ Failed to sync product {bitrix_id}: HTTP {response.status_code}")
                
    except httpx.TimeoutException:
        logger.error(f"⏱️ Timeout syncing product {bitrix_id} to Bitrix")
    except Exception as e:
        logger.error(f"❌ Error syncing product {bitrix_id} to Bitrix: {e}")
        # Не блокируем основную операцию при ошибке синхронизации

@app.post("/api/products/{product_id}/activate")
async def activate_product(
    product_id: str,
    db: Client = Depends(get_supabase)
):
    """Активировать товар"""
    
    try:
        # Проверяем что товар существует и получаем его metadata
        product_result = db.table('products')\
            .select('id, name, is_active, metadata')\
            .eq('id', product_id)\
            .single()\
            .execute()
        
        if not product_result.data:
            raise HTTPException(status_code=404, detail="Товар не найден")
        
        product = product_result.data
        product_name = product['name']
        metadata = product.get('metadata', {}) or {}
        bitrix_id = metadata.get('bitrix_id')
        
        if product['is_active']:
            return {
                "success": False,
                "message": f"Товар '{product_name}' уже активен",
                "product_id": product_id,
                "is_active": True
            }
        
        # Активируем товар в Supabase
        result = db.table('products')\
            .update({
                'is_active': True,
                'updated_at': datetime.utcnow().isoformat()
            })\
            .eq('id', product_id)\
            .execute()
        
        logger.info(f"Activated product {product_id}: {product_name}")
        
        # Синхронизируем с Bitrix асинхронно
        if bitrix_id:
            asyncio.create_task(sync_product_status_to_bitrix(bitrix_id, True))
        
        return {
            "success": True,
            "message": f"Товар '{product_name}' активирован",
            "product_id": product_id,
            "is_active": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Activate product error: {e}")
        raise HTTPException(status_code=500, detail="Failed to activate product")

@app.post("/api/products/{product_id}/deactivate")
async def deactivate_product(
    product_id: str,
    db: Client = Depends(get_supabase)
):
    """Деактивировать товар"""
    
    try:
        # Проверяем что товар существует и получаем его metadata
        product_result = db.table('products')\
            .select('id, name, is_active, metadata')\
            .eq('id', product_id)\
            .single()\
            .execute()
        
        if not product_result.data:
            raise HTTPException(status_code=404, detail="Товар не найден")
        
        product = product_result.data
        product_name = product['name']
        metadata = product.get('metadata', {}) or {}
        bitrix_id = metadata.get('bitrix_id')
        
        if not product['is_active']:
            return {
                "success": False,
                "message": f"Товар '{product_name}' уже деактивирован",
                "product_id": product_id,
                "is_active": False
            }
        
        # Деактивируем товар в Supabase
        result = db.table('products')\
            .update({
                'is_active': False,
                'updated_at': datetime.utcnow().isoformat()
            })\
            .eq('id', product_id)\
            .execute()
        
        logger.info(f"Deactivated product {product_id}: {product_name}")
        
        # Синхронизируем с Bitrix асинхронно
        if bitrix_id:
            asyncio.create_task(sync_product_status_to_bitrix(bitrix_id, False))
        
        return {
            "success": True,
            "message": f"Товар '{product_name}' деактивирован",
            "product_id": product_id,
            "is_active": False
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Deactivate product error: {e}")
        raise HTTPException(status_code=500, detail="Failed to deactivate product")

# ==================== AVAILABILITY MANAGEMENT ====================

async def sync_product_availability_to_bitrix(bitrix_id: str, is_available: bool):
    """Синхронизация наличия товара в Bitrix через свойство IN_STOCK"""
    if not app_config.BITRIX_PRODUCT_SYNC_ENABLED:
        logger.info("Product sync is disabled")
        return
        
    try:
        payload = {
            "action": "update_product_availability",
            "bitrix_id": bitrix_id,
            "is_available": is_available
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                app_config.BITRIX_PRODUCT_SYNC_URL,
                json=payload,
                headers={"X-API-TOKEN": app_config.BITRIX_API_TOKEN}
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get('success'):
                logger.info(f"✅ Product {bitrix_id} availability synced to Bitrix: {is_available}")
            else:
                logger.error(f"❌ Failed to sync product {bitrix_id} availability: {result.get('error')}")
                
    except Exception as e:
        logger.error(f"❌ Error syncing product {bitrix_id} availability to Bitrix: {e}")

@app.post("/api/products/{product_id}/set-available")
async def set_product_available(
    product_id: str,
    db: Client = Depends(get_supabase)
):
    """Сделать товар доступным (в наличии)"""
    
    try:
        # Проверяем что товар существует и получаем его metadata
        product_result = db.table('products')\
            .select('id, name, metadata')\
            .eq('id', product_id)\
            .execute()
            
        if not product_result.data:
            raise HTTPException(status_code=404, detail="Product not found")
            
        product = product_result.data[0]
        product_name = product.get('name', 'Unknown')
        
        # Обновляем metadata.properties.IN_STOCK на '158' (в наличии)
        metadata = product.get('metadata', {})
        if not isinstance(metadata, dict):
            metadata = {}
        
        if 'properties' not in metadata:
            metadata['properties'] = {}
        
        metadata['properties']['IN_STOCK'] = '158'  # В наличии
        
        # Обновляем товар в базе данных
        db.table('products')\
            .update({
                'metadata': metadata,
                'updated_at': datetime.now().isoformat()
            })\
            .eq('id', product_id)\
            .execute()
        
        # Получаем bitrix_id для синхронизации
        bitrix_id = None
        if isinstance(metadata, dict):
            bitrix_id = metadata.get('bitrix_id')
        
        if not bitrix_id:
            logger.warning(f"Product {product_id} has no bitrix_id, skipping Bitrix sync")
        
        logger.info(f"✅ Product '{product_name}' set as AVAILABLE (IN_STOCK=158)")
        
        # Синхронизируем с Bitrix если есть bitrix_id
        if bitrix_id:
            asyncio.create_task(sync_product_availability_to_bitrix(bitrix_id, True))
        
        return {
            "success": True,
            "message": f"Товар '{product_name}' сделан доступным",
            "product_id": product_id,
            "is_available": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Set available error: {e}")
        raise HTTPException(status_code=500, detail="Failed to set product as available")

@app.post("/api/products/{product_id}/set-unavailable")
async def set_product_unavailable(
    product_id: str,
    db: Client = Depends(get_supabase)
):
    """Сделать товар недоступным (нет в наличии)"""
    
    try:
        # Проверяем что товар существует и получаем его metadata
        product_result = db.table('products')\
            .select('id, name, metadata')\
            .eq('id', product_id)\
            .execute()
            
        if not product_result.data:
            raise HTTPException(status_code=404, detail="Product not found")
            
        product = product_result.data[0]
        product_name = product.get('name', 'Unknown')
        
        # Обновляем metadata.properties.IN_STOCK на '159' (нет в наличии)
        metadata = product.get('metadata', {})
        if not isinstance(metadata, dict):
            metadata = {}
        
        if 'properties' not in metadata:
            metadata['properties'] = {}
        
        metadata['properties']['IN_STOCK'] = '159'  # Нет в наличии
        
        # Обновляем товар в базе данных
        db.table('products')\
            .update({
                'metadata': metadata,
                'updated_at': datetime.now().isoformat()
            })\
            .eq('id', product_id)\
            .execute()
        
        # Получаем bitrix_id для синхронизации
        bitrix_id = None
        if isinstance(metadata, dict):
            bitrix_id = metadata.get('bitrix_id')
        
        if not bitrix_id:
            logger.warning(f"Product {product_id} has no bitrix_id, skipping Bitrix sync")
        
        logger.info(f"❌ Product '{product_name}' set as UNAVAILABLE (IN_STOCK=159)")
        
        # Синхронизируем с Bitrix если есть bitrix_id
        if bitrix_id:
            asyncio.create_task(sync_product_availability_to_bitrix(bitrix_id, False))
        
        return {
            "success": True,
            "message": f"Товар '{product_name}' сделан недоступным",
            "product_id": product_id,
            "is_available": False
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Set unavailable error: {e}")
        raise HTTPException(status_code=500, detail="Failed to set product as unavailable")


# ==================== WAREHOUSE (СКЛАД) ====================

# ==================== INVENTORY MANAGEMENT ====================

@app.get("/crm/inventory", response_class=HTMLResponse)
async def inventory_management(
    request: Request,
    search: Optional[str] = None,
    page: int = 1,
    db: Client = Depends(get_supabase)
):
    """Inventory management page for flowers"""
    
    try:
        limit = 50
        offset = (page - 1) * limit
        
        # Build query for flowers with stock information
        query = db.table('flowers').select('id, name, name_en, quantity, is_active, updated_at', count='exact')
        
        # Apply search filter
        if search:
            search_term = f"%{search}%"
            query = query.ilike('name', search_term)
        
        # Sort and paginate
        query = query.order('quantity', desc=False).order('name')
        query = query.range(offset, offset + limit - 1)
        
        result = query.execute()
        total_pages = (result.count // limit) + (1 if result.count % limit > 0 else 0)
        
        # Get total count of flower types
        total_flowers = db.table('flowers').select('*', count='exact').execute().count
        
        return templates.TemplateResponse("inventory.html", {
            "request": request,
            "flowers": result.data or [],  # Переименовали с products на flowers
            "total": result.count,
            "page": page,
            "total_pages": total_pages,
            "active_page": "inventory",
            "search_term": search,
            "stats": {
                "total": total_flowers
            }
        })
        
    except Exception as e:
        logger.error(f"Inventory management error: {e}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Failed to load inventory",
            "active_page": "inventory"
        })

@app.get("/crm/warehouse", response_class=HTMLResponse)
async def warehouse_dashboard(
    request: Request,
    search: Optional[str] = None,
    db: Client = Depends(get_supabase)
):
    """Warehouse (Склад) dashboard showing all flowers with usage statistics"""
    
    try:
        # Get all flowers
        query = db.table('flowers').select('*').order('name')
        
        if search:
            query = query.ilike('name', f'%{search}%')
        
        flowers_result = query.execute()
        
        # OPTIMIZED: Get all composition statistics in one query
        all_compositions = db.table('product_composition')\
            .select('flower_id, amount, products(id, name, metadata)')\
            .execute()
        
        # Group compositions by flower_id for fast lookup
        composition_by_flower = {}
        for comp in all_compositions.data:
            flower_id = comp['flower_id']
            if flower_id not in composition_by_flower:
                composition_by_flower[flower_id] = []
            composition_by_flower[flower_id].append(comp)
        
        # Build warehouse statistics
        warehouse_stats = []
        
        for flower in flowers_result.data:
            flower_compositions = composition_by_flower.get(flower['id'], [])
            
            # Calculate statistics from the grouped data
            total_used = sum(comp['amount'] for comp in flower_compositions)
            products_count = len(flower_compositions)
            
            # Get recent products that use this flower (limit to 5)
            recent_usage = []
            for comp in flower_compositions[:5]:  # Take only first 5
                if comp.get('products'):
                    recent_usage.append({
                        'product_name': comp['products']['name'],
                        'amount': comp['amount']
                    })
            
            warehouse_stats.append({
                'flower': flower,
                'total_used': total_used,
                'products_count': products_count,
                'recent_usage': recent_usage
            })
        
        # Sort by most used flowers
        warehouse_stats.sort(key=lambda x: x['total_used'], reverse=True)
        
        return templates.TemplateResponse("warehouse.html", {
            "request": request,
            "warehouse_stats": warehouse_stats,
            "search": search or "",
            "active_page": "warehouse",
            "total_flowers": len(warehouse_stats)
        })
        
    except Exception as e:
        logger.error(f"Warehouse dashboard error: {e}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Failed to load warehouse data",
            "active_page": "warehouse"
        })


# ==================== FLOWER DETAIL ENDPOINTS ====================

@app.get("/crm/warehouse/{flower_id}", response_class=HTMLResponse)
async def flower_detail(
    request: Request,
    flower_id: str,
    db: Client = Depends(get_supabase)
):
    """
    Детальная страница цветка с возможностью редактирования
    """
    try:
        # Get flower data
        flower_result = db.table('flowers')\
            .select('*')\
            .eq('id', flower_id)\
            .limit(1)\
            .execute()
        
        if not flower_result.data:
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error": "Цветок не найден",
                "active_page": "warehouse"
            })
        
        flower = flower_result.data[0]
        
        # Get composition statistics for this flower
        compositions = db.table('product_composition')\
            .select('product_id, amount, products(id, name, price, is_active, created_at)')\
            .eq('flower_id', flower_id)\
            .execute()
        
        # Calculate statistics
        total_used = sum(comp['amount'] for comp in compositions.data)
        products_count = len(compositions.data)
        
        # Prepare products list with details
        products_using_flower = []
        total_products_value = 0
        
        for comp in compositions.data:
            if comp.get('products'):
                product = comp['products']
                product_info = {
                    'id': product['id'],
                    'name': product['name'],
                    'price': product.get('price', 0),
                    'amount_used': comp['amount'],
                    'is_active': product.get('is_active', True),
                    'created_at': product.get('created_at'),
                    'total_value': float(product.get('price', 0)) * comp['amount']
                }
                products_using_flower.append(product_info)
                total_products_value += product_info['total_value']
        
        # Sort products by usage amount (descending)
        products_using_flower.sort(key=lambda x: x['amount_used'], reverse=True)
        
        # Calculate average usage
        avg_usage = total_used / products_count if products_count > 0 else 0
        
        return templates.TemplateResponse("flower_detail.html", {
            "request": request,
            "flower": flower,
            "total_used": total_used,
            "products_count": products_count,
            "avg_usage": round(avg_usage, 1),
            "products_using_flower": products_using_flower,
            "total_products_value": total_products_value,
            "active_page": "warehouse"
        })
        
    except Exception as e:
        logger.error(f"Flower detail error: {e}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Ошибка загрузки данных цветка",
            "active_page": "warehouse"
        })

@app.post("/crm/warehouse/{flower_id}")
async def update_flower(
    request: Request,
    flower_id: str,
    db: Client = Depends(get_supabase)
):
    """
    Обновление данных цветка
    """
    try:
        # Get form data
        form_data = await request.form()
        
        # Validate data
        update_data = {
            'name': form_data.get('name', '').strip(),
            'name_en': form_data.get('name_en', '').strip() or None,
            'sort_order': int(form_data.get('sort_order', 500)),
            'is_active': form_data.get('is_active') == 'true',
            'updated_at': datetime.now().isoformat()
        }
        
        # Validate required fields
        if not update_data['name']:
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error": "Название цветка обязательно для заполнения",
                "active_page": "warehouse"
            })
        
        # Update flower in database
        result = db.table('flowers')\
            .update(update_data)\
            .eq('id', flower_id)\
            .execute()
        
        if not result.data:
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error": "Не удалось обновить цветок",
                "active_page": "warehouse"
            })
        
        logger.info(f"Updated flower {flower_id}: {update_data['name']}")
        
        # Redirect back to flower detail page
        return RedirectResponse(f"/crm/warehouse/{flower_id}", status_code=303)
        
    except ValueError as e:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": f"Неверные данные: {str(e)}",
            "active_page": "warehouse"
        })
    except Exception as e:
        logger.error(f"Flower update error: {e}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Ошибка обновления цветка",
            "active_page": "warehouse"
        })


# ==================== WEBHOOK ENDPOINTS ====================

@app.post("/api/webhooks/bitrix/order")
async def webhook_bitrix_order(
    request: Request,
    x_webhook_token: Optional[str] = Header(None),
    db: Client = Depends(get_supabase)
):
    """
    Webhook endpoint для приема новых/обновленных заказов от Bitrix
    """
    from webhook_handler import WebhookHandler
    
    handler = WebhookHandler(db)
    
    # Проверка токена
    if not handler.verify_webhook_token(x_webhook_token or ''):
        logger.warning(f"Invalid webhook token received: {x_webhook_token}")
        raise HTTPException(status_code=401, detail="Invalid webhook token")
    
    try:
        # Получаем данные из webhook
        data = await request.json()
        logger.info(f"Received order webhook from Bitrix: {data.get('order_id', 'unknown')}")
        
        # Обрабатываем webhook
        result = await handler.handle_order_webhook(data)
        
        return result
        
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/webhooks/bitrix/status")
async def webhook_bitrix_status(
    request: Request,
    x_webhook_token: Optional[str] = Header(None),
    db: Client = Depends(get_supabase)
):
    """
    Webhook endpoint для приема изменений статуса заказа от Bitrix
    """
    from webhook_handler import WebhookHandler
    
    handler = WebhookHandler(db)
    
    # Проверка токена
    if not handler.verify_webhook_token(x_webhook_token or ''):
        raise HTTPException(status_code=401, detail="Invalid webhook token")
    
    try:
        data = await request.json()
        result = await handler.handle_status_webhook(data)
        return result
        
    except Exception as e:
        logger.error(f"Status webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sync/status")
async def get_sync_status(db: Client = Depends(get_supabase)):
    """
    API endpoint для получения статуса синхронизации
    """
    from webhook_handler import WebhookHandler
    
    handler = WebhookHandler(db)
    stats = handler.get_sync_statistics()
    
    return stats

# ==================== FLOWERS API ====================

@app.get("/api/flowers")
async def get_flowers(
    db: Client = Depends(get_supabase)
):
    """Get all active flowers from dictionary"""
    try:
        result = db.table('flowers')\
            .select('*')\
            .eq('is_active', True)\
            .order('sort_order')\
            .execute()
        
        return result.data
    except Exception as e:
        logger.error(f"Get flowers error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get flowers")


@app.post("/api/flowers", status_code=201)
async def create_flower(
    flower_data: dict,
    db: Client = Depends(get_supabase)
):
    """Create a new flower in dictionary"""
    try:
        result = db.table('flowers')\
            .insert(flower_data)\
            .execute()
        
        if result.data:
            logger.info(f"Created flower: {flower_data.get('name')} ({flower_data.get('xml_id')})")
            return result.data[0]
        else:
            raise HTTPException(status_code=400, detail="Failed to create flower")
            
    except Exception as e:
        logger.error(f"Create flower error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create flower: {str(e)}")

@app.post("/api/flowers/bulk_update_names")
async def bulk_update_flower_names(
    db: Client = Depends(get_supabase)
):
    """Mass update flower names from English to Russian"""
    try:
        # Translation dictionary for English to Russian flower names
        translations = {
            "Dutch Roses": "Голландские розы",
            "Eustomas": "Эустомы", 
            "Callas": "Каллы",
            "Field Flowers": "Полевые цветы",
            "Peony Roses": "Пионовидные розы",
            "Anthuriums": "Антуриумы",
            "Asters": "Астры",
            "Cornflowers": "Васильки",
            "Hyacinths": "Гиацинты",
            "Hypericum": "Зверобой",
            "Irises": "Ирисы",
            "Lilacs": "Сирень",
            "Ranunculus": "Лютики",
            "Pistachio": "Фисташка",
            "Alanhoe": "Каланхоэ",
            "Alenopsis": "Фаленопсис",
            "Amedoreya": "Хамедорея",
            "Anemon": "Анемона",
            "Diantum": "Диантус",
            "Edilantus": "Эдилантус",
            "Efflera": "Эффлера",
            "Egoniya": "Бегония",
            "Eperomiya": "Пеперомия",
            "Ern": "Папоротник",
            "Georgin": "Георгин",
            "Glaonema": "Аглаонема",
            "Ikus": "Икус",
            "Ileks": "Илекс",
            "Lagurus": "Лагурус",
            "Miks": "Микс",
            "Nobilis": "Нобилис",
            "Ordilina": "Ордилина",
            "Patifillum": "Спатифиллум",
            "Pionovidnyy Tyulpan": "Пионовидный тюльпан",
            "Podsolnuhi": "Подсолнечник",
            "Racena": "Драцена",
            "Rizantema": "Ризантема",
            "Ruskus": "Рускус",
            "Statica": "Статица",
            "Stifa": "Стифа",
            "Suhocvet": "Сухоцвет",
            "Trelitciya": "Стрелиция",
            "Tyulpanov": "Тюльпан",
            "Ukkulent": "Суккулент",
            "Uzmaniya": "Узмания",
            "Viburnum": "Калина"
        }
        
        updated_count = 0
        
        for english_name, russian_name in translations.items():
            # Find and update flowers with English names
            result = db.table('flowers')\
                .update({'name': russian_name})\
                .eq('name', english_name)\
                .execute()
            
            if result.data:
                updated_count += len(result.data)
                logger.info(f"Updated '{english_name}' to '{russian_name}'")
        
        return {
            "success": True,
            "updated_count": updated_count,
            "message": f"Successfully updated {updated_count} flower names to Russian"
        }
        
    except Exception as e:
        logger.error(f"Bulk update flower names error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/flowers/fix_encoding")
async def fix_flower_encoding(
    db: Client = Depends(get_supabase)
):
    """Fix encoding issues by deactivating corrupted records"""
    try:
        # Deactivate the corrupted garden-peonies record
        result = db.table('flowers')\
            .update({'is_active': False})\
            .eq('xml_id', 'garden-peonies')\
            .execute()
        
        deactivated_count = len(result.data) if result.data else 0
        
        return {
            "success": True,
            "deactivated_count": deactivated_count,
            "message": f"Deactivated {deactivated_count} corrupted records"
        }
        
    except Exception as e:
        logger.error(f"Fix encoding error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== PRODUCT COMPOSITION API ====================

@app.get("/api/products/{product_id}/composition")
async def get_product_composition(
    product_id: str,
    db: Client = Depends(get_supabase)
):
    """Get composition for a product"""
    try:
        # Get composition with flower details
        result = db.table('product_composition')\
            .select('*, flowers(id, xml_id, name)')\
            .eq('product_id', product_id)\
            .order('amount', desc=True)\
            .execute()
        
        # Format response
        composition = []
        for item in result.data:
            if item.get('flowers'):
                composition.append({
                    'id': item['id'],
                    'flower_id': item['flower_id'],
                    'flower_name': item['flowers']['name'],
                    'flower_xml_id': item['flowers']['xml_id'],
                    'amount': item['amount']
                })
        
        return composition
    except Exception as e:
        logger.error(f"Get product composition error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get product composition")

@app.post("/api/products/{product_id}/composition")
async def update_product_composition(
    product_id: str,
    composition: List[ProductCompositionRequest],
    db: Client = Depends(get_supabase)
):
    """Update product composition"""
    try:
        # Delete existing composition
        db.table('product_composition')\
            .delete()\
            .eq('product_id', product_id)\
            .execute()
        
        # Insert new composition
        if composition:
            new_items = []
            for item in composition:
                new_items.append({
                    'product_id': product_id,
                    'flower_id': item.flower_id,
                    'amount': item.amount
                })
            
            result = db.table('product_composition')\
                .insert(new_items)\
                .execute()
        
        return {"status": "success", "message": "Composition updated"}
    except Exception as e:
        logger.error(f"Update product composition error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update product composition")

@app.post("/api/product_composition", status_code=201)
async def create_product_composition(
    composition_data: dict,
    db: Client = Depends(get_supabase)
):
    """Create a single product composition entry"""
    try:
        result = db.table('product_composition')\
            .insert(composition_data)\
            .execute()
        
        if result.data:
            logger.info(f"Created composition: product {composition_data.get('product_id')} + flower {composition_data.get('flower_id')}")
            return result.data[0]
        else:
            raise HTTPException(status_code=400, detail="Failed to create composition")
            
    except Exception as e:
        logger.error(f"Create composition error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create composition: {str(e)}")

# ==================== API ENDPOINTS ====================

@app.get("/api/products/search")
async def search_products(
    q: str,
    db: Client = Depends(get_supabase)
):
    """Search products by name for order creation"""
    try:
        # Search products
        products = db.table('products')\
            .select('id, name, price, quantity')\
            .ilike('name', f'%{q}%')\
            .eq('is_active', True)\
            .limit(10)\
            .execute()
        
        return products.data or []
        
    except Exception as e:
        logger.error(f"Product search error: {e}")
        return []

@app.get("/api/orders/stats")
async def get_order_stats(db: Client = Depends(get_supabase)):
    """API endpoint for order statistics"""
    
    try:
        today = date.today().isoformat()
        
        # Today's orders
        today_orders = db.table('orders')\
            .select('id, total_amount', count='exact')\
            .gte('created_at', today)\
            .execute()
        
        # Orders by status
        all_orders = db.table('orders')\
            .select('status')\
            .execute()
        
        status_counts = {}
        for order in all_orders.data:
            status = order['status']
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "today": {
                "count": today_orders.count,
                "revenue": sum(float(o['total_amount']) for o in today_orders.data)
            },
            "statuses": status_counts
        }
        
    except Exception as e:
        logger.error(f"Stats API error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get statistics")

# ==================== SYNC MONITORING ====================

@app.get("/crm/sync", response_class=HTMLResponse)
async def sync_monitoring(
    request: Request,
    db: Client = Depends(get_supabase)
):
    """Страница мониторинга синхронизации"""
    
    try:
        from webhook_handler import WebhookHandler
        
        handler = WebhookHandler(db)
        stats = handler.get_sync_statistics()
        
        # Получаем состояние синхронизации
        sync_state = db.table('sync_state')\
            .select('*')\
            .execute()
        
        # Получаем маппинги
        mappings_count = db.table('sync_mapping')\
            .select('entity_type', count='exact')\
            .execute()
        
        return templates.TemplateResponse("sync_monitoring.html", {
            "request": request,
            "stats": stats,
            "sync_state": sync_state.data,
            "mappings_count": mappings_count.count,
            "active_page": "sync"
        })
        
    except Exception as e:
        logger.error(f"Sync monitoring error: {e}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Failed to load sync monitoring",
            "active_page": "sync"
        })

# ==================== FLORISTS API ====================

@app.get("/api/florists")
async def get_florists(db: Client = Depends(get_supabase)):
    """Get all florists for Cvetykz shop (Bitrix shop_id 17008)"""
    
    try:
        # Get florists with shop_id = Cvetykz UUID and bitrix_shop_id = "17008"
        cvetykz_shop_id = "7f52091f-a6f1-4d23-a2c9-6754109065f4"
        bitrix_shop_id = "17008"
        
        result = db.table('users')\
            .select('id, name, email, phone, preferences')\
            .eq('preferences->>shop_id', cvetykz_shop_id)\
            .eq('preferences->>bitrix_shop_id', bitrix_shop_id)\
            .eq('preferences->>is_florist', 'true')\
            .order('name')\
            .execute()
        
        florists = []
        for user in result.data:
            preferences = user.get('preferences', {})
            florists.append({
                'id': user['id'],
                'name': user['name'],
                'email': user.get('email'),
                'phone': user.get('phone'),
                'role': preferences.get('florist_role', 'Флорист'),
                'bitrix_id': preferences.get('bitrix_id'),
                'is_active': preferences.get('is_active', True)
            })
        
        # Сортируем: сначала главные флористы, потом обычные
        florists.sort(key=lambda x: (0 if x['role'] == 'Главный флорист' else 1, x['name'] or ''))
        
        logger.info(f"Found {len(florists)} florists for Cvetykz (shop_id: {cvetykz_shop_id}, bitrix_shop_id: {bitrix_shop_id})")
        return {"florists": florists}
        
    except Exception as e:
        logger.error(f"Get florists error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get florists")

@app.post("/api/orders/{order_id}/assign-florist")
async def assign_florist(
    order_id: str,
    florist_id: str = Form(...),
    db: Client = Depends(get_supabase)
):
    """Assign florist to order"""
    
    try:
        # Validate florist exists, is active, and belongs to Cvetykz shop
        cvetykz_shop_id = "7f52091f-a6f1-4d23-a2c9-6754109065f4"
        bitrix_shop_id = "17008"
        
        florist_result = db.table('users')\
            .select('id, name, preferences')\
            .eq('id', florist_id)\
            .eq('preferences->>shop_id', cvetykz_shop_id)\
            .eq('preferences->>bitrix_shop_id', bitrix_shop_id)\
            .eq('preferences->>is_florist', 'true')\
            .single()\
            .execute()
        
        if not florist_result.data:
            raise HTTPException(status_code=400, detail="Invalid florist")
        
        florist = florist_result.data
        florist_name = florist['name']
        
        # Update order with responsible florist
        db.table('orders')\
            .update({
                'responsible_id': florist_id,
                'responsible_name': florist_name,
                'updated_at': datetime.now().isoformat()
            })\
            .eq('id', order_id)\
            .execute()
        
        logger.info(f"Assigned florist {florist_name} to order {order_id}")
        return {
            "success": True,
            "florist": {
                "id": florist_id,
                "name": florist_name,
                "role": florist.get('preferences', {}).get('florist_role', 'Флорист')
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Assign florist error: {e}")
        raise HTTPException(status_code=500, detail="Failed to assign florist")

# ============= REST API Endpoints =============

@app.get("/api/products")
async def api_get_products(
    db: Client = Depends(get_supabase),
    skip: int = 0,
    limit: int = 100,
    include_inactive: bool = False,
    seller_id: Optional[str] = None
):
    """Get all products via API"""
    try:
        query = db.table('products').select('*')
        
        # По умолчанию показываем только активные товары
        if not include_inactive:
            query = query.eq('is_active', True)
        
        # Фильтр по магазину если указан
        if seller_id:
            query = query.eq('seller_id', seller_id)
        
        result = query.range(skip, skip + limit - 1).execute()
        return result.data
    except Exception as e:
        logger.error(f"API get products error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/products/{product_id}/activate")
async def activate_product(
    product_id: str,
    db: Client = Depends(get_supabase)
):
    """Activate a single product"""
    try:
        # Check if product exists
        product = db.table('products').select('*').eq('id', product_id).execute()
        if not product.data:
            raise HTTPException(status_code=404, detail="Product not found")
        
        # Update product status
        result = db.table('products')\
            .update({'is_active': True})\
            .eq('id', product_id)\
            .execute()
        
        # Sync to Bitrix if enabled
        if app_config.BITRIX_SYNC_ENABLED and product.data[0].get('bitrix_product_id'):
            await sync_product_status_to_bitrix(
                product.data[0]['bitrix_product_id'], 
                is_active=True
            )
        
        logger.info(f"✅ Product {product_id} activated")
        return {"success": True, "product_id": product_id, "is_active": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating product {product_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/products/{product_id}/deactivate")
async def deactivate_product(
    product_id: str,
    db: Client = Depends(get_supabase)
):
    """Deactivate a single product"""
    try:
        # Check if product exists
        product = db.table('products').select('*').eq('id', product_id).execute()
        if not product.data:
            raise HTTPException(status_code=404, detail="Product not found")
        
        # Update product status
        result = db.table('products')\
            .update({'is_active': False})\
            .eq('id', product_id)\
            .execute()
        
        # Sync to Bitrix if enabled
        if app_config.BITRIX_SYNC_ENABLED and product.data[0].get('bitrix_product_id'):
            await sync_product_status_to_bitrix(
                product.data[0]['bitrix_product_id'], 
                is_active=False
            )
        
        logger.info(f"❌ Product {product_id} deactivated")
        return {"success": True, "product_id": product_id, "is_active": False}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deactivating product {product_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/products/bulk-activate")
async def bulk_activate_products(
    product_ids: List[str],
    db: Client = Depends(get_supabase)
):
    """Activate multiple products at once"""
    try:
        if not product_ids:
            raise HTTPException(status_code=400, detail="No product IDs provided")
        
        # Update all products
        result = db.table('products')\
            .update({'is_active': True})\
            .in_('id', product_ids)\
            .execute()
        
        activated_count = len(result.data) if result.data else 0
        
        # Sync to Bitrix if enabled (async in background)
        if app_config.BITRIX_SYNC_ENABLED:
            for product in result.data:
                if product.get('bitrix_product_id'):
                    asyncio.create_task(
                        sync_product_status_to_bitrix(
                            product['bitrix_product_id'], 
                            is_active=True
                        )
                    )
        
        logger.info(f"✅ Bulk activated {activated_count} products")
        return {
            "success": True, 
            "activated_count": activated_count,
            "product_ids": product_ids
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error bulk activating products: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/products/bulk-deactivate")
async def bulk_deactivate_products(
    product_ids: List[str],
    db: Client = Depends(get_supabase)
):
    """Deactivate multiple products at once"""
    try:
        if not product_ids:
            raise HTTPException(status_code=400, detail="No product IDs provided")
        
        # Update all products
        result = db.table('products')\
            .update({'is_active': False})\
            .in_('id', product_ids)\
            .execute()
        
        deactivated_count = len(result.data) if result.data else 0
        
        # Sync to Bitrix if enabled (async in background)
        if app_config.BITRIX_SYNC_ENABLED:
            for product in result.data:
                if product.get('bitrix_product_id'):
                    asyncio.create_task(
                        sync_product_status_to_bitrix(
                            product['bitrix_product_id'], 
                            is_active=False
                        )
                    )
        
        logger.info(f"❌ Bulk deactivated {deactivated_count} products")
        return {
            "success": True, 
            "deactivated_count": deactivated_count,
            "product_ids": product_ids
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error bulk deactivating products: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/orders")
async def api_create_order(
    order_data: dict,
    db: Client = Depends(get_supabase)
):
    """Create a new order via API"""
    try:
        # Generate order number using synchronized production number generator
        new_number = order_number_generator.generate_order_number(
            is_webhook=False,
            force_local=False
        )
        logger.info(f"Generated new order number: {new_number}")
        
        # Check if number already exists in Supabase
        existing_order = db.table('orders').select('id').eq('order_number', new_number).execute()
        if existing_order.data:
            # If exists, use local prefix to avoid conflicts
            new_number = order_number_generator.generate_local_order_number()
            logger.warning(f"Order number collision detected, using local number: {new_number}")
        
        # Validate and update inventory first
        inventory_result = await validate_and_update_inventory(order_data.get('items', []), db, operation="reserve")
        if not inventory_result['success']:
            raise HTTPException(status_code=400, detail=f"Inventory error: {inventory_result['error']}")
        
        # Calculate total
        total = sum(item.get('price', 0) * item.get('quantity', 1) 
                   for item in order_data.get('items', []))
        
        # Prepare order data - use actual table columns
        new_order = {
            "order_number": new_number,
            "status": order_data.get('status', 'new'),
            "recipient_name": order_data.get('recipient_name', order_data.get('customer_name')),
            "recipient_phone": order_data.get('recipient_phone', order_data.get('customer_phone')),
            "delivery_address": order_data.get('delivery_address'),
            "delivery_date": order_data.get('delivery_date'),
            "delivery_time": order_data.get('delivery_time'),
            "payment_method": order_data.get('payment_method', 'cash'),
            "payment_status": order_data.get('payment_status', 'pending'),
            "postcard_text": order_data.get('postcard_text'),
            "comment": order_data.get('comment'),
            "total_amount": total,
            "delivery_fee": order_data.get('delivery_fee', 0),
            "discount_amount": order_data.get('discount_amount', 0),
            "metadata": {
                "user_name": order_data.get('customer_name', order_data.get('user_name')),
                "user_phone": order_data.get('customer_phone', order_data.get('user_phone'))
            },
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Insert order
        order_result = db.table('orders').insert(new_order).execute()
        
        if order_result.data:
            order_id = order_result.data[0]['id']
            
            try:
                # Insert order items
                for item in order_data.get('items', []):
                    order_item = {
                        "order_id": order_id,
                        "product_id": item.get('product_id'),
                        "quantity": item.get('quantity', 1),
                        "price": item.get('price', 0),
                        "total": item.get('price', 0) * item.get('quantity', 1),
                        "product_snapshot": {
                            "name": item.get('product_name', 'Product'),
                            "price": item.get('price', 0)
                        }
                    }
                    db.table('order_items').insert(order_item).execute()
                
                logger.info(f"API created order: {order_id} with number {new_number} (inventory reserved: {len(inventory_result['updates'])} products)")
                return {
                    "success": True,
                    "order": {
                        "id": order_id,
                        "order_number": new_number,
                        "status": "new",
                        "total_amount": total
                    }
                }
                
            except Exception as e:
                # If order items creation fails, rollback inventory changes
                logger.error(f"API order items creation failed, rolling back inventory: {e}")
                await validate_and_update_inventory(order_data.get('items', []), db, operation="release")
                raise e
        else:
            # If order creation fails, rollback inventory changes
            await validate_and_update_inventory(order_data.get('items', []), db, operation="release")
            raise HTTPException(status_code=400, detail="Failed to create order")
            
    except Exception as e:
        logger.error(f"API order creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/orders")
async def api_get_orders(
    db: Client = Depends(get_supabase),
    skip: int = 0,
    limit: int = 100
):
    """Get all orders via API"""
    try:
        result = db.table('orders')\
            .select('*, order_items(*)')\
            .order('created_at', desc=True)\
            .range(skip, skip + limit - 1)\
            .execute()
        return result.data
    except Exception as e:
        logger.error(f"API get orders error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== PRE-DELIVERY PHOTOS ====================

@app.post("/api/orders/{order_id}/pre-delivery-photos")
async def upload_pre_delivery_photos(
    order_id: str,
    photos: List[UploadFile] = File(...),
    db: Client = Depends(get_supabase)
):
    """
    Upload pre-delivery photos for an order and automatically change status to 'assembled'
    Only allowed for orders with status 'accepted'
    """
    try:
        # 1. Проверяем существование заказа и его статус
        order_result = db.table('orders').select('*').eq('id', order_id).execute()
        if not order_result.data:
            raise HTTPException(status_code=404, detail="Заказ не найден")
        
        order = order_result.data[0]
        if order['status'] != 'accepted':
            raise HTTPException(
                status_code=400, 
                detail=f"Загрузка фото доступна только для принятых заказов. Текущий статус: {order['status']}"
            )
        
        # 2. Создаем директорию для заказа
        upload_dir = Path(f"static/uploads/pre-delivery/{order_id}")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # 3. Сохраняем файлы
        saved_photos = []
        for photo in photos:
            # Проверяем тип файла
            if not photo.content_type.startswith('image/'):
                raise HTTPException(status_code=400, detail=f"Файл {photo.filename} не является изображением")
            
            # Генерируем уникальное имя файла
            file_extension = photo.filename.split('.')[-1] if '.' in photo.filename else 'jpg'
            unique_filename = f"{uuid.uuid4().hex}.{file_extension}"
            file_path = upload_dir / unique_filename
            
            # Сохраняем файл
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(photo.file, buffer)
            
            # Добавляем информацию о фото
            saved_photos.append({
                "url": f"/static/uploads/pre-delivery/{order_id}/{unique_filename}",
                "filename": photo.filename,
                "uploaded_at": datetime.now().isoformat(),
                "uploaded_by": "CRM User",  # TODO: Добавить реальную авторизацию
                "type": "pre_delivery",
                "size": os.path.getsize(file_path)
            })
        
        # 4. Обновляем заказ в БД и меняем статус
        current_photos = order.get('pre_delivery_photos', [])
        all_photos = current_photos + saved_photos
        
        update_result = db.table('orders').update({
            'pre_delivery_photos': all_photos,
            'status': 'assembled',  # Автоматическая смена статуса!
            'updated_at': datetime.now().isoformat()
        }).eq('id', order_id).execute()
        
        logger.info(f"Pre-delivery photos uploaded for order {order_id}, status changed to 'assembled'")
        
        # 5. Синхронизация фотографий с Bitrix
        bitrix_order_id = order.get('bitrix_order_id')
        order_number = order.get('order_number')
        
        if bitrix_order_id and order_number:
            # Собираем пути к только что загруженным фотографиям
            photo_paths = [f"static/uploads/pre-delivery/{order_id}/{os.path.basename(photo['url'])}" for photo in saved_photos]
            
            # Запускаем синхронизацию асинхронно (не блокируем ответ пользователю)
            import asyncio
            asyncio.create_task(sync_photos_to_bitrix(
                order_id=order_id,
                order_number=order_number, 
                bitrix_order_id=bitrix_order_id,
                photo_paths=photo_paths
            ))
            logger.info(f"Started photo sync to Bitrix for order {bitrix_order_id}")
        else:
            logger.warning(f"Cannot sync photos: missing bitrix_order_id or order_number for order {order_id}")
        
        return {
            "message": f"Загружено {len(saved_photos)} фото. Статус заказа изменен на 'Собран'",
            "photos_uploaded": len(saved_photos),
            "status_changed_to": "assembled",
            "photos": saved_photos
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading pre-delivery photos for order {order_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки фото: {str(e)}")


@app.get("/api/orders/{order_id}/pre-delivery-photos")
async def get_pre_delivery_photos(
    order_id: str,
    db: Client = Depends(get_supabase)
):
    """Get pre-delivery photos for an order"""
    try:
        result = db.table('orders').select('pre_delivery_photos').eq('id', order_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Заказ не найден")
        
        photos = result.data[0].get('pre_delivery_photos', [])
        return {"photos": photos}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting pre-delivery photos for order {order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/orders/{order_id}/pre-delivery-photos/{photo_index}")
async def delete_pre_delivery_photo(
    order_id: str,
    photo_index: int,
    db: Client = Depends(get_supabase)
):
    """Delete a specific pre-delivery photo by index"""
    try:
        # Получаем заказ
        result = db.table('orders').select('pre_delivery_photos').eq('id', order_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Заказ не найден")
        
        photos = result.data[0].get('pre_delivery_photos', [])
        if photo_index >= len(photos) or photo_index < 0:
            raise HTTPException(status_code=404, detail="Фото не найдено")
        
        # Удаляем файл с диска
        photo_to_delete = photos[photo_index]
        file_path = Path(photo_to_delete['url'].lstrip('/'))
        if file_path.exists():
            file_path.unlink()
        
        # Удаляем из массива
        photos.pop(photo_index)
        
        # Обновляем в БД
        db.table('orders').update({
            'pre_delivery_photos': photos,
            'updated_at': datetime.now().isoformat()
        }).eq('id', order_id).execute()
        
        logger.info(f"Deleted pre-delivery photo {photo_index} from order {order_id}")
        return {"message": "Фото удалено", "remaining_photos": len(photos)}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting pre-delivery photo for order {order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== WEBHOOKS ====================

@app.post("/webhooks/bitrix/order")
async def webhook_bitrix_order(
    request: Request,
    db: Client = Depends(get_supabase)
):
    """
    Handle webhook from Bitrix for order creation/update
    """
    data = {}  # Initialize data variable
    try:
        # Get request body
        body = await request.json()
        
        # Validate token
        token = body.get('token')
        if token != app_config.WEBHOOK_TOKEN:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        event = body.get('event')
        data = body.get('data', {})
        
        logger.info(f"Received webhook: {event}, order ID: {data.get('ID')}")
        
        # Дополнительное логирование для отслеживания статусов
        if 'STATUS_ID' in data:
            logger.info(f"Order {data.get('ID')} status from Bitrix: {data.get('STATUS_ID')}")
        
        # Check for duplicate webhooks
        from webhook_deduplication import webhook_deduplicator
        from sync_guard import sync_guard
        order_id = str(data.get('ID'))
        
        if not webhook_deduplicator.should_process_webhook(event, order_id, data):
            logger.info(f"Skipping duplicate webhook for order {order_id}")
            return {"status": "success", "action": "skipped_duplicate", "order_id": order_id}
        
        # Pause sync-back for this order to prevent feedback loops
        sync_guard.pause_sync_back(order_id)
        
        # Import transformer here to avoid circular imports
        from core.transformer import OptimizedTransformer
        transformer = OptimizedTransformer()
        
        # Initialize supabase_order variable
        supabase_order = None
        
        if event == 'order.create':
            # Transform Bitrix order to Supabase format
            supabase_order = transformer.transform_bitrix_to_supabase(data)
            
            # Ensure we use the original Bitrix order number
            if supabase_order:
                bitrix_number = data.get('ACCOUNT_NUMBER') or data.get('ID')
                if bitrix_number:
                    supabase_order['order_number'] = str(bitrix_number)
                    supabase_order['bitrix_order_id'] = int(data.get('ID'))
                    logger.info(f"Using original Bitrix order number: {bitrix_number}")
        elif event in ['order.update', 'order.status.change', 'order.status_change', 'order.status_change_direct']:
            # Handle order updates and status changes
            logger.info(f"Processing order update/status change for order {data.get('ID')}")
            
            # Check if order exists in Supabase
            existing = db.table('orders').select('id, status').eq('bitrix_order_id', data['ID']).execute()
            
            if not existing.data:
                logger.warning(f"Order {data.get('ID')} not found in Supabase for update")
                logger.info(f"Attempting to create missing order {data.get('ID')} from update webhook")
                
                # Try to create the missing order using the update data
                supabase_order = transformer.transform_bitrix_to_supabase(data)
                if supabase_order:
                    # Use original Bitrix order number
                    bitrix_number = data.get('ACCOUNT_NUMBER') or data.get('ID')
                    if bitrix_number:
                        supabase_order['order_number'] = str(bitrix_number)
                        supabase_order['bitrix_order_id'] = int(data.get('ID'))
                        logger.info(f"Creating missing order with original number: {bitrix_number}")
                    
                    # Continue with order creation logic instead of returning
                else:
                    logger.error(f"Failed to transform missing order {data.get('ID')}")
                    return {"status": "error", "action": "order_transform_failed", "order_id": data.get('ID')}
            
            # Transform update data
            update_data = transformer.transform_bitrix_update(data)
            
            if update_data and existing.data:
                # Update existing order
                result = db.table('orders').update(update_data).eq('bitrix_order_id', data['ID']).execute()
                
                # Log status change if it occurred
                if 'status' in update_data:
                    old_status = existing.data[0].get('status')
                    new_status = update_data['status']
                    logger.info(f"Order {data.get('ID')} status changed: {old_status} → {new_status}")
                
                return {"status": "success", "action": "order_updated", "order_id": data.get('ID'), "changes": list(update_data.keys())}
            elif not existing.data and supabase_order:
                # Order doesn't exist, create it - don't return here, continue to creation logic
                logger.info(f"Creating missing order {data.get('ID')} that was updated via webhook")
            else:
                logger.info(f"No significant changes detected for order {data.get('ID')}")
                return {"status": "success", "action": "no_changes", "order_id": data.get('ID')}
        else:
            logger.warning(f"Unknown event type: {event}")
            return {"status": "success", "action": "unknown_event", "event": event}

        # Handle order creation - continue with existing logic
        if event == 'order.create':
            
            # Handle user creation/update if USER_ID and user data are provided
            if 'USER_ID' in data and data['USER_ID'] and 'user' in data:
                bitrix_user_id = data['USER_ID']
                user_data = data['user']
                
                # Check if user already exists
                user_result = db.table('users').select('id').eq('bitrix_user_id', int(bitrix_user_id)).execute()
                
                if user_result.data:
                    # Update existing user
                    user_update = transformer.transform_bitrix_user(user_data, bitrix_user_id)
                    del user_update['created_at']  # Don't update creation time
                    
                    db.table('users').update(user_update).eq('id', user_result.data[0]['id']).execute()
                    if supabase_order is not None:
                        supabase_order['user_id'] = user_result.data[0]['id']
                    logger.info(f"Updated user {user_result.data[0]['id']} for bitrix_user_id {bitrix_user_id}")
                else:
                    # Create new user
                    new_user = transformer.transform_bitrix_user(user_data, bitrix_user_id)
                    user_result = db.table('users').insert(new_user).execute()
                    
                    if user_result.data:
                        if supabase_order is not None:
                            supabase_order['user_id'] = user_result.data[0]['id']
                        logger.info(f"Created new user {user_result.data[0]['id']} for bitrix_user_id {bitrix_user_id}")
                    else:
                        logger.error(f"Failed to create user for bitrix_user_id {bitrix_user_id}")
            elif 'USER_ID' in data and data['USER_ID']:
                # Fallback: only lookup existing user without user data
                user_result = db.table('users').select('id').eq('bitrix_user_id', int(data['USER_ID'])).execute()
                if user_result.data:
                    if supabase_order is not None:
                        supabase_order['user_id'] = user_result.data[0]['id']
                    logger.info(f"Found user {user_result.data[0]['id']} for bitrix_user_id {data['USER_ID']}")
                else:
                    logger.warning(f"User not found for bitrix_user_id {data['USER_ID']} and no user data provided")
            
            # Check if we have a valid order to process
            if supabase_order is None:
                logger.error(f"Cannot process order {data.get('ID')}: supabase_order is None")
                return {"status": "error", "message": "Order data transformation failed", "order_id": data.get('ID')}
            
            # Check if order already exists by bitrix_order_id
            existing = db.table('orders').select('id').eq('bitrix_order_id', data['ID']).execute()
            
            if existing.data:
                # Update existing order
                result = db.table('orders').update(supabase_order).eq('bitrix_order_id', data['ID']).execute()
                action = 'update_existing'
            else:
                # Create new order
                result = db.table('orders').insert(supabase_order).execute()
                action = 'create_order'
            
            # Transform and save order items
            if 'basket' in data:
                # Transform each basket item
                items = []
                for bitrix_item in data['basket']:
                    item = transformer.transform_basket_item(bitrix_item)
                    items.append(item)
                # Delete old items if updating
                if existing.data:
                    db.table('order_items').delete().eq('order_id', existing.data[0]['id']).execute()
                
                # Insert new items
                for item in items:
                    if existing.data:
                        item['order_id'] = existing.data[0]['id']
                    else:
                        item['order_id'] = result.data[0]['id']
                    db.table('order_items').insert(item).execute()
            
            # ====== ОБРАТНАЯ СИНХРОНИЗАЦИЯ В BITRIX ======
            # Проверяем нужно ли выполнять обратную синхронизацию
            webhook_source = data.get('webhook_source', '')
            recipient_name = data.get('properties', {}).get('nameRecipient') or data.get('recipient_name', '')
            order_id = data.get('ID', '')
            
            # НЕ синхронизировать если:
            # 1. Заказ создан из production Bitrix
            # 2. Это тестовый заказ обратной синхронизации  
            # 3. ID заказа подозрительно высокий (timestamp-like)
            # 4. Синхронизация отключена
            should_skip_sync = (
                webhook_source.startswith('production_real') or
                'Получатель Обратной Синхронизации' in recipient_name or
                'reverse_sync' in recipient_name.lower() or
                int(str(order_id)[:10]) > 1756000000 or  # Timestamp больше чем Aug 2025
                not app_config.BITRIX_SYNC_ENABLED
            )
            
            if action == 'create_order' and not should_skip_sync:
                logger.info(f"🔄 Starting reverse sync for non-Bitrix order: {order_id}")
                
                # Получаем товары заказа для передачи в Bitrix
                order_items = []
                if 'basket' in data:
                    for bitrix_item in data['basket']:
                        item = transformer.transform_basket_item(bitrix_item)
                        order_items.append(item)
                
                # Создаем заказ в Bitrix
                bitrix_order_id = await create_order_in_bitrix(supabase_order, order_items)
                
                if bitrix_order_id:
                    # Получаем правильный ID заказа из Supabase
                    supabase_order_id = None
                    if existing.data:
                        supabase_order_id = existing.data[0]['id']
                    elif result.data:
                        supabase_order_id = result.data[0]['id']
                    
                    # Обновляем bitrix_order_id в Supabase заказе
                    try:
                        if supabase_order_id:
                            db.table('orders').update({
                                'bitrix_order_id': bitrix_order_id,
                                'updated_at': datetime.now().isoformat()
                            }).eq('id', supabase_order_id).execute()
                            
                            logger.info(f"✅ Reverse sync completed: Supabase Order {supabase_order_id} ↔ Bitrix Order {bitrix_order_id}")
                        else:
                            logger.error("❌ Failed to get Supabase order ID for bitrix_order_id update")
                    except Exception as e:
                        logger.error(f"❌ Failed to update bitrix_order_id in Supabase: {e}")
                else:
                    # Получаем правильный ID заказа для логирования
                    supabase_order_id = None
                    if existing.data:
                        supabase_order_id = existing.data[0]['id']
                    elif result.data:
                        supabase_order_id = result.data[0]['id']
                    
                    logger.warning(f"⚠️ Reverse sync failed for order {supabase_order_id}, but order created in Supabase")
            elif action == 'create_order' and should_skip_sync:
                logger.info(f"⏭️ Skipping reverse sync for order {order_id}: test/system order")
            else:
                logger.debug(f"⏩ Skipping reverse sync: webhook_source={webhook_source}, action={action}")
            
            # Отправляем Telegram уведомление (асинхронно) с rate limiting
            order_id = result.data[0]['id'] if result.data else None
            if order_id and webhook_deduplicator.should_send_notification(str(data.get('ID')), action):
                asyncio.create_task(send_order_telegram_notification(supabase_order, action))
            elif order_id:
                logger.info(f"Notification rate limited for order {data.get('ID')}")
            
            return {"status": "success", "action": action, "order_id": order_id}
            
        elif event == 'order.update':
            # Log production data for debugging
            logger.info(f"Production order.update data: {json.dumps(data, default=str, ensure_ascii=False)}")
            
            # Получаем текущие данные заказа перед обновлением (для отслеживания изменений)
            current_order = db.table('orders').select('status, recipient_phone, delivery_address').eq('bitrix_order_id', data['ID']).execute()
            previous_status = current_order.data[0]['status'] if current_order.data else None
            
            # Update existing order
            update_data = transformer.transform_bitrix_update(data)
            result = db.table('orders').update(update_data).eq('bitrix_order_id', data['ID']).execute()
            
            # Для уведомлений передаем полные данные с номером заказа
            order_id = None
            if result.data:
                notification_data = result.data[0].copy()
                notification_data['bitrix_order_id'] = data.get('ID')
                notification_data['order_number'] = data.get('ACCOUNT_NUMBER', data.get('ID'))
                
                # Добавляем информацию о предыдущем статусе
                notification_data['previous_status'] = previous_status
                notification_data['status_changed'] = previous_status != notification_data.get('status')
                
                # Добавляем исходные данные Bitrix для лучшего маппинга
                notification_data['bitrix_data'] = data
                
                # Отправляем Telegram уведомление с rate limiting
                order_id = result.data[0]['id']
                action = "status_change" if notification_data['status_changed'] else "update"
                if webhook_deduplicator.should_send_notification(str(data.get('ID')), action):
                    asyncio.create_task(send_order_telegram_notification(notification_data, action))
                else:
                    logger.info(f"Notification rate limited for order {data.get('ID')}")
            
            return {"status": "success", "action": "update", "order_id": order_id}
            
        elif event == 'order.status_change':
            # Специальная обработка для изменения статуса заказа
            logger.info(f"Processing status change for order {data.get('ID')}")
            
            # Получаем текущие данные заказа перед обновлением (для отслеживания изменений)
            current_order = db.table('orders').select('status, recipient_phone, delivery_address').eq('bitrix_order_id', data['ID']).execute()
            previous_status = current_order.data[0]['status'] if current_order.data else None
            
            # Обновляем статус заказа
            update_data = transformer.transform_bitrix_update(data)
            result = db.table('orders').update(update_data).eq('bitrix_order_id', data['ID']).execute()
            
            # Для уведомлений передаем полные данные с номером заказа
            order_id = None
            if result.data:
                notification_data = result.data[0].copy()
                notification_data['bitrix_order_id'] = data.get('ID')
                notification_data['order_number'] = data.get('ACCOUNT_NUMBER', data.get('ID'))
                
                # Добавляем информацию о предыдущем статусе
                notification_data['previous_status'] = previous_status
                notification_data['status_changed'] = previous_status != notification_data.get('status')
                
                # Добавляем исходные данные Bitrix для лучшего маппинга
                notification_data['bitrix_data'] = data
                
                # Отправляем уведомление для изменения статуса с rate limiting
                order_id = result.data[0]['id']
                if webhook_deduplicator.should_send_notification(str(data.get('ID')), "status_change"):
                    asyncio.create_task(send_order_telegram_notification(notification_data, "status_change"))
                else:
                    logger.info(f"Status change notification rate limited for order {data.get('ID')}")
                
                logger.info(f"Status change notification sent for order {data.get('ID')}: {previous_status} -> {notification_data.get('status')}")
            
            return {"status": "success", "action": "status_change", "order_id": order_id}
            
        else:
            raise HTTPException(status_code=400, detail=f"Unknown event: {event}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook error for order {data.get('ID', 'unknown')}: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== INVENTORY API ENDPOINTS ====================

@app.post("/api/inventory/update")
async def update_product_quantity(
    product_data: dict,
    db: Client = Depends(get_supabase)
):
    """Update quantity for a single product"""
    try:
        product_id = product_data.get('product_id')
        new_quantity = product_data.get('quantity')
        reason = product_data.get('reason', 'Manual update')
        
        if not product_id or new_quantity is None:
            raise HTTPException(status_code=400, detail="product_id and quantity are required")
        
        # Get current quantity for history
        current_product = db.table('products').select('quantity, name').eq('id', product_id).single().execute()
        if not current_product.data:
            raise HTTPException(status_code=404, detail="Product not found")
        
        old_quantity = current_product.data.get('quantity', 0)
        
        # Update product quantity
        result = db.table('products').update({
            'quantity': new_quantity,
            'updated_at': datetime.utcnow().isoformat()
        }).eq('id', product_id).execute()
        
        if result.data:
            logger.info(f"Updated product {product_id} quantity: {old_quantity} -> {new_quantity}")
            return {
                "success": True,
                "product_id": product_id,
                "old_quantity": old_quantity,
                "new_quantity": new_quantity,
                "change": new_quantity - old_quantity
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to update product quantity")
            
    except Exception as e:
        logger.error(f"Inventory update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/inventory/bulk-update")
async def bulk_update_quantities(
    update_data: dict,
    db: Client = Depends(get_supabase)
):
    """Bulk update quantities for multiple products"""
    try:
        updates = update_data.get('updates', [])  # List of {product_id, quantity, reason}
        
        if not updates:
            raise HTTPException(status_code=400, detail="No updates provided")
        
        updated_products = []
        errors = []
        
        for update in updates:
            try:
                product_id = update.get('product_id')
                new_quantity = update.get('quantity')
                
                if not product_id or new_quantity is None:
                    errors.append(f"Missing product_id or quantity in update: {update}")
                    continue
                
                # Update individual product
                result = db.table('products').update({
                    'quantity': new_quantity,
                    'updated_at': datetime.utcnow().isoformat()
                }).eq('id', product_id).execute()
                
                if result.data:
                    updated_products.append({
                        "product_id": product_id,
                        "new_quantity": new_quantity
                    })
                else:
                    errors.append(f"Failed to update product {product_id}")
                    
            except Exception as e:
                errors.append(f"Error updating product {update.get('product_id', 'unknown')}: {str(e)}")
        
        return {
            "success": len(updated_products) > 0,
            "updated_count": len(updated_products),
            "updated_products": updated_products,
            "errors": errors
        }
        
    except Exception as e:
        logger.error(f"Bulk inventory update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/inventory/low-stock")
async def get_low_stock_products(
    threshold: int = 5,
    db: Client = Depends(get_supabase)
):
    """Get products with low stock (quantity <= threshold)"""
    try:
        result = db.table('products')\
            .select('id, name, quantity, price')\
            .lte('quantity', threshold)\
            .gt('quantity', 0)\
            .eq('is_active', True)\
            .order('quantity')\
            .execute()
        
        return {
            "success": True,
            "threshold": threshold,
            "count": len(result.data) if result.data else 0,
            "products": result.data or []
        }
        
    except Exception as e:
        logger.error(f"Low stock query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/inventory/delivery")
async def add_delivery(
    delivery_data: dict,
    db: Client = Depends(get_supabase)
):
    """Add delivery of products to warehouse"""
    try:
        product_id = delivery_data.get('product_id')
        quantity = int(delivery_data.get('quantity', 0))
        delivery_date = delivery_data.get('delivery_date')  # Format: "22 августа"
        note = delivery_data.get('note', '')
        
        if not product_id or quantity <= 0:
            raise HTTPException(status_code=400, detail="Invalid product_id or quantity")
        
        # Get current product
        product_result = db.table('products')\
            .select('id, name, quantity')\
            .eq('id', product_id)\
            .single()\
            .execute()
            
        if not product_result.data:
            raise HTTPException(status_code=404, detail="Product not found")
            
        product = product_result.data
        new_quantity = (product.get('quantity') or 0) + quantity
        
        # Update product quantity
        db.table('products')\
            .update({
                'quantity': new_quantity,
                'updated_at': datetime.utcnow().isoformat()
            })\
            .eq('id', product_id)\
            .execute()
        
        # Record delivery history  
        delivery_record = {
            'product_id': product_id,
            'quantity': quantity,
            'delivery_date': delivery_date,
            'reason': 'delivery',
            'note': note,
            'created_at': datetime.utcnow().isoformat()
        }
        
        # Create deliveries table entry
        db.table('inventory_movements')\
            .insert(delivery_record)\
            .execute()
        
        logger.info(f"Delivery added: {product['name']} +{quantity} = {new_quantity}")
        
        return {
            'success': True,
            'message': f"Поставка добавлена: {product['name']} +{quantity}",
            'product': {
                'id': product_id,
                'name': product['name'],
                'old_quantity': product.get('quantity', 0),
                'new_quantity': new_quantity,
                'delivery_date': delivery_date
            }
        }
        
    except Exception as e:
        logger.error(f"Add delivery error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/inventory/writeoff")
async def writeoff_product(
    writeoff_data: dict,
    db: Client = Depends(get_supabase)
):
    """Write off products from warehouse"""
    try:
        product_id = writeoff_data.get('product_id')
        quantity = int(writeoff_data.get('quantity', 0))
        writeoff_date = writeoff_data.get('writeoff_date')  # Format: "22 августа"
        reason = writeoff_data.get('reason', 'Списание')
        note = writeoff_data.get('note', '')
        
        if not product_id or quantity <= 0:
            raise HTTPException(status_code=400, detail="Invalid product_id or quantity")
        
        # Get current product
        product_result = db.table('products')\
            .select('id, name, quantity')\
            .eq('id', product_id)\
            .single()\
            .execute()
            
        if not product_result.data:
            raise HTTPException(status_code=404, detail="Product not found")
            
        product = product_result.data
        current_quantity = product.get('quantity', 0)
        
        if current_quantity < quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient quantity. Available: {current_quantity}")
        
        new_quantity = current_quantity - quantity
        
        # Update product quantity
        db.table('products')\
            .update({
                'quantity': new_quantity,
                'updated_at': datetime.utcnow().isoformat()
            })\
            .eq('id', product_id)\
            .execute()
        
        # Record writeoff history  
        writeoff_record = {
            'product_id': product_id,
            'quantity': -quantity,  # Negative for writeoff
            'delivery_date': writeoff_date,
            'reason': 'writeoff',
            'note': f"{reason}: {note}",
            'created_at': datetime.utcnow().isoformat()
        }
        
        # Create inventory movement entry
        db.table('inventory_movements')\
            .insert(writeoff_record)\
            .execute()
        
        logger.info(f"Writeoff recorded: {product['name']} -{quantity} = {new_quantity}")
        
        return {
            'success': True,
            'message': f"Списание выполнено: {product['name']} -{quantity}",
            'product': {
                'id': product_id,
                'name': product['name'],
                'old_quantity': current_quantity,
                'new_quantity': new_quantity,
                'writeoff_date': writeoff_date
            }
        }
        
    except Exception as e:
        logger.error(f"Writeoff error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/inventory/history")
async def get_inventory_history(
    flower_id: Optional[str] = None,
    limit: int = 50,
    db: Client = Depends(get_supabase)
):
    """Get flower inventory movement history"""
    try:
        query = db.table('flower_inventory_movements')\
            .select('*, flowers(name)')\
            .order('created_at', desc=True)\
            .limit(limit)
            
        if flower_id:
            query = query.eq('flower_id', flower_id)
            
        result = query.execute()
        
        movements = []
        for movement in result.data or []:
            # Handle quantity sign based on movement type
            quantity = movement.get('quantity', 0)
            movement_type = movement.get('movement_type', '')
            
            # For writeoffs, make quantity negative for display
            if movement_type == 'writeoff':
                quantity = -abs(quantity)
            
            movements.append({
                'id': movement.get('id'),
                'flower_id': movement.get('flower_id'),
                'product_name': movement.get('flowers', {}).get('name', 'Unknown Flower'),
                'quantity': quantity,
                'delivery_date': movement.get('delivery_date'),
                'reason': movement.get('movement_type', 'unknown'),
                'note': movement.get('note'),
                'created_at': movement.get('created_at')
            })
        
        return {
            'success': True,
            'movements': movements,
            'count': len(movements)
        }
        
    except Exception as e:
        logger.error(f"Get flower inventory history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== FLOWER API ENDPOINTS ====================

@app.get("/api/flowers/search")
async def search_flowers(
    q: str = "",
    limit: int = 50,
    db: Client = Depends(get_supabase)
):
    """Search flowers by name"""
    try:
        query = db.table('flowers').select('id, name, quantity, name_en').eq('is_active', True)
        
        # Add search filter if query provided
        if q.strip():
            query = query.ilike('name', f'%{q}%')
            
        result = query.limit(limit).execute()
        return result.data or []
        
    except Exception as e:
        logger.error(f"Search flowers error: {e}")
        return []

@app.post("/api/flowers/update-quantity")
async def update_flower_quantity(
    request_data: dict,
    db: Client = Depends(get_supabase)
):
    """Update flower quantity"""
    try:
        flower_id = request_data.get('flower_id')
        quantity = request_data.get('quantity')
        reason = request_data.get('reason', 'Manual update')
        
        if not flower_id or quantity is None:
            raise HTTPException(status_code=400, detail="flower_id and quantity are required")
        
        # Update flower quantity
        result = db.table('flowers')\
            .update({'quantity': quantity, 'updated_at': 'now()'})\
            .eq('id', flower_id)\
            .execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Flower not found")
        
        # TODO: Add to flower_movements table when created
        
        return {
            'success': True,
            'message': 'Flower quantity updated successfully',
            'flower_id': flower_id,
            'new_quantity': quantity
        }
        
    except Exception as e:
        logger.error(f"Update flower quantity error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/flowers/delivery")
async def add_flower_delivery(
    delivery_data: dict,
    db: Client = Depends(get_supabase)
):
    """Add flower delivery (increase stock)"""
    try:
        flower_id = delivery_data.get('flower_id')
        quantity = delivery_data.get('quantity')
        note = delivery_data.get('note', '')
        
        if not flower_id or not quantity or quantity <= 0:
            raise HTTPException(status_code=400, detail="flower_id and positive quantity are required")
        
        # Get current quantity
        current_result = db.table('flowers')\
            .select('quantity')\
            .eq('id', flower_id)\
            .single()\
            .execute()
        
        if not current_result.data:
            raise HTTPException(status_code=404, detail="Flower not found")
        
        current_quantity = current_result.data.get('quantity', 0)
        new_quantity = current_quantity + quantity
        
        # Update flower quantity
        update_result = db.table('flowers')\
            .update({'quantity': new_quantity, 'updated_at': 'now()'})\
            .eq('id', flower_id)\
            .execute()
        
        # Add delivery record to flower_inventory_movements
        movement_result = db.table('flower_inventory_movements').insert({
            'flower_id': flower_id,
            'movement_type': 'delivery',
            'quantity': quantity,
            'reason': delivery_data.get('reason', 'Flower delivery'),
            'note': note,
            'delivery_date': delivery_data.get('delivery_date'),
            'created_by': 'CRM System'
        }).execute()
        
        return {
            'success': True,
            'message': f'Added {quantity} flowers to inventory',
            'flower_id': flower_id,
            'previous_quantity': current_quantity,
            'added_quantity': quantity,
            'new_quantity': new_quantity
        }
        
    except Exception as e:
        logger.error(f"Add flower delivery error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/flowers/writeoff")
async def writeoff_flowers(
    writeoff_data: dict,
    db: Client = Depends(get_supabase)
):
    """Write off flowers (decrease stock)"""
    try:
        flower_id = writeoff_data.get('flower_id')
        quantity = writeoff_data.get('quantity')
        reason = writeoff_data.get('reason', 'Manual writeoff')
        note = writeoff_data.get('note', '')
        
        if not flower_id or not quantity or quantity <= 0:
            raise HTTPException(status_code=400, detail="flower_id and positive quantity are required")
        
        # Get current quantity
        current_result = db.table('flowers')\
            .select('quantity')\
            .eq('id', flower_id)\
            .single()\
            .execute()
        
        if not current_result.data:
            raise HTTPException(status_code=404, detail="Flower not found")
        
        current_quantity = current_result.data.get('quantity', 0)
        
        if current_quantity < quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient stock. Available: {current_quantity}")
        
        new_quantity = current_quantity - quantity
        
        # Update flower quantity
        update_result = db.table('flowers')\
            .update({'quantity': new_quantity, 'updated_at': 'now()'})\
            .eq('id', flower_id)\
            .execute()
        
        # Add writeoff record to flower_inventory_movements
        movement_result = db.table('flower_inventory_movements').insert({
            'flower_id': flower_id,
            'movement_type': 'writeoff',
            'quantity': quantity,
            'reason': reason,
            'note': note,
            'created_by': 'CRM System'
        }).execute()
        
        return {
            'success': True,
            'message': f'Wrote off {quantity} flowers',
            'flower_id': flower_id,
            'previous_quantity': current_quantity,
            'writeoff_quantity': quantity,
            'new_quantity': new_quantity,
            'reason': reason
        }
        
    except Exception as e:
        logger.error(f"Writeoff flowers error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/webhook-stats")
async def get_webhook_stats():
    """Get webhook deduplication and sync guard statistics"""
    try:
        from webhook_deduplication import webhook_deduplicator
        from sync_guard import sync_guard
        
        return {
            "deduplication": webhook_deduplicator.get_cache_stats(),
            "sync_guard": sync_guard.get_stats(),
            "status": "active"
        }
    except Exception as e:
        logger.error(f"Error getting webhook stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== MODULAR WEBHOOK HANDLERS ====================

@app.post("/webhooks/bitrix/product")
async def webhook_bitrix_product(
    request: Request,
    db: Client = Depends(get_supabase)
):
    """
    Handle webhook from Bitrix for product creation/update/deletion
    Uses modular webhooks.products module for cleaner architecture
    """
    from webhooks.products import handle_product_webhook
    return await handle_product_webhook(request, db)

@app.post("/webhooks/bitrix/shop")
async def webhook_bitrix_shop(
    request: Request,
    db: Client = Depends(get_supabase)
):
    """
    Handle webhook from Bitrix for shop creation/update/status changes
    Automatically updates product statuses when shop status changes
    """
    from webhooks.shops import handle_shop_webhook
    return await handle_shop_webhook(request, db)

@app.post("/webhooks/bitrix/florist")
async def webhook_bitrix_florist(
    request: Request,
    db: Client = Depends(get_supabase)
):
    """
    Handle webhook from Bitrix for florist activation/deactivation/shop assignment
    Automatically updates product statuses when florist status changes
    """
    from webhooks.florists import handle_florist_webhook
    return await handle_florist_webhook(request, db)

# ==================== MODULAR WEBHOOK API ENDPOINTS ====================

@app.post("/api/sync/products/status")
async def sync_products_status(db: Client = Depends(get_supabase)):
    """Синхронизирует статусы всех товаров согласно 4 критериям активности"""
    from webhooks.products import sync_all_product_statuses
    
    try:
        stats = await sync_all_product_statuses(db)
        return {
            "status": "success",
            "message": "Product status synchronization completed",
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Error in product status sync: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sync/shops")
async def sync_shops_from_bitrix(db: Client = Depends(get_supabase)):
    """Синхронизирует магазины из Bitrix в Supabase"""
    from webhooks.shops import update_shop_product_counts
    
    try:
        await update_shop_product_counts(db)
        return {
            "status": "success",
            "message": "Shop synchronization completed"
        }
    except Exception as e:
        logger.error(f"Error in shop sync: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/florists/stats")
async def get_florists_stats():
    """Получает статистику по флористам"""
    from webhooks.florists import get_florist_statistics
    
    try:
        stats = await get_florist_statistics()
        return {
            "status": "success",
            "data": stats
        }
    except Exception as e:
        logger.error(f"Error getting florist stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# ==================== TELEGRAM NOTIFICATION HELPERS ====================

async def send_order_telegram_notification(order_data: dict, action: str):
    """Отправить Telegram уведомление о заказе"""
    try:
        from telegram_notifier import send_order_notification
        await send_order_notification(order_data, action)
    except Exception as e:
        logger.error(f"Failed to send order telegram notification: {e}")

async def send_product_telegram_notification(product_data: dict, action: str):
    """Отправить Telegram уведомление о товаре"""
    try:
        from telegram_notifier import send_product_notification
        await send_product_notification(product_data, action)
    except Exception as e:
        logger.error(f"Failed to send product telegram notification: {e}")

async def send_error_telegram_notification(error_type: str, error_data: dict):
    """Отправить Telegram уведомление об ошибке"""
    try:
        from telegram_notifier import send_error_notification
        await send_error_notification(error_type, error_data)
    except Exception as e:
        logger.error(f"Failed to send error telegram notification: {e}")

# ==================== CACHE MONITORING ====================

@app.get("/cache/stats")
async def cache_stats():
    """Cache statistics endpoint for monitoring performance"""
    from cache_utils import simple_cache
    return {
        "cache_stats": simple_cache.stats(),
        "timestamp": datetime.now().isoformat()
    }

@app.post("/cache/clear")
async def clear_cache():
    """Clear all cache (for debugging)"""
    from cache_utils import simple_cache
    simple_cache.clear()
    return {
        "message": "Cache cleared",
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host=app_config.HOST,
        port=app_config.PORT,
        reload=app_config.DEBUG
    )