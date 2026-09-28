-- ============================================================
-- DEVTech — migration: customer ratings for completed jobs
-- ============================================================
-- One rating per booking, submitted by the customer after the
-- technician marks the job complete. Immutable once written.
--
-- Safe to re-run — CREATE TABLE IF NOT EXISTS is idempotent.
--
-- Run with:
--   mysql -u root -p devtech_db < database/migrate_ratings.sql
-- ============================================================

USE devtech_db;

CREATE TABLE IF NOT EXISTS service_ratings (
    id             INT PRIMARY KEY AUTO_INCREMENT,
    booking_id     INT UNIQUE NOT NULL,
    technician_id  INT NOT NULL,
    customer_id    INT NOT NULL,
    stars          TINYINT NOT NULL,
    experience     TEXT,
    improvement    TEXT,
    submitted_at   DATETIME DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_ratings_booking
        FOREIGN KEY (booking_id)
        REFERENCES bookings(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_ratings_technician
        FOREIGN KEY (technician_id)
        REFERENCES users(id),

    CONSTRAINT fk_ratings_customer
        FOREIGN KEY (customer_id)
        REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---- supporting index ----
-- The technician's average rating is computed from this column on
-- every monitor-page load, so it needs an index. MySQL automatically
-- indexes the FK column, but on some versions that index is only
-- created for the constraint's own use — this guarantees the join
-- uses it.
SET @idx_exists := (
    SELECT COUNT(*)
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME   = 'service_ratings'
      AND INDEX_NAME   = 'idx_ratings_technician'
);

SET @sql := IF(@idx_exists = 0,
    'CREATE INDEX idx_ratings_technician ON service_ratings(technician_id)',
    'SELECT "idx_ratings_technician already exists" AS result'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SELECT 'Migration complete: service_ratings' AS status;