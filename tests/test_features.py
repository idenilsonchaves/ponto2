
import sys
import os
import unittest
from datetime import date
import calendar

# Adicionar diretório raiz ao path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.reports import ReportService
from database.operations import DatabaseManager

class MockDB:
    def __init__(self):
        self.configs = {}

    def get_config(self, key, default):
        return self.configs.get(key, default)

class TestNewFeatures(unittest.TestCase):
    def setUp(self):
        self.db = MockDB()
        self.report_service = ReportService()
        # Injetar mock db no service (hacky mas funciona pra teste unitário rápido)
        self.report_service.db = self.db

    def test_periodo_fechamento_padrao(self):
        """Teste do padrão: Dia 1 ao Fim do Mês"""
        self.db.configs = {"dia_fechamento": "1", "tipo_fechamento": "MES_ANTERIOR"}
        
        # Maio 2024
        inicio, fim = self.report_service._obter_periodo_fechamento(2024, 5)
        self.assertEqual(inicio, date(2024, 5, 1))
        self.assertEqual(fim, date(2024, 5, 31))

    def test_periodo_fechamento_mes_anterior(self):
        """Teste Customizado: Dia 21 (Mes Anterior) a 20 (Mes Atual)"""
        self.db.configs = {"dia_fechamento": "21", "tipo_fechamento": "MES_ANTERIOR"}
        
        # Referência: Maio 2024
        # Esperado: 21/04 a 20/05
        inicio, fim = self.report_service._obter_periodo_fechamento(2024, 5)
        self.assertEqual(inicio, date(2024, 4, 21))
        self.assertEqual(fim, date(2024, 5, 20))

    def test_periodo_fechamento_proximo_mes(self):
        """Teste Customizado: Dia 21 (Mes Atual) a 20 (Proximo Mes)"""
        self.db.configs = {"dia_fechamento": "21", "tipo_fechamento": "PROXIMO_MES"}
        
        # Referência: Maio 2024
        # Esperado: 21/05 a 20/06
        inicio, fim = self.report_service._obter_periodo_fechamento(2024, 5)
        self.assertEqual(inicio, date(2024, 5, 21))
        self.assertEqual(fim, date(2024, 6, 20))

    def test_virada_ano_mes_anterior(self):
        """Teste Virada de Ano (Janeiro) - Mes Anterior"""
        self.db.configs = {"dia_fechamento": "26", "tipo_fechamento": "MES_ANTERIOR"}
        
        # Referência: Janeiro 2024
        # Esperado: 26/12/2023 a 25/01/2024
        inicio, fim = self.report_service._obter_periodo_fechamento(2024, 1)
        self.assertEqual(inicio, date(2023, 12, 26))
        self.assertEqual(fim, date(2024, 1, 25))

    def test_virada_ano_proximo_mes(self):
        """Teste Virada de Ano (Dezembro) - Proximo Mes"""
        self.db.configs = {"dia_fechamento": "26", "tipo_fechamento": "PROXIMO_MES"}
        
        # Referência: Dezembro 2023
        # Esperado: 26/12/2023 a 25/01/2024
        inicio, fim = self.report_service._obter_periodo_fechamento(2023, 12)
        self.assertEqual(inicio, date(2023, 12, 26))
        self.assertEqual(fim, date(2024, 1, 25))

if __name__ == '__main__':
    unittest.main()
