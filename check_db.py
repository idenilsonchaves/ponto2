import sys
import os
import sqlite3
from datetime import datetime

# Adicionar diretório atual ao path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.operations import db_manager

def verificar_registros():
    print("=== VERIFICAÇÃO DE REGISTROS DE PONTO ===")
    print(f"Banco de dados: {db_manager.db_path}")
    
    with db_manager._connect() as conn:
        cursor = conn.cursor()
        
        # 1. Verificar últimos registros brutos
        print("\n--- Últimos 10 registros (tabela 'registros') ---")
        cursor.execute("""
            SELECT id, funcionario_id, data, tipo, hora_entrada, saida_almoco, retorno_almoco, saida_final, ts_server 
            FROM registros 
            ORDER BY id DESC 
            LIMIT 10
        """)
        rows = cursor.fetchall()
        
        if not rows:
            print("Nenhum registro encontrado.")
        else:
            print(f"{'ID':<5} | {'FuncID':<6} | {'Data':<10} | {'Tipo':<15} | {'Entrada':<8} | {'S.Almoço':<8} | {'R.Almoço':<8} | {'Saída':<8} | {'Registrado Em'}")
            print("-" * 110)
            for row in rows:
                func_id = str(row['funcionario_id']) if row['funcionario_id'] is not None else "-"
                print(f"{row['id']:<5} | {func_id:<6} | {row['data']:<10} | {row['tipo']:<15} | "
                      f"{row['hora_entrada'] or '-':<8} | {row['saida_almoco'] or '-':<8} | "
                      f"{row['retorno_almoco'] or '-':<8} | {row['saida_final'] or '-':<8} | {row['ts_server']}")

        # 2. Contagem total
        cursor.execute("SELECT COUNT(*) as total FROM registros")
        total = cursor.fetchone()['total']
        print(f"\nTotal de registros no banco: {total}")

if __name__ == "__main__":
    verificar_registros()
