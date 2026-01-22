
==============================================================================
GUIA DE INSTALAÇÃO - SISTEMA DE PONTO (PYTHON/FASTAPI)
==============================================================================

IMPORTANTE:
Este sistema foi desenvolvido em PYTHON. Ele NÃO roda em hospedagens que suportam
apenas PHP (como a maioria dos planos básicos de WordPress).

------------------------------------------------------------------------------
VERIFIQUE SE SUA HOSPEDAGEM É COMPATÍVEL
------------------------------------------------------------------------------
Para rodar este sistema, sua hospedagem (UOL Host, HostGator, etc) precisa oferecer:
1. Suporte a "Python App" ou "Aplicações Python" no Painel de Controle (cPanel).
2. Ou acesso SSH (Terminal) para instalar o Python manualmente.
3. Ou ser um servidor VPS/Cloud.

Se o seu plano for "Hospedagem de Sites" básica, provavelmente só suporta PHP.
Nesse caso, você precisará fazer um upgrade para VPS ou usar um host especializado
em Python (como PythonAnywhere, Render ou Railway).

------------------------------------------------------------------------------
COMO INSTALAR (SE TIVER SUPORTE A PYTHON/CPANEL)
------------------------------------------------------------------------------
1. No Painel de Controle, procure por "Setup Python App" ou "Criar Aplicação Python".
2. Crie uma nova aplicação:
   - Versão do Python: 3.9 ou superior
   - Pasta da Aplicação: ponto (ou onde você subiu os arquivos)
   - Arquivo de Inicialização: passenger_wsgi.py
   - Ponto de Entrada (Entry Point): application
3. Faça o upload de todos os arquivos deste pacote para a pasta escolhida.
4. No painel, copie o comando para entrar no ambiente virtual (algo como "source ...").
5. Abra o Terminal (SSH) da hospedagem, cole o comando e rode:
   pip install -r requirements.txt
6. Reinicie a aplicação no painel.

------------------------------------------------------------------------------
ESTRUTURA DE ARQUIVOS
------------------------------------------------------------------------------
/ponto
  ├── passenger_wsgi.py  <- Arquivo que liga o site ao servidor
  ├── web_app.py         <- Código principal do site
  ├── requirements.txt   <- Lista de bibliotecas necessárias
  ├── config.ini         <- Configurações
  ├── database.db        <- Seu banco de dados (dentro de config/)
  └── ... (pastas static, templates, etc)

------------------------------------------------------------------------------
SUPORTE
------------------------------------------------------------------------------
Se precisar de ajuda, entre em contato com o suporte da sua hospedagem e pergunte:
"Meu plano suporta aplicações Python/WSGI com Passenger?"
