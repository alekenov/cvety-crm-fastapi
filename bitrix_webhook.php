<?php
/**
 * Webhook интеграция для отправки заказов из Bitrix в Python CRM
 * 
 * Этот код нужно добавить в файл:
 * /home/bitrix/www/local/php_interface/init.php
 * 
 * Или создать отдельный файл:
 * /home/bitrix/www/local/php_interface/webhook_integration.php
 * и подключить его в init.php через require_once
 */

// ===== КОНФИГУРАЦИЯ =====
define('WEBHOOK_URL', 'https://your-python-crm.com/api/webhooks/bitrix/order');
define('WEBHOOK_TOKEN', 'secret-webhook-token-2024');
define('WEBHOOK_ENABLED', true); // Можно выключить для отладки
define('WEBHOOK_LOG_FILE', '/home/bitrix/www/upload/webhook_log.txt'); // Лог для отладки

// ===== ОБРАБОТЧИКИ СОБЫТИЙ =====

/**
 * Обработчик создания нового заказа
 */
AddEventHandler("sale", "OnOrderAdd", "SendOrderToFastAPI");

/**
 * Обработчик обновления заказа
 */
AddEventHandler("sale", "OnOrderUpdate", "SendOrderUpdateToFastAPI");

/**
 * Обработчик изменения статуса заказа
 */
AddEventHandler("sale", "OnSaleStatusOrderChange", "SendStatusChangeToFastAPI");

/**
 * Основная функция отправки заказа в Python CRM
 */
function SendOrderToFastAPI($ID, $arFields = null) {
    if (!WEBHOOK_ENABLED) {
        return;
    }
    
    try {
        // Защита от дублирования
        if (isset($GLOBALS['webhook_sent_order_' . $ID])) {
            return;
        }
        $GLOBALS['webhook_sent_order_' . $ID] = true;
        
        // Загружаем модуль sale
        if (!CModule::IncludeModule("sale")) {
            WebhookLog("ERROR: Cannot include sale module for order $ID");
            return;
        }
        
        // Получаем полные данные заказа
        $orderData = GetFullOrderData($ID);
        
        if (!$orderData) {
            WebhookLog("ERROR: Cannot get order data for ID $ID");
            return;
        }
        
        // Отправляем webhook
        $result = SendWebhook(WEBHOOK_URL, $orderData);
        
        // Логируем результат
        if ($result['success']) {
            WebhookLog("SUCCESS: Order $ID sent to Python CRM");
        } else {
            WebhookLog("ERROR: Failed to send order $ID - " . $result['error']);
        }
        
    } catch (Exception $e) {
        WebhookLog("EXCEPTION: " . $e->getMessage());
    }
}

/**
 * Обработчик обновления заказа
 */
function SendOrderUpdateToFastAPI($ID, $arFields) {
    // Используем ту же функцию, что и для создания
    SendOrderToFastAPI($ID, $arFields);
}

/**
 * Обработчик изменения статуса
 */
function SendStatusChangeToFastAPI($ID, $STATUS_ID) {
    if (!WEBHOOK_ENABLED) {
        return;
    }
    
    try {
        $data = array(
            'order_id' => $ID,
            'status' => $STATUS_ID,
            'timestamp' => date('c')
        );
        
        // Отправляем на другой endpoint
        $result = SendWebhook(
            str_replace('/order', '/status', WEBHOOK_URL),
            $data
        );
        
        if ($result['success']) {
            WebhookLog("SUCCESS: Status change for order $ID sent");
        } else {
            WebhookLog("ERROR: Failed to send status change for order $ID");
        }
        
    } catch (Exception $e) {
        WebhookLog("EXCEPTION in status change: " . $e->getMessage());
    }
}

/**
 * Получение полных данных заказа
 */
function GetFullOrderData($orderId) {
    try {
        // Получаем основные данные заказа
        $order = CSaleOrder::GetByID($orderId);
        
        if (!$order) {
            return null;
        }
        
        // Добавляем ID в данные
        $order['order_id'] = $orderId;
        
        // Получаем товары заказа
        $basket = array();
        $dbBasket = CSaleBasket::GetList(
            array(),
            array("ORDER_ID" => $orderId),
            false,
            false,
            array()
        );
        
        while ($item = $dbBasket->Fetch()) {
            $basket[] = array(
                'ID' => $item['ID'],
                'PRODUCT_ID' => $item['PRODUCT_ID'],
                'NAME' => $item['NAME'],
                'PRICE' => $item['PRICE'],
                'QUANTITY' => $item['QUANTITY'],
                'CURRENCY' => $item['CURRENCY'],
                'DISCOUNT_PRICE' => $item['DISCOUNT_PRICE'],
                'VAT_RATE' => $item['VAT_RATE'],
                'PRODUCT_XML_ID' => $item['PRODUCT_XML_ID'],
                'DETAIL_PAGE_URL' => $item['DETAIL_PAGE_URL']
            );
        }
        
        $order['basket'] = $basket;
        
        // Получаем свойства заказа
        $properties = array();
        $dbProps = CSaleOrderPropsValue::GetList(
            array(),
            array("ORDER_ID" => $orderId)
        );
        
        while ($prop = $dbProps->Fetch()) {
            $code = $prop['CODE'] ?: 'PROP_' . $prop['ORDER_PROPS_ID'];
            $properties[$code] = $prop['VALUE'];
        }
        
        $order['properties'] = $properties;
        
        // Добавляем timestamp
        $order['webhook_timestamp'] = date('c');
        
        return $order;
        
    } catch (Exception $e) {
        WebhookLog("ERROR in GetFullOrderData: " . $e->getMessage());
        return null;
    }
}

/**
 * Отправка webhook запроса
 */
function SendWebhook($url, $data) {
    try {
        $jsonData = json_encode($data, JSON_UNESCAPED_UNICODE);
        
        // Настройки cURL
        $ch = curl_init($url);
        curl_setopt($ch, CURLOPT_POST, 1);
        curl_setopt($ch, CURLOPT_POSTFIELDS, $jsonData);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_TIMEOUT, 5); // Таймаут 5 секунд
        curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, 2); // Таймаут соединения 2 секунды
        curl_setopt($ch, CURLOPT_HTTPHEADER, array(
            'Content-Type: application/json',
            'X-Webhook-Token: ' . WEBHOOK_TOKEN,
            'Content-Length: ' . strlen($jsonData)
        ));
        
        // SSL настройки для локальной разработки
        if (strpos($url, 'localhost') !== false || strpos($url, '127.0.0.1') !== false) {
            curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
            curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, false);
        }
        
        $response = curl_exec($ch);
        $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $error = curl_error($ch);
        curl_close($ch);
        
        if ($error) {
            return array('success' => false, 'error' => $error);
        }
        
        if ($httpCode >= 200 && $httpCode < 300) {
            return array('success' => true, 'response' => $response);
        } else {
            return array('success' => false, 'error' => "HTTP $httpCode: $response");
        }
        
    } catch (Exception $e) {
        return array('success' => false, 'error' => $e->getMessage());
    }
}

/**
 * Функция логирования для отладки
 */
function WebhookLog($message) {
    if (defined('WEBHOOK_LOG_FILE')) {
        $logMessage = date('[Y-m-d H:i:s] ') . $message . PHP_EOL;
        file_put_contents(WEBHOOK_LOG_FILE, $logMessage, FILE_APPEND | LOCK_EX);
    }
}

/**
 * Тестовая функция для проверки webhook
 * Можно вызвать из PHP консоли Bitrix: TestWebhook(122005);
 */
function TestWebhook($orderId) {
    echo "Testing webhook for order $orderId\n";
    
    // Временно включаем логирование
    $oldLogFile = WEBHOOK_LOG_FILE;
    define('WEBHOOK_LOG_FILE', '/tmp/webhook_test.log');
    
    // Отправляем webhook
    SendOrderToFastAPI($orderId);
    
    // Читаем лог
    if (file_exists('/tmp/webhook_test.log')) {
        echo "Log output:\n";
        echo file_get_contents('/tmp/webhook_test.log');
        unlink('/tmp/webhook_test.log');
    }
    
    echo "Test completed\n";
}

// ===== АСИНХРОННАЯ ОТПРАВКА (ОПЦИОНАЛЬНО) =====
/**
 * Для больших нагрузок можно использовать фоновую отправку
 */
function SendWebhookAsync($url, $data) {
    $jsonData = json_encode($data, JSON_UNESCAPED_UNICODE);
    $jsonData = escapeshellarg($jsonData);
    
    $cmd = sprintf(
        'curl -X POST %s -H "Content-Type: application/json" -H "X-Webhook-Token: %s" -d %s > /dev/null 2>&1 &',
        escapeshellarg($url),
        escapeshellarg(WEBHOOK_TOKEN),
        $jsonData
    );
    
    exec($cmd);
    
    return array('success' => true, 'async' => true);
}