import sqlite3
import os

def check_db(db_path):
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    print(f"\nChecking database: {db_path}")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"Tables found: {', '.join(tables)}")
        
        # Count records in each table
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"  - {table}: {count} records")
            except Exception as e:
                print(f"  - {table}: Error counting ({e})")
                
        conn.close()
    except Exception as e:
        print(f"Error connecting to database: {e}")

if __name__ == "__main__":
    check_db("database.db")
    check_db("dist/database.db")
