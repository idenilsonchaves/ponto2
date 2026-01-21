from dataclasses import dataclass
from typing import Dict, Any, List, Optional

@dataclass
class DiaTrabalhoDTO:
    data: str
    horas_trabalhadas: float
    extras_50: float
    extras_100: float
    horas_noturnas: float
    atrasos: float
    faltas: int
    saldo_banco: float
    intrajornada_min: int
    interjornada_min: Optional[int]
    violacao_intrajornada: bool
    violacao_interjornada: bool
    observacao: str = ""

@dataclass
class RelatorioMensalDTO:
    funcionario_id: int
    funcionario_nome: str
    ano: int
    mes: int
    dias: List[DiaTrabalhoDTO]
    totais: Dict[str, float]

@dataclass
class DashboardDTO:
    presentes_hoje: int
    total_funcionarios: int
    presenca_mensal: List[Dict[str, Any]]
