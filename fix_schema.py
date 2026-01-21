import sqlite3
import os

def create_deps_table(db_path):
    if not os.path.exists(db_path):
        return

    print(f"Updating schema for {db_path}...")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create departamentos table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS departamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT UNIQUE
            )
        """)
        print("  - departamentos table checked/created.")
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"  - Error updating schema: {e}")

if __name__ == "__main__":
    create_deps_table("database.db")
    create_deps_table("dist/database.db")
