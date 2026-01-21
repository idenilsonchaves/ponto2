import flet as ft
from datetime import datetime
import sys
import os

# Adicionar diretório atual ao path para importar módulos do projeto
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.operations import db_manager
from models.entities import RegistroPonto

def main(page: ft.Page):
    page.title = "Ponto Eletrônico - Tablet"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.padding = 20

    # Função auxiliar para obter largura da tela de forma segura
    def get_screen_width():
        try:
            if hasattr(page, 'width') and page.width:
                return page.width
        except (RuntimeError, AttributeError):
            pass
        return 800  # Default para tablets

    # Estado da aplicação
    current_funcionario = None

    # Elementos UI - Responsivo
    txt_pin = ft.TextField(
        label="Digite seu PIN", 
        password=True, 
        can_reveal_password=True, 
        text_align=ft.TextAlign.CENTER,
        width=300,  # Será ajustado dinamicamente no reset_screen
        text_size=24,
        keyboard_type=ft.KeyboardType.NUMBER
    )
    
    lbl_status = ft.Text("", size=16, color=ft.Colors.RED)
    lbl_welcome = ft.Text("", size=20, weight=ft.FontWeight.BOLD)
    
    def on_pin_change(e):
        lbl_status.value = ""
        lbl_status.update()

    txt_pin.on_change = on_pin_change

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

    def registrar_ponto(tipo_registro, custom_datetime=None):
        nonlocal current_funcionario
        if not current_funcionario:
            return

        cpf = current_funcionario.cpf
        now = custom_datetime if custom_datetime else datetime.now()
        data = now.strftime("%Y-%m-%d")
        hora = now.strftime("%H:%M:%S")

        # Validações (apenas para registros em tempo real; retroativos podem quebrar a sequência)
        if not custom_datetime:
            valido, msg = validar_sequencia_registros(cpf, data, tipo_registro)
            if not valido:
                page.snack_bar = ft.SnackBar(
                    ft.Text(f"Erro: {msg}"),
                    bgcolor=ft.Colors.RED
                )
                page.snack_bar.open = True
                page.update()
                return
            
            if verificar_duplicata(cpf, data, hora, tipo_registro):
                page.snack_bar = ft.SnackBar(
                    ft.Text("Atenção: Registro já feito neste minuto!"),
                    bgcolor=ft.Colors.ORANGE
                )
                page.snack_bar.open = True
                page.update()
                return

        # Criar registro
        registro = RegistroPonto(
            funcionario_id=current_funcionario.id,
            cpf=cpf,
            data=data,
            tipo=tipo_registro,
            ts=f"{data} {hora}",
            ts_device=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ts_server=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            device_id="tablet_android"
        )

        # Definir horário baseado no tipo
        if tipo_registro == "ENTRADA":
            registro.hora_entrada = hora
        elif tipo_registro == "SAIDA_ALMOCO":
            registro.saida_almoco = hora
        elif tipo_registro == "RETORNO_ALMOCO":
            registro.retorno_almoco = hora
        elif tipo_registro == "SAIDA_FINAL":
            registro.saida_final = hora
            registro.hora_saida = hora

        try:
            # Verificar se já existe registro no dia
            registro_existente = db_manager.obter_registro_do_dia(cpf, data)
            
            if registro_existente:
                registro.id = registro_existente["id"]
                # Preservar dados anteriores
                registro.hora_entrada = registro.hora_entrada or registro_existente.get("hora_entrada")
                registro.saida_almoco = registro.saida_almoco or registro_existente.get("saida_almoco")
                registro.retorno_almoco = registro.retorno_almoco or registro_existente.get("retorno_almoco")
                registro.saida_final = registro.saida_final or registro_existente.get("saida_final")
                registro.hora_saida = registro.hora_saida or registro_existente.get("hora_saida")
                
                # Preservar metadados
                registro.foto_path = registro.foto_path or registro_existente.get("foto_path")
                registro.gps_lat = registro.gps_lat or registro_existente.get("gps_lat")
                registro.gps_lng = registro.gps_lng or registro_existente.get("gps_lng")
                registro.ip_addr = registro.ip_addr or registro_existente.get("ip_addr")

            db_manager.salvar_registro(registro)
            
            # Feedback Visual
            page.snack_bar = ft.SnackBar(
                ft.Text(f"{tipo_registro.replace('_', ' ').title()} registrado com sucesso às {hora}!"),
                bgcolor=ft.Colors.GREEN
            )
            page.snack_bar.open = True
            
            # Voltar para tela inicial após delay
            reset_screen()
            
        except Exception as e:
            page.snack_bar = ft.SnackBar(
                ft.Text(f"Erro ao registrar: {str(e)}"),
                bgcolor=ft.Colors.RED
            )
            page.snack_bar.open = True
            page.update()

    def verificar_pin(e):
        nonlocal current_funcionario
        pin = txt_pin.value
        if not pin:
            lbl_status.value = "Por favor, digite o PIN."
            lbl_status.update()
            return

        funcionario = db_manager.obter_funcionario_por_pin(pin)
        if not funcionario:
            # Fallback CPF
            funcionario = db_manager.obter_funcionario_por_cpf(pin)

        if funcionario and funcionario.ativo:
            current_funcionario = funcionario
            show_actions_screen()
        else:
            lbl_status.value = "Funcionário não encontrado ou inativo."
            lbl_status.update()
            txt_pin.value = ""
            txt_pin.focus()
            txt_pin.update()

    def reset_screen():
        nonlocal current_funcionario
        current_funcionario = None
        txt_pin.value = ""
        lbl_status.value = ""
        
        # Ajustar largura do PIN baseado no tamanho da tela
        try:
            screen_width = get_screen_width()
        except:
            screen_width = 800  # Default se não conseguir obter
        
        pin_width = min(400, int(screen_width * 0.8)) if screen_width else 300
        txt_pin.width = pin_width
        
        page.clean()
        page.add(
            ft.Column(
                [
                    ft.Icon(ft.Icons.ACCESS_TIME, size=64, color=ft.Colors.BLUE),
                    ft.Text("Ponto Eletrônico", size=30, weight=ft.FontWeight.BOLD),
                    ft.Container(height=20),
                    txt_pin,
                    ft.Container(height=10),
                    ft.ElevatedButton(
                        "Entrar", 
                        on_click=verificar_pin,
                        style=ft.ButtonStyle(
                            shape=ft.RoundedRectangleBorder(radius=8),
                            padding=20,
                        ),
                        width=200
                    ),
                    ft.Container(height=10),
                    lbl_status
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                scroll=ft.ScrollMode.AUTO if screen_width < 600 else ft.ScrollMode.HIDDEN
            )
        )
        page.update()

    def show_actions_screen():
        page.clean()
        
        # Obter nome curto
        nome = current_funcionario.nome.split()[0]
        
        # Layout responsivo
        try:
            screen_width = get_screen_width()
        except:
            screen_width = 800  # Default se não conseguir obter
        
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
        
        # Botão de registro retroativo
        def open_retroactive_dialog(e):
            # Elementos do Dialog
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
                    # Parse data/hora
                    d_str = tf_data.value
                    h_str = tf_hora.value
                    dt_full = datetime.strptime(f"{d_str} {h_str}", "%d/%m/%Y %H:%M")
                    
                    # Chama registrar_ponto com data/hora customizada (sem validações de sequência)
                    registrar_ponto(dd_tipo.value, custom_datetime=dt_full)
                    dlg_retro.open = False
                    page.update()
                except ValueError:
                    page.snack_bar = ft.SnackBar(
                        ft.Text("Formato de data/hora inválido! Use DD/MM/AAAA e HH:MM"),
                        bgcolor=ft.Colors.RED
                    )
                    page.snack_bar.open = True
                    page.update()
                except Exception as ex:
                    page.snack_bar = ft.SnackBar(
                        ft.Text(f"Erro: {ex}"),
                        bgcolor=ft.Colors.RED
                    )
                    page.snack_bar.open = True
                    page.update()
            
            dlg_retro = ft.AlertDialog(
                title=ft.Text("Registro Retroativo"),
                content=ft.Column(
                    [
                        ft.Text("Use apenas em caso de esquecimento!"),
                        dd_tipo,
                        tf_data,
                        tf_hora,
                    ],
                    tight=True,
                ),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda _: setattr(dlg_retro, "open", False) or page.update()),
                    ft.TextButton("Registrar", on_click=confirmar_retroativo),
                ],
            )
            page.dialog = dlg_retro
            dlg_retro.open = True
            page.update()
        
        page.add(
            ft.Column(
                [
                    ft.Text(f"Olá, {nome}!", size=text_size_nome, weight=ft.FontWeight.BOLD),
                    ft.Text(datetime.now().strftime("%d/%m/%Y"), size=16),
                    ft.Text(datetime.now().strftime("%H:%M"), size=text_size_hora, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE),
                    ft.Container(height=30),
                    
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                "Entrada", 
                                icon=ft.Icons.LOGIN,
                                on_click=lambda _: registrar_ponto("ENTRADA"),
                                width=btn_width,
                                expand=btn_width is None,
                                height=btn_height,
                                style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE)
                            ),
                            ft.ElevatedButton(
                                "Saída Almoço", 
                                icon=ft.Icons.RESTAURANT,
                                on_click=lambda _: registrar_ponto("SAIDA_ALMOCO"),
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
                            ft.ElevatedButton(
                                "Volta Almoço", 
                                icon=ft.Icons.RESTAURANT_MENU,
                                on_click=lambda _: registrar_ponto("RETORNO_ALMOCO"),
                                width=btn_width,
                                expand=btn_width is None,
                                height=btn_height,
                                style=ft.ButtonStyle(bgcolor=ft.Colors.ORANGE, color=ft.Colors.WHITE)
                            ),
                            ft.ElevatedButton(
                                "Saída", 
                                icon=ft.Icons.LOGOUT,
                                on_click=lambda _: registrar_ponto("SAIDA_FINAL"),
                                width=btn_width,
                                expand=btn_width is None,
                                height=btn_height,
                                style=ft.ButtonStyle(bgcolor=ft.Colors.RED, color=ft.Colors.WHITE)
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        wrap=use_wrap
                    ),
                    ft.Container(height=40),
                    ft.OutlinedButton(
                        "Esqueci de bater o ponto (Retroativo)",
                        icon=ft.Icons.HISTORY,
                        on_click=open_retroactive_dialog,
                    ),
                    ft.Container(height=20),
                    ft.TextButton("Cancelar / Sair", on_click=lambda _: reset_screen(), icon=ft.Icons.ARROW_BACK)
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                scroll=ft.ScrollMode.AUTO if screen_width < 600 else ft.ScrollMode.HIDDEN
            )
        )
        page.update()

    # Iniciar na tela de PIN
    reset_screen()

if __name__ == "__main__":
    # Para rodar como app desktop durante desenvolvimento
    # Removido assets_dir para mobile build se não existir
    ft.app(target=main)
