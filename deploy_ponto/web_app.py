import uvicorn
from fastapi import FastAPI, Request, Form, HTTPException, Depends, Query, Response, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from typing import Optional, List
from datetime import datetime, date, timedelta
import calendar
import os
import shutil
import csv
from io import StringIO

# Importar lógica do projeto existente
from database.operations import db_manager
from models.entities import Funcionario, RegistroPonto
from services.reports import report_service
from services.auth import auth_service
from services.email_service import EmailService
from config.settings import config
from utils.helpers import FileUtils, SecurityUtils

app = FastAPI(root_path=os.getenv("ROOT_PATH", ""))

# Exception Handler para 403 (Redirecionar para login em vez de JSON cru)
@app.exception_handler(403)
async def custom_403_handler(request: Request, exc: HTTPException):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return RedirectResponse(url=request.url_for("login_page").include_query_params(erro="Acesso negado. Faça login para continuar."), status_code=303)
    return JSONResponse(status_code=403, content={"detail": exc.detail})

# Montar arquivos estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")

# Configuração de Sessão (Chave secreta deve ser segura em produção)
app.add_middleware(SessionMiddleware, secret_key="sua_chave_secreta_aqui")

# Configurar templates
templates = Jinja2Templates(directory="templates")

# Serviços
email_service = EmailService()

# Dependência para verificar login
async def get_current_user(request: Request):
    user = request.session.get("user")
    if not user:
        return None
    return user

async def require_admin(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso não autorizado")
    return user

# Rotas Públicas

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, erro: str = Query(None)):
    return templates.TemplateResponse("login.html", {"request": request, "erro": erro})

@app.get("/registro", response_class=HTMLResponse)
async def registro_page(request: Request):
    return templates.TemplateResponse("registro_usuario.html", {"request": request})

@app.post("/registro")
async def registro(request: Request, cpf: str = Form(...), username: str = Form(...), password: str = Form(...), email: str = Form(...)):
    sucesso, msg = auth_service.register_user(cpf, username, password, email)
    if sucesso:
        return RedirectResponse(url="/login?erro=Cadastro realizado! Faça login.", status_code=303)
    else:
        return templates.TemplateResponse("registro_usuario.html", {
            "request": request,
            "erro": msg,
            "cpf": cpf,
            "username": username,
            "email": email
        })

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    sucesso, resultado = auth_service.login(username, password)
    if sucesso:
        # Verificar se 2FA está habilitado
        use_2fa = config.get("SECURITY", "use_2fa") == "1"
        if use_2fa:
            # Gerar código e "enviar" (logar)
            code = SecurityUtils.gerar_codigo_2fa()
            print(f"\n{'='*40}\nCÓDIGO 2FA PARA {username}: {code}\n{'='*40}\n")
            
            # Guardar estado parcial na sessão
            request.session["pre_2fa_user"] = resultado
            request.session["2fa_code"] = code
            
            return templates.TemplateResponse("login_2fa.html", {"request": request})
            
        request.session["user"] = resultado
        if resultado.get("role") == "admin":
            return RedirectResponse(url=request.url_for("admin_dashboard"), status_code=303)
        else:
            return RedirectResponse(url=request.url_for("portal_funcionario"), status_code=303)
    else:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "erro": resultado.get("error", "Erro ao fazer login")
        })

@app.post("/login/2fa")
async def login_2fa(request: Request, code: str = Form(...)):
    user_data = request.session.get("pre_2fa_user")
    stored_code = request.session.get("2fa_code")
    
    if not user_data or not stored_code:
        # Sessão expirou ou acesso inválido
        return RedirectResponse(url=request.url_for("login_page"), status_code=303)
        
    if code == stored_code:
        # Sucesso 2FA
        request.session["user"] = user_data
        # Limpar dados temporários
        request.session.pop("pre_2fa_user", None)
        request.session.pop("2fa_code", None)
        
        if user_data.get("role") == "admin":
            return RedirectResponse(url="/admin", status_code=303)
        else:
            return RedirectResponse(url="/portal", status_code=303)
    else:
        return templates.TemplateResponse("login_2fa.html", {
            "request": request,
            "erro": "Código de verificação incorreto."
        })

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url=request.url_for("login_page"), status_code=303)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Tela Principal (Kiosk do Ponto)"""
    return templates.TemplateResponse("ponto.html", {"request": request})

@app.post("/verificar_pin", response_class=HTMLResponse)
async def verificar_pin(request: Request, pin: str = Form(...)):
    """Verifica PIN e mostra opções de ponto"""
    funcionario = db_manager.obter_funcionario_por_pin(pin)
    if not funcionario:
        funcionario = db_manager.obter_funcionario_por_cpf(pin)
    
    if not funcionario or not funcionario.ativo:
        return templates.TemplateResponse("ponto.html", {
            "request": request, 
            "erro": "Funcionário não encontrado ou inativo.",
            "pin": pin
        })
    
    # Se achou, mostra tela de registro
    nome_curto = funcionario.nome.split()[0]
    return templates.TemplateResponse("registro.html", {
        "request": request, 
        "funcionario": funcionario,
        "nome": nome_curto,
        "hora_atual": datetime.now().strftime("%H:%M")
    })

@app.post("/registrar_ponto", response_class=HTMLResponse)
async def registrar_ponto(
    request: Request, 
    func_id: int = Form(...), 
    tipo: str = Form(...)
):
    """Registra o ponto efetivamente"""
    try:
        funcionario = db_manager.obter_funcionario_por_id(func_id)
        if not funcionario:
            raise Exception("Funcionário inválido")

        # Lógica de registro (reusando a do DB)
        sucesso, msg = db_manager.registrar_ponto(
            funcionario.cpf, 
            tipo, 
            None, # Foto
            None, # Lat
            None, # Lon
            "Web Interface" # Obs
        )
        
        if sucesso:
            cor = "success"
        else:
            cor = "danger"
            
        return templates.TemplateResponse("resultado.html", {
            "request": request,
            "msg": msg,
            "tipo": tipo,
            "cor": cor,
            "nome": funcionario.nome.split()[0]
        })
        
    except Exception as e:
        return templates.TemplateResponse("ponto.html", {
            "request": request, 
            "erro": f"Erro no sistema: {str(e)}"
        })

# --- ÁREA ADMIN ---

@app.get("/portal", response_class=HTMLResponse)
async def portal_funcionario(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    # Se for admin, pode ir pro admin também
    if user.get("role") == "admin":
        return RedirectResponse(url="/admin", status_code=303)
        
    return templates.TemplateResponse("portal.html", {"request": request, "user": user})

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, user: dict = Depends(require_admin)):
    """Painel Admin - Dashboard"""
    # Lógica do Dashboard (adaptada do Desktop)
    funcionarios_ativos = db_manager.obter_funcionarios(ativos_only=True)
    hoje = date.today()
    hoje_str = hoje.isoformat()
    
    presentes_hoje = len([f for f in funcionarios_ativos if db_manager.obter_registro_do_dia(f.cpf, hoje_str)])
    total_funcionarios = len(funcionarios_ativos)
    
    feriado_hoje = db_manager.verificar_feriado(hoje_str)
    abonados_hoje = db_manager.contar_abonados(hoje_str)
    
    if feriado_hoje or hoje.weekday() >= 5:
        faltas = 0
    else:
        faltas = max(0, total_funcionarios - presentes_hoje - abonados_hoje)
        
    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request, 
        "presentes": presentes_hoje,
        "total": total_funcionarios,
        "faltas": faltas,
        "abonados": abonados_hoje,
        "active_tab": "dashboard",
        "user": user
    })

@app.get("/admin/funcionarios", response_class=HTMLResponse)
async def admin_funcionarios(request: Request, user: dict = Depends(require_admin)):
    """Gestão de Funcionários"""
    funcionarios = db_manager.obter_funcionarios(ativos_only=False)
    departamentos = db_manager.obter_departamentos()
    return templates.TemplateResponse("admin_funcionarios.html", {
        "request": request, 
        "funcionarios": funcionarios,
        "departamentos": departamentos,
        "active_tab": "funcionarios",
        "user": user
    })

@app.post("/admin/funcionario/salvar")
async def salvar_funcionario(
    request: Request,
    id: Optional[str] = Form(None),
    nome: str = Form(...),
    cpf: str = Form(...),
    pis: Optional[str] = Form(None),
    pin: Optional[str] = Form(None),
    cargo: Optional[str] = Form(None),
    departamento: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    carga_horaria: Optional[str] = Form(None),
    hora_entrada: Optional[str] = Form("08:00"),
    hora_saida: Optional[str] = Form("17:00"),
    ativo: bool = Form(False),
    user: dict = Depends(require_admin)
):
    """Salva funcionário"""
    try:
        # Converter ID
        func_id = int(id) if id and id.strip() else None

        # Converter carga horária HH:mm para minutos
        carga_min = 480 # Default 8h
        if carga_horaria:
            try:
                h, m = map(int, carga_horaria.split(':'))
                carga_min = h * 60 + m
            except:
                pass

        f = Funcionario(
            id=func_id,
            nome=nome,
            cpf=cpf,
            pis=pis or "",
            pin=pin or "",
            cargo=cargo or "",
            departamento=departamento or "",
            email=email or "",
            carga_horaria_min=carga_min,
            hora_entrada=hora_entrada or "08:00",
            hora_saida=hora_saida or "17:00",
            ativo=ativo
        )
        
        db_manager.salvar_funcionario(f)
        return RedirectResponse(url=request.url_for("admin_funcionarios"), status_code=303)
    except Exception as e:
        return f"Erro ao salvar: {e}"

@app.post("/admin/funcionario/excluir")
async def excluir_funcionario(
    id: int = Form(...),
    user: dict = Depends(require_admin)
):
    try:
        db_manager.excluir_funcionario(id)
        return RedirectResponse(url=request.url_for("admin_funcionarios"), status_code=303)
    except Exception as e:
        return f"Erro ao excluir: {e}"

@app.get("/admin/registros", response_class=HTMLResponse)
async def admin_registros(
    request: Request,
    data_inicio: str = Query(None),
    data_fim: str = Query(None),
    func_id: int = Query(None),
    user: dict = Depends(require_admin)
):
    """Visualização de Registros"""
    if not data_inicio:
        data_inicio = (date.today() - timedelta(days=7)).isoformat()
    if not data_fim:
        data_fim = date.today().isoformat()
        
    registros = db_manager.obter_registros_por_periodo(data_inicio, data_fim, func_id)
    funcionarios = db_manager.obter_funcionarios(ativos_only=True)
    
    return templates.TemplateResponse("admin_registros.html", {
        "request": request,
        "registros": registros,
        "funcionarios": funcionarios,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "func_id_sel": func_id,
        "active_tab": "registros",
        "user": user
    })

@app.post("/admin/registros/salvar")
async def salvar_registro_admin(
    request: Request,
    id: int = Form(None),
    funcionario_id: int = Form(...),
    data: str = Form(...),
    hora_entrada: str = Form(None),
    saida_almoco: str = Form(None),
    retorno_almoco: str = Form(None),
    saida_final: str = Form(None),
    user: dict = Depends(require_admin)
):
    try:
        # Validar horários vazios como None
        def clean_time(t): return t if t and t.strip() else None
        
        hora_entrada = clean_time(hora_entrada)
        saida_almoco = clean_time(saida_almoco)
        retorno_almoco = clean_time(retorno_almoco)
        saida_final = clean_time(saida_final)

        # Se for edição, buscar existente para preservar campos
        if id:
            reg_dict = db_manager.obter_registro_por_id(id)
            if not reg_dict:
                return "Registro não encontrado"
            
            # Reconstruir objeto
            registro = RegistroPonto(
                id=id,
                funcionario_id=reg_dict['funcionario_id'],
                cpf=reg_dict['cpf'],
                data=reg_dict['data'],
                tipo=reg_dict['tipo'],
                ts=reg_dict['ts'],
                ts_device=reg_dict['ts_device'],
                ts_server=reg_dict['ts_server'],
                device_id=reg_dict['device_id'],
                gps_lat=reg_dict['gps_lat'],
                gps_lng=reg_dict['gps_lng'],
                foto_path=reg_dict['foto_path'],
                ip_addr=reg_dict['ip_addr']
            )
        else:
            # Novo registro
            funcionario = db_manager.obter_funcionario_por_id(funcionario_id)
            if not funcionario:
                return "Funcionário não encontrado"
            
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            registro = RegistroPonto(
                funcionario_id=funcionario_id,
                cpf=funcionario.cpf,
                data=data,
                tipo="MANUAL",
                ts=f"{data} 00:00:00", # Placeholder
                ts_device=now_str,
                ts_server=now_str,
                device_id="admin_web",
                gps_lat=None,
                gps_lng=None,
                foto_path=None,
                ip_addr=request.client.host
            )
        
        # Atualizar horários
        registro.hora_entrada = hora_entrada
        registro.saida_almoco = saida_almoco
        registro.retorno_almoco = retorno_almoco
        registro.saida_final = saida_final
        
        db_manager.salvar_registro(registro)
        
        return RedirectResponse(
            url=str(request.url_for("admin_registros")) + f"?data_inicio={data}&data_fim={data}&func_id={funcionario_id}", 
            status_code=303
        )

    except Exception as e:
        return f"Erro ao salvar registro: {e}"

@app.post("/admin/registros/excluir")
async def excluir_registro_admin(
    request: Request,
    id: int = Form(...),
    user: dict = Depends(require_admin)
):
    try:
        db_manager.excluir_registro(id)
        return RedirectResponse(url=request.url_for("admin_registros"), status_code=303)
    except Exception as e:
        return f"Erro ao excluir: {e}"

@app.get("/admin/ajustes", response_class=HTMLResponse)
async def admin_ajustes(request: Request, status: str = Query(None), user: dict = Depends(require_admin)):
    """Gestão de Solicitações de Ajuste"""
    ajustes = db_manager.obter_ajustes(status=status)
    return templates.TemplateResponse("admin_ajustes.html", {
        "request": request,
        "ajustes": ajustes,
        "active_tab": "ajustes",
        "status_filter": status,
        "user": user
    })

@app.post("/admin/ajustes/aprovar")
async def aprovar_ajuste(
    request: Request, 
    id: int = Form(...),
    user: dict = Depends(require_admin)
):
    db_manager.atualizar_status_ajuste(id, "APROVADO", user["username"])
    return RedirectResponse(url="/admin/ajustes", status_code=303)

@app.post("/admin/ajustes/rejeitar")
async def rejeitar_ajuste(
    request: Request, 
    id: int = Form(...),
    user: dict = Depends(require_admin)
):
    db_manager.atualizar_status_ajuste(id, "REJEITADO", user["username"])
    return RedirectResponse(url="/admin/ajustes", status_code=303)

@app.get("/admin/auditoria", response_class=HTMLResponse)
async def admin_auditoria(request: Request, user: dict = Depends(require_admin)):
    """Logs de Auditoria"""
    auditoria = db_manager.obter_auditoria(limit=100)
    return templates.TemplateResponse("admin_auditoria.html", {
        "request": request,
        "auditoria": auditoria,
        "active_tab": "auditoria",
        "user": user
    })

@app.get("/admin/config", response_class=HTMLResponse)
async def admin_config(request: Request, user: dict = Depends(require_admin)):
    """Configurações"""
    # Construir dicionário unificado
    config_dict = {}
    
    # Do config.ini
    config_dict['ui_theme'] = config.get('UI', 'theme')
    config_dict['backup_dir'] = config.get('DATABASE', 'backup_dir')
    config_dict['smtp_host'] = config.get('EMAIL', 'smtp_host')
    config_dict['smtp_port'] = config.get('EMAIL', 'smtp_port')
    config_dict['smtp_user'] = config.get('EMAIL', 'smtp_user')
    config_dict['smtp_pass'] = config.get('EMAIL', 'smtp_pass')
    config_dict['notify_enabled'] = config.get('EMAIL', 'notify_enabled')
    config_dict['use_2fa'] = config.get('SECURITY', 'use_2fa')
    config_dict['max_login_attempts'] = config.get('SECURITY', 'max_login_attempts')
    config_dict['lockout_minutes'] = config.get('SECURITY', 'lockout_minutes')
    
    # Do banco (prioridade ou complementar)
    config_dict['dia_fechamento'] = db_manager.get_config("dia_fechamento", "1")
    config_dict['tipo_fechamento'] = db_manager.get_config("tipo_fechamento", "MES_ANTERIOR")
    config_dict['empresa_nome'] = db_manager.get_config("empresa_nome", "")
    config_dict['empresa_endereco'] = db_manager.get_config("empresa_endereco", "")
    
    # Passar db_path
    db_path = config.get('DATABASE', 'path')
    
    # Listar backups
    backups = []
    backup_dir = config.get('DATABASE', 'backup_dir')
    if os.path.exists(backup_dir):
        try:
            for f in os.listdir(backup_dir):
                if f.startswith("backup_") and f.endswith(".db"):
                    path = os.path.join(backup_dir, f)
                    size_mb = os.path.getsize(path) / (1024 * 1024)
                    dt_mod = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%d/%m/%Y %H:%M:%S")
                    backups.append({
                        "name": f,
                        "size": f"{size_mb:.2f} MB",
                        "date": dt_mod
                    })
            # Ordenar por data (mais recente primeiro)
            backups.sort(key=lambda x: x['name'], reverse=True)
        except Exception as e:
            print(f"Erro ao listar backups: {e}")

    return templates.TemplateResponse("admin_config.html", {
        "request": request,
        "config": config_dict,
        "db_path": db_path,
        "backups": backups,
        "active_tab": "config",
        "user": user
    })

@app.post("/admin/backup/criar")
async def criar_backup(request: Request, user: dict = Depends(require_admin)):
    try:
        FileUtils.fazer_backup_automatico()
        return RedirectResponse(url=str(request.url_for("admin_config")) + "?tab=db", status_code=303)
    except Exception as e:
        return f"Erro ao criar backup: {e}"

@app.post("/admin/backup/restaurar")
async def restaurar_backup(
    request: Request, 
    filename: str = Form(...),
    user: dict = Depends(require_admin)
):
    try:
        backup_dir = config.get('DATABASE', 'backup_dir')
        backup_path = os.path.join(backup_dir, filename)
        
        if not os.path.exists(backup_path):
            return "Arquivo de backup não encontrado"
            
        # Fazer backup do atual antes de restaurar (segurança)
        FileUtils.fazer_backup_automatico()
        
        # Restaurar
        db_path = config.get('DATABASE', 'path')
        shutil.copy2(backup_path, db_path)
        
        return RedirectResponse(url="/admin/config?tab=db", status_code=303)
    except Exception as e:
        return f"Erro ao restaurar backup: {e}"

@app.post("/admin/backup/excluir")
async def excluir_backup(
    request: Request, 
    filename: str = Form(...),
    user: dict = Depends(require_admin)
):
    try:
        backup_dir = config.get('DATABASE', 'backup_dir')
        backup_path = os.path.join(backup_dir, filename)
        
        if os.path.exists(backup_path):
            os.remove(backup_path)
            
        return RedirectResponse(url="/admin/config?tab=db", status_code=303)
    except Exception as e:
        return f"Erro ao excluir backup: {e}"

@app.post("/admin/backup/upload")
async def upload_backup(
    request: Request, 
    file: UploadFile = File(...),
    user: dict = Depends(require_admin)
):
    try:
        if not file.filename.endswith(".db"):
             return "Arquivo inválido. Deve ser .db"
             
        backup_dir = config.get('DATABASE', 'backup_dir')
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
            
        # Adicionar timestamp para evitar conflito
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = f"upload_{ts}_{file.filename}"
        path = os.path.join(backup_dir, safe_name)
        
        with open(path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        return RedirectResponse(url="/admin/config?tab=db", status_code=303)
    except Exception as e:
        return f"Erro ao fazer upload: {e}"

@app.post("/admin/config/salvar")
async def salvar_config(
    request: Request,
    dia_fechamento: str = Form(None),
    tipo_fechamento: str = Form(None),
    ui_theme: str = Form(None),
    backup_dir: str = Form(None),
    smtp_host: str = Form(None),
    smtp_port: str = Form(None),
    smtp_user: str = Form(None),
    smtp_pass: str = Form(None),
    notify_enabled: str = Form(None),
    use_2fa: str = Form(None),
    max_login_attempts: str = Form(None),
    lockout_minutes: str = Form(None),
    empresa_nome: str = Form(None),
    empresa_endereco: str = Form(None),
    user: dict = Depends(require_admin)
):
    """Salva configurações"""
    # Salvar no Banco
    if dia_fechamento: db_manager.set_config("dia_fechamento", dia_fechamento)
    if empresa_nome: db_manager.set_config("empresa_nome", empresa_nome)
    if empresa_endereco: db_manager.set_config("empresa_endereco", empresa_endereco)
    
    # Salvar no config.ini
    if ui_theme: config.set('UI', 'theme', ui_theme)
    if backup_dir: config.set('DATABASE', 'backup_dir', backup_dir)
    if smtp_host: config.set('EMAIL', 'smtp_host', smtp_host)
    if smtp_port: config.set('EMAIL', 'smtp_port', smtp_port)
    if smtp_user: config.set('EMAIL', 'smtp_user', smtp_user)
    if smtp_pass: config.set('EMAIL', 'smtp_pass', smtp_pass)
    
    # Checkbox vem como '1' ou None/missing
    config.set('EMAIL', 'notify_enabled', '1' if notify_enabled else '0')
    config.set('SECURITY', 'use_2fa', '1' if use_2fa else '0')
    
    if max_login_attempts: config.set('SECURITY', 'max_login_attempts', max_login_attempts)
    if lockout_minutes: config.set('SECURITY', 'lockout_minutes', lockout_minutes)
    
    config.save()
    
    return RedirectResponse(url=f"/admin/config?tab={last_tab}&msg=Configurações salvas com sucesso", status_code=303)

@app.post("/admin/config/test-email")
async def test_email(
    request: Request,
    to_email: str = Form(...),
    user: dict = Depends(require_admin)
):
    try:
        success = email_service.send_test_email(to_email)
        msg = "E-mail enviado com sucesso!" if success else "Falha ao enviar e-mail. Verifique os logs."
        return RedirectResponse(url=f"/admin/config?tab=email&msg={msg}", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/admin/config?tab=email&msg=Erro: {e}", status_code=303)

@app.get("/admin/relatorios", response_class=HTMLResponse)
async def admin_relatorios(request: Request, user: dict = Depends(require_admin)):
    """Relatórios"""
    funcionarios = db_manager.obter_funcionarios(ativos_only=True)
    hoje = date.today()
        
    return templates.TemplateResponse("admin_relatorios.html", {
        "request": request,
        "funcionarios": funcionarios,
        "hoje": hoje,
        "active_tab": "relatorios",
        "user": user
    })

@app.post("/admin/relatorios/gerar")
async def gerar_relatorio(
    request: Request,
    mes: int = Form(...),
    ano: int = Form(...),
    funcionario_id: int = Form(...),
    formato: str = Form(...), # pdf, excel, html
    user: dict = Depends(require_admin)
):
    try:
        if formato == "pdf":
            pdf_path = report_service.gerar_espelho_ponto_pdf(funcionario_id, ano, mes)
            filename = os.path.basename(pdf_path)
            return FileResponse(
                path=pdf_path, 
                filename=filename, 
                media_type='application/pdf'
            )
        elif formato == "excel":
            xlsx_path = report_service.gerar_espelho_ponto_xlsx(funcionario_id, ano, mes)
            filename = os.path.basename(xlsx_path)
            return FileResponse(
                path=xlsx_path,
                filename=filename,
                media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        elif formato == "html":
            # Gerar DTO e renderizar template de visualização
            relatorio = report_service.gerar_relatorio_mensal(funcionario_id, ano, mes)
            data_inicio, data_fim = report_service._obter_periodo_fechamento(ano, mes)
            
            return templates.TemplateResponse("relatorio_view.html", {
                "request": request,
                "relatorio": relatorio,
                "data_inicio": data_inicio,
                "data_fim": data_fim,
                "user": user
            })
            
    except Exception as e:
        return templates.TemplateResponse("admin_relatorios.html", {
            "request": request,
            "funcionarios": db_manager.obter_funcionarios(ativos_only=True),
            "hoje": date.today(),
            "active_tab": "relatorios",
            "erro": f"Erro ao gerar relatório: {str(e)}",
            "user": user
        })

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
