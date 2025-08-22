<?php
/**
 * Тестовый скрипт для проверки production webhook
 * Запускать на сервере 185.125.90.141
 */

// Тестовые данные заказа
$testOrderData = array(
    'ID' => '999002',
    'ACCOUNT_NUMBER' => 'PROD-TEST-002',
    'STATUS_ID' => 'N',
    'PRICE' => '2000',
    'PRICE_DELIVERY' => '200',
    'USER_ID' => '171533',
    'DATE_INSERT' => date('Y-m-d H:i:s'),
    'properties' => array(
        'nameRecipient' => 'Тест с production сервера',
        'phoneRecipient' => '+77771234567',
        'addressRecipient' => 'Астана, ул. Production 1',
        'data' => date('Y-m-d', strtotime('+1 day')),
        'when' => '26',
        'city' => 'astana'
    ),
    'basket' => array(
        array(
            'ID' => '1002',
            'PRODUCT_ID' => '12346',
            'NAME' => 'Production тестовый букет',
            'PRICE' => '1800',
            'QUANTITY' => '1'
        )
    ),
    'user' => array(
        'ID' => '171533',
        'EMAIL' => 'test@cvety.kz',
        'NAME' => 'Тест',
        'LAST_NAME' => 'Production'
    )
);

// Подключаем init.php чтобы функции webhook были доступны
require_once '/home/bitrix/www/bitrix/php_interface/init.php';

echo "🧪 ТЕСТ PRODUCTION WEBHOOK\n";
echo "========================\n\n";

echo "📦 Тестовый заказ ID: " . $testOrderData['ID'] . "\n";
echo "📧 Отправка webhook...\n";

// Вызываем функцию отправки webhook напрямую
if (function_exists('sendOrderWebhookToPythonCRM')) {
    $result = sendOrderWebhookToPythonCRM($testOrderData['ID'], 'order.create');
    
    if ($result) {
        echo "✅ Webhook отправлен успешно!\n";
    } else {
        echo "❌ Ошибка отправки webhook\n";
        echo "📄 Проверьте логи: tail -f /tmp/bitrix_webhook.log\n";
    }
} else {
    echo "❌ Функция sendOrderWebhookToPythonCRM не найдена\n";
    echo "   Проверьте, что webhook код правильно интегрирован в init.php\n";
}

echo "\n📊 МОНИТОРИНГ:\n";
echo "Логи webhook: tail -f /tmp/bitrix_webhook.log\n";
echo "Очередь ошибок: cat /tmp/failed_webhooks.json\n";
echo "\n";
?>