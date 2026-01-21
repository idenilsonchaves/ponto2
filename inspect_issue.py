import sqlite3
import os

def inspect_db(db_path):
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return

    print(f"--- Inspecting {db_path} ---")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Check Ajustes for the 24th
    print("Checking Ajustes for 2025-12-24:")
    cursor.execute("SELECT * FROM ajustes WHERE data = '2025-12-24'")
    ajustes = cursor.fetchall()
    for a in ajustes:
        print(dict(a))

    # Check Registros for the 24th
    print("\nChecking Registros for 2025-12-24:")
    cursor.execute("SELECT * FROM registros WHERE data = '2025-12-24'")
    registros = cursor.fetchall()
    for r in registros:
        print(dict(r))
    
    conn.close()

if __name__ == "__main__":
    # Check both potential databases
    inspect_db(os.path.join(os.getcwd(), "dist", "database.db"))
    inspect_db(os.path.join(os.getcwd(), "config", "database.db"))
