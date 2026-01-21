import sys
import os
import logging
from logging.handlers import RotatingFileHandler

# Adicionar o diretório atual ao path para imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox, QTabWidget, QFileDialog, QInputDialog
from PyQt6.QtGui import QAction
from PyQt6.QtCore import QTimer

from config.settings import config
from database.operations import db_manager
from services.auth import auth_service
from services.reports import report_service
from ui.dialogs import LoginDialog
from utils.helpers import FileUtils
from ui.widgets import FuncionariosWidget, RegistrosWidget, DashboardWidget, AjustesWidget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sistema de Ponto Eletrônico")
        self.setGeometry(100, 100, 1200, 700)
        
        # Inicializar serviços
        self.db = db_manager
        self.auth = auth_service
        self.report_service = report_service
        
        # Configurar interface
        self._setup_logging()
        self._setup_ui()
        self._carregar_dados()
        
        # Timer para atualizações automáticas
        self.timer_atualizacao = QTimer(self)
        self.timer_atualizacao.timeout.connect(self._atualizar_dashboard)
        self.timer_atualizacao.start(30000)  # 30 segundos
        
        # Mostrar login
        self._mostrar_login()
    
    def _setup_logging(self):
        log_path = os.path.join(config.base_dir, "logs", "app.log")
        logger = logging.getLogger("sistemaponto")
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = RotatingFileHandler(
                log_path, 
                maxBytes=512000, 
                backupCount=3, 
                encoding="utf-8"
            )
            formatter = logging.Formatter(
                "%(asctime)s %(levelname)s %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        self.logger = logger
        self.logger.info("Sistema iniciado")
    
    def _setup_ui(self):
        # Menu Bar
        menubar = self.menuBar()
        sistema_menu = menubar.addMenu("Sistema")
        
        config_action = QAction("Configurações", self)
        config_action.triggered.connect(self._abrir_configuracoes)
        sistema_menu.addAction(config_action)
        
        sistema_menu.addSeparator()
        
        sair_action = QAction("Sair", self)
        sair_action.triggered.connect(self.close)
        sistema_menu.addAction(sair_action)

        # Widget central com abas
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        # Criar widgets
        self.dashboard_widget = DashboardWidget(self)
        self.registros_widget = RegistrosWidget(self)
        self.funcionarios_widget = FuncionariosWidget(self)
        self.ajustes_widget = AjustesWidget(self)
        
        # Adicionar abas
        self.tabs.addTab(self.dashboard_widget, "Dashboard")
        self.tabs.addTab(self.registros_widget, "Registros")
        self.tabs.addTab(self.funcionarios_widget, "Funcionários")
        self.tabs.addTab(self.ajustes_widget, "Ajustes")
    
    def _carregar_dados(self):
        try:
            self.funcionarios_todos = self.db.obter_funcionarios(ativos_only=False)
            self.funcionarios_ativos = self.db.obter_funcionarios(ativos_only=True)
            self.funcionarios_widget.carregar_dados(self.funcionarios_todos)
            self.registros_widget.carregar_funcionarios(self.funcionarios_ativos)
            
            # Carregar registros recentes
            self._carregar_registros_recentes()
            
            # Carregar ajustes
            if hasattr(self, 'ajustes_widget'):
                self.ajustes_widget._carregar_dados()
            
        except Exception as e:
            self.logger.error(f"Erro ao carregar dados: {e}")
            QMessageBox.critical(self, "Erro", f"Falha ao carregar dados: {e}")
    
    def _carregar_registros_recentes(self):
        from datetime import date, timedelta
        
        data_inicio = (date.today() - timedelta(days=7)).isoformat()
        data_fim = date.today().isoformat()
        
        registros = self.db.obter_registros_por_periodo(data_inicio, data_fim)
        self.registros_widget.carregar_registros(registros)
    
    def _mostrar_login(self):
        self.logger.info("Mostrando login...")
        dialog = LoginDialog(self)
        self.logger.info("Dialog criado. Executando...")
        res = dialog.exec()
        self.logger.info(f"Dialog result: {res}")
        if res:
            username, password = dialog.get_credentials()
            sucesso, resultado = self.auth.login(username, password)
            
            if sucesso:
                self.logger.info(f"Login bem-sucedido: {username}")
                self._atualizar_interface_por_permissao()
                self._atualizar_dashboard()
            else:
                msg = resultado.get("error", "Falha no login") if isinstance(resultado, dict) else "Falha no login"
                QMessageBox.warning(self, "Login", msg)
                self._mostrar_login()
        else:
            sys.exit(0)
    
    def _atualizar_interface_por_permissao(self):
        usuario = self.auth.get_current_user()
        if not usuario:
            return
        
        # Exemplo: desabilitar funcionalidades baseado na role
        is_admin = usuario.get("role") == "admin"
        self.funcionarios_widget.btn_excluir.setEnabled(is_admin)
    
    def _atualizar_dashboard(self):
        try:
            from datetime import date, datetime, timedelta
            
            lista = getattr(self, 'funcionarios_ativos', [])
            hoje = date.today()
            hoje_str = hoje.isoformat()
            
            presentes_hoje = len([f for f in lista if self.db.obter_registro_do_dia(f.cpf, hoje_str)])
            total_funcionarios = len(lista)
            
            # Verificar Feriado e Abonados para Hoje
            feriado_hoje = self.db.verificar_feriado(hoje_str)
            abonados_hoje = self.db.contar_abonados(hoje_str)
            
            if feriado_hoje or hoje.weekday() >= 5:
                atrasos = 0
                faltas = 0
            else:
                # Faltas = Total - Presentes - Abonados
                # Nota: Isso considera quem ainda não chegou como falta
                faltas = max(0, total_funcionarios - presentes_hoje - abonados_hoje)
                atrasos = 0  # TODO: Implementar lógica de atraso baseada em horário padrão
            
            mes, ano = self.dashboard_widget.obter_mes_ano() if hasattr(self, 'dashboard_widget') else (date.today().month, date.today().year)
            data_inicio = date(ano, mes, 1)
            # Calcular ultimo dia do mes
            ultimo_dia_date = (date(ano, mes, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            data_fim = ultimo_dia_date.day
            
            registros = self.db.obter_registros_por_periodo(data_inicio.isoformat(), date(ano, mes, data_fim).isoformat())
            mapa = {}
            for r in registros:
                d = r.get('data')
                cpf = r.get('cpf')
                if not d or not cpf:
                    continue
                s = mapa.get(d) or set()
                s.add(cpf)
                mapa[d] = s
            
            dados_presenca = []
            dia = 1
            while dia <= data_fim:
                d = date(ano, mes, dia)
                dstr = d.isoformat()
                
                is_feriado = self.db.verificar_feriado(dstr) is not None
                is_weekend = d.weekday() >= 5
                
                if is_feriado or is_weekend:
                    presentes = total_funcionarios
                else:
                    presentes = len(mapa.get(dstr, set()))
                
                dados_presenca.append({"dia": dia, "presentes": presentes, "total": total_funcionarios})
                dia += 1
            
            self.dashboard_widget.atualizar_resumo(
                presentes=presentes_hoje,
                total=total_funcionarios,
                faltas=faltas,
                abonadas=abonados_hoje,
                extras=0
            )
            self.dashboard_widget.atualizar_grafico(dados_presenca)
            
        except Exception as e:
            self.logger.error(f"Erro ao atualizar dashboard: {e}")
    
    # Métodos para funcionários
    def _novo_funcionario(self):
        from ui.dialogs import FuncionarioDialog
        
        dialog = FuncionarioDialog(self)
        if dialog.exec():
            funcionario = dialog.get_funcionario_data()
            try:
                self.db.salvar_funcionario(funcionario)
                self._carregar_dados()
                QMessageBox.information(self, "Sucesso", "Funcionário salvo com sucesso!")
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Falha ao salvar funcionário: {e}")
    
    def _editar_funcionario(self):
        from ui.dialogs import FuncionarioDialog
        
        func_id = self.funcionarios_widget.obter_id_selecionado()
        if not func_id:
            QMessageBox.information(self, "Editar", "Selecione um funcionário.")
            return
        
        funcionario = self.db.obter_funcionario_por_id(func_id)
        if not funcionario:
            QMessageBox.warning(self, "Erro", "Funcionário não encontrado.")
            return
        
        dialog = FuncionarioDialog(self, funcionario)
        if dialog.exec():
            funcionario_editado = dialog.get_funcionario_data()
            try:
                self.db.salvar_funcionario(funcionario_editado)
                self._carregar_dados()
                QMessageBox.information(self, "Sucesso", "Funcionário atualizado!")
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Falha ao atualizar: {e}")
    
    def _excluir_funcionario(self):
        func_id = self.funcionarios_widget.obter_id_selecionado()
        if not func_id:
            QMessageBox.information(self, "Excluir", "Selecione um funcionário.")
            return
        
        resposta = QMessageBox.question(
            self, "Confirmação", 
            "Tem certeza que deseja excluir este funcionário?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if resposta == QMessageBox.StandardButton.Yes:
            try:
                self.db.excluir_funcionario(func_id)
                self._carregar_dados()
                QMessageBox.information(self, "Sucesso", "Funcionário excluído!")
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Falha ao excluir: {e}")
    
    def _limpar_selecao_funcionario(self):
        self.funcionarios_widget.tabela.clearSelection()
    
    def _on_double_click_funcionario(self, row, column):
        self._editar_funcionario()
    
    # Métodos para registros
    def _registrar_ponto(self, tipo):
        from ui.dialogs import RetroactiveDateTimeDialog, RegistroDetalhesDialog
        from datetime import datetime
        from models.entities import RegistroPonto
        
        pin = self.registros_widget.obter_cpf_registro()
        if not pin:
            QMessageBox.warning(self, "Registro", "Digite seu PIN.")
            return
        
        # Verificar se funcionário existe pelo PIN e está ativo
        funcionario = self.db.obter_funcionario_por_pin(pin)
        if not funcionario:
            # Fallback to try finding by CPF for backward compatibility or admin usage
            funcionario = self.db.obter_funcionario_por_cpf(pin)
            
        if not funcionario or not funcionario.ativo:
            QMessageBox.warning(self, "Registro", "Funcionário não encontrado ou inativo (Verifique o PIN).")
            return
            
        cpf = funcionario.cpf
        
        # Perguntar se é retroativo
        resposta = QMessageBox.question(
            self, "Registro", 
            f"Olá {funcionario.nome.split()[0]}, registrar ponto agora?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if resposta == QMessageBox.StandardButton.Yes:
            data = datetime.now().strftime("%Y-%m-%d")
            hora = datetime.now().strftime("%H:%M:%S")
        else:
            dialog = RetroactiveDateTimeDialog(self)
            if not dialog.exec():
                return
            data, hora = dialog.get_datetime()
        
        # Perguntar por detalhes adicionais
        detalhes = None
        resposta_detalhes = QMessageBox.question(
            self, "Detalhes", 
            "Adicionar localização/foto?"
        )
        
        if resposta_detalhes == QMessageBox.StandardButton.Yes:
            dialog_detalhes = RegistroDetalhesDialog(self)
            if dialog_detalhes.exec():
                detalhes = dialog_detalhes.get_data()
        
        # Criar registro
        registro = RegistroPonto(
            funcionario_id=funcionario.id,
            cpf=cpf,
            data=data,
            tipo=tipo,
            ts=f"{data} {hora}",
            ts_device=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ts_server=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            device_id="desktop_app"
        )
        
        # Definir horário baseado no tipo
        if tipo == "ENTRADA":
            registro.hora_entrada = hora
        elif tipo == "SAIDA_ALMOCO":
            registro.saida_almoco = hora
        elif tipo == "RETORNO_ALMOCO":
            registro.retorno_almoco = hora
        elif tipo == "SAIDA_FINAL":
            registro.saida_final = hora
            registro.hora_saida = hora
        
        # Adicionar detalhes se fornecidos
        if detalhes:
            registro.gps_lat = detalhes.get("lat")
            registro.gps_lng = detalhes.get("lng")
            registro.foto_path = detalhes.get("foto")
        
        try:
            # Verificar se já existe registro no dia
            registro_existente = self.db.obter_registro_do_dia(cpf, data)
            
            if registro_existente:
                # Atualizar registro existente
                registro.id = registro_existente["id"]
                # Preservar dados anteriores para não sobrescrever com None
                registro.hora_entrada = registro.hora_entrada or registro_existente.get("hora_entrada")
                registro.saida_almoco = registro.saida_almoco or registro_existente.get("saida_almoco")
                registro.retorno_almoco = registro.retorno_almoco or registro_existente.get("retorno_almoco")
                registro.saida_final = registro.saida_final or registro_existente.get("saida_final")
                registro.hora_saida = registro.hora_saida or registro_existente.get("hora_saida")
                
                # Preservar metadados se não houver novos
                registro.foto_path = registro.foto_path or registro_existente.get("foto_path")
                registro.gps_lat = registro.gps_lat or registro_existente.get("gps_lat")
                registro.gps_lng = registro.gps_lng or registro_existente.get("gps_lng")
                registro.ip_addr = registro.ip_addr or registro_existente.get("ip_addr")
            
            self.db.salvar_registro(registro)
            self.registros_widget.limpar_cpf_registro()
            self._carregar_registros_recentes()
            self._atualizar_dashboard()
            
            QMessageBox.information(self, "Registro", f"{tipo.replace('_', ' ').title()} registrado com sucesso!")
            
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao registrar ponto: {e}")
    
    def _abrir_configuracoes(self):
        from ui.dialogs import ConfiguracoesDialog
        
        # Verificar permissão de admin
        usuario = self.auth.get_current_user()
        if not usuario or usuario.get("role") != "admin":
            QMessageBox.warning(self, "Acesso Negado", "Apenas administradores podem acessar as configurações.")
            return
            
        dialog = ConfiguracoesDialog(self)
        if dialog.exec():
            # Recarregar configurações se necessário
            pass

    def _solicitar_ajuste(self):
        from ui.dialogs import AjustePontoDialog
        
        pin = self.registros_widget.obter_cpf_registro()
        if not pin:
            QMessageBox.warning(self, "Ajuste", "Digite seu PIN.")
            return
            
        # Validar se funcionário existe
        funcionario = self.db.obter_funcionario_por_pin(pin)
        if not funcionario:
             funcionario = self.db.obter_funcionario_por_cpf(pin)
             
        if not funcionario:
            QMessageBox.warning(self, "Ajuste", "Funcionário não encontrado (Verifique o PIN).")
            return
            
        cpf = funcionario.cpf
        
        dialog = AjustePontoDialog(self)
        if dialog.exec():
            dados = dialog.get_data()
            dados["cpf"] = cpf
            
            try:
                self.db.salvar_ajuste(dados)
                QMessageBox.information(self, "Sucesso", "Solicitação de ajuste enviada com sucesso!")
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Falha ao salvar ajuste: {e}")

    def _aplicar_filtros(self):
        filtros = self.registros_widget.obter_filtros()
        
        try:
            registros = self.db.obter_registros_por_periodo(
                filtros["data_inicio"],
                filtros["data_fim"],
                filtros["funcionario_id"]
            )
            self.registros_widget.carregar_registros(registros)
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao aplicar filtros: {e}")
    
    def _limpar_filtros(self):
        from datetime import date
        
        self.registros_widget.date_inicio.setDate(date.today())
        self.registros_widget.date_fim.setDate(date.today())
        self.registros_widget.combo_funcionario.setCurrentIndex(0)
        self._carregar_registros_recentes()
    
    def _exportar_registros(self):
        from services.reports import report_service
        import csv
        from openpyxl import Workbook
        
        try:
            filtros = self.registros_widget.obter_filtros()
            registros = self.db.obter_registros_por_periodo(
                filtros["data_inicio"],
                filtros["data_fim"],
                filtros["funcionario_id"]
            )
            
            if not registros:
                QMessageBox.information(self, "Exportar", "Nenhum registro encontrado para exportar.")
                return

            # Escolher formato
            formato, ok = QInputDialog.getItem(
                self, "Exportar Registros", 
                "Selecione o formato:", 
                ["CSV (Texto)", "Excel (.xlsx)"], 
                0, False
            )
            if not ok:
                return

            if "CSV" in formato:
                path, _ = QFileDialog.getSaveFileName(self, "Salvar CSV", "registros.csv", "CSV (*.csv)")
                if path:
                    with open(path, "w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f, delimiter=";")
                        headers = ["Data", "CPF", "Nome", "Entrada", "Saída Almoço", "Retorno", "Saída Final", "Tipo"]
                        writer.writerow(headers)
                        for r in registros:
                            writer.writerow([
                                r.get("data"), r.get("cpf"), r.get("funcionario_nome"),
                                r.get("hora_entrada"), r.get("saida_almoco"), r.get("retorno_almoco"),
                                r.get("saida_final") or r.get("hora_saida"), r.get("tipo")
                            ])
                    QMessageBox.information(self, "Sucesso", "Arquivo CSV exportado com sucesso!")
            
            else: # Excel
                path, _ = QFileDialog.getSaveFileName(self, "Salvar Excel", "registros.xlsx", "Excel (*.xlsx)")
                if path:
                    wb = Workbook()
                    ws = wb.active
                    ws.title = "Registros"
                    headers = ["Data", "CPF", "Nome", "Entrada", "Saída Almoço", "Retorno", "Saída Final", "Tipo"]
                    ws.append(headers)
                    for r in registros:
                        ws.append([
                            r.get("data"), r.get("cpf"), r.get("funcionario_nome"),
                            r.get("hora_entrada"), r.get("saida_almoco"), r.get("retorno_almoco"),
                            r.get("saida_final") or r.get("hora_saida"), r.get("tipo")
                        ])
                    wb.save(path)
                    QMessageBox.information(self, "Sucesso", "Arquivo Excel exportado com sucesso!")
            
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao exportar: {e}")
    
    def _exportar_espelho_ponto(self):
        from services.reports import report_service
        from datetime import datetime
        import os
        import webbrowser
        
        try:
            filtros = self.registros_widget.obter_filtros()
            func_id = self.registros_widget.combo_funcionario.currentData()
            
            if not func_id:
                QMessageBox.warning(self, "Espelho do Ponto", "Selecione um funcionário específico para gerar o espelho.")
                return
                
            data_ini = datetime.strptime(filtros["data_inicio"], "%Y-%m-%d")
            ano = data_ini.year
            mes = data_ini.month
            
            # Escolher formato
            formato, ok = QInputDialog.getItem(
                self, "Espelho de Ponto", 
                "Selecione o formato:", 
                ["PDF (Documento)", "Excel (.xlsx)", "HTML (Navegador)"], 
                0, False
            )
            if not ok:
                return

            if "PDF" in formato:
                path = report_service.gerar_espelho_ponto_pdf(func_id, ano, mes)
                # Abrir PDF se possível
                try:
                    os.startfile(path)
                except:
                    QMessageBox.information(self, "Sucesso", f"PDF gerado em:\n{path}")
                    
            elif "Excel" in formato:
                path = report_service.gerar_espelho_ponto_xlsx(func_id, ano, mes)
                try:
                    os.startfile(path)
                except:
                    QMessageBox.information(self, "Sucesso", f"Excel gerado em:\n{path}")
                    
            else: # HTML
                path_html = report_service.gerar_espelho_ponto_html(func_id, ano, mes)
                url = "file:///" + path_html.replace(os.sep, "/")
                webbrowser.open(url, new=2)

        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao gerar espelho: {e}")

    def _importar_registros(self):
        import csv
        try:
            path, _ = QFileDialog.getOpenFileName(self, "Importar Registros", "", "CSV (*.csv)")
            if not path:
                return
            count = 0
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    from models.entities import RegistroPonto
                    cpf = row.get("cpf") or row.get("CPF")
                    data = row.get("data") or row.get("Data")
                    if not cpf or not data:
                        continue
                    func = self.db.obter_funcionario_por_cpf(cpf)
                    if not func:
                        continue
                    reg = RegistroPonto(
                        funcionario_id=func.id,
                        cpf=cpf,
                        data=data,
                        hora_entrada=row.get("hora_entrada") or None,
                        saida_almoco=row.get("saida_almoco") or None,
                        retorno_almoco=row.get("retorno_almoco") or None,
                        saida_final=row.get("saida_final") or None,
                        tipo=row.get("tipo") or "IMPORT",
                        ts=f"{data} {(row.get('hora_entrada') or '00:00:00')}"
                    )
                    self.db.salvar_registro(reg)
                    count += 1
            self._carregar_registros_recentes()
            QMessageBox.information(self, "Importar", f"{count} registros importados.")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao importar: {e}")

    def _imprimir_registros(self):
        import os
        import webbrowser
        try:
            filtros = self.registros_widget.obter_filtros()
            registros = self.db.obter_registros_por_periodo(
                filtros["data_inicio"],
                filtros["data_fim"],
                filtros["funcionario_id"]
            )
            css = """
            <style>
            @page { size: A4 portrait; margin: 6mm; }
            body { font-family: Arial, sans-serif; color: #222; }
            table { width: 100%; border-collapse: collapse; }
            th, td { border: 1px solid #777; padding: 4px 6px; font-size: 11px; }
            th { background: #f0f0f0; }
            .print-btn { position: fixed; top: 12px; right: 12px; background: #1976d2; color: #fff; border: none; padding: 8px 12px; border-radius: 4px; cursor: pointer; }
            @media print { .print-btn { display: none; } }
            </style>
            """
            rows = ""
            for r in registros:
                rows += f"<tr><td>{r.get('data','')}</td><td>{r.get('cpf','')}</td><td>{r.get('hora_entrada','')}</td><td>{r.get('saida_almoco','')}</td><td>{r.get('retorno_almoco','')}</td><td>{r.get('saida_final') or r.get('hora_saida','')}</td><td>{r.get('tipo','')}</td></tr>"
            html = f"""
            <html><head><meta charset='utf-8'>{css}</head><body>
            <button class='print-btn' onclick='window.print()'>Imprimir</button>
            <h3>Registros de Ponto</h3>
            <table><thead><tr>
            <th>Data</th><th>CPF</th><th>Entrada</th><th>Saída Almoço</th><th>Retorno</th><th>Saída Final</th><th>Tipo</th>
            </tr></thead><tbody>{rows}</tbody></table>
            </body></html>
            """
            path = FileUtils.obter_caminho_relatorio("registros", "html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            url = "file:///" + path.replace(os.sep, "/")
            webbrowser.open(url, new=2)
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao imprimir: {e}")
    
    def closeEvent(self, event):
        FileUtils.fazer_backup_automatico()
        self.logger.info("Sistema finalizado")
        event.accept()

def main():
    app = QApplication(sys.argv)
    
    # Configurar estilo da aplicação
    app.setStyle('Fusion')
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
