#!/bin/bash
# Import orders from production MySQL (Aug 17-19, 2025)

echo "📥 Importing orders from production (Aug 17-19, 2025)..."
echo "============================================================"
echo ""

# Production credentials
PROD_USER="usercvety"
PROD_PASS='QQlPCtTA@z2%mhy'
PROD_DB="dbcvety"
PROD_HOST="185.125.90.141"

# Local Docker MySQL credentials
LOCAL_USER="root"
LOCAL_PASS="cvety123"
LOCAL_DB="cvety_db"

echo "🔗 Connecting to production and exporting data..."

# Create temporary directory for exports
mkdir -p /tmp/prod_export

# Export orders from production
echo "📊 Exporting orders from Aug 17-19, 2025..."
ssh root@${PROD_HOST} << ENDSSH
cd /tmp

# Export orders
echo "Exporting orders..."
mysqldump -u ${PROD_USER} -p'${PROD_PASS}' ${PROD_DB} b_sale_order \
  --where="DATE(DATE_INSERT) BETWEEN '2025-08-17' AND '2025-08-19'" \
  --no-create-info \
  --complete-insert \
  --skip-triggers > orders_aug_17_19.sql

# Count orders
COUNT=\$(grep -c "INSERT INTO" orders_aug_17_19.sql 2>/dev/null || echo "0")
echo "  Found orders: \$COUNT"

# Get order IDs for related data
mysql -u ${PROD_USER} -p'${PROD_PASS}' ${PROD_DB} -N -e "
  SELECT ID FROM b_sale_order 
  WHERE DATE(DATE_INSERT) BETWEEN '2025-08-17' AND '2025-08-19'
" > order_ids.txt

# Convert to comma-separated list
ORDER_IDS=\$(cat order_ids.txt | tr '\n' ',' | sed 's/,\$//')

if [ ! -z "\$ORDER_IDS" ]; then
  echo "📦 Exporting basket items..."
  mysqldump -u ${PROD_USER} -p'${PROD_PASS}' ${PROD_DB} b_sale_basket \
    --where="ORDER_ID IN (\$ORDER_IDS)" \
    --no-create-info \
    --complete-insert \
    --skip-triggers > basket_aug_17_19.sql
  
  echo "📝 Exporting order properties..."
  mysqldump -u ${PROD_USER} -p'${PROD_PASS}' ${PROD_DB} b_sale_order_props_value \
    --where="ORDER_ID IN (\$ORDER_IDS)" \
    --no-create-info \
    --complete-insert \
    --skip-triggers > props_aug_17_19.sql
  
  # Create archive
  tar -czf orders_aug_17_19.tar.gz orders_aug_17_19.sql basket_aug_17_19.sql props_aug_17_19.sql
  echo "✅ Archive created: /tmp/orders_aug_17_19.tar.gz"
  
  # Show statistics
  BASKET_COUNT=\$(grep -c "INSERT INTO" basket_aug_17_19.sql 2>/dev/null || echo "0")
  PROPS_COUNT=\$(grep -c "INSERT INTO" props_aug_17_19.sql 2>/dev/null || echo "0")
  echo "  Basket items: \$BASKET_COUNT"
  echo "  Order properties: \$PROPS_COUNT"
else
  echo "⚠️ No orders found for the specified date range"
fi

# Cleanup
rm -f order_ids.txt

ENDSSH

echo ""
echo "📥 Downloading archive from production..."
scp root@${PROD_HOST}:/tmp/orders_aug_17_19.tar.gz /tmp/prod_export/

if [ -f /tmp/prod_export/orders_aug_17_19.tar.gz ]; then
  echo "📦 Extracting archive..."
  cd /tmp/prod_export
  tar -xzf orders_aug_17_19.tar.gz
  
  echo ""
  echo "🔄 Importing to local MySQL..."
  
  # Check if Docker container is running
  if docker ps | grep -q cvety_mysql; then
    # Import orders
    if [ -f orders_aug_17_19.sql ]; then
      echo "  • Importing orders..."
      docker exec -i cvety_mysql mysql -u ${LOCAL_USER} -p${LOCAL_PASS} ${LOCAL_DB} < orders_aug_17_19.sql
      ORDER_RESULT=$?
      if [ $ORDER_RESULT -eq 0 ]; then
        echo "    ✅ Orders imported successfully"
      else
        echo "    ⚠️ Some orders may have failed (duplicates are normal)"
      fi
    fi
    
    # Import basket items
    if [ -f basket_aug_17_19.sql ]; then
      echo "  • Importing basket items..."
      docker exec -i cvety_mysql mysql -u ${LOCAL_USER} -p${LOCAL_PASS} ${LOCAL_DB} < basket_aug_17_19.sql
      BASKET_RESULT=$?
      if [ $BASKET_RESULT -eq 0 ]; then
        echo "    ✅ Basket items imported successfully"
      else
        echo "    ⚠️ Some basket items may have failed (duplicates are normal)"
      fi
    fi
    
    # Import order properties
    if [ -f props_aug_17_19.sql ]; then
      echo "  • Importing order properties..."
      docker exec -i cvety_mysql mysql -u ${LOCAL_USER} -p${LOCAL_PASS} ${LOCAL_DB} < props_aug_17_19.sql
      PROPS_RESULT=$?
      if [ $PROPS_RESULT -eq 0 ]; then
        echo "    ✅ Order properties imported successfully"
      else
        echo "    ⚠️ Some properties may have failed (duplicates are normal)"
      fi
    fi
    
    echo ""
    echo "✅ Import completed!"
    
    # Verify imported data
    echo ""
    echo "📊 Verifying imported data:"
    docker exec cvety_mysql mysql -u ${LOCAL_USER} -p${LOCAL_PASS} ${LOCAL_DB} -e "
      SELECT 
        DATE(DATE_INSERT) as date,
        COUNT(*) as orders_count,
        MIN(ID) as first_id,
        MAX(ID) as last_id,
        SUM(PRICE) as total_revenue
      FROM b_sale_order
      WHERE DATE(DATE_INSERT) BETWEEN '2025-08-17' AND '2025-08-19'
      GROUP BY DATE(DATE_INSERT)
      ORDER BY date;
    "
    
    echo ""
    echo "📊 Sample orders (first 5):"
    docker exec cvety_mysql mysql -u ${LOCAL_USER} -p${LOCAL_PASS} ${LOCAL_DB} -e "
      SELECT 
        ID,
        ACCOUNT_NUMBER,
        STATUS_ID,
        PRICE,
        USER_ID,
        DATE_FORMAT(DATE_INSERT, '%Y-%m-%d %H:%i') as created
      FROM b_sale_order
      WHERE DATE(DATE_INSERT) BETWEEN '2025-08-17' AND '2025-08-19'
      ORDER BY ID DESC
      LIMIT 5;
    "
    
  else
    echo "❌ Docker container cvety_mysql is not running!"
    echo "   Please start it: cd /Users/alekenov/cvety-local && docker-compose up -d"
    exit 1
  fi
  
  # Cleanup temporary files
  echo ""
  echo "🧹 Cleaning up temporary files..."
  rm -f /tmp/prod_export/*.sql
  
else
  echo "❌ Failed to download archive from production"
  exit 1
fi

echo ""
echo "🚀 Ready to test migration!"
echo ""
echo "Test with a few orders first:"
echo "  python3 migrate_from_local_mysql.py --count 5"
echo ""
echo "Or migrate specific order IDs:"
echo "  python3 migrate_from_local_mysql.py --order-ids 122001,122002,122003"
echo ""
echo "To migrate all Aug 17-19 orders:"
echo "  python3 migrate_from_local_mysql.py --date-from 2025-08-17 --date-to 2025-08-19"