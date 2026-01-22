import re
import hashlib
import binascii
import os
from typing import Optional
from pathlib import Path

class Validators:
    @staticmethod
    def validar_cpf(cpf: str) -> bool:
        cpf = ''.join(filter(str.isdigit, cpf))
        if len(cpf) != 11 or cpf == cpf[0] * 11:
            return False
        def calcular_digito(digs):
            soma = sum(int(d) * w for d, w in zip(digs, range(len(digs) + 1, 1, -1)))
            resto = (soma * 10) % 11
            return 0 if resto == 10 else resto
        d1 = calcular_digito(cpf[:9])
        d2 = calcular_digito(cpf[:10])
        return cpf[-2:] == f"{d1}{d2}"
    
    @staticmethod
    def validar_email(email: str) -> bool:
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    @staticmethod
    def formatar_cpf(cpf: str) -> str:
        cpf = ''.join(filter(str.isdigit, cpf))
        if len(cpf) == 11:
            return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
        return cpf

class SecurityUtils:
    @staticmethod
    def hash_password(password: str) -> str:
        salt = os.urandom(16)
        h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
        return binascii.hexlify(salt).decode() + "$" + binascii.hexlify(h).decode()
    
    @staticmethod
    def verify_password(password: str, stored_hash: str) -> bool:
        try:
            salt_hex, hash_hex = stored_hash.split("$")
            salt = binascii.unhexlify(salt_hex.encode())
            h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
            return binascii.hexlify(h).decode() == hash_hex
        except Exception:
            return False
    
    @staticmethod
    def gerar_codigo_2fa() -> str:
        import random
        return f"{random.randint(100000, 999999)}"

class FileUtils:
    @staticmethod
    def garantir_diretorios(base_dir: str):
        diretorios = ["logs", "relatorios", "backups", "fotos", "config"]
        for diretorio in diretorios:
            Path(os.path.join(base_dir, diretorio)).mkdir(parents=True, exist_ok=True)
    
    @staticmethod
    def obter_caminho_relatorio(nome: str, extensao: str = "pdf") -> str:
        from config.settings import config
        import datetime
        
        # Garantir que o diretório existe
        relatorios_dir = os.path.join(config.base_dir, "relatorios")
        os.makedirs(relatorios_dir, exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(relatorios_dir, f"{nome}_{timestamp}.{extensao}")
    
    @staticmethod
    def fazer_backup_automatico():
        from config.settings import config
        from database.operations import db_manager
        import datetime
        import shutil
        try:
            backup_dir = Path(config.get("DATABASE", "backup_dir"))
            backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"backup_{timestamp}.db"
            shutil.copy2(db_manager.db_path, backup_path)
            backups = sorted(backup_dir.glob("backup_*.db"), key=os.path.getmtime)
            for old_backup in backups[:-10]:
                old_backup.unlink()
        except Exception as e:
            print(f"Erro no backup automático: {e}")

class DateUtils:
    @staticmethod
    def obter_dias_uteis_mes(ano: int, mes: int) -> list:
        import calendar
        from datetime import date, timedelta
        dias_uteis = []
        data_inicio = date(ano, mes, 1)
        data_fim = date(ano, mes, calendar.monthrange(ano, mes)[1])
        data_atual = data_inicio
        while data_atual <= data_fim:
            if data_atual.weekday() < 5:
                dias_uteis.append(data_atual)
            data_atual += timedelta(days=1)
        return dias_uteis
    
    @staticmethod
    def formatar_data_brasil(data_str: Optional[str]) -> str:
        if not data_str:
            return ""
        from datetime import datetime
        try:
            data = datetime.strptime(data_str, "%Y-%m-%d")
            return data.strftime("%d/%m/%Y")
        except (ValueError, TypeError):
            return data_str
    
    @staticmethod
    def formatar_hora_brasil(hora_str: Optional[str]) -> str:
        if not hora_str:
            return ""
        from datetime import datetime
        try:
            hora = datetime.strptime(hora_str, "%H:%M:%S")
            return hora.strftime("%H:%M")
        except (ValueError, TypeError):
            return hora_str

class StringUtils:
    @staticmethod
    def truncar_texto(texto: str, max_length: int) -> str:
        if len(texto) <= max_length:
            return texto
        return texto[:max_length-3] + "..."
    
    @staticmethod
    def capitalizar_nome(nome: str) -> str:
        partes = nome.split()
        capitalizado = []
        for parte in partes:
            if parte.lower() in ['da', 'de', 'do', 'das', 'dos']:
                capitalizado.append(parte.lower())
            else:
                capitalizado.append(parte.capitalize())
        return ' '.join(capitalizado)
    
    @staticmethod
    def remover_acentos(texto: str) -> str:
        import unicodedata
        return ''.join(
            c for c in unicodedata.normalize('NFD', texto)
            if unicodedata.category(c) != 'Mn'
        )
