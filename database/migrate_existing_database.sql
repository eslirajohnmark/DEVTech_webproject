-- ============================================================
-- Upgrade an EXISTING devtech_db to the current schema.sql.
-- 
-- Safe to run multiple times - uses INFORMATION_SCHEMA checks
-- instead of "ADD COLUMN IF NOT EXISTS" for MySQL 5.7 compatibility.
-- ============================================================

USE devtech_db;

-- Helper stored procedure to safely add columns (MySQL 5.7 compatible)
DROP PROCEDURE IF EXISTS add_column_if_not_exists;
DELIMITER //
CREATE PROCEDURE add_column_if_not_exists(
    IN table_name VARCHAR(64),
    IN column_name VARCHAR(64),
    IN column_definition VARCHAR(255)
)
BEGIN
    DECLARE col_count INT;
    
    SELECT COUNT(*) INTO col_count
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = table_name
      AND COLUMN_NAME = column_name;
    
    IF col_count = 0 THEN
        SET @sql = CONCAT('ALTER TABLE ', table_name, ' ADD COLUMN ', column_name, ' ', column_definition);
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END //
DELIMITER ;

-- ---- users: Google/Facebook login identity ----
CALL add_column_if_not_exists('users', 'oauth_provider', 'VARCHAR(20) NULL');
CALL add_column_if_not_exists('users', 'oauth_id', 'VARCHAR(255) NULL');

-- Add unique constraint if it doesn't exist
SET @constraint_exists = (
    SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'users'
      AND CONSTRAINT_NAME = 'uq_users_oauth_identity'
);
SET @sql = IF(@constraint_exists = 0,
    'ALTER TABLE users ADD CONSTRAINT uq_users_oauth_identity UNIQUE (oauth_provider, oauth_id)',
    'SELECT "uq_users_oauth_identity already exists"'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ---- transactions: proof-of-payment upload + wider reference numbers ----
CALL add_column_if_not_exists('transactions', 'receipt_image', 'VARCHAR(255) NULL');

-- Modify column (safe to run multiple times)
ALTER TABLE transactions
    MODIFY COLUMN transaction_number VARCHAR(50) NOT NULL;

-- ---- bookings: wider booking numbers (matches app.py's model) ----
ALTER TABLE bookings
    MODIFY COLUMN booking_number VARCHAR(50) NOT NULL;

-- ---- orders: delivery-address snapshot + wider order numbers ----
ALTER TABLE orders
    MODIFY COLUMN order_number VARCHAR(50) NOT NULL;

CALL add_column_if_not_exists('orders', 'recipient_name', 'VARCHAR(100) NULL');
CALL add_column_if_not_exists('orders', 'recipient_phone', 'VARCHAR(20) NULL');
CALL add_column_if_not_exists('orders', 'address_line', 'VARCHAR(255) NULL');
CALL add_column_if_not_exists('orders', 'city', 'VARCHAR(50) NULL');
CALL add_column_if_not_exists('orders', 'province', 'VARCHAR(50) NULL');
CALL add_column_if_not_exists('orders', 'postal_code', 'VARCHAR(10) NULL');
CALL add_column_if_not_exists('orders', 'latitude', 'DECIMAL(10,7) NULL');
CALL add_column_if_not_exists('orders', 'longitude', 'DECIMAL(10,7) NULL');

-- Backfill existing orders from the customer's current profile
UPDATE orders o
JOIN users u ON u.id = o.user_id
SET
    o.recipient_name  = COALESCE(o.recipient_name, u.full_name),
    o.recipient_phone = COALESCE(o.recipient_phone, u.phone),
    o.address_line    = COALESCE(o.address_line, u.address),
    o.city            = COALESCE(o.city, u.city),
    o.province        = COALESCE(o.province, u.province),
    o.postal_code     = COALESCE(o.postal_code, u.postal_code),
    o.latitude        = COALESCE(o.latitude, u.latitude),
    o.longitude       = COALESCE(o.longitude, u.longitude)
WHERE o.address_line IS NULL
  AND o.id > 0;

-- Clean up the stored procedure
DROP PROCEDURE IF EXISTS add_column_if_not_exists;

-- ============================================================
-- Adds technician assignment + identity verification to an
-- EXISTING devtech_db. Skip this if setting up a brand new
-- database from schema.sql, which already includes these columns.
-- Safe to run multiple times.
-- ============================================================

USE devtech_db;

DROP PROCEDURE IF EXISTS add_column_if_not_exists_tv;
DELIMITER //
CREATE PROCEDURE add_column_if_not_exists_tv(
    IN p_table VARCHAR(64),
    IN p_column VARCHAR(64),
    IN p_definition VARCHAR(255)
)
BEGIN
    DECLARE col_count INT;
    SELECT COUNT(*) INTO col_count
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = p_table AND COLUMN_NAME = p_column;

    IF col_count = 0 THEN
        SET @sql = CONCAT('ALTER TABLE ', p_table, ' ADD COLUMN ', p_column, ' ', p_definition);
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END //
DELIMITER ;

-- ---- users: technician identity verification ----
-- id_number is an internal audit record only - the app never returns it
-- through any API response or template, only the id_verified boolean.
CALL add_column_if_not_exists_tv('users', 'id_type', 'VARCHAR(30) NULL');
CALL add_column_if_not_exists_tv('users', 'id_number', 'VARCHAR(50) NULL');
CALL add_column_if_not_exists_tv('users', 'id_verified', 'BOOLEAN DEFAULT FALSE');
CALL add_column_if_not_exists_tv('users', 'id_verified_at', 'DATETIME NULL');

-- ---- bookings: technician assignment ----
CALL add_column_if_not_exists_tv('bookings', 'technician_id', 'INT NULL');
CALL add_column_if_not_exists_tv('bookings', 'assigned_at', 'DATETIME NULL');

SET @fk_exists = (
    SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'bookings'
      AND CONSTRAINT_NAME = 'fk_bookings_technician'
);
SET @sql = IF(@fk_exists = 0,
    'ALTER TABLE bookings ADD CONSTRAINT fk_bookings_technician FOREIGN KEY (technician_id) REFERENCES users(id)',
    'SELECT "fk_bookings_technician already exists"'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

DROP PROCEDURE IF EXISTS add_column_if_not_exists_tv;
