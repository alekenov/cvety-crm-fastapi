<?php
/**
 * Production Webhook Integration для Bitrix CMS
 * 
 * ИНСТРУКЦИЯ ПО УСТАНОВКЕ:
 * 1. Скопировать этот код в /home/bitrix/www/bitrix/php_interface/init.php (в конец файла)
 * 2. Заменить URL и токен на production значения
 * 3. Протестировать создание заказа в Bitrix
 */

// Production настройки webhook
define('PYTHON_CRM_WEBHOOK_URL', 'https://your-python-crm-domain.com/webhooks/bitrix/order');
define('PYTHON_CRM_WEBHOOK_TOKEN', 'production-secure-token-2025');

// Логирование webhook событий
define('WEBHOOK_LOG_FILE', '/tmp/bitrix_webhook.log');

/**
 * Логирование webhook событий
 */
function logWebhookEvent($message, $level = 'INFO') {
    $timestamp = date('Y-m-d H:i:s');
    $logMessage = "[$timestamp] [$level] $message\n";
    file_put_contents(WEBHOOK_LOG_FILE, $logMessage, FILE_APPEND | LOCK_EX);
}

/**
 * Отправка webhook в Python CRM с retry механизмом
 */
function sendOrderWebhookToPythonCRM($orderId, $event = 'order.create', $maxRetries = 3) {
    $retryCount = 0;
    
    while ($retryCount < $maxRetries) {
        try {
            logWebhookEvent("Отправка webhook для заказа $orderId, попытка " . ($retryCount + 1));
            
            // Получаем полные данные заказа
            $orderData = getFullOrderData($orderId);
            if (!$orderData) {
                logWebhookEvent("Заказ $orderId не найден", 'ERROR');
                return false;
            }
            
            // Формируем payload
            $payload = [
                'event' => $event,
                'token' => PYTHON_CRM_WEBHOOK_TOKEN,
                'data' => $orderData
            ];
            
            // Отправляем HTTP POST запрос с таймаутом
            $context = stream_context_create([
                'http' => [
                    'method' => 'POST',
                    'header' => [
                        'Content-Type: application/json',
                        'User-Agent: Bitrix-Webhook/1.0'
                    ],
                    'content' => json_encode($payload),
                    'timeout' => 15, // Увеличенный таймаут для production
                    'ignore_errors' => true
                ]
            ]);
            
            $response = file_get_contents(PYTHON_CRM_WEBHOOK_URL, false, $context);
            $httpCode = 0;
            
            // Получаем HTTP код ответа
            if (isset($http_response_header[0])) {
                preg_match('/HTTP\/\d\.\d\s+(\d+)/', $http_response_header[0], $matches);
                $httpCode = isset($matches[1]) ? intval($matches[1]) : 0;
            }
            
            if ($response !== false && $httpCode >= 200 && $httpCode < 300) {
                $responseData = json_decode($response, true);
                
                if ($responseData && isset($responseData['status']) && $responseData['status'] === 'success') {
                    logWebhookEvent("Webhook успешно отправлен для заказа $orderId");
                    
                    // Сохраняем информацию о синхронизации в свойствах заказа
                    if (isset($responseData['order_id'])) {
                        saveSyncInfo($orderId, $responseData['order_id']);
                    }
                    
                    return true;
                } else {
                    throw new Exception('Python CRM вернул ошибку: ' . $response);
                }
            } else {
                throw new Exception("HTTP ошибка $httpCode: $response");
            }
            
        } catch (Exception $e) {
            $retryCount++;
            logWebhookEvent("Ошибка отправки webhook для заказа $orderId (попытка $retryCount): " . $e->getMessage(), 'ERROR');
            
            if ($retryCount >= $maxRetries) {
                // После всех неудачных попыток - сохраняем в очередь для повторной отправки
                saveFailedWebhook($orderId, $event, $e->getMessage());
                return false;
            }
            
            // Ждем перед следующей попыткой
            sleep(min($retryCount * 2, 10)); // Exponential backoff до 10 секунд
        }
    }
    
    return false;
}

/**
 * Получение полных данных заказа
 */
function getFullOrderData($orderId) {
    try {
        // Основные данные заказа
        $order = CSaleOrder::GetByID($orderId);
        if (!$order) {
            return null;
        }
        
        // Получаем корзину заказа
        $basket = [];
        $basketDb = CSaleBasket::GetList(
            [],
            ["ORDER_ID" => $orderId],
            false,
            false,
            ["ID", "PRODUCT_ID", "NAME", "PRICE", "CURRENCY", "QUANTITY", "DISCOUNT_PRICE", "PRODUCT_XML_ID"]
        );
        while ($basketItem = $basketDb->Fetch()) {
            $basket[] = $basketItem;
        }
        
        // Получаем свойства заказа
        $properties = [];
        $propsDb = CSaleOrderPropsValue::GetList(
            [],
            ["ORDER_ID" => $orderId],
            false,
            false,
            ["ID", "ORDER_PROPS_ID", "NAME", "VALUE", "CODE"]
        );
        while ($prop = $propsDb->Fetch()) {
            if ($prop['CODE']) {
                $properties[$prop['CODE']] = $prop['VALUE'];
            } else {
                $properties[$prop['NAME']] = $prop['VALUE'];
            }
        }
        
        // Получаем данные пользователя
        $user = null;
        if ($order['USER_ID']) {
            $userDb = CUser::GetList(
                "id", "asc",
                ["ID" => $order['USER_ID']],
                ["SELECT" => ["ID", "LOGIN", "EMAIL", "NAME", "LAST_NAME", "PERSONAL_PHONE"]]
            );
            if ($userFetch = $userDb->Fetch()) {
                $user = $userFetch;
            }
        }
        
        // Собираем все данные
        $fullOrderData = array_merge($order, [
            'basket' => $basket,
            'properties' => $properties,
            'user' => $user,
            'webhook_timestamp' => time(),
            'webhook_source' => 'production_bitrix'
        ]);
        
        return $fullOrderData;
        
    } catch (Exception $e) {
        logWebhookEvent("Ошибка получения данных заказа $orderId: " . $e->getMessage(), 'ERROR');
        return null;
    }
}

/**
 * Сохранение информации о синхронизации
 */
function saveSyncInfo($bitrixOrderId, $pythonOrderId) {
    try {
        // Можно добавить в custom таблицу или в свойства заказа
        // Пока просто логируем
        logWebhookEvent("Заказ $bitrixOrderId синхронизирован с Python CRM: $pythonOrderId");
    } catch (Exception $e) {
        logWebhookEvent("Ошибка сохранения sync info: " . $e->getMessage(), 'ERROR');
    }
}

/**
 * Сохранение неудачных webhook в очередь
 */
function saveFailedWebhook($orderId, $event, $error) {
    $failedWebhook = [
        'order_id' => $orderId,
        'event' => $event,
        'error' => $error,
        'timestamp' => time(),
        'retry_count' => 0
    ];
    
    // Сохраняем в файл для последующей обработки
    $failedFile = '/tmp/failed_webhooks.json';
    $failedWebhooks = [];
    
    if (file_exists($failedFile)) {
        $content = file_get_contents($failedFile);
        $failedWebhooks = json_decode($content, true) ?: [];
    }
    
    $failedWebhooks[] = $failedWebhook;
    file_put_contents($failedFile, json_encode($failedWebhooks), LOCK_EX);
    
    logWebhookEvent("Webhook для заказа $orderId добавлен в очередь повторной отправки", 'WARNING');
}

/**
 * Event handler для создания/обновления заказа
 */
function OnSaleOrderSavedHandler(&$ID, $arFields, $orderID, $isNew) {
    // Проверяем, нужно ли отправлять webhook
    if (!defined('PYTHON_CRM_WEBHOOK_URL') || empty(PYTHON_CRM_WEBHOOK_URL)) {
        return;
    }
    
    $event = $isNew ? 'order.create' : 'order.update';
    
    logWebhookEvent("Обработка события $event для заказа $ID");
    
    // Отправляем webhook асинхронно
    if (function_exists('fastcgi_finish_request')) {
        fastcgi_finish_request();
    }
    
    sendOrderWebhookToPythonCRM($ID, $event);
}

/**
 * Event handler для изменения статуса заказа
 */
function OnSaleStatusOrderHandler($ID, $statusID) {
    if (!defined('PYTHON_CRM_WEBHOOK_URL') || empty(PYTHON_CRM_WEBHOOK_URL)) {
        return;
    }
    
    logWebhookEvent("Обработка изменения статуса заказа $ID на $statusID");
    
    // Отправляем webhook для изменения статуса
    sendOrderWebhookToPythonCRM($ID, 'order.status_change');
}

/**
 * Получение полных данных товара
 */
function getFullProductData($productId) {
    try {
        // Подключаем модуль инфоблоков
        if (!CModule::IncludeModule("iblock")) {
            logWebhookEvent("Модуль iblock не подключен", 'ERROR');
            return null;
        }
        
        // Основные данные товара
        $product = CIBlockElement::GetByID($productId)->GetNext();
        if (!$product) {
            return null;
        }
        
        // Получаем свойства товара
        $properties = [];
        $propsDb = CIBlockElement::GetProperty(
            $product['IBLOCK_ID'], 
            $productId, 
            "sort", 
            "asc"
        );
        while ($prop = $propsDb->Fetch()) {
            if ($prop['CODE']) {
                $properties[$prop['CODE']] = $prop['VALUE'];
            } else {
                $properties[$prop['NAME']] = $prop['VALUE'];
            }
        }
        
        // Получаем цены товара
        $prices = [];
        if (CModule::IncludeModule("catalog")) {
            $priceDb = CPrice::GetList(
                [],
                ["PRODUCT_ID" => $productId]
            );
            while ($price = $priceDb->Fetch()) {
                $prices[] = $price;
            }
        }
        
        // Собираем все данные
        $fullProductData = array_merge($product, [
            'PROPERTIES' => $properties,
            'PRICES' => $prices,
            'webhook_timestamp' => date('Y-m-d\TH:i:s'),
            'webhook_source' => 'production_bitrix'
        ]);
        
        return $fullProductData;
        
    } catch (Exception $e) {
        logWebhookEvent("Ошибка получения данных товара $productId: " . $e->getMessage(), 'ERROR');
        return null;
    }
}

/**
 * Отправка webhook для товара в Python CRM
 */
function sendProductWebhookToPythonCRM($productId, $event = 'product.create', $maxRetries = 3) {
    $retryCount = 0;
    
    while ($retryCount < $maxRetries) {
        try {
            logWebhookEvent("Отправка product webhook для товара $productId, попытка " . ($retryCount + 1));
            
            // Получаем полные данные товара
            $productData = getFullProductData($productId);
            if (!$productData) {
                logWebhookEvent("Товар $productId не найден", 'ERROR');
                return false;
            }
            
            // Формируем payload
            $payload = [
                'event' => $event,
                'token' => PYTHON_CRM_WEBHOOK_TOKEN,
                'data' => $productData
            ];
            
            // Отправляем HTTP POST запрос
            $context = stream_context_create([
                'http' => [
                    'method' => 'POST',
                    'header' => [
                        'Content-Type: application/json',
                        'User-Agent: Bitrix-Product-Webhook/1.0'
                    ],
                    'content' => json_encode($payload),
                    'timeout' => 15,
                    'ignore_errors' => true
                ]
            ]);
            
            $productWebhookUrl = str_replace('/webhooks/bitrix/order', '/webhooks/bitrix/product', PYTHON_CRM_WEBHOOK_URL);
            $response = file_get_contents($productWebhookUrl, false, $context);
            $httpCode = 0;
            
            // Получаем HTTP код ответа
            if (isset($http_response_header[0])) {
                preg_match('/HTTP\/\d\.\d\s+(\d+)/', $http_response_header[0], $matches);
                $httpCode = isset($matches[1]) ? intval($matches[1]) : 0;
            }
            
            if ($response !== false && $httpCode >= 200 && $httpCode < 300) {
                $responseData = json_decode($response, true);
                
                if ($responseData && isset($responseData['status']) && $responseData['status'] === 'success') {
                    logWebhookEvent("Product webhook успешно отправлен для товара $productId");
                    return true;
                } else {
                    throw new Exception('Python CRM вернул ошибку: ' . $response);
                }
            } else {
                throw new Exception("HTTP ошибка $httpCode: $response");
            }
            
        } catch (Exception $e) {
            $retryCount++;
            logWebhookEvent("Ошибка отправки product webhook для товара $productId (попытка $retryCount): " . $e->getMessage(), 'ERROR');
            
            if ($retryCount >= $maxRetries) {
                return false;
            }
            
            sleep(min($retryCount * 2, 10));
        }
    }
    
    return false;
}

/**
 * Event handler для добавления товара
 */
function OnAfterIBlockElementAddHandler(&$arFields) {
    if (!defined('PYTHON_CRM_WEBHOOK_URL') || empty(PYTHON_CRM_WEBHOOK_URL)) {
        return;
    }
    
    // Проверяем, что это товар из каталога (IBLOCK_ID = 2 обычно каталог)
    $catalogIBlocks = [2, 27]; // Основной каталог и торговые предложения
    if (!in_array($arFields['IBLOCK_ID'], $catalogIBlocks)) {
        return;
    }
    
    $productId = $arFields['ID'];
    logWebhookEvent("Обработка добавления товара $productId");
    
    // Отправляем webhook асинхронно
    if (function_exists('fastcgi_finish_request')) {
        fastcgi_finish_request();
    }
    
    sendProductWebhookToPythonCRM($productId, 'product.create');
}

/**
 * Event handler для обновления товара
 */
function OnAfterIBlockElementUpdateHandler(&$arFields) {
    if (!defined('PYTHON_CRM_WEBHOOK_URL') || empty(PYTHON_CRM_WEBHOOK_URL)) {
        return;
    }
    
    // Проверяем, что это товар из каталога
    $catalogIBlocks = [2, 27];
    if (!in_array($arFields['IBLOCK_ID'], $catalogIBlocks)) {
        return;
    }
    
    $productId = $arFields['ID'];
    logWebhookEvent("Обработка обновления товара $productId");
    
    // Отправляем webhook асинхронно
    if (function_exists('fastcgi_finish_request')) {
        fastcgi_finish_request();
    }
    
    sendProductWebhookToPythonCRM($productId, 'product.update');
}

/**
 * Event handler для удаления товара
 */
function OnBeforeIBlockElementDeleteHandler($arFields) {
    if (!defined('PYTHON_CRM_WEBHOOK_URL') || empty(PYTHON_CRM_WEBHOOK_URL)) {
        return;
    }
    
    // Проверяем, что это товар из каталога
    $catalogIBlocks = [2, 27];
    if (!in_array($arFields['IBLOCK_ID'], $catalogIBlocks)) {
        return;
    }
    
    $productId = $arFields['ID'];
    logWebhookEvent("Обработка удаления товара $productId");
    
    // Отправляем webhook для деактивации
    sendProductWebhookToPythonCRM($productId, 'product.delete');
}

// Регистрируем обработчики событий
AddEventHandler("sale", "OnSaleOrderSaved", "OnSaleOrderSavedHandler");
AddEventHandler("sale", "OnSaleStatusOrder", "OnSaleStatusOrderHandler");

// Регистрируем обработчики событий товаров
AddEventHandler("iblock", "OnAfterIBlockElementAdd", "OnAfterIBlockElementAddHandler");
AddEventHandler("iblock", "OnAfterIBlockElementUpdate", "OnAfterIBlockElementUpdateHandler");
AddEventHandler("iblock", "OnBeforeIBlockElementDelete", "OnBeforeIBlockElementDeleteHandler");

/**
 * Функция для обработки очереди неудачных webhook
 * Можно запускать по cron каждые 5 минут
 */
function processFailedWebhooks() {
    $failedFile = '/tmp/failed_webhooks.json';
    
    if (!file_exists($failedFile)) {
        return;
    }
    
    $content = file_get_contents($failedFile);
    $failedWebhooks = json_decode($content, true) ?: [];
    
    if (empty($failedWebhooks)) {
        return;
    }
    
    $remainingWebhooks = [];
    $processedCount = 0;
    
    foreach ($failedWebhooks as $webhook) {
        // Пропускаем, если слишком много попыток
        if ($webhook['retry_count'] >= 10) {
            logWebhookEvent("Webhook для заказа {$webhook['order_id']} отклонен после 10 попыток", 'ERROR');
            continue;
        }
        
        // Пропускаем, если еще рано повторять (exponential backoff)
        $nextRetryTime = $webhook['timestamp'] + (pow(2, $webhook['retry_count']) * 60);
        if (time() < $nextRetryTime) {
            $remainingWebhooks[] = $webhook;
            continue;
        }
        
        logWebhookEvent("Повторная отправка webhook для заказа {$webhook['order_id']}");
        
        if (sendOrderWebhookToPythonCRM($webhook['order_id'], $webhook['event'], 1)) {
            $processedCount++;
            logWebhookEvent("Webhook для заказа {$webhook['order_id']} успешно отправлен при повторе");
        } else {
            // Увеличиваем счетчик попыток
            $webhook['retry_count']++;
            $webhook['timestamp'] = time();
            $remainingWebhooks[] = $webhook;
        }
    }
    
    // Сохраняем оставшиеся неудачные webhook
    file_put_contents($failedFile, json_encode($remainingWebhooks), LOCK_EX);
    
    if ($processedCount > 0) {
        logWebhookEvent("Обработано $processedCount неудачных webhook из очереди");
    }
}

logWebhookEvent("Production webhook integration загружен и активирован (заказы + товары)");

/**
 * КОМАНДЫ ДЛЯ МОНИТОРИНГА:
 * 
 * 1. Просмотр логов:
 *    tail -f /tmp/bitrix_webhook.log
 * 
 * 2. Просмотр очереди неудачных webhook:
 *    cat /tmp/failed_webhooks.json | jq .
 * 
 * 3. Обработка очереди вручную:
 *    php -r "include '/home/bitrix/www/bitrix/php_interface/init.php'; processFailedWebhooks();"
 * 
 * 4. Добавить в crontab для автоматической обработки очереди:
 *    */5 * * * * php -r "include '/home/bitrix/www/bitrix/php_interface/init.php'; processFailedWebhooks();"
 */

?>