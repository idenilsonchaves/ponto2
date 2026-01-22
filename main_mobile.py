import flet as ft
from datetime import datetime, date, timedelta
import sys
import os
import shutil
import traceback
import threading
import time
import webbrowser

# Verificar dependências
try:
    from openpyxl import Workbook
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False
    print("Aviso: openpyxl não instalado. Exportação Excel desabilitada.")

# Adicionar diretório atual ao path para importar módulos do projeto
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from database.operations import db_manager
    from models.entities import RegistroPonto, Funcionario
    from services.auth import auth_service
    from services.reports import report_service
    from config.settings import config
    from utils.helpers import FileUtils
except ImportError as e:
    print(f"Erro ao importar módulos: {e}")
    print("Certifique-se de que os módulos database, models, services e config existem.")
    sys.exit(1)

# Garantir que os diretórios necessários existam
FileUtils.garantir_diretorios(config.base_dir)

def safe_update(control, update_func):
    """Atualiza controle com tratamento de erro"""
    try:
        update_func()
        if hasattr(control, 'update'):
            # Só tenta atualizar se o controle estiver anexado a uma página
            if hasattr(control, 'page') and control.page:
                control.update()
    except Exception as e:
        # Silencia erros de UI que não afetam funcionalidade
        pass

def safe_page_update(page):
    """Atualiza página com tratamento de erro silenciado"""
    try:
        if page:
            page.update()
    except Exception:
        pass

def main(page: ft.Page):
    page.title = "Ponto Eletrônico - Tablet"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 5  # Reduzido para mobile
    page.window_min_width = 320  # Para mobile
    page.window_min_height = 480  # Para mobile
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    
    # Configurar viewport para mobile
    page.window_width = 800
    page.window_height = 600
    
    # Estado da aplicação
    current_mode = "pin"
    last_screen_width = 0
    current_funcionario = None
    admin_user = None
    
    # --- FUNÇÕES AUXILIARES ---
    def get_screen_width(preferred_width: int | float | None = None):
        nonlocal last_screen_width
        widths = []
        if preferred_width and preferred_width > 0:
            widths.append(preferred_width)
        
        # Tentar obter width da janela
        for attr in ("width", "window_width"):
            val = getattr(page, attr, None)
            if val:
                widths.append(val)
                break
        
        # Usar o último valor conhecido ou default
        for candidate in widths:
            if candidate and candidate > 0:
                last_screen_width = candidate
                return candidate
        
        return last_screen_width or 800

    def on_resize(e):
        """Atualiza layout quando a tela é redimensionada"""
        try:
            nonlocal current_funcionario
            if current_funcionario:
                show_ponto_actions()
            else:
                reset_ponto_screen()
            
            # Só atualizar se a página já tiver controles adicionados
            if page.controls:
                safe_page_update(page)
        except Exception as ex:
            print(f"Erro ignorado no on_resize: {ex}")

    def show_msg(msg, color=ft.Colors.GREEN):
        """Exibe mensagem no SnackBar"""
        try:
            page.snack_bar = ft.SnackBar(ft.Text(str(msg)), bgcolor=color)
            page.snack_bar.open = True
            safe_page_update(page)
        except Exception:
            pass

    page.on_resize = on_resize
    
    # --- ELEMENTOS DA ABA PONTO ---
    txt_pin = ft.TextField(
        label="Digite seu PIN ou CPF",
        text_align=ft.TextAlign.CENTER,
        width=300,
        text_size=20,  # Reduzido para mobile
        keyboard_type=ft.KeyboardType.NUMBER,
        input_filter=ft.InputFilter(allow=True, regex_string=r"[0-9]", replacement_string="")
    )
    
    lbl_status_ponto = ft.Text("", size=14, color=ft.Colors.RED)  # Reduzido
    container_ponto = ft.Container(expand=True)
    
    # --- ELEMENTOS DA ABA ADMIN ---
    txt_user_admin = ft.TextField(label="Usuário", width=300)
    txt_pass_admin = ft.TextField(label="Senha", password=True, can_reveal_password=True, width=300)
    lbl_status_admin = ft.Text("", color=ft.Colors.RED)
    container_admin = ft.Container(expand=True)
    
    # Configurações
    tf_empresa = ft.TextField(label="Nome da Empresa")
    tf_cnpj = ft.TextField(label="CNPJ")
    tf_tolerancia = ft.TextField(label="Tolerância (minutos)", keyboard_type=ft.KeyboardType.NUMBER)
    tf_fechamento = ft.TextField(label="Dia de Fechamento", keyboard_type=ft.KeyboardType.NUMBER)
    
    # Dashboard Admin
    dd_funcionarios = ft.Dropdown(label="Funcionário", width=300)  # Reduzido para mobile
    dd_mes = ft.Dropdown(
        label="Mês",
        width=120,  # Reduzido
        options=[ft.dropdown.Option(str(i), str(i)) for i in range(1, 13)],
        value=str(datetime.now().month)
    )
    dd_ano = ft.Dropdown(
        label="Ano",
        width=120,  # Reduzido
        options=[ft.dropdown.Option(str(i), str(i)) for i in range(2024, 2031)],
        value=str(datetime.now().year)
    )
    lbl_report_result = ft.Text()
    
    # --- VALIDAÇÕES ---
    def validar_sequencia_registros(cpf, data_str, tipo_registro):
        """Valida a sequência lógica dos registros de ponto"""
        registro_dia = db_manager.obter_registro_do_dia(cpf, data_str)
        if not registro_dia:
            if tipo_registro != "ENTRADA":
                return False, "Registre a entrada primeiro"
            return True, None
        
        tem_entrada = bool(registro_dia.get("hora_entrada"))
        tem_saida_almoco = bool(registro_dia.get("saida_almoco"))
        tem_retorno = bool(registro_dia.get("retorno_almoco"))
        tem_saida_final = bool(registro_dia.get("saida_final") or registro_dia.get("hora_saida"))
        
        sequencia_esperada = {
            "ENTRADA": not tem_entrada,
            "SAIDA_ALMOCO": tem_entrada and not tem_saida_almoco,
            "RETORNO_ALMOCO": tem_saida_almoco and not tem_retorno,
            "SAIDA_FINAL": (tem_entrada and (tem_retorno or not tem_saida_almoco)) and not tem_saida_final
        }
        
        if not sequencia_esperada.get(tipo_registro, False):
            mensagens = {
                "ENTRADA": "Entrada já registrada hoje",
                "SAIDA_ALMOCO": "Registre a entrada primeiro",
                "RETORNO_ALMOCO": "Registre a saída para almoço primeiro",
                "SAIDA_FINAL": "Registre a entrada primeiro"
            }
            return False, mensagens.get(tipo_registro, "Sequência de registros inválida")
        
        return True, None

    def verificar_duplicata(cpf, data_str, hora_str, tipo_registro):
        """Verifica se já existe registro no mesmo minuto"""
        registro_dia = db_manager.obter_registro_do_dia(cpf, data_str)
        if not registro_dia:
            return False
        
        hora_atual = datetime.strptime(f"{data_str} {hora_str}", "%Y-%m-%d %H:%M:%S")
        campos = {
            "ENTRADA": registro_dia.get("hora_entrada"),
            "SAIDA_ALMOCO": registro_dia.get("saida_almoco"),
            "RETORNO_ALMOCO": registro_dia.get("retorno_almoco"),
            "SAIDA_FINAL": registro_dia.get("saida_final") or registro_dia.get("hora_saida")
        }
        
        hora_existente = campos.get(tipo_registro)
        if hora_existente:
            try:
                hora_exist = datetime.strptime(f"{data_str} {hora_existente}", "%Y-%m-%d %H:%M:%S")
                diff_seconds = abs((hora_atual - hora_exist).total_seconds())
                if diff_seconds < 60:
                    return True
            except:
                pass
        
        return False
    
    # --- LÓGICA DO PONTO ---
    def registrar_ponto(tipo_registro, custom_datetime=None, obs=None, lat=None, lng=None, foto_path=None):
        nonlocal current_funcionario
        
        if not current_funcionario:
            page.snack_bar = ft.SnackBar(ft.Text("Erro: Nenhum funcionário selecionado"), bgcolor=ft.Colors.RED)
            page.snack_bar.open = True
            safe_page_update(page)
            return
        
        # Mostrar indicador de progresso
        progress = ft.ProgressRing()
        page.add(progress)
        safe_page_update(page)
        
        try:
            cpf = current_funcionario.cpf
            now = custom_datetime if custom_datetime else datetime.now()
            data_str = now.strftime("%Y-%m-%d")
            hora_str = now.strftime("%H:%M:%S")
            
            # Validações apenas para registros em tempo real
            if not custom_datetime:
                valido, msg = validar_sequencia_registros(cpf, data_str, tipo_registro)
                if not valido:
                    page.snack_bar = ft.SnackBar(ft.Text(f"Erro: {msg}"), bgcolor=ft.Colors.RED)
                    page.snack_bar.open = True
                    safe_page_update(page)
                    return
                
                if verificar_duplicata(cpf, data_str, hora_str, tipo_registro):
                    page.snack_bar = ft.SnackBar(ft.Text("Atenção: Registro já feito neste minuto!"), bgcolor=ft.Colors.ORANGE)
                    page.snack_bar.open = True
                    safe_page_update(page)
                    return
            
            # Criar registro
            registro = RegistroPonto(
                funcionario_id=current_funcionario.id,
                cpf=cpf,
                data=data_str,
                tipo=tipo_registro,
                ts=f"{data_str} {hora_str}",
                ts_device=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ts_server=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                device_id="tablet_android"
            )
            
            # Adicionar detalhes
            if lat:
                try:
                    registro.gps_lat = float(lat)
                except (ValueError, TypeError):
                    pass
            if lng:
                try:
                    registro.gps_lng = float(lng)
                except (ValueError, TypeError):
                    pass
            if obs:
                registro.obs = obs
            if foto_path:
                registro.foto_path = foto_path
            
            # Definir horário conforme tipo
            if tipo_registro == "ENTRADA":
                registro.hora_entrada = hora_str
            elif tipo_registro == "SAIDA_ALMOCO":
                registro.saida_almoco = hora_str
            elif tipo_registro == "RETORNO_ALMOCO":
                registro.retorno_almoco = hora_str
            elif tipo_registro == "SAIDA_FINAL":
                registro.saida_final = hora_str
                registro.hora_saida = hora_str
            
            # Verificar se já existe registro para o dia
            registro_existente = db_manager.obter_registro_do_dia(cpf, data_str)
            if registro_existente:
                registro.id = registro_existente["id"]
                registro.hora_entrada = registro.hora_entrada or registro_existente.get("hora_entrada")
                registro.saida_almoco = registro.saida_almoco or registro_existente.get("saida_almoco")
                registro.retorno_almoco = registro.retorno_almoco or registro_existente.get("retorno_almoco")
                registro.saida_final = registro.saida_final or registro_existente.get("saida_final")
                registro.hora_saida = registro.hora_saida or registro_existente.get("hora_saida")
            
            # Salvar no banco
            db_manager.salvar_registro(registro)
            
            # Feedback de sucesso
            msg_sucesso = f"{tipo_registro.replace('_', ' ')} registrado com sucesso!"
            
            # SnackBar
            page.snack_bar = ft.SnackBar(
                ft.Text(msg_sucesso),
                bgcolor=ft.Colors.GREEN
            )
            page.snack_bar.open = True
            
            reset_ponto_screen()
            
        except Exception as e:
            page.snack_bar = ft.SnackBar(
                ft.Text(f"Erro ao registrar ponto: {str(e)}"),
                bgcolor=ft.Colors.RED
            )
            page.snack_bar.open = True
        finally:
            page.remove(progress)
            safe_page_update(page)

    def verificar_pin(e):
        nonlocal current_funcionario
        pin = txt_pin.value.strip()
        
        if not pin:
            lbl_status_ponto.value = "Digite o PIN ou CPF."
            safe_update(lbl_status_ponto, lambda: None)
            return
        
        # Buscar funcionário
        funcionario = db_manager.obter_funcionario_por_pin(pin)
        if not funcionario:
            funcionario = db_manager.obter_funcionario_por_cpf(pin)
        
        if funcionario and funcionario.ativo:
            current_funcionario = funcionario
            show_ponto_actions()
        else:
            lbl_status_ponto.value = "Funcionário não encontrado ou inativo."
            safe_update(lbl_status_ponto, lambda: None)
            txt_pin.value = ""
            txt_pin.focus()
            safe_update(txt_pin, lambda: None)

    def reset_ponto_screen(update_view=True):
        nonlocal current_funcionario
        current_funcionario = None
        txt_pin.value = ""
        lbl_status_ponto.value = ""
        
        screen_width = get_screen_width()
        pin_width = min(300, int(screen_width * 0.9)) if screen_width else 250  # Ajustado para mobile
        txt_pin.width = pin_width
        
        content = ft.Column(
            [
                ft.Icon(ft.Icons.ACCESS_TIME, size=48, color=ft.Colors.BLUE),  # Reduzido
                ft.Text("Ponto Eletrônico", size=24, weight=ft.FontWeight.BOLD),  # Reduzido
                ft.Container(height=15),
                txt_pin,
                ft.Container(height=10),
                ft.FilledButton("Entrar", on_click=verificar_pin, height=45, width=200),
                ft.Container(height=10),
                lbl_status_ponto,
                ft.Container(height=15),
                ft.FilledTonalButton(
                    "Solicitar Abono / Justificar Falta",
                    icon=ft.Icons.MEDICAL_SERVICES,
                    on_click=abrir_dialog_abono,
                    style=ft.ButtonStyle(color=ft.Colors.ORANGE_700)
                ),
                ft.Container(height=20),
                ft.OutlinedButton(
                    "Acessar Sistema Online",
                    icon=ft.Icons.PUBLIC,
                    on_click=lambda _: page.launch_url("http://guaribinhaclube.com/ponto"),
                    width=250
                ),
                ft.Text("(Dados deste App não sincronizam com o site)", size=12, color=ft.Colors.GREY)
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            scroll=ft.ScrollMode.AUTO
        )
        
        container_ponto.content = content
        if update_view:
            safe_update(container_ponto, lambda: None)

    def abrir_dialog_abono(e):
        # Dialog para solicitar abono
        tf_cpf_abono = ft.TextField(label="Seu CPF")
        tf_data_abono = ft.TextField(label="Data (AAAA-MM-DD)", value=date.today().isoformat())
        tf_obs_abono = ft.TextField(label="Motivo / Observação", multiline=True, min_lines=2, max_lines=4)
        dd_tipo_abono = ft.Dropdown(
            label="Tipo",
            options=[
                ft.dropdown.Option("Atestado Médico"),
                ft.dropdown.Option("Folga Combinada"),
                ft.dropdown.Option("Problema Pessoal"),
                ft.dropdown.Option("Outros")
            ],
            value="Atestado Médico"
        )
        
        file_path_ref = ft.Ref[str]()
        
        def on_file_picked(e: ft.FilePickerResultEvent):
            if e.files:
                f = e.files[0]
                file_path_ref.current = f.path
                lbl_file.value = f"Arquivo: {f.name}"
                safe_update(lbl_file, lambda: None)
        
        file_picker = ft.FilePicker(on_result=on_file_picked)
        page.overlay.append(file_picker)
        safe_page_update(page)
        
        lbl_file = ft.Text("Nenhum arquivo selecionado", italic=True, size=12)
        
        def enviar_solicitacao(e):
            if not tf_cpf_abono.value or not tf_data_abono.value:
                page.snack_bar = ft.SnackBar(ft.Text("CPF e Data obrigatórios!"), bgcolor=ft.Colors.RED)
                page.snack_bar.open = True
                safe_page_update(page)
                return
            
            try:
                # Validar data
                datetime.strptime(tf_data_abono.value, "%Y-%m-%d")
                
                # Verificar se funcionário existe
                func = db_manager.obter_funcionario_por_cpf(tf_cpf_abono.value)
                if not func:
                    page.snack_bar = ft.SnackBar(ft.Text("Funcionário não encontrado!"), bgcolor=ft.Colors.RED)
                    page.snack_bar.open = True
                    safe_page_update(page)
                    return
                
                # Copiar arquivo se houver
                final_path = None
                if file_path_ref.current:
                    try:
                        base_docs = os.path.join(os.getcwd(), "assets", "docs")
                        if not os.path.exists(base_docs):
                            os.makedirs(base_docs)
                        
                        fname = os.path.basename(file_path_ref.current)
                        ts = int(datetime.now().timestamp())
                        final_path = os.path.join(base_docs, f"{ts}_{fname}")
                        shutil.copy2(file_path_ref.current, final_path)
                    except Exception as ex_file:
                        print(f"Erro copiando arquivo: {ex_file}")
                
                dados = {
                    "cpf": tf_cpf_abono.value,
                    "data": tf_data_abono.value,
                    "tipo": dd_tipo_abono.value,
                    "hora": "00:00",
                    "observacao": tf_obs_abono.value,
                    "justificativa_path": final_path
                }
                
                db_manager.salvar_ajuste(dados)
                
                dlg_abono.open = False
                safe_page_update(page)
                
                page.snack_bar = ft.SnackBar(ft.Text("Solicitação enviada com sucesso!"), bgcolor=ft.Colors.GREEN)
                page.snack_bar.open = True
                safe_page_update(page)
                
            except ValueError:
                page.snack_bar = ft.SnackBar(ft.Text("Data inválida! Use AAAA-MM-DD"), bgcolor=ft.Colors.RED)
                page.snack_bar.open = True
                safe_page_update(page)
            except Exception as ex:
                page.snack_bar = ft.SnackBar(ft.Text(f"Erro: {ex}"), bgcolor=ft.Colors.RED)
                page.snack_bar.open = True
                safe_page_update(page)
        
        dlg_abono = ft.AlertDialog(
            title=ft.Text("Solicitar Abono"),
            content=ft.Column([
                tf_cpf_abono,
                tf_data_abono,
                dd_tipo_abono,
                tf_obs_abono,
                ft.FilledTonalButton("Anexar Documento", icon=ft.Icons.UPLOAD_FILE,
                                    on_click=lambda _: file_picker.pick_files(allow_multiple=False)),
                lbl_file
            ], tight=True, scroll=ft.ScrollMode.AUTO),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: setattr(dlg_abono, 'open', False) or safe_page_update(page)),
                ft.FilledButton("Enviar", on_click=enviar_solicitacao),
            ]
        )
        page.dialog = dlg_abono
        dlg_abono.open = True
        safe_page_update(page)

    def show_ponto_actions():
        if not current_funcionario:
            reset_ponto_screen()
            return
        
        nome = current_funcionario.nome.split()[0] if current_funcionario.nome else "Funcionário"
        
        def open_retroactive_dialog(e):
            dd_tipo = ft.Dropdown(
                label="Tipo de Registro",
                options=[
                    ft.dropdown.Option("ENTRADA", "Entrada"),
                    ft.dropdown.Option("SAIDA_ALMOCO", "Saída Almoço"),
                    ft.dropdown.Option("RETORNO_ALMOCO", "Retorno Almoço"),
                    ft.dropdown.Option("SAIDA_FINAL", "Saída"),
                ],
                value="ENTRADA"
            )
            
            now = datetime.now()
            tf_data = ft.TextField(label="Data (DD/MM/AAAA)", value=now.strftime("%d/%m/%Y"))
            tf_hora = ft.TextField(label="Hora (HH:MM)", value=now.strftime("%H:%M"))
            
            def confirmar_retroativo(e):
                try:
                    d_str = tf_data.value
                    h_str = tf_hora.value
                    dt_full = datetime.strptime(f"{d_str} {h_str}", "%d/%m/%Y %H:%M")
                    
                    registrar_ponto(dd_tipo.value, custom_datetime=dt_full)
                    dlg_retro.open = False
                    safe_page_update(page)
                except ValueError:
                    page.snack_bar = ft.SnackBar(
                        ft.Text("Formato inválido! Use DD/MM/AAAA e HH:MM"),
                        bgcolor=ft.Colors.RED
                    )
                    page.snack_bar.open = True
                    safe_page_update(page)
                except Exception as ex:
                    page.snack_bar = ft.SnackBar(
                        ft.Text(f"Erro: {ex}"),
                        bgcolor=ft.Colors.RED
                    )
                    page.snack_bar.open = True
                    safe_page_update(page)
            
            dlg_retro = ft.AlertDialog(
                title=ft.Text("Registro Retroativo"),
                content=ft.Column([
                    ft.Text("Use apenas em caso de esquecimento!", size=14),
                    dd_tipo,
                    tf_data,
                    tf_hora
                ], tight=True, scroll=ft.ScrollMode.AUTO),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda _: setattr(dlg_retro, 'open', False) or safe_page_update(page)),
                    ft.FilledButton("Registrar", on_click=confirmar_retroativo),
                ]
            )
            
            page.overlay.append(dlg_retro)
            dlg_retro.open = True
            safe_page_update(page)

        def open_details_dialog(tipo):
            tf_obs = ft.TextField(label="Observação (Opcional)", multiline=True, min_lines=1, max_lines=3)
            
            def pular_e_registrar(e):
                registrar_ponto(tipo)
                dlg_details.open = False
                safe_page_update(page)
            
            def confirmar_com_obs(e):
                obs_final = tf_obs.value if tf_obs.value else None
                registrar_ponto(tipo, obs=obs_final)
                dlg_details.open = False
                safe_page_update(page)
            
            dlg_details = ft.AlertDialog(
                title=ft.Text(f"Registrar {tipo.replace('_', ' ').title()}"),
                content=ft.Column([
                    ft.Text("Deseja adicionar observação?", size=14),
                    tf_obs,
                ], tight=True, scroll=ft.ScrollMode.AUTO),
                actions=[
                    ft.TextButton("Pular", on_click=pular_e_registrar),
                    ft.FilledButton("Confirmar", on_click=confirmar_com_obs),
                ]
            )
            
            page.dialog = dlg_details
            dlg_details.open = True
            safe_page_update(page)
        
        # Layout responsivo
        screen_width = get_screen_width()
        
        # Para mobile, usar botões empilhados verticalmente
        if screen_width < 600:
            container_ponto.content = ft.Column(
                [
                    ft.Text(f"Olá, {nome}!", size=20, weight=ft.FontWeight.BOLD),
                    ft.Text(datetime.now().strftime("%H:%M"), size=32, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE),
                    ft.Container(height=20),
                    ft.FilledButton(
                        "Entrada",
                        icon=ft.Icons.LOGIN,
                        on_click=lambda _: open_details_dialog("ENTRADA"),
                        height=60,
                        style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE)
                    ),
                    ft.Container(height=10),
                    ft.FilledButton(
                        "Saída Almoço",
                        icon=ft.Icons.RESTAURANT,
                        on_click=lambda _: open_details_dialog("SAIDA_ALMOCO"),
                        height=60,
                        style=ft.ButtonStyle(bgcolor=ft.Colors.ORANGE, color=ft.Colors.WHITE)
                    ),
                    ft.Container(height=10),
                    ft.FilledButton(
                        "Volta Almoço",
                        icon=ft.Icons.RESTAURANT_MENU,
                        on_click=lambda _: open_details_dialog("RETORNO_ALMOCO"),
                        height=60,
                        style=ft.ButtonStyle(bgcolor=ft.Colors.ORANGE, color=ft.Colors.WHITE)
                    ),
                    ft.Container(height=10),
                    ft.FilledButton(
                        "Saída",
                        icon=ft.Icons.LOGOUT,
                        on_click=lambda _: open_details_dialog("SAIDA_FINAL"),
                        height=60,
                        style=ft.ButtonStyle(bgcolor=ft.Colors.RED, color=ft.Colors.WHITE)
                    ),
                    ft.Container(height=20),
                    ft.FilledTonalButton(
                        "Esqueci de bater o ponto",
                        icon=ft.Icons.HISTORY,
                        on_click=open_retroactive_dialog
                    ),
                    ft.Container(height=10),
                    ft.TextButton("Sair", on_click=lambda _: reset_ponto_screen(), icon=ft.Icons.ARROW_BACK)
                ],
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                alignment=ft.MainAxisAlignment.CENTER,
                scroll=ft.ScrollMode.AUTO
            )
        else:
            # Para tablet/desktop
            btn_width = min(200, screen_width * 0.4)
            container_ponto.content = ft.Column(
                [
                    ft.Text(f"Olá, {nome}!", size=24, weight=ft.FontWeight.BOLD),
                    ft.Text(datetime.now().strftime("%H:%M"), size=40, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE),
                    ft.Container(height=30),
                    ft.Row(
                        [
                            ft.FilledButton(
                                "Entrada",
                                icon=ft.Icons.LOGIN,
                                on_click=lambda _: open_details_dialog("ENTRADA"),
                                width=btn_width,
                                height=70,
                                style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE)
                            ),
                            ft.FilledButton(
                                "Saída Almoço",
                                icon=ft.Icons.RESTAURANT,
                                on_click=lambda _: open_details_dialog("SAIDA_ALMOCO"),
                                width=btn_width,
                                height=70,
                                style=ft.ButtonStyle(bgcolor=ft.Colors.ORANGE, color=ft.Colors.WHITE)
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=10
                    ),
                    ft.Container(height=10),
                    ft.Row(
                        [
                            ft.FilledButton(
                                "Volta Almoço",
                                icon=ft.Icons.RESTAURANT_MENU,
                                on_click=lambda _: open_details_dialog("RETORNO_ALMOCO"),
                                width=btn_width,
                                height=70,
                                style=ft.ButtonStyle(bgcolor=ft.Colors.ORANGE, color=ft.Colors.WHITE)
                            ),
                            ft.FilledButton(
                                "Saída",
                                icon=ft.Icons.LOGOUT,
                                on_click=lambda _: open_details_dialog("SAIDA_FINAL"),
                                width=btn_width,
                                height=70,
                                style=ft.ButtonStyle(bgcolor=ft.Colors.RED, color=ft.Colors.WHITE)
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=10
                    ),
                    ft.Container(height=20),
                    ft.FilledTonalButton(
                        "Esqueci de bater o ponto (Retroativo)",
                        icon=ft.Icons.HISTORY,
                        on_click=open_retroactive_dialog,
                        width=min(400, screen_width * 0.8)
                    ),
                    ft.Container(height=20),
                    ft.TextButton("Sair", on_click=lambda _: reset_ponto_screen(), icon=ft.Icons.ARROW_BACK)
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                scroll=ft.ScrollMode.AUTO
            )
        
        safe_update(container_ponto, lambda: None)
    
    # --- LÓGICA DE ADMINISTRAÇÃO ---
    def carregar_funcionarios_dropdown():
        try:
            funcs = db_manager.obter_funcionarios(ativos_only=False)
            dd_funcionarios.options = [ft.dropdown.Option(key=str(f.id), text=f"{f.nome} ({f.cpf})") for f in funcs]
            if funcs and not dd_funcionarios.value:
                dd_funcionarios.value = str(funcs[0].id)
            safe_update(dd_funcionarios, lambda: None)
        except Exception as e:
            print(f"Erro ao carregar funcionários: {e}")

    def gerar_relatorio(tipo="html"):
        try:
            if not dd_funcionarios.value:
                lbl_report_result.value = "Selecione um funcionário"
                safe_update(lbl_report_result, lambda: None)
                return
            
            if tipo == "xlsx" and not EXCEL_AVAILABLE:
                page.snack_bar = ft.SnackBar(
                    ft.Text("Exportação Excel requer openpyxl: pip install openpyxl"),
                    bgcolor=ft.Colors.ORANGE
                )
                page.snack_bar.open = True
                safe_page_update(page)
                return
            
            fid = int(dd_funcionarios.value)
            mes = int(dd_mes.value)
            ano = int(dd_ano.value)
            
            # Mostrar progresso
            progress = ft.ProgressRing()
            page.add(progress)
            safe_page_update(page)
            
            try:
                if tipo == "html":
                    path = report_service.gerar_espelho_ponto_html(fid, ano, mes)
                elif tipo == "xlsx":
                    path = report_service.gerar_espelho_ponto_xlsx(fid, ano, mes)
                else:
                    path = report_service.gerar_espelho_ponto_pdf(fid, ano, mes)
                
                # Copiar para assets
                filename = os.path.basename(path)
                assets_dir = os.path.join(os.getcwd(), "assets", "relatorios")
                os.makedirs(assets_dir, exist_ok=True)
                
                assets_path = os.path.join(assets_dir, filename)
                print(f"Gerando relatório: {path} -> {assets_path}")
                shutil.copy(path, assets_path)
                
                lbl_report_result.value = "Relatório gerado com sucesso!"
                lbl_report_result.spans = [
                    ft.TextSpan(
                        " Clique aqui para abrir.",
                        ft.TextStyle(color=ft.Colors.BLUE, decoration=ft.TextDecoration.UNDERLINE),
                        on_click=lambda e: webbrowser.open(assets_path)
                    )
                ]
                
                page.snack_bar = ft.SnackBar(
                    ft.Text(f"Relatório {tipo.upper()} gerado! Abrindo..."),
                    bgcolor=ft.Colors.GREEN
                )
                page.snack_bar.open = True
                safe_page_update(page)
                
                # Tentar abrir automaticamente
                try:
                    webbrowser.open(assets_path)
                except Exception as ex_open:
                    print(f"Erro ao abrir arquivo automaticamente: {ex_open}")
                
            finally:
                page.remove(progress)
                safe_page_update(page)
                
        except ImportError as ie:
            msg = str(ie)
            if "reportlab" in msg:
                msg = "Geração de PDF indisponível neste dispositivo/ambiente."
            
            lbl_report_result.value = f"Erro: {msg}"
            lbl_report_result.spans = []
            safe_update(lbl_report_result, lambda: None)
            
            page.snack_bar = ft.SnackBar(ft.Text(msg), bgcolor=ft.Colors.ORANGE)
            page.snack_bar.open = True
            safe_page_update(page)
            
        except Exception as e:
            lbl_report_result.value = f"Erro ao gerar relatório: {str(e)}"
            lbl_report_result.spans = []
            safe_update(lbl_report_result, lambda: None)
            page.snack_bar = ft.SnackBar(
                ft.Text(f"Erro: {str(e)}"),
                bgcolor=ft.Colors.RED
            )
            page.snack_bar.open = True
            safe_page_update(page)
    
    # --- SUB-VIEWS DO ADMIN ---
    def view_dashboard():
        carregar_funcionarios_dropdown()
        
        # Stats container
        stats_container = ft.Container()
        
        def atualizar_resumo(e=None):
            try:
                if not dd_funcionarios.value:
                    stats_container.content = ft.Text("Selecione um funcionário", color=ft.Colors.GREY)
                    safe_update(stats_container, lambda: None)
                    return
                
                fid = int(dd_funcionarios.value)
                mes = int(dd_mes.value)
                ano = int(dd_ano.value)
                
                relatorio = report_service.gerar_relatorio_mensal(fid, ano, mes)
                totais = relatorio.totais if hasattr(relatorio, 'totais') else {}
                
                def make_stat_card(label, value, color):
                    return ft.Card(
                        content=ft.Container(
                            content=ft.Column(
                                [
                                    ft.Text(label, size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_700),
                                    ft.Text(str(value), size=16, weight=ft.FontWeight.BOLD, color=color)  # Reduzido
                                ],
                                alignment=ft.MainAxisAlignment.CENTER,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER
                            ),
                            padding=10,
                            width=80,  # Reduzido para mobile
                            height=70  # Reduzido
                        )
                    )
                
                stats_container.content = ft.Row(
                    [
                        make_stat_card("Trabalhadas", f"{totais.get('horas_trabalhadas', 0):.1f}h", ft.Colors.BLUE),
                        make_stat_card("Extras 50%", f"{totais.get('extras_50', 0):.1f}h", ft.Colors.GREEN),
                        make_stat_card("Atrasos", f"{totais.get('atrasos', 0):.1f}h", ft.Colors.ORANGE),
                        make_stat_card("Faltas", str(totais.get('faltas', 0)), ft.Colors.RED),
                    ],
                    scroll=ft.ScrollMode.AUTO,
                    alignment=ft.MainAxisAlignment.CENTER
                )
                safe_update(stats_container, lambda: None)
                
            except Exception as ex:
                stats_container.content = ft.Text(f"Erro ao carregar resumo: {ex}", color=ft.Colors.RED)
                safe_update(stats_container, lambda: None)
        
        # Configurar eventos
        dd_funcionarios.on_change = atualizar_resumo
        dd_mes.on_change = atualizar_resumo
        dd_ano.on_change = atualizar_resumo
        
        # Inicializar
        atualizar_resumo()
        
        return ft.Column(
            [
                ft.Text("Dashboard & Relatórios", size=18, weight=ft.FontWeight.BOLD),  # Reduzido
                ft.Divider(),
                ft.Text("Detalhes por Funcionário"),
                ft.Column([  # Empilhado para mobile
                    dd_funcionarios,
                    ft.Row([dd_mes, dd_ano], spacing=10)
                ], spacing=10),
                stats_container,
                ft.Divider(),
                ft.Text("Ações", size=16),
                ft.ResponsiveRow(
                    [
                        ft.Container(
                            ft.FilledButton("Atualizar", on_click=atualizar_resumo, expand=True),
                            col={"sm": 12, "md": 3}
                        ),
                        ft.Container(
                            ft.FilledTonalButton("HTML", on_click=lambda _: gerar_relatorio("html"), 
                                               icon=ft.Icons.HTML_OUTLINED, expand=True),
                            col={"sm": 6, "md": 3}
                        ),
                        ft.Container(
                            ft.FilledTonalButton("PDF", on_click=lambda _: gerar_relatorio("pdf"), 
                                               icon=ft.Icons.PICTURE_AS_PDF, expand=True),
                            col={"sm": 6, "md": 3}
                        ),
                        ft.Container(
                            ft.FilledButton("Excel", on_click=lambda _: gerar_relatorio("xlsx"), 
                                          icon=ft.Icons.TABLE_CHART, expand=True,
                                          style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE)),
                            col={"sm": 12, "md": 3}
                        ),
                    ],
                    spacing=10
                ),
                ft.Container(height=10),
                lbl_report_result,
            ],
            scroll=ft.ScrollMode.AUTO
        )
    
    def view_funcionarios():
        # Controles do formulário
        tf_nome = ft.TextField(label="Nome Completo", expand=True)
        tf_cpf = ft.TextField(label="CPF", expand=True)
        tf_pis = ft.TextField(label="PIS", expand=True)
        tf_pin = ft.TextField(label="PIN (Acesso)", password=True, can_reveal_password=True, expand=True)
        tf_cargo = ft.TextField(label="Cargo", expand=True)
        tf_email = ft.TextField(label="Email", expand=True)
        dd_departamento = ft.Dropdown(label="Departamento", expand=True)
        tf_entrada = ft.TextField(label="Entrada Padrão", value="08:00", expand=True)
        tf_saida = ft.TextField(label="Saída Padrão", value="17:00", expand=True)
        chk_ativo = ft.Checkbox(label="Ativo", value=True)
        
        # Diálogo de funcionário
        # Definir largura inicial segura para mobile (menor que 320px)
        initial_width = 300
        
        dlg_funcionario = ft.AlertDialog(
            modal=True,
            title=ft.Text("Funcionário"),
            content=ft.Container(
                content=ft.Column([
                    tf_nome, tf_cpf, tf_pis, tf_pin,
                    tf_cargo, tf_email, dd_departamento,
                    ft.Row([tf_entrada, tf_saida], spacing=10),
                    chk_ativo
                ], tight=True, scroll=ft.ScrollMode.AUTO),
                width=initial_width,
                # Evitar altura fixa para não cortar em telas pequenas horizontalmente
                padding=10
            ),
            actions=[
                ft.TextButton("Cancelar"),
                ft.FilledButton("Salvar"),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        # Variável para armazenar ID em edição
        editing_func_id = None
        
        # Função para abrir diálogo de edição
        def open_edit_dialog(func=None):
            try:
                nonlocal editing_func_id
                print("Tentando abrir diálogo de funcionário...")

                # Garantir que o diálogo anterior esteja fechado
                if getattr(page, 'dialog', None):
                    page.dialog.open = False
                    page.update()

                # Ajustar largura responsiva com segurança
                try:
                    sw = get_screen_width()
                    new_width = min(400, sw - 40) if sw > 40 else 300
                    dlg_funcionario.content.width = new_width
                except Exception as ex_width:
                    print(f"Erro ao ajustar largura: {ex_width}")
                    dlg_funcionario.content.width = 300
                
                if func:
                    dlg_funcionario.title = ft.Text(f"Editar: {func.nome}")
                    tf_nome.value = func.nome or ""
                    tf_cpf.value = func.cpf or ""
                    tf_pis.value = func.pis or ""
                    tf_pin.value = func.pin or ""
                    tf_cargo.value = func.cargo or ""
                    tf_email.value = func.email or ""
                    tf_entrada.value = func.hora_entrada or "08:00"
                    tf_saida.value = func.hora_saida or "17:00"
                    chk_ativo.value = bool(func.ativo)
                    editing_func_id = func.id
                    
                    # Carregar departamentos
                    try:
                        deps = db_manager.obter_departamentos()
                        dd_departamento.options = [
                            ft.dropdown.Option(key=str(d['id']), text=d['nome']) 
                            for d in deps
                        ]
                        if func.departamento:
                            dd_departamento.value = str(func.departamento)
                    except Exception as e:
                        print(f"Erro ao carregar departamentos: {e}")
                else:
                    dlg_funcionario.title = ft.Text("Novo Funcionário")
                    # Limpar campos
                    for field in [tf_nome, tf_cpf, tf_pis, tf_pin, tf_cargo, tf_email]:
                        field.value = ""
                    tf_entrada.value = "08:00"
                    tf_saida.value = "17:00"
                    chk_ativo.value = True
                    dd_departamento.value = None
                    editing_func_id = None
                    
                    # Carregar departamentos
                    try:
                        deps = db_manager.obter_departamentos()
                        dd_departamento.options = [
                            ft.dropdown.Option(key=str(d['id']), text=d['nome']) 
                            for d in deps
                        ]
                    except Exception as e:
                        print(f"Erro ao carregar departamentos: {e}")
                
                # Configurar ações
                dlg_funcionario.actions = [
                    ft.TextButton("Cancelar", on_click=lambda e: fechar_dialogo()),
                    ft.FilledButton("Salvar", on_click=lambda e: salvar_funcionario()),
                ]
                
                # Usar page.open se disponível (Flet >= 0.21.0)
                if hasattr(page, 'open'):
                    page.open(dlg_funcionario)
                else:
                    # Fallback para versões antigas
                    page.dialog = dlg_funcionario
                    dlg_funcionario.open = True
                    safe_page_update(page)
                
            except Exception as e:
                print(f"Erro crítico ao abrir diálogo: {e}")
                show_msg(f"Erro ao abrir diálogo: {e}", ft.Colors.RED)
        
        def fechar_dialogo():
            if hasattr(page, 'close'):
                page.close(dlg_funcionario)
            else:
                dlg_funcionario.open = False
                safe_page_update(page)
        
        def salvar_funcionario():
            try:
                if not tf_nome.value.strip() or not tf_cpf.value.strip():
                    page.snack_bar = ft.SnackBar(
                        ft.Text("Nome e CPF são obrigatórios"),
                        bgcolor=ft.Colors.RED
                    )
                    page.snack_bar.open = True
                    safe_page_update(page)
                    return
                
                funcionario = Funcionario(
                    id=editing_func_id,
                    nome=tf_nome.value.strip(),
                    cpf=tf_cpf.value.strip(),
                    pis=tf_pis.value.strip() or None,
                    pin=tf_pin.value.strip() or None,
                    cargo=tf_cargo.value.strip() or None,
                    email=tf_email.value.strip() or None,
                    ativo=chk_ativo.value,
                    departamento=int(dd_departamento.value) if dd_departamento.value else None,
                    carga_horaria_min=480,
                    hora_entrada=tf_entrada.value.strip() or "08:00",
                    hora_saida=tf_saida.value.strip() or "17:00"
                )
                
                db_manager.salvar_funcionario(funcionario)
                
                fechar_dialogo()
                carregar_tabela()
                
                page.snack_bar = ft.SnackBar(
                    ft.Text("Funcionário salvo com sucesso!"),
                    bgcolor=ft.Colors.GREEN
                )
                page.snack_bar.open = True
                safe_page_update(page)
                
            except Exception as ex:
                page.snack_bar = ft.SnackBar(
                    ft.Text(f"Erro ao salvar funcionário: {str(ex)}"),
                    bgcolor=ft.Colors.RED
                )
                page.snack_bar.open = True
                safe_page_update(page)
        
        # Tabela de funcionários
        tabela = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Nome")),
                ft.DataColumn(ft.Text("CPF")),
                ft.DataColumn(ft.Text("Status")),
                ft.DataColumn(ft.Text("Ações")),
            ],
            rows=[],
            column_spacing=10,  # Reduzido
            heading_row_height=35,  # Reduzido
            data_row_min_height=40,  # Reduzido
            data_row_max_height=40,  # Reduzido
        )
        
        def carregar_tabela(e=None):
            try:
                funcs = db_manager.obter_funcionarios(ativos_only=False)
                tabela.rows.clear()
                
                for f in funcs:
                    tabela.rows.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(f.nome[:20] + "..." if len(f.nome) > 20 else f.nome)),
                                ft.DataCell(ft.Text(f.cpf)),
                                ft.DataCell(
                                    ft.Icon(
                                        ft.Icons.CHECK_CIRCLE if f.ativo else ft.Icons.CANCEL,
                                        color=ft.Colors.GREEN if f.ativo else ft.Colors.RED,
                                        size=20  # Reduzido
                                    )
                                ),
                                ft.DataCell(
                                    ft.Row([
                                        ft.IconButton(
                                            ft.Icons.EDIT,
                                            icon_size=20,  # Reduzido
                                            tooltip="Editar",
                                            on_click=lambda _, func=f: open_edit_dialog(func)
                                        ),
                                        ft.IconButton(
                                            ft.Icons.DELETE,
                                            icon_size=20,  # Reduzido
                                            icon_color=ft.Colors.RED,
                                            tooltip="Excluir",
                                            on_click=lambda _, fid=f.id: confirmar_exclusao(fid)
                                        )
                                    ], spacing=5)  # Reduzido
                                )
                            ]
                        )
                    )
                
                safe_update(tabela, lambda: None)
                
            except Exception as ex:
                print(f"Erro ao carregar tabela: {ex}")
        
        def confirmar_exclusao(func_id):
            def excluir_confirmado(e):
                try:
                    db_manager.excluir_funcionario(func_id)
                    dlg_confirm.open = False
                    carregar_tabela()
                    safe_page_update(page)
                    
                    page.snack_bar = ft.SnackBar(
                        ft.Text("Funcionário excluído com sucesso"),
                        bgcolor=ft.Colors.GREEN
                    )
                    page.snack_bar.open = True
                    safe_page_update(page)
                except Exception as ex:
                    page.snack_bar = ft.SnackBar(
                        ft.Text(f"Erro ao excluir: {str(ex)}"),
                        bgcolor=ft.Colors.RED
                    )
                    page.snack_bar.open = True
                    safe_page_update(page)
            
            dlg_confirm = ft.AlertDialog(
                title=ft.Text("Confirmar Exclusão"),
                content=ft.Text("Tem certeza que deseja excluir este funcionário?"),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda e: setattr(dlg_confirm, 'open', False) or safe_page_update(page)),
                    ft.FilledButton("Excluir", on_click=excluir_confirmado, style=ft.ButtonStyle(bgcolor=ft.Colors.RED)),
                ]
            )
            
            page.dialog = dlg_confirm
            dlg_confirm.open = True
            safe_page_update(page)
        
        # Carregar tabela inicial
        carregar_tabela()
        
        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("Funcionários", size=18, weight=ft.FontWeight.BOLD, expand=True),
                        ft.FilledButton(
                            "Novo Funcionário",
                            icon=ft.Icons.ADD,
                            on_click=lambda _: open_edit_dialog(),
                            style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE)
                        )
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                ),
                ft.Divider(),
                ft.Container(
                    content=tabela,
                    expand=True,
                    border=ft.Border.all(1, ft.Colors.GREY_400),
                    border_radius=8,
                    padding=5,  # Reduzido
                )
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True
        )
    
    def view_auditoria():
        lv_auditoria = ft.ListView(expand=True, spacing=5, padding=5)  # Reduzido
        
        def carregar_logs():
            lv_auditoria.controls.clear()
            try:
                logs = db_manager.obter_auditoria()
                if not logs:
                    lv_auditoria.controls.append(ft.Text("Nenhum registro de auditoria.", italic=True))
                else:
                    for log in logs[:50]:  # Limitar para performance
                        lv_auditoria.controls.append(
                            ft.Card(
                                content=ft.Container(
                                    content=ft.Column([
                                        ft.Text(f"{log['ts']} - {log['usuario']}", size=12, weight=ft.FontWeight.BOLD),
                                        ft.Text(f"Ação: {log['acao']}", size=11),
                                        ft.Text(log['dados'][:100] + "..." if len(log['dados']) > 100 else log['dados'], 
                                               size=10, color=ft.Colors.GREY_700),
                                    ], spacing=2),  # Reduzido
                                    padding=5  # Reduzido
                                )
                            )
                        )
            except Exception as e:
                lv_auditoria.controls.append(ft.Text(f"Erro ao carregar auditoria: {e}", color=ft.Colors.RED))
            safe_update(lv_auditoria, lambda: None)
        
        carregar_logs()
        
        return ft.Column([
            ft.Text("Auditoria", size=18, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            ft.Container(content=lv_auditoria, expand=True)
        ], expand=True)
    
    # Outras views (ajustes, configurações, etc.) - manter estrutura similar
    # ... (mantenha as outras views como view_ajustes, view_departamentos, view_configuracoes)
    
    def view_ajustes():
        # Implementação simplificada similar às outras
        return ft.Column([
            ft.Text("Ajustes", size=18, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            ft.Text("Funcionalidade em desenvolvimento...")
        ])
    
    def view_departamentos():
        tf_novo_dep = ft.TextField(label="Novo Departamento", expand=True)
        lv_deps = ft.ListView(expand=True, spacing=10, padding=10)

        def carregar_deps():
            lv_deps.controls.clear()
            try:
                deps = db_manager.obter_departamentos()
                if not deps:
                    lv_deps.controls.append(ft.Text("Nenhum departamento cadastrado.", italic=True))
                else:
                    for d in deps:
                        lv_deps.controls.append(
                            ft.Card(
                                content=ft.ListTile(
                                    title=ft.Text(d['nome']),
                                    trailing=ft.IconButton(
                                        ft.Icons.DELETE,
                                        icon_color=ft.Colors.RED,
                                        tooltip="Excluir",
                                        on_click=lambda _, did=d['id']: delete_dep(did)
                                    )
                                )
                            )
                        )
            except Exception as e:
                lv_deps.controls.append(ft.Text(f"Erro: {e}", color=ft.Colors.RED))
            safe_update(lv_deps, lambda: None)

        def show_msg(msg, color=ft.Colors.GREEN):
            page.snack_bar = ft.SnackBar(ft.Text(msg), bgcolor=color)
            page.snack_bar.open = True
            page.update()

        def add_dep(e):
            nome = tf_novo_dep.value.strip()
            if not nome:
                show_msg("Digite o nome do departamento", ft.Colors.RED)
                return
            
            try:
                db_manager.salvar_departamento(nome)
                tf_novo_dep.value = ""
                carregar_deps()
                show_msg("Departamento adicionado!", ft.Colors.GREEN)
            except Exception as ex:
                show_msg(f"Erro ao adicionar: {ex}", ft.Colors.RED)

        def delete_dep(did):
            try:
                if db_manager.excluir_departamento(did):
                    carregar_deps()
                    show_msg("Departamento removido!", ft.Colors.GREEN)
                else:
                    show_msg("Erro ao remover departamento", ft.Colors.RED)
            except Exception as ex:
                show_msg(f"Erro: {ex}", ft.Colors.RED)

        carregar_deps()

        return ft.Column([
            ft.Text("Gestão de Departamentos", size=20, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            ft.Row([tf_novo_dep, ft.IconButton(ft.Icons.ADD, on_click=add_dep, icon_color=ft.Colors.BLUE, tooltip="Adicionar")]),
            ft.Container(content=lv_deps, expand=True, border=ft.Border.all(1, ft.Colors.GREY_300), border_radius=5)
        ], expand=True)
    
    def view_configuracoes():
        tf_dia_fechamento = ft.TextField(
            label="Dia de Fechamento", 
            value=db_manager.get_config("dia_fechamento", "1"),
            keyboard_type=ft.KeyboardType.NUMBER,
            helper_text="Ex: 1 para fechar dia 30/31, 21 para fechar dia 20"
        )
        
        def show_msg(msg, color=ft.Colors.GREEN):
            page.snack_bar = ft.SnackBar(ft.Text(msg), bgcolor=color)
            page.snack_bar.open = True
            page.update()

        def salvar_config(e):
            try:
                dia = int(tf_dia_fechamento.value)
                if 1 <= dia <= 28:
                    db_manager.set_config("dia_fechamento", str(dia))
                    show_msg("Configuração salva!", ft.Colors.GREEN)
                else:
                    show_msg("Dia deve ser entre 1 e 28", ft.Colors.RED)
            except ValueError:
                show_msg("Digite um número válido", ft.Colors.RED)
            except Exception as ex:
                show_msg(f"Erro: {ex}", ft.Colors.RED)

        return ft.Column([
            ft.Text("Configurações do Sistema", size=20, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            ft.Text("Período de Apuração do Ponto", size=16, weight=ft.FontWeight.BOLD),
            ft.Text("Defina o dia de início do novo período. O sistema fechará o ponto no dia anterior.", size=12, color=ft.Colors.GREY_700),
            ft.Container(height=10),
            tf_dia_fechamento,
            ft.ElevatedButton("Salvar Configurações", on_click=salvar_config, icon=ft.Icons.SAVE),
        ], expand=True)
    
    def build_admin_dashboard():
        content_admin_area = ft.Container(expand=True)
        
        def set_admin_view(view_idx, update_view=True):
            views = [
                view_dashboard,
                view_funcionarios,
                view_departamentos,
                view_auditoria,
                view_ajustes,
                view_configuracoes
            ]
            
            if 0 <= view_idx < len(views):
                content_admin_area.content = views[view_idx]()
            
            if update_view:
                safe_update(content_admin_area, lambda: None)
        
        # Para mobile, usar NavigationBar em vez de NavigationRail
        screen_width = get_screen_width()
        
        if screen_width < 600:
            # Mobile - NavigationBar na parte inferior
            nav_items = [
                ft.NavigationDestination(icon=ft.Icons.DESCRIPTION, label="Relatórios"),
                ft.NavigationDestination(icon=ft.Icons.PEOPLE, label="Funcionários"),
                ft.NavigationDestination(icon=ft.Icons.BUSINESS, label="Deptos"),
                ft.NavigationDestination(icon=ft.Icons.SECURITY, label="Auditoria"),
                ft.NavigationDestination(icon=ft.Icons.EDIT_CALENDAR, label="Ajustes"),
                ft.NavigationDestination(icon=ft.Icons.SETTINGS, label="Config"),
            ]
            
            nav_bar = ft.NavigationBar(
                destinations=nav_items,
                selected_index=0,
                on_change=lambda e: set_admin_view(e.control.selected_index),
            )
            
            set_admin_view(0, update_view=False)
            
            return ft.Column(
                [
                    ft.Row([
                        ft.Text(f"Admin: {admin_user or ''}", size=16, weight=ft.FontWeight.BOLD, expand=True),
                        ft.FilledTonalButton("Sair", on_click=logout_admin, style=ft.ButtonStyle(color=ft.Colors.RED)),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Divider(),
                    content_admin_area,
                    nav_bar
                ],
                expand=True
            )
        else:
            # Tablet/Desktop - NavigationRail na lateral
            nav_rail = ft.NavigationRail(
                selected_index=0,
                label_type=ft.NavigationRailLabelType.ALL,
                min_width=80,  # Reduzido
                min_extended_width=150,  # Reduzido
                destinations=[
                    ft.NavigationRailDestination(icon=ft.Icons.DESCRIPTION, label="Relatórios"),
                    ft.NavigationRailDestination(icon=ft.Icons.PEOPLE, label="Funcionários"),
                    ft.NavigationRailDestination(icon=ft.Icons.BUSINESS, label="Deptos"),
                    ft.NavigationRailDestination(icon=ft.Icons.SECURITY, label="Auditoria"),
                    ft.NavigationRailDestination(icon=ft.Icons.EDIT_CALENDAR, label="Ajustes"),
                    ft.NavigationRailDestination(icon=ft.Icons.SETTINGS, label="Config"),
                ],
                on_change=lambda e: set_admin_view(e.control.selected_index),
            )
            
            set_admin_view(0, update_view=False)
            
            return ft.Row(
                [
                    nav_rail,
                    ft.VerticalDivider(width=1),
                    ft.Column([
                        ft.Row([
                            ft.Text(f"Admin: {admin_user or ''}", size=16, weight=ft.FontWeight.BOLD, expand=True),
                            ft.FilledTonalButton("Sair", on_click=logout_admin, style=ft.ButtonStyle(color=ft.Colors.RED)),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Divider(),
                        content_admin_area
                    ], expand=True)
                ],
                expand=True
            )
    
    def login_admin(e):
        user = txt_user_admin.value.strip()
        pwd = txt_pass_admin.value.strip()
        
        if not user or not pwd:
            lbl_status_admin.value = "Preencha usuário e senha."
            safe_update(lbl_status_admin, lambda: None)
            return
        
        sucesso, res = auth_service.login(user, pwd)
        if sucesso:
            nonlocal admin_user
            admin_user = user
            container_admin.content = build_admin_dashboard()
            safe_update(container_admin, lambda: None)
            txt_pass_admin.value = ""
        else:
            lbl_status_admin.value = "Login inválido."
            safe_update(lbl_status_admin, lambda: None)
    
    def logout_admin(e):
        nonlocal admin_user
        admin_user = None
        reset_admin_login()
    
    def reset_admin_login(update_view=True):
        container_admin.content = ft.Column(
            [
                ft.Container(height=20),
                ft.Icon(ft.Icons.LOCK_PERSON, size=48, color=ft.Colors.BLUE),  # Reduzido
                ft.Text("Login Administrativo", size=24, weight=ft.FontWeight.BOLD),  # Reduzido
                ft.Container(height=20),
                txt_user_admin,
                ft.Container(height=10),
                txt_pass_admin,
                ft.Container(height=10),
                ft.FilledButton("Login Admin", on_click=login_admin, height=45, width=200),
                ft.Container(height=10),
                lbl_status_admin
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            scroll=ft.ScrollMode.AUTO
        )
        if update_view:
            safe_update(container_admin, lambda: None)
    
    # --- SISTEMA DE ABAS ---
    content_area = ft.Container(expand=True)
    
    def set_tab(index, update_view=True):
        if index == 0:
            content_area.content = ft.Container(
                content=container_ponto,
                padding=10,  # Reduzido
                alignment=ft.Alignment(0, 0),
                expand=True
            )
            btn_tab_ponto.style = ft.ButtonStyle(
                bgcolor=ft.Colors.BLUE_100,
                color=ft.Colors.BLUE_900,
                shape=ft.RoundedRectangleBorder(radius=0)
            )
            btn_tab_admin.style = ft.ButtonStyle(
                bgcolor=ft.Colors.TRANSPARENT,
                color=ft.Colors.GREY_700,
                shape=ft.RoundedRectangleBorder(radius=0)
            )
        else:
            if not admin_user:
                reset_admin_login(update_view=False)
            content_area.content = ft.Container(
                content=container_admin,
                padding=10,  # Reduzido
                expand=True
            )
            btn_tab_ponto.style = ft.ButtonStyle(
                bgcolor=ft.Colors.TRANSPARENT,
                color=ft.Colors.GREY_700,
                shape=ft.RoundedRectangleBorder(radius=0)
            )
            btn_tab_admin.style = ft.ButtonStyle(
                bgcolor=ft.Colors.BLUE_100,
                color=ft.Colors.BLUE_900,
                shape=ft.RoundedRectangleBorder(radius=0)
            )
        
        if update_view:
            safe_update(content_area, lambda: None)
            safe_update(btn_tab_ponto, lambda: None)
            safe_update(btn_tab_admin, lambda: None)
    
    btn_tab_ponto = ft.TextButton(
        "Ponto",
        icon=ft.Icons.ACCESS_TIME,
        on_click=lambda _: set_tab(0),
        height=50,
        expand=True,
        tooltip="Registrar Ponto"
    )
    
    btn_tab_admin = ft.TextButton(
        "Admin",
        icon=ft.Icons.ADMIN_PANEL_SETTINGS,
        on_click=lambda _: set_tab(1),
        height=50,
        expand=True,
        tooltip="Administração"
    )
    
    # --- INICIALIZAÇÃO ---
    reset_ponto_screen(update_view=False)
    reset_admin_login(update_view=False)
    
    # Layout principal com tabs
    main_layout = ft.Column(
        [
            ft.Container(
                content=content_area,
                expand=True
            ),
            ft.Container(
                content=ft.Row(
                    [
                        btn_tab_ponto,
                        ft.VerticalDivider(width=1),
                        btn_tab_admin
                    ],
                    spacing=0,
                    alignment=ft.MainAxisAlignment.SPACE_EVENLY
                ),
                bgcolor=ft.Colors.GREY_50,
                border=ft.Border(top=ft.BorderSide(1, ft.Colors.GREY_300))
            )
        ],
        expand=True,
        spacing=0
    )
    
    page.add(main_layout)
    set_tab(0)

if __name__ == "__main__":
    # Garantir que a pasta de relatórios existe
    assets_path = os.path.join(os.getcwd(), "assets")
    relatorios_path = os.path.join(assets_path, "relatorios")
    os.makedirs(relatorios_path, exist_ok=True)
    
    # Iniciar aplicação
    try:
        print(f"Iniciando app com assets em: {assets_path}")
        ft.run(main, assets_dir=assets_path)
    except Exception as e:
        print(f"Erro ao iniciar aplicação: {e}")
        traceback.print_exc()