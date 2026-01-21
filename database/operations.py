import os
import sqlite3
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

from config.settings import config
from models.entities import Funcionario, RegistroPonto, Usuario, Jornada
from utils.helpers import SecurityUtils

class DatabaseManager:
    def __init__(self):
        self.db_path = config.get("DATABASE", "path")
        self._ensure_directories()
        self._init_db()
    
    def _ensure_directories(self):
        Path(config.get("DATABASE", "backup_dir")).mkdir(parents=True, exist_ok=True)
        Path(os.path.join(config.base_dir, "logs")).mkdir(parents=True, exist_ok=True)
        Path(os.path.join(config.base_dir, "relatorios")).mkdir(parents=True, exist_ok=True)
    
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    
    def _init_db(self):
        with self._connect() as conn:
            self._create_tables(conn)
            self._check_schema_updates(conn)
            self._seed_defaults(conn)
    
    def _check_schema_updates(self, conn: sqlite3.Connection):
        """Verifica e aplica atualizações de schema (migrações simples)"""
        cursor = conn.cursor()
        
        # Verificar colunas da tabela funcionarios
        cursor.execute("PRAGMA table_info(funcionarios)")
        columns = [row["name"] for row in cursor.fetchall()]
        
        if "pis" not in columns:
            try:
                cursor.execute("ALTER TABLE funcionarios ADD COLUMN pis TEXT")
                logging.info("Coluna 'pis' adicionada à tabela funcionarios")
            except Exception as e:
                logging.error(f"Erro ao adicionar coluna pis: {e}")

        if "pin" not in columns:
            try:
                cursor.execute("ALTER TABLE funcionarios ADD COLUMN pin TEXT")
                logging.info("Coluna 'pin' adicionada à tabela funcionarios")
            except Exception as e:
                logging.error(f"Erro ao adicionar coluna pin: {e}")

    def _create_tables(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS funcionarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                cpf TEXT UNIQUE NOT NULL,
                pis TEXT,
                cargo TEXT,
                departamento TEXT,
                carga_horaria_min INTEGER DEFAULT 480,
                email TEXT,
                hora_entrada TEXT,
                hora_saida TEXT,
                ativo INTEGER DEFAULT 1,
                pin TEXT
            )
            """
        )
        
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS registros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                funcionario_id INTEGER,
                cpf TEXT,
                data TEXT,
                hora_entrada TEXT,
                hora_saida TEXT,
                saida_almoco TEXT,
                retorno_almoco TEXT,
                saida_final TEXT,
                ts TEXT,
                tipo TEXT,
                ts_device TEXT,
                ts_server TEXT,
                device_id TEXT,
                gps_lat REAL,
                gps_lng REAL,
                foto_path TEXT,
                ip_addr TEXT,
                antifraude_msg TEXT,
                extra_noturna_inicio TEXT,
                extra_noturna_fim TEXT,
                FOREIGN KEY(funcionario_id) REFERENCES funcionarios(id) ON DELETE SET NULL
            )
            """
        )
        
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT,
                role TEXT NOT NULL,
                funcionario_id INTEGER,
                failed_attempts INTEGER DEFAULT 0,
                lock_until TEXT,
                require_2fa INTEGER DEFAULT 0,
                FOREIGN KEY(funcionario_id) REFERENCES funcionarios(id) ON DELETE SET NULL
            )
            """
        )
        
        tables_sql = [
            """
            CREATE TABLE IF NOT EXISTS ajustes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                funcionario_id INTEGER,
                cpf TEXT,
                data TEXT,
                tipo TEXT,
                hora TEXT,
                observacao TEXT,
                status TEXT,
                created_at TEXT,
                approved_by TEXT,
                approved_at TEXT,
                justificativa_path TEXT,
                FOREIGN KEY(funcionario_id) REFERENCES funcionarios(id) ON DELETE SET NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS jornadas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                funcionario_id INTEGER,
                tipo TEXT,
                carga_diaria_min INTEGER,
                hora_entrada_padrao TEXT,
                hora_saida_padrao TEXT,
                inicio_data TEXT,
                allowed_lat REAL,
                allowed_lng REAL,
                allowed_radius_m INTEGER,
                numero TEXT,
                descricao TEXT,
                horario_json TEXT,
                FOREIGN KEY(funcionario_id) REFERENCES funcionarios(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS feriados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT UNIQUE,
                descricao TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS departamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT UNIQUE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS banco_horas_mov (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                funcionario_id INTEGER,
                data TEXT,
                horas REAL,
                motivo TEXT,
                created_at TEXT,
                FOREIGN KEY(funcionario_id) REFERENCES funcionarios(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS auditoria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                usuario TEXT,
                acao TEXT,
                dados TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS app_config (
                k TEXT PRIMARY KEY,
                v TEXT
            )
            """
        ]
        
        for sql in tables_sql:
            cursor.execute(sql)
        
        indexes_sql = [
            "CREATE INDEX IF NOT EXISTS idx_registros_cpf_data ON registros(cpf, data)",
            "CREATE INDEX IF NOT EXISTS idx_registros_func_data ON registros(funcionario_id, data)",
            "CREATE INDEX IF NOT EXISTS idx_ajustes_status ON ajustes(status)",
            "CREATE INDEX IF NOT EXISTS idx_feriados_data ON feriados(data)"
        ]
        
        for sql in indexes_sql:
            try:
                cursor.execute(sql)
            except sqlite3.Error:
                pass
        
        conn.commit()

    def _seed_defaults(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) as c FROM usuarios")
            row = cursor.fetchone()
            count = (row[0] if isinstance(row, tuple) else row["c"]) if row else 0
            if count == 0:
                pwd_hash = SecurityUtils.hash_password("admin")
                cursor.execute(
                    """
                    INSERT INTO usuarios (username, password_hash, role, funcionario_id, failed_attempts, require_2fa)
                    VALUES (?, ?, ?, NULL, 0, 0)
                    """,
                    ("admin", pwd_hash, "admin"),
                )
                conn.commit()
        except sqlite3.Error:
            pass
    
    def salvar_funcionario(self, funcionario: Funcionario) -> int:
        with self._connect() as conn:
            cursor = conn.cursor()
            data = funcionario.to_dict()
            
            if funcionario.id:
                cursor.execute(
                    """
                    UPDATE funcionarios SET nome=?, cpf=?, pis=?, cargo=?, departamento=?, carga_horaria_min=?,
                    email=?, hora_entrada=?, hora_saida=?, ativo=?, pin=? WHERE id=?
                    """,
                    (
                        data["nome"], data["cpf"], data["pis"], data["cargo"], data["departamento"], data["carga_horaria_min"],
                        data["email"], data["hora_entrada"], data["hora_saida"], data["ativo"], data["pin"], funcionario.id,
                    ),
                )
                return funcionario.id
            else:
                cursor.execute(
                    """
                    INSERT INTO funcionarios (nome, cpf, pis, cargo, departamento, carga_horaria_min,
                    email, hora_entrada, hora_saida, ativo, pin) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["nome"], data["cpf"], data["pis"], data["cargo"], data["departamento"], data["carga_horaria_min"],
                        data["email"], data["hora_entrada"], data["hora_saida"], data["ativo"], data["pin"],
                    ),
                )
                return cursor.lastrowid

    def obter_ajustes(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.cursor()
            
            query = (
                """
                SELECT a.*, f.nome as funcionario_nome 
                FROM ajustes a
                LEFT JOIN funcionarios f ON a.funcionario_id = f.id
                """
            )
            params = []
            
            if status:
                query += " WHERE a.status = ?"
                params.append(status)
            
            query += " ORDER BY a.created_at DESC"
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def adicionar_feriado(self, data: str, descricao: str) -> int:
        with self._connect() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO feriados (data, descricao) VALUES (?, ?)",
                    (data, descricao)
                )
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                # Feriado já existe nesta data
                return -1

    def remover_feriado(self, feriado_id: int) -> bool:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM feriados WHERE id=?", (feriado_id,))
            return cursor.rowcount > 0

    def obter_feriados(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM feriados ORDER BY data DESC")
            return [dict(row) for row in cursor.fetchall()]

    def verificar_feriado(self, data: str) -> Optional[str]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT descricao FROM feriados WHERE data=?", (data,))
            row = cursor.fetchone()
            return row["descricao"] if row else None

    def contar_abonados(self, data: str) -> int:
        with self._connect() as conn:
            cursor = conn.cursor()
            # Ajustes aprovados que justificam falta (Atestado, Folga, Abono)
            # Assumindo que tipos 'Atestado', 'Folga', 'Abono' contam como abonados
            cursor.execute(
                """
                SELECT COUNT(*) as c FROM ajustes 
                WHERE data=? AND status='APROVADO' 
                AND tipo IN ('Atestado', 'Folga', 'Abono', 'Feriado')
                """, 
                (data,)
            )
            row = cursor.fetchone()
            return row["c"] if row else 0

    def verificar_abono(self, funcionario_id: int, data: str) -> Optional[str]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT tipo FROM ajustes 
                WHERE funcionario_id=? AND data=? AND status='APROVADO'
                AND tipo IN ('Atestado', 'Folga', 'Abono', 'Feriado')
                """, 
                (funcionario_id, data)
            )
            row = cursor.fetchone()
            return row["tipo"] if row else None


    def atualizar_status_ajuste(self, ajuste_id: int, status: str, aprovado_por: Optional[str] = None) -> None:
        with self._connect() as conn:
            cursor = conn.cursor()
            
            # 1. Atualizar status do ajuste
            cursor.execute(
                """
                UPDATE ajustes 
                SET status = ?, approved_by = ?, approved_at = datetime('now')
                WHERE id = ?
                """,
                (status, aprovado_por, ajuste_id)
            )
            
            # 2. Se APROVADO, aplicar no registro de ponto (para tipos de horário)
            if status == "APROVADO":
                cursor.execute("SELECT * FROM ajustes WHERE id=?", (ajuste_id,))
                ajuste = cursor.fetchone()
                
                if ajuste:
                    tipo = ajuste["tipo"]
                    # Mapear tipo para coluna da tabela registros (case-insensitive)
                    coluna = None
                    t_upper = tipo.upper() if tipo else ""
                    
                    if t_upper == "ENTRADA": coluna = "hora_entrada"
                    elif t_upper in ["SAÍDA ALMOÇO", "SAIDA ALMOCO"]: coluna = "saida_almoco"
                    elif t_upper in ["RETORNO ALMOÇO", "RETORNO ALMOCO"]: coluna = "retorno_almoco"
                    elif t_upper in ["SAÍDA FINAL", "SAIDA FINAL", "SAIDA"]: coluna = "saida_final"
                    
                    if coluna:
                        func_id = ajuste["funcionario_id"]
                        data = ajuste["data"]
                        hora = ajuste["hora"]
                        cpf = ajuste["cpf"]
                        
                        # Verificar se já existe registro
                        cursor.execute(
                            "SELECT id FROM registros WHERE funcionario_id=? AND data=?", 
                            (func_id, data)
                        )
                        registro = cursor.fetchone()
                        
                        if registro:
                            # Atualizar existente
                            cursor.execute(f"UPDATE registros SET {coluna}=? WHERE id=?", (hora, registro["id"]))
                        else:
                            # Criar novo
                            cursor.execute(
                                f"INSERT INTO registros (funcionario_id, cpf, data, {coluna}) VALUES (?, ?, ?, ?)",
                                (func_id, cpf, data, hora)
                            )
            
            conn.commit()
    
    def obter_funcionarios(self, ativos_only: bool = True) -> List[Funcionario]:
        with self._connect() as conn:
            cursor = conn.cursor()
            if ativos_only:
                cursor.execute("SELECT * FROM funcionarios WHERE ativo=1 ORDER BY nome")
            else:
                cursor.execute("SELECT * FROM funcionarios ORDER BY nome")
            
            return [Funcionario.from_dict(dict(row)) for row in cursor.fetchall()]
    
    def obter_funcionario_por_id(self, func_id: int) -> Optional[Funcionario]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM funcionarios WHERE id=?", (func_id,))
            row = cursor.fetchone()
            return Funcionario.from_dict(dict(row)) if row else None
    
    def obter_funcionario_por_cpf(self, cpf: str) -> Optional[Funcionario]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM funcionarios WHERE cpf=?", (cpf,))
            row = cursor.fetchone()
            return Funcionario.from_dict(dict(row)) if row else None
            
    def obter_funcionario_por_pin(self, pin: str) -> Optional[Funcionario]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM funcionarios WHERE pin=?", (pin,))
            row = cursor.fetchone()
            return Funcionario.from_dict(dict(row)) if row else None
    
    def excluir_funcionario(self, func_id: int) -> bool:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM funcionarios WHERE id=?", (func_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def salvar_registro(self, registro: RegistroPonto) -> int:
        with self._connect() as conn:
            cursor = conn.cursor()
            
            if registro.id:
                # Portaria 671: Imutabilidade do registro original.
                # Em vez de UPDATE direto, devemos preservar o registro original?
                # A norma diz que o registro original (batida bruta) deve ser preservado.
                # Se estamos editando um registro existente, isso geralmente é uma "correção" ou "tratamento".
                # O correto seria ter uma tabela separada para o "tratamento" ou manter o histórico.
                # Como simplificação robusta, vamos impedir a alteração de campos chave de auditoria (ts, ts_device)
                # e garantir que qualquer edição seja logada na tabela de auditoria (já existe tabela auditoria).
                # Mas para garantir 100% de imutabilidade do DADO BRUTO, não deveríamos permitir UPDATE aqui
                # se isso altera a batida original capturada.
                # No entanto, a estrutura atual usa 'registros' tanto para o bruto quanto para o processado.
                # Vamos assumir que 'registros' contém o estado ATUAL do ponto.
                # Para cumprir "Imutabilidade", o INSERT inicial nunca deve ser deletado fisicamente.
                # O UPDATE aqui altera o estado consolidado do dia.
                
                # Vamos registrar a alteração na auditoria antes de aplicar
                cursor.execute("SELECT * FROM registros WHERE id=?", (registro.id,))
                original = cursor.fetchone()
                if original:
                    dados_antigos = dict(original)
                    self.registrar_auditoria(
                        conn, 
                        registro.ts or "SYSTEM", 
                        "SYSTEM", # Deveria ser o usuário logado
                        "UPDATE_REGISTRO", 
                        f"Alteração de ponto ID {registro.id}. Antes: {dados_antigos}"
                    )

                cursor.execute(
                    """
                    UPDATE registros SET hora_entrada=?, hora_saida=?, saida_almoco=?,
                    retorno_almoco=?, saida_final=?, tipo=?, 
                    gps_lat=?, gps_lng=?, foto_path=?, ip_addr=?,
                    antifraude_msg=?, extra_noturna_inicio=?, extra_noturna_fim=?
                    WHERE id=?
                    """,
                    (
                        registro.hora_entrada, registro.hora_saida, registro.saida_almoco,
                        registro.retorno_almoco, registro.saida_final, registro.tipo, 
                        registro.gps_lat,
                        registro.gps_lng, registro.foto_path, registro.ip_addr, registro.antifraude_msg,
                        registro.extra_noturna_inicio, registro.extra_noturna_fim, registro.id,
                    ),
                )
                return registro.id
            else:
                cursor.execute(
                    """
                    INSERT INTO registros (funcionario_id, cpf, data, hora_entrada, hora_saida,
                    saida_almoco, retorno_almoco, saida_final, ts, tipo, ts_device, ts_server,
                    device_id, gps_lat, gps_lng, foto_path, ip_addr, antifraude_msg,
                    extra_noturna_inicio, extra_noturna_fim)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        registro.funcionario_id, registro.cpf, registro.data, registro.hora_entrada,
                        registro.hora_saida, registro.saida_almoco, registro.retorno_almoco,
                        registro.saida_final, registro.ts, registro.tipo, registro.ts_device,
                        registro.ts_server, registro.device_id, registro.gps_lat, registro.gps_lng,
                        registro.foto_path, registro.ip_addr, registro.antifraude_msg,
                        registro.extra_noturna_inicio, registro.extra_noturna_fim,
                    ),
                )
                new_id = cursor.lastrowid
                
                # Registrar criação na auditoria para rastreabilidade completa
                self.registrar_auditoria(
                    conn,
                    registro.ts,
                    "SYSTEM",
                    "INSERT_REGISTRO",
                    f"Novo registro ID {new_id} criado para CPF {registro.cpf} Data {registro.data}"
                )
                
                return new_id

    def registrar_auditoria(self, conn: sqlite3.Connection, ts: str, usuario: str, acao: str, dados: str):
        try:
            conn.execute(
                "INSERT INTO auditoria (ts, usuario, acao, dados) VALUES (?, ?, ?, ?)",
                (ts, usuario, acao, dados)
            )
        except Exception as e:
            print(f"Erro ao salvar auditoria: {e}")

    
    def obter_auditoria(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM auditoria ORDER BY ts DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def obter_ajustes(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.cursor()
            
            query = (
                """
                SELECT a.*, f.nome as funcionario_nome 
                FROM ajustes a
                LEFT JOIN funcionarios f ON a.funcionario_id = f.id
                """
            )
            params = []
            
            if status:
                query += " WHERE a.status = ?"
                params.append(status)
            
            query += " ORDER BY a.created_at DESC"
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def atualizar_status_ajuste(self, ajuste_id: int, status: str, aprovado_por: Optional[str] = None) -> None:
        with self._connect() as conn:
            cursor = conn.cursor()
            aprovado_at = datetime.now().isoformat() if status == "APROVADO" else None
            
            cursor.execute(
                """
                UPDATE ajustes 
                SET status = ?, approved_by = ?, approved_at = ?
                WHERE id = ?
                """,
                (status, aprovado_por, aprovado_at, ajuste_id)
            )

    def obter_registros_por_periodo(self, data_inicio: str, data_fim: str, 
                                   funcionario_id: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.cursor()
            
            query = (
                """
                SELECT r.*, f.nome as funcionario_nome, f.carga_horaria_min 
                FROM registros r 
                LEFT JOIN funcionarios f ON r.funcionario_id = f.id 
                WHERE r.data BETWEEN ? AND ?
                """
            )
            params = [data_inicio, data_fim]
            
            if funcionario_id:
                query += " AND r.funcionario_id = ?"
                params.append(funcionario_id)
            
            query += " ORDER BY r.data ASC, r.hora_entrada ASC"
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def obter_registro_do_dia(self, cpf: str, data: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM registros WHERE cpf=? AND data=?
                """,
                (cpf, data),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def salvar_ajuste(self, dados: Dict[str, Any]) -> int:
        with self._connect() as conn:
            cursor = conn.cursor()
            
            # Buscar funcionário por CPF para obter o ID
            cursor.execute("SELECT id FROM funcionarios WHERE cpf=?", (dados.get("cpf"),))
            row = cursor.fetchone()
            func_id = row["id"] if row else None
            
            cursor.execute(
                """
                INSERT INTO ajustes (
                    funcionario_id, cpf, data, tipo, hora, observacao, 
                    status, created_at, justificativa_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
                """,
                (
                    func_id, dados.get("cpf"), dados.get("data"), dados.get("tipo"),
                    dados.get("hora"), dados.get("observacao"), "PENDENTE",
                    dados.get("justificativa_path")
                )
            )
            return cursor.lastrowid

    def obter_saldo_movimentos(self, funcionario_id: int, data_limite: str) -> float:
        """
        Retorna a soma das horas de banco_horas_mov para o funcionário até a data limite (exclusive).
        """
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT SUM(horas) as total FROM banco_horas_mov WHERE funcionario_id=? AND data < ?",
                (funcionario_id, data_limite)
            )
            row = cursor.fetchone()
            return row["total"] if row and row["total"] is not None else 0.0

    def criar_departamento(self, nome: str) -> int:
        with self._connect() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO departamentos (nome) VALUES (?)", (nome,))
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                return -1

    def obter_departamentos(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, nome FROM departamentos ORDER BY nome")
            return [dict(row) for row in cursor.fetchall()]

    def excluir_departamento(self, dep_id: int) -> bool:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM departamentos WHERE id=?", (dep_id,))
            return cursor.rowcount > 0

db_manager = DatabaseManager()
