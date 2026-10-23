# fix_settings_table.py
"""One-off repair for old databases whose system_settings table used a column
named `key`. Connects using DATABASE_URL from .env; no credentials in source."""
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


def fix_settings_table():
    load_dotenv()
    url = os.environ.get('DATABASE_URL')
    if not url:
        print("❌ DATABASE_URL is not set. Copy .env.example to .env and fill it in.")
        return

    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            # Check if table exists
            if conn.execute(text("SHOW TABLES LIKE 'system_settings'")).fetchone():
                print("Found system_settings table")

                # Check if 'key' column exists
                if conn.execute(text("SHOW COLUMNS FROM system_settings LIKE 'key'")).fetchone():
                    print("Renaming 'key' column to 'setting_key'...")
                    conn.execute(text("ALTER TABLE system_settings CHANGE `key` setting_key VARCHAR(50) UNIQUE NOT NULL"))
                    print("✓ Column renamed successfully!")
                else:
                    print("Column 'key' not found. Checking if 'setting_key' exists...")
                    if conn.execute(text("SHOW COLUMNS FROM system_settings LIKE 'setting_key'")).fetchone():
                        print("✓ Column 'setting_key' already exists. No changes needed.")
                    else:
                        print("Creating 'setting_key' column...")
                        conn.execute(text("ALTER TABLE system_settings ADD setting_key VARCHAR(50) UNIQUE NOT NULL"))
                        print("✓ Column created successfully!")
            else:
                print("Table 'system_settings' doesn't exist. Creating it...")
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS system_settings (
                        id INT PRIMARY KEY AUTO_INCREMENT,
                        setting_key VARCHAR(50) UNIQUE NOT NULL,
                        value TEXT,
                        description VARCHAR(200),
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    )
                """))
                print("✓ Table created successfully!")

        print("\n✅ Database fixed successfully!")
        print("Now restart your Flask application.")

    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nPlease check:")
        print("1. MySQL is running")
        print("2. DATABASE_URL in .env is correct")
        print("3. The database it names exists")


if __name__ == '__main__':
    fix_settings_table()
