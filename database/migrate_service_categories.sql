-- ============================================================
-- DEVTech — migration: service category visual metadata
-- ============================================================
-- Adds five columns to service_categories so the customer-facing
-- catalog page can render the reference grid: colored icon tiles,
-- ordered display, URL-friendly slugs, and an optional tagline.
--
-- Safe to re-run. Every ALTER is guarded by an information_schema
-- check, so running this twice is a no-op the second time.
--
-- Run with:
--   mysql -u root -p devtech_db < database/migrate_service_categories.sql
-- ============================================================

USE devtech_db;

-- ---- helper: add a column only if it doesn't already exist ----
DROP PROCEDURE IF EXISTS devtech_add_column;
DELIMITER //
CREATE PROCEDURE devtech_add_column(
    IN p_table   VARCHAR(64),
    IN p_column  VARCHAR(64),
    IN p_def     VARCHAR(255)
)
BEGIN
    DECLARE col_count INT DEFAULT 0;

    SELECT COUNT(*) INTO col_count
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME   = p_table
      AND COLUMN_NAME  = p_column;

    IF col_count = 0 THEN
        SET @sql = CONCAT(
            'ALTER TABLE ', p_table,
            ' ADD COLUMN ', p_column, ' ', p_def
        );
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
        SELECT CONCAT('Added column ', p_table, '.', p_column) AS result;
    ELSE
        SELECT CONCAT('Column ', p_table, '.', p_column, ' already exists') AS result;
    END IF;
END //
DELIMITER ;

-- ---- the five new columns ----

-- URL-friendly identifier used by /user/book/<slug>.
-- Nullable because existing rows predate this migration; the app
-- falls back to `cat-<id>` when slug is NULL.
CALL devtech_add_column(
    'service_categories', 'slug',
    'VARCHAR(50) NULL UNIQUE'
);

-- Hex color for the icon tile and card header.
-- Defaults to the primary blue so existing rows still render.
CALL devtech_add_column(
    'service_categories', 'color',
    'VARCHAR(20) NOT NULL DEFAULT "#2563eb"'
);

-- Font Awesome class name (without the "fa-" prefix handled in code;
-- the app prepends "fas fa-" when rendering).
CALL devtech_add_column(
    'service_categories', 'icon',
    'VARCHAR(50) NOT NULL DEFAULT "fa-tools"'
);

-- Ordering hint for the catalog grid. Lower numbers appear first.
-- Existing rows default to 100 so they sort after seeded ones.
CALL devtech_add_column(
    'service_categories', 'display_order',
    'INT NOT NULL DEFAULT 100'
);

-- Optional one-line note shown at the bottom of a category card
-- (e.g. the data-recovery disclaimer in the reference design).
CALL devtech_add_column(
    'service_categories', 'tagline',
    'VARCHAR(200) NULL'
);

-- ---- backfill slugs for existing rows ----
-- Generates a slug from the category name. Two categories named
-- "Hardware Repair" and "hardware repair" would collide, so this
-- appends the id on duplicates.
UPDATE service_categories
SET slug = LOWER(
    REPLACE(
        REPLACE(
            REPLACE(name, ' & ', '-'),
            ' ', '-'
        ),
        '/', '-'
    )
)
WHERE slug IS NULL;

-- Resolve any slug collisions by appending the id.
-- Runs once; after this the UNIQUE constraint on slug is satisfied.
UPDATE service_categories sc
JOIN (
    SELECT slug, COUNT(*) AS n
    FROM service_categories
    WHERE slug IS NOT NULL
    GROUP BY slug
    HAVING n > 1
) dup ON dup.slug = sc.slug
SET sc.slug = CONCAT(sc.slug, '-', sc.id);

-- ---- cleanup ----
DROP PROCEDURE IF EXISTS devtech_add_column;

SELECT 'Migration complete: service_categories' AS status;