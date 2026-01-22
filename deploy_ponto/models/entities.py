from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class Funcionario:
    id: Optional[int] = None
    nome: str = ""
    cpf: str = ""
    pis: str = ""  # Added PIS
    cargo: str = ""
    departamento: str = ""
    carga_horaria_min: int = 480
    email: str = ""
    hora_entrada: str = "08:00"
    hora_saida: str = "17:00"
    ativo: bool = True
    pin: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "nome": self.nome,
            "cpf": self.cpf,
            "pis": self.pis,
            "cargo": self.cargo,
            "departamento": self.departamento,
            "carga_horaria_min": self.carga_horaria_min,
            "email": self.email,
            "hora_entrada": self.hora_entrada,
            "hora_saida": self.hora_saida,
            "ativo": 1 if self.ativo else 0,
            "pin": self.pin
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Funcionario':
        return cls(
            id=data.get("id"),
            nome=data.get("nome", ""),
            cpf=data.get("cpf", ""),
            pis=data.get("pis", ""),
            cargo=data.get("cargo", ""),
            departamento=data.get("departamento", ""),
            carga_horaria_min=data.get("carga_horaria_min", 480),
            email=data.get("email", ""),
            hora_entrada=data.get("hora_entrada", "08:00"),
            hora_saida=data.get("hora_saida", "17:00"),
            ativo=bool(data.get("ativo", True)),
            pin=data.get("pin", "")
        )

@dataclass
class RegistroPonto:
    id: Optional[int] = None
    funcionario_id: Optional[int] = None
    cpf: str = ""
    data: str = ""
    hora_entrada: Optional[str] = None
    hora_saida: Optional[str] = None
    saida_almoco: Optional[str] = None
    retorno_almoco: Optional[str] = None
    saida_final: Optional[str] = None
    tipo: str = ""
    ts: str = ""
    ts_device: str = ""
    ts_server: str = ""
    device_id: str = ""
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None
    foto_path: Optional[str] = None
    ip_addr: Optional[str] = None
    antifraude_msg: Optional[str] = None
    extra_noturna_inicio: Optional[str] = None
    extra_noturna_fim: Optional[str] = None

@dataclass
class Usuario:
    id: Optional[int] = None
    username: str = ""
    password_hash: str = ""
    salt: str = ""
    role: str = "func"
    funcionario_id: Optional[int] = None
    failed_attempts: int = 0
    lock_until: Optional[str] = None
    require_2fa: bool = False

@dataclass
class Jornada:
    id: Optional[int] = None
    funcionario_id: Optional[int] = None
    tipo: str = "FIXO"
    carga_diaria_min: int = 480
    hora_entrada_padrao: str = "08:00"
    hora_saida_padrao: str = "17:00"
    inicio_data: str = ""
    allowed_lat: Optional[float] = None
    allowed_lng: Optional[float] = None
    allowed_radius_m: int = 0
    numero: Optional[str] = None
    descricao: Optional[str] = None
    horario_json: Optional[str] = None
