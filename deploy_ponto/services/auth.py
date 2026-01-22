import hashlib
import binascii
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple

from database.operations import db_manager

class AuthService:
    def __init__(self):
        self.current_user: Optional[Dict[str, Any]] = None
    
    def hash_password(self, password: str) -> str:
        salt = os.urandom(16)
        h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
        return binascii.hexlify(salt).decode() + "$" + binascii.hexlify(h).decode()
    
    def verify_password(self, password: str, stored_hash: str) -> bool:
        try:
            salt_hex, hash_hex = stored_hash.split("$")
            salt = binascii.unhexlify(salt_hex.encode())
            h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
            return binascii.hexlify(h).decode() == hash_hex
        except Exception:
            return False
    
    def login(self, username: str, password: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        with db_manager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM usuarios WHERE username=?", (username,))
            user_data = cursor.fetchone()
            
            if not user_data:
                cursor.execute("SELECT id FROM funcionarios WHERE cpf=?", (username,))
                func_data = cursor.fetchone()
                if func_data:
                    self.current_user = {
                        "username": username,
                        "role": "func",
                        "funcionario_id": func_data["id"]
                    }
                    return True, self.current_user
                return False, {"error": "Usuário ou senha inválidos"}
            
            user_dict = dict(user_data)
            
            if user_dict.get("lock_until"):
                try:
                    lock_until = datetime.strptime(user_dict["lock_until"], "%Y-%m-%d %H:%M:%S")
                    if datetime.now() < lock_until:
                        return False, {"error": "Conta bloqueada temporariamente"}
                except ValueError:
                    pass
            
            if self.verify_password(password, user_dict.get("password_hash", "")):
                cursor.execute("UPDATE usuarios SET failed_attempts=0, lock_until=NULL WHERE id=?", 
                             (user_dict["id"],))
                conn.commit()
                
                self.current_user = {
                    "username": user_dict["username"],
                    "role": user_dict["role"],
                    "funcionario_id": user_dict["funcionario_id"]
                }
                return True, self.current_user
            else:
                failed_attempts = (user_dict.get("failed_attempts") or 0) + 1
                max_attempts = 5
                lock_until = None
                
                if failed_attempts >= max_attempts:
                    lock_until = (datetime.now() + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
                    failed_attempts = 0
                
                cursor.execute("UPDATE usuarios SET failed_attempts=?, lock_until=? WHERE id=?", 
                             (failed_attempts, lock_until, user_dict["id"]))
                conn.commit()
                return False, {"error": "Usuário ou senha inválidos"}
    
    def logout(self):
        self.current_user = None
    
    def get_current_user(self) -> Optional[Dict[str, Any]]:
        return self.current_user
    
    def register_user(self, cpf: str, username: str, password: str, email: str) -> Tuple[bool, str]:
        """Registra um novo usuário vinculado a um funcionário existente"""
        
        # Limpar CPF (apenas números)
        cpf_clean = "".join(filter(str.isdigit, cpf))
        
        with db_manager._connect() as conn:
            cursor = conn.cursor()
            
            # 1. Verificar se funcionário existe
            cursor.execute("SELECT id, nome FROM funcionarios WHERE cpf=?", (cpf_clean,))
            func = cursor.fetchone()
            if not func:
                return False, "CPF não encontrado na base de funcionários."
                
            func_id = func["id"]
            
            # 2. Verificar se já tem usuário
            cursor.execute("SELECT id FROM usuarios WHERE funcionario_id=?", (func_id,))
            if cursor.fetchone():
                return False, "Este funcionário já possui cadastro."
                
            # 3. Verificar se username já existe
            cursor.execute("SELECT id FROM usuarios WHERE username=?", (username,))
            if cursor.fetchone():
                return False, "Nome de usuário já está em uso."
                
            # 4. Atualizar email do funcionário e criar usuário
            pwd_hash = self.hash_password(password)
            
            try:
                # Atualiza o email no cadastro do funcionário
                if email:
                    cursor.execute("UPDATE funcionarios SET email=? WHERE id=?", (email, func_id))
                
                cursor.execute(
                    """
                    INSERT INTO usuarios (username, password_hash, role, funcionario_id, failed_attempts, require_2fa)
                    VALUES (?, ?, ?, ?, 0, 0)
                    """,
                    (username, pwd_hash, role, func_id)
                )
                conn.commit()
                return True, "Cadastro realizado com sucesso!"
            except Exception as e:
                return False, f"Erro ao criar usuário: {str(e)}"

    def has_permission(self, permission: str) -> bool:
        if not self.current_user:
            return False
        
        role = self.current_user.get("role", "guest")
        
        permissions = {
            "admin": ["admin", "gerente", "func"],
            "gerente": ["gerente", "func"],
            "func": ["func"],
            "guest": ["guest"]
        }
        
        return role in permissions.get(permission, [])

auth_service = AuthService()
