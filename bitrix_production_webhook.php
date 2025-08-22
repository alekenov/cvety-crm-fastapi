<?php
/**
 * Webhook код для добавления в production Bitrix
 * Файл: /home/bitrix/www/bitrix/php_interface/init.php
 * 
 * Добавить этот код в конец файла init.php на production сервере
 */

// URL Python CRM для отправки webhook
define('PYTHON_CRM_WEBHOOK_URL', 'https://your-python-crm.com/webhooks/bitrix/order');
// В продакшне заменить на реальный URL и установить HTTPS

// Токен для аутентификации webhook (заменить на криптографически стойкий)
define('PYTHON_CRM_WEBHOOK_TOKEN', 'production-secure-token-2025');

/**
 * Отправляет webhook в Python CRM
 */
function sendOrderWebhookToPythonCRM($orderId, $event = 'order.create') {
    try {
        // Получаем данные заказа
        $order = CSaleOrder::GetByID($orderId);
        if (!$order) {
            AddMessage2Log("Webhook: Order $orderId not found", "python_crm_webhook");
            return false;
        }
        
        // Получаем товары в заказе
        $basket = array();
        $basketDb = CSaleBasket::GetList(
            array(),
            array("ORDER_ID" => $orderId),
            false,
            false,
            array("ID", "PRODUCT_ID", "NAME", "PRICE", "CURRENCY", "QUANTITY", "DISCOUNT_PRICE")
        );
        while ($basketItem = $basketDb->Fetch()) {
            $basket[] = $basketItem;
        }
        
        // Получаем свойства заказа
        $properties = array();
        $propsDb = CSaleOrderPropsValue::GetList(
            array(),
            array("ORDER_ID" => $orderId),
            false,
            false,
            array("ID", "ORDER_PROPS_ID", "NAME", "VALUE", "CODE")
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
                ($by = "id"),
                ($sort = "asc"),
                array("ID" => $order['USER_ID']),
                array(
                    "SELECT" => array("ID", "LOGIN", "EMAIL", "NAME", "LAST_NAME", "PERSONAL_PHONE")
                )
            );
            if ($userFetch = $userDb->Fetch()) {
                $user = $userFetch;
            }
        }
        
        // Формируем payload для webhook
        $payload = array(
            'event' => $event,
            'token' => PYTHON_CRM_WEBHOOK_TOKEN,
            'data' => array_merge($order, array(
                'basket' => $basket,
                'properties' => $properties,
                'user' => $user
            ))
        );
        
        // Отправляем HTTP POST запрос
        $context = stream_context_create(array(
            'http' => array(
                'method' => 'POST',
                'header' => array(
                    'Content-Type: application/json',
                    'User-Agent: Bitrix-Webhook/1.0'
                ),
                'content' => json_encode($payload),
                'timeout' => 10
            )
        ));
        
        $response = file_get_contents(PYTHON_CRM_WEBHOOK_URL, false, $context);
        
        if ($response === false) {
            throw new Exception('HTTP request failed');
        }
        
        // Парсим ответ
        $responseData = json_decode($response, true);
        
        if ($responseData && isset($responseData['status']) && $responseData['status'] === 'success') {
            AddMessage2Log("Webhook: Order $orderId successfully sent to Python CRM", "python_crm_webhook");
            return true;
        } else {
            throw new Exception('Python CRM returned error: ' . $response);
        }
        
    } catch (Exception $e) {
        AddMessage2Log("Webhook error for order $orderId: " . $e->getMessage(), "python_crm_webhook");
        
        // В случае ошибки можно добавить заказ в очередь для повторной отправки
        // Здесь можно реализовать retry механизм
        
        return false;
    }
}

/**
 * Event handler для создания заказа
 */
function OnSaleOrderSavedHandler(&$ID, $arFields, $orderID, $isNew) {
    // Отправляем webhook только для новых заказов или при изменении статуса
    if ($isNew || (isset($arFields['STATUS_ID']) && $arFields['STATUS_ID'])) {
        $event = $isNew ? 'order.create' : 'order.update';
        
        // Отправляем асинхронно, чтобы не замедлить создание заказа
        if (function_exists('fastcgi_finish_request')) {
            fastcgi_finish_request();
        }
        
        sendOrderWebhookToPythonCRM($ID, $event);
    }
}

/**
 * Event handler для изменения статуса заказа
 */
function OnSaleStatusOrderHandler($ID, $statusID) {
    // Отправляем webhook при изменении статуса
    sendOrderWebhookToPythonCRM($ID, 'order.update');
}

// Регистрируем event handlers
AddEventHandler("sale", "OnSaleOrderSaved", "OnSaleOrderSavedHandler");
AddEventHandler("sale", "OnSaleStatusOrder", "OnSaleStatusOrderHandler");

/**
 * ИНСТРУКЦИЯ ПО УСТАНОВКЕ:
 * 
 * 1. Скопировать этот код в конец файла /home/bitrix/www/bitrix/php_interface/init.php
 * 
 * 2. Заменить PYTHON_CRM_WEBHOOK_URL на реальный URL вашего Python CRM:
 *    define('PYTHON_CRM_WEBHOOK_URL', 'https://your-python-crm.com/webhooks/bitrix/order');
 * 
 * 3. Заменить токен на криптографически стойкий:
 *    define('PYTHON_CRM_WEBHOOK_TOKEN', 'your-secure-token-here');
 * 
 * 4. Обновить токен в Python CRM (.env файл):
 *    WEBHOOK_TOKEN=your-secure-token-here
 * 
 * 5. Настроить HTTPS для безопасной передачи данных
 * 
 * 6. Протестировать создание нового заказа в Bitrix
 * 
 * 7. Проверить логи:
 *    tail -f /var/log/bitrix/php_errors.log | grep python_crm_webhook
 * 
 * ВАЖНО:
 * - Использовать HTTPS для production
 * - Регулярно проверять логи на ошибки
 * - Можно добавить retry механизм для failed webhooks
 * - При большой нагрузке рассмотреть очередь сообщений (Redis/RabbitMQ)
 */
?>