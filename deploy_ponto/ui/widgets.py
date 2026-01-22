from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QLabel, QLineEdit, QDateEdit, QComboBox,
    QGroupBox, QTextEdit, QFrame, QGridLayout, QProgressBar, QMessageBox
)
from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import QStyle

class StyledTableWidget(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.setSortingEnabled(True)
        self.setStyleSheet(
            """
            QTableWidget { gridline-color: #e0e0e0; }
            QHeaderView::section { background: #f5f5f5; padding: 6px; border: 1px solid #e0e0e0; }
            QTableWidget::item:selected { background: #e3f2fd; }
            """
        )

class FuncionariosWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.layout = QVBoxLayout(self)
        self._setup_ui()
    
    def _setup_ui(self):
        self.setStyleSheet(
            """
            QPushButton { background: #1976d2; color: #fff; border: none; border-radius: 6px; padding: 6px 10px; font-weight: bold; }
            QPushButton:hover { filter: brightness(0.95); }
            #btnNovoFuncionario { background: #2e7d32; }
            #btnExcluir { background: #c62828; }
            #btnLimpar { background: #757575; }
            QGroupBox { border: 1px solid #e0e0e0; border-radius: 6px; margin-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }
            """
        )
        filter_group = QGroupBox("Filtros")
        filter_layout = QHBoxLayout(filter_group)
        
        self.btn_novo = QPushButton("Novo Funcionário")
        self.btn_editar = QPushButton("Editar")
        self.btn_excluir = QPushButton("Excluir")
        self.btn_excluir.setObjectName("btnExcluir")
        self.btn_limpar = QPushButton("Limpar")
        self.btn_limpar.setObjectName("btnLimpar")
        
        filter_layout.addWidget(self.btn_novo)
        filter_layout.addWidget(self.btn_editar)
        filter_layout.addWidget(self.btn_excluir)
        filter_layout.addWidget(self.btn_limpar)
        filter_layout.addStretch()
        
        self.tabela = StyledTableWidget()
        self.tabela.setColumnCount(6)
        self.tabela.setHorizontalHeaderLabels([
            "ID", "Nome", "CPF", "Departamento", "Carga (HH:mm)", "Ativo"
        ])
        
        self.layout.addWidget(filter_group)
        self.layout.addWidget(self.tabela)
        
        self.btn_novo.clicked.connect(self.parent._novo_funcionario)
        self.btn_editar.clicked.connect(self.parent._editar_funcionario)
        self.btn_excluir.clicked.connect(self.parent._excluir_funcionario)
        self.btn_limpar.clicked.connect(self.parent._limpar_selecao_funcionario)
        self.tabela.cellDoubleClicked.connect(self.parent._on_double_click_funcionario)
    
    def carregar_dados(self, funcionarios):
        self.tabela.setRowCount(len(funcionarios))
        for i, func in enumerate(funcionarios):
            self.tabela.setItem(i, 0, QTableWidgetItem(str(func.id)))
            self.tabela.setItem(i, 1, QTableWidgetItem(func.nome))
            self.tabela.setItem(i, 2, QTableWidgetItem(func.cpf))
            self.tabela.setItem(i, 3, QTableWidgetItem(func.departamento or ""))
            
            horas = func.carga_horaria_min // 60
            minutos = func.carga_horaria_min % 60
            self.tabela.setItem(i, 4, QTableWidgetItem(f"{horas:02d}:{minutos:02d}"))
            
            self.tabela.setItem(i, 5, QTableWidgetItem("Sim" if func.ativo else "Não"))
    
    def obter_id_selecionado(self):
        row = self.tabela.currentRow()
        if row >= 0:
            item = self.tabela.item(row, 0)
            return int(item.text()) if item else None
        return None

class RegistrosWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.layout = QVBoxLayout(self)
        self._setup_ui()
    
    def _setup_ui(self):
        self.setStyleSheet(
            """
            QPushButton { background: #eceff1; color: #333; border: none; border-radius: 6px; padding: 6px 10px; }
            #btnEntrada { background: #1976d2; }
            #btnEntrada:hover { background: #1565c0; }
            #btnSaidaAlmoco { background: #fb8c00; }
            #btnSaidaAlmoco:hover { background: #ef6c00; }
            #btnRetornoAlmoco { background: #2e7d32; }
            #btnRetornoAlmoco:hover { background: #1b5e20; }
            #btnSaidaFinal { background: #c62828; }
            #btnSaidaFinal:hover { background: #b71c1c; }
            #btnEntrada, #btnSaidaAlmoco, #btnRetornoAlmoco, #btnSaidaFinal { color: #fff; font-weight: bold; }
            QGroupBox { border: 1px solid #e0e0e0; border-radius: 6px; margin-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }
            """
        )
        registro_group = QGroupBox("Registro Rápido")
        registro_layout = QHBoxLayout(registro_group)
        
        self.txt_cpf = QLineEdit()
        self.txt_cpf.setPlaceholderText("Digite seu PIN (4 dígitos)")
        self.txt_cpf.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_cpf.setMaxLength(4)
        self.txt_cpf.setFixedWidth(200)
        self.txt_cpf.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.txt_cpf.setStyleSheet("font-size: 24px; padding: 10px; font-weight: bold;")
        
        self.btn_entrada = QPushButton("ENTRADA")
        self.btn_saida_almoco = QPushButton("SAÍDA ALMOÇO")
        self.btn_retorno_almoco = QPushButton("RETORNO ALMOÇO")
        self.btn_saida_final = QPushButton("SAÍDA FINAL")
        
        # Estilo dos botões
        for btn in [self.btn_entrada, self.btn_saida_almoco, 
                   self.btn_retorno_almoco, self.btn_saida_final]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(50)
        
        self.btn_entrada.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.btn_saida_almoco.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold;")
        self.btn_retorno_almoco.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold;")
        self.btn_saida_final.setStyleSheet("background-color: #F44336; color: white; font-weight: bold;")
        
        registro_layout.addWidget(self.txt_cpf)
        registro_layout.addWidget(self.btn_entrada)
        registro_layout.addWidget(self.btn_saida_almoco)
        registro_layout.addWidget(self.btn_retorno_almoco)
        registro_layout.addWidget(self.btn_saida_final)
        
        self.btn_ajuste = QPushButton("Solicitar Ajuste")
        self.btn_ajuste.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ajuste.setMinimumHeight(50)
        self.btn_ajuste.setStyleSheet("background-color: #9C27B0; color: white; font-weight: bold;")
        registro_layout.addWidget(self.btn_ajuste)
        
        filtro_group = QGroupBox("Filtros")
        filtro_layout = QHBoxLayout(filtro_group)
        
        # Seletor Rápido de Mês
        self.lbl_mes_ref = QLabel("Mês Ref:")
        self.date_mes_ref = QDateEdit()
        self.date_mes_ref.setDate(QDate.currentDate())
        self.date_mes_ref.setDisplayFormat("MM/yyyy")
        self.date_mes_ref.setCalendarPopup(True)
        self.date_mes_ref.setFixedWidth(100)
        self.date_mes_ref.dateChanged.connect(self._atualizar_datas_por_mes)
        
        self.lbl_data_inicio = QLabel("De:")
        self.date_inicio = QDateEdit()
        # Inicializar com o primeiro dia do mês atual
        current_date = QDate.currentDate()
        self.date_inicio.setDate(QDate(current_date.year(), current_date.month(), 1))
        self.date_inicio.setDisplayFormat("dd/MM/yyyy")
        
        self.lbl_data_fim = QLabel("Até:")
        self.date_fim = QDateEdit()
        # Inicializar com o último dia do mês atual
        last_day = QDate(current_date.year(), current_date.month(), 1).addMonths(1).addDays(-1)
        self.date_fim.setDate(last_day)
        self.date_fim.setDisplayFormat("dd/MM/yyyy")
        
        self.lbl_funcionario = QLabel("Funcionário:")
        self.combo_funcionario = QComboBox()
        
        self.btn_filtrar = QPushButton("Filtrar")
        self.btn_limpar_filtros = QPushButton("Limpar")
        self.btn_exportar = QPushButton("Exportar")
        self.btn_espelho = QPushButton("Espelho do Ponto")
        self.btn_importar = QPushButton("Importar")
        self.btn_imprimir = QPushButton("Imprimir")
        
        filtro_layout.addWidget(self.lbl_mes_ref)
        filtro_layout.addWidget(self.date_mes_ref)
        filtro_layout.addWidget(self.lbl_data_inicio)
        filtro_layout.addWidget(self.date_inicio)
        filtro_layout.addWidget(self.lbl_data_fim)
        filtro_layout.addWidget(self.date_fim)
        filtro_layout.addWidget(self.lbl_funcionario)
        filtro_layout.addWidget(self.combo_funcionario)
        filtro_layout.addWidget(self.btn_filtrar)
        filtro_layout.addWidget(self.btn_limpar_filtros)
        filtro_layout.addWidget(self.btn_importar)
        filtro_layout.addWidget(self.btn_exportar)
        filtro_layout.addWidget(self.btn_espelho)
        filtro_layout.addWidget(self.btn_imprimir)
        
        self.tabela = StyledTableWidget()
        self.tabela.setColumnCount(11)
        self.tabela.setHorizontalHeaderLabels([
            "Data", "Entrada", "Saída Almoço", "Retorno", "Saída Final",
            "GPS", "Foto", "Total", "Saldo", "Tipo", "CPF"
        ])
        
        self.layout.addWidget(registro_group)
        self.layout.addWidget(filtro_group)
        self.layout.addWidget(self.tabela)
        
        self.btn_entrada.clicked.connect(lambda: self.parent._registrar_ponto("ENTRADA"))
        self.btn_saida_almoco.clicked.connect(lambda: self.parent._registrar_ponto("SAIDA_ALMOCO"))
        self.btn_retorno_almoco.clicked.connect(lambda: self.parent._registrar_ponto("RETORNO_ALMOCO"))
        self.btn_saida_final.clicked.connect(lambda: self.parent._registrar_ponto("SAIDA_FINAL"))
        self.btn_filtrar.clicked.connect(self.parent._aplicar_filtros)
        self.btn_limpar_filtros.clicked.connect(self.parent._limpar_filtros)
        self.btn_importar.clicked.connect(self.parent._importar_registros)
        self.btn_exportar.clicked.connect(self.parent._exportar_registros)
        self.btn_espelho.clicked.connect(self.parent._exportar_espelho_ponto)
        self.btn_imprimir.clicked.connect(self.parent._imprimir_registros)
        self.btn_ajuste.clicked.connect(self.parent._solicitar_ajuste)

    def _atualizar_datas_por_mes(self, date):
        # Set start date to 1st of month
        dt_inicio = QDate(date.year(), date.month(), 1)
        self.date_inicio.setDate(dt_inicio)
        
        # Set end date to last day of month
        dt_fim = dt_inicio.addMonths(1).addDays(-1)
        self.date_fim.setDate(dt_fim)
    
    def carregar_funcionarios(self, funcionarios):
        self.combo_funcionario.clear()
        self.combo_funcionario.addItem("Todos", None)
        for func in funcionarios:
            self.combo_funcionario.addItem(f"{func.nome} ({func.cpf})", func.id)
    
    def carregar_registros(self, registros):
        self.tabela.setRowCount(len(registros))
        for i, reg in enumerate(registros):
            horas_trabalhadas = self.parent.report_service.calcular_horas_dia(reg)
            saldo = horas_trabalhadas - (reg.get("carga_horaria_min", 480) / 60)
            gps_text = ""
            if reg.get("gps_lat") is not None and reg.get("gps_lng") is not None:
                gps_text = f"{reg['gps_lat']:.5f}, {reg['gps_lng']:.5f}"
            self.tabela.setItem(i, 0, QTableWidgetItem(reg.get("data", "")))
            self.tabela.setItem(i, 1, QTableWidgetItem(reg.get("hora_entrada") or ""))
            self.tabela.setItem(i, 2, QTableWidgetItem(reg.get("saida_almoco") or ""))
            self.tabela.setItem(i, 3, QTableWidgetItem(reg.get("retorno_almoco") or ""))
            self.tabela.setItem(i, 4, QTableWidgetItem(reg.get("saida_final") or reg.get("hora_saida") or ""))
            self.tabela.setItem(i, 5, QTableWidgetItem(gps_text))
            self.tabela.setItem(i, 6, QTableWidgetItem(reg.get("foto_path") or ""))
            self.tabela.setItem(i, 7, QTableWidgetItem(f"{horas_trabalhadas:.2f}"))
            self.tabela.setItem(i, 8, QTableWidgetItem(f"{saldo:+.2f}"))
            self.tabela.setItem(i, 9, QTableWidgetItem(reg.get("tipo") or ""))
            self.tabela.setItem(i, 10, QTableWidgetItem(reg.get("cpf") or ""))
    
    def obter_cpf_registro(self):
        return self.txt_cpf.text().strip()
    
    def limpar_cpf_registro(self):
        self.txt_cpf.clear()
    
    def obter_filtros(self):
        return {
            "data_inicio": self.date_inicio.date().toString("yyyy-MM-dd"),
            "data_fim": self.date_fim.date().toString("yyyy-MM-dd"),
            "funcionario_id": self.combo_funcionario.currentData(),
        }

class DashboardWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.layout = QVBoxLayout(self)
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(
            """
            QPushButton {
                background-color: #1976d2;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1565c0;
            }
            QPushButton:pressed {
                background-color: #0d47a1;
            }
            QDateEdit {
                padding: 6px;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                background: white;
            }

            QFrame#card { background: #ffffff; border: 1px solid #e0e0e0; border-radius: 12px; }
            QLabel#cardTitle { color: #607d8b; font-size: 13px; }
            QLabel#cardValue { font-size: 28px; font-weight: 700; }
            QLabel#cardIcon { margin-bottom: 6px; }
            
            QFrame#presencaCard { 
                background: #ffffff; 
                border: 1px solid #e0e0e0; 
                border-radius: 12px; 
            }
            QLabel#presencaTitle {
                font-size: 16px;
                font-weight: 600;
                color: #2c3e50;
                padding: 16px;
            }
            QTableWidget {
                background-color: transparent;
                border: none;
                gridline-color: #f5f5f5;
                selection-background-color: #e3f2fd;
                selection-color: #000000;
            }
            QHeaderView::section {
                background-color: #ffffff;
                color: #7f8c8d;
                font-weight: 600;
                border: none;
                border-bottom: 2px solid #f0f0f0;
                padding: 12px 8px;
                text-align: left;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid #f9f9f9;
            }
            QProgressBar {
                background-color: #f0f0f0;
                border: none;
                border-radius: 4px;
                min-height: 8px;
                max-height: 8px;
            }
            QProgressBar::chunk {
                background-color: #4caf50;
                border-radius: 4px;
            }
            """
        )
        top = QHBoxLayout()
        self.date_mes = QDateEdit()
        self.date_mes.setDate(QDate.currentDate())
        self.date_mes.setDisplayFormat("MM/yyyy")
        self.btn_refresh = QPushButton("Atualizar")
        self.btn_refresh.clicked.connect(lambda: self.parent._atualizar_dashboard())
        top.addWidget(QLabel("Mês:"))
        top.addWidget(self.date_mes)
        top.addStretch()
        top.addWidget(self.btn_refresh)
        self.layout.addLayout(top)
        grid = QGridLayout()
        self.card_presentes = self._criar_card("Presentes Hoje", "0/0", "#2e7d32", QStyle.StandardPixmap.SP_DialogApplyButton)
        self.card_faltas = self._criar_card("Faltas Hoje", "0", "#c62828", QStyle.StandardPixmap.SP_MessageBoxCritical)
        self.card_abonadas = self._criar_card("Abonadas Hoje", "0", "#1565c0", QStyle.StandardPixmap.SP_DialogHelpButton)
        self.card_extras = self._criar_card("Horas Extras", "0h", "#ef6c00", QStyle.StandardPixmap.SP_ArrowForward)
        
        grid.addWidget(self.card_presentes, 0, 0)
        grid.addWidget(self.card_faltas, 0, 1)
        grid.addWidget(self.card_abonadas, 0, 2)
        grid.addWidget(self.card_extras, 0, 3)
        self.layout.addLayout(grid)
        
        self.presenca_frame = QFrame()
        self.presenca_frame.setObjectName("presencaCard")
        grafico_layout = QVBoxLayout(self.presenca_frame)
        grafico_layout.setContentsMargins(0, 0, 0, 20)
        grafico_layout.setSpacing(0)
        
        title_label = QLabel("Presença do Mês")
        title_label.setObjectName("presencaTitle")
        grafico_layout.addWidget(title_label)
        
        self.grafico_table = QTableWidget(0, 3)
        self.grafico_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.grafico_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.grafico_table.setShowGrid(False)
        self.grafico_table.verticalHeader().setVisible(False)
        self.grafico_table.setFrameShape(QFrame.Shape.NoFrame)
        
        self.grafico_table.setHorizontalHeaderLabels(["Dia", "%", "Presença"])
        self.grafico_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.grafico_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.grafico_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        grafico_layout.addWidget(self.grafico_table)
        
        self.info_label = QLabel("Sem dados para o período selecionado")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setStyleSheet("color: #90a4ae; font-size: 14px; margin-top: 20px;")
        grafico_layout.addWidget(self.info_label)
        
        self.layout.addWidget(self.presenca_frame)

    def obter_mes_ano(self):
        d = self.date_mes.date()
        return d.month(), d.year()

    def _criar_card(self, titulo, valor, cor, icon_sp):
        frame = QFrame()
        frame.setObjectName("card")
        v = QVBoxLayout(frame)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(6)
        frame.setMinimumHeight(130)
        t = QLabel(titulo)
        t.setObjectName("cardTitle")
        icon_label = QLabel()
        icon_label.setObjectName("cardIcon")
        icon = self.style().standardIcon(icon_sp)
        icon_label.setPixmap(icon.pixmap(32, 32))
        val = QLabel(valor)
        val.setObjectName("cardValue")
        val.setStyleSheet(f"color: {cor};")
        val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(t)
        v.addWidget(icon_label)
        v.addWidget(val)
        return frame

    def atualizar_resumo(self, presentes, total, faltas, abonadas, extras):
        self.card_presentes.layout().itemAt(2).widget().setText(f"{presentes}/{total}")
        self.card_faltas.layout().itemAt(2).widget().setText(str(faltas))
        self.card_abonadas.layout().itemAt(2).widget().setText(str(abonadas))
        self.card_extras.layout().itemAt(2).widget().setText(str(extras))

    def atualizar_grafico(self, dados_presenca):
        if not dados_presenca:
            self.grafico_table.setRowCount(0)
            self.info_label.show()
            return
        self.info_label.hide()
        self.grafico_table.setRowCount(len(dados_presenca))
        for i, dia in enumerate(dados_presenca):
            percent = int((dia["presentes"] / dia["total"] * 100) if dia["total"] else 0)
            self.grafico_table.setItem(i, 0, QTableWidgetItem(str(dia["dia"])))
            self.grafico_table.setItem(i, 1, QTableWidgetItem(f"{percent}%"))
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(percent)
            bar.setTextVisible(False)
            self.grafico_table.setCellWidget(i, 2, bar)

class AjustesWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.layout = QVBoxLayout(self)
        self._setup_ui()
    
    def _setup_ui(self):
        # Filtros
        filter_layout = QHBoxLayout()
        self.combo_status = QComboBox()
        self.combo_status.addItems(["Todos", "PENDENTE", "APROVADO", "REJEITADO"])
        self.combo_status.currentTextChanged.connect(self._carregar_dados)
        
        self.btn_aprovar = QPushButton("Aprovar")
        self.btn_aprovar.setStyleSheet("background-color: #2e7d32; color: white;")
        self.btn_aprovar.clicked.connect(self._aprovar)
        self.btn_aprovar.setEnabled(False)
        
        self.btn_rejeitar = QPushButton("Rejeitar")
        self.btn_rejeitar.setStyleSheet("background-color: #c62828; color: white;")
        self.btn_rejeitar.clicked.connect(self._rejeitar)
        self.btn_rejeitar.setEnabled(False)
        
        self.btn_refresh = QPushButton("Atualizar")
        self.btn_refresh.clicked.connect(self._carregar_dados)
        
        filter_layout.addWidget(QLabel("Status:"))
        filter_layout.addWidget(self.combo_status)
        filter_layout.addWidget(self.btn_aprovar)
        filter_layout.addWidget(self.btn_rejeitar)
        filter_layout.addWidget(self.btn_refresh)
        filter_layout.addStretch()
        
        self.layout.addLayout(filter_layout)
        
        # Tabela
        self.tabela = StyledTableWidget()
        self.tabela.setColumnCount(8)
        self.tabela.setHorizontalHeaderLabels([
            "ID", "Funcionário", "Data", "Hora", "Tipo", "Observação", "Status", "Criado em"
        ])
        self.tabela.itemSelectionChanged.connect(self._on_selection_change)
        
        self.layout.addWidget(self.tabela)
    
    def _carregar_dados(self):
        status = self.combo_status.currentText()
        if status == "Todos":
            status = None
            
        ajustes = self.parent.db.obter_ajustes(status)
        self.tabela.setRowCount(len(ajustes))
        
        for i, aj in enumerate(ajustes):
            self.tabela.setItem(i, 0, QTableWidgetItem(str(aj["id"])))
            self.tabela.setItem(i, 1, QTableWidgetItem(aj.get("funcionario_nome") or aj.get("cpf")))
            self.tabela.setItem(i, 2, QTableWidgetItem(aj["data"]))
            self.tabela.setItem(i, 3, QTableWidgetItem(aj["hora"]))
            self.tabela.setItem(i, 4, QTableWidgetItem(aj["tipo"]))
            self.tabela.setItem(i, 5, QTableWidgetItem(aj.get("observacao") or ""))
            self.tabela.setItem(i, 6, QTableWidgetItem(aj["status"]))
            self.tabela.setItem(i, 7, QTableWidgetItem(aj["created_at"]))
            
    def _on_selection_change(self):
        rows = self.tabela.selectionModel().selectedRows()
        if not rows:
            self.btn_aprovar.setEnabled(False)
            self.btn_rejeitar.setEnabled(False)
            return
            
        # Obter status da linha selecionada
        row = rows[0].row()
        status_item = self.tabela.item(row, 6)
        if status_item and status_item.text() == "PENDENTE":
            self.btn_aprovar.setEnabled(True)
            self.btn_rejeitar.setEnabled(True)
        else:
            self.btn_aprovar.setEnabled(False)
            self.btn_rejeitar.setEnabled(False)

    def _obter_id_selecionado(self):
        rows = self.tabela.selectionModel().selectedRows()
        if rows:
            return int(self.tabela.item(rows[0].row(), 0).text())
        return None

    def _aprovar(self):
        ajuste_id = self._obter_id_selecionado()
        if not ajuste_id: return
        
        # Verificar permissão admin
        usuario = self.parent.auth.get_current_user()
        if usuario and usuario.get("role") != "admin":
            QMessageBox.warning(self, "Acesso Negado", "Apenas administradores podem aprovar ajustes.")
            return

        try:
            user_name = usuario.get("username") if usuario else "admin"
            self.parent.db.atualizar_status_ajuste(ajuste_id, "APROVADO", user_name)
            self._carregar_dados()
            QMessageBox.information(self, "Sucesso", "Ajuste aprovado!")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao aprovar: {e}")

    def _rejeitar(self):
        ajuste_id = self._obter_id_selecionado()
        if not ajuste_id: return
        
        usuario = self.parent.auth.get_current_user()
        if usuario and usuario.get("role") != "admin":
            QMessageBox.warning(self, "Acesso Negado", "Apenas administradores podem rejeitar ajustes.")
            return

        try:
            user_name = usuario.get("username") if usuario else "admin"
            self.parent.db.atualizar_status_ajuste(ajuste_id, "REJEITADO", user_name)
            self._carregar_dados()
            QMessageBox.information(self, "Sucesso", "Ajuste rejeitado!")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao rejeitar: {e}")
