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
    from models.entities import RegistroPonto
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
    page.padding = 10
    page.window_min_width = 400
    page.window_min_height = 600
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    
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

    page.on_resize = on_resize

    # --- ELEMENTOS DA ABA PONTO ---
    txt_pin = ft.TextField(
        label="Digite seu PIN ou CPF",
        text_align=ft.TextAlign.CENTER,
        width=300,
        text_size=24,
        keyboard_type=ft.KeyboardType.NUMBER,
        input_filter=ft.InputFilter(allow=True, regex_string=r"[0-9]", replacement_string="")
    )
    
    lbl_status_ponto = ft.Text("", size=16, color=ft.Colors.RED)
    container_ponto = ft.Container()

    # --- ELEMENTOS DA ABA ADMIN ---
    txt_user_admin = ft.TextField(label="Usuário", width=300)
    txt_pass_admin = ft.TextField(label="Senha", password=True, can_reveal_password=True, width=300)
    lbl_status_admin = ft.Text("", color=ft.Colors.RED)
    container_admin = ft.Container()
    
    # Configurações
    tf_empresa = ft.TextField(label="Nome da Empresa")
    tf_cnpj = ft.TextField(label="CNPJ")
    tf_tolerancia = ft.TextField(label="Tolerância (minutos)", keyboard_type=ft.KeyboardType.NUMBER)
    tf_fechamento = ft.TextField(label="Dia de Fechamento", keyboard_type=ft.KeyboardType.NUMBER)
    
    # Dashboard Admin
    dd_funcionarios = ft.Dropdown(label="Funcionário", width=400)
    dd_mes = ft.Dropdown(
        label="Mês",
        width=150,
        options=[ft.dropdown.Option(str(i), str(i)) for i in range(1, 13)],
        value=str(datetime.now().month)
    )
    dd_ano = ft.Dropdown(
        label="Ano",
        width=150,
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
            
            # 1. SnackBar
            page.snack_bar = ft.SnackBar(
                ft.Text(msg_sucesso),
                bgcolor=ft.Colors.GREEN
            )
            page.snack_bar.open = True
            
            # 2. Diálogo de Confirmação (Garantia de visualização)
            def fechar_dlg_sucesso(e):
                dlg_sucesso.open = False
                safe_page_update(page)
            
            dlg_sucesso = ft.AlertDialog(
                title=ft.Text("Sucesso", color=ft.Colors.GREEN),
                content=ft.Text(msg_sucesso, size=16),
                actions=[
                    ft.ElevatedButton("OK", on_click=fechar_dlg_sucesso, bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE)
                ],
                actions_alignment=ft.MainAxisAlignment.CENTER,
            )
            page.overlay.append(dlg_sucesso)
            dlg_sucesso.open = True
            
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
        pin_width = min(400, int(screen_width * 0.8)) if screen_width else 300
        txt_pin.width = pin_width
        
        content = ft.Column(
            [
                ft.Icon(ft.Icons.ACCESS_TIME, size=64, color=ft.Colors.BLUE),
                ft.Text("Ponto Eletrônico", size=30, weight=ft.FontWeight.BOLD),
                ft.Container(height=20),
                txt_pin,
                ft.Container(height=10),
                ft.Button("Entrar", on_click=verificar_pin, height=50, width=200),
                ft.Container(height=10),
                lbl_status_ponto,
                ft.Container(height=20),
                ft.TextButton("Solicitar Abono / Justificar Falta", 
                              icon=ft.Icons.MEDICAL_SERVICES,
                              on_click=abrir_dialog_abono, 
                              style=ft.ButtonStyle(color=ft.Colors.ORANGE_700))
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            scroll=ft.ScrollMode.AUTO if screen_width < 600 else ft.ScrollMode.HIDDEN
        )
        
        container_ponto.content = content
        if update_view:
            safe_update(container_ponto, lambda: None)

    def abrir_dialog_abono(e):
        # Dialog para solicitar abono
        tf_cpf_abono = ft.TextField(label="Seu CPF")
        tf_data_abono = ft.TextField(label="Data (AAAA-MM-DD)", value=date.today().isoformat())
        tf_obs_abono = ft.TextField(label="Motivo / Observação", multiline=True)
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

                # Copiar arquivo se houver (opcional, simples copy)
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
                    "hora": "00:00", # Abono dia todo geralmente
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
                ft.ElevatedButton("Anexar Documento", icon=ft.Icons.UPLOAD_FILE, 
                                  on_click=lambda _: file_picker.pick_files(allow_multiple=False)),
                lbl_file
            ], tight=True),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: setattr(dlg_abono, 'open', False) or safe_page_update(page)),
                ft.TextButton("Enviar", on_click=enviar_solicitacao),
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
                    ft.Text("Use apenas em caso de esquecimento!"),
                    dd_tipo,
                    tf_data,
                    tf_hora
                ], tight=True),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda _: setattr(dlg_retro, 'open', False) or safe_page_update(page)),
                    ft.TextButton("Registrar", on_click=confirmar_retroativo),
                ]
            )
            
            # Usando overlay para garantir que o dialog apareça
            page.overlay.append(dlg_retro)
            dlg_retro.open = True
            safe_page_update(page)

        def open_details_dialog(tipo):
            tf_obs = ft.TextField(label="Observação (Opcional)", expand=True)
            tf_lat = ft.TextField(label="Latitude", read_only=False, expand=True, hint_text="Ex: -23.5505")
            tf_lng = ft.TextField(label="Longitude", read_only=False, expand=True, hint_text="Ex: -46.6333")
            
            file_picker = ft.FilePicker()
            foto_path_storage = {"path": None}
            
            txt_foto_status = ft.Text("Nenhuma foto selecionada", color=ft.Colors.GREY_600, size=12)
            txt_gps_status = ft.Text("Insira as coordenadas GPS manualmente", color=ft.Colors.GREY_600, size=12)
            
            def on_file_selected(e):
                if e.files and len(e.files) > 0:
                    foto_path_storage["path"] = e.files[0].path
                    txt_foto_status.value = f"Foto: {e.files[0].name}"
                    txt_foto_status.color = ft.Colors.GREEN
                    safe_update(txt_foto_status, lambda: None)
                else:
                    foto_path_storage["path"] = None
                    txt_foto_status.value = "Foto cancelada"
                    txt_foto_status.color = ft.Colors.RED
                    safe_update(txt_foto_status, lambda: None)
            
            file_picker.on_result = on_file_selected
            
            def capturar_gps(e):
                """Simplificando para entrada manual apenas"""
                txt_gps_status.value = "Insira as coordenadas GPS manualmente"
                txt_gps_status.color = ft.Colors.ORANGE
                safe_update(txt_gps_status, lambda: None)
            
            def selecionar_foto(e):
                file_picker.pick_files(
                    dialog_title="Selecione uma foto",
                    allowed_extensions=["jpg", "jpeg", "png"],
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_mime_types=["image/jpeg", "image/png", "image/jpg"]
                )
            
            def confirmar_registro(e):
                obs_final = tf_obs.value
                lat_val = tf_lat.value.strip() if tf_lat.value else None
                lng_val = tf_lng.value.strip() if tf_lng.value else None
                foto_val = foto_path_storage.get("path")
                
                registrar_ponto(tipo, obs=obs_final, lat=lat_val, lng=lng_val, foto_path=foto_val)
                dlg_details.open = False
                safe_page_update(page)
            
            def pular_e_registrar(e):
                registrar_ponto(tipo)
                dlg_details.open = False
                safe_page_update(page)

            dlg_details = ft.AlertDialog(
                title=ft.Text(f"Registrar {tipo.replace('_', ' ').title()}"),
                content=ft.Column([
                    ft.Text("Deseja adicionar detalhes?", size=14, weight=ft.FontWeight.BOLD),
                    tf_obs,
                    ft.Divider(),
                    ft.Text("Localização GPS", size=14, weight=ft.FontWeight.BOLD),
                    ft.Row([tf_lat, tf_lng], wrap=False),
                    ft.Container(height=5),
                    ft.Button("Como obter GPS?", icon=ft.Icons.HELP_OUTLINE, on_click=capturar_gps),
                    txt_gps_status,
                    ft.Divider(),
                    ft.Text("Foto do Registro", size=14, weight=ft.FontWeight.BOLD),
                    ft.Row([
                        ft.Button("Selecionar Foto", icon=ft.Icons.PHOTO_LIBRARY, on_click=selecionar_foto),
                    ], wrap=True),
                    txt_foto_status
                ], tight=True, scroll=ft.ScrollMode.AUTO),
                actions=[
                    ft.TextButton("Pular e Registrar", on_click=pular_e_registrar),
                    ft.Button("Confirmar com Detalhes", on_click=confirmar_registro),
                ]
            )
            
            page.overlay.append(file_picker)
            page.dialog = dlg_details
            dlg_details.open = True
            safe_page_update(page)

        # Layout responsivo
        screen_width = get_screen_width()
        
        if screen_width < 600:  # Smartphone
            btn_width = None
            btn_height = 70
            text_size_nome = 24
            text_size_hora = 36
            use_wrap = True
        else:  # Tablet/Desktop
            btn_width = 160
            btn_height = 70
            text_size_nome = 28
            text_size_hora = 40
            use_wrap = False
        
        container_ponto.content = ft.Column(
            [
                ft.Text(f"Olá, {nome}!", size=text_size_nome, weight=ft.FontWeight.BOLD),
                ft.Text(datetime.now().strftime("%H:%M"), size=text_size_hora, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE),
                ft.Container(height=30),
                ft.Row(
                    [
                        ft.Button(
                            "Entrada",
                            icon=ft.Icons.LOGIN,
                            on_click=lambda _: open_details_dialog("ENTRADA"),
                            width=btn_width,
                            expand=btn_width is None,
                            height=btn_height,
                            style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE)
                        ),
                        ft.Button(
                            "Saída Almoço",
                            icon=ft.Icons.RESTAURANT,
                            on_click=lambda _: open_details_dialog("SAIDA_ALMOCO"),
                            width=btn_width,
                            expand=btn_width is None,
                            height=btn_height,
                            style=ft.ButtonStyle(bgcolor=ft.Colors.ORANGE, color=ft.Colors.WHITE)
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    wrap=use_wrap
                ),
                ft.Container(height=10),
                ft.Row(
                    [
                        ft.Button(
                            "Volta Almoço",
                            icon=ft.Icons.RESTAURANT_MENU,
                            on_click=lambda _: open_details_dialog("RETORNO_ALMOCO"),
                            width=btn_width,
                            expand=btn_width is None,
                            height=btn_height,
                            style=ft.ButtonStyle(bgcolor=ft.Colors.ORANGE, color=ft.Colors.WHITE)
                        ),
                        ft.Button(
                            "Saída",
                            icon=ft.Icons.LOGOUT,
                            on_click=lambda _: open_details_dialog("SAIDA_FINAL"),
                            width=btn_width,
                            expand=btn_width is None,
                            height=btn_height,
                            style=ft.ButtonStyle(bgcolor=ft.Colors.RED, color=ft.Colors.WHITE)
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    wrap=use_wrap
                ),
                ft.Container(height=20),
                ft.OutlinedButton(
                    "Esqueci de bater o ponto (Retroativo)",
                    icon=ft.Icons.HISTORY,
                    on_click=open_retroactive_dialog,
                    width=None if screen_width < 600 else 400
                ),
                ft.Container(height=20),
                ft.TextButton("Cancelar", on_click=lambda _: reset_ponto_screen(), icon=ft.Icons.ARROW_BACK)
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            scroll=ft.ScrollMode.AUTO if screen_width < 600 else ft.ScrollMode.HIDDEN
        )
        
        safe_update(container_ponto, lambda: None)

    # --- LÓGICA DE ADMINISTRAÇÃO ---
    def carregar_funcionarios_dropdown():
        try:
            funcs = db_manager.obter_funcionarios(ativos_only=False)
            dd_funcionarios.options = [ft.dropdown.Option(key=str(f.id), text=f.nome) for f in funcs]
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
                # Usar diretório atual de trabalho para garantir compatibilidade com assets_dir do Flet
                assets_dir = os.path.join(os.getcwd(), "assets", "relatorios")
                os.makedirs(assets_dir, exist_ok=True)
                
                assets_path = os.path.join(assets_dir, filename)
                print(f"Gerando relatório: {path} -> {assets_path}")
                shutil.copy(path, assets_path)
                
                # Gerar URL (mantida para referência, mas usaremos arquivo direto)
                url = f"/relatorios/{filename}"
                
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
                
                # Tentar abrir automaticamente com navegador/visualizador padrão
                try:
                    webbrowser.open(assets_path)
                except Exception as ex_open:
                    print(f"Erro ao abrir arquivo automaticamente: {ex_open}")
                
            finally:
                page.remove(progress)
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
        
        # --- GLOBAL STATS SECTION ---
        global_stats_container = ft.Column()
        
        def load_global_stats():
            try:
                from datetime import date, timedelta
                hoje = date.today()
                hoje_str = hoje.isoformat()
                
                # Dados para Pizza (Hoje)
                funcs = db_manager.obter_funcionarios(ativos_only=True)
                total = len(funcs)
                presentes = 0
                for f in funcs:
                    if db_manager.obter_registro_do_dia(f.cpf, hoje_str):
                        presentes += 1
                
                faltas = max(0, total - presentes)
                # Verificar se é fim de semana ou feriado para ajustar faltas (simplificado)
                if hoje.weekday() >= 5 or db_manager.verificar_feriado(hoje_str):
                    faltas = 0 # Não conta falta em folga
                    status_text = "Fim de Semana/Feriado"
                else:
                    status_text = "Dia Útil"

                # Gráfico de Pizza
                pie_chart = ft.PieChart(
                    sections=[
                        ft.PieChartSection(
                            value=presentes,
                            title=f"{presentes}",
                            color=ft.Colors.GREEN,
                            radius=40,
                            title_style=ft.TextStyle(size=12, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)
                        ),
                        ft.PieChartSection(
                            value=faltas,
                            title=f"{faltas}",
                            color=ft.Colors.RED,
                            radius=40,
                            title_style=ft.TextStyle(size=12, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)
                        ),
                    ],
                    sections_space=2,
                    center_space_radius=30,
                    height=150,
                    expand=True
                )
                
                # Legenda Pizza
                legend_pie = ft.Row([
                    ft.Row([ft.Container(width=10, height=10, bgcolor=ft.Colors.GREEN), ft.Text("Presentes", size=12)]),
                    ft.Row([ft.Container(width=10, height=10, bgcolor=ft.Colors.RED), ft.Text("Ausentes", size=12)]),
                ], alignment=ft.MainAxisAlignment.CENTER)

                # Dados para Barras (Últimos 7 dias)
                bar_groups = []
                data_inicio = hoje - timedelta(days=6)
                
                registros_semana = db_manager.obter_registros_por_periodo(data_inicio.isoformat(), hoje_str)
                # Map data -> set(cpf)
                presenca_map = {}
                for r in registros_semana:
                    d = r.get('data')
                    if d:
                        s = presenca_map.get(d, set())
                        s.add(r.get('cpf'))
                        presenca_map[d] = s
                
                for i in range(7):
                    d = data_inicio + timedelta(days=i)
                    d_str = d.isoformat()
                    d_label = d.strftime("%d/%m")
                    qtd = len(presenca_map.get(d_str, set()))
                    
                    bar_groups.append(
                        ft.BarChartGroup(
                            x=i,
                            bar_rods=[
                                ft.BarChartRod(
                                    from_y=0,
                                    to_y=qtd,
                                    width=16,
                                    color=ft.Colors.BLUE,
                                    border_radius=ft.border_radius.all(4)
                                )
                            ]
                        )
                    )

                bar_chart = ft.BarChart(
                    bar_groups=bar_groups,
                    border=ft.border.all(1, ft.Colors.GREY_200),
                    left_axis=ft.ChartAxis(labels_size=30, title=ft.Text("Funcs", size=10)),
                    bottom_axis=ft.ChartAxis(
                        labels=[
                            ft.ChartAxisLabel(
                                value=i,
                                label=ft.Text((data_inicio + timedelta(days=i)).strftime("%d/%m"), size=10)
                            ) for i in range(7)
                        ],
                        labels_size=20,
                    ),
                    horizontal_grid_lines=ft.ChartGridLines(color=ft.Colors.GREY_100, width=1, dash_pattern=[3, 3]),
                    tooltip_bgcolor=ft.Colors.with_opacity(0.8, ft.Colors.GREY_900),
                    max_y=total + 2, # Margem superior
                    height=180,
                )

                global_stats_container.content = ft.Column([
                    ft.Text(f"Visão Geral ({status_text})", weight=ft.FontWeight.BOLD),
                    ft.Row([
                        ft.Column([ft.Text("Hoje", weight=ft.FontWeight.BOLD), pie_chart, legend_pie], expand=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    ]),
                    ft.Divider(),
                    ft.Text("Presença (Últimos 7 dias)", weight=ft.FontWeight.BOLD),
                    ft.Container(content=bar_chart, padding=10),
                ])
                safe_update(global_stats_container, lambda: None)

            except Exception as e:
                print(f"Erro loading global stats: {e}")
                global_stats_container.content = ft.Text(f"Erro ao carregar gráficos: {e}", color=ft.Colors.RED)
                safe_update(global_stats_container, lambda: None)

        # Load initially
        load_global_stats()
        
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
                                    ft.Text(str(value), size=20, weight=ft.FontWeight.BOLD, color=color)
                                ],
                                alignment=ft.MainAxisAlignment.CENTER,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER
                            ),
                            padding=10,
                            width=100,
                            height=80
                        )
                    )
                
                stats_container.content = ft.Row(
                    [
                        make_stat_card("Trabalhadas", f"{totais.get('horas_trabalhadas', 0):.1f}h", ft.Colors.BLUE),
                        make_stat_card("Extras 50%", f"{totais.get('extras_50', 0):.1f}h", ft.Colors.GREEN),
                        make_stat_card("Atrasos", f"{totais.get('atrasos', 0):.1f}h", ft.Colors.ORANGE),
                        make_stat_card("Faltas", str(totais.get('faltas', 0)), ft.Colors.RED),
                        make_stat_card("Banco", f"{totais.get('saldo_banco', 0):.1f}h", ft.Colors.PURPLE),
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

        return ft.Column(
            [
                ft.Text("Dashboard & Relatórios", size=20, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                global_stats_container,
                ft.Divider(),
                ft.Text("Detalhes por Funcionário"),
                ft.Row([dd_funcionarios, dd_mes, dd_ano], wrap=True),
                stats_container,
                ft.Divider(),
                ft.Text("Ações"),
                ft.Row(
                    [
                        ft.Button("Atualizar", on_click=lambda e: (atualizar_resumo(e), load_global_stats())),
                        ft.Button("HTML", on_click=lambda _: gerar_relatorio("html"), icon=ft.Icons.HTML_OUTLINED),
                        ft.Button("PDF", on_click=lambda _: gerar_relatorio("pdf"), icon=ft.Icons.PICTURE_AS_PDF),
                        ft.Button("Excel", on_click=lambda _: gerar_relatorio("xlsx"), icon=ft.Icons.TABLE_CHART, 
                                 style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE)),
                    ],
                    wrap=True
                ),
                ft.Container(height=20),
                lbl_report_result,
            ],
            scroll=ft.ScrollMode.AUTO
        )

    def view_funcionarios():
        from models.entities import Funcionario
        
        # --- Search Bar ---
        tf_busca = ft.TextField(
            label="Buscar por Nome ou CPF", 
            prefix_icon=ft.Icons.SEARCH,
            expand=True
        )
        
        tf_nome = ft.TextField(label="Nome Completo")
        tf_cpf = ft.TextField(label="CPF")
        tf_pis = ft.TextField(label="PIS")
        tf_pin = ft.TextField(label="PIN (Acesso)", password=True, can_reveal_password=True)
        tf_cargo = ft.TextField(label="Cargo")
        tf_email = ft.TextField(label="Email")
        dd_departamento = ft.Dropdown(label="Departamento", options=[])
        tf_entrada = ft.TextField(label="Entrada Padrão (HH:MM)", value="08:00")
        tf_saida = ft.TextField(label="Saída Padrão (HH:MM)", value="17:00")
        chk_ativo = ft.Checkbox(label="Ativo", value=True)
        
        def carregar_deps_dropdown():
            try:
                deps = db_manager.obter_departamentos()
                dd_departamento.options = [ft.dropdown.Option(d['nome']) for d in deps]
                # safe_update(dd_departamento, lambda: None) # Pode falhar se não estiver na arvore ainda
            except Exception as e:
                print(f"Erro loading deps: {e}")

        dlg_funcionario = ft.AlertDialog(
            title=ft.Text("Funcionário"),
            content=ft.Column([
                tf_nome, tf_cpf, tf_pis, tf_pin, 
                tf_cargo, dd_departamento, tf_email,
                ft.Row([tf_entrada, tf_saida]),
                chk_ativo
            ], tight=True, scroll=ft.ScrollMode.AUTO),
        )

        def salvar_func(e):
            try:
                if not tf_nome.value or not tf_cpf.value:
                    page.snack_bar = ft.SnackBar(ft.Text("Nome e CPF são obrigatórios"), bgcolor=ft.Colors.RED)
                    page.snack_bar.open = True
                    safe_page_update(page)
                    return

                f = Funcionario(
                    id=getattr(dlg_funcionario, 'data_id', None),
                    nome=tf_nome.value,
                    cpf=tf_cpf.value,
                    pis=tf_pis.value,
                    pin=tf_pin.value,
                    cargo=tf_cargo.value,
                    email=tf_email.value,
                    ativo=chk_ativo.value,
                    departamento=dd_departamento.value,
                    carga_horaria_min=480, # Mantendo padrão por enquanto, idealmente calcular
                    hora_entrada=tf_entrada.value,
                    hora_saida=tf_saida.value
                )
                
                print(f"Salvando funcionário: {f}")
                db_manager.salvar_funcionario(f)
                dlg_funcionario.open = False
                safe_page_update(page)
                carregar_tabela()
                
                page.snack_bar = ft.SnackBar(ft.Text("Funcionário salvo com sucesso!"), bgcolor=ft.Colors.GREEN)
                page.snack_bar.open = True
                safe_page_update(page)
            except Exception as ex:
                print(f"Erro ao salvar funcionário: {ex}")
                traceback.print_exc()
                page.snack_bar = ft.SnackBar(ft.Text(f"Erro: {ex}"), bgcolor=ft.Colors.RED)
                page.snack_bar.open = True
                safe_page_update(page)

        dlg_funcionario.actions = [
            ft.TextButton("Cancelar", on_click=lambda _: setattr(dlg_funcionario, 'open', False) or safe_page_update(page)),
            ft.TextButton("Salvar", on_click=salvar_func),
        ]

        def open_add(e):
            print("Abrindo dialog novo funcionário...")
            try:
                carregar_deps_dropdown()
                dlg_funcionario.title.value = "Novo Funcionário"
                dlg_funcionario.data_id = None
                tf_nome.value = ""
                tf_cpf.value = ""
                tf_pis.value = ""
                tf_pin.value = ""
                tf_cargo.value = ""
                tf_email.value = ""
                dd_departamento.value = None
                tf_entrada.value = "08:00"
                tf_saida.value = "17:00"
                chk_ativo.value = True
                
                page.dialog = dlg_funcionario
                dlg_funcionario.open = True
                safe_page_update(page)
            except Exception as ex:
                print(f"Erro ao abrir dialog: {ex}")
                page.snack_bar = ft.SnackBar(ft.Text(f"Erro ao abrir: {ex}"), bgcolor=ft.Colors.RED)
                page.snack_bar.open = True
                safe_page_update(page)

        def open_edit(func):
            carregar_deps_dropdown()
            dlg_funcionario.title.value = f"Editar {func.nome}"
            dlg_funcionario.data_id = func.id
            tf_nome.value = func.nome
            tf_cpf.value = func.cpf
            tf_pis.value = func.pis or ""
            tf_pin.value = func.pin or ""
            tf_cargo.value = func.cargo or ""
            tf_email.value = func.email or ""
            dd_departamento.value = func.departamento or None
            tf_entrada.value = func.hora_entrada or "08:00"
            tf_saida.value = func.hora_saida or "17:00"
            chk_ativo.value = bool(func.ativo)
            page.dialog = dlg_funcionario
            dlg_funcionario.open = True
            safe_page_update(page)
        
        def delete_func(fid):
            def confirm_delete(e):
                try:
                    db_manager.excluir_funcionario(fid)
                    confirm_dlg.open = False # Fechar dialog antes de atualizar
                    carregar_tabela()
                    page.snack_bar = ft.SnackBar(ft.Text("Funcionário excluído!"), bgcolor=ft.Colors.GREEN)
                    page.snack_bar.open = True
                    safe_page_update(page)
                except Exception as ex:
                    page.snack_bar = ft.SnackBar(ft.Text(f"Erro: {ex}"), bgcolor=ft.Colors.RED)
                    page.snack_bar.open = True
                    safe_page_update(page)
            
            # Dialog de confirmação
            confirm_dlg = ft.AlertDialog(
                title=ft.Text("Confirmar Exclusão"),
                content=ft.Text("Tem certeza que deseja excluir este funcionário?"),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda _: setattr(confirm_dlg, 'open', False) or safe_page_update(page)),
                    ft.TextButton("Excluir", on_click=confirm_delete, style=ft.ButtonStyle(color=ft.Colors.RED)),
                ]
            )
            page.dialog = confirm_dlg
            confirm_dlg.open = True
            safe_page_update(page)

        tabela = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Nome")),
                ft.DataColumn(ft.Text("CPF")),
                ft.DataColumn(ft.Text("Ativo")),
                ft.DataColumn(ft.Text("Ações")),
            ],
            rows=[]
        )

        def carregar_tabela(e=None):
            try:
                funcs = db_manager.obter_funcionarios(ativos_only=False)
                
                # Filtrar se houver busca
                termo = tf_busca.value.lower() if tf_busca.value else ""
                if termo:
                    funcs = [f for f in funcs if termo in f.nome.lower() or termo in f.cpf]
                
                tabela.rows = []
                for f in funcs:
                    tabela.rows.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(f.nome)),
                                ft.DataCell(ft.Text(f.cpf)),
                                ft.DataCell(ft.Icon(ft.Icons.CHECK if f.ativo else ft.Icons.CLOSE, 
                                                   color=ft.Colors.GREEN if f.ativo else ft.Colors.RED)),
                                ft.DataCell(ft.Row([
                                    ft.IconButton(ft.Icons.EDIT, on_click=lambda _, f=f: open_edit(f)),
                                    ft.IconButton(ft.Icons.DELETE, icon_color=ft.Colors.RED, 
                                                 on_click=lambda _, fid=f.id: delete_func(fid))
                                ]))
                            ]
                        )
                    )
                safe_update(tabela, lambda: None)
            except Exception as e:
                print(f"Erro ao carregar tabela: {e}")

        # Bind search
        tf_busca.on_change = carregar_tabela

        carregar_tabela()
        
        header = ft.Row(
            [
                ft.Text("Gestão de Funcionários", size=20, weight=ft.FontWeight.BOLD),
                ft.Button(
                    "Novo Funcionário",
                    icon=ft.Icons.ADD,
                    on_click=open_add,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        
        return ft.Column(
            [
                header,
                ft.Divider(),
                tf_busca, # Adicionado na UI
                ft.Container(
                    content=tabela,
                    height=400,
                    expand=True,
                    border=ft.border.all(1, ft.Colors.GREY_300),
                    border_radius=5,
                    padding=10
                )
            ],
            scroll=ft.ScrollMode.AUTO
        )

    def view_auditoria():
        lv_auditoria = ft.ListView(expand=True, spacing=10, padding=10)
        
        def carregar_logs():
            lv_auditoria.controls.clear()
            try:
                logs = db_manager.obter_auditoria()
                if not logs:
                    lv_auditoria.controls.append(ft.Text("Nenhum registro de auditoria.", italic=True))
                else:
                    for log in logs:
                        lv_auditoria.controls.append(
                            ft.Container(
                                content=ft.Column([
                                    ft.Text(f"{log['ts']} - {log['usuario']} ({log['acao']})", weight=ft.FontWeight.BOLD),
                                    ft.Text(log['dados'], size=12, color=ft.Colors.GREY_700),
                                    ft.Divider()
                                ]),
                                padding=5
                            )
                        )
            except Exception as e:
                lv_auditoria.controls.append(ft.Text(f"Erro ao carregar auditoria: {e}", color=ft.Colors.RED))
            safe_update(lv_auditoria, lambda: None)

        carregar_logs()
        return ft.Column([
            ft.Text("Auditoria do Sistema", size=20, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            ft.Container(content=lv_auditoria, expand=True)
        ], expand=True)

    def view_ajustes():
        # --- Seção de Ajuste de Ponto (Manual) ---
        carregar_funcionarios_dropdown()
        
        col_registros = ft.ListView(
            height=300, # Altura fixa para scrollar dentro
            spacing=10,
            padding=10,
            auto_scroll=False
        )
        
        # --- Seção de Aprovação de Abonos ---
        lv_pendentes = ft.ListView(height=200, spacing=10, padding=10)
        
        def carregar_pendentes():
            lv_pendentes.controls.clear()
            try:
                ajustes = db_manager.obter_ajustes(status="PENDENTE")
                if not ajustes:
                    lv_pendentes.controls.append(ft.Text("Nenhum abono pendente.", italic=True))
                else:
                    for aj in ajustes:
                        nome_func = aj.get('funcionario_nome', 'Desconhecido')
                        data_req = aj.get('data', '?')
                        tipo = aj.get('tipo', 'Abono')
                        obs = aj.get('observacao', '')
                        path = aj.get('justificativa_path')
                        
                        btn_ver = None
                        if path and os.path.exists(path):
                            btn_ver = ft.IconButton(
                                ft.Icons.ATTACHMENT, 
                                tooltip="Ver Anexo",
                                on_click=lambda _, p=path: webbrowser.open(p)
                            )
                        
                        lv_pendentes.controls.append(
                            ft.Card(
                                content=ft.Container(
                                    content=ft.Column([
                                        ft.ListTile(
                                            leading=ft.Icon(ft.Icons.info),
                                            title=ft.Text(f"{nome_func} - {data_req}"),
                                            subtitle=ft.Text(f"{tipo}: {obs}"),
                                            trailing=btn_ver
                                        ),
                                        ft.Row([
                                            ft.TextButton("Aprovar", on_click=lambda _, aid=aj['id']: processar_ajuste(aid, "APROVADO")),
                                            ft.TextButton("Rejeitar", on_click=lambda _, aid=aj['id']: processar_ajuste(aid, "REJEITADO"), style=ft.ButtonStyle(color=ft.Colors.RED)),
                                        ], alignment=ft.MainAxisAlignment.END)
                                    ]),
                                    padding=10
                                )
                            )
                        )
            except Exception as e:
                lv_pendentes.controls.append(ft.Text(f"Erro ao carregar pendentes: {e}", color=ft.Colors.RED))
            safe_update(lv_pendentes, lambda: None)

        def processar_ajuste(aid, status):
            try:
                db_manager.atualizar_status_ajuste(aid, status, aprovado_por="ADMIN")
                page.snack_bar = ft.SnackBar(ft.Text(f"Ajuste {status}!"), bgcolor=ft.Colors.GREEN if status == "APROVADO" else ft.Colors.RED)
                page.snack_bar.open = True
                safe_page_update(page)
                carregar_pendentes()
            except Exception as e:
                page.snack_bar = ft.SnackBar(ft.Text(f"Erro: {e}"), bgcolor=ft.Colors.RED)
                page.snack_bar.open = True
                safe_page_update(page)

        def carregar_pontos(e):
            col_registros.controls.clear()
            
            try:
                if not dd_funcionarios.value:
                    col_registros.controls.append(ft.Text("Selecione um funcionário", color=ft.Colors.GREY))
                    safe_update(col_registros, lambda: None)
                    return
                
                fid = int(dd_funcionarios.value)
                mes = int(dd_mes.value)
                ano = int(dd_ano.value)
                
                data_inicio = date(ano, mes, 1)
                ultimo_dia = (date(ano, mes, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                
                registros = db_manager.obter_registros_por_periodo(
                    data_inicio.isoformat(),
                    ultimo_dia.isoformat(),
                    funcionario_id=fid
                )
                
                reg_map = {r.get("data"): r for r in registros}
                
                dias_list = []
                curr = data_inicio
                while curr <= ultimo_dia:
                    dias_list.append(curr)
                    curr += timedelta(days=1)
                
                for d in dias_list:
                    d_str = d.isoformat()
                    reg = reg_map.get(d_str, {})
                    
                    def criar_edit_handler(data_ref=d_str, reg_atual=reg):
                        def handler(e):
                            tf_ent = ft.TextField(label="Entrada", value=reg_atual.get("hora_entrada") or "")
                            tf_sai_alm = ft.TextField(label="Saída Almoço", value=reg_atual.get("saida_almoco") or "")
                            tf_ret_alm = ft.TextField(label="Retorno Almoço", value=reg_atual.get("retorno_almoco") or "")
                            tf_sai = ft.TextField(label="Saída", value=reg_atual.get("saida_final") or reg_atual.get("hora_saida") or "")
                            
                            def salvar_ajuste_ponto(e):
                                try:
                                    funcionario = db_manager.obter_funcionario_por_id(fid)
                                    novo_reg = RegistroPonto(
                                        id=reg_atual.get("id"),
                                        funcionario_id=fid,
                                        cpf=funcionario.cpf if funcionario else "",
                                        data=data_ref,
                                        hora_entrada=tf_ent.value,
                                        saida_almoco=tf_sai_alm.value,
                                        retorno_almoco=tf_ret_alm.value,
                                        saida_final=tf_sai.value,
                                        hora_saida=tf_sai.value,
                                        tipo="AJUSTE_MANUAL",
                                        ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        ts_device="manual_admin",
                                        ts_server="manual_admin",
                                        device_id="admin_tablet"
                                    )
                                    db_manager.salvar_registro(novo_reg)
                                    dlg_ajuste.open = False
                                    safe_page_update(page)
                                    carregar_pontos(None)
                                    page.snack_bar = ft.SnackBar(ft.Text("Ajuste salvo!"), bgcolor=ft.Colors.GREEN)
                                    page.snack_bar.open = True
                                    safe_page_update(page)
                                except Exception as ex:
                                    page.snack_bar = ft.SnackBar(ft.Text(f"Erro: {ex}"), bgcolor=ft.Colors.RED)
                                    page.snack_bar.open = True
                                    safe_page_update(page)
                            
                            dlg_ajuste = ft.AlertDialog(
                                title=ft.Text(f"Ajuste - {data_ref}"),
                                content=ft.Column([tf_ent, tf_sai_alm, tf_ret_alm, tf_sai], tight=True),
                                actions=[
                                    ft.TextButton("Cancelar", on_click=lambda _: setattr(dlg_ajuste, 'open', False) or safe_page_update(page)),
                                    ft.TextButton("Salvar", on_click=salvar_ajuste_ponto)
                                ]
                            )
                            page.dialog = dlg_ajuste
                            dlg_ajuste.open = True
                            safe_page_update(page)
                        return handler
                    
                    ent = reg.get("hora_entrada") or "--:--"
                    sa1 = reg.get("saida_almoco") or "--:--"
                    re1 = reg.get("retorno_almoco") or "--:--"
                    sai = reg.get("saida_final") or reg.get("hora_saida") or "--:--"
                    
                    row_card = ft.Card(
                        content=ft.Container(
                            content=ft.Row(
                                [
                                    ft.Text(d.strftime("%d/%m"), weight=ft.FontWeight.BOLD, width=50),
                                    ft.Text(f"E: {ent}", width=80),
                                    ft.Text(f"S: {sa1}", width=80),
                                    ft.Text(f"R: {re1}", width=80),
                                    ft.Text(f"S: {sai}", width=80),
                                    ft.IconButton(ft.Icons.EDIT, on_click=criar_edit_handler())
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                            ),
                            padding=10
                        )
                    )
                    col_registros.controls.append(row_card)
                
                if not dias_list:
                    col_registros.controls.append(ft.Text("Nenhum registro encontrado", color=ft.Colors.GREY))
                
                safe_update(col_registros, lambda: None)
                
            except Exception as ex:
                col_registros.controls.append(ft.Text(f"Erro: {ex}", color=ft.Colors.RED))
                safe_update(col_registros, lambda: None)

        carregar_pendentes()
        
        return ft.Column(
            [
                ft.Text("Solicitações de Abono (Pendentes)", size=20, weight=ft.FontWeight.BOLD),
                ft.Container(content=lv_pendentes, height=200, border=ft.border.all(1, ft.Colors.ORANGE_200), border_radius=5),
                ft.Divider(),
                ft.Text("Ajuste Manual de Ponto", size=20, weight=ft.FontWeight.BOLD),
                ft.Row([dd_funcionarios, dd_mes, dd_ano, ft.Button("Carregar", on_click=carregar_pontos)], wrap=True),
                ft.Divider(),
                ft.Container(
                    content=col_registros,
                    height=300,
                    border=ft.border.all(1, ft.Colors.GREY_300),
                    border_radius=5
                )
            ],
            scroll=ft.ScrollMode.AUTO
        )

    def salvar_configs(e):
        try:
            config.set("APP", "empresa_nome", tf_empresa.value)
            config.set("APP", "empresa_cnpj", tf_cnpj.value)
            config.set("APP", "tolerancia_minutos", tf_tolerancia.value)
            config.set("APP", "fechamento_dia", tf_fechamento.value)
            
            config.save()
            
            page.snack_bar = ft.SnackBar(
                ft.Text("Configurações salvas com sucesso!"),
                bgcolor=ft.Colors.GREEN
            )
            page.snack_bar.open = True
            safe_page_update(page)
        except Exception as ex:
            page.snack_bar = ft.SnackBar(
                ft.Text(f"Erro ao salvar: {ex}"),
                bgcolor=ft.Colors.RED
            )
            page.snack_bar.open = True
            safe_page_update(page)

    def view_departamentos():
        tf_dep_nome = ft.TextField(label="Nome do Departamento", expand=True)
        lv_deps = ft.ListView(height=400, spacing=10, padding=10)
        
        def carregar_deps():
            lv_deps.controls.clear()
            try:
                deps = db_manager.obter_departamentos()
                if not deps:
                    lv_deps.controls.append(ft.Text("Nenhum departamento cadastrado.", italic=True))
                else:
                    for d in deps:
                        lv_deps.controls.append(
                            ft.ListTile(
                                title=ft.Text(d['nome']),
                                trailing=ft.IconButton(
                                    ft.Icons.DELETE, 
                                    icon_color=ft.Colors.RED,
                                    on_click=lambda _, did=d['id']: remover_dep(did)
                                )
                            )
                        )
            except Exception as e:
                lv_deps.controls.append(ft.Text(f"Erro: {e}", color=ft.Colors.RED))
            safe_update(lv_deps, lambda: None)

        def add_dep(e):
            if not tf_dep_nome.value:
                return
            res = db_manager.criar_departamento(tf_dep_nome.value)
            if res != -1:
                tf_dep_nome.value = ""
                page.snack_bar = ft.SnackBar(ft.Text("Departamento adicionado!"), bgcolor=ft.Colors.GREEN)
                carregar_deps()
            else:
                page.snack_bar = ft.SnackBar(ft.Text("Departamento já existe!"), bgcolor=ft.Colors.ORANGE)
            page.snack_bar.open = True
            safe_page_update(page)

        def remover_dep(did):
            if db_manager.excluir_departamento(did):
                page.snack_bar = ft.SnackBar(ft.Text("Departamento removido!"), bgcolor=ft.Colors.GREEN)
                carregar_deps()
            else:
                page.snack_bar = ft.SnackBar(ft.Text("Erro ao remover!"), bgcolor=ft.Colors.RED)
            page.snack_bar.open = True
            safe_page_update(page)

        carregar_deps()
        
        return ft.Column([
            ft.Text("Gestão de Departamentos", size=20, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            ft.Row([tf_dep_nome, ft.IconButton(ft.Icons.ADD, on_click=add_dep)]),
            ft.Container(content=lv_deps, border=ft.border.all(1, ft.Colors.GREY_300), border_radius=5)
        ], scroll=ft.ScrollMode.AUTO)

    def view_configuracoes():
        tf_empresa.value = config.get("APP", "empresa_nome", "")
        tf_cnpj.value = config.get("APP", "empresa_cnpj", "")
        tf_tolerancia.value = config.get("APP", "tolerancia_minutos", "10")
        tf_fechamento.value = config.get("APP", "fechamento_dia", "1")

        # --- Gestão de Feriados ---
        tf_data_feriado = ft.TextField(label="Data (AAAA-MM-DD)", width=150, hint_text="2024-12-25")
        tf_desc_feriado = ft.TextField(label="Descrição", expand=True)
        
        lv_feriados = ft.ListView(height=200, spacing=10, padding=10)

        def carregar_feriados():
            lv_feriados.controls.clear()
            try:
                feriados = db_manager.obter_feriados()
                if not feriados:
                     lv_feriados.controls.append(ft.Text("Nenhum feriado cadastrado.", italic=True, color=ft.Colors.GREY))
                else:
                    for f in feriados:
                        lv_feriados.controls.append(
                            ft.ListTile(
                                title=ft.Text(f"{f['data']} - {f['descricao']}"),
                                trailing=ft.IconButton(
                                    ft.Icons.DELETE, 
                                    icon_color=ft.Colors.RED,
                                    on_click=lambda _, fid=f['id']: remover_feriado_click(fid)
                                )
                            )
                        )
            except Exception as e:
                lv_feriados.controls.append(ft.Text(f"Erro ao carregar: {e}", color=ft.Colors.RED))
            
            safe_update(lv_feriados, lambda: None)

        def adicionar_feriado_click(e):
            if not tf_data_feriado.value or not tf_desc_feriado.value:
                page.snack_bar = ft.SnackBar(ft.Text("Preencha data e descrição"), bgcolor=ft.Colors.RED)
                page.snack_bar.open = True
                safe_page_update(page)
                return
            
            try:
                # Validação simples de formato de data
                datetime.strptime(tf_data_feriado.value, "%Y-%m-%d")
                
                res = db_manager.adicionar_feriado(tf_data_feriado.value, tf_desc_feriado.value)
                if res == -1:
                     page.snack_bar = ft.SnackBar(ft.Text("Feriado já existe nesta data"), bgcolor=ft.Colors.ORANGE)
                else:
                     page.snack_bar = ft.SnackBar(ft.Text("Feriado adicionado"), bgcolor=ft.Colors.GREEN)
                     tf_data_feriado.value = ""
                     tf_desc_feriado.value = ""
                     carregar_feriados()
            except ValueError:
                page.snack_bar = ft.SnackBar(ft.Text("Data inválida! Use o formato AAAA-MM-DD"), bgcolor=ft.Colors.RED)
            except Exception as ex:
                page.snack_bar = ft.SnackBar(ft.Text(f"Erro: {ex}"), bgcolor=ft.Colors.RED)
            
            page.snack_bar.open = True
            safe_page_update(page)

        def remover_feriado_click(fid):
            try:
                if db_manager.remover_feriado(fid):
                     page.snack_bar = ft.SnackBar(ft.Text("Feriado removido"), bgcolor=ft.Colors.GREEN)
                     carregar_feriados()
                else:
                     page.snack_bar = ft.SnackBar(ft.Text("Erro ao remover feriado"), bgcolor=ft.Colors.RED)
            except Exception as ex:
                page.snack_bar = ft.SnackBar(ft.Text(f"Erro: {ex}"), bgcolor=ft.Colors.RED)
            
            page.snack_bar.open = True
            safe_page_update(page)

        carregar_feriados()

        return ft.Column(
            [
                ft.Text("Configurações do Sistema", size=20, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                ft.Text("Dados da Empresa", weight=ft.FontWeight.BOLD),
                tf_empresa,
                tf_cnpj,
                ft.Divider(),
                ft.Text("Regras de Ponto", weight=ft.FontWeight.BOLD),
                tf_tolerancia,
                tf_fechamento,
                ft.Divider(),
                ft.Text("Gestão de Feriados", weight=ft.FontWeight.BOLD),
                ft.Row([tf_data_feriado, tf_desc_feriado, ft.IconButton(ft.Icons.ADD, on_click=adicionar_feriado_click)]),
                ft.Container(
                    content=lv_feriados,
                    border=ft.border.all(1, ft.Colors.GREY_300),
                    border_radius=5,
                    height=200,
                    padding=5
                ),
                ft.Divider(),
                ft.Text("Manutenção do Sistema", weight=ft.FontWeight.BOLD),
                ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text("Backup do Banco de Dados", size=16),
                                ft.Text("Salva uma cópia de segurança dos dados atuais.", size=12, color=ft.Colors.GREY),
                            ]
                        ),
                        ft.ElevatedButton(
                            "Fazer Backup Agora",
                            icon=ft.Icons.BACKUP,
                            on_click=lambda e: fazer_backup_click(e)
                        )
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                ),
                ft.Container(height=20),
                ft.Button("Salvar Configurações Gerais", on_click=salvar_configs, 
                         icon=ft.Icons.SAVE, bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE)
            ],
            scroll=ft.ScrollMode.AUTO
        )

    def fazer_backup_click(e):
        try:
            import shutil
            from pathlib import Path
            
            # Garantir diretório
            backup_path_str = config.get("DATABASE", "backup_dir")
            backup_dir = Path(backup_path_str)
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Nome do arquivo
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"backup_manual_{timestamp}.db"
            dest = backup_dir / filename
            
            # Copiar
            shutil.copy2(db_manager.db_path, dest)
            
            # Limpeza de backups antigos (manter últimos 10)
            backups = sorted(backup_dir.glob("backup_*.db"), key=os.path.getmtime)
            if len(backups) > 10:
                for old in backups[:-10]:
                    try:
                        old.unlink()
                    except:
                        pass

            e.page.snack_bar = ft.SnackBar(
                ft.Text(f"Backup realizado com sucesso!\nArquivo: {filename}"), 
                bgcolor=ft.Colors.GREEN
            )
            e.page.snack_bar.open = True
            e.safe_page_update(page)
            
        except Exception as ex:
            e.page.snack_bar = ft.SnackBar(ft.Text(f"Erro no backup: {ex}"), bgcolor=ft.Colors.RED)
            e.page.snack_bar.open = True
            e.safe_page_update(page)

    def build_admin_dashboard():
        content_admin_area = ft.Container(expand=True)
        
        def set_admin_view(view_idx, update_view=True):
            if view_idx == 0:
                content_admin_area.content = view_dashboard()
            elif view_idx == 1:
                content_admin_area.content = view_funcionarios()
            elif view_idx == 2:
                content_admin_area.content = view_departamentos()
            elif view_idx == 3:
                content_admin_area.content = view_auditoria()
            elif view_idx == 4:
                content_admin_area.content = view_ajustes()
            elif view_idx == 5:
                content_admin_area.content = view_configuracoes()
            
            if update_view:
                safe_update(content_admin_area, lambda: None)

        nav_rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=100,
            min_extended_width=200,
            destinations=[
                ft.NavigationRailDestination(
                    icon=ft.Icons.DESCRIPTION, selected_icon=ft.Icons.DESCRIPTION, label="Relatórios"
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.PEOPLE, selected_icon=ft.Icons.PEOPLE, label="Funcionários"
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.BUSINESS, selected_icon=ft.Icons.BUSINESS, label="Deptos"
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.SECURITY, selected_icon=ft.Icons.SECURITY, label="Auditoria"
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.EDIT_CALENDAR, selected_icon=ft.Icons.EDIT_CALENDAR, label="Ajustes"
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.SETTINGS, selected_icon=ft.Icons.SETTINGS, label="Config"
                ),
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
                        ft.Text(f"Admin Logado: {admin_user or ''}", weight=ft.FontWeight.BOLD),
                        ft.Button("Sair", on_click=logout_admin, color=ft.Colors.RED)
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
                ft.Icon(ft.Icons.LOCK_PERSON, size=64, color=ft.Colors.BLUE),
                ft.Text("Login Administrativo", size=30, weight=ft.FontWeight.BOLD),
                ft.Container(height=20),
                txt_user_admin,
                ft.Container(height=10),
                txt_pass_admin,
                ft.Container(height=10),
                ft.Button("Login Admin", on_click=login_admin, height=50, width=200),
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
                padding=20,
                alignment=ft.Alignment(0, 0)
            )
            btn_tab_ponto.style = ft.ButtonStyle(
                bgcolor=ft.Colors.BLUE_200,
                color=ft.Colors.BLACK,
                shape=ft.RoundedRectangleBorder(radius=0)
            )
            btn_tab_admin.style = ft.ButtonStyle(
                bgcolor=ft.Colors.TRANSPARENT,
                color=ft.Colors.BLACK,
                shape=ft.RoundedRectangleBorder(radius=0)
            )
        else:
            if not admin_user:
                reset_admin_login(update_view=False)
            content_area.content = ft.Container(
                content=container_admin,
                padding=20,
                expand=True
            )
            btn_tab_ponto.style = ft.ButtonStyle(
                bgcolor=ft.Colors.TRANSPARENT,
                color=ft.Colors.BLACK,
                shape=ft.RoundedRectangleBorder(radius=0)
            )
            btn_tab_admin.style = ft.ButtonStyle(
                bgcolor=ft.Colors.BLUE_200,
                color=ft.Colors.BLACK,
                shape=ft.RoundedRectangleBorder(radius=0)
            )
        
        if update_view:
            safe_update(content_area, lambda: None)
            safe_update(btn_tab_ponto, lambda: None)
            safe_update(btn_tab_admin, lambda: None)

    btn_tab_ponto = ft.Button(
        "Registrar Ponto",
        icon=ft.Icons.ACCESS_TIME,
        on_click=lambda _: set_tab(0),
        height=50,
        expand=True
    )
    
    btn_tab_admin = ft.Button(
        "Administração",
        icon=ft.Icons.ADMIN_PANEL_SETTINGS,
        on_click=lambda _: set_tab(1),
        height=50,
        expand=True
    )

    # --- INICIALIZAÇÃO ---
    reset_ponto_screen(update_view=False)
    reset_admin_login(update_view=False)
    
    # Layout principal
    main_layout = ft.Column(
        [
            ft.Row(
                [
                    ft.Container(btn_tab_ponto, expand=True),
                    ft.Container(btn_tab_admin, expand=True)
                ],
                spacing=0
            ),
            ft.Container(
                content=content_area,
                expand=True
            )
        ],
        expand=True
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