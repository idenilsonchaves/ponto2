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
        # Verifica se há variável de ambiente do Flet para armazenamento (Mobile)
        if "FLET_APP_STORAGE_DATA" in os.environ:
            return os.environ["FLET_APP_STORAGE_DATA"]

        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
            
        # Se estiver rodando como script, o settings.py está em <root>/config/settings.py
        # Então o base_dir deve ser o pai do diretório atual
        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.dirname(current_dir)
        
        return base_dir
    
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
