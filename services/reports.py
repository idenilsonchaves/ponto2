import calendar
import json
import sys
import os
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional

# Adicionar diretório raiz ao path se necessário
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)
# Tentar adicionar o diretório pai também (caso seja executado de services/)
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from database.operations import db_manager
from models.dto import DiaTrabalhoDTO, RelatorioMensalDTO
from utils.helpers import FileUtils
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

class ReportService:
    def __init__(self):
        self.db = db_manager
    
    def calcular_horas_dia(self, registro: Dict[str, Any]) -> float:
        def parse_time(hora_str: Optional[str]) -> Optional[datetime]:
            if not hora_str:
                return None
            try:
                return datetime.strptime(hora_str, "%H:%M:%S")
            except ValueError:
                return None
        
        entrada = parse_time(registro.get("hora_entrada"))
        saida_almoco = parse_time(registro.get("saida_almoco"))
        retorno_almoco = parse_time(registro.get("retorno_almoco"))
        saida_final = parse_time(registro.get("saida_final")) or parse_time(registro.get("hora_saida"))
        
        total = 0.0
        
        if entrada and saida_almoco and saida_almoco > entrada:
            total += (saida_almoco - entrada).total_seconds() / 3600
        
        if retorno_almoco and saida_final and saida_final > retorno_almoco:
            total += (saida_final - retorno_almoco).total_seconds() / 3600
        
        return max(0.0, total)
    
    def is_feriado(self, data_str: str) -> bool:
        with self.db._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM feriados WHERE data=?", (data_str,))
            return cursor.fetchone() is not None
    
    def get_jornada_funcionario(self, funcionario_id: int) -> Optional[Dict[str, Any]]:
        with self.db._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT tipo, carga_diaria_min, hora_entrada_padrao, hora_saida_padrao, 
                       inicio_data, horario_json 
                FROM jornadas WHERE funcionario_id=?
                """,
                (funcionario_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def is_dia_trabalho(self, funcionario_id: int, data_str: str) -> bool:
        try:
            data = datetime.strptime(data_str, "%Y-%m-%d").date()
        except ValueError:
            return True
        
        jornada = self.get_jornada_funcionario(funcionario_id)
        if not jornada:
            return data.weekday() < 5 and not self.is_feriado(data_str)
        
        if jornada.get("horario_json"):
            try:
                horarios = json.loads(jornada["horario_json"]) or {}
                dia_semana = str(data.weekday())
                horario_dia = horarios.get(dia_semana)
                if horario_dia:
                    return True
            except (json.JSONDecodeError, KeyError):
                pass
        
        tipo = (jornada.get("tipo", "FIXO") or "FIXO").upper()
        
        if tipo in ("FIXO", "5X2", "5x2"):
            return data.weekday() < 5 and not self.is_feriado(data_str)
        elif tipo in ("6X1", "6x1"):
            inicio = datetime.strptime(jornada["inicio_data"], "%Y-%m-%d").date() if jornada.get("inicio_data") else data
            delta = (data - inicio).days
            return (delta % 7) < 6 and not self.is_feriado(data_str)
        elif tipo == "12X36":
            inicio = datetime.strptime(jornada["inicio_data"], "%Y-%m-%d").date() if jornada.get("inicio_data") else data
            delta = (data - inicio).days
            return (delta % 2) == 0 and not self.is_feriado(data_str)
        
        return not self.is_feriado(data_str)
    
    def calcular_dia_detalhado(self, registro: Dict[str, Any], carga_min: int = 480, 
                             funcionario_id: Optional[int] = None) -> DiaTrabalhoDTO:
        horas_trabalhadas = self.calcular_horas_dia(registro)
        
        carga_requerida = carga_min
        if funcionario_id:
            jornada = self.get_jornada_funcionario(funcionario_id)
            if jornada and jornada.get("horario_json"):
                try:
                    data_reg = datetime.strptime(registro["data"], "%Y-%m-%d").date()
                    horarios = json.loads(jornada["horario_json"])
                    dia_semana = str(data_reg.weekday())
                    horario_dia = horarios.get(dia_semana)
                    if horario_dia:
                        def calc_carga_min(entrada: str, saida_almoco: str, retorno_almoco: str, saida_final: str) -> int:
                            try:
                                t_entrada = datetime.strptime(entrada, "%H:%M:%S")
                                t_saida_almoco = datetime.strptime(saida_almoco, "%H:%M:%S")
                                t_retorno_almoco = datetime.strptime(retorno_almoco, "%H:%M:%S")
                                t_saida_final = datetime.strptime(saida_final, "%H:%M:%S")
                                carga = 0
                                if t_saida_almoco > t_entrada:
                                    carga += int((t_saida_almoco - t_entrada).total_seconds() // 60)
                                if t_saida_final > t_retorno_almoco:
                                    carga += int((t_saida_final - t_retorno_almoco).total_seconds() // 60)
                                return carga
                            except (ValueError, TypeError):
                                return carga_min
                        carga_requerida = calc_carga_min(
                            horario_dia.get("entrada", "08:00:00"),
                            horario_dia.get("saida_almoco", "12:00:00"),
                            horario_dia.get("retorno_almoco", "13:00:00"),
                            horario_dia.get("saida_final", "17:00:00")
                        )
                except (json.JSONDecodeError, KeyError, ValueError):
                    pass
        
        dia_trabalho = True
        if funcionario_id:
            dia_trabalho = self.is_dia_trabalho(funcionario_id, registro.get("data", date.today().isoformat()))
        
        extras_50 = 0.0
        extras_100 = 0.0
        atrasos = 0.0
        faltas = 0
        
        if not dia_trabalho or self.is_feriado(registro.get("data", date.today().isoformat())):
            extras_100 = horas_trabalhadas
        else:
            if horas_trabalhadas > (carga_requerida / 60):
                extras_50 = min(horas_trabalhadas - (carga_requerida / 60), 2.0)
                extras_100 = max(0.0, horas_trabalhadas - (carga_requerida / 60) - 2.0)
            else:
                atrasos = (carga_requerida / 60) - horas_trabalhadas
            
            if not registro.get("hora_entrada") and not registro.get("saida_final") and not registro.get("hora_saida"):
                faltas = 1
        
        horas_noturnas = self.calcular_horas_noturnas(registro)
        
        # Adicionar o bônus da hora reduzida ao total trabalhado
        # Fator: (60 / 52.5) - 1 = 0.142857
        # Exemplo: 7h noturnas viram 8h (7 * 1.1428)
        # O calcular_horas_dia já retornou 7. Precisamos somar (7 * 0.1428)
        if horas_noturnas > 0:
            bonus_noturno = horas_noturnas * ((60 / 52.5) - 1)
            horas_trabalhadas += bonus_noturno

        saldo_banco = horas_trabalhadas - (carga_requerida / 60) if dia_trabalho and not self.is_feriado(registro.get("data", date.today().isoformat())) else horas_trabalhadas
        
        intrajornada_min = self.calcular_intrajornada(registro)
        interjornada_min = self.calcular_interjornada(funcionario_id, registro.get("data", date.today().isoformat())) if funcionario_id else None
        
        violacao_intrajornada = (intrajornada_min < 60) if horas_trabalhadas >= 6 and intrajornada_min else False
        violacao_interjornada = (interjornada_min is not None and interjornada_min < 11 * 60)
        
        observacao = ""
        data_str = registro.get("data", date.today().isoformat())
        
        nome_feriado = self.db.verificar_feriado(data_str)
        if nome_feriado:
            observacao = f"Feriado: {nome_feriado}"
            
        if funcionario_id:
            tipo_abono = self.db.verificar_abono(funcionario_id, data_str)
            if tipo_abono:
                observacao = tipo_abono
                
        if faltas > 0 and not observacao:
            observacao = "Falta"
        
        return DiaTrabalhoDTO(
            data=registro.get("data", date.today().isoformat()),
            horas_trabalhadas=horas_trabalhadas,
            extras_50=extras_50,
            extras_100=extras_100,
            horas_noturnas=horas_noturnas,
            atrasos=atrasos,
            faltas=faltas,
            saldo_banco=saldo_banco,
            intrajornada_min=intrajornada_min,
            interjornada_min=interjornada_min,
            violacao_intrajornada=violacao_intrajornada,
            violacao_interjornada=violacao_interjornada,
            observacao=observacao,
        )
    
    def calcular_horas_noturnas(self, registro: Dict[str, Any]) -> float:
        """
        Calcula horas noturnas (22:00 - 05:00) com fator de redução (52m30s).
        Fator: 60 / 52.5 = 1.142857
        """
        try:
            # Horários de referência
            ini_noite = datetime.strptime("22:00:00", "%H:%M:%S").time()
            fim_noite = datetime.strptime("05:00:00", "%H:%M:%S").time()
            
            # Converter strings do registro para datetime
            fmt = "%H:%M:%S"
            entrada = datetime.strptime(registro.get("hora_entrada", ""), fmt) if registro.get("hora_entrada") else None
            saida = datetime.strptime(registro.get("saida_final", "") or registro.get("hora_saida", ""), fmt) if (registro.get("saida_final") or registro.get("hora_saida")) else None
            
            # Se não tiver par completo, não calcula
            if not entrada or not saida:
                return 0.0
                
            # Ajustar datas (assumindo que saída pode ser no dia seguinte)
            # Se saída < entrada, assumimos dia seguinte
            dt_entrada = datetime.combine(datetime.today(), entrada.time())
            dt_saida = datetime.combine(datetime.today(), saida.time())
            if dt_saida < dt_entrada:
                dt_saida += timedelta(days=1)
                
            # Definir intervalo noturno para o dia da entrada e dia seguinte
            # Noite 1: 22h do dia da entrada até 05h do dia seguinte
            inicio_noturno = datetime.combine(dt_entrada.date(), ini_noite)
            fim_noturno = datetime.combine(dt_entrada.date() + timedelta(days=1), fim_noite)
            
            # Intersecção
            inicio_inter = max(dt_entrada, inicio_noturno)
            fim_inter = min(dt_saida, fim_noturno)
            
            horas_noturnas = 0.0
            
            if fim_inter > inicio_inter:
                delta = (fim_inter - inicio_inter).total_seconds() / 3600
                # Aplicar redução da hora noturna (1h relógio = 1h + 14.28% ou 52m30s)
                # Na prática, computa-se a hora cheia com acréscimo de 20% no valor, 
                # mas para banco de horas/contagem, usa-se a redução.
                # Aqui vamos retornar a quantidade de horas "fictícias" a mais geradas pela redução?
                # Ou apenas o total de horas trabalhadas em horário noturno?
                # Geralmente o sistema exibe "Horas Noturnas" como a quantidade de horas relógio feitas à noite
                # para depois aplicar o adicional de 20% na folha.
                # MAS a "Hora Reduzida" impacta na contagem de horas trabalhadas para o banco/extra.
                # Se trabalhou 7h à noite, conta como 8h trabalhadas.
                
                # Vamos retornar o valor JÁ COM A REDUÇÃO para somar no total?
                # O método calcular_horas_dia já soma o tempo linear.
                # Se quisermos adicionar o "bônus" da redução, retornamos apenas a diferença?
                # Não, o método chama separadamente.
                
                horas_noturnas = delta
            
            return horas_noturnas

        except (ValueError, TypeError):
            return 0.0
    
    def calcular_intrajornada(self, registro: Dict[str, Any]) -> int:
        saida_almoco = registro.get("saida_almoco")
        retorno_almoco = registro.get("retorno_almoco")
        
        if saida_almoco and retorno_almoco:
            try:
                t_saida = datetime.strptime(saida_almoco, "%H:%M:%S")
                t_retorno = datetime.strptime(retorno_almoco, "%H:%M:%S")
                return int((t_retorno - t_saida).total_seconds() // 60)
            except ValueError:
                pass
        return 0
    
    def calcular_interjornada(self, funcionario_id: int, data_str: str) -> Optional[int]:
        try:
            data = datetime.strptime(data_str, "%Y-%m-%d").date()
            data_anterior = data - timedelta(days=1)
            
            with self.db._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT saida_final, hora_saida FROM registros 
                    WHERE funcionario_id=? AND data=?
                    """,
                    (funcionario_id, data_anterior.isoformat()),
                )
                registro_anterior = cursor.fetchone()
                cursor.execute(
                    """
                    SELECT hora_entrada FROM registros 
                    WHERE funcionario_id=? AND data=?
                    """,
                    (funcionario_id, data_str),
                )
                registro_atual = cursor.fetchone()
            
            if not registro_anterior or not registro_atual:
                return None
            
            saida_anterior = registro_anterior["saida_final"] or registro_anterior["hora_saida"]
            entrada_atual = registro_atual["hora_entrada"]
            
            if not saida_anterior or not entrada_atual:
                return None
            
            try:
                t_saida = datetime.strptime(saida_anterior, "%H:%M:%S")
                t_entrada = datetime.strptime(entrada_atual, "%H:%M:%S")
                saida_datetime = datetime.combine(data_anterior, t_saida.time())
                entrada_datetime = datetime.combine(data, t_entrada.time())
                diferenca = entrada_datetime - saida_datetime
                return int(diferenca.total_seconds() // 60)
            except ValueError:
                return None
        except Exception:
            return None
    
    def _obter_periodo_fechamento(self, ano: int, mes: int):
        from config.settings import config
        dia_fechamento = int(config.get("APP", "fechamento_dia", "1"))
        
        if dia_fechamento == 1:
            # Período normal: 01/MM a FIM/MM
            data_inicio = date(ano, mes, 1)
            data_fim = date(ano, mes, calendar.monthrange(ano, mes)[1])
        else:
            # Período customizado: dia_fechamento/MêsAnterior a (dia_fechamento-1)/MesAtual
            # Ex: dia 21 -> 21/09 a 20/10
            
            # Data Fim = (dia_fechamento - 1) do mês atual
            # Se dia_fechamento for 21, data_fim = 20
            dia_fim_periodo = dia_fechamento - 1
            if dia_fim_periodo < 1:
                # Caso extremo, se config for 1, cai no if acima. Se for inválido, fallback
                dia_fim_periodo = 1
                
            try:
                data_fim = date(ano, mes, dia_fim_periodo)
            except ValueError:
                # Caso o dia não exista no mês (ex: 30 de Fev), ajusta para o último dia
                ultimo_dia_mes = calendar.monthrange(ano, mes)[1]
                data_fim = date(ano, mes, min(dia_fim_periodo, ultimo_dia_mes))
            
            # Data Início = dia_fechamento do mês anterior
            mes_anterior = mes - 1
            ano_anterior = ano
            if mes_anterior < 1:
                mes_anterior = 12
                ano_anterior = ano - 1
                
            try:
                data_inicio = date(ano_anterior, mes_anterior, dia_fechamento)
            except ValueError:
                # Caso o dia não exista no mês anterior
                ultimo_dia_mes_ant = calendar.monthrange(ano_anterior, mes_anterior)[1]
                data_inicio = date(ano_anterior, mes_anterior, min(dia_fechamento, ultimo_dia_mes_ant))
                
        return data_inicio, data_fim

    def gerar_relatorio_mensal(self, funcionario_id: int, ano: int, mes: int) -> RelatorioMensalDTO:
        data_inicio, data_fim = self._obter_periodo_fechamento(ano, mes)
        
        funcionario = db_manager.obter_funcionario_por_id(funcionario_id)
        if not funcionario:
            raise ValueError("Funcionário não encontrado")
        registros = db_manager.obter_registros_por_periodo(
            data_inicio.isoformat(), 
            data_fim.isoformat(), 
            funcionario_id,
        )
        dias = []
        totais = {
            "horas_trabalhadas": 0.0,
            "extras_50": 0.0,
            "extras_100": 0.0,
            "horas_noturnas": 0.0,
            "atrasos": 0.0,
            "faltas": 0,
            "saldo_banco": 0.0,
        }
        data_atual = data_inicio
        while data_atual <= data_fim:
            data_str = data_atual.isoformat()
            registro_dia = next((r for r in registros if r.get("data") == data_str), {"data": data_str})
            detalhes_dia = self.calcular_dia_detalhado(
                registro_dia, 
                funcionario.carga_horaria_min, 
                funcionario_id,
            )
            dias.append(detalhes_dia)
            totais["horas_trabalhadas"] += detalhes_dia.horas_trabalhadas
            totais["extras_50"] += detalhes_dia.extras_50
            totais["extras_100"] += detalhes_dia.extras_100
            totais["horas_noturnas"] += detalhes_dia.horas_noturnas
            totais["atrasos"] += detalhes_dia.atrasos
            totais["faltas"] += detalhes_dia.faltas
            totais["saldo_banco"] += detalhes_dia.saldo_banco
            data_atual += timedelta(days=1)
        return RelatorioMensalDTO(
            funcionario_id=funcionario_id,
            funcionario_nome=funcionario.nome,
            ano=ano,
            mes=mes,
            dias=dias,
            totais=totais,
        )

    def gerar_espelho_ponto_xlsx(self, funcionario_id: int, ano: int, mes: int) -> str:
        rel = self.gerar_relatorio_mensal(funcionario_id, ano, mes)
        data_inicio, data_fim = self._obter_periodo_fechamento(ano, mes)
        
        registros = db_manager.obter_registros_por_periodo(
            data_inicio.isoformat(),
            data_fim.isoformat(),
            funcionario_id,
        )
        reg_map = {r.get("data"): r for r in registros}
        wb = Workbook()
        ws = wb.active
        ws.title = "Espelho de Ponto"
        thin = Side(style="thin")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        ws["A1"] = "Espelho de Ponto"
        ws["A1"].font = Font(size=14, bold=True)
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=12)
        ws["A2"] = "Funcionário"
        ws["B2"] = rel.funcionario_nome
        ws["A3"] = "Período"
        ws["B3"] = f"{data_inicio.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')}"
        headers = [
            "Data", "Entrada", "Saída Almoço", "Retorno", "Saída Final",
            "Total (h)", "Extras 50", "Extras 100", "Atrasos", "Faltas", "Banco (h)", "Observação"
        ]
        for col, h in enumerate(headers, start=1):
            cell = ws.cell(row=5, column=col, value=h)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="EEEEEE", end_color="EEEEEE", fill_type="solid")
            cell.alignment = Alignment(horizontal="center")
            cell.border = border
        r = 6
        for dia in rel.dias:
            dstr = dia.data
            reg = reg_map.get(dstr, {})
            row_vals = [
                dstr,
                reg.get("hora_entrada") or "",
                reg.get("saida_almoco") or "",
                reg.get("retorno_almoco") or "",
                reg.get("saida_final") or reg.get("hora_saida") or "",
                round(dia.horas_trabalhadas, 2),
                round(dia.extras_50, 2),
                round(dia.extras_100, 2),
                round(dia.atrasos, 2),
                dia.faltas,
                round(dia.saldo_banco, 2),
                dia.observacao,
            ]
            for c, v in enumerate(row_vals, start=1):
                cell = ws.cell(row=r, column=c, value=v)
                cell.border = border
                if c == 1:
                    cell.alignment = Alignment(horizontal="center")
            r += 1
        ws.cell(row=r, column=1, value="Totais").font = Font(bold=True)
        ws.cell(row=r, column=6, value=round(rel.totais["horas_trabalhadas"], 2))
        ws.cell(row=r, column=7, value=round(rel.totais["extras_50"], 2))
        ws.cell(row=r, column=8, value=round(rel.totais["extras_100"], 2))
        ws.cell(row=r, column=9, value=round(rel.totais["atrasos"], 2))
        ws.cell(row=r, column=10, value=rel.totais["faltas"])
        ws.cell(row=r, column=11, value=round(rel.totais["saldo_banco"], 2))
        for i in range(1, 13):
            ws.column_dimensions[chr(64 + i)].width = 16
        path = FileUtils.obter_caminho_relatorio(
            f"espelho_{rel.funcionario_nome}_{ano}_{mes:02d}", "xlsx"
        )
        wb.save(path)
        return path

    def gerar_espelho_ponto_pdf(self, funcionario_id: int, ano: int, mes: int) -> str:
        if not REPORTLAB_AVAILABLE:
            raise ImportError("Biblioteca reportlab não instalada. PDF indisponível no momento.")

        rel = self.gerar_relatorio_mensal(funcionario_id, ano, mes)
        data_inicio, data_fim = self._obter_periodo_fechamento(ano, mes)
        
        registros = db_manager.obter_registros_por_periodo(
            data_inicio.isoformat(),
            data_fim.isoformat(),
            funcionario_id,
        )
        reg_map = {r.get("data"): r for r in registros}
        path = FileUtils.obter_caminho_relatorio(
            f"espelho_{rel.funcionario_nome}_{ano}_{mes:02d}", "pdf"
        )
        doc = SimpleDocTemplate(path, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
        styles = getSampleStyleSheet()
        
        # Estilos Customizados
        styles["Title"].textColor = colors.HexColor("#2c3e50")
        styles["Title"].fontSize = 16
        styles["Title"].alignment = 1 # Center
        styles["Heading2"].textColor = colors.HexColor("#34495e")
        styles["Heading2"].fontSize = 12
        styles["Heading2"].alignment = 1
        
        story = []
        
        # Cabeçalho da Empresa
        from config.settings import config
        empresa_razao = config.get("EMPRESA", "razao_social", "EMPRESA NÃO CONFIGURADA")
        story.append(Paragraph(empresa_razao, styles["Title"]))
        story.append(Spacer(1, 5))
        story.append(Paragraph("ESPELHO DE PONTO", styles["Heading2"]))
        story.append(Spacer(1, 15))
        
        # Dados do Funcionário
        func = db_manager.obter_funcionario_por_id(funcionario_id)
        cpf = func.cpf if func else ""
        
        carga_str = "08:00"
        if func:
            h = func.carga_horaria_min // 60
            m = func.carga_horaria_min % 60
            carga_str = f"{h:02d}:{m:02d}"

        # Tabela de Info
        info_data = [
            ["Funcionário:", rel.funcionario_nome, "CPF:", cpf],
            ["Departamento:", func.departamento if func else "", "Cargo:", func.cargo if func else ""],
            ["Período:", f"{data_inicio.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')}", "Carga Horária:", carga_str]
        ]
        
        info_table = Table(info_data, colWidths=[80, 200, 60, 150])
        info_table.setStyle(TableStyle([
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('TEXTCOLOR', (0,0), (-1,-1), colors.HexColor("#2c3e50")),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 15))

        # Tabela de Registros
        headers = [
            "Data", "Entrada", "Saída 1", "Entrada 2", "Saída",
            "Total", "Noturna", "Ext 50", "Ext 100", "Atrasos", "Faltas", "Banco", "Obs"
        ]
        data_rows = [headers]
        
        from utils.helpers import DateUtils
        
        for dia in rel.dias:
            dstr = dia.data
            reg = reg_map.get(dstr, {})
            fmt = DateUtils.formatar_hora_brasil
            
            row = [
                DateUtils.formatar_data_brasil(dstr),
                fmt(reg.get("hora_entrada")),
                fmt(reg.get("saida_almoco")),
                fmt(reg.get("retorno_almoco")),
                fmt(reg.get("saida_final") or reg.get("hora_saida")),
                f"{dia.horas_trabalhadas:.2f}",
                f"{dia.horas_noturnas:.2f}",
                f"{dia.extras_50:.2f}",
                f"{dia.extras_100:.2f}",
                f"{dia.atrasos:.2f}",
                str(dia.faltas),
                f"{dia.saldo_banco:+.2f}",
                dia.observacao[:15] # Limitar tamanho para caber
            ]
            data_rows.append(row)

        # Largura das colunas (total ~555pt para A4 com margens 20)
        # 13 colunas
        col_widths = [50, 35, 35, 35, 35, 35, 35, 35, 35, 35, 30, 40, 80]
        
        table = Table(data_rows, colWidths=col_widths, repeatRows=1)
        
        # Estilo da Tabela
        tbl_style = [
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#2c3e50")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 8),
            ('FONTSIZE', (0,1), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#e0e0e0")),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#f8f9fa")]),
        ]
        
        # Colorir finais de semana e feriados
        for i, dia in enumerate(rel.dias, start=1):
            dstr = dia.data
            try:
                dt = datetime.strptime(dstr, "%Y-%m-%d").date()
                if self.is_feriado(dstr):
                     tbl_style.append(('BACKGROUND', (0,i), (-1,i), colors.HexColor("#fef2f2")))
                     tbl_style.append(('TEXTCOLOR', (0,i), (-1,i), colors.HexColor("#c0392b")))
                elif dt.weekday() >= 5:
                     tbl_style.append(('BACKGROUND', (0,i), (-1,i), colors.HexColor("#fdfbf7")))
                     tbl_style.append(('TEXTCOLOR', (0,i), (-1,i), colors.HexColor("#b7950b")))
            except:
                pass
                
        table.setStyle(TableStyle(tbl_style))
        story.append(table)
        story.append(Spacer(1, 12))
        
        # Totais
        totais_data = [
            ["TOTAIS", "", "", "", "", 
             f"{rel.totais['horas_trabalhadas']:.2f}", 
             f"{rel.totais['horas_noturnas']:.2f}",
             f"{rel.totais['extras_50']:.2f}",
             f"{rel.totais['extras_100']:.2f}",
             f"{rel.totais['atrasos']:.2f}",
             str(rel.totais['faltas']),
             f"{rel.totais['saldo_banco']:+.2f}",
             ""]
        ]
        totais_table = Table(totais_data, colWidths=col_widths)
        totais_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#e9ecef")),
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#bdc3c7")),
            ('SPAN', (0,0), (4,0)), # Mesclar primeiras colunas
            ('ALIGN', (0,0), (0,0), 'RIGHT'),
        ]))
        story.append(totais_table)
        story.append(Spacer(1, 20))
        
        # Resumo Banco
        saldo_anterior = self.calcular_saldo_acumulado(funcionario_id, data_inicio)
        saldo_periodo = rel.totais["saldo_banco"]
        saldo_atual = saldo_anterior + saldo_periodo
        
        resumo_data = [
            ["RESUMO BANCO DE HORAS", ""],
            ["Saldo Anterior:", f"{saldo_anterior:+.2f}"],
            ["Saldo Período:", f"{saldo_periodo:+.2f}"],
            ["SALDO ATUAL:", f"{saldo_atual:+.2f}"]
        ]
        
        resumo_table = Table(resumo_data, colWidths=[150, 100], hAlign='LEFT')
        resumo_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (1,0), colors.HexColor("#2c3e50")),
            ('TEXTCOLOR', (0,0), (1,0), colors.white),
            ('FONTNAME', (0,0), (1,0), 'Helvetica-Bold'),
            ('FONTNAME', (0,3), (1,3), 'Helvetica-Bold'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#bdc3c7")),
            ('ALIGN', (1,0), (1,-1), 'RIGHT'),
            ('BACKGROUND', (0,3), (1,3), colors.HexColor("#f8f9fa")),
        ]))
        story.append(resumo_table)
        
        story.append(Spacer(1, 40))
        
        # Assinaturas
        sig_data = [
            ["___________________________", "___________________________"],
            ["Assinatura do Empregador", "Assinatura do Funcionário"]
        ]
        sig_table = Table(sig_data, colWidths=[250, 250])
        sig_table.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('TEXTCOLOR', (0,0), (-1,-1), colors.HexColor("#666666")),
        ]))
        story.append(sig_table)
        
        doc.build(story)
        return path

    def calcular_saldo_acumulado(self, funcionario_id: int, data_limite: date) -> float:
        """
        Calcula o saldo acumulado de banco de horas desde o início até o dia anterior a data_limite.
        """
        # Encontrar a data do primeiro registro
        with self.db._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT MIN(data) as primeira_data FROM registros WHERE funcionario_id=?", 
                (funcionario_id,)
            )
            row = cursor.fetchone()
            if not row or not row["primeira_data"]:
                return 0.0
            primeira_data_str = row["primeira_data"]
        
        primeira_data = datetime.strptime(primeira_data_str, "%Y-%m-%d").date()
        
        # Iterar mês a mês até o mês anterior ao data_limite
        # Se data_limite é 01/05/2024, calculamos até 30/04/2024
        
        saldo_total = 0.0
        
        # Iterar do primeiro dia do mês da primeira data até o mês anterior à data_limite
        curr_year = primeira_data.year
        curr_month = primeira_data.month
        
        limit_year = data_limite.year
        limit_month = data_limite.month
        
        # Enquanto (curr_year, curr_month) < (limit_year, limit_month)
        while (curr_year < limit_year) or (curr_year == limit_year and curr_month < limit_month):
            rel = self.gerar_relatorio_mensal(funcionario_id, curr_year, curr_month)
            saldo_total += rel.totais["saldo_banco"]
            
            # Próximo mês
            curr_month += 1
            if curr_month > 12:
                curr_month = 1
                curr_year += 1
                
        # Adicionar saldo de movimentos manuais (banco_horas_mov) se houver
        saldo_movimentos = self.db.obter_saldo_movimentos(funcionario_id, data_limite.isoformat())
        saldo_total += saldo_movimentos
        
        return saldo_total

    def gerar_espelho_ponto_html(self, funcionario_id: int, ano: int, mes: int) -> str:
        rel = self.gerar_relatorio_mensal(funcionario_id, ano, mes)
        data_inicio, data_fim = self._obter_periodo_fechamento(ano, mes)
        
        registros = db_manager.obter_registros_por_periodo(
            data_inicio.isoformat(),
            data_fim.isoformat(),
            funcionario_id,
        )
        reg_map = {r.get("data"): r for r in registros}
        funcionario = db_manager.obter_funcionario_por_id(funcionario_id)
        cpf = funcionario.cpf if funcionario else ""
        pis = funcionario.pis if funcionario else ""
        cargo = funcionario.cargo if funcionario else ""
        departamento = funcionario.departamento if funcionario else ""
        
        carga_str = "08:00"
        if funcionario:
            h = funcionario.carga_horaria_min // 60
            m = funcionario.carga_horaria_min % 60
            carga_str = f"{h:02d}:{m:02d}"

        # Dados da Empresa
        from config.settings import config
        empresa_razao = config.get("EMPRESA", "razao_social", "EMPRESA NÃO CONFIGURADA")
        empresa_cnpj = config.get("EMPRESA", "cnpj", "")
        empresa_endereco = config.get("EMPRESA", "endereco", "")
        
        path = FileUtils.obter_caminho_relatorio(
            f"espelho_{rel.funcionario_nome}_{ano}_{mes:02d}", "html"
        )
        
        css = """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
            :root {
                --primary: #2c3e50;
                --secondary: #34495e;
                --accent: #3498db;
                --success: #27ae60;
                --danger: #e74c3c;
                --warning: #f39c12;
                --light: #f8f9fa;
                --border: #e9ecef;
            }
            body { 
                font-family: 'Inter', system-ui, -apple-system, sans-serif; 
                margin: 0; 
                padding: 40px; 
                background: #f0f2f5; 
                color: #1a1a1a;
                -webkit-print-color-adjust: exact;
                line-height: 1.5;
            }
            .container { 
                background: white; 
                padding: 50px; 
                border-radius: 12px; 
                box-shadow: 0 10px 30px rgba(0,0,0,0.05);
                max-width: 1100px; 
                margin: 0 auto; 
            }
            .header { 
                display: flex; 
                justify-content: space-between; 
                align-items: flex-start; 
                border-bottom: 2px solid var(--border); 
                padding-bottom: 30px; 
                margin-bottom: 40px;
            }
            .header-logo {
                font-size: 24px;
                font-weight: 800;
                color: var(--primary);
                text-transform: uppercase;
                letter-spacing: -0.5px;
                margin-bottom: 8px;
            }
            .company-info {
                font-size: 13px;
                color: #666;
                margin-bottom: 2px;
            }
            .header-title h1 {
                margin: 0;
                font-size: 32px;
                color: var(--primary);
                font-weight: 700;
                letter-spacing: -1px;
            }
            .header-title p {
                margin: 5px 0 0;
                color: #666;
                font-size: 15px;
                text-align: right;
            }
            
            .info-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 25px;
                background: #f8f9fa;
                padding: 25px;
                border-radius: 10px;
                margin-bottom: 40px;
                border: 1px solid var(--border);
            }
            .info-item {
                display: flex;
                flex-direction: column;
            }
            .info-label {
                font-size: 11px;
                color: #7f8c8d;
                text-transform: uppercase;
                margin-bottom: 6px;
                font-weight: 600;
                letter-spacing: 0.5px;
            }
            .info-value {
                font-size: 15px;
                font-weight: 600;
                color: var(--primary);
            }
            
            table { 
                width: 100%; 
                border-collapse: separate;
                border-spacing: 0;
                margin-bottom: 40px; 
                font-size: 13px;
                background: white;
            }
            th { 
                background: var(--light); 
                color: var(--secondary); 
                padding: 15px 10px; 
                text-align: center; 
                font-weight: 600;
                border-bottom: 2px solid #dee2e6;
                text-transform: uppercase;
                font-size: 11px;
                letter-spacing: 0.5px;
            }
            td { 
                border-bottom: 1px solid var(--border); 
                padding: 12px 10px; 
                text-align: center; 
                color: #444;
            }
            tr:last-child td { border-bottom: none; }
            tr:hover td { background-color: #f8f9fa; }
            
            .weekend td { background-color: #fdfbf7; color: #b7950b; }
            .feriado td { background-color: #fef2f2; color: #c0392b; }
            
            tfoot tr td { 
                background: var(--light); 
                font-weight: 700; 
                border-top: 2px solid #dee2e6;
                color: var(--primary);
                padding: 15px 10px;
                font-size: 14px;
            }
            
            .summary-container {
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                margin-top: 40px;
                gap: 40px;
            }
            .notes-section {
                flex: 1;
            }
            .notes-box {
                border: 1px solid var(--border);
                border-radius: 8px;
                height: 100px;
                background: #fdfdfd;
            }
            
            .summary-box {
                width: 350px;
                border: 1px solid var(--border);
                border-radius: 10px;
                overflow: hidden;
                box-shadow: 0 2px 10px rgba(0,0,0,0.02);
            }
            .summary-header {
                background: var(--primary);
                color: white;
                padding: 15px;
                text-align: center;
                font-weight: 600;
                font-size: 14px;
                letter-spacing: 0.5px;
                text-transform: uppercase;
            }
            .summary-row {
                display: flex;
                justify-content: space-between;
                padding: 15px 20px;
                border-bottom: 1px solid var(--border);
                font-size: 14px;
            }
            .summary-row:last-child { border-bottom: none; }
            .summary-label { color: #666; }
            .summary-value { font-weight: 700; font-family: 'Inter', monospace; }
            
            .footer {
                margin-top: 80px;
                display: flex;
                justify-content: space-between;
                padding-top: 30px;
                border-top: 1px solid var(--border);
            }
            .signature-box {
                width: 40%;
                text-align: center;
            }
            .signature-line {
                border-top: 1px solid #000;
                margin-bottom: 12px;
                width: 100%;
            }
            .signature-text {
                font-size: 13px;
                font-weight: 500;
                color: var(--primary);
                text-transform: uppercase;
            }
            
            .print-btn {
                position: fixed;
                top: 30px;
                right: 30px;
                background: var(--accent);
                color: white;
                border: none;
                padding: 12px 25px;
                border-radius: 50px;
                cursor: pointer;
                font-weight: 600;
                box-shadow: 0 4px 15px rgba(52, 152, 219, 0.3);
                transition: all 0.2s;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            .print-btn:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(52, 152, 219, 0.4); }
            
            @media print {
                body { background: white; padding: 0; }
                .container { box-shadow: none; padding: 0; max-width: 100%; border-radius: 0; }
                .print-btn { display: none; }
                .weekend td { background-color: #fdfbf7 !important; -webkit-print-color-adjust: exact; }
                .feriado td { background-color: #fef2f2 !important; -webkit-print-color-adjust: exact; }
                th { background-color: #f8f9fa !important; color: black !important; -webkit-print-color-adjust: exact; }
                .summary-header { background: #2c3e50 !important; color: white !important; -webkit-print-color-adjust: exact; }
            }
            
            /* Utility classes for values */
            .val-pos { color: var(--success); }
            .val-neg { color: var(--danger); }
            .val-neutral { color: var(--secondary); }
        </style>
        """
        
        rows = ""
        from utils.helpers import DateUtils
        
        for dia in rel.dias:
            dstr = dia.data
            reg = reg_map.get(dstr, {})
            
            # Formatação
            fmt = DateUtils.formatar_hora_brasil
            
            # Determinar classe CSS para fim de semana ou feriado
            try:
                dt = datetime.strptime(dstr, "%Y-%m-%d").date()
                css_class = ""
                if self.is_feriado(dstr):
                    css_class = "feriado"
                elif dt.weekday() >= 5:
                    css_class = "weekend"
            except:
                css_class = ""
            
            rows += f"""
            <tr class='{css_class}'>
                <td style='text-align: left; padding-left: 15px; font-weight: 500;'>{DateUtils.formatar_data_brasil(dstr)}</td>
                <td>{fmt(reg.get('hora_entrada'))}</td>
                <td>{fmt(reg.get('saida_almoco'))}</td>
                <td>{fmt(reg.get('retorno_almoco'))}</td>
                <td>{fmt(reg.get('saida_final') or reg.get('hora_saida'))}</td>
                <td style='font-weight: 600;'>{dia.horas_trabalhadas:.2f}</td>
                <td style='color: #666;'>{dia.horas_noturnas:.2f}</td>
                <td style='color: #666;'>{dia.extras_50:.2f}</td>
                <td style='color: #666;'>{dia.extras_100:.2f}</td>
                <td style='color: var(--danger); font-weight: 500;'>{dia.atrasos:.2f}</td>
                <td style='color: { "var(--danger)" if dia.faltas else "#ccc" }; font-weight: 700;'>{dia.faltas}</td>
                <td style='font-weight: 700; color: { "var(--success)" if dia.saldo_banco >= 0 else "var(--danger)" };'>{dia.saldo_banco:+.2f}</td>
                <td style='font-size: 11px; color: #555; text-align: left;'>{dia.observacao}</td>
            </tr>
            """
        
        # Calcular Resumo Banco de Horas
        saldo_anterior = self.calcular_saldo_acumulado(funcionario_id, data_inicio)
        
        # O saldo do período já está calculado no relatório mensal (saldo_banco total)
        saldo_periodo = rel.totais["saldo_banco"]
        saldo_atual = saldo_anterior + saldo_periodo
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Espelho de Ponto - {rel.funcionario_nome}</title>
            {css}
        </head>
        <body>
            <button class="print-btn" onclick="window.print()">🖨️ IMPRIMIR / PDF</button>
            
            <div class="container">
                <div class="header">
                    <div class="header-left">
                        <div class="header-logo">{empresa_razao}</div>
                        <div class="company-info">{empresa_cnpj}</div>
                        <div class="company-info">{empresa_endereco}</div>
                    </div>
                    <div class="header-title">
                        <h1>Espelho de Ponto</h1>
                        <p>Período: {data_inicio.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')}</p>
                    </div>
                </div>
                
                <div class="info-grid">
                    <div class="info-item">
                        <span class="info-label">Funcionário</span>
                        <span class="info-value">{rel.funcionario_nome}</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">CPF</span>
                        <span class="info-value">{cpf}</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">PIS</span>
                        <span class="info-value">{pis}</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">Departamento</span>
                        <span class="info-value">{departamento}</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">Cargo</span>
                        <span class="info-value">{cargo}</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">Carga Horária</span>
                        <span class="info-value">{carga_str}</span>
                    </div>
                </div>
                
                <table>
                <thead>
                    <tr>
                        <th style='text-align: left; padding-left: 15px;'>Data</th>
                        <th>Entrada</th>
                        <th>Saída Almoço</th>
                        <th>Retorno</th>
                        <th>Saída</th>
                        <th>Total</th>
                        <th>Noturna</th>
                        <th>Ext 50%</th>
                        <th>Ext 100%</th>
                        <th>Atrasos</th>
                        <th>Faltas</th>
                        <th>Banco</th>
                        <th>Observação</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
                <tfoot>
                    <tr>
                        <td colspan='5' style='text-align: right; padding-right: 20px;'>TOTAIS DO PERÍODO</td>
                        <td>{rel.totais['horas_trabalhadas']:.2f}</td>
                        <td>{rel.totais['horas_noturnas']:.2f}</td>
                        <td>{rel.totais['extras_50']:.2f}</td>
                        <td>{rel.totais['extras_100']:.2f}</td>
                        <td>{rel.totais['atrasos']:.2f}</td>
                        <td>{rel.totais['faltas']}</td>
                        <td style='color: { "var(--success)" if rel.totais["saldo_banco"] >= 0 else "var(--danger)" };'>{rel.totais['saldo_banco']:+.2f}</td>
                        <td></td>
                    </tr>
                </tfoot>
            </table>
            
            <div class="summary-container">
                <div class="notes-section">
                    <p style='font-size: 12px; color: #666; margin-bottom: 8px; font-weight: 600; text-transform: uppercase;'>Observações</p>
                    <div class="notes-box"></div>
                </div>
                
                <div class='summary-box'>
                    <div class='summary-header'>Resumo do Banco de Horas</div>
                    <div class='summary-row'>
                        <span class='summary-label'>Saldo Anterior</span>
                        <span class='summary-value' style='color: { "var(--success)" if saldo_anterior >= 0 else "var(--danger)" };'>{saldo_anterior:+.2f}</span>
                    </div>
                    <div class='summary-row'>
                        <span class='summary-label'>Saldo do Período</span>
                        <span class='summary-value' style='color: { "var(--success)" if saldo_periodo >= 0 else "var(--danger)" };'>{saldo_periodo:+.2f}</span>
                    </div>
                    <div class='summary-row' style='background: #f8f9fa;'>
                        <span class='summary-label' style='font-weight: 700; color: var(--primary);'>SALDO ATUAL</span>
                        <span class='summary-value' style='color: { "var(--success)" if saldo_atual >= 0 else "var(--danger)" }; font-size: 16px;'>{saldo_atual:+.2f}</span>
                    </div>
                </div>
            </div>
            
            <div class='footer'>
                <div class='signature-box'>
                    <div class='signature-line'></div>
                    <div class='signature-text'>Assinatura do Empregador</div>
                </div>
                <div class='signature-box'>
                    <div class='signature-line'></div>
                    <div class='signature-text'>Assinatura do Funcionário</div>
                    <div style='font-size: 10px; color: #999; margin-top: 5px;'>Reconheço a exatidão das informações acima</div>
                </div>
            </div>
            
            <div style='text-align: center; margin-top: 40px; font-size: 11px; color: #b0b0b0;'>
                Documento gerado eletronicamente em {datetime.now().strftime("%d/%m/%Y às %H:%M:%S")} • Sistema Ponto.NET
                <br>Conforme Portaria 671/2021
            </div>
        </div>
        </body>
        </html>
        """
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
            
        return path

    def gerar_arquivo_afd(self) -> str:
        """
        Gera o Arquivo Fonte de Dados (AFD) conforme Portaria 671/1510.
        Considera todos os registros do banco.
        """
        with self.db._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT r.*, f.pis 
                FROM registros r
                LEFT JOIN funcionarios f ON r.funcionario_id = f.id
                ORDER BY r.data ASC, r.hora_entrada ASC
            """)
            registros = cursor.fetchall()
            
        if not registros:
            return ""

        # Dados da Empresa (Placeholder ou Config)
        cnpj = config.get("EMPRESA", "cnpj", "00000000000000").replace(".", "").replace("/", "").replace("-", "")
        razao = config.get("EMPRESA", "razao_social", "EMPRESA PADRAO LTDA")[:150]
        rep_num = config.get("EMPRESA", "rep_num", "00000000000000000")
        
        lines = []
        nsr_counter = 1
        
        # Datas do arquivo
        min_date_str = registros[0]["data"]
        max_date_str = registros[-1]["data"]
        min_date = datetime.strptime(min_date_str, "%Y-%m-%d").strftime("%d%m%Y")
        max_date = datetime.strptime(max_date_str, "%Y-%m-%d").strftime("%d%m%Y")
        
        now = datetime.now()
        gen_date = now.strftime("%d%m%Y")
        gen_time = now.strftime("%H%M")
        
        # Cabeçalho (Tipo 1)
        # 000000000(9) 1(1) 1(1) CNPJ(14) CEI(12) RAZAO(150) REP(17) DATA_INI(8) DATA_FIM(8) DATA_GER(8) HORA_GER(4)
        header = f"00000000011{cnpj:<14}{'':<12}{razao:<150}{rep_num:<17}{min_date}{max_date}{gen_date}{gen_time}"
        lines.append(header)
        
        type_3_count = 0
        
        for r in registros:
            pis = (r["pis"] or "").replace(".", "").replace("-", "")
            if not pis or len(pis) < 11:
                pis = "00000000000" # Placeholder PIS inválido
            pis = pis.ljust(12) # PIS deve ter 12 dígitos (com dígito verificador?) O campo é 12.
            
            data_dma = datetime.strptime(r["data"], "%Y-%m-%d").strftime("%d%m%Y")
            
            # Decompor registro diário em marcacoes
            # Ordem: Entrada, Saida Almoco, Retorno Almoco, Saida Final
            times = []
            if r["hora_entrada"]: times.append(r["hora_entrada"])
            if r["saida_almoco"]: times.append(r["saida_almoco"])
            if r["retorno_almoco"]: times.append(r["retorno_almoco"])
            if r["saida_final"]: times.append(r["saida_final"])
            elif r["hora_saida"]: times.append(r["hora_saida"])
            
            # Ordenar horários
            times.sort()
            
            for t in times:
                try:
                    hm = datetime.strptime(t, "%H:%M:%S").strftime("%H%M")
                    nsr_str = f"{nsr_counter:09d}"
                    # Detalhe (Tipo 3)
                    # NSR(9) 3(1) DATA(8) HORA(4) PIS(12)
                    line = f"{nsr_str}3{data_dma}{hm}{pis[:12]}" 
                    lines.append(line)
                    nsr_counter += 1
                    type_3_count += 1
                except:
                    pass
        
        # Trailer (Tipo 9)
        # 999999999(9) 9(1) QTD_2(9) QTD_3(9) QTD_4(9) QTD_5(9)
        trailer = f"9999999999{0:09d}{type_3_count:09d}{0:09d}{0:09d}"
        lines.append(trailer)
        
        path = FileUtils.obter_caminho_relatorio(f"AFD_{gen_date}_{gen_time}", "txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
            
        return path

    def gerar_comprovante_ponto_pdf(self, funcionario_id: int, data: str, hora: str, tipo: str) -> str:
        funcionario = self.db.obter_funcionario_por_id(funcionario_id)
        nome = funcionario.nome if funcionario else "Desconhecido"
        cpf = funcionario.cpf if funcionario else ""
        pis = funcionario.pis if funcionario else ""
        
        cnpj = config.get("EMPRESA", "cnpj", "00.000.000/0000-00")
        razao = config.get("EMPRESA", "razao_social", "EMPRESA PADRAO LTDA")
        
        filename = f"comprovante_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        path = FileUtils.obter_caminho_relatorio(filename, "pdf")
        
        doc = SimpleDocTemplate(path, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        
        # Estilo Cupom
        story.append(Paragraph("COMPROVANTE DE REGISTRO DE PONTO", styles["Title"]))
        story.append(Spacer(1, 12))
        
        story.append(Paragraph(f"EMPREGADOR: {razao}", styles["Normal"]))
        story.append(Paragraph(f"CNPJ: {cnpj}", styles["Normal"]))
        story.append(Spacer(1, 12))
        
        story.append(Paragraph(f"FUNCIONÁRIO: {nome}", styles["Normal"]))
        story.append(Paragraph(f"PIS: {pis}", styles["Normal"]))
        story.append(Paragraph(f"CPF: {cpf}", styles["Normal"]))
        story.append(Spacer(1, 12))
        
        story.append(Paragraph(f"DATA: {datetime.strptime(data, '%Y-%m-%d').strftime('%d/%m/%Y')}", styles["Normal"]))
        story.append(Paragraph(f"HORÁRIO: {hora}", styles["Normal"]))
        story.append(Paragraph(f"TIPO: {tipo}", styles["Normal"]))
        
        nsr = "N/A" # No persistent NSR for individual punches yet
        story.append(Paragraph(f"NSR: {nsr}", styles["Normal"]))
        
        story.append(Spacer(1, 24))
        story.append(Paragraph("Autenticação Digital:", styles["Normal"]))
        import hashlib
        hash_str = hashlib.md5(f"{nome}{data}{hora}{tipo}".encode()).hexdigest().upper()
        story.append(Paragraph(hash_str, styles["Normal"]))
        
        doc.build(story)
        return path

report_service = ReportService()
