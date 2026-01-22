import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QDateEdit, QTimeEdit, QDialogButtonBox, QComboBox, QSpinBox, QCheckBox,
    QFileDialog, QMessageBox, QLabel, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QWidget
)
from PyQt6.QtCore import QDate, QTime, Qt
from PyQt6.QtGui import QGuiApplication, QIcon
from pathlib import Path
import os
from datetime import datetime

from models.entities import Funcionario
from config.settings import config
from database.operations import DatabaseManager

class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        logging.info("LoginDialog initializing...")
        self.setWindowTitle("Login")
        dpi_x = QGuiApplication.primaryScreen().logicalDotsPerInchX() if QGuiApplication.primaryScreen() else 96.0
        width_px = int(5.9055 * dpi_x)
        self.setFixedSize(width_px, 280)
        layout = QVBoxLayout(self)
        self.setStyleSheet(
            """
            QDialog { background: #f9f9fb; }
            QLabel#title { font-size: 20px; font-weight: 600; }
            QLabel#subtitle { color: #555; }
            QLineEdit { padding: 8px; border: 1px solid #cfd8dc; border-radius: 6px; }
            QCheckBox { color: #333; }
            QPushButton { background: #1976d2; color: #fff; border: none; border-radius: 6px; padding: 8px 12px; }
            QPushButton:hover { background: #1565c0; }
            QPushButton:disabled { background: #9e9e9e; }
            """
        )
        
        title = QLabel("Login")
        title.setObjectName("title")
        subtitle = QLabel("Entre com seus dados corretamente para acessar o sistema.")
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        
        form = QFormLayout()
        self.txt_user = QLineEdit()
        self.txt_user.setPlaceholderText("E-mail ou usuário")
        last_user = config.get("APP", "last_user", "")
        if last_user:
            self.txt_user.setText(last_user)
        
        self.txt_pass = QLineEdit()
        self.txt_pass.setPlaceholderText("Senha")
        self.txt_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.chk_show = QCheckBox("Mostrar senha")
        self.chk_show.toggled.connect(lambda v: self.txt_pass.setEchoMode(QLineEdit.EchoMode.Normal if v else QLineEdit.EchoMode.Password))
        
        form.addRow("E-mail:", self.txt_user)
        form.addRow("Senha:", self.txt_pass)
        form.addRow("", self.chk_show)
        layout.addLayout(form)
        
        row = QHBoxLayout()
        self.remember = QCheckBox("Lembrar-me")
        self.remember.setChecked(config.get("APP", "remember_user", "1") == "1")
        
        self.forgot = QLabel("<a href='#'>Esqueci minha senha</a>")
        self.forgot.setOpenExternalLinks(False)
        self.forgot.linkActivated.connect(self._on_forgot)
        
        row.addWidget(self.remember)
        row.addStretch()
        row.addWidget(self.forgot)
        layout.addLayout(row)
        
        self.btn_ok = QPushButton("Entrar")
        self.btn_ok.clicked.connect(self._on_accept)
        layout.addWidget(self.btn_ok)
        
        self.txt_user.returnPressed.connect(self._on_accept)
        self.txt_pass.returnPressed.connect(self._on_accept)
    
    def get_credentials(self):
        return (self.txt_user.text().strip(), self.txt_pass.text())
    
    def _on_forgot(self):
        QMessageBox.information(self, "Recuperação de senha", "Contate o administrador para redefinir sua senha.")
    
    def _on_accept(self):
        if self.remember.isChecked():
            try:
                config.set("APP", "last_user", self.txt_user.text().strip())
                config.set("APP", "remember_user", "1")
                config.save()
            except Exception:
                pass
        else:
            try:
                config.set("APP", "remember_user", "0")
                config.save()
            except Exception:
                pass
        if not self.txt_user.text().strip():
            QMessageBox.warning(self, "Validação", "Informe seu e-mail ou usuário.")
            return
        if not self.txt_pass.text():
            QMessageBox.warning(self, "Validação", "Informe sua senha.")
            return
        self.accept()

class FuncionarioDialog(QDialog):
    def __init__(self, parent=None, funcionario: Funcionario = None):
        super().__init__(parent)
        self.funcionario = funcionario or Funcionario()
        self.setWindowTitle("Editar Funcionário" if funcionario else "Novo Funcionário")
        self.setMinimumWidth(420)
        layout = QFormLayout(self)
        self.nome_edit = QLineEdit()
        self.nome_edit.setText(self.funcionario.nome)
        self.cpf_edit = QLineEdit()
        self.cpf_edit.setText(self.funcionario.cpf)
        if funcionario:
            self.cpf_edit.setEnabled(False)
        self.pis_edit = QLineEdit()
        self.pis_edit.setText(self.funcionario.pis or "")
        self.cargo_edit = QLineEdit()
        self.cargo_edit.setText(self.funcionario.cargo)
        self.departamento_edit = QLineEdit()
        self.departamento_edit.setText(self.funcionario.departamento)
        
        # Carga horária em formato HH:mm
        self.carga_time = QTimeEdit()
        self.carga_time.setDisplayFormat("HH:mm")
        # Converter minutos para QTime
        total_min = self.funcionario.carga_horaria_min
        horas = total_min // 60
        minutos = total_min % 60
        self.carga_time.setTime(QTime(horas, minutos))
        
        self.email_edit = QLineEdit()
        self.email_edit.setText(self.funcionario.email)
        self.pin_edit = QLineEdit()
        self.pin_edit.setText(self.funcionario.pin)
        self.pin_edit.setMaxLength(4)
        self.pin_edit.setPlaceholderText("4 dígitos")
        self.entrada_edit = QTimeEdit()
        self.entrada_edit.setDisplayFormat("HH:mm")
        self.entrada_edit.setTime(QTime.fromString(self.funcionario.hora_entrada, "HH:mm"))
        self.saida_edit = QTimeEdit()
        self.saida_edit.setDisplayFormat("HH:mm")
        self.saida_edit.setTime(QTime.fromString(self.funcionario.hora_saida, "HH:mm"))
        self.ativo_check = QCheckBox()
        self.ativo_check.setChecked(self.funcionario.ativo)
        layout.addRow("Nome *", self.nome_edit)
        layout.addRow("CPF *", self.cpf_edit)
        layout.addRow("PIS", self.pis_edit)
        layout.addRow("PIN (4 dígitos)", self.pin_edit)
        layout.addRow("Cargo", self.cargo_edit)
        layout.addRow("Departamento", self.departamento_edit)
        layout.addRow("Carga Horária Diária", self.carga_time)
        layout.addRow("Email", self.email_edit)
        layout.addRow("Entrada Padrão", self.entrada_edit)
        layout.addRow("Saída Padrão", self.saida_edit)
        layout.addRow("Ativo", self.ativo_check)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
    
    def validate_and_accept(self):
        if not self.nome_edit.text().strip():
            QMessageBox.warning(self, "Validação", "O nome é obrigatório.")
            return
        if not self.cpf_edit.text().strip():
            QMessageBox.warning(self, "Validação", "O CPF é obrigatório.")
            return
        self.accept()
    
    def get_funcionario_data(self) -> Funcionario:
        self.funcionario.nome = self.nome_edit.text().strip()
        self.funcionario.cpf = self.cpf_edit.text().strip()
        self.funcionario.pis = self.pis_edit.text().strip()
        self.funcionario.pin = self.pin_edit.text().strip()
        self.funcionario.cargo = self.cargo_edit.text().strip()
        self.funcionario.departamento = self.departamento_edit.text().strip()
        
        # Converter QTime para minutos
        t = self.carga_time.time()
        self.funcionario.carga_horaria_min = t.hour() * 60 + t.minute()
        
        self.funcionario.email = self.email_edit.text().strip()
        self.funcionario.hora_entrada = self.entrada_edit.time().toString("HH:mm")
        self.funcionario.hora_saida = self.saida_edit.time().toString("HH:mm")
        self.funcionario.ativo = self.ativo_check.isChecked()
        return self.funcionario

class RetroactiveDateTimeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Registro Retroativo")
        self.setFixedSize(300, 150)
        self.result = (None, None)
        layout = QFormLayout(self)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.time_edit = QTimeEdit()
        self.time_edit.setTime(QTime.currentTime())
        self.time_edit.setDisplayFormat("HH:mm:ss")
        layout.addRow("Data:", self.date_edit)
        layout.addRow("Hora:", self.time_edit)
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)
    
    def accept(self):
        self.result = (
            self.date_edit.date().toString("yyyy-MM-dd"),
            self.time_edit.time().toString("HH:mm:ss")
        )
        super().accept()
    
    def get_datetime(self):
        return self.result

class RegistroDetalhesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Detalhes da Marcação")
        self.setFixedSize(380, 160)
        self.result = {"lat": None, "lng": None, "foto": None}
        layout = QFormLayout(self)
        self.lat_edit = QLineEdit()
        self.lat_edit.setPlaceholderText("Latitude")
        self.lng_edit = QLineEdit()
        self.lng_edit.setPlaceholderText("Longitude")
        h = QHBoxLayout()
        self.foto_edit = QLineEdit()
        self.foto_edit.setPlaceholderText("Caminho da foto")
        btn_escolher = QPushButton("Escolher...")
        btn_escolher.clicked.connect(self._choose_file)
        btn_webcam = QPushButton("Capturar Webcam")
        btn_webcam.clicked.connect(self._capture_webcam)
        h.addWidget(self.foto_edit)
        h.addWidget(btn_escolher)
        h.addWidget(btn_webcam)
        layout.addRow("Latitude", self.lat_edit)
        layout.addRow("Longitude", self.lng_edit)
        layout.addRow("Foto", h)
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)
    
    def _choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 
            "Selecione a foto", 
            str(Path.home()), 
            "Imagens (*.png *.jpg *.jpeg)"
        )
        if path:
            self.foto_edit.setText(path)
    
    def _capture_webcam(self):
        try:
            import cv2
            cap = cv2.VideoCapture(0)
            ok, frame = cap.read()
            cap.release()
            if ok:
                outdir = os.path.join(Path.home(), "Pictures")
                os.makedirs(outdir, exist_ok=True)
                path = os.path.join(outdir, f"ponto_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
                cv2.imwrite(path, frame)
                self.foto_edit.setText(path)
                QMessageBox.information(self, "Webcam", "Foto capturada com sucesso.")
            else:
                QMessageBox.warning(self, "Webcam", "Falha ao capturar imagem.")
        except Exception as e:
            QMessageBox.warning(self, "Webcam", f"Webcam indisponível: {e}")
    
    def accept(self):
        try:
            lat = float(self.lat_edit.text()) if self.lat_edit.text().strip() else None
        except ValueError:
            lat = None
        try:
            lng = float(self.lng_edit.text()) if self.lng_edit.text().strip() else None
        except ValueError:
            lng = None
        foto = self.foto_edit.text().strip() or None
        self.result = {"lat": lat, "lng": lng, "foto": foto}
        super().accept()
    
    def get_data(self):
        return self.result

class ExtraNoturnaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Extra Noturna")
        self.setFixedSize(300, 150)
        layout = QFormLayout(self)
        self.ini = QTimeEdit()
        self.ini.setDisplayFormat("HH:mm:ss")
        self.ini.setTime(QTime(22, 0, 0))
        self.fim = QTimeEdit()
        self.fim.setDisplayFormat("HH:mm:ss")
        self.fim.setTime(QTime(5, 0, 0))
        layout.addRow("Início", self.ini)
        layout.addRow("Fim", self.fim)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)
    
    def get_times(self):
        return (
            self.ini.time().toString("HH:mm:ss"),
            self.fim.time().toString("HH:mm:ss")
        )

class AjustePontoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Solicitar Ajuste de Ponto")
        self.setFixedSize(400, 200)
        layout = QFormLayout(self)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.time_edit = QTimeEdit()
        self.time_edit.setTime(QTime.currentTime())
        self.time_edit.setDisplayFormat("HH:mm:ss")
        self.tipo_combo = QComboBox()
        self.tipo_combo.addItem("Entrada")
        self.tipo_combo.addItem("Saída Almoço")
        self.tipo_combo.addItem("Retorno Almoço")
        self.tipo_combo.addItem("Saída Final")
        self.tipo_combo.addItem("Extra Noturna")
        self.tipo_combo.addItems(["Atestado", "Folga", "Abono"])
        self.observacao_edit = QLineEdit()
        self.observacao_edit.setPlaceholderText("Observação (opcional)")
        layout.addRow("Data *", self.date_edit)
        layout.addRow("Hora *", self.time_edit)
        layout.addRow("Tipo *", self.tipo_combo)
        layout.addRow("Observação", self.observacao_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
    
    def get_data(self):
        return {
            "data": self.date_edit.date().toString("yyyy-MM-dd"),
            "hora": self.time_edit.time().toString("HH:mm:ss"),
            "tipo": self.tipo_combo.currentText(),
            "observacao": self.observacao_edit.text().strip(),
        }

class ConfiguracoesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.db = DatabaseManager()
        self.setWindowTitle("Configurações do Sistema")
        self.setMinimumSize(600, 500)
        layout = QVBoxLayout(self)
        
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # Aba Geral (APP + UI)
        self.tab_geral = QWidget()
        self._setup_tab_geral()
        self.tabs.addTab(self.tab_geral, "Geral")
        
        # Aba Banco de Dados
        self.tab_db = QWidget()
        self._setup_tab_db()
        self.tabs.addTab(self.tab_db, "Banco de Dados")
        
        # Aba Email
        self.tab_email = QWidget()
        self._setup_tab_email()
        self.tabs.addTab(self.tab_email, "Email")
        
        # Aba Segurança
        self.tab_security = QWidget()
        self._setup_tab_security()
        self.tabs.addTab(self.tab_security, "Segurança")

        # Aba Feriados
        self.tab_feriados = QWidget()
        self._setup_tab_feriados()
        self.tabs.addTab(self.tab_feriados, "Feriados")

        # Aba Empresa
        self.tab_empresa = QWidget()
        self._setup_tab_empresa()
        self.tabs.addTab(self.tab_empresa, "Empresa")
        
        # Botões
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | 
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def _setup_tab_geral(self):
        layout = QFormLayout(self.tab_geral)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["light", "dark"])
        self.theme_combo.setCurrentText(config.get("UI", "theme", "dark"))
        
        self.font_family = QLineEdit(config.get("UI", "font_family", "Segoe UI"))
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 24)
        self.font_size.setValue(int(config.get("UI", "font_size", "10")))
        
        self.remember_user = QCheckBox("Lembrar último usuário")
        self.remember_user.setChecked(config.get("APP", "remember_user", "1") == "1")
        
        layout.addRow("Tema:", self.theme_combo)
        layout.addRow("Fonte:", self.font_family)
        layout.addRow("Tamanho da Fonte:", self.font_size)
        layout.addRow("", self.remember_user)
        
    def _setup_tab_db(self):
        layout = QFormLayout(self.tab_db)
        
        self.db_path = QLineEdit(config.get("DATABASE", "path", ""))
        self.db_path.setReadOnly(True)  # Melhor não editar manualmente para evitar quebra
        
        self.backup_dir = QLineEdit(config.get("DATABASE", "backup_dir", ""))
        btn_backup = QPushButton("Selecionar Pasta...")
        btn_backup.clicked.connect(self._select_backup_dir)
        
        h_backup = QHBoxLayout()
        h_backup.addWidget(self.backup_dir)
        h_backup.addWidget(btn_backup)
        
        layout.addRow("Caminho do Banco:", self.db_path)
        layout.addRow("Diretório de Backup:", h_backup)
        layout.addRow(QLabel("Nota: O caminho do banco deve ser alterado via config.ini se necessário."))

    def _setup_tab_email(self):
        layout = QFormLayout(self.tab_email)
        
        self.smtp_host = QLineEdit(config.get("EMAIL", "smtp_host", "localhost"))
        self.smtp_port = QSpinBox()
        self.smtp_port.setRange(1, 65535)
        self.smtp_port.setValue(int(config.get("EMAIL", "smtp_port", "25")))
        
        self.smtp_user = QLineEdit(config.get("EMAIL", "smtp_user", ""))
        self.smtp_pass = QLineEdit(config.get("EMAIL", "smtp_pass", ""))
        self.smtp_pass.setEchoMode(QLineEdit.EchoMode.Password)
        
        self.notify_enabled = QCheckBox("Habilitar Notificações")
        self.notify_enabled.setChecked(config.get("EMAIL", "notify_enabled", "0") == "1")
        
        layout.addRow("SMTP Host:", self.smtp_host)
        layout.addRow("SMTP Port:", self.smtp_port)
        layout.addRow("Usuário:", self.smtp_user)
        layout.addRow("Senha:", self.smtp_pass)
        layout.addRow("", self.notify_enabled)

    def _setup_tab_security(self):
        layout = QFormLayout(self.tab_security)
        
        self.use_2fa = QCheckBox("Exigir 2FA (Autenticação de Dois Fatores)")
        self.use_2fa.setChecked(config.get("SECURITY", "use_2fa", "0") == "1")
        
        self.max_attempts = QSpinBox()
        self.max_attempts.setRange(1, 10)
        self.max_attempts.setValue(int(config.get("SECURITY", "max_login_attempts", "5")))
        
        self.lockout = QSpinBox()
        self.lockout.setRange(1, 1440)
        self.lockout.setValue(int(config.get("SECURITY", "lockout_minutes", "15")))
        
        layout.addRow("", self.use_2fa)
        layout.addRow("Max. Tentativas Login:", self.max_attempts)
        layout.addRow("Tempo de Bloqueio (min):", self.lockout)

    def _setup_tab_feriados(self):
        layout = QVBoxLayout(self.tab_feriados)
        
        # Tabela de Feriados
        self.tabela_feriados = QTableWidget(0, 2)
        self.tabela_feriados.setHorizontalHeaderLabels(["Data", "Descrição"])
        self.tabela_feriados.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.tabela_feriados)
        
        # Controles
        form = QHBoxLayout()
        self.date_feriado = QDateEdit()
        self.date_feriado.setCalendarPopup(True)
        self.date_feriado.setDate(QDate.currentDate())
        
        self.desc_feriado = QLineEdit()
        self.desc_feriado.setPlaceholderText("Descrição do Feriado")
        
        btn_add = QPushButton("Adicionar")
        btn_add.clicked.connect(self._adicionar_feriado)
        
        btn_del = QPushButton("Remover Selecionado")
        btn_del.clicked.connect(self._remover_feriado)
        
        form.addWidget(self.date_feriado)
        form.addWidget(self.desc_feriado)
        form.addWidget(btn_add)
        form.addWidget(btn_del)
        layout.addLayout(form)
        
        self._carregar_feriados()

    def _setup_tab_empresa(self):
        layout = QFormLayout(self.tab_empresa)
        
        self.empresa_razao = QLineEdit(config.get("EMPRESA", "razao_social", ""))
        self.empresa_razao.setPlaceholderText("Razão Social da Empresa")
        
        self.empresa_cnpj = QLineEdit(config.get("EMPRESA", "cnpj", ""))
        self.empresa_cnpj.setPlaceholderText("00.000.000/0000-00")
        
        self.empresa_endereco = QLineEdit(config.get("EMPRESA", "endereco", ""))
        self.empresa_endereco.setPlaceholderText("Logradouro, Número, Bairro, Cidade - UF")
        
        self.empresa_rep_nome = QLineEdit(config.get("EMPRESA", "rep_nome", ""))
        self.empresa_rep_nome.setPlaceholderText("Nome do Representante Legal") # Para assinatura se precisar
        
        self.empresa_rep_cpf = QLineEdit(config.get("EMPRESA", "rep_cpf", ""))
        self.empresa_rep_cpf.setPlaceholderText("CPF do Representante")

        layout.addRow("Razão Social:", self.empresa_razao)
        layout.addRow("CNPJ:", self.empresa_cnpj)
        layout.addRow("Endereço:", self.empresa_endereco)
        layout.addRow("Representante (Nome):", self.empresa_rep_nome)
        layout.addRow("Representante (CPF):", self.empresa_rep_cpf)

    def _carregar_feriados(self):
        feriados = self.db.obter_feriados()
        self.tabela_feriados.setRowCount(len(feriados))
        for i, f in enumerate(feriados):
            self.tabela_feriados.setItem(i, 0, QTableWidgetItem(f["data"]))
            self.tabela_feriados.setItem(i, 1, QTableWidgetItem(f["descricao"]))

    def _adicionar_feriado(self):
        data = self.date_feriado.date().toString("yyyy-MM-dd")
        desc = self.desc_feriado.text().strip()
        if not desc:
            QMessageBox.warning(self, "Aviso", "Digite a descrição.")
            return
            
        try:
            self.db.adicionar_feriado(data, desc)
            self.desc_feriado.clear()
            self._carregar_feriados()
        except Exception as e:
            QMessageBox.critical(self, "Erro", str(e))

    def _remover_feriado(self):
        row = self.tabela_feriados.currentRow()
        if row < 0:
            return
        data = self.tabela_feriados.item(row, 0).text()
        try:
            self.db.remover_feriado(data)
            self._carregar_feriados()
        except Exception as e:
            QMessageBox.critical(self, "Erro", str(e))

    def _select_backup_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Selecionar Diretório de Backup", self.backup_dir.text())
        if d:
            self.backup_dir.setText(d)

    def _save_and_accept(self):
        try:
            # UI
            config.set("UI", "theme", self.theme_combo.currentText())
            config.set("UI", "font_family", self.font_family.text())
            config.set("UI", "font_size", str(self.font_size.value()))
            
            # APP
            config.set("APP", "remember_user", "1" if self.remember_user.isChecked() else "0")
            
            # DATABASE
            config.set("DATABASE", "backup_dir", self.backup_dir.text())
            
            # EMAIL
            config.set("EMAIL", "smtp_host", self.smtp_host.text())
            config.set("EMAIL", "smtp_port", str(self.smtp_port.value()))
            config.set("EMAIL", "smtp_user", self.smtp_user.text())
            config.set("EMAIL", "smtp_pass", self.smtp_pass.text())
            config.set("EMAIL", "notify_enabled", "1" if self.notify_enabled.isChecked() else "0")
            
            # SECURITY
            config.set("SECURITY", "use_2fa", "1" if self.use_2fa.isChecked() else "0")
            config.set("SECURITY", "max_login_attempts", str(self.max_attempts.value()))
            config.set("SECURITY", "lockout_minutes", str(self.lockout.value()))
            
            # EMPRESA
            config.set("EMPRESA", "razao_social", self.empresa_razao.text())
            config.set("EMPRESA", "cnpj", self.empresa_cnpj.text())
            config.set("EMPRESA", "endereco", self.empresa_endereco.text())
            config.set("EMPRESA", "rep_nome", self.empresa_rep_nome.text())
            config.set("EMPRESA", "rep_cpf", self.empresa_rep_cpf.text())

            config.save()
            QMessageBox.information(self, "Sucesso", "Configurações salvas com sucesso!")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao salvar configurações: {e}")

