import os
import sys
import configparser
from pathlib import Path
from typing import Any

class Config:
    def __init__(self):
        self.base_dir = self._get_base_dir()
        self.config_path = os.path.join(self.base_dir, "config.ini")
        self.config = configparser.ConfigParser()
        self._load_config()
    
    def _get_base_dir(self) -> str:
        # No Android/Mobile, os arquivos empacotados ficam em locais read-only
        # Precisamos de um local writable para o banco de dados
        # O Flet geralmente expõe variáveis de ambiente ou podemos usar diretórios padrão
        if "ANDROID_ARGUMENT" in os.environ:
             # Tentativa simples de usar o diretório de dados do app no Android (ex: /data/data/com.example.app/files)
             # Mas como é Flet/Python, melhor usar um diretório seguro na home
             return os.environ.get("HOME", "/data/data/com.example.app/files")
        
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))
    
    def _load_config(self):
        self.config["DATABASE"] = {
            "path": os.path.join(self.base_dir, "database.db"),
            "backup_dir": os.path.join(self.base_dir, "backups")
        }
        
        self.config["UI"] = {
            "theme": "dark",
            "font_family": "Segoe UI",
            "font_size": "10"
        }
        
        self.config["EMAIL"] = {
            "smtp_host": "localhost",
            "smtp_port": "25",
            "smtp_user": "",
            "smtp_pass": "",
            "notify_enabled": "0"
        }
        
        self.config["SECURITY"] = {
            "use_2fa": "0",
            "max_login_attempts": "5",
            "lockout_minutes": "15"
        }
        
        self.config["APP"] = {
            "remember_user": "1",
            "last_user": "",
            "fechamento_dia": "21"
        }
        
        if os.path.exists(self.config_path):
            self.config.read(self.config_path, encoding="utf-8")
        db_path = self.config["DATABASE"].get("path", os.path.join(self.base_dir, "database.db"))
        if not os.path.isabs(db_path):
            db_path = os.path.join(self.base_dir, db_path)
        self.config["DATABASE"]["path"] = db_path
        backup_dir = self.config["DATABASE"].get("backup_dir", os.path.join(self.base_dir, "backups"))
        if not os.path.isabs(backup_dir):
            backup_dir = os.path.join(self.base_dir, backup_dir)
        self.config["DATABASE"]["backup_dir"] = backup_dir
    
    def save(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            self.config.write(f)
    
    def get(self, section: str, key: str, default: Any = None) -> Any:
        try:
            return self.config.get(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return default
    
    def set(self, section: str, key: str, value: Any):
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = str(value)

config = Config()
