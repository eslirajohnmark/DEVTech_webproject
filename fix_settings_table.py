# fix_settings_table.py
import pymysql

def fix_settings_table():
    try:
        # Connect to MySQL
        conn = pymysql.connect(
            host='localhost',
            user='root',
            password='admin123',  # Change this to your password
            database='devtech_db'
        )
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("SHOW TABLES LIKE 'system_settings'")
        if cursor.fetchone():
            print("Found system_settings table")
            
            # Check if 'key' column exists
            cursor.execute("SHOW COLUMNS FROM system_settings LIKE 'key'")
            if cursor.fetchone():
                print("Renaming 'key' column to 'setting_key'...")
                cursor.execute("ALTER TABLE system_settings CHANGE `key` setting_key VARCHAR(50) UNIQUE NOT NULL")
                print("✓ Column renamed successfully!")
            else:
                print("Column 'key' not found. Checking if 'setting_key' exists...")
                cursor.execute("SHOW COLUMNS FROM system_settings LIKE 'setting_key'")
                if cursor.fetchone():
                    print("✓ Column 'setting_key' already exists. No changes needed.")
                else:
                    print("Creating 'setting_key' column...")
                    cursor.execute("ALTER TABLE system_settings ADD setting_key VARCHAR(50) UNIQUE NOT NULL")
                    print("✓ Column created successfully!")
        else:
            print("Table 'system_settings' doesn't exist. Creating it...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_settings (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    setting_key VARCHAR(50) UNIQUE NOT NULL,
                    value TEXT,
                    description VARCHAR(200),
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """)
            print("✓ Table created successfully!")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print("\n✅ Database fixed successfully!")
        print("Now restart your Flask application.")
        
    except pymysql.Error as e:
        print(f"❌ Error: {e}")
        print("\nPlease check:")
        print("1. MySQL is running")
        print("2. Password is correct")
        print("3. Database 'devtech_db' exists")

if __name__ == '__main__':
    fix_settings_table()